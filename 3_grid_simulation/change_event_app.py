"""Change Event Capacity Simulator — NiceGUI app.

Run:  python 3_grid_simulation/change_event_app.py   (serves on http://localhost:8081)

Every number on screen is a PLANNING ASSUMPTION until an event-log CSV is
loaded. The storm simulator (streamlit_app.py) is untouched; this is a
separate app.
"""
from __future__ import annotations

import inspect
import io
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from nicegui import events, run, ui

sys.path.insert(0, str(Path(__file__).resolve().parent))
import change_event_sim as ces  # noqa: E402

TITLE = "Change Event Capacity Simulator"
ASSUMPTION_CAPTION = "All numbers on this page are planning assumptions. No field data is loaded."
PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#B279A2"]


class AppState:
    def __init__(self) -> None:
        self.params: ces.Params = ces.Params()
        self.fit: Optional[ces.FitResult] = None
        self.fit_name: Optional[str] = None
        self.runs: Optional[pd.DataFrame] = None
        self.inputs: Dict[str, ui.element] = {}


def _num(state: AppState, key: str, label: str, value, min=None, max=None, step=None, fmt=None) -> ui.number:
    el = ui.number(label, value=value, min=min, max=max, step=step, format=fmt).classes("w-full")
    state.inputs[key] = el
    return el


def _collect_params(state: AppState) -> ces.Params:
    v = {k: el.value for k, el in state.inputs.items()}
    base = state.fit.params if state.fit else ces.Params()
    mix = {c: float(v[f"mix_{c}"]) for c in ces.SITE_CLASSES}
    total = sum(mix.values()) or 1.0
    mix = {c: x / total for c, x in mix.items()}  # normalize so the mix always sums to 1
    return replace(
        base,
        windows_per_week=int(v["windows_per_week"]), window_hours=float(v["window_hours"]),
        horizon_weeks=int(v["horizon_weeks"]),
        arrivals_per_week=float(v["arrivals_per_week"]), initial_backlog=int(v["initial_backlog"]),
        backlog_age_weeks=float(v["backlog_age_weeks"]),
        rate_fe=float(v["rate_fe"]), rate_bl=float(v["rate_bl"]), rate_ie=float(v["rate_ie"]),
        class_mix=mix,
        reduction=float(v["reduction"]), admin_reduction=float(v["admin_reduction"]),
        travel_sigma=float(v["travel_sigma"]), tool_sigma=float(v["tool_sigma"]),
        gonogo_sigma=float(v["gonogo_sigma"]),
    )


def _scenarios(state: AppState) -> List[ces.Scenario]:
    sc = list(ces.DEFAULT_SCENARIOS)
    if state.inputs["custom_on"].value:
        sc.append(ces.Scenario(
            name=state.inputs["custom_name"].value or "Custom",
            teams=int(state.inputs["custom_teams"].value),
            ai_lever=bool(state.inputs["custom_ai"].value)))
    return sc


def _caption_text(state: AppState) -> str:
    if state.fit is None:
        return ASSUMPTION_CAPTION
    still = ", ".join(state.fit.missing) or "none"
    return (f"Parameters fitted from event log '{state.fit_name}' ({state.fit.n_sites} sites, "
            f"{state.fit.n_visits} visits). Still at planning-assumption defaults: {still}.")


def _histogram_series(runs: pd.DataFrame, col: str, bins: int = 12):
    lo, hi = float(runs[col].min()), float(runs[col].max())
    if hi <= lo:
        hi = lo + 1.0
    edges = np.linspace(lo, hi, bins + 1)
    labels = [f"{a:.1f}" for a in edges[:-1]]
    series = []
    for i, (name, g) in enumerate(runs.groupby("scenario", sort=False)):
        counts, _ = np.histogram(g[col], bins=edges)
        series.append({"name": name, "type": "bar", "data": counts.tolist(),
                       "itemStyle": {"color": PALETTE[i % len(PALETTE)]}})
    return labels, series


def render_results(state: AppState, container: ui.element) -> None:
    runs = state.runs
    container.clear()
    with container:
        caption = _caption_text(state)
        ui.label(caption).classes("text-sm italic text-grey-7")

        # 1. Headline table
        ui.label("1. Headline: scenarios side by side (median, p5–p95)").classes("text-lg font-bold mt-2")
        ht = ces.headline_table(runs)
        cols = [{"name": "metric", "label": "Metric", "field": "metric", "align": "left"}]
        cols += [{"name": c, "label": c, "field": c, "align": "right"} for c in ht.columns]
        rows = [{"metric": idx, **{c: ht.loc[idx, c] for c in ht.columns}} for idx in ht.index]
        ui.table(columns=cols, rows=rows, row_key="metric").classes("w-full")

        # 2. Backlog over time
        ui.label("2. Backlog of change-ready sites over time (median per week)").classes("text-lg font-bold mt-4")
        bc = ces.backlog_curves(runs)
        weeks = sorted(bc["week"].unique().tolist())
        series = []
        for i, (name, g) in enumerate(bc.groupby("scenario", sort=False)):
            series.append({"name": name, "type": "line", "data": g.sort_values("week")["backlog"].tolist(),
                           "itemStyle": {"color": PALETTE[i % len(PALETTE)]}})
        ui.echart({"tooltip": {"trigger": "axis"}, "legend": {"top": 0},
                   "xAxis": {"type": "category", "data": weeks, "name": "week"},
                   "yAxis": {"type": "value", "name": "sites waiting"},
                   "series": series}).classes("w-full h-72")

        # 3. Paid hours lost by cause
        ui.label("3. Paid hours lost by cause over the horizon (median)").classes("text-lg font-bold mt-4")
        lt = ces.lost_hours_table(runs)
        series = []
        for i, name in enumerate(lt.columns):
            series.append({"name": name, "type": "bar", "data": [round(float(x), 1) for x in lt[name]],
                           "itemStyle": {"color": PALETTE[i % len(PALETTE)]}})
        ui.echart({"tooltip": {"trigger": "axis"}, "legend": {"top": 0}, "grid": {"left": 320},
                   "xAxis": {"type": "value", "name": "hours"},
                   "yAxis": {"type": "category", "data": list(lt.index), "inverse": True,
                             "axisLabel": {"width": 300, "overflow": "truncate"}},
                   "series": series}).classes("w-full h-96")

        # 4. Distribution of changes per team-week
        ui.label("4. Distribution of changes closed per team-week").classes("text-lg font-bold mt-4")
        labels, series = _histogram_series(runs, "closed_per_team_week")
        ui.echart({"tooltip": {"trigger": "axis"}, "legend": {"top": 0},
                   "xAxis": {"type": "category", "data": labels, "name": "changes / team-week"},
                   "yAxis": {"type": "value", "name": "runs"},
                   "series": series}).classes("w-full h-72")

        # 5. Nights per change and revisit rate
        ui.label("5. Nights per closed change and revisit rate (median)").classes("text-lg font-bold mt-4")
        med = runs.groupby("scenario", sort=False)[["nights_per_change", "revisit_rate"]].median()
        ui.echart({"tooltip": {"trigger": "axis"}, "legend": {"top": 0},
                   "xAxis": {"type": "category", "data": list(med.index)},
                   "yAxis": {"type": "value"},
                   "series": [
                       {"name": "Nights per change", "type": "bar",
                        "data": [round(float(x), 2) for x in med["nights_per_change"]],
                        "itemStyle": {"color": PALETTE[0]}},
                       {"name": "Revisit rate", "type": "bar",
                        "data": [round(float(x), 2) for x in med["revisit_rate"]],
                        "itemStyle": {"color": PALETTE[1]}},
                   ]}).classes("w-full h-64")

        # 6. Downloads
        ui.label("6. Downloads").classes("text-lg font-bold mt-4")
        per_run = runs.drop(columns=["backlog_series"]).to_csv(index=False).encode()
        headline = ht.to_csv().encode()
        with ui.row():
            ui.button("Per-run CSV", icon="download",
                      on_click=lambda: ui.download.content(per_run, "change_event_per_run.csv"))
            ui.button("Headline table CSV", icon="download",
                      on_click=lambda: ui.download.content(headline, "change_event_headline.csv"))
        ui.label(caption).classes("text-sm italic text-grey-7 mt-2")


@ui.page("/")
def index() -> None:
    state = AppState()
    ui.page_title(TITLE)

    with ui.header().classes("items-center"):
        ui.label(TITLE).classes("text-xl font-bold")
        ui.space()
        ui.label("Planning-assumption defaults. Not benchmarks.").classes("text-sm")

    with ui.left_drawer(value=True).classes("bg-grey-1").props("width=340"):
        ui.label("Monte Carlo").classes("font-bold")
        _num(state, "runs", "Simulation runs", 100, 10, 500, 10)
        _num(state, "seed", "Seed", 42, 0, None, 1)

        ui.separator()
        ui.label("Calendar (planning assumptions)").classes("font-bold")
        _num(state, "windows_per_week", "Change windows per week", 4, 1, 7, 1)
        _num(state, "window_hours", "Window length (hours)", 8, 2, 14, 0.5)
        _num(state, "horizon_weeks", "Horizon (weeks)", 16, 4, 52, 1)

        ui.separator()
        ui.label("Arrivals and backlog (planning assumptions)").classes("font-bold")
        _num(state, "arrivals_per_week", "Change-ready sites per week", 4, 0, 30, 0.5)
        _num(state, "initial_backlog", "Initial backlog (sites)", 25, 0, 300, 1)
        _num(state, "backlog_age_weeks", "Backlog age spread (weeks)", 8, 0, 52, 1)

        ui.separator()
        ui.label("Team loaded rates, $/hr (planning assumptions)").classes("font-bold")
        _num(state, "rate_fe", "Field engineer", 95, 0, None, 5)
        _num(state, "rate_bl", "Bridge lead", 85, 0, None, 5)
        _num(state, "rate_ie", "Implementation engineer", 125, 0, None, 5)

        ui.separator()
        ui.label("Site-class mix (normalized to 1)").classes("font-bold")
        for c, d in ces.Params().class_mix.items():
            _num(state, f"mix_{c}", c, d, 0, 1, 0.05)

        ui.separator()
        ui.label("AI lever").classes("font-bold")
        _num(state, "reduction", "Reduction of event and rework probabilities", 0.25, 0, 0.9, 0.05)
        _num(state, "admin_reduction", "Reduction of administrative tail", 0.40, 0, 0.9, 0.05)

        ui.separator()
        ui.label("Custom fourth scenario").classes("font-bold")
        state.inputs["custom_on"] = ui.switch("Include custom scenario", value=False)
        state.inputs["custom_name"] = ui.input("Name", value="2 teams + AI lever").classes("w-full")
        _num(state, "custom_teams", "Teams", 2, 1, 10, 1)
        state.inputs["custom_ai"] = ui.switch("AI lever on", value=True)

        with ui.expansion("Advanced: lognormal sigmas", icon="tune").classes("w-full"):
            _num(state, "travel_sigma", "Travel sigma", 0.5, 0.05, 1.5, 0.05)
            _num(state, "tool_sigma", "Tool-time sigma", 0.4, 0.05, 1.5, 0.05)
            _num(state, "gonogo_sigma", "Go/no-go wait sigma", 0.5, 0.05, 1.5, 0.05)

        ui.separator()
        ui.label("Field data (optional)").classes("font-bold")
        fit_label = ui.label("No event log loaded.").classes("text-xs text-grey-7")

        async def on_upload(e: events.UploadEventArguments) -> None:
            data = e.file.read()
            if inspect.isawaitable(data):
                data = await data
            if isinstance(data, str):
                data = data.encode()
            try:
                with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as tmp:
                    tmp.write(data)
                    path = tmp.name
                state.fit = ces.fit_from_event_log(path)
                state.fit_name = e.file.name
                fit_label.set_text(f"Fitted from {e.file.name}: {state.fit.n_sites} sites, {state.fit.n_visits} visits. "
                                   f"Still default: {', '.join(state.fit.missing) or 'none'}")
                ui.notify("Event log loaded. Press Run to use the fitted parameters.", type="positive")
            except Exception as ex:  # surface schema problems to the user
                state.fit, state.fit_name = None, None
                fit_label.set_text(f"Could not fit: {ex}")
                ui.notify(f"Event log rejected: {ex}", type="negative")

        ui.upload(label="Event log CSV", auto_upload=True, on_upload=on_upload).props("accept=.csv").classes("w-full")

        def clear_fit() -> None:
            state.fit, state.fit_name = None, None
            fit_label.set_text("No event log loaded.")

        ui.button("Clear event log", on_click=clear_fit).props("flat dense")

    caption = ui.label(ASSUMPTION_CAPTION).classes("text-sm italic text-grey-7")
    status = ui.label("").classes("text-sm")
    results = ui.column().classes("w-full")

    async def run_sim() -> None:
        try:
            p = _collect_params(state)
            p.validate()
        except Exception as ex:
            ui.notify(f"Invalid parameters: {ex}", type="negative")
            return
        n = int(state.inputs["runs"].value)
        seed = int(state.inputs["seed"].value)
        scenarios = _scenarios(state)
        run_btn.disable()
        status.set_text(f"Running {n} runs × {len(scenarios)} scenarios…")
        try:
            state.runs = await run.io_bound(ces.run_scenarios, p, scenarios, n, seed)
        except Exception as ex:
            status.set_text(f"Simulation failed: {ex}")
            ui.notify(f"Simulation failed: {ex}", type="negative")
            return
        finally:
            run_btn.enable()
        ok = bool(state.runs["conservation_ok"].all())
        status.set_text(f"Done. Conservation holds on every run: {ok}.")
        caption.set_text(_caption_text(state))
        render_results(state, results)

    with ui.row().classes("items-center"):
        run_btn = ui.button("Run simulation", icon="play_arrow", on_click=run_sim).props("color=primary")
        ui.label("Three default scenarios: 1 team baseline, 1 team + AI lever, 2 teams baseline.").classes("text-sm")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title=TITLE, port=8081, reload=False, show=False)
