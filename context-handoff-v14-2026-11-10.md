# 财税合规 · 上下文交接单 v14（当前唯一基线）

> 生成：2026-11-10 ｜ **下个会话只读本文件即可继续**。v9–v13 均为历史快照，保留不覆盖。
> 本轮：L0 原文层扩容 + 业务事项 11 字段接入深度解读 + 三处边界闭环 → 升 **v15.0**。

---

## 0. 一句话状态

`E:\workbuddy-data\finance-tax-compliance\`：知识库 **v15.0 · 472 条 / 56 文件 / A 318 · B1 4 · B2 150**；`business_case` 30/30 全 A、`article_text **455** 条**（23 文件 37 + L0 原文层 418）、corpus 唯一逐字条文 **119**、引用零悬空。后端 Python 3.12 纯标准库（8777），前端 5 tab。**188 题评测 0 未达标且 v5 指标与基线逐项一致**，冒烟 19/19、e2e 83/83、trust 24/24、单测 37/37、一致性 29/29。

## 1. 实测基线

| 项 | 值 |
|---|---|
| `kb.json` | v15.0 / 472 条 / 56 文件 / `verified_at=2026-11-09`（全库基线；变动条目单条标 2026-11-10） |
| tier / status | A 318 / B1 4 / B2 150；414 现行 / 50 汇编动态 / 6 草案 / 2 废止 |
| entry_type | regulation 345 / digest 31 / table_row 4 / concept 30 / relation 8 / scenario 14 / verification 10 / **business_case 30（全 A）** |
| `pending_field` | 全库 **7**（属地/到期隔离项，应保留）；business_case **0** |
| SQLite | regulation 472、fts 472、**article_text 121**、citation_verification 15、alias 89、rule_reference 329、golden_case 79；运行时留痕 query_log / eval_run / eval_result / external_lookup_log（重建后需导回） |
| L0 corpus | `knowledge-base/corpus/`：`authoritative-articles-v5.md`（37）、`company-law-2023.md`（1）、`announcement-2023-12.md`（2）、**`vat-law-2024.md`（38）**、**`vat-regulation-2025.md`（54）** + `manifest.json`（5 份 / 双源 / SHA256）+ **`IMPORT-BACKLOG.md`（18 税种进度）** |
| 评测 | 188 题：Recall@5 1.0 / MRR 0.6836 / 引用 0.6451 / 弃答·角色·禁用 1.0 / 规则 0.9468 / 要点 0.9714；基线 `reports/eval-report-baseline-2026-11-10-pre-s2s3.json` |
| 前端 | 5 tab（chat / kb / incentives / about / business）；业务事项视图含 6 类筛选、11 字段、依据跳转、CSV 导出 |
| 深度解读 | `POST /api/ask {mode:"deep"}` 额外返回 `answer.business_cases`（命中业务事项 ≤3 条，含 11 字段；**弃答不挂**） |
| 启动 | 主用计划任务 `TaxQA-Server`（`pythonw.exe` 无控制台，托管进程不随会话退出）：`schtasks /run /tn "TaxQA-Server"`；根 `start-qa.bat` v2（健康检查 + 轮询就绪 + 单实例 + 日志 `app/logs/server.log`）用于首次/手动拉起 |
| 外部核验 | `config.json` 默认 `false`；本机 `app/config.local.json`（不入库）覆盖为 `true` |
| 回滚 | `backups/baseline-v15-2026-11-11.zip`（含 corpus 目录）；重建前 DB 备份 `backups/pre-v15-rebuild*-2026-11-10.db` |
| 版本库卫生 | `app/finance-tax-compliance.db` **已停止跟踪**且**已从全部历史中清除**（2026-11-11 经授权执行 filter-branch，`.git` 20 MB→1.8 MB，历史 DB 残留 0，提交 15→13）；`.gitignore` 已覆盖；重建链可完全复现该库 |

## 2. 本轮交付（2026-11-10 · v15.0）

1. **三处边界闭环**：广宣费 → 财政部 税务总局公告 **2025 年第 16 号**（三类行业 30%、2026-01-01 至 2027-12-31、2020 年第 43 号同日废止）；CAS11／CAS36 → **财会〔2006〕3号**；权益性交易 → **财会函〔2008〕60号第（三）8 项**（纠正了「财会〔2008〕11 号」的常见误记）。
2. **深度解读接入**：`business_case_context()` 以独立字段返回，`score/len(q) ≥ 0.7` + `score ≥ 4.0` + 相对条带 `≥ top1×0.5`；`abstain` 不挂。
3. **L0 扩容**：新增 `app/fetch_corpus.py`（双源抓取、拆条、条号连续、NFKC 逐条比对，不一致拒绝入库）；导入增值税法 38 条 + 实施条例 54 条；`article_text` 40 → **455**；新增 `corpus/IMPORT-BACKLOG.md`（18 税种进度，**完成 2/18**）。
4. **修缺陷**：53.2 拼接导致降 B2、免责声明写死 2026-11-07、`backup_baseline.py` 漏 corpus 目录、`index.html` 主题文件数 50→56。

详见 `reports/upgrade-report-v15-2026-11-10.md`。

## 3. 架构契约（改知识库前必读）

1. **重建链 8 步**：`build_kb.py → enrich_kb.py → build_concepts.py → import_corpus.py → build_v5.py → audit_kb.py → build_coverage_matrix.py → eval_kb.py`。**`import_corpus.py` 必须在 `build_v5.py` 之前**。`enrich_kb.py` 会 `os.remove(DB)`，重建后从备份导回 `query_log` / `eval_run` / `eval_result` / `external_lookup_log`；alias 由 SYNONYMS + `build_concepts.py` 自动重建为 89 条。
2. **条目格式**：`## NN.x 标题` + `| 字段 | 内容 |` 两列表；`id=前缀-节号`；`status` 从 `时效性/生效状态/状态` 提取；`tier` 由 `enrich_kb.py` 实证重算。51–56 走 `business_case` 11 字段专用模板。
3. **同步 6+2 处**：`build_kb.py`（FILES + A 层集合 + 版本）→ `00-index.md`（含版本日志）→ `static/index.html` → `e2e-test.py` → 根 `README.md` → `app/README.md` → `server.py`（refs / 端点）→ `PENDING-VERIFICATION.md` / `change_log`。改计数后逐处 grep 残留。
4. **三条不变量**：① 业务事项层不得回到主检索（会改 BM25 IDF，实测让 Recall@5 1.0→0.9944）；② 不新增 RULES 规则来暴露新条目；③ 深度模式的业务事项只走**独立字段**，不得写进 `sections`/`text`/`refs`（否则评测与 trust 都会变）。
5. **L0 原文层**：新增条文用 `app/fetch_corpus.py`（两源、逐条比对、条号连续）→ `import_corpus.py` → `build_v5.py`；**不要**手写 corpus md 或直接改 `kb.json` / DB / `corpus-articles.json`。逐字条文不得由模型复述。
6. **外部核验**：本机覆盖机制见 `reports/external-lookup-implementation-2026-11-09.md` §9；策略见 `reports/adaptive-retrieval-reply-policy-2026-11-09.md`。默认关闭，离线行为不变。
7. **服务启动**：首选计划任务 `schtasks /run /tn "TaxQA-Server"`（pythonw 无控制台）。**由工具/会话直接启动的进程会随会话结束被杀**（实测任务结果 -1073741510 = 0xC000013A，即控制台关闭触发 Ctrl+C），`start` 并不能真正脱离；`start-qa.bat` 只用于首次注册或手动拉起。改 `server.py` 后先按 `Name -eq 'pythonw.exe' -and CommandLine -like '*server.py*'` 精确停旧进程，再 `schtasks /run`。

## 4. 剩余不确定性（不许猜）

1. **L0 仅完成 2/18 税种**（增值税法系）；其余 16 个税种与其配套条例/细则标「待入」，见 `corpus/IMPORT-BACKLOG.md`。企业所得税法（60 条）与实施条例（133 条）条数最多，建议优先。
2. 广宣费三类行业清单已核到，但**行业是否属「化妆品制造或销售」等的具体判定**仍须按主营业务与主管税务机关口径确认。
3. ~~业务招待费 60%/5‰ 未核验~~ **2026-11-11 已核**：企税条例第四十三条（发生额 60%、不超过当年销售（营业）收入 5‰）+ 国税函〔2009〕202 号视同销售收入口径，已写入 53.2。
4. 南沙 15%：文号已于 2026-11-11 做实为**财税〔2022〕40 号**，先行启动区＝南沙湾／庆盛枢纽／南沙枢纽 3 区块；**2027 年延续文件经四渠道检索仍未检索到**，维持 P-24 到期预警（距到期约 7 周）。另有 P-06b / P-10b / P-23。
   - 广宣费三类行业判定：16 号公告未定义判定方法，已在 53.2 如实写明「无更细官方口径、不作推断」。
5. L0 与 23 文件内容重叠，按 (法规名, 条号) 去重；23 文件退役后 corpus 才是唯一逐字事实源。
6. 逐字语料用于结论前仍须复核施行日与现行性；不承诺 100% 准确。

## 5. 下一步建议（有序）

1. 继续 L0：按 `IMPORT-BACKLOG.md` 分批导入，优先企业所得税法 + 实施条例、个人所得税法 + 实施条例。
2. 业务事项详情页可加「按依据跳转到法规条目」的**精确条目跳转**（当前是检索回填关键词）。
3. 前端渲染 `answer.business_cases`（后端已返回，前端深度解读面板尚未展示该块）。
4. 把 L0 逐字层以低权重接入检索（需先量化对 188 题的影响，退化即回滚）。

## 6. 关键路径与坑位速查

| 项 | 值 |
|---|---|
| Python | `C:/Users/aa152/AppData/Local/Programs/Python/Python312/python.exe`（`python` 缺包、`py` 已坏）；脚本一律绝对路径 |
| 服务重启 | 过滤必须带进程名（服务为 `pythonw.exe`）且 `CommandLine -like '*server.py*'`，只按命令行文本会误杀 PowerShell 自身；启动用 `schtasks /run /tn "TaxQA-Server"`；`tasklist` 里可能有用户自装程序的同名进程（如桌宠的 pythonw），别按名字一刀切 |
| 评测 | 启动后预热 3 发再跑 `eval_kb.py`；188 题约 7 分钟；基线 `reports/eval-report-baseline-2026-11-10-pre-s2s3.json` |
| 抓取法规 | **先 `--dry-run`**，看双源是否逐条一致；页脚噪声/章节标题已内置过滤；全角半角靠 NFKC 归一化；繁体镜像（big5.）不可作第二源 |
| 批量替换 | 一次性脚本逐处打印命中数（命中 0 立即中止）；**多行拼接务必带换行**（本轮 53.2 因缺 `\n` 拼成 `\|\|` 导致降 B2）；`python -c` 内不放反引号/Windows 反斜杠 |
| .bat 写入 | Python `newline='\r\n'` + UTF-8，配 `chcp 65001`，不加 BOM |
| 文件操作 | Write 只新建不覆盖；改已交付物先备份、起新版本留旧；删除前先出清单 |
| 质量红线 | 文号/日期/比例/条号进文档前必须联网核验（本轮纠正「财会〔2008〕11 号」→「财会函〔2008〕60号」）；历史报告口径不篡改；不承诺 100% 准确 |

---

## 7. 2026-11-11 系统审计（v15.1 之后）

详见 `reports/system-audit-2026-11-11.md`。修 5 处真实缺陷：

1. **P0** `server.py` 系统提示词核验日写死 `2026-11-06`、`deep_dive.py` 写死 `2026-11-07` → 均改为读 `kb.json.verified_at`（现为 2026-11-09）；
2. **P0** `app/finance-tax-compliance.db` 曾被 12 次提交（含 2237 行用户提问）→ `git rm --cached` + gitignore；
3. **P1** CI 覆盖面不足（`deep_dive`/`orchestrator`/`retrieval`/corpus 工具链未做语法检查，`test_business_deep.py` 未接入）→ 扩到 20 模块 + 新增 3 道闸门（核验日不写死 / DB 不入库 / 语料一致性）；
4. **P1** `checklist.py` 快照写死 `2026-11-08` → 改读快照；
5. **P2** `apply_corrections.py` 加「已执行完毕、勿重复运行」警示。

**新增可复跑审计脚本**：`app/test_system_audit.py`（30 项：端点/模式/上下文/数据一致性/静态资源）。

**明确未改**：8 个独立工具脚本（非死代码）、`/api/deep-dive` 不覆盖基础术语（设计取舍）。

**2026-11-11 追加**：① 业务招待费双限与视同销售收入口径已核实写入；② 广宣费行业判定确认无更细官方口径；③ 南沙文号做实为财税〔2022〕40 号并补 3 区块、2027 延续仍未检索到；④ 历史 git 中的运行时 DB 已清除（`.git` 20 MB→1.8 MB，提交 15→13，代码与知识库零丢失，已 force-push；GitHub 侧需等其后台 GC 才显示体积下降）；⑤ 层数因补全字段升为 **A 318 / B1 4 / B2 150**，全部当前基线文档已同步。

**唯一保留项**：L0 原文层 16 个税种的法规条文导入——这是内容生产（需逐部检索双官方源 URL 后抓取比对），不是事实核查；`corpus/IMPORT-BACKLOG.md` §六 已给出逐部检索词与验收标准，补齐 `batch-sources.json` 后跑 `python app/batch_import_corpus.py` 即可。

---

*本交接单由 WorkBuddy 汇编；v14 为当前唯一基线。*
