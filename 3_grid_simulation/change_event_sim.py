"""Change Event Capacity Simulator.

A SimPy discrete-event model of network change-event teams working evening
change windows at utility sites. One team is a field engineer on site, a
bridge lead and an implementation engineer. Sites arrive "change-ready",
wait for a team, and are visited one or more times until closed.

Every numeric default in `Params` is a PLANNING ASSUMPTION. None of them is a
benchmark. Replace them with `fit_from_event_log()` output when field data
exists.

The simulation clock counts change-window minutes only. Window k falls on
calendar day (k // windows_per_week) * 7 + (k % windows_per_week). The
administrative tail (prep and reporting) is paid daytime work and does not
consume window capacity.

Randomness: each site owns one numpy Generator seeded from (seed, site_id).
Per-site draws (class, devices, tool time) happen once; per-visit draws
happen in a fixed order with fixed counts, so the same site sees the same
draws in every scenario (common random numbers). Event outcomes compare a
uniform against a threshold, so lowering a probability can only switch an
event off, never on.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass, field, asdict, replace
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import simpy

CAUSES = ["packet", "gonogo", "remediation", "access", "hardware"]
CAUSE_LABELS = {
    "packet": "Packet defect (walkdown / package / manifest mismatch)",
    "gonogo": "Go/no-go not ready (ops center, renewables center, firewall ticket)",
    "remediation": "Showstopping remediation not complete or unverified",
    "access": "Access failure (escort, badge, key, gate code)",
    "hardware": "Hardware or tools missing or damaged",
    "qa_rework": "Quality rework (post-photo corrective actions)",
    "admin_tail": "Administrative tail (prep, reports, uploads)",
    "idle": "Team idle (no change-ready site or window too short)",
}
SITE_CLASSES = ["standard", "renewables", "complex", "logical"]

EVENT_VOCAB = [
    "depart", "check_in", "gate_start", "gate_end", "packet_issue",
    "gonogo_wait_start", "gonogo_wait_end", "remediation_block", "access_issue",
    "hardware_issue", "resumed", "no_go", "device_done", "renewables_call", "qa_rework",
    "closure_start", "checkout", "revisit_scheduled", "prep_start", "prep_end",
    "report_start", "report_sent",
]


# --------------------------------------------------------------------------- #
# Parameters
# --------------------------------------------------------------------------- #
@dataclass
class Params:
    """All model parameters. Every default is a planning assumption."""

    # Calendar
    windows_per_week: int = 4
    window_hours: float = 8.0
    horizon_weeks: int = 16
    min_start_minutes: float = 180.0  # if less remains in the window, wait for the next one

    # Arrivals
    arrivals_per_week: float = 4.0
    initial_backlog: int = 25
    backlog_age_weeks: float = 8.0  # backlog ready_times spread over this many prior weeks

    # Rates, $/hour, planning assumptions
    rate_fe: float = 95.0
    rate_bl: float = 85.0
    rate_ie: float = 125.0

    # Site classes
    class_mix: Dict[str, float] = field(default_factory=lambda: {
        "standard": 0.70, "renewables": 0.15, "complex": 0.10, "logical": 0.05})
    devices_tri: Dict[str, tuple] = field(default_factory=lambda: {
        "standard": (8, 15, 25), "renewables": (4, 8, 15),
        "complex": (20, 35, 60), "logical": (5, 10, 20)})
    complex_multiplier: float = 1.5  # gate and closure times for complex sites

    # Time components, minutes
    travel_median: float = 60.0
    travel_sigma: float = 0.5
    gate_tri: tuple = (45, 70, 120)
    tool_per_device_median: float = 12.0
    tool_sigma: float = 0.4
    renewables_call_tri: tuple = (3, 5, 10)
    rework_p: float = 0.30
    rework_tri: tuple = (10, 20, 45)
    closure_tri: tuple = (45, 75, 120)
    prep_bl_tri: tuple = (90, 150, 240)
    prep_ie_tri: tuple = (60, 90, 150)
    report_tri: tuple = (60, 90, 180)

    # Wait and defect events, evaluated in CAUSES order at the gate
    event_p: Dict[str, float] = field(default_factory=lambda: {
        "packet": 0.20, "gonogo": 0.15, "remediation": 0.10,
        "access": 0.20, "hardware": 0.12})
    event_abort: Dict[str, float] = field(default_factory=lambda: {
        "packet": 0.30, "gonogo": 0.20, "remediation": 0.60,
        "access": 0.25, "hardware": 0.35})
    delay_tri: Dict[str, tuple] = field(default_factory=lambda: {
        "packet": (30, 60, 120), "remediation": (30, 60, 120),
        "access": (20, 45, 90), "hardware": (30, 60, 120)})
    gonogo_median: float = 45.0
    gonogo_sigma: float = 0.5

    # AI lever
    reduction: float = 0.25        # applied to event and rework probabilities
    admin_reduction: float = 0.40  # applied to the administrative tail

    # Derived
    @property
    def window_minutes(self) -> float:
        return self.window_hours * 60.0

    @property
    def total_windows(self) -> int:
        return self.windows_per_week * self.horizon_weeks

    @property
    def total_minutes(self) -> float:
        return self.total_windows * self.window_minutes

    @property
    def team_rate(self) -> float:
        return self.rate_fe + self.rate_bl + self.rate_ie

    def validate(self) -> None:
        total = sum(self.class_mix.get(c, 0.0) for c in SITE_CLASSES)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"class_mix must sum to 1, got {total:.4f}")
        for c in CAUSES:
            if not 0.0 <= self.event_p[c] <= 1.0 or not 0.0 <= self.event_abort[c] <= 1.0:
                raise ValueError(f"event probabilities for {c} must be in [0, 1]")

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, default=list)


@dataclass
class Scenario:
    name: str
    teams: int = 1
    ai_lever: bool = False


DEFAULT_SCENARIOS = [
    Scenario("1 team baseline", teams=1, ai_lever=False),
    Scenario("1 team + AI lever", teams=1, ai_lever=True),
    Scenario("2 teams baseline", teams=2, ai_lever=False),
]


# --------------------------------------------------------------------------- #
# Calendar helpers
# --------------------------------------------------------------------------- #
def window_index(t: float, p: Params) -> int:
    return int(t // p.window_minutes)


def calendar_day(t: float, p: Params) -> float:
    k = window_index(t, p)
    return (k // p.windows_per_week) * 7 + (k % p.windows_per_week) + (t % p.window_minutes) / 1440.0


# --------------------------------------------------------------------------- #
# Site
# --------------------------------------------------------------------------- #
class Site:
    def __init__(self, site_id: int, ready_time_days: float, p: Params, seed: int):
        self.id = site_id
        self.ready_time = ready_time_days
        self.rng = np.random.default_rng(np.random.SeedSequence([seed, site_id]))
        self.status = "waiting"
        self.visits = 0
        self.aborted_visits = 0
        self.nights = 0
        self.immune: set = set()
        self.close_time: Optional[float] = None
        # Per-site draws, once, before any scenario-dependent logic.
        self.site_class = self._draw_class(p)
        lo, mode, hi = p.devices_tri[self.site_class]
        self.devices = int(round(self.rng.triangular(lo, mode, hi)))
        self.devices = max(1, self.devices)
        self.tool_minutes = float(np.sum(self.rng.lognormal(
            math.log(p.tool_per_device_median), p.tool_sigma, size=self.devices)))
        lo, mode, hi = p.renewables_call_tri
        self.renewables_minutes = float(np.sum(self.rng.triangular(lo, mode, hi, size=self.devices)))
        self.rooms = 1 + self.devices // 8

    def _draw_class(self, p: Params) -> str:
        u = self.rng.uniform()
        acc = 0.0
        for c in SITE_CLASSES:
            acc += p.class_mix.get(c, 0.0)
            if u < acc:
                return c
        return SITE_CLASSES[0]

    def draw_visit(self, p: Params) -> dict:
        """Fixed-order, fixed-count draws for one visit (scenario independent)."""
        r = self.rng
        d: dict = {}
        for c in CAUSES:
            d[f"{c}_u"] = r.uniform()
            d[f"{c}_abort_u"] = r.uniform()
            if c == "gonogo":
                d[f"{c}_delay"] = r.lognormal(math.log(p.gonogo_median), p.gonogo_sigma)
            else:
                lo, mode, hi = p.delay_tri[c]
                d[f"{c}_delay"] = r.triangular(lo, mode, hi)
        d["travel"] = r.lognormal(math.log(p.travel_median), p.travel_sigma)
        d["gate"] = r.triangular(*p.gate_tri)
        d["closure"] = r.triangular(*p.closure_tri)
        d["prep_bl"] = r.triangular(*p.prep_bl_tri)
        d["prep_ie"] = r.triangular(*p.prep_ie_tri)
        d["report"] = r.triangular(*p.report_tri)
        d["rework_u"] = r.uniform(size=self.rooms)
        lo, mode, hi = p.rework_tri
        d["rework_delay"] = r.triangular(lo, mode, hi, size=self.rooms)
        return d


# --------------------------------------------------------------------------- #
# Single run
# --------------------------------------------------------------------------- #
class RunState:
    def __init__(self, p: Params, sc: Scenario):
        self.p = p
        self.sc = sc
        self.sites: List[Site] = []
        self.lost: Dict[str, float] = {c: 0.0 for c in CAUSES}
        self.lost["qa_rework"] = 0.0
        self.admin_bl = 0.0
        self.admin_ie = 0.0
        self.busy = 0.0
        self.travel = 0.0
        self.gate = 0.0
        self.closure = 0.0
        self.tool = 0.0
        self.renewables = 0.0
        self.backlog_series: List[int] = []
        self.arrivals = 0


def _factor(sc: Scenario, p: Params) -> float:
    return (1.0 - p.reduction) if sc.ai_lever else 1.0


def _admin_factor(sc: Scenario, p: Params) -> float:
    return (1.0 - p.admin_reduction) if sc.ai_lever else 1.0


def visit(env: simpy.Environment, site: Site, st: RunState):
    """One scheduled night at a site. Returns True if the site closed."""
    p, sc = st.p, st.sc
    f = _factor(sc, p)
    site.visits += 1
    d = site.draw_visit(p)
    logical = site.site_class == "logical"
    mult = p.complex_multiplier if site.site_class == "complex" else 1.0

    # Administrative tail for this night (paid outside the window).
    af = _admin_factor(sc, p)
    st.admin_bl += (d["prep_bl"] + d["report"]) * af
    st.admin_ie += d["prep_ie"] * af

    # Wait for the next window if too little of this one remains.
    rem = p.window_minutes - (env.now % p.window_minutes)
    if rem < p.min_start_minutes:
        yield env.timeout(rem)
    start = env.now
    start_window = window_index(start, p)

    travel = 0.0 if logical else d["travel"]
    if travel:
        yield env.timeout(travel)
    st.travel += travel

    gate = d["gate"] * mult
    yield env.timeout(gate)
    st.gate += gate

    # Wait and defect events, in order. First no-go aborts the night.
    for c in CAUSES:
        if logical and c in ("remediation", "access", "hardware"):
            continue
        if c in site.immune:
            continue
        if d[f"{c}_u"] < p.event_p[c] * f:
            delay = d[f"{c}_delay"] * (f if c == "gonogo" else 1.0)
            yield env.timeout(delay)
            if d[f"{c}_abort_u"] < p.event_abort[c]:
                st.lost[c] += travel + gate + delay
                site.immune.add(c)
                site.aborted_visits += 1
                site.nights += window_index(env.now, p) - start_window + 1
                st.busy += env.now - start
                return False
            st.lost[c] += delay

    # Tool time: the real work. Never reduced by the lever.
    yield env.timeout(site.tool_minutes)
    st.tool += site.tool_minutes
    if site.site_class == "renewables":
        yield env.timeout(site.renewables_minutes)
        st.renewables += site.renewables_minutes

    # Quality rework loop, per room.
    rework = float(np.sum(d["rework_delay"][d["rework_u"] < p.rework_p * f]))
    if rework:
        yield env.timeout(rework)
        st.lost["qa_rework"] += rework

    closure = d["closure"] * mult
    yield env.timeout(closure)
    st.closure += closure

    site.nights += window_index(env.now, p) - start_window + 1
    st.busy += env.now - start
    site.close_time = env.now
    return True


def site_process(env: simpy.Environment, site: Site, teams: simpy.Resource, st: RunState):
    while True:
        with teams.request() as req:
            yield req
            site.status = "in_progress"
            closed = yield env.process(visit(env, site, st))
        if closed:
            site.status = "closed"
            return
        site.status = "waiting"  # re-request puts the site at the back of the FIFO queue


def arrivals_process(env: simpy.Environment, st: RunState, teams: simpy.Resource, seed: int):
    p = st.p
    rng = np.random.default_rng(np.random.SeedSequence([seed, 0, 10_000_019]))
    mean_gap = (p.windows_per_week * p.window_minutes) / p.arrivals_per_week if p.arrivals_per_week > 0 else None
    while mean_gap is not None:
        yield env.timeout(rng.exponential(mean_gap))
        site = Site(len(st.sites), calendar_day(env.now, p), p, seed)
        st.sites.append(site)
        st.arrivals += 1
        env.process(site_process(env, site, teams, st))


def monitor_process(env: simpy.Environment, st: RunState):
    p = st.p
    week_minutes = p.windows_per_week * p.window_minutes
    while True:
        st.backlog_series.append(sum(1 for s in st.sites if s.status == "waiting"))
        yield env.timeout(week_minutes)


def simulate(p: Params, sc: Scenario, seed: int, run_id: int = 0):
    """Run one replication; returns (metrics dict, RunState with sites)."""
    p.validate()
    run_seed = seed * 1_000_003 + run_id
    env = simpy.Environment()
    st = RunState(p, sc)
    teams = simpy.Resource(env, capacity=sc.teams)

    backlog_rng = np.random.default_rng(np.random.SeedSequence([run_seed, 1, 10_000_079]))
    for i in range(p.initial_backlog):
        ready = float(backlog_rng.uniform(-p.backlog_age_weeks * 7.0, 0.0))
        site = Site(i, ready, p, run_seed)
        st.sites.append(site)
        env.process(site_process(env, site, teams, st))

    env.process(arrivals_process(env, st, teams, run_seed))
    env.process(monitor_process(env, st))
    env.run(until=p.total_minutes)
    st.backlog_series.append(sum(1 for s in st.sites if s.status == "waiting"))

    closed = [s for s in st.sites if s.status == "closed"]
    n_closed = len(closed)
    n_in_progress = sum(1 for s in st.sites if s.status == "in_progress")
    n_waiting = sum(1 for s in st.sites if s.status == "waiting")
    conservation_ok = (p.initial_backlog + st.arrivals) == (n_closed + n_in_progress + n_waiting)

    team_weeks = sc.teams * p.horizon_weeks
    paid_window = sc.teams * p.total_minutes
    admin = st.admin_bl + st.admin_ie
    idle = max(0.0, paid_window - st.busy)
    devices = sum(s.devices for s in closed)
    cost = (paid_window / 60.0) * p.team_rate + (st.admin_bl / 60.0) * p.rate_bl + (st.admin_ie / 60.0) * p.rate_ie
    wait_lost = sum(st.lost[c] for c in CAUSES) + st.lost["qa_rework"]
    eol = np.array([calendar_day(s.close_time, p) - s.ready_time for s in closed]) if closed else np.array([np.nan])
    aborted = sum(s.aborted_visits for s in st.sites)

    out = {
        "run_id": run_id,
        "scenario": sc.name,
        "teams": sc.teams,
        "ai_lever": sc.ai_lever,
        "closed": n_closed,
        "devices": devices,
        "closed_per_team_week": n_closed / team_weeks,
        "devices_per_team_week": devices / team_weeks,
        "wrench_time_ratio": st.tool / (paid_window + admin) if (paid_window + admin) > 0 else np.nan,
        "revisit_rate": aborted / n_closed if n_closed else np.nan,
        "nights_per_change": (sum(s.nights for s in closed) / n_closed) if n_closed else np.nan,
        "backlog_end": n_waiting,
        "eol_median_days": float(np.nanmedian(eol)),
        "eol_p95_days": float(np.nanpercentile(eol, 95)),
        "cost_total": cost,
        "cost_per_change": cost / n_closed if n_closed else np.nan,
        "cost_per_device": cost / devices if devices else np.nan,
        "lost_hours_per_change": (wait_lost / 60.0) / n_closed if n_closed else np.nan,
        "hours_tool": st.tool / 60.0,
        "hours_travel": st.travel / 60.0,
        "hours_gate": st.gate / 60.0,
        "hours_closure": st.closure / 60.0,
        "hours_renewables_calls": st.renewables / 60.0,
        "hours_admin_tail": admin / 60.0,
        "hours_idle": idle / 60.0,
        "arrivals": st.arrivals,
        "in_progress_end": n_in_progress,
        "conservation_ok": conservation_ok,
        "backlog_series": list(st.backlog_series),
    }
    for c in CAUSES:
        out[f"lost_hours_{c}"] = st.lost[c] / 60.0
    out["lost_hours_qa_rework"] = st.lost["qa_rework"] / 60.0
    return out, st


def run_once(p: Params, sc: Scenario, seed: int, run_id: int = 0) -> dict:
    return simulate(p, sc, seed, run_id)[0]


# --------------------------------------------------------------------------- #
# Monte Carlo and summaries
# --------------------------------------------------------------------------- #
def run_monte_carlo(p: Params, sc: Scenario, n_runs: int, seed: int) -> pd.DataFrame:
    rows = [run_once(p, sc, seed, i) for i in range(n_runs)]
    return pd.DataFrame(rows)


def run_scenarios(p: Params, scenarios: List[Scenario], n_runs: int, seed: int) -> pd.DataFrame:
    return pd.concat([run_monte_carlo(p, sc, n_runs, seed) for sc in scenarios], ignore_index=True)


HEADLINE_METRICS = [
    ("closed_per_team_week", "Changes / team-week"),
    ("devices_per_team_week", "Devices / team-week"),
    ("wrench_time_ratio", "Wrench-time ratio"),
    ("cost_per_change", "Cost / change ($)"),
    ("eol_p95_days", "EOL exposure p95 (days)"),
    ("revisit_rate", "Revisit rate"),
    ("backlog_end", "Backlog at end"),
]


def summarize(runs: pd.DataFrame) -> pd.DataFrame:
    """Median, p5 and p95 per scenario for every numeric metric."""
    num = runs.drop(columns=["backlog_series"]).select_dtypes("number").columns
    g = runs.groupby("scenario", sort=False)[list(num)]
    med = g.median().add_suffix("_median")
    p5 = g.quantile(0.05).add_suffix("_p5")
    p95 = g.quantile(0.95).add_suffix("_p95")
    return pd.concat([med, p5, p95], axis=1)


def headline_table(runs: pd.DataFrame) -> pd.DataFrame:
    s = summarize(runs)
    rows = {}
    for key, label in HEADLINE_METRICS:
        med, lo, hi = s[f"{key}_median"], s[f"{key}_p5"], s[f"{key}_p95"]
        if key == "cost_per_change":
            rows[label] = [f"{m:,.0f} ({a:,.0f}–{b:,.0f})" for m, a, b in zip(med, lo, hi)]
        elif key in ("backlog_end",):
            rows[label] = [f"{m:.0f} ({a:.0f}–{b:.0f})" for m, a, b in zip(med, lo, hi)]
        else:
            rows[label] = [f"{m:.2f} ({a:.2f}–{b:.2f})" for m, a, b in zip(med, lo, hi)]
    return pd.DataFrame(rows, index=s.index).T


def lost_hours_table(runs: pd.DataFrame) -> pd.DataFrame:
    """Median paid hours lost by cause per scenario, including rework, admin and idle."""
    cols = {f"lost_hours_{c}": CAUSE_LABELS[c] for c in CAUSES}
    cols["lost_hours_qa_rework"] = CAUSE_LABELS["qa_rework"]
    cols["hours_admin_tail"] = CAUSE_LABELS["admin_tail"]
    cols["hours_idle"] = CAUSE_LABELS["idle"]
    med = runs.groupby("scenario", sort=False)[list(cols)].median()
    return med.rename(columns=cols).T


def backlog_curves(runs: pd.DataFrame) -> pd.DataFrame:
    """Median backlog per week per scenario (long format)."""
    out = []
    for name, g in runs.groupby("scenario", sort=False):
        arr = np.array(g["backlog_series"].tolist())
        for w, v in enumerate(np.median(arr, axis=0)):
            out.append({"scenario": name, "week": w, "backlog": v})
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- #
# Field-data intake
# --------------------------------------------------------------------------- #
NON_OBSERVABLE = {"arrivals_per_week", "initial_backlog", "backlog_age_weeks", "prep_ie_tri",
                  "travel_sigma", "tool_sigma", "gonogo_sigma", "rate_fe", "rate_bl", "rate_ie"}


@dataclass
class FitResult:
    params: Params
    missing: List[str]
    n_sites: int
    n_visits: int


def _tri_from(values: List[float]) -> Optional[tuple]:
    if len(values) < 3:
        return None
    v = np.array(values, dtype=float)
    return (float(np.min(v)), float(np.median(v)), float(np.max(v)))


def fit_from_event_log(path, base: Optional[Params] = None) -> FitResult:
    """Derive engine parameters from an event log CSV.

    Columns: site_id, site_class, visit_n, event_time (ISO 8601), event, note.
    Anything the log cannot support stays at its planning-assumption default
    and is listed in `missing`.
    """
    base = base or Params()
    df = pd.read_csv(path)
    required = {"site_id", "site_class", "visit_n", "event_time", "event"}
    if not required.issubset(df.columns):
        raise ValueError(f"event log needs columns {sorted(required)}")
    bad = set(df["event"]) - set(EVENT_VOCAB)
    if bad:
        raise ValueError(f"unknown events in log: {sorted(bad)}")
    df["event_time"] = pd.to_datetime(df["event_time"])
    df = df.sort_values(["site_id", "visit_n", "event_time"]).reset_index(drop=True)

    travel, gate, closure, prep, report, gonogo = [], [], [], [], [], []
    tool_per_device, ren_calls, rework_delays = [], [], []
    delays = {c: [] for c in ("packet", "remediation", "access", "hardware")}
    occ = {c: 0 for c in CAUSES}
    aborts = {c: 0 for c in CAUSES}
    rework_events, rooms_total = 0, 0
    devices_by_class: Dict[str, list] = {c: [] for c in SITE_CLASSES}
    class_of_site: Dict[str, str] = {}
    n_visits = 0

    issue_event = {"packet": "packet_issue", "remediation": "remediation_block",
                   "access": "access_issue", "hardware": "hardware_issue"}

    for (sid, vn), g in df.groupby(["site_id", "visit_n"], sort=False):
        n_visits += 1
        g = g.reset_index(drop=True)
        cls = str(g["site_class"].iloc[0])
        class_of_site[str(sid)] = cls
        first = g.drop_duplicates("event", keep="first")
        times = dict(zip(first["event"], first["event_time"]))  # first occurrence per event name

        def mins(a, b):
            return (times[b] - times[a]).total_seconds() / 60.0

        if "depart" in times and "check_in" in times:
            travel.append(mins("depart", "check_in"))
        if "gate_start" in times and "gate_end" in times:
            gate.append(mins("gate_start", "gate_end"))
        if "closure_start" in times and "checkout" in times:
            closure.append(mins("closure_start", "checkout"))
        if "prep_start" in times and "prep_end" in times:
            prep.append(mins("prep_start", "prep_end"))
        if "report_start" in times and "report_sent" in times:
            report.append(mins("report_start", "report_sent"))
        if "gonogo_wait_start" in times:
            occ["gonogo"] += 1
            if "gonogo_wait_end" in times:
                gonogo.append(mins("gonogo_wait_start", "gonogo_wait_end"))
            elif "no_go" in times:
                aborts["gonogo"] += 1
        no_go = "no_go" in times

        # Issue events: delay = time to the next event in the visit.
        for c, ev in issue_event.items():
            idx = g.index[g["event"] == ev].tolist()
            if not idx:
                continue
            occ[c] += 1
            i = idx[0]
            nxt = g.iloc[i + 1] if i + 1 < len(g) else None
            if nxt is not None and nxt["event"] == "no_go":
                aborts[c] += 1
            elif nxt is not None:
                delays[c].append((nxt["event_time"] - g.loc[i, "event_time"]).total_seconds() / 60.0)

        dd = g[g["event"] == "device_done"]["event_time"].tolist()
        if len(dd) >= 2:
            tool_per_device.extend(np.diff(np.array(dd, dtype="datetime64[s]")).astype(float) / 60.0)
        if dd and not no_go:
            devices_by_class.setdefault(cls, []).append(len(dd))
            rooms_total += 1 + len(dd) // 8
        rc = g.index[g["event"] == "renewables_call"].tolist()
        for i in rc:
            prev = g.iloc[i - 1] if i > 0 else None
            if prev is not None and prev["event"] == "device_done":
                ren_calls.append((g.loc[i, "event_time"] - prev["event_time"]).total_seconds() / 60.0)
        rw = g.index[g["event"] == "qa_rework"].tolist()
        rework_events += len(rw)
        for i in rw:
            if i + 1 < len(g):
                rework_delays.append((g.loc[i + 1, "event_time"] - g.loc[i, "event_time"]).total_seconds() / 60.0)

    missing: List[str] = []
    upd: dict = {}

    def set_or_missing(name, value):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            missing.append(name)
        else:
            upd[name] = value

    set_or_missing("travel_median", float(np.median(travel)) if travel else None)
    set_or_missing("gate_tri", _tri_from(gate))
    set_or_missing("closure_tri", _tri_from(closure))
    set_or_missing("prep_bl_tri", _tri_from(prep))
    set_or_missing("report_tri", _tri_from(report))
    set_or_missing("tool_per_device_median", float(np.median(tool_per_device)) if tool_per_device else None)
    set_or_missing("renewables_call_tri", _tri_from(ren_calls))
    set_or_missing("rework_tri", _tri_from(rework_delays))
    set_or_missing("gonogo_median", float(np.median(gonogo)) if gonogo else None)
    if rooms_total:
        upd["rework_p"] = min(1.0, rework_events / rooms_total)
    else:
        missing.append("rework_p")

    event_p = dict(base.event_p)
    event_abort = dict(base.event_abort)
    delay_tri = dict(base.delay_tri)
    if n_visits:
        for c in CAUSES:
            event_p[c] = occ[c] / n_visits
            if occ[c]:
                event_abort[c] = aborts[c] / occ[c]
            else:
                missing.append(f"event_abort.{c}")
            if c != "gonogo":
                t = _tri_from(delays[c])
                if t:
                    delay_tri[c] = t
                else:
                    missing.append(f"delay_tri.{c}")
    else:
        missing.extend(["event_p", "event_abort", "delay_tri"])
    upd["event_p"], upd["event_abort"], upd["delay_tri"] = event_p, event_abort, delay_tri

    if class_of_site:
        counts = pd.Series(list(class_of_site.values())).value_counts()
        mix = {c: float(counts.get(c, 0)) / len(class_of_site) for c in SITE_CLASSES}
        upd["class_mix"] = mix
    else:
        missing.append("class_mix")
    dev = dict(base.devices_tri)
    for c in SITE_CLASSES:
        t = _tri_from(devices_by_class.get(c, []))
        if t:
            dev[c] = (int(t[0]), int(round(t[1])), int(t[2]))
        else:
            missing.append(f"devices_tri.{c}")
    upd["devices_tri"] = dev

    # Not observable from a per-visit event log.
    missing.extend(sorted(NON_OBSERVABLE))
    params = replace(base, **upd)
    return FitResult(params=params, missing=sorted(set(missing)), n_sites=len(class_of_site), n_visits=n_visits)


def make_synthetic_event_log(path, n_sites: int = 40, seed: int = 7, p: Optional[Params] = None) -> pd.DataFrame:
    """Write a synthetic event log consistent with the engine's assumptions.

    Purely synthetic. No real site, program, or person is represented.
    """
    p = p or Params()
    rng = np.random.default_rng(seed)
    rows = []
    t0 = pd.Timestamp("2026-01-05 18:00:00")
    site_ids = [f"S{i:03d}" for i in range(n_sites)]
    classes = rng.choice(SITE_CLASSES, size=n_sites, p=[p.class_mix[c] for c in SITE_CLASSES])
    night = 0

    def add(sid, cls, vn, t, ev, note=""):
        rows.append({"site_id": sid, "site_class": cls, "visit_n": vn,
                     "event_time": t.strftime("%Y-%m-%dT%H:%M:%S"), "event": ev, "note": note})

    for sid, cls in zip(site_ids, classes):
        lo, mode, hi = p.devices_tri[cls]
        devices = max(1, int(round(rng.triangular(lo, mode, hi))))
        immune = set()
        vn = 0
        closed = False
        while not closed and vn < 4:
            vn += 1
            night += 1
            day = t0 + pd.Timedelta(days=(night // 4) * 7 + (night % 4))
            t = day - pd.Timedelta(minutes=float(rng.triangular(*p.prep_bl_tri)) + 240)
            add(sid, cls, vn, t, "prep_start")
            t = t + pd.Timedelta(minutes=float(rng.triangular(*p.prep_bl_tri)))
            add(sid, cls, vn, t, "prep_end")
            t = day
            if cls != "logical":
                add(sid, cls, vn, t, "depart")
                t += pd.Timedelta(minutes=float(rng.lognormal(math.log(p.travel_median), p.travel_sigma)))
            add(sid, cls, vn, t, "check_in")
            add(sid, cls, vn, t, "gate_start")
            t += pd.Timedelta(minutes=float(rng.triangular(*p.gate_tri)))
            add(sid, cls, vn, t, "gate_end")
            aborted = False
            for c in CAUSES:
                if cls == "logical" and c in ("remediation", "access", "hardware"):
                    continue
                if c in immune or rng.uniform() >= p.event_p[c]:
                    continue
                if c == "gonogo":
                    add(sid, cls, vn, t, "gonogo_wait_start")
                    t += pd.Timedelta(minutes=float(rng.lognormal(math.log(p.gonogo_median), p.gonogo_sigma)))
                    if rng.uniform() < p.event_abort[c]:
                        add(sid, cls, vn, t, "no_go", "go/no-go not granted")
                        aborted = True
                        immune.add(c)
                        break
                    add(sid, cls, vn, t, "gonogo_wait_end")
                    continue
                ev = {"packet": "packet_issue", "remediation": "remediation_block",
                      "access": "access_issue", "hardware": "hardware_issue"}[c]
                add(sid, cls, vn, t, ev)
                t += pd.Timedelta(minutes=float(rng.triangular(*p.delay_tri[c])))
                if rng.uniform() < p.event_abort[c]:
                    add(sid, cls, vn, t, "no_go", f"{c} abort")
                    aborted = True
                    immune.add(c)
                    break
                add(sid, cls, vn, t, "resumed")
            if aborted:
                add(sid, cls, vn, t, "revisit_scheduled")
            else:
                for _ in range(devices):
                    t += pd.Timedelta(minutes=float(rng.lognormal(math.log(p.tool_per_device_median), p.tool_sigma)))
                    add(sid, cls, vn, t, "device_done")
                    if cls == "renewables":
                        t += pd.Timedelta(minutes=float(rng.triangular(*p.renewables_call_tri)))
                        add(sid, cls, vn, t, "renewables_call")
                rooms = 1 + devices // 8
                for _ in range(rooms):
                    if rng.uniform() < p.rework_p:
                        add(sid, cls, vn, t, "qa_rework")
                        t += pd.Timedelta(minutes=float(rng.triangular(*p.rework_tri)))
                add(sid, cls, vn, t, "closure_start")
                t += pd.Timedelta(minutes=float(rng.triangular(*p.closure_tri)))
                add(sid, cls, vn, t, "checkout")
                closed = True
            t2 = day + pd.Timedelta(days=1, hours=-9)
            add(sid, cls, vn, t2, "report_start")
            add(sid, cls, vn, t2 + pd.Timedelta(minutes=float(rng.triangular(*p.report_tri))), "report_sent")
    out = pd.DataFrame(rows)
    out = out.sort_values(["site_id", "visit_n", "event_time"], kind="stable").reset_index(drop=True)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return out


def write_template(path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["site_id", "site_class", "visit_n", "event_time", "event", "note"])
        w.writerow(["S001", "standard", 1, "2026-01-05T17:05:00", "depart", "field engineer leaves base"])
        w.writerow(["S001", "standard", 1, "2026-01-05T18:10:00", "check_in", "ops center called, building A"])
        w.writerow(["S001", "standard", 1, "2026-01-05T18:10:00", "gate_start", ""])
        w.writerow(["S001", "standard", 1, "2026-01-05T19:20:00", "gate_end", ""])
        w.writerow(["S001", "standard", 1, "2026-01-05T19:35:00", "device_done", "first device"])


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Change Event Capacity Simulator (planning assumptions by default)")
    ap.add_argument("--runs", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--event-log", type=str, default=None, help="CSV event log to fit parameters from")
    ap.add_argument("--csv", type=str, default=None, help="write per-run results to this CSV")
    args = ap.parse_args(argv)

    p = Params()
    note = "PLANNING ASSUMPTIONS (no field data loaded)"
    if args.event_log:
        fit = fit_from_event_log(args.event_log)
        p = fit.params
        note = f"fitted from {args.event_log} ({fit.n_sites} sites, {fit.n_visits} visits); still default: {', '.join(fit.missing) or 'none'}"

    runs = run_scenarios(p, DEFAULT_SCENARIOS, args.runs, args.seed)
    pd.set_option("display.width", 160)
    print(f"Change Event Capacity Simulator — {args.runs} runs, seed {args.seed}")
    print(f"Parameters: {note}")
    print("\nHeadline (median, p5–p95):")
    print(headline_table(runs).to_string())
    print("\nMedian paid hours lost by cause over the horizon:")
    print(lost_hours_table(runs).round(1).to_string())
    print(f"\nConservation holds on every run: {bool(runs['conservation_ok'].all())}")
    if args.csv:
        runs.drop(columns=["backlog_series"]).to_csv(args.csv, index=False)
        print(f"Per-run results written to {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
