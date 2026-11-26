"""Tests for culvert-opt."""

from __future__ import annotations

import json

import pytest

from culvert_opt import (
    CatchmentHydrology,
    design_road_culvert,
    estimate_gravel_maintenance,
    kirpich_tc_minutes,
    rational_peak_runoff_m3_s,
)
from culvert_opt.cli import main as cli_main


def test_kirpich_and_rational_formula() -> None:
    tc_flat = kirpich_tc_minutes(800.0, 0.01)
    tc_steep = kirpich_tc_minutes(800.0, 0.08)
    assert tc_flat > tc_steep >= 5.0
    # C=0.5, i=72 mm/hr, A=10 ha => Q = 0.5 * 72 * 10 / 360 = 1.0 m3/s
    assert rational_peak_runoff_m3_s(
        catchment_area_ha=10.0,
        rainfall_intensity_mm_hr=72.0,
        runoff_coefficient=0.5,
    ) == pytest.approx(1.0)


def test_culvert_sizing_and_scour_apron_trigger() -> None:
    design = design_road_culvert(
        CatchmentHydrology(
            catchment_area_ha=45.0,
            flow_length_m=600.0,
            catchment_slope=0.05,
            land_cover="steep_bare_hillside",
            culvert_slope=0.025,
        )
    )
    assert design.total_capacity_80pct_full_m3_s >= design.design_peak_q_m3_s
    assert design.barrel_diameter_mm >= 900
    assert design.scour_protection_required is True
    assert design.riprap_d50_mm >= 150


def test_gravel_maintenance_and_cli(capsys: pytest.CaptureFixture[str]) -> None:
    gm = estimate_gravel_maintenance(road_length_km=10.0, adt_vehicles_day=150.0, annual_rainfall_mm=1400.0)
    assert 1.5 <= gm.years_between_regravelling <= 5.0
    assert gm.regravelling_cost_usd > 50000.0

    assert cli_main(["--area-ha", "25", "--road-km", "8"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["culvert_design"]["barrel_diameter_mm"] >= 600
