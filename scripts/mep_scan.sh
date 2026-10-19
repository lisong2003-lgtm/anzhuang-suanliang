#!/usr/bin/env bash
set -euo pipefail
PY="${CAD_SKILL_PYTHON:-}"
if [[ -z "${PY}" ]]; then
  for c in \
    "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" \
    "/opt/homebrew/bin/python3.12" "/usr/local/bin/python3.12" \
    "/opt/homebrew/bin/python3.11" "/usr/local/bin/python3.11" \
    "$(command -v python3 || true)"; do
    if [[ -n "$c" && -x "$c" ]] && "$c" -c 'import sys; assert sys.version_info >= (3,10)' >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
if [[ -z "${PY}" || ! -x "${PY}" ]]; then
  echo "❌未找到 Python 3.10+；请设置 CAD_SKILL_PYTHON 指向运行时 Python" >&2
  exit 2
fi
exec "$PY" "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/mep_scan.py" "$@"
