# 路由索引

- `scripts/mep_scan.py`：DWG → 扫描 JSON（管线分段、设备、文本、块、楼层锚点）；依赖 `cad-file-reader`。
- `scripts/mep_plan.py`：扫描 JSON → 概算清单底稿 + 物资计划草稿 xlsx；只读索引，不读 DWG。
- `scripts/self_test.py`：核心解析、匹配、展开和输出逻辑自检。
- `--cad-measurement`：把 `cad-file-reader` 测量候选导入“CAD测量候选核对”工作表，仅作识图复核，不参与算量。
- `references/loss_rules.json`：损耗、预留、匹配半径、层高、立管、桥架异常阈值配置。
- `references/standard_rules.json`：GB 50856 等规范口径、覆盖状态和转化边界。
- `references/dual_caliber_rules.json`：概算清单项、项目特征、物资材料行和依据映射。
- 干线估算：`--trunk-scan` 输入干线平面/母线层；无规格标注时列路由量，不硬分配。
- 依赖查找：优先 `CAD_SKILL_DIR`，再找同级/常见技能目录中的 `cad-file-reader`。
