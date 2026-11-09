# 财税合规 · 上下文交接单 v12（v14.0 当前基线）

> 生成：2026-11-09 ｜ **下个会话只读本文件即可继续**。v9 / v10 / v11 均为历史快照，保留不覆盖。
> 本轮完成 v10 与 v13 报告列出的三项剩余工作：业务事项前端入口、10 条边界提示闭环、L0 逐字原文层。

---

## 0. 一句话状态

`E:\workbuddy-data\finance-tax-compliance\`：知识库 **v14.0 · 472 条 / 56 文件 / A 317 · B1 4 · B2 151**；`business_case` **30/30 达标**、`article_text` **40 条**；前端 5 个导航项（含业务事项视图）。后端 Python 3.12 纯标准库（8777），前端原生三件套，云端 HY4。**188 题评测 0 未达标且 v5 指标与基线逐项一致**，冒烟 19/19、e2e **78/78**、trust 24/24、检索单测 37/37。

## 1. 实测基线

| 项 | 值 |
|---|---|
| `kb.json` | v14.0 / 472 条 / 56 文件 / `verified_at=2026-11-09` |
| tier / status | A 317 / B1 4 / B2 151；414 现行 / 50 汇编动态 / 6 草案 / 2 废止 |
| entry_type | regulation 345 / digest 31 / table_row 4 / concept 30 / relation 8 / scenario 14 / verification 10 / **business_case 30（全 A）** |
| `pending_field` | 全库 **7**（历史隔离项）；business_case **0** |
| SQLite | regulation 472、fts 472、article_text **40**、citation_verification 15、alias 89、rule_reference 329、golden_case 79、query_log / eval_run / eval_result / external_lookup_log（运行时留痕，重建后需导回） |
| corpus | `knowledge-base/corpus/` 3 份逐字语料 + manifest（SHA256 回写）；`app/corpus-articles.json` 38 条唯一逐字条文 |
| 评测 | 188 题（自动 109 + 手工 79）：Recall@5 1.0 / MRR 0.6836 / 引用 0.6451 / 弃答·角色·禁用 1.0 / 规则 0.9468 / 要点 0.9714 |
| 前端 | 5 个 tab（chat / kb / incentives / about / **business**，快捷键 1–5）；`GET /api/business-cases?q=` 列表模式返回 30 条含 11 字段 |
| 外部核验 | `config.json` 默认 `false`；本机 `app/config.local.json`（不入库）覆盖为 `true`。仓库默认关闭、本机启用 |
| Git | `git@github.com:jianhaot264-cmd/finance-tax-compliance.git`（SSH，Public），CI 已多次绿灯 |

## 2. 本轮交付

1. **业务事项前端入口**：`app/static/business.js` 独立模块 + `#view-business` 视图 + `polish.css` 样式；`retrieval.retrieve_business_cases()` 支持 q 为空的列表模式与 `_bc_item()` 完整字段；`server.py` 传 `topk=50`；`app.js` 加 `TAB_META.business`、快捷键 5 与 `/` 聚焦；e2e 新增 5 条断言（73 → **78**）。
2. **10 条边界提示闭环**：51–56 中 10 处「待核验」按官方原文与库内已双源核验依据逐条改写；6 个文件头统一引用 `reports/upgrade-report-v14-2026-11-09.md` 的核验记录表。关键核验：公司法 2023 修订第 210 条（10% / 50%，中国政府网 + 最高法）、2023 年第 12 号第二/五条（中国政府网 + 税务总局政策法规库）、财会〔2011〕17 号应付税款法（中国税务报解读 + 库内 38 文件）。**不臆造文号**；南沙 2027 延续保留为明确边界事实（P-24）。
3. **L0 逐字原文层**：`corpus/` + `manifest.json` + `app/import_corpus.py`（校验/去重/SHA256）+ `build_v5.py` 多来源导入；`article_text` 37 → 40。L0 不进 FILES、不参与主检索索引。

## 3. 架构契约（改知识库前必读）

1. **重建链**：`build_kb.py → enrich_kb.py → build_concepts.py → import_corpus.py → build_v5.py → audit_kb.py → build_coverage_matrix.py → eval_kb.py`。**`import_corpus.py` 必须在 `build_v5.py` 之前**。`enrich_kb.py` 会 `os.remove(DB)`，重建后从备份导回 `query_log` / `eval_run` / `eval_result` / `external_lookup_log`；alias 由 SYNONYMS + `build_concepts.py` 自动重建为 89 条，无需导回。
2. **条目格式**：`## NN.x 标题` + `| 字段 | 内容 |` 两列表；`id=前缀-节号`；`status` 从 `时效性/生效状态/状态` 提取；`tier` 由 `enrich_kb.py` 实证重算。51–56 走 `business_case` 11 字段专用模板（已在 `enrich_kb.py` / `audit_kb.py` 注册）。
3. **同步 6+2 处**：`build_kb.py`（FILES + A 层集合 + 版本）→ `00-index.md` → `static/index.html` → `e2e-test.py` → 根 `README.md` → `app/README.md` → `server.py`（refs / 端点）→ `PENDING-VERIFICATION.md` / `change_log`。**新增/改动计数后必须逐处 grep 残留**。
4. **两条不变量**：① 业务事项层不得回到主检索（会改变 BM25 IDF，实测让 Recall@5 1.0→0.9944）；② 不新增 RULES 规则来暴露新条目（会改变 188 题自动题口径）。新条目走 `/api/business-cases` 独立通道。
5. **L0 原文层**：新增逐字条文写 `corpus/*.md` + 更新 `manifest.json`（双源 ≥2、时效四态、条数），跑 `import_corpus.py` 校验通过后才写入 `article_text`；**不要**直接编辑 `kb.json` / DB / `corpus-articles.json`。
6. **外部核验**：本机覆盖机制见 `reports/external-lookup-implementation-2026-11-09.md` §9；策略规格见 `reports/adaptive-retrieval-reply-policy-2026-11-09.md`。默认关闭，离线行为不变。

## 4. 剩余不确定性（不许猜）

1. 边界提示中涉及具体条款清单（广宣费三类行业、CAS11/CAS36 文号、权益性交易具体规定）仍标「以官方原文为准」，未臆造文号。
2. 南沙 15% 2027 延续仍是 P-24 隔离项；另有 P-06b / P-10b / P-23。
3. L0 目前与 23 文件内容重叠，按增量接入（识别出历史 37 条中 2 条同法同条号重复）；待 23 文件退役后 corpus 才是唯一逐字事实源。更多法规原文待按 `SOURCES-CHANNELS.md` 八步 SOP 分批回库。
4. 逐字语料用于结论前仍须复核施行日与现行性；不承诺 100% 准确。

## 5. 下一步建议

1. 继续扩 L0 原文层：按税种/准则分批导入 18 税种法律与实施条例全文，每条挂双源链接与 SHA256。
2. 前端业务事项视图可增加「按依据跳转到法规条目」与导出 CSV。
3. 把 `/api/business-cases` 的 11 字段接入 `/api/ask` 的深度解读模式（当前仅独立视图）。
4. 历史报告（v13 升级报告、外部核验落地报告）里写的 `73/73` 是 v13 口径，当前为 **78/78**。

## 6. 关键路径与坑位速查

| 项 | 值 |
|---|---|
| Python | `C:/Users/aa152/AppData/Local/Programs/Python/Python312/python.exe`（`python` 缺包、`py` 已坏）；脚本一律绝对路径 |
| 服务重启 | `Get-CimInstance Win32_Process` 过滤 `Name -eq 'python.exe' -and CommandLine -like '*server.py*'`；**只按命令行文本过滤会误杀 PowerShell 自身** |
| 评测 | 服务启动后预热 3 发再跑 `eval_kb.py`；188 题约 7 分钟；基线 `reports/eval-report-v12-baseline-2026-11-09.json` |
| 规则字段 | 每条 RULES 必带 `role/risk/conclusion/basis/tips/refs/q/must`，缺 `role` 全服 KeyError |
| 批量替换 | 多处分散替换用一次性脚本逐处打印命中数（命中 0 立即中止）；**命令行 `python -c` 里不要放反引号或 Windows 反斜杠**，会被 shell 解释 |
| 文件操作 | Write 只新建不覆盖；改已交付物起新版本留旧；删除前先出清单；AI 产出归 `E:\workbuddy-data\`，小写英文 + 连字符 + `yyyy-mm-dd` |
| 质量红线 | 文号/日期/比例/条号进文档前必须联网核验，不确定标「以官方原文为准」；不承诺 100% 准确，只报验证结果 + 剩余不确定性 |

---

*本交接单由 WorkBuddy 汇编；v14.0 当前唯一基线。*
