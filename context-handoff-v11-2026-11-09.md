# 财税合规 · 上下文交接单 v11（v13.0 当前基线）

> 生成：2026-11-09 ｜ **下个会话只读本文件即可继续**，不必回看历史或 v9/v10。
> v9（v11.0 历史）、v10（v12.0 导入前基线）均保留不覆盖。
> 当前仓库：本地 3 个提交，最新 `ae9c6d5`（A 线）与待提交的 B 线；**两次提交都未 push**。

---

## 0. 一句话状态

`E:\workbuddy-data\finance-tax-compliance\`：知识库 **v13.0 · 472 条 / 56 文件 / A 307 · B1 4 · B2 161**；新增 51–56 六个业务事项文件 / 30 条 `business_case` 结构化条目；后端 Python 3.12 纯标准库（8777），前端原生三件套，云端 HY4。**评测 188 题 0 未达标且指标与 v12 基线逐项一致**，冒烟 19/19、e2e 73/73、trust 24/24。

## 1. 实测基线

| 项 | 值 |
|---|---|
| `kb.json` | v13.0 / 472 条 / 56 文件 / `verified_at=2026-11-09` / `enriched_at` 已动态化 |
| tier / status | A 307 / B1 4 / B2 161；414 现行有效 / 50 汇编·动态 / 6 草案 / 2 已废止 |
| entry_type | regulation 345 / digest 31 / table_row 4 / concept 30 / relation 8 / scenario 14 / verification 10 / **business_case 30** |
| SQLite | regulation 472、fts 472、article_text 37、alias 89（含 60 条历史 short_title）、rule_reference 329、query_log 663、eval_run 4 / eval_result 40（后三者重建后由备份导回） |
| 评测 | 188 题 = 自动 109（RULES）+ 手工 79；Recall@5 1.0、MRR 0.6836、引用 0.6451、弃答/角色/禁用 1.0、规则 0.9468、要点 0.9714 |
| 服务 | `http://localhost:8777`，`/api/meta` = v13.0 / 472 / 109 / 2026-11-09；桌面快捷方式指向 `start-qa.bat`，无需更新 |
| Git | `git@github.com:jianhaot264-cmd/finance-tax-compliance.git`（SSH，Public）；已推送至 `b1fb073`，B 线 `2339437` 与收尾提交见最新 log |
| 基线包 | `backups/baseline-v12-2026-11-09.zip`（120 文件）、`backups/baseline-v13-2026-11-09.zip`；DB 备份 `backups/pre-v13-rebuild-2026-11-09.db` |

## 2. 本轮交付

**A 线（已提交 `ae9c6d5`）**：修 6 处计数漂移、补版本日志 v10–v12、清硬编码核验日（`build_v5.py` 改读 `kb.json.verified_at`，`enrich_kb.py` 的 `enriched_at` 动态化）、修 CI badge 占位符、`.gitignore` 排除中间产物、纳入 49/50 两个知识文件与 `start-qa.bat`、生成 v12 基线包。26 文件，+1893/−376。

**B 线（本轮）**：
1. **6 个业务事项文件 / 30 条条目**：51 收入、52 资产、53 费用、54 税费、55 往来、56 期末结转；每条 11 字段（适用范围 / 确认计量 / 会计分录与流程 / 税务处理 / 税会差异 / 参照依据与关键条款 / 依据层级 / 生效状态 / 适用边界 / 信源 / 核验）。
2. **专家团正式协作**：团队 `tax-compliance-kb-expansion`，`voucher-accountant`（分录）、`tax-filing-specialist`（税务与差异）、`compliance-auditor`（依据与边界）并行产出，主理人汇编，未代写专业内容。
3. **注册 `business_case` 专用模板**：`enrich_kb.py` 的 `EXPLAIN_TYPES` 加 51–56 → 11 字段模板；`audit_kb.py` 的 `EXPLAIN_TYPES` 集合加该类型；`build_kb.py` FILES/A 层集合/版本同步；覆盖矩阵新增 6 类（39 类 0 空白）。
4. **独立检索通道**：`retrieval.py` 主检索只用 `main_entries`（排除 business_case），另建 `bm25_business` 与 `retrieve_business_cases()`；`server.py` 新增 `GET /api/business-cases?q=...`（返回 30 条，实测首条命中 51-51.1）。
5. **依据核验**：财政部会计司官网确认 CAS30 财会〔2026〕11 号（2026-08-05 印发，2027/2029/2030 分阶段施行）与解释第20号；三个官方入口（会计司准则专栏 / 税务总局政策法规库 / 国家法律法规数据库）实测可达；禁止清单下发成员，杜绝已废止依据与编造文号。

## 3. 关键架构契约（改知识库前必读）

1. **条目格式**：`## NN.x 标题` + `| 字段 | 内容 |` 两列表 → `build_kb.py` 生成 `id=前缀-节号`；`status` 从 `时效性/生效状态/状态` 字段提取；`tier` 由 `enrich_kb.py` 实证重算。
2. **单一事实源**：`knowledge-base/*.md` → `build_kb.py` → `enrich_kb.py` → `build_concepts.py` → `build_v5.py` → `audit_kb.py` → `build_coverage_matrix.py` → `eval_kb.py`。**不手工编辑 kb.json / DB**。
3. **同步 6+2 处**：`build_kb.py`（FILES + A 层集合 + 版本）→ `00-index.md` → `static/index.html` → `e2e-test.py`（「N 条法规」断言）→ 根 `README.md` → `app/README.md` → `server.py`（RULES refs / 端点）→ `PENDING-VERIFICATION.md` / `change_log`。
4. **不要新增 RULES 规则来暴露新条目**：评测集自动题由 `len(RULES)` 生成，加规则会改变 188 题口径；新条目走 `/api/business-cases` 独立通道。
5. **业务事项层不得回到主检索**：扩容语料会改变 BM25 IDF，实测会让 `A-vat-simple-method` 掉出 Top5（Recall@5 1.0→0.9944）。任何检索内核改动都必须跑 `eval_kb.py` 与基线 `reports/eval-report-v12-baseline-2026-11-09.json` 对比。
6. **重建副作用**：`enrich_kb.py` 会 `os.remove(DB)`；重建后必须从备份导回 `query_log` / `eval_run` / `eval_result`（alias 由 SYNONYMS 与 build_concepts 自动重建，无需导回）。先备份再重建。

## 4. 剩余不确定性（不许猜）

1. 10 条 `business_case` 因适用边界如实标「待核验」被记 `pending_field`（全库 7→17），属边界提示非数据缺失；作申报依据前回查官方原文。
2. 信源是**官方入口级渠道**（按文号/准则号检索），逐条全文直达链接待回库核验。
3. 白名单外具体准则只写名称 + 条款要旨，文号标「以财政部会计司现行目录为准」；条号不确定写「以原文为准」。
4. `build_v5.py` 的 `article_text` 仍只从 `file=="23"` 提取 37 条逐字法条，多来源 L0 原文层尚未建（方案见 v10 §5）。
5. **已更正（15:30）**：alias 89 = synonym 29 + concept_code 30 + concept_name 30，库中无 `short_title`；此前「历史 60 条短标题别名、重建掉到 29」为误判，死代码已移除，重建后 alias 仍 89 条、无需导回。
6. 隔离项不变：P-06b（BLOCKED）、P-24 南沙 15% 2026-12-31（EXPIRING）、P-10b / P-23（SCOPE）。

## 5. 下一步建议（按优先级）

1. **push 待办**：本地 `ae9c6d5` + B 线提交均未推送；推送前确认清单（见最终回复/报告），SSH Deploy Key 已配好。
2. 修 `enrich_kb.py` 短标题别名根因。
3. 闭环 10 条业务事项边界提示（优先 51.2 / 53.2 / 55.3 / 56.4）。
4. 按 v10 §5 三态分层建 L0 逐字原文层 `knowledge-base/corpus/` + manifest，扩展 `article_text` 多来源。
5. 前端增加 `/api/business-cases` 业务事项浏览入口。

## 6. 关键路径与坑位速查

| 项 | 值 |
|---|---|
| Python | `C:/Users/aa152/AppData/Local/Programs/Python/Python312/python.exe`（`python` 缺包、`py` 已坏）；脚本一律绝对路径 |
| 服务重启 | 用 `Get-CimInstance Win32_Process` 过滤 `Name -eq 'python.exe' -and CommandLine -like '*server.py*'`；**不要只按命令行文本过滤**，会误匹配 PowerShell 自身 |
| 评测预热 | 服务启动后先打 3 发 `/api/ask` 再跑 `eval_kb.py`，否则大面积空响应假失败；188 题约需 7 分钟 |
| 评测基线 | `reports/eval-report-v12-baseline-2026-11-09.json`（Recall@5 1.0 / MRR 0.6836 / 引用 0.6451） |
| 规则字段 | 每条 RULES 必带 `role/risk/conclusion/basis/tips/refs/q/must`，缺 `role` 全服 KeyError |
| 文件操作 | Write 只新建不覆盖；改已交付物起新版本留旧；删除前先出清单；AI 产出归 `E:\workbuddy-data\`，小写英文 + 连字符 + `yyyy-mm-dd` |
| 质量红线 | 文号/日期/比例/条号进文档前必须联网核验，不确定标待核验；不承诺 100% 准确，只报验证结果 + 剩余不确定性 |
| 批量修改 | 多处分散替换用一次性脚本并逐处打印命中数（命中 0 立即中止），避免同文件多次 Edit 覆盖竞态 |

---

*本交接单由财税合规专家团主理人汇编；专业内容由张记账、孙申报、赵审计三位成员分别产出。*
