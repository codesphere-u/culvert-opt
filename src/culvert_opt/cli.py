"""CLI entrypoint for culvert-opt."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .drainage import CatchmentHydrology, design_road_culvert, estimate_gravel_maintenance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="culvert-opt",
        description="Size rural feeder-road drainage culverts (Rational + Manning) and re-gravelling budgets.",
    )
    parser.add_argument("--area-ha", type=float, default=35.0, help="Upstream catchment area (ha).")
    parser.add_argument("--flow-length-m", type=float, default=750.0, help="Longest catchment flow path (m).")
    parser.add_argument("--catchment-slope", type=float, default=0.04, help="Average catchment slope (m/m).")
    parser.add_argument("--land-cover", default="smallholder_farmland", help="Land cover runoff key.")
    parser.add_argument("--r24-mm", type=float, default=120.0, help="25-year 24-hour design storm depth (mm).")
    parser.add_argument("--road-km", type=float, default=12.0, help="Feeder-road length for gravel budget (km).")
    args = parser.parse_args(argv)

    culv = design_road_culvert(
        CatchmentHydrology(
            catchment_area_ha=args.area_ha,
            flow_length_m=args.flow_length_m,
            catchment_slope=args.catchment_slope,
            land_cover=args.land_cover,
            idf_r24_mm=args.r24_mm,
        )
    )
    gravel = estimate_gravel_maintenance(road_length_km=args.road_km)
    print(json.dumps({"culvert_design": asdict(culv), "gravel_maintenance": asdict(gravel)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
