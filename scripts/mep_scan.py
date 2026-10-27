#!/usr/bin/env python3
"""扫描安装图纸 DWG：管线分段、设备、文本、块计数、属性组、楼层锚点。"""
from __future__ import annotations

try:
    import os as _boot_os, sys as _boot_sys
    _boot_sys.path.insert(0, _boot_os.path.dirname(_boot_os.path.abspath(__file__)))
    import pyboot as _boot_pyboot
    _boot_pyboot.ensure_utf8_io()
except Exception:
    pass


import argparse
import json
import math
import re
import os
import sys

import i18n
from collections import defaultdict
from pathlib import Path

try:
    import resource  # type: ignore
except ImportError:
    resource = None


def _ensure_base() -> Path:
    """显式依赖底座：优先 CAD_SKILL_DIR，未装时自动下载安装 cad-file-reader，并自动补齐其 vendor。"""
    import subprocess
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
        if (candidate / "scripts").exists():
            return candidate.resolve()

    script = Path(__file__).resolve().parent / "ensure_base.sh"
    if script.is_file():
        env = None
        if override:
            env = {**os.environ, "CAD_SKILL_DIR": override}
        res = subprocess.run(["bash", str(script)], capture_output=True,
                             text=True, env=env)
        out = res.stdout.strip()
        if res.returncode == 0 and out:
            return Path(out)
        raise RuntimeError(
            "未找到识图底座 cad-file-reader，且自动安装失败。"
            "请联网重试，或设 CAD_SKILL_DIR 指向底座；离线可设 SKILL_NO_BASE=1 使用已有扫描结果降级。"
        )
    raise RuntimeError("未找到 cad-file-reader；请先安装该技能，或设置 CAD_SKILL_DIR 指向其目录。")


CAD_SKILL_DIR = _ensure_base()
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
if VENDOR.is_dir():
    sys.path.insert(0, str(VENDOR))

sys.path.insert(0, str(SCRIPTS))
import ezdwg  # noqa: E402
import read_cad  # noqa: E402

SEG_LAYER_RE = re.compile(r"(WIRE|PIPE|CABLETRAY|BUSB|LGT|E-WIRE|E-CABLETRAY)", re.I)
OUTDOOR_LAYER_RE = re.compile(
    r"(强电|弱电|电缆|排管|电缆沟|管网|综合管网|室外管网|雨水|污水|废水|给水|中水|消防|喷淋|燃气|热力|暖通|采暖|供热|通信|照明|景观|路灯|SITE[_-]?PIPE|OUTDOOR|DIM_|EQUIP_|管线-|HEATER|HEATING)",
    re.I,
)


def route_layer(layer: str, domain: str = "auto") -> bool:
    """判断图层是否可作为安装路由；auto 兼容室内，outdoor 扩展室外管网。"""
    if domain == "indoor":
        return bool(SEG_LAYER_RE.search(layer))
    if domain == "outdoor":
        return bool(SEG_LAYER_RE.search(layer) or OUTDOOR_LAYER_RE.search(layer))
    return bool(SEG_LAYER_RE.search(layer) or OUTDOOR_LAYER_RE.search(layer))


def pipe_layer(layer: str) -> bool:
    """判断图层是否属于给排水/管网管段，供管径标注匹配使用。"""
    return layer.upper().startswith("PIPE-") or bool(re.search(r"(管网|室外管网|雨水|污水|废水|给水|中水|消防|喷淋|燃气|热力|暖通|采暖|供热|SITE[_-]?PIPE|DIM_|EQUIP_|管线-|HEATER|HEATING)", layer, re.I))
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


def infer_unit_from_doc(doc: object, max_segments: int = 5000) -> dict:
    """在 INSUNITS=0 时用图面线段长度中位数给出保守单位候选。

    室外总图常用米作坐标、但 INSUNITS 仍为 0；如果中位数远小于常见毫米
    构件长度，则判为 m。推断结果仍标记为 auto_inferred，不是人工确认。
    """
    lengths: list[float] = []
    try:
        for entity in doc.modelspace().iter_entities():
            dxftype = str(getattr(entity, "dxftype", ""))
            dxf = getattr(entity, "dxf", {}) or {}
            if dxftype == "LINE":
                start, end = dxf.get("start") or (), dxf.get("end") or ()
                if len(start) >= 2 and len(end) >= 2 and sane(start[0], start[1], end[0], end[1]):
                    length = math.hypot(float(end[0]) - float(start[0]), float(end[1]) - float(start[1]))
                    if length > 0:
                        lengths.append(length)
            elif dxftype == "LWPOLYLINE":
                points = [(float(p[0]), float(p[1])) for p in (dxf.get("points") or []) if sane(p[0], p[1])]
                for a, b in zip(points, points[1:]):
                    length = math.hypot(b[0] - a[0], b[1] - a[1])
                    if length > 0:
                        lengths.append(length)
            if len(lengths) >= max_segments:
                break
    except Exception:
        return {"unit": "unknown", "median": None, "sample_count": 0, "reason": "无法读取几何"}
    if len(lengths) < 20:
        return {"unit": "unknown", "median": None, "sample_count": len(lengths),
                "reason": "有效线段不足20条，无法保守推断"}
    lengths.sort()
    median = lengths[len(lengths) // 2]
    # 毫米建筑图常见分段远大于 100 mm；米制总图常见分段小于 100。
    if 0.1 <= median <= 100.0:
        return {"unit": "m", "median": round(median, 4), "sample_count": len(lengths),
                "reason": f"线段长度中位数 {median:.3g}，按室外米制总图推断；请用原图尺寸复核"}
    if median >= 500.0:
        return {"unit": "mm", "median": round(median, 4), "sample_count": len(lengths),
                "reason": f"线段长度中位数 {median:.3g}，按毫米图推断"}
    return {"unit": "unknown", "median": round(median, 4), "sample_count": len(lengths),
            "reason": "单位推断落在灰区，需人工确认"}


def drawing_unit_info(doc: object, requested: str = "auto") -> dict:
    """读取 $INSUNITS，必要时按调用方声明归一化到毫米。

    INSUNITS=0/None 在旧图里很常见；可用图面线段中位数做保守推断，
    但仍把结果标成 auto_inferred，并提示用原图尺寸人工复核。
    """
    header: dict = {}
    try:
        header = doc.header_variables() or {}
    except Exception:
        header = {}
    code = header.get("insunits")
    detected = "unknown"
    if code == 4:
        detected = "mm"
    elif code == 6:
        detected = "m"
    inference = {"unit": "unknown", "median": None, "sample_count": 0, "reason": ""}
    if requested == "auto" and detected == "unknown":
        inference = infer_unit_from_doc(doc)
        if inference["unit"] in {"m", "mm"}:
            detected = inference["unit"]
            status = "auto_inferred"
    effective = requested if requested != "auto" else detected
    if effective not in {"mm", "m"}:
        effective = "unknown"
    factor = 1000.0 if effective == "m" else (1.0 if effective == "mm" else 1.0)
    if requested != "auto" and effective != "unknown":
        status = "confirmed_by_user"
    elif detected != "unknown":
        status = status if status == "auto_inferred" else "auto"
    else:
        status = "review"
    return {
        "insunits": code,
        "ltscale": header.get("ltscale"),
        "textsize": header.get("textsize"),
        "detected": detected,
        "effective": effective,
        "coord_scale_to_mm": factor,
        "length_scale_to_mm": factor,
        "status": status,
        "unit_inference": inference,
        "review_reason": "" if status != "review" else "INSUNITS=0/未知，图面坐标单位未确认；如已知则用 --unit mm 或 --unit m 重扫",
    }


def scan(path: str, max_text: int = 40000, left_boundary_mm: float | None = None, domain: str = "auto", unit: str = "auto") -> dict:
    doc = ezdwg.read(path)
    _layers, layer_by_handle = read_cad._raw_dwg_layers(path)
    default_layer = next(iter(layer_by_handle.values()), "0") if layer_by_handle else "0"
    unit_info = drawing_unit_info(doc, unit)
    coord_scale = float(unit_info["coord_scale_to_mm"])
    length_scale = float(unit_info["length_scale_to_mm"])

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
                    length *= length_scale
                    wire[layer]["entities"] += 1
                    wire[layer]["length_mm"] += length
                    if route_layer(layer, domain):
                        for seg_i, (a, b) in enumerate(zip(pts, pts[1:])):
                            seg_len = math.hypot(b[0] - a[0], b[1] - a[1]) * length_scale
                            if seg_len > 0:
                                segments.append(
                                    [layer, round(seg_len, 1),
                                     round((a[0] + b[0]) / 2 * coord_scale, 1), round((a[1] + b[1]) / 2 * coord_scale, 1)]
                                )
                                if pipe_layer(layer):
                                    bulge = 0.0
                                    if dxftype == "LWPOLYLINE" and dxf.get("bulges"):
                                        try:
                                            bulge = float(dxf["bulges"][seg_i] or 0)
                                        except (TypeError, ValueError, IndexError):
                                            pass
                                    pipe_len = poly_len([a, b], [bulge], False) * length_scale
                                    pipe_segments.append(
                                        [layer, round(pipe_len, 1),
                                         round(a[0] * coord_scale, 1), round(a[1] * coord_scale, 1), round(a[2] * length_scale, 1),
                                         round(b[0] * coord_scale, 1), round(b[1] * coord_scale, 1), round(b[2] * length_scale, 1)]
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
                                    "x": float(pos[0]) * coord_scale, "y": float(pos[1]) * coord_scale})

        elif dxftype in ("TEXT", "MTEXT") and len(texts) < max_text:
            text = decode_cad_text(str(dxf.get("text") or dxf.get("raw_text") or "")).strip()
            pos = dxf.get("insert") or ()
            if text and len(pos) >= 2 and sane(pos[0], pos[1]):
                texts.append({"layer": layer, "text": text,
                              "x": float(pos[0]) * coord_scale, "y": float(pos[1]) * coord_scale,
                              "h": float(dxf.get("height") or 0) * length_scale})
                if FLOOR_RE.match(text) and float(dxf.get("height") or 0) >= 10000:
                    floor_labels.setdefault(text, [float(pos[0]) * coord_scale, float(pos[1]) * coord_scale])

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
        "domain": domain,
        "drawing_unit": unit_info,
        "geometry_scope": "modelspace_only",
        "block_reference_count": sum(inserts.values()),
        "block_geometry_review": "图面可能包含块参照内线路；本扫描只统计 modelspace 顶层实体，块内管段需用原图或专项块展开核对" if inserts else "",
        "cad_reader": cad_reader_info(),
        "peak_rss_mb": peak_rss_mb(),
    }


def main() -> None:
    raw = sys.argv[1:]
    lang = i18n.argv_lang(raw)
    desc = (__doc__ if lang == "zh" else
            "Scan MEP DWG drawings: pipe segments, devices, text, block counts, attributes, floor anchors.")
    ap = argparse.ArgumentParser(description=desc)
    i18n.add_lang_arg(ap, default=lang)
    ap.add_argument("dwg", help="input DWG drawing" if lang == "en" else "输入 DWG 图纸")
    ap.add_argument("--out", required=True, help="output JSON path" if lang == "en" else "输出 JSON 路径")
    ap.add_argument("--max-text", type=int, default=40000,
                    help="max text records to keep (default 40000)" if lang == "en" else "最大文本数")
    ap.add_argument("--left-boundary-mm", type=float, default=None,
                    help="x split of an independent drawing zone on the left (e.g. emergency / trunk), in mm" if lang == "en" else "同文件左侧独立图区（应急/桥架等）的 x 分界，单位 mm")
    ap.add_argument("--domain", choices=("auto", "indoor", "outdoor"), default="auto",
                    help="interpretation domain; outdoor for external pipe networks / landscape electric" if lang == "en" else "识图域；室外综合管网/景观电气用 outdoor")
    ap.add_argument("--unit", choices=("auto", "mm", "m"), default="auto",
                    help="drawing coordinate unit; use --unit mm/m when INSUNITS=0" if lang == "en" else "图面坐标单位；INSUNITS=0 时可用 --unit mm/m 显式确认")
    args = ap.parse_args(raw)
    result = scan(args.dwg, args.max_text, args.left_boundary_mm, args.domain, args.unit)
    out_doc = {
        "status": "ok",
        "message": ("scan completed" if lang == "en" else "扫描完成"),
        "schema": result.get("schema", "anzhuang-suanliang/mep-scan/v0"),
    }
    result.setdefault("meta", {}).update(out_doc)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    if lang == "en":
        print(f"OK {result['file']} segments={len(result['segments'])} "
              f"texts={len(result['texts'])} peak_rss={result['peak_rss_mb']}MB")
    else:
        print(f"OK {result['file']} 段数={len(result['segments'])} "
              f"文本={len(result['texts'])} 峰值RSS={result['peak_rss_mb']}MB")


if __name__ == "__main__":
    main()
