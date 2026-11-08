# 项目清理审计（已执行）

> 扫描时间：2026-11-08 00:55 ｜ 执行时间：2026-11-08 09:10 ｜ 目录：`E:\workbuddy-data\finance-tax-compliance\`
> 状态：**已执行**。26 个文件（B 类 18 + C 类 8）已移到回收站，未直接 rm。备份清单：`backups/cleanup-2026-11-08-manifest.json`。
> 结论：目录本身已较干净（无 `__pycache__`、无 `.tmp/.log/.bak`、无 `kb-pre-enrich` 残留）；可清理项集中在**旧基线、可重生成的截图、被取代的历史报告/评测备份**。

## 执行结果

| 项 | 数量 | 大小 | 去向 |
|---|---:|---:|---|
| QA 截图（可重生成） | 11 | 1.43 MB | `wb-trash/cleanup-2026-11-08/app/qa-screenshots/` |
| v6 旧截图 | 1 | 98 KB | `wb-trash/cleanup-2026-11-08/reports/` |
| v8/v9 评测备份 | 2 | 43 KB | `wb-trash/cleanup-2026-11-08/app/` |
| v6 报告 md/html | 2 | 60 KB | `wb-trash/cleanup-2026-11-08/reports/` |
| v7/v8 交接单 | 2 | 32 KB | `wb-trash/cleanup-2026-11-08/` |
| 旧基线 v6–v9（zip+manifest） | 8 | 11.8 MB | `wb-trash/cleanup-2026-11-08/backups/` |
| **合计** | **26** | **≈13.4 MB** | 回收站（可恢复） |

**清理后体积**：app 8.9 MB（-2.1）、backups 7.2 MB（-11.8）、reports 1.6 MB（-0.1）、knowledge-base 1.0 MB（不变）→ 项目 **31 MB → 18 MB**。

**保留**：v10/v11 两代基线、全部 48 个知识库文件、当前报告/数据导出、`apply_corrections.py`、`eval-report-v5.json`、`regulations-master-*.csv`、`sme-tax-compliance-incentives-*`、`coverage-matrix-*`、`legislative-rewrite-plan-*`、`expiry-radar.*`、`policy-radar/*`、`context-handoff-v9`。

**验证**：`/api/health` = v11.0 / 429 条；冒烟 **19/19**；基线已重建（102 文件 / 3.76 MB）。

---

## 1. 总体积

| 目录 | 体积 | 文件数 | 判断 |
|---|---:|---:|---|
| `app/` | 11 MB | 44 | 核心程序 + 数据库 + 前端，**保留** |
| `backups/` | 19 MB | 12 | 6 代基线，**旧代可删** |
| `knowledge-base/` | 1.0 MB | 51 | 48 主题 + 索引/信源/隔离清单，**全部保留** |
| `reports/` | 1.7 MB | 22 | 当前报告/数据 + 历史报告，**部分可删** |
| 根目录交接单 | 40 KB | 3 | v7/v8/v9，**保留 v9，v7/v8 可删** |

---

## 2. A 类：必须保留（核心可用文件）

| 类别 | 文件 | 理由 |
|---|---|---|
| 后端 | `app/server.py`、`retrieval.py`、`orchestrator.py`、`deep_dive.py` | 服务运行必需 |
| 数据链 | `build_kb.py`、`enrich_kb.py`、`build_concepts.py`、`build_v5.py`、`audit_kb.py`、`eval_kb.py`、`expiry_scan.py`、`build_coverage_matrix.py`、`backup_baseline.py` | 重建/审计/评测/雷达/矩阵/备份，全部可复用 |
| 数据 | `app/kb.json`、`concepts.json`、`finance-tax-compliance.db`、`golden_extra.json` | 运行时数据与评测集 |
| 前端 | `app/static/*`（8 个） | 页面必需 |
| 启动/配置 | `app/config.json`、`app/start_server.bat`、`app/README.md` | 启动与文档 |
| 留痕脚本 | `app/apply_corrections.py` | 一次性回写脚本，已执行，留作 v4 订正留痕（8 KB，建议保留） |
| 知识库 | `knowledge-base/` 51 个 md | 单一事实源，**一个都不能删** |
| 当前报告 | `upgrade-report-v11-2026-11-08.md/.html`、`eval-report-v5.json`、`audit-stats.json`、`regulations-master-2026-11-07.csv`、`concept-map-2026-11-07.csv`、`coverage-matrix-2026-11-08.csv/.json`、`expiry-radar.json/.md`、`policy-radar/*`、`legislative-rewrite-plan-*`、`sme-tax-compliance-incentives-*`、`build_report_html.py` | 当前版本报告、数据导出、月度雷达、交付物 |
| 最新基线 | `backups/baseline-v11-2026-11-08.zip` + manifest、`baseline-v10-2026-11-07.zip` + manifest | 唯一回滚点；保留最近两代 |
| 最新交接单 | `context-handoff-v9-2026-11-08.md` | 下轮续作入口 |

---

## 3. B 类：建议删除（可再生成 / 已被取代，低风险）

| # | 文件 | 大小 | 理由 | 可恢复性 |
|---|---|---:|---|---|
| 1 | `app/qa-screenshots/*.png`（11 张） | 1.43 MB | e2e 每次运行自动重生成；含旧版 `07-about-models.png`、`08-model-price-table.png`（11-05）、`10-concept-head.png`（截图裁切残留） | 跑一次 `e2e-test.py` 即恢复 |
| 2 | `reports/qa-upgrade-v6.png` | 98 KB | v6 时期旧截图，已被 v11 报告取代 | 无重生成价值 |
| 3 | `app/golden-extra-v8-backup-2026-11-07.json` | 16 KB | P0/P1 前评测集，已被 v10/v11 取代 | 历史留痕，价值低 |
| 4 | `app/golden-extra-v9-backup-2026-11-07.json` | 26 KB | v10 前评测集，已被 v10 备份取代 | 同上 |
| 5 | `reports/upgrade-report-v6-2026-11-07.md/.html` | 60 KB | v6 升级报告，已被 v10/v11 报告取代 | 历史文档 |
| 6 | `context-handoff-v7-2026-11-07.md` | 20 KB | 已被 v8/v9 取代 | 历史文档 |
| 7 | `context-handoff-v8-2026-11-07.md` | 12 KB | 已被 v9 取代 | 历史文档 |
|  | **小计** | **≈1.66 MB** | | |

> 说明：第 3–7 项体量很小，删不删对空间影响不大；若你重视「版本沿革」，可只删 1–2 项。

---

## 4. C 类：需你确认（旧基线，占空间最大）

| # | 文件 | 大小 | 说明 |
|---|---|---:|---|
| 1 | `baseline-v6-2026-11-07.zip` + manifest | 2.38 MB | v6（260 条）基线，已被 v11 完全覆盖 |
| 2 | `baseline-v7-2026-11-07.zip` + manifest | 2.96 MB | v7（含 P0 补库）基线 |
| 3 | `baseline-v8-2026-11-07.zip` + manifest | 3.21 MB | v8（P1 补库）基线 |
| 4 | `baseline-v9-2026-11-07.zip` + manifest | 3.24 MB | v9（P2 机制）基线，363 条 |
|  | **小计** | **≈11.79 MB** | 删除后仍可用 v10/v11 回滚；v6–v9 的历史内容已被 v11 包含 |

**建议**：保留 `v10` + `v11` 两代，删除 `v6–v9`。理由：v11 的 `knowledge-base/` 已包含 48 个文件全量内容，v6–v9 的差异只是历史版本；保留最近两代足以应对「上一版回滚」和「当前版回滚」。

**风险**：删除后无法回到 v6–v9 的**精确文件状态**（例如 v9 时期的 `server.py` 旧规则）。若你需要复现历史评测，建议保留 v9。

---

## 5. 不建议删除

| 项 | 理由 |
|---|---|
| `apply_corrections.py` | 8 KB，v4 订正留痕，删了会失去「24 条源条目如何回写」的可复现证据 |
| `expiry-radar.json/.md` 与 `policy-radar/*` | 前者是机器可读雷达，后者是月度报告；每月自动化会读写 |
| `eval-report-v5.json`（350 KB） | 文件名沿用旧版，但内容是**当前 181 题**评测结果，删了无法对比基线 |
| `regulations-master-2026-11-07.csv`（728 KB） | 生产主数据表，企业系统导入用 |
| `sme-tax-compliance-incentives-*` | 已交付的中小企业专题手册，不是过程文件 |
| `knowledge-base/PENDING-VERIFICATION.md` | 隔离清单，删了审计会失去阻断项来源 |

---

## 6. 执行方式（确认后）

1. **先备份**：删除前把待删清单写入 `backups/cleanup-2026-11-08-manifest.json`（路径+大小+SHA256 前 16 位）。
2. **移到回收站**：`/c/Users/aa152/AppData/Local/Temp/wb-trash/cleanup-2026-11-08/`，**不直接 rm**；确认无误后由你决定是否清空。
3. **分批**：每批 ≤10 个文件，逐批核对数量。
4. **不动**：`knowledge-base/`、`app/*.py`、`app/static/`、`kb.json`、`db`、`golden_extra.json`、最新两代基线。
5. **验收**：清理后跑 `/api/health` + `--smoke`，确认服务与回归不受影响。

---

## 7. 一句话建议

删 **B 类 7 项 + C 类旧基线 v6–v9**，合计约 **13.4 MB**，项目从 31 MB 降到约 **18 MB**；保留 v10/v11 两代基线与全部 48 个知识库文件，功能与回滚能力不受影响。
