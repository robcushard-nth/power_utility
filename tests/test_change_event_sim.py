"""Tests for the Change Event Capacity Simulator (brief v2, section 2.4)."""
import random
from pathlib import Path

import numpy as np
import pytest

import change_event_sim as ces

SEED = 123
N_RUNS = 20
DATA = Path(__file__).resolve().parents[1] / "3_grid_simulation" / "data"
BASE, LEVER, TWO = ces.DEFAULT_SCENARIOS


@pytest.fixture(scope="module")
def runs():
    return ces.run_scenarios(ces.Params(), ces.DEFAULT_SCENARIOS, N_RUNS, SEED)


def test_conservation_holds_on_every_run(runs):
    assert runs["conservation_ok"].all()
    assert (runs["closed"] + runs["in_progress_end"] + runs["backlog_end"]
            == runs["arrivals"] + ces.Params().initial_backlog).all()


def test_two_teams_close_at_least_as_many_as_one(runs):
    med = runs.groupby("scenario", sort=False)["closed"].median()
    assert med[TWO.name] >= med[BASE.name]


def test_ai_lever_does_not_increase_lost_hours_per_closed_change(runs):
    med = runs.groupby("scenario", sort=False)["lost_hours_per_change"].median()
    assert med[LEVER.name] <= med[BASE.name]


def test_ai_lever_never_changes_tool_time_draws():
    p = ces.Params()
    _, base = ces.simulate(p, BASE, SEED, 0)
    _, lever = ces.simulate(p, LEVER, SEED, 0)
    base_tool = {s.id: s.tool_minutes for s in base.sites}
    lever_tool = {s.id: s.tool_minutes for s in lever.sites}
    common = set(base_tool) & set(lever_tool)
    assert len(common) >= p.initial_backlog
    for sid in common:
        assert base_tool[sid] == pytest.approx(lever_tool[sid])
    # Same seed, same results.
    a = ces.run_once(p, BASE, SEED, 0)
    b = ces.run_once(p, BASE, SEED, 0)
    assert a == b


def test_fit_from_event_log_returns_every_engine_parameter():
    fit = ces.fit_from_event_log(DATA / "example_synthetic_event_log.csv")
    assert isinstance(fit.params, ces.Params)
    fit.params.validate()
    # Only parameters a per-visit event log cannot observe may remain at default.
    assert set(fit.missing) <= ces.NON_OBSERVABLE
    for c in ces.CAUSES:
        assert 0.0 <= fit.params.event_p[c] <= 1.0
        assert 0.0 <= fit.params.event_abort[c] <= 1.0
    assert fit.n_sites > 0 and fit.n_visits >= fit.n_sites
    # The fitted parameters run.
    out = ces.run_once(fit.params, BASE, SEED, 0)
    assert out["conservation_ok"]


def test_site_class_mix_validated_and_logical_sites_skip_field_events():
    bad = ces.Params(class_mix={"standard": 0.5, "renewables": 0.5, "complex": 0.5, "logical": 0.0})
    with pytest.raises(ValueError):
        bad.validate()
    p = ces.Params(class_mix={"standard": 0.0, "renewables": 0.0, "complex": 0.0, "logical": 1.0},
                   event_p={c: 1.0 for c in ces.CAUSES},
                   event_abort={c: 0.0 for c in ces.CAUSES})
    out, st = ces.simulate(p, BASE, SEED, 0)
    assert all(s.site_class == "logical" for s in st.sites)
    assert st.travel == 0.0
    for c in ("remediation", "access", "hardware"):
        assert st.lost[c] == 0.0
    assert st.lost["packet"] > 0.0 and st.lost["gonogo"] > 0.0


def test_storm_simulator_still_imports_and_runs():
    import simpy
    import storm_response as storm

    random.seed(1)
    env = simpy.Environment()
    grid = storm.GridRestoration(env, storm.NUM_CREWS)
    env.process(storm.outage_generator(env, grid))
    env.run(until=storm.SIMULATION_TIME)
    assert len(grid.wait_times) > 0
    assert storm.NUM_CREWS == 5 and storm.SIMULATION_TIME == 1440


# --- NiceGUI app smoke test (main file set in pytest.ini) -------------------- #
async def test_app_renders_and_runs(user) -> None:
    import change_event_app

    await user.open("/")
    await user.should_see(change_event_app.TITLE)
    await user.should_see(change_event_app.ASSUMPTION_CAPTION)
    runs_input = next(iter(user.find("Simulation runs").elements))
    runs_input.set_value(10)
    user.find("Run simulation").click()
    await user.should_see("Done. Conservation holds on every run: True", retries=200)
    await user.should_see("1. Headline")
    await user.should_see("6. Downloads")
