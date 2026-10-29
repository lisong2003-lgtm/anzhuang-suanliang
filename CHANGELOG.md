# Changelog

## 0.4.26

- **更新发布** 补 CHANGELOG 详细条目与 README.en 版本号；三端（Codex/WorkBuddy/发布仓库）同版本同内容再次校验通过。tujian-suanliang 的 manifest tests 仅保留真实存在的 `scripts/self_test.py`（完整 tests 见本机 shangwu-suanliang 商务版）。
- 算法、契约、权限、SKILL.md 正文与上一版无变化。

## 0.4.25

- **授权与保留** 新增「授权与保留」段落：作者 lis 声明本技能可商用/可再分发/可对外授权，商用前按双许可说明确认是否需联系作者申报。
- **脱敏（发布合规）** rules 中的公司内部来源字段由「公司知识库/…/规范图集」改为「公开规范与行业通用做法整理」，不再引用公司内部资料路径。
- **版本对齐** 本机 `~/.codex/skills`、`~/.workbuddy/skills` 与发布仓库同步同版本；算法、契约、兼容性与上一版一致，未改业务逻辑。

## 0.4.23

- **修复** `mep_plan.py` 的 `from openpyxl import ...` 由模块顶层改为出表函数内延迟导入，缺库时给出安装指引而非裸 traceback；未装 openpyxl 也能正常执行 `--help`。
- **新增** `scripts/runtime_env.sh`：统一解析 Python 解释器、识图底座目录，并把「本技能 scripts + 底座 scripts + 底座 vendor」注入 PYTHONPATH，无需全局 pip 安装。
- **修复** 底座探测仅覆盖 `$HOME/.codex`、`~/.claude`，现增加同级目录与 `~/.workbuddy/skills/*/cad-file-reader`；自动安装落点由硬编码 `$HOME/.codex` 改为与技能同级目录。
- **新增** `requirements.txt` 与 Windows 启动器 `mep_scan.cmd` / `mep_plan.cmd` / `anzhuang_statesync.cmd`（静态校验，未实机验证）。
- **文档** CLI 示例改为 `bash scripts/*.sh`；清理 `## 依赖` 空标题。
- **修复（发布兼容）** `mep_plan.py` 调用 `cad_validate.sh` 改为 `bash` 启动；`ensure_base.sh` / `setup.sh` 内部调用同样改为 `bash`，不依赖执行位。
- **修复（跨 Agent）** `mep_plan.py` 底座探测增加同级目录与 `~/.workbuddy/skills/*`，保留 `~/.claude`、`$HOME/.codex` 回退。

## 0.4.22 (2026-10-23)
- 修复 SkillHub 版 Windows 无 `.cmd` 时的接线说明：改为 `python scripts/*_statesync.py` 等价调用（bus 安装用 `python install_py.py --apply`）；GitHub 完整包保留 `.cmd`。平台发布调整，算法/契约/口径不变。


## 0.4.21 (2026-10-22)
- lis-skill-bus 可选联动（试点）：scripts/anzhuang_statesync.py push/pull 对接 cad-contract/v1（route_segments/circuits/systems/equipment 等），新 Windows anzhuang_statesync.cmd（未实机跑通，仅静态校验）；bus 未装自动降级。算法/口径不变。

## 0.4.20 (2026-10-21)
- 三平台对齐（cross-platform + i18n overseas）：README.en.md、`--lang en|zh` 主入口、i18n.py、CFI 三平台 workflow 全绿。
- 不改变业务算法/中文模板；平台专用调整只改发布副本。

# 更新记录
## v0.4.19 — 2026-10-19（三平台发布对齐）

- 发布对齐：以本机为规范源同步三平台；含 qto-project/v1 联动契约与 zero-config 底座默认仓库。
## P1 联动（2026-10-19，文档说明）

- 新增与 `cad-file-reader` 的目录级联动说明：识别放 `<项目目录>/识别/<slug>/`，量算输出写 `<项目目录>/算量/<slug>/`，可用底座 `scripts/qto_p1_link.py` 登记；不改算法与口径。

## 0.4.13 — 2026-10-18（安装/电气替代版回归入池）

- 补充同项目替换版电气系统图回归清单 `anzhuang-suanliang-ts-elec-sys.json`（kind=electrical），与本轮 cad-file-reader 替代版共用同源 CAD 扫描，正式电气候选复核 1/1 通过：systems=1165/equipment=2430/circuits=1943，contract_valid=true。
- 依赖底座升至 cad-file-reader 0.28.14（含 `--dwg-dxf-fallback` 自动回退支持）。

## 0.4.12 — 2026-10-18（第二期真图回归：45 例 45/45 全通过）

- 45 例按 5 张一批串行跑完，45/45 `contract_valid=true`，覆盖给排水/暖通/电气三类。
- 自检 `run_preflight.sh` self_test OK + 发布合规扫描 problems=0。

## 0.4.11 — 2026-10-16（单位自动推断 + 图层别名扩展 + 输入质量核对）
- `scripts/mep_scan.py` 新增 `infer_unit_from_doc()`：INSUNITS=0 时按前 5000 条 LINE/LWPOLYLINE 长度中位数保守推断（0.1~100→m 标 `auto_inferred`；≥500→mm；灰区→`unknown/review`），不再静默按毫米误算；`drawing_unit_info()` 增加 `unit_inference` 字段与复核说明。
- 图层别名扩展：`ELECTRIC_ROUTE_RE`/`PIPE_ROUTE_RE` 及 `water_system`/`water_zone` 增加市政/室外常见图层别名（`PIPE-*`/`WIRE-*`/`管道-*` 等）。
- Excel 输出新增 `输入质量核对` sheet，汇总单位推断、块内几何复核提示与待核对项。
- 单测 `self_test.py` 增加单位推断断言（median=22.0→auto_inferred/m）。
- 真图验证：范村室外管网总图（6800 段、文本 4641、单位 median 5.11→auto_inferred/m、`PIPE-污水` 累计 10.4km 级）、范村室外强电总图（620 段、文本 1812），已出 xlsx。
- 自测：`run_preflight.sh` self_test OK，发布合规扫描 problems=0。

## 0.4.10 — 2026-10-12（真图回归纳入发布预检）
- 新增 `scripts/run_preflight.sh`：全量自测 → 发布合规扫描 → 真图回归（复用 cad 底座，--manifest 强制），发布前统一入口。
- `ensure_base.sh` 保留 SHA-256 完整性校验；默认底座版本 cad-file-reader 0.28.5。

## 0.4.6 — 2026-10-12（底座自动安装加固）

- `ensure_base.sh` 增加 cad-file-reader 完整包 SHA-256 校验（从同 Release 下载 SHA256SUMS），校验失败拒绝安装与执行。
- 自动安装底座前校验包内 manifest 版本；默认底座版本升至 0.28.1。
- 平台安全扫描合规：自动下载底座改为带完整性校验、版本固定。


## 0.4.0 — 2026-10-05

对接 cad-file-reader 0.25.0 底座增强：旋转标注聚合、图例匹配、契约置信度/跨专业引用字段；版本门槛升至 `cad-file-reader >= 0.25.0`。

## 0.3.0 — 2026-10-05

对接 cad-file-reader 0.19/0.20 底座的 MEP 拓扑关联候选与交接校验。

- `mep_plan.py` 新增 `--mep-geometry`：可导入 cad-mep-geometry/v2 的 `mep_relations`（设备—管段、立管—管段、端点连接、系统冲突），进「MEP关联候选核对」工作表；候选固定 `final_quantity=false`，不参与本技能算量。
- `--cad-measurement` 导入前用 cad-file-reader `cad_validate.sh` 校验交接 JSON；校验失败只提示，不阻断。
- 自检扩展：覆盖 `mep_relations` 解析与空输入。

## 0.2.0 — 2026-09-20

- 对接 `cad-file-reader >= 0.18.0`，扫描结果记录底座版本和测量候选兼容状态。
- `mep_plan.py --cad-measurement` 支持导入“CAD测量候选核对”工作表；候选固定 `final_quantity=false`，不参与算量。
- 补充安装识图与算量边界说明，不输出金额、结算量或竣工计量。

## 0.1.0

- 首次发布安装算量技能。
- 支持 DWG 扫描索引与概算清单底稿、物资计划草稿双口径输出。
- 固化桥架 50m 异常单段阈值和剔除清单。
- 固化电线 `(路由长 + 两端预留) × 芯数` 展开。
- 增加规范约束、双口径映射、置信度分级、总量守恒和核对清单。
- 将 DWG 依赖重构为 `cad-file-reader` 动态发现，支持 `CAD_SKILL_DIR`。
