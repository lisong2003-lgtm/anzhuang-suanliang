#!/usr/bin/env python3
"""扫描安装图纸 DWG：管线分段、设备、文本、块计数、属性组、楼层锚点。"""
from __future__ import annotations

import argparse
import json
import math
import re
import os
import sys
from collections import defaultdict
from pathlib import Path

try:
    import resource  # type: ignore
except ImportError:
    resource = None


def resolve_cad_skill_dir() -> Path:
    """按环境变量、同级技能目录和常见安装位置查找 cad-file-reader。"""
    candidates: list[Path] = []
    override = os.environ.get("CAD_SKILL_DIR", "").strip()
    if override:
        candidates.append(Path(override).expanduser())
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "cad-file-reader")
    candidates.extend([
        Path.home() / ".codex" / "skills" / "cad-file-reader",
        Path.home() / ".claude" / "skills" / "cad-file-reader",
    ])
    for candidate in candidates:
        if (candidate / "scripts").exists() and (candidate / "vendor").exists():
            return candidate.resolve()
    raise RuntimeError(
        "未找到 cad-file-reader；请先安装该技能，或设置 CAD_SKILL_DIR 指向其目录。"
    )


CAD_SKILL_DIR = resolve_cad_skill_dir()
VENDOR = CAD_SKILL_DIR / "vendor"
SCRIPTS = CAD_SKILL_DIR / "scripts"


def cad_reader_info() -> dict:
    """记录识图底座版本和测量候选兼容状态，便于扫描结果追溯。"""
    version = ""
    try:
        version = str(json.loads((CAD_SKILL_DIR / "manifest.json").read_text(encoding="utf-8")).get("version") or "")
    except Exception:
        pass
    parts = []
    for piece in version.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    compatible = len(parts) >= 2 and (parts[0], parts[1]) >= (0, 25)
    return {"version": version, "measurement_candidates_compatible": compatible}
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(VENDOR))

import ezdwg  # noqa: E402
import read_cad  # noqa: E402

SEG_LAYER_RE = re.compile(r"(WIRE|PIPE|CABLETRAY|BUSB|LGT|E-WIRE|E-CABLETRAY)", re.I)
FLOOR_RE = re.compile(r"^(JF|[1-9]F|ROOF|RF|B1|B2)$")
UNICODE_ESCAPE_RE = re.compile(r"(?:\\U\+|U\+)([0-9A-Fa-f]{4})")


def decode_cad_text(text: str) -> str:
    """补齐 ezdwg 保留在部分属性文本中的 \\U+ 转义。"""
    return UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


def peak_rss_mb() -> int:
    if resource is None:
        return 0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(rss / 1048576) if sys.platform == "darwin" else int(rss / 1024)


def sane(*vals) -> bool:
    for v in vals:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return False
        if not (math.isfinite(f) and abs(f) < 1e12):
            return False
    return True


def poly_len(points, bulges, closed) -> float:
    n = len(points)
    if n < 2:
        return 0.0
    total = 0.0
    segs = n if closed else n - 1
    for i in range(segs):
        a, b = points[i], points[(i + 1) % n]
        chord = math.hypot(b[0] - a[0], b[1] - a[1])
        bulge = 0.0
        if bulges and i < len(bulges):
            try:
                bulge = float(bulges[i] or 0.0)
            except (TypeError, ValueError):
                pass
        if abs(bulge) > 1e-9 and chord > 1e-9:
            theta = 4.0 * math.atan(abs(bulge))
            total += chord / (2.0 * math.sin(theta / 2.0)) * theta
        else:
            total += chord
    return total


def scan(path: str, max_text: int = 40000, left_boundary_mm: float | None = None) -> dict:
    doc = ezdwg.read(path)
    _layers, layer_by_handle = read_cad._raw_dwg_layers(path)
    default_layer = next(iter(layer_by_handle.values()), "0") if layer_by_handle else "0"

    wire = defaultdict(lambda: {"entities": 0, "length_mm": 0.0})
    segments = []
    pipe_segments = []
    inserts = defaultdict(int)
    attrib_groups = defaultdict(lambda: defaultdict(int))
    devices = []
    texts = []
    floor_labels = {}
    entity_counts = defaultdict(int)

    for e in doc.modelspace().iter_entities():
        dxftype = str(getattr(e, "dxftype", ""))
        entity_counts[dxftype] += 1
        dxf = getattr(e, "dxf", {}) or {}
        h = dxf.get("layer_handle")
        layer = default_layer if h in (None, 0) else layer_by_handle.get(h, f"handle:{h}")

        if dxftype in ("LINE", "LWPOLYLINE"):
            pts = []
            if dxftype == "LINE":
                s, t = dxf.get("start") or (), dxf.get("end") or ()
                if len(s) >= 2 and len(t) >= 2 and sane(s[0], s[1], t[0], t[1]):
                    z1 = float(s[2]) if len(s) > 2 and sane(s[2]) else 0.0
                    z2 = float(t[2]) if len(t) > 2 and sane(t[2]) else 0.0
                    pts = [(float(s[0]), float(s[1]), z1), (float(t[0]), float(t[1]), z2)]
            else:
                elevation = float(dxf.get("elevation") or 0) if sane(dxf.get("elevation") or 0) else 0.0
                pts = [(p[0], p[1], elevation)
                       for p in (dxf.get("points") or []) if sane(p[0], p[1])]
            if len(pts) >= 2:
                length = poly_len(
                    pts,
                    dxf.get("bulges") or [] if dxftype == "LWPOLYLINE" else [],
                    bool(dxf.get("closed")),
                )
                if length > 0:
                    wire[layer]["entities"] += 1
                    wire[layer]["length_mm"] += length
                    if SEG_LAYER_RE.search(layer):
                        for seg_i, (a, b) in enumerate(zip(pts, pts[1:])):
                            seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
                            if seg_len > 0:
                                segments.append(
                                    [layer, round(seg_len, 1),
                                     round((a[0] + b[0]) / 2, 1), round((a[1] + b[1]) / 2, 1)]
                                )
                                if layer.startswith("PIPE-"):
                                    bulge = 0.0
                                    if dxftype == "LWPOLYLINE" and dxf.get("bulges"):
                                        try:
                                            bulge = float(dxf["bulges"][seg_i] or 0)
                                        except (TypeError, ValueError, IndexError):
                                            pass
                                    pipe_len = poly_len([a, b], [bulge], False)
                                    pipe_segments.append(
                                        [layer, round(pipe_len, 1),
                                         round(a[0], 1), round(a[1], 1), round(a[2], 1),
                                         round(b[0], 1), round(b[1], 1), round(b[2], 1)]
                                    )

        elif dxftype in ("INSERT", "MINSERT"):
            name = str(dxf.get("name") or "")
            if name:
                inserts[name] += 1

        elif dxftype == "ATTRIB":
            text = decode_cad_text(str(dxf.get("text") or "")).strip()
            tag = str(dxf.get("tag") or "").strip()
            pos = dxf.get("insert") or ()
            if text:
                attrib_groups[tag][text] += 1
                if len(pos) >= 2 and sane(pos[0], pos[1]):
                    devices.append({"text": text, "tag": tag,
                                    "x": float(pos[0]), "y": float(pos[1])})

        elif dxftype in ("TEXT", "MTEXT") and len(texts) < max_text:
            text = decode_cad_text(str(dxf.get("text") or dxf.get("raw_text") or "")).strip()
            pos = dxf.get("insert") or ()
            if text and len(pos) >= 2 and sane(pos[0], pos[1]):
                texts.append({"layer": layer, "text": text,
                              "x": float(pos[0]), "y": float(pos[1]),
                              "h": float(dxf.get("height") or 0)})
                if FLOOR_RE.match(text) and float(dxf.get("height") or 0) >= 10000:
                    floor_labels.setdefault(text, [float(pos[0]), float(pos[1])])

    zones = sorted(floor_labels, key=lambda k: floor_labels[k][0])
    xs = [floor_labels[z][0] for z in zones]
    bounds = [0.0] + [(a + b) / 2 for a, b in zip(xs, xs[1:])] + [float("inf")]

    def zone_of(x: float) -> str:
        if left_boundary_mm is not None and x < left_boundary_mm:
            return "左图区"
        for i, z in enumerate(zones):
            if bounds[i] <= x < bounds[i + 1]:
                return z
        return zones[0] if zones else "全图"

    dev_by_zone = defaultdict(lambda: defaultdict(int))
    seg_by_zone = defaultdict(lambda: defaultdict(float))
    for layer, length, x, _y in segments:
        seg_by_zone[zone_of(x)][layer] += length
    for rec in devices:
        dev_by_zone[zone_of(rec["x"])][rec["text"]] += 1

    return {
        "ok": True,
        "file": Path(path).name,
        "path": path,
        "entity_counts": dict(sorted(entity_counts.items(), key=lambda kv: -kv[1])),
        "wire_layers": {k: {"entities": v["entities"], "length_mm": round(v["length_mm"], 1)}
                        for k, v in sorted(wire.items(), key=lambda kv: -kv[1]["length_mm"])},
        "segments": segments,
        "pipe_segments": pipe_segments,
        "inserts": dict(sorted(inserts.items(), key=lambda kv: -kv[1])),
        "attrib_groups": {tag: dict(sorted(t.items(), key=lambda kv: -kv[1]))
                          for tag, t in attrib_groups.items()},
        "devices": devices,
        "texts": texts,
        "floor_labels": floor_labels,
        "wire_by_zone": {z: {k: round(v / 1000, 1) for k, v in sorted(ls.items(), key=lambda kv: -kv[1])}
                         for z, ls in seg_by_zone.items()},
        "devices_by_zone": {z: dict(sorted(d.items(), key=lambda kv: -kv[1]))
                            for z, d in dev_by_zone.items()},
        "cad_reader": cad_reader_info(),
        "peak_rss_mb": peak_rss_mb(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dwg")
    ap.add_argument("--out", required=True, help="输出 JSON 路径")
    ap.add_argument("--max-text", type=int, default=40000)
    ap.add_argument("--left-boundary-mm", type=float, default=None,
                    help="同文件左侧独立图区（应急/桥架等）的 x 分界，单位 mm")
    args = ap.parse_args()
    result = scan(args.dwg, args.max_text, args.left_boundary_mm)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(f"OK {result['file']} 段数={len(result['segments'])} "
          f"文本={len(result['texts'])} 峰值RSS={result['peak_rss_mb']}MB")


if __name__ == "__main__":
    main()
