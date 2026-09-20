#!/usr/bin/env python3
"""自检：解析与匹配逻辑最小验证。运行：python3 self_test.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mep_plan import (  # noqa: E402
    box_circuits, boxed_system_specs, connectivity_check, conservation_row,
    device_rows, material_rows, match_circuits, parse_spec, spec_tables,
    support_estimates, trunk_cables, riser_identification, trunk_routes,
    unmatched_clusters, tray_route_totals, water_diameter,
    water_segment_specs, water_system, water_zone, wire_expanded_length,
    measurement_candidates,
)


def main() -> None:
    info = parse_spec("WDZC-BYJ-3×2.5-PC20-WC.CC")
    assert info["conduit"] == "PC20" and info["cores"] == 3 and not info["is_cable"], info
    info = parse_spec("WDZB-YJY-5x16-MR")
    assert info["is_cable"] and info["cores"] == 5 and info["tray"], info

    sys_scan = {"texts": [{"text": "WL1:WDZC-BYJ-3X2.5-PC20-WC.CC", "x": 0, "y": 0}]}
    specs, ctype = spec_tables([sys_scan])
    assert specs["WL1"]["WDZC-BYJ-3X2.5-PC20"] == 1 and ctype["L"] == "照明"

    sys_two = {
        "texts": [
            {"text": "B1AL1", "x": 0, "y": 0},
            {"text": "WL1:WDZC-BYJ-3X2.5-PC20", "x": 1000, "y": 1000},
            {"text": "B1AL2", "x": 100_000, "y": 100_000},
            {"text": "WL1:WDZC-BYJ-3X4-PC20", "x": 101_000, "y": 101_000},
        ]
    }
    boxed = boxed_system_specs([sys_two], radius_mm=100_000)
    assert boxed[("B1AL1", "WL1")]["WDZC-BYJ-3X2.5-PC20"] == 1, boxed
    assert boxed[("B1AL2", "WL1")]["WDZC-BYJ-3X4-PC20"] == 1, boxed

    plan = {
        "file": "plan.dwg",
        "texts": [{"text": "1-1AL1:WL1", "x": 1000, "y": 1000}],
        "segments": [["WIRE-照明", 5_000_000, 1100, 1100],
                     ["WIRE-照明", 5_000_000, 20_000, 20_000],
                     ["WIRE-照明", 5_000_000, 999_000, 999_000]],
    }
    by_spec, by_layer, amb = match_circuits(
        [plan], specs, radius_mm=30_000, high_radius_mm=10_000
    )
    assert abs(by_spec["WDZC-BYJ-3X2.5-PC20"]["length_mm"] - 10_000_000) < 1e-6
    assert by_spec["WDZC-BYJ-3X2.5-PC20"]["confidence"]["高"] == 5_000_000
    assert by_spec["WDZC-BYJ-3X2.5-PC20"]["confidence"]["中"] == 5_000_000
    assert by_spec["WDZC-BYJ-3X2.5-PC20"]["sources"]["plan.dwg"] == 10_000_000
    assert abs(by_layer["WIRE-照明"]["matched"] - 10_000_000) < 1e-6
    assert abs(by_layer["WIRE-照明"]["total"] - 15_000_000) < 1e-6 and not amb

    boxes = box_circuits([plan], specs, radius_mm=30_000)
    assert boxes[0]["box"] == "1-1AL1" and boxes[0]["circuit"] == "WL1", boxes
    assert boxes[0]["spec"] == "WDZC-BYJ-3X2.5-PC20"
    assert boxes[0]["length_mm"] == 10_000_000 and boxes[0]["objects"] == 2

    clusters = unmatched_clusters([plan], specs, radius_mm=30_000)
    assert len(clusters) == 1 and clusters[0]["length_mm"] == 5_000_000, clusters
    assert clusters[0]["layers"]["WIRE-照明"] == 5_000_000

    by_dn, inferred, un = water_diameter(
        [{"texts": [{"text": "DN100", "x": 0, "y": 0}],
          "segments": [["PIPE-给水", 4_000_000, 100, 100],
                       ["PIPE-给水", 4_000_000, 20_000, 20_000],
                       ["PIPE-给水", 4_000_000, 900_000, 900_000]]}],
        radius_mm=15_000,
        fallback_radius_mm=30_000,
    )
    assert by_dn[("PIPE-给水", "DN100")] == 4_000_000
    assert inferred[("PIPE-给水", "DN100")] == 4_000_000
    assert un["PIPE-给水"] == 4_000_000

    assert water_system("PIPE-给水2区") == "给水"
    assert water_zone("PIPE-给水2区", "给水") == "2区"
    by_dn2, _inferred2, _un2 = water_diameter(
        [{"texts": [{"layer": "TEXT_给水", "text": "DN100", "x": 0, "y": 0},
                    {"layer": "TEXT_消防", "text": "DN200", "x": 0, "y": 0}],
          "segments": [["PIPE-给水", 4_000_000, 100, 100],
                       ["PIPE-消防", 5_000_000, 100, 100]]}],
        radius_mm=15_000,
    )
    assert by_dn2[("PIPE-给水", "DN100")] == 4_000_000
    assert by_dn2[("PIPE-消防", "DN200")] == 5_000_000

    pipe_scan = {
        "file": "pipe.dwg",
        "pipe_segments": [
            ["PIPE-给水", 1_000_000, 0, 0, 0, 1000_000, 0, 0],
            ["PIPE-给水", 1_000_000, 1_100_000, 0, 0, 2_000_000, 0, 0],
        ],
        "texts": [{"layer": "TEXT_给水", "text": "DN100", "x": 500_000, "y": 500},
                  {"layer": "TEXT_给水", "text": "DN100", "x": 1_550_000, "y": 500}],
    }
    records = water_segment_specs([pipe_scan], radius_mm=15_000, fallback_radius_mm=30_000)
    assert len(records) == 2 and all(r["dn"] == "DN100" for r in records), records
    summary, rows = connectivity_check(records, {"water_connect_radius_mm": 150_000,
                                                 "connectivity_grid_mm": 10_000_000})
    assert summary[0][1] == 2 and summary[2][1] == 2, summary
    assert len(rows) == 1 and rows[0][2] == "DN100" and rows[0][6] == 2, rows

    risers = riser_identification(
        [{"texts": [{"layer": "DIM_污水", "text": "WL-B1/B1'", "x": 0, "y": 0},
                    {"layer": "WPK图框", "text": "HYL-X", "x": 1, "y": 1}]}]
    )
    assert [(r["system"], r["id"].upper()) for r in risers] == [
        ("污水", "WL-B1"), ("污水", "WL-B1'")
    ], risers

    rows = support_estimates(by_dn, un, 3_000, {
        "water_support_spacing_m": {"supply": {"DN100": 4.0, "default": 3.0}},
        "tray_support_spacing_m": 1.5,
    })
    assert ["PIPE-给水", "DN100", 4000.0, 4.0, 1000, ""] in rows
    assert ["PIPE-给水", "默认", 4000.0, 3.0, 1334, ""] in rows
    assert ["桥架", "全部", 3.0, 1.5, 2, "水平吊架估算"] in rows

    trunks = trunk_cables(
        [{"texts": [{"text": "WDZB-YJY-4x50+1x25-MR", "x": 0, "y": 0},
                    {"text": "WL1:WDZC-BYJ-3X2.5-PC20", "x": 1, "y": 1}]}]
    )
    assert trunks["WDZB-YJY-4x50+1x25-MR"] == 1 and len(trunks) == 1

    trunk_scan = {
        "file": "trunk.dwg",
        "texts": [{"text": "WDZB-YJY-4x50+1x25-MR", "x": 0, "y": 0}],
        "segments": [["CABLETRAY", 2_000_000, 1_000, 1_000],
                     ["CABLETRAY", 1_000_000, 90_000, 90_000]],
    }
    matched, unmatched, layers, conf = trunk_routes([trunk_scan], radius_mm=30_000)
    assert matched["WDZB-YJY-4x50+1x25-MR"] == 2_000_000
    assert unmatched["CABLETRAY"] == 1_000_000
    assert layers["CABLETRAY"] == [3_000_000, 2]
    assert conf["CABLETRAY"]["高"] == 2_000_000
    assert conf["CABLETRAY"]["低"] == 1_000_000

    tray_total, tray_excluded = tray_route_totals(
        [{"segments": [["CABLETRAY", 60_000, 0, 0], ["CABLETRAY", 2_000, 0, 0]]}],
        max_segment_mm=50_000,
    )
    assert tray_total == 2_000 and tray_excluded == 60_000, (tray_total, tray_excluded)
    assert wire_expanded_length(10, 3, 3) == 39

    row = conservation_row("测试", 10_000_000, 10_000_000)
    assert row[-1] == "通过" and abs(row[3]) < 1e-6
    assert conservation_row("测试", 10_000_000, 9_000_000)[-1] == "异常"

    scans = [
        {"file": "a.dwg", "attrib_groups": {"A": {"照明配电箱": 2}},
         "devices": [{"tag": "WHAT", "text": "闸阀", "x": 0, "y": 0},
                     {"tag": "SPEC", "text": "DN25", "x": 1000, "y": 0},
                     {"tag": "UN", "text": "个", "x": 2000, "y": 0}]},
        {"file": "b.dwg", "attrib_groups": {"A": {"照明配电箱": 3}},
         "devices": [{"tag": "WHAT", "text": "闸阀", "x": 0, "y": 0},
                     {"tag": "SPEC", "text": "DN25", "x": 1000, "y": 0},
                     {"tag": "UN", "text": "个", "x": 2000, "y": 0}]},
    ]
    devices = device_rows(scans)
    assert devices[0][0] == "照明配电箱" and devices[0][1] == 5
    assert set(devices[0][2]) == {"a.dwg", "b.dwg"}
    materials = material_rows(scans)
    assert materials[0]["name"] == "闸阀" and materials[0]["spec"] == "DN25"
    assert materials[0]["qty"] == 2 and len(materials[0]["sources"]) == 2
    assert measurement_candidates({"measurements": [{"id": "m1", "kind": "length", "value": 3.0, "final_quantity": False}]})[0]["id"] == "m1"
    print("self_test OK")


if __name__ == "__main__":
    main()
