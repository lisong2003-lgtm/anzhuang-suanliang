@echo off
rem mep_plan 跨平台 CLI 入口（Windows；macOS/Linux 用 scripts/mep_plan.sh）。
setlocal
set "PY_SCRIPT=%~dp0mep_plan.py"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%PY_SCRIPT%" %*
  exit /b %errorlevel%
)
where python >nul 2>nul
if %errorlevel%==0 (
  python "%PY_SCRIPT%" %*
  exit /b %errorlevel%
)
echo [mep_plan] 未找到 Python 3（py/python）；请安装 Python 并加入 PATH 1>&2
exit /b 127
