#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安装算量 -> lis-skill-bus 可选接线（不侵入算量核心）。

push  : 把本技能输出契约包装成 cad-contract/v1 并发到 lis-skill-bus
        （优先 skillbus_client.py；bus 未安装时直接写本机默认状态文件，
        与 bus 同构，不报错）。
pull  : 从 bus 拉取最近一次 cad-contract/v1，并按本专业 target sections 命中判定；
        命中且含可复用 section 时可选落盘 --out / --out-dir；未命中/缺字段/无 bus
        一律返回 hit=false / usable=false，由本技能走正常解析。

用法：
  python3 anzhuang_statesync.py push --entry-file 输出.json --project 项目 \
          [--building 楼栋] [--floor 楼层] [--specialty 安装] [--skill anzhuang-suanliang]
  python3 anzhuang_statesync.py pull --project 项目 [--building 楼栋] [--floor 楼层] \
          [--out 落盘.json] [--out-dir 输出目录] [--entry-id xxx] [--require-core|--require-all]

纯 stdlib、不联网、不读云；公司数据只落本机 SKILLBUS_STATE_DIR / 技能状态文件。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SKILL = "anzhuang-suanliang"
DEFAULT_SECTIONS = [
        'route_segments',
        'circuits',
        'systems',
        'equipment',
        'labels',
        'measurements',

]
DEFAULT_CORE_SECTIONS = [
        'circuits',
        'route_segments',
]
DEFAULT_SPECIALTY = "安装"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_STATE_FILE = Path(os.environ.get(
    "SKILLBUS_STATE_DIR",
    Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills" / ".skillbus",
)) / "state.json"


def log_err(msg: str) -> None:
    print(f"[{SKILL} statesync] {msg}", file=sys.stderr)


# ------------------------------------------------------------------------- bus 定位
def _candidate_paths() -> list[Path]:
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    out: list[Path] = []
    for var in ("SKILLBUS_HOME", "SKILLBUS_CLIENT"):
        raw = os.environ.get(var)
        if not raw:
            continue
        p = Path(raw) if var.endswith("CLIENT") else Path(raw) / "skillbus_client.py"
        out.append(p)
    out.append(codex_home / "mcp_servers" / "lis-skill-bus" / "skillbus_client.py")
    out.append(codex_home / "skills" / "lis-skill-bus" / "skillbus_client.py")
    out.append(codex_home / "skills" / ".skillbus" / "skillbus_client.py")
    patterns = (
        str(home / "Documents" / "Codex" / "*" / "tan" / "work" / "lis-skill-bus" / "skillbus_client.py"),
        str(home / "Documents" / "Codex" / "*" / "*" / "lis-skill-bus" / "skillbus_client.py"),
        str(home / "Documents" / "*" / "lis-skill-bus" / "skillbus_client.py"),
        str(home / ".codex" / "*" / "lis-skill-bus" / "skillbus_client.py"),
    )
    for pat in patterns:
        out.extend(Path(x) for x in glob.glob(pat))
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        r = str(p.resolve())
        if r not in seen:
            seen.add(r)
            uniq.append(p)
    return uniq


def _is_dev_copy(p: Path) -> bool:
    s = str(p.resolve()).replace("\\", "/")
    markers = (
        "/tan/work/",
        "/work/lis-skill-bus",
        "/lis-skill-bus-step",
        "/Documents/Codex/",
    )
    return any(m in s for m in markers)


def find_bus_client() -> Path | None:
    if os.environ.get("SKILLBUS_DISABLE") == "1":
        return None
    for p in _candidate_paths():
        if p.is_file():
            if _is_dev_copy(p):
                print(f"[{SKILL} statesync] bus 命中来源：{p}（临时副本/dev，非正式安装）", file=sys.stderr)
            else:
                print(f"[{SKILL} statesync] bus 命中来源：{p}（正式安装）", file=sys.stderr)
            return p
    return None


# ------------------------------------------------------------------------- 降级直写（与 bus state.json 同构）
def _key(project: str, building: str, floor: str) -> str:
    parts = [x for x in (project, building, floor) if x]
    return "__slash__".join(parts) if parts else "__project__"


def read_local_state() -> dict:
    if not DEFAULT_STATE_FILE.exists():
        return {"state_version": 1, "projects": {}}
    try:
        return json.loads(DEFAULT_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"state_version": 1, "projects": {}, "_corrupted": str(DEFAULT_STATE_FILE)}


def write_local_state(state: dict) -> None:
    DEFAULT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEFAULT_STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, DEFAULT_STATE_FILE)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def wrap_entry(entry: dict, project: str, building: str, floor: str, specialty: str, skill: str) -> dict:
    entry = dict(entry or {})
    if entry.get("schema") == "cad-contract/v1":
        pk = dict(entry.get("project_key") or {})
        for field, val in (("project", project), ("building", building),
                           ("floor", floor), ("zone", ""), ("room", "")):
            if val:
                pk[field] = val
        if specialty:
            pk["specialty"] = specialty
        entry["project_key"] = pk
        return entry
    pk = {
        "project": project, "building": building, "floor": floor,
        "zone": "", "room": "", "specialty": specialty or DEFAULT_SPECIALTY,
        "source": "file", "review_required": False,
    }
    src = entry.get("source") or {}
    if isinstance(src, dict) and "file" in src:
        file_name = str(src.get("file", ""))
        sha = str(src.get("sha256", ""))
    else:
        file_name = str(entry.get("source_file") or "")
        sha = str(entry.get("input_sha256") or "")
    contract = dict(entry)
    if "qto_spec" not in contract and isinstance(entry.get("contract"), dict) and entry["contract"].get("schema") == "qto-project/v1":
        contract = entry["contract"]
    return {
        "_id": f"{skill}:{project}:{building}:{floor}:{int(time.time() * 1000)}",
        "schema": "cad-contract/v1",
        "spec": "qto-project/v1",
        "version": "1",
        "project_key": pk,
        "producer": {
            "skill": skill,
            "schema": "qto-project/v1",
            "produced_at": _now(),
            "final_quantity": False,
        },
        "source": {"file": file_name, "sha256": sha, "page": None,
                   "evidence": [f"producer={skill}"]},
        "contract": contract,
        "review": {"review_required": False, "tier": "confirmed_evidence", "reason": []},
    }


def push_fallback(project: str, building: str, floor: str, entry: dict, skill: str) -> dict:
    state = read_local_state()
    key = _key(project, building, floor)
    bucket = state.setdefault("projects", {}).setdefault(key, {})
    entry = dict(entry or {})
    prov = dict(entry.get("_provenance") or {})
    prov.update({"source_skill": skill, "pushed_at": _now()})
    entry["_provenance"] = prov
    eid = entry.get("_id")
    if eid:
        old = bucket.get(eid)
        bucket[eid] = entry if old is None else {**(old or {}), **entry}
    else:
        entry = {**(bucket.get("_last") or {}), **entry}
        bucket["_last"] = entry
    write_local_state(state)
    return {"project_key": key, "saved": True, "degraded": True,
            "entry_id": eid or "_last", "count": len(bucket)}


def pull_fallback(project: str, building: str, floor: str) -> dict:
    state = read_local_state()
    key = _key(project, building, floor)
    bucket = state.get("projects", {}).get(key, {})
    picked = bucket.get("_last") or next(iter(bucket.values()), None)
    return {"project_key": key, "hit": picked is not None, "entry": picked}


# ------------------------------------------------------------------------- 命中判定
def _section_items(contract: dict, section: str):
    if not isinstance(contract, dict):
        return None
    direct = contract.get(section)
    if isinstance(direct, list):
        return direct
    nested = contract.get("sections")
    if isinstance(nested, dict):
        val = nested.get(section)
        if isinstance(val, list):
            return val
    return None


def match_sections(entry: dict, targets: list[str]) -> dict:
    c = (entry or {}).get("contract") or {}
    matched, missing, empty, review_flagged = [], [], [], []
    for s in targets:
        items = _section_items(c, s)
        if items is None:
            missing.append(s)
        elif len(items) == 0:
            empty.append(s)
        else:
            matched.append(s)
            if any(not isinstance(it, dict) for it in items):
                continue
            if any(str(it.get("confidence_tier")) == "review_required"
                   or "review_required" in str(it.get("review", ""))
                   or bool(it.get("review_required"))
                   for it in items if isinstance(it, dict)):
                review_flagged.append(s)
    return {"matched": matched, "missing": missing, "empty": empty,
            "review_flagged": review_flagged,
            "candidate_only": True, "usable": bool(matched)}



def _unique(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def apply_core_rule(entry, mm, core_targets):
    """--require-core：必选核心至少一个命中且非空才算 usable，否则缺项标进 review_flagged。"""
    core = match_sections(entry, core_targets)
    missing_core = [s for s in core_targets if s in core["missing"] or s in core["empty"]]
    core_matched = core["matched"]
    if not core_matched:
        return False, core_matched, missing_core, _unique(mm["review_flagged"] + missing_core)
    return True, core_matched, missing_core, list(mm["review_flagged"])


# ------------------------------------------------------------------------- 子命令
def cmd_push(args: argparse.Namespace) -> int:
    if not args.entry_file:
        log_err("push 需要 --entry-file")
        return 2
    try:
        payload = json.loads(Path(args.entry_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log_err(f"--entry-file 读取失败：{exc}")
        return 2
    entry = wrap_entry(payload, args.project, args.building, args.floor,
                       args.specialty, args.skill)
    client = find_bus_client()
    tmp = SCRIPT_DIR / f".{SKILL}_push_{os.getpid()}.json"
    try:
        tmp.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        if client is not None:
            r = subprocess.run([sys.executable, str(client), "push",
                                "--project", args.project, "--building", args.building,
                                "--floor", args.floor, "--skill", args.skill,
                                "--entry-file", str(tmp)], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"bus 客户端退出码 {r.returncode}：{r.stderr.strip()[:200]}")
            print(f"[{SKILL} statesync] 已推送 bus：{client}")
            try:
                print(r.stdout.strip())
            except Exception:
                pass
            return 0
        result = push_fallback(args.project, args.building, args.floor, entry, args.skill)
        print(f"[{SKILL} statesync] bus 未安装，降级直写 {DEFAULT_STATE_FILE}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        log_err(f"推送异常，降级直写本机状态文件：{exc}")
        try:
            result = push_fallback(args.project, args.building, args.floor, entry, args.skill)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc2:  # noqa: BLE001
            log_err(f"降级也失败：{exc2}")
            return 2
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def cmd_pull(args: argparse.Namespace) -> int:
    client = find_bus_client()
    if client is None:
        result = pull_fallback(args.project, args.building, args.floor)
    else:
        cmd = [sys.executable, str(client), "pull", "--project", args.project,
               "--building", args.building, "--floor", args.floor]
        if args.entry_id:
            cmd += ["--entry-id", args.entry_id]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(json.dumps({"hit": False, "reason": f"bus pull 失败 rc={r.returncode}",
                              "stderr": r.stderr[-300:]}, ensure_ascii=False, indent=2))
            return 0
        try:
            result = json.loads(r.stdout)
        except json.JSONDecodeError:
            print(json.dumps({"hit": False, "reason": "bus pull 输出无法解析"},
                             ensure_ascii=False, indent=2))
            return 0
    entry = result.get("entry")
    if not result.get("hit") or entry is None:
        print(json.dumps({"hit": False, "reason": result.get("reason", "无共享状态（降级：本机正常解析）"),
                          "project_key": result.get("project_key", "")}, ensure_ascii=False, indent=2))
        return 0
    schema = entry.get("schema")
    if schema != "cad-contract/v1":
        print(json.dumps({"hit": True, "usable": False, "reason": f"schema={schema!r} 不是 cad-contract/v1"},
                         ensure_ascii=False, indent=2))
        return 0
    mm = match_sections(entry, args.target_sections)
    usable = mm["usable"]
    review_flagged = list(mm["review_flagged"])
    core_matched, core_missing = [], []
    if args.require_all and mm["missing"]:
        usable = False
    if args.require_core:
        core_ok, core_matched, core_missing, review_flagged = apply_core_rule(entry, mm, args.core_sections)
        if not core_ok:
            usable = False
    core_fields = {}
    if args.require_core:
        core_fields = {"core_sections": args.core_sections,
                       "core_matched": core_matched,
                       "core_missing_core": core_missing}
    if not usable:
        reason = "缺必选核心 section" if core_missing else "目标 section 字段未命中"
        print(json.dumps({"hit": True, "usable": False,
                          "reason": reason,
                          "target_sections": args.target_sections,
                          "matched": mm["matched"], "missing": mm["missing"],
                          "empty": mm["empty"],
                          "review_flagged": review_flagged,
                          "candidate_only": True, **core_fields}, ensure_ascii=False, indent=2))
        return 0
    if args.out:
        Path(args.out).write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.out_dir:
        od = Path(args.out_dir)
        od.mkdir(parents=True, exist_ok=True)
        (od / "cad-contract.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        (od / "bus-pull-status.json").write_text(json.dumps({
            "hit": True, "usable": True, "schema": schema,
            "matched": mm["matched"], "missing": mm["missing"],
            "review_flagged": review_flagged, "candidate_only": True, **core_fields,
            "project_key": entry.get("project_key", {})}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"hit": True, "usable": True, "schema": schema,
                      "matched": mm["matched"], "missing": mm["missing"],
                      "empty": mm["empty"], "review_flagged": review_flagged,
                      "candidate_only": True, **core_fields,
                      "project_key": entry.get("project_key", {})},
                     ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"{SKILL} 与 lis-skill-bus 可选接线")
    ap.add_argument("command", choices=["push", "pull"])
    ap.add_argument("--project", required=True, help="项目标识")
    ap.add_argument("--building", default="", help="楼栋（可选）")
    ap.add_argument("--floor", default="", help="楼层（可选）")
    ap.add_argument("--specialty", default=DEFAULT_SPECIALTY, help=f"专业（默认 {DEFAULT_SPECIALTY}）")
    ap.add_argument("--skill", default=SKILL, help="producer.skill 名称")
    ap.add_argument("--entry-file", default="", help="push 用的本技能输出 JSON")
    ap.add_argument("--target-sections", default=",".join(DEFAULT_SECTIONS),
                    help="命中判定的 cad contract section 字段（逗号分隔）")
    ap.add_argument("--out", default="", help="pull 命中时写入的从契约文件")
    ap.add_argument("--out-dir", default="", help="pull 命中时写入 cad-contract.json + bus-pull-status.json 的目录")
    ap.add_argument("--entry-id", default="", help="pull 指定 entry_id（默认最近一条）")
    ap.add_argument("--require-all", action="store_true", help="所有 target sections 都命中才算 usable")
    ap.add_argument("--require-core", action="store_true",
                    help="必选核心 section 至少一命中且非空才算 usable（默认关闭，保持宽松）")
    ap.add_argument("--core-sections", default=",".join(DEFAULT_CORE_SECTIONS),
                    help="必选核心 section（逗号分隔，默认：" + ",".join(DEFAULT_CORE_SECTIONS) + "）")
    args = ap.parse_args(argv)
    args.target_sections = [s.strip() for s in (args.target_sections or "").split(",") if s.strip()]
    args.core_sections = [s.strip() for s in (args.core_sections or "").split(",") if s.strip()]
    if args.command == "push":
        return cmd_push(args)
    return cmd_pull(args)


if __name__ == "__main__":
    raise SystemExit(main())
