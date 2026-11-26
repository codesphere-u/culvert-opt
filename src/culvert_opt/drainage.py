"""Rational Method hydrology, Manning circular culvert hydraulics, scour & rural road graveling."""

from __future__ import annotations

import math
from dataclasses import dataclass

RUNOFF_COEFFICIENTS: dict[str, float] = {
    "forest_dense": 0.25,
    "smallholder_farmland": 0.45,
    "steep_bare_hillside": 0.65,
    "peri_urban_mixed": 0.60,
    "paved_trading_center": 0.85,
}

# Standard East African precast concrete culvert diameters (mm)
_STANDARD_PIPE_MM: tuple[int, ...] = (600, 900, 1200, 1500)


def kirpich_tc_minutes(flow_length_m: float, slope_m_per_m: float) -> float:
    """Kirpich (1940) catchment time of concentration (minutes)."""
    if flow_length_m <= 0.0 or slope_m_per_m <= 0.0:
        raise ValueError("flow_length_m and slope_m_per_m must be strictly positive")
    tc = 0.0195 * float(flow_length_m**0.77) * float(slope_m_per_m ** (-0.385))
    return max(5.0, tc)


def rational_peak_runoff_m3_s(
    *,
    catchment_area_ha: float,
    rainfall_intensity_mm_hr: float,
    runoff_coefficient: float,
) -> float:
    """Rational Method peak storm discharge: Q (m3/s) = (C * i * A_ha) / 360."""
    if catchment_area_ha <= 0 or rainfall_intensity_mm_hr <= 0 or not (0.05 <= runoff_coefficient <= 1.0):
        raise ValueError("Invalid area, rainfall intensity, or runoff coefficient")
    return (runoff_coefficient * rainfall_intensity_mm_hr * catchment_area_ha) / 360.0


@dataclass(frozen=True)
class CatchmentHydrology:
    """Stormwater catchment inputs for a rural road stream/ditch crossing."""

    catchment_area_ha: float
    flow_length_m: float
    catchment_slope: float
    land_cover: str = "smallholder_farmland"
    idf_r24_mm: float = 120.0  # 25-year 24-hour design storm depth (mm)
    climate_uplift_pct: float = 15.0  # Climate-change extreme rainfall safety margin
    culvert_slope: float = 0.015
    manning_n: float = 0.013  # Precast concrete pipe


@dataclass(frozen=True)
class CulvertDesign:
    """Selected culvert barrel configuration, hydraulic capacity, outlet velocity & riprap apron."""

    tc_minutes: float
    design_intensity_mm_hr: float
    design_peak_q_m3_s: float
    barrel_count: int
    barrel_diameter_mm: int
    total_capacity_80pct_full_m3_s: float
    outlet_velocity_m_s: float
    headwater_to_diameter_ratio: float
    self_cleansing_ok: bool
    scour_protection_required: bool
    riprap_d50_mm: int
    warnings: tuple[str, ...]


def _circular_manning_full(diameter_m: float, slope: float, manning_n: float) -> tuple[float, float]:
    """Full-barrel Manning capacity (m3/s) and flow velocity (m/s) for a circular pipe."""
    area = math.pi * (diameter_m**2) / 4.0
    r_hyd = diameter_m / 4.0
    vel = (1.0 / manning_n) * float(r_hyd ** (2.0 / 3.0)) * math.sqrt(slope)
    return (area * vel, vel)


def design_road_culvert(hydro: CatchmentHydrology) -> CulvertDesign:
    """Size single or multi-barrel concrete culvert with HW/D washout & scour protection checks."""
    key = hydro.land_cover.strip().lower()
    if key not in RUNOFF_COEFFICIENTS:
        raise KeyError(f"Unknown land_cover '{hydro.land_cover}'. Options: {sorted(RUNOFF_COEFFICIENTS)}")
    c_val = RUNOFF_COEFFICIENTS[key]

    tc_min = kirpich_tc_minutes(hydro.flow_length_m, hydro.catchment_slope)
    tc_hr = tc_min / 60.0
    # Tropical short-duration IDF curve: i(t) = (R24 / 24) * (24 / t_hr)^(2/3)
    base_i = (hydro.idf_r24_mm / 24.0) * float((24.0 / tc_hr) ** (2.0 / 3.0))
    design_i = base_i * (1.0 + hydro.climate_uplift_pct / 100.0)
    q_peak = rational_peak_runoff_m3_s(
        catchment_area_ha=hydro.catchment_area_ha,
        rainfall_intensity_mm_hr=design_i,
        runoff_coefficient=c_val,
    )

    # Select smallest barrel config whose 80%-depth safe capacity (freeboard for debris) >= q_peak
    chosen_n = 1
    chosen_d = _STANDARD_PIPE_MM[-1]
    chosen_cap = 0.0
    chosen_vel = 0.0
    found = False

    for count in (1, 2, 3, 4):
        for d_mm in _STANDARD_PIPE_MM:
            q_full, v_full = _circular_manning_full(d_mm / 1000.0, hydro.culvert_slope, hydro.manning_n)
            safe_cap = count * q_full * 0.85  # 15% freeboard against woody debris clogging
            if safe_cap >= q_peak:
                chosen_n = count
                chosen_d = d_mm
                chosen_cap = safe_cap
                chosen_vel = v_full * min(1.12, (q_peak / max(1e-6, count * q_full)) ** 0.25)
                found = True
                break
        if found:
            break

    if not found:
        q_full, v_full = _circular_manning_full(1.5, hydro.culvert_slope, hydro.manning_n)
        chosen_n = max(4, math.ceil(q_peak / (q_full * 0.85)))
        chosen_d = 1500
        chosen_cap = chosen_n * q_full * 0.85
        chosen_vel = v_full

    # Approximate inlet-control HW/D ratio
    q_per_barrel = q_peak / chosen_n
    d_m = chosen_d / 1000.0
    hw_d = 0.55 + 0.65 * (q_per_barrel / (math.sqrt(9.81) * float(d_m**2.5)))

    self_clean = chosen_vel >= 0.75
    scour_req = chosen_vel > 2.5
    # Isbash riprap median stone diameter D50 (mm) for outlet apron energy dissipation
    riprap_mm = max(150, int(math.ceil((chosen_vel**2) * 32.0 / 50.0) * 50)) if scour_req else 0

    warnings: list[str] = []
    if not self_clean:
        warnings.append(
            f"SILTATION RISK: outlet velocity {chosen_vel:.2f} m/s < 0.75 m/s self-cleansing threshold; "
            "steepen culvert gradient slightly to >=0.5%."
        )
    if scour_req:
        warnings.append(
            f"OUTLET SCOUR HAZARD ({chosen_vel:.2f} m/s > 2.5 m/s): install stone-pitched headwall and "
            f"riprap apron (D50 >= {riprap_mm} mm) to prevent road embankment washout."
        )
    if hw_d > 1.2:
        warnings.append(
            f"HIGH HEADWATER (HW/D={hw_d:.2f} > 1.2): road overtopping risk; consider reinforced concrete box culvert."
        )

    return CulvertDesign(
        tc_minutes=round(tc_min, 1),
        design_intensity_mm_hr=round(design_i, 1),
        design_peak_q_m3_s=round(q_peak, 3),
        barrel_count=chosen_n,
        barrel_diameter_mm=chosen_d,
        total_capacity_80pct_full_m3_s=round(chosen_cap, 3),
        outlet_velocity_m_s=round(chosen_vel, 2),
        headwater_to_diameter_ratio=round(hw_d, 2),
        self_cleansing_ok=self_clean,
        scour_protection_required=scour_req,
        riprap_d50_mm=riprap_mm,
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class GravelMaintenancePlan:
    """HDM-4 style unpaved laterite feeder-road gravel loss and periodic re-gravelling budget."""

    road_length_km: float
    annual_gravel_loss_mm: float
    years_between_regravelling: float
    regravelling_volume_m3: float
    regravelling_cost_usd: float


def estimate_gravel_maintenance(
    *,
    road_length_km: float,
    carriageway_width_m: float = 6.0,
    adt_vehicles_day: float = 120.0,
    annual_rainfall_mm: float = 1200.0,
    avg_grade_pct: float = 4.0,
    initial_layer_mm: float = 150.0,
    min_layer_mm: float = 50.0,
    murram_usd_per_m3_compacted: float = 18.0,
) -> GravelMaintenancePlan:
    """Estimate annual laterite gravel thickness loss (mm/yr) and periodic re-gravelling cost."""
    if road_length_km <= 0 or carriageway_width_m <= 0 or initial_layer_mm <= min_layer_mm:
        raise ValueError("Invalid road dimensions or gravel layer thicknesses")
    # Empirical tropical gravel loss (mm/yr): traffic abrasion + rainfall erosion * gradient factor
    loss_mm_yr = 8.0 + (0.09 * adt_vehicles_day) + (0.012 * annual_rainfall_mm * (1.0 + 0.08 * avg_grade_pct))
    cycle_yrs = (initial_layer_mm - min_layer_mm) / loss_mm_yr
    # Re-gravel back to initial_layer_mm with 1.25 loose-to-compacted bulking factor
    replenish_m = (initial_layer_mm - min_layer_mm) / 1000.0
    vol_m3 = road_length_km * 1000.0 * carriageway_width_m * replenish_m * 1.25
    cost = vol_m3 * murram_usd_per_m3_compacted
    return GravelMaintenancePlan(
        road_length_km=round(road_length_km, 2),
        annual_gravel_loss_mm=round(loss_mm_yr, 1),
        years_between_regravelling=round(cycle_yrs, 2),
        regravelling_volume_m3=round(vol_m3, 1),
        regravelling_cost_usd=round(cost, 2),
    )
