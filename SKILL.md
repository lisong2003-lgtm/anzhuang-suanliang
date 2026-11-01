---
name: anzhuang-suanliang
slug: anzhuang-suanliang
displayName: 安装算量 · 概算底稿与物资计划双口径
version: 0.4.31
platforms: [macos, windows, linux]
author: lis
license: CC-BY-NC-SA-4.0
description: 从安装工程 DWG/扫描索引提取概算清单底稿与物资计划草稿：按回路规格分档管线，展开电线芯线与预留，估算电缆、桥架、给排水、喷淋、支吊架和设备数量。目标是概算出量、物资计划、图审查量和专业软件结果交叉核对；不替代翻样、下料、结算，也不输出金额。
i18n:
  en: README.en.md
  zh: README.md
locale: zh-CN
locales: [zh-CN, en-US]
---

# 安装算量（概算清单 + 物资计划双口径）

## 识图契约红线（硬规则，禁止绕行）
- 算量技能**不得单独识别 DWG/DXF/PDF**：识图必须由 `cad-file-reader` 完成一次，产出统一契约后各算量技能共享复用（同一张图只解析一次）。
- **禁止算量技能自行 `import ezdwg/read_cad`、自带或重新下载 cad-file-reader 来解图**；底座缺失时如实标 `unavailable`，不得降级成“自己解图”。
- 用户要算量 = 必须先走 `cad-file-reader → 契约 → 算量`；计算入口默认拒绝直接 DWG，开发/回归调试才能用显式 `CAD_ALLOW_DIRECT=1` 逃生。
- `lis-skill-bus` 是连接 cad-file-reader 契约与各算量技能的唯一定接线；算量结果必须带契约来源（图号/坐标证据）。
- **DWG 解码兜底只能在 cad-file-reader 内完成**：遇到 ezdwg/libredwg 读不了的 ACAD 新变体/损坏卷（实测例：sample-site结构 2#/3#），由 cad-file-reader 用独立 `ODAFileConverter` 在副本上转 DXF 复扫并回读校验；本技能**不得自行调用 CAD/看图 App/ODAFileConverter 解图**，只消费底座给出的契约 JSON。
- **内存双档**：常规识图默认 `CAD_MEM_LIMIT_MB=4096`（mem_guard 默认）；仅实测超 4GB 的真实大图且串行跑时临时覆盖 `CAD_MEM_LIMIT_MB=8192`，不全局改默认；mem_guard 只在识图子进程内自终止，不杀 WorkBuddy/Codex。


> **融合入口**：本技能可单独使用；若手上是一整套图纸、要跨专业出一张总表，用 `cad-suite` 一个入口即可跑完发现→识图→关系→聚合→跨专业对照→算量→出表，不必逐个调用。口径与红线在 cad-suite 里是同一份。

## 0.2.0 优化概况

- 对接 `cad-file-reader >= 0.25.0`，扫描结果记录底座版本和测量候选兼容状态。
- `mep_plan.py --cad-measurement` 可把长度/面积/体积识图候选导入“CAD测量候选核对”工作表；候选固定 `final_quantity=false`，不参与本技能算量。
- 保留安装专业双口径输出、回路规格匹配、水系统分区、立管识别、支架估算和核对清单；不输出金额、结算量或竣工计量。

两步出表：先扫描 DWG 建索引，再用索引生成 xlsx。

```bash
# 1. 识图与扫描两条路（识图契约红线）：识图只由 cad-file-reader 产出契约，同一张图只解析一次
#    a) 已有 cad-file-reader 契约（cad_scan/cad_mep_geometry 产物）时只消费契约，不再打开 DWG：
bash scripts/mep_scan.sh 平面_契约.json --contract --out 平面.json
bash scripts/mep_scan.sh 系统_契约.json --contract --out 系统.json
bash scripts/mep_scan.sh 说明_契约.json --contract --out 说明.json
bash scripts/mep_scan.sh 干线_契约.json --contract --out 干线.json
#    b) 直接传 DWG 默认被拒（exit 2，提示先走 cad-file-reader）；仅回归/调试可用 CAD_ALLOW_DIRECT=1 逃生

# 2. 生成双口径表；已有 .scan.json 时不要重新扫 DWG
bash scripts/mep_plan.sh \
  --scan 平面.json \
  --system 系统.json 说明.json \
  --trunk-scan 干线.json \
  --out-prefix 安装计划
```

输出包含：口径、规范约束、双口径映射、导管与桥架、电线电缆、干线电缆、设备、图层分档、配电箱回路、未匹配坐标簇、分层、水专业、水系统分区、连通性核对、立管识别、支架估算、置信度分级、总量守恒、材料表提取、材料归并、立管估算、核对清单。

## 图层与匹配口径（0.4.29）

- **图层先分档再出量**：`DIM-*`（标注）、`EQUIP-*`（设备符号）、图框/墙体/轴网/文字一律不计入任何量；每层归「电气回路 / 桥架 / 水专业 / 非管线路由 / 未归类」，见「图层分档」表。
- **电气优先于水**：`WIRE-消防` 是消防联动线路，只进电线电缆，不进水专业——早期两条判据互不排斥，同一批管长会进两张表、全楼量翻倍。
- **回路标注两种形态都认**：平面图有 `W1:规格` 就按回路号匹配；只标裸规格（`WDZ-BYJ-3*10-(CT)PVC32-FWC`）时按规格就近匹配，回路列记 `-`。
- **匹配距离按「点到线段」**：扫描端给每段线带两端坐标，一条 60m 直线标在端头的规格也够得到；标注够不到的线段再按「相邻传播」（同层 2.5m 内接力定规格，置信度记低）。
- **未出量要交代去向**：某层未出量超过 30% 时，「图层分档」直接给出主规格候选与占比，便于人工一次确认；「总量守恒」区分 通过 / 未出量 / 异常 三态，不再恒等通过。

## 市政管长汇总（0.4.30，吃识图包产物）

吃 cad-file-reader 市政识图包的 `*.municipal.json`（管道标注：系统/管径/原文 + 市政图层几何段）：

```bash
# 先识图：bash ../../cad-file-reader/scripts/cad_municipal_geometry.sh 市政详情.json --out-dir 市政识图
scripts/municipal_pipe_length.sh --municipal 市政识图/xxx.municipal.json --out-prefix 市政管长
```

长度三档证据：① 标注文本 `L=25000` / `长度4500`（置信高）② 桩号差 `K0+240.5~K0+412.3`（纵断面主口径，跨千米进位）③ 管道图层面线段合计（按该图层管道标注的系统多数派归属，管径记「未标注」）。系统已有显式长度时其图面线段整体跳过（防重复计数）。输出按系统 × 管径汇总，标 final_quantity=false（图面长度，不含井段扣减/弯曲增长，非施工下料长度）。

## 显式依赖与降级（0.9+）
## 强依赖底座说明（cad-file-reader 强依赖，不做弱化）

本技能采用**识图与算量分离**的固定架构，`cad-file-reader` 是**强依赖底座**，不是可选增强：

- **为什么必须强依赖**：DWG/DXF/DWT/PDF 的解析、图层/文字/块/图框/几何提取、识图候选和测量候选全部集中在底座完成，一次解图、全项目复用，保证证据坐标与契约一致。本技能只做本专业口径的量算、扣减、损耗、分账和台账，不重复解析图纸。
- **分工**：底座输出 `final_quantity=false` 的识图/测量候选；本技能输出本专业概算底稿/物资计划草稿（`final_quantity=true` 仅本专业口径）。
- **版本约束**：底座最低版本以各技能 `SKILL.md`「前置/依赖」写的 `>=x.y.z` 为准；缺底座或版本不够时明确报错，不静默用错误数据。
- **安装**：先装底座（`cad-file-reader` 的 `scripts/setup.sh`），再装本技能；运行时底座可在 `SKILL_NO_BASE=1` 下退化为只读已有扫描/候选/表格输入，但精度受限并必须在结果标注。
- **联动**：装有 lis-skill-bus 时，底座与各算量技能通过 `cad-contract/v1` 共享契约，同一张图只解一次；不装 bus 时各技能自动降级为各自 `state/`，功能不丢失。


- 底座 `cad-file-reader >= 0.28.1` 是本技能的**显式依赖**：运行首次会自动检测，缺失时自动下载安装底座并补齐 vendor（联网，下载包做 SHA-256 完整性与版本校验，校验失败拒绝安装）；已装则直接复用，不重复下载。
- 独立/离线场景可设 `SKILL_NO_BASE=1`：不再自动安装底座，仅使用已有扫描 JSON、测量候选或表格输入（精度受限并在结果中标注）。
- 可设 `CAD_AUTO_SETUP=0` 关闭底座内部的 vendor 自动下载；手动安装用 `scripts/setup.sh` 或 `scripts/ensure_base.sh`。

- 依赖 `cad-file-reader >= 0.25.0`；扫描结果会记录底座版本和测量候选兼容状态。
- 可用 `cad_measure.sh` 先生成长度/面积/体积识图候选，再通过 `mep_plan.py --cad-measurement` 导入“CAD测量候选核对”工作表；候选固定 `final_quantity=false`，不参与本技能算量。

- `cad-file-reader` 负责全部 DWG/DXF/PDF 识图并产出 MEP 契约；`mep_scan.sh --contract` 只消费契约 JSON，不再打开 DWG。找不到时设置 `CAD_SKILL_DIR=/path/to/cad-file-reader`。
- `mep_plan.py` 只读 `.scan.json`，不依赖 CAD 解析。
- Python ≥3.10；openpyxl 生成 xlsx。

## 口径与算法

- 管长＝WIRE/PIPE/CABLETRAY 图层 LINE/LWPOLYLINE 单线中心线水平投影（含弧段弧长），未含立管与竖向。
- 回路匹配＝线段中点就近回路标注（默认 30m 半径，`match_radius_mm` 可调），多规格同号回路取多数规格并计入歧义表。
- 配电箱回路＝优先识别“配电箱:回路”标注并按箱/回路/规格汇总；裸回路不硬归属。
- 未匹配坐标簇＝未匹配电气管段按 50m 网格汇总，输出前 50 簇供回图核对。
- 电线展开＝(匹配管长＋两端预留)×芯数；电缆展开＝匹配管长＋两端预留；预留＝每端 1.5m×回路数（`reserve_per_end_m`）。
- 桥架＝单段不超过 `tray_max_segment_mm`（默认 50m）才计入；超长段按异常剔除并单独列出。
- 订货量＝净量×(1+损耗)；损耗、预留和阈值见 `references/loss_rules.json`。
- 规范约束＝`references/standard_rules.json` 区分快算量、GB 50856 清单量、商务概算量和物资计划量；`references/dual_caliber_rules.json` 输出概算清单项与物资材料行映射。
- 水专业管径＝管段就近同系统 DN/De 标注；未标注管段按邻近已标注管段兜底推测，输出注明推测长度。
- 水系统分区＝按 PIPE 图层归并系统和高/中/低、室外等尾缀分区；分区表只拆分水平长度，不重复计总量。
- 连通性核对＝同图同系统/同管径端点吸附，输出开路端点、孤立段和疑似跨层/跨分区坐标簇；只回图确认，不改总长。
- 立管编号＝水专业标注层的 `JL/PL/TL/FL/WL/YL/HL/RL/HYL/SPL-编号`；同号跨图只计 1 根，折算长度按层高推定并标 [推测]。
- 置信度＝高（直接近距标注）、中（远距标注/歧义/邻近兜底）、低（相邻传播/未标注）；总量守恒表核对源总长与分档合计，区分 通过/未出量/异常。
- 支架＝按水专业图层/管径最大间距向上取整，桥架按水平吊架间距估算；仅供物资备料。
- 干线电缆＝系统图规格次数 + 干线平面/母线层就近规格匹配；无就近规格标注时按图层列“未分配量”，不硬分配规格。
- 立管＝配置里人工填根数×层高×(楼层数-1)，输出标 [推测]。
- 设备数量＝ATTRIB 属性实例数（已滤门窗编号/单字母标注噪声）；水专业器具＝块引用计数，块名 `$` 前缀需对照图例命名。

## 依据

规范只存口径与边界，不复制全文。参考 GB 50856、GB 50500、GB 50015、GB 50084、GB 50116、GB 51309、GB 51348、GB 50974、GB 50261、GB 50303、GB 55024 和 GB 50166；详见 `README.md` 与 `references/standard_rules.json`。

## 边界（必须随结果告知）

1. 输出是概算底稿和物资计划草稿；不是定额级清单、结算量或竣工计量。
2. 不输出金额、单价、措施费、规费和税金。
3. 未含竖向实测长度、管件、套管；立管识别只按图面编号折算；支架仅按间距估算。
4. 回路标注覆盖不到的管长归「图层分档-未出量」，并给出主规格候选；不擅自按主规格回填数量，需人工确认后分档。
5. 水专业邻近管段兜底只是计划口径补充，抽查主干变径点后再提报。
6. 同一设备出现在多张图时按各图分别计数后合计，跨图重复需人工剔除。
7. 天正自定义实体的投影线可能与实际管线有出入，抽查 3~5 处回图核对后再提报。
8. 设备/材料表跨图重复会标注“跨图重复”；乱码名称不得猜测。
9. `CAD测量候选核对` 中的值只作识图证据，`final_quantity=false`；不得直接当管长、材料量或结算量。

## 判定与升级路径

- 交付必须附“匹配率 + 歧义回路数 + 需人工核对项 + 规范约束覆盖状态”。
- 需要定额级清单、对量、结算或竣工计量：超出本技能边界，改用专业软件建模。

## lis-skill-bus 可选联动（试点，不强制）

- 状态过滤：项目名/楼栋/楼层一致时，本技能可与 `cad-file-reader` 及其它算量 skill 通过 lis-skill-bus 交换 `cad-contract/v1`；命中即复用，不再重复解图。
- 拉取（开工前，推荐）：`scripts/anzhuang_statesync.sh pull --project 项目 [--building 楼栋] [--floor 楼层] [--out 落盘.json]`
  —— 命中且契约含本专业 section 字段（`route_segments`、`circuits`、`systems`、`equipment`、`labels`、`measurements`）时返回 `hit=true usable=true`，可直接复用；未命中/缺字段/无 bus 一律返回 `hit=false`/`usable=false`，走本技能正常解析。
- 发布（算量落盘后，可选）：`scripts/anzhuang_statesync.sh push --entry-file <本技能输出.json> --project 项目 [--building 楼栋] [--floor 楼层] [--specialty 安装]`，自动包装成 `cad-contract/v1` 后入 bus。
- 对应接线脚本：`lis-skill-bus/integration/anzhuang_pull_contract.sh` / `anzhuang_publish_contract.sh`（薄壳，等价调用本技能 statesync）。
- 命中口径：`usable=true` 为本机状态里的「候选级命中」（`candidate_only=true`）；命中 section 内若有 `review_required`/P2/P3 项，statesync 只标 `review_flagged`，P0–P3 与复核项过滤仍在本技能算量核心按既有口径完成，不因 bus 命中而跳过滤。
- 命中开关（默认宽松）：默认仍为「至少一个 section 字段命中即 `usable=true`」的候选级命中；加 `--require-core` 后收紧为必选核心 section 至少一个命中且非空（安装=`circuits` 回路 / `route_segments` 桥架），缺核心时 `usable=false` 并把缺项写入 `review_flagged`。是否把默认改为收紧属业务口径，待用户/业务确认。
- bus 路径变更：仅需设置 `SKILLBUS_HOME` 指向新 bus 目录，本技能任何文件无需改动。
- 兼容/降级：客户端按如下优先级定位 `skillbus_client.py`，正式路径存在时不回退 dev 副本：
① `SKILLBUS_HOME`（bus 目录）或 `SKILLBUS_CLIENT`（直接指向 client 文件）显式指定
② `$HOME/.codex/mcp_servers/lis-skill-bus/skillbus_client.py`（正式安装落点）
③ `$HOME/.codex/skills/lis-skill-bus/skillbus_client.py` / `$HOME/.codex/skills/.skillbus/skillbus_client.py`
④ 常见本机开发副本（`tan/work` 等，最后才回退）。
命中 dev/临时副本时 stderr 会输出告警行「bus 命中来源：<路径>（临时副本/dev，非正式安装）」，正式路径输出「（正式安装）」；找不到 bus 时不报错，直接写 `$HOME/.codex/skills/.skillbus/state.json`（与 bus 同构，后续装 bus 可无缝读取）。 无 MCP/无 bus 不影响任何算量能力；本技能算法、口径、扣减、损耗、分账与台账逻辑不变。

- Windows 接线：GitHub 完整包 scripts/anzhuang_statesync.cmd push/pull（GitHub/ClawHub 包含 .cmd，SkillHub 轻量包剔除 .cmd、Windows 改用同目录 .py 入口；macOS/Linux 用 `bash scripts/anzhuang_statesync.sh` 等价调用）；等价 lis-skill-bus/integration/anzhuang_publish_contract.sh / anzhuang_pull_contract.sh。Windows 未实机跑通，仅静态校验通过（CRLF 行尾；无 /Users、/bin/sh、python3 硬编码；py 启动器 + %PYTHON%/%CODEX_PYTHON% 回退；默认路径用 %USERPROFILE%\.codex）。

## QTO 五专业联动（P1，可选）

可与 `cad-file-reader` 及其它算量 skill 联动（可选）：识别放 `<项目目录>/识别/<slug>/`，量算层输出写 `<项目目录>/算量/<slug>/`，用底座 `<底座>/scripts/qto_p1_link.py` 登记。此联动只在目录上登记输入/输出与缺口，不替代本技能既有算法、口径与复核。

## 环境与运行时（自动解析，无需手工配置）

- 所有 `scripts/*.sh` 入口都 `source scripts/runtime_env.sh`，由它统一解析三件事：
  1. **解释器**：`CAD_SKILL_PYTHON` / `CODEX_PYTHON` → Codex 运行时 → PATH 上的 `python3.12/3.11` → `python3`（要求 ≥3.10）；
  2. **识图底座**：`CAD_SKILL_DIR` → 同级 `../cad-file-reader` → `~/.workbuddy/skills/*/cad-file-reader` → `~/.claude` → `$HOME/.codex`；
  3. **依赖路径**：把「本技能 scripts + 底座 scripts + 底座 vendor」拼进 `PYTHONPATH`，`ezdxf / ezdwg / openpyxl` 等**无需全局 pip 安装**。
- 推荐用对应的 `bash scripts/<入口>.sh`；直接 `python3 <入口>.py` 只在全局已装齐依赖时可用。
- 依赖缺失时按 `requirements.txt` 安装：`python3 -m pip install -r requirements.txt`。

## 授权与保留

本技能以 **CC-BY-NC-SA-4.0** 授权给公众：可自由使用与改造，但**仅限非商业用途**（个人学习、研究与非营利使用）；改造后若公开发布，须以相同条款授权。

企业、机构或将本技能用于经营性项目（如承接工程造价、算量咨询业务）的商业使用，需另行取得作者书面授权。

作者（lis）作为著作权人，不受上述许可限制，明确保留以下权利：

1. 将本作品用于任何商业目的；
2. 改造、再发布、封装为收费商品或服务；
3. 向第三方授予商业使用授权。

完整许可文本见 `LICENSE.md`。
