# 财税合规 · 上下文交接单 v13（当前唯一基线）

> 生成：2026-11-10 ｜ **下个会话只读本文件即可继续**。v9–v12 均为历史快照，保留不覆盖。
> 本轮为**工程增强**（2026-11-10 优化报告）：数据层 v14.0 一字未改，只动启动器/日志/前端/文档。

---

## 0. 一句话状态

`E:\workbuddy-data\finance-tax-compliance\`：知识库 **v14.0 · 472 条 / 56 文件 / A 317 · B1 4 · B2 151**，`business_case` 30/30 达标、`article_text` 40 条、引用零悬空。后端 Python 3.12 纯标准库（8777），前端 5 个 tab。**188 题评测 0 未达标且 v5 指标与基线逐项一致**，冒烟 19/19、e2e **83/83**、trust 24/24、检索单测 37/37、一致性 21/21。服务以**独立进程**运行，不再随会话后台任务回收。

## 1. 实测基线

| 项 | 值 |
|---|---|
| `kb.json` | v14.0 / 472 条 / 56 文件 / `verified_at=2026-11-09`（数据层未变，核验日不刷新） |
| tier / status | A 317 / B1 4 / B2 151；414 现行 / 50 汇编动态 / 6 草案 / 2 废止 |
| entry_type | regulation 345 / digest 31 / table_row 4 / concept 30 / relation 8 / scenario 14 / verification 10 / **business_case 30（全 A）** |
| `pending_field` | 全库 **7**（属地/到期隔离项，已逐条核实应保留）；business_case **0** |
| SQLite | regulation 472、fts 472、article_text **40**、citation_verification 15、alias 89、rule_reference 329、golden_case 79；运行时留痕 query_log / eval_run / eval_result / external_lookup_log（重建后需导回） |
| corpus | `knowledge-base/corpus/` 3 份逐字语料 + manifest（SHA256 回写）；`app/corpus-articles.json` 38 条唯一逐字条文 |
| 评测 | 188 题（自动 109 + 手工 79）：Recall@5 1.0 / MRR 0.6836 / 引用 0.6451 / 弃答·角色·禁用 1.0 / 规则 0.9468 / 要点 0.9714；基线 `reports/eval-report-v12-baseline-2026-11-09.json` |
| 前端 | 5 tab（chat / kb / incentives / about / **business**，快捷键 1–5）；业务事项视图支持 6 类筛选、11 字段详情、《法规名》跳转法规库、CSV 导出（17 列 / BOM） |
| 启动 | 根目录 `start-qa.bat` **v2**：`/api/health` 真实探测 + 轮询就绪 20s + 失败提示 + 单实例保护 + `TAXQA_NO_BROWSER=1` 无声自检；服务为独立进程；日志 `app/logs/server.log`（>1MB 轮转，已 gitignore） |
| 外部核验 | `config.json` 默认 `false`；本机 `app/config.local.json`（不入库）覆盖为 `true`。仓库默认关闭、本机启用 |
| 回滚 | `backups/baseline-v14-2026-11-10.zip`（含 README/.gitignore/start-qa.bat/v13 交接单） |
| Git | `git@github.com:jianhaot264-cmd/finance-tax-compliance.git`（SSH，Public），CI 多次绿灯 |

## 2. 本轮交付（2026-11-10）

1. **P0 健壮性**：v1 启动器备份为 `backups/start-qa-v1-2026-11-10.bat`；v2 改为健康检查驱动；`server.py` 加 `_Tee` 日志落盘与端口占用友好报错（退出码 2）；实测二次调用走 `ready` 分支、全程 1 个进程。
2. **P1 前端**：`business.js` 新增 `lawLinkify/csvCell/flashBtn/exportCsv/jumpToKb`，`index.html` 加 `#bc-export`，`polish.css` 加样式，e2e +5 断言（78 → **83**）。内容级验证：全量 CSV 31×17、筛选后 6 行、依据跳转回填 `企业会计准则第14号`。
3. **P2 巡检**：`expiry_scan.py` 基准日 2026-11-10 命中 130 条 / **90 天内 19 条**，机制已内建，7 条隔离项保留，历史报告数字不篡改。
4. **P3 文档**：15 处精确替换，重点修复根 README 重建链缺 `import_corpus.py`、app README 双续作入口、启动器说明过时、e2e 口径 73→83；`backup_baseline.py` ROOT_FILES 补根文件。

详见 `reports/optimization-report-2026-11-10.md`。

## 3. 架构契约（改知识库前必读）

1. **重建链 8 步**：`build_kb.py → enrich_kb.py → build_concepts.py → import_corpus.py → build_v5.py → audit_kb.py → build_coverage_matrix.py → eval_kb.py`。**`import_corpus.py` 必须在 `build_v5.py` 之前**，否则 L0 逐字条文不入库。`enrich_kb.py` 会 `os.remove(DB)`，重建后从备份导回 `query_log` / `eval_run` / `eval_result` / `external_lookup_log`；alias 由 SYNONYMS + `build_concepts.py` 自动重建为 89 条，无需导回。
2. **条目格式**：`## NN.x 标题` + `| 字段 | 内容 |` 两列表；`id=前缀-节号`；`status` 从 `时效性/生效状态/状态` 提取；`tier` 由 `enrich_kb.py` 实证重算。51–56 走 `business_case` 11 字段专用模板。
3. **同步 6+2 处**：`build_kb.py`（FILES + A 层集合 + 版本）→ `00-index.md` → `static/index.html` → `e2e-test.py` → 根 `README.md` → `app/README.md` → `server.py`（refs / 端点）→ `PENDING-VERIFICATION.md` / `change_log`。**改计数后逐处 grep 残留**。
4. **两条不变量**：① 业务事项层不得回到主检索（会改变 BM25 IDF，实测让 Recall@5 1.0→0.9944）；② 不新增 RULES 规则来暴露新条目（会改变 188 题自动题口径）。新条目走 `/api/business-cases` 独立通道。
5. **L0 原文层**：新增逐字条文写 `corpus/*.md` + 更新 `manifest.json`（双源 ≥2、时效四态、条数），跑 `import_corpus.py` 校验通过后才写入 `article_text`；**不要**直接编辑 `kb.json` / DB / `corpus-articles.json`。
6. **外部核验**：本机覆盖机制见 `reports/external-lookup-implementation-2026-11-09.md` §9；策略规格见 `reports/adaptive-retrieval-reply-policy-2026-11-09.md`。默认关闭，离线行为不变。
7. **服务启动**：推荐根目录 `start-qa.bat`（独立进程）；避免用会话后台任务启动（会被回收）。改 `server.py` 后需重启：先按 `Get-CimInstance Win32_Process` 精确过滤 `Name -eq 'python.exe' -and CommandLine -like '*server.py*'` 停旧进程，再用启动器拉起。

## 4. 剩余不确定性（不许猜）

1. 边界提示中涉及具体条款清单（广宣费三类行业、CAS11/CAS36 文号、权益性交易具体规定）仍标「以官方原文为准」，未臆造文号。
2. 南沙 15% 2027 延续仍是 P-24 隔离项；另有 P-06b / P-10b / P-23。
3. L0 目前与 23 文件内容重叠，按增量接入（识别出历史 37 条中 2 条同法同条号重复）；待 23 文件退役后 corpus 才是唯一逐字事实源。更多法规原文待按 `SOURCES-CHANNELS.md` 八步 SOP 分批回库。
4. 逐字语料用于结论前仍须复核施行日与现行性；不承诺 100% 准确。
5. 外部检索目前只接入 `build_llm_context`（`/api/llm-context` 与云端 LLM 链路），`/api/ask` 本地链路不变；抓的是官方栏目页，属**线索级核验**，非逐条法规全文比对。

## 5. 下一步建议（有序，勿一次吞下）

1. 扩 L0 原文层：按税种/准则分批导入 18 税种法律与实施条例全文，每条挂双源链接与 SHA256。**属专业内容产出，若启动须按专家团铁律建团队走 SOP**。
2. 把 `/api/business-cases` 的 11 字段接入 `/api/ask` 深度解读模式（当前仅独立视图）——会改本地答案文本，须先备份 188 题基线，退化即回滚。
3. 闭环剩余边界：广宣费三类行业清单、CAS11/CAS36 文号、权益性交易规定，按八步 SOP 逐条联网核验。

## 6. 关键路径与坑位速查

| 项 | 值 |
|---|---|
| Python | `C:/Users/aa152/AppData/Local/Programs/Python/Python312/python.exe`（`python` 缺包、`py` 已坏）；脚本一律绝对路径 |
| 服务重启 | 只按命令行文本过滤会误杀 PowerShell 自身，务必加 `Name -eq 'python.exe'`；启动用 `start-qa.bat` 而非会话后台任务 |
| 评测 | 服务启动后预热 3 发再跑 `eval_kb.py`；188 题约 7 分钟；基线 `reports/eval-report-v12-baseline-2026-11-09.json` |
| 规则字段 | 每条 RULES 必带 `role/risk/conclusion/basis/tips/refs/q/must`，缺 `role` 全服 KeyError |
| 批量替换 | 多处分散替换用一次性脚本逐处打印命中数（命中 0 立即中止）；**命令行 `python -c` 里不要放反引号或 Windows 反斜杠**，会被 shell 解释 |
| .bat 写入 | 用 Python `newline='\r\n'` + UTF-8 写，配 `chcp 65001`；不要加 BOM |
| 文件操作 | Write 只新建不覆盖；改已交付物先备份、起新版本留旧；删除前先出清单；AI 产出归 `E:\workbuddy-data\`，小写英文 + 连字符 + `yyyy-mm-dd` |
| 质量红线 | 文号/日期/比例/条号进文档前必须联网核验，不确定标「以官方原文为准」；历史报告口径不篡改；不承诺 100% 准确，只报验证结果 + 剩余不确定性 |

---

*本交接单由 WorkBuddy 汇编；v13 为当前唯一基线。*
