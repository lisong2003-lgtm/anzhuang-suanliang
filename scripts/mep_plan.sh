#!/usr/bin/env bash
# mep_plan 跨平台 CLI 入口（macOS / Linux；Windows 用 scripts/mep_plan.cmd 或 python scripts/mep_plan.py）。
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/mep_plan.py" "$@"
