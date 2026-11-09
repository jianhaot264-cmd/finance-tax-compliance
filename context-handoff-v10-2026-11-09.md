# 财税合规 · 上下文交接单 v10（导入前基线版）

> 生成：2026-11-09 ｜ 用途：**下个会话只读本文件即可继续**，不必回看历史对话或 v9。  
> 本轮性质：**只读扫描复盘 + 上下文压缩**。未修改任何现有文件、未提交 Git、未联网导入法规、未启动服务。  
> 保留关系：v9（`context-handoff-v9-2026-11-08.md`）为 v11.0 历史快照，不删不覆盖；本文件是当前唯一事实基线。  
> 目标：为**导入企业会计准则、税法法律法规等具体/逐字知识库**打下可执行基础。



---

## 0. 一句话状态

`E:\workbuddy-data\finance-tax-compliance\` 知识库 **v12.0 · 442 条 / 50 文件 / A 287 · B1 4 · B2 151**；后端 Python 3.12 纯标准库（8777），前端原生三件套，云端 HY4 流式；检索五路召回 + RRF + 弃答，问答走五阶段编排与四层信任防线。上一轮验证：冒烟 19/19、全量 e2e 73/73、评测 186 题 0 失败、trust 24/24。**当前最新成果尚未提交 Git，且文档计数存在 v11/v12 混写**——这是导入前必须先处理的两件事。

---

## 1. 磁盘实测基线（本轮只读核验，不是文档声明）

| 对象                              | 实测值                                                                                                                                                                                                                                                                                                     |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/kb.json`                   | `kb_version=v12.0`，`generated_at/verified_at=2026-11-09`，**442 条 / 50 文件**                                                                                                                                                                                                                              |
| tier                            | **A 287 / B1 4 / B2 151**（合计 442）                                                                                                                                                                                                                                                                       |
| status                          | **387 现行有效 / 47 汇编·动态 / 6 草案阶段 / 2 已废止**                                                                                                                                                                                                                                                                |
| entry 字段                        | 29 键：`id/file/heading/no/title/fields/body_md/search_text/category/tier/status` + `enrich_kb` 补的 `entry_type/doc_no/issuer/level/publish_date/effective_date/expiry_date/scope/core_clauses/compliance_points/sources/source_count/source_text/verified_at/status_norm/quality_flags/concept_complete`  |
| `app/finance-tax-compliance.db` | 5.83 MB / **23 表**：regulation 442、regulation_fts 442、article_text **37**、citation_verification 15、alias 89、concept 30、concept_relation 247、scenario 14、boundary_item 44、verification_item 10、golden_case 79、rule_reference **329**、pending_item 5、change_log 16、query_log 663、eval_run 4、eval_result 40 |
| `kb_meta`                       | v12.0 / 442 / 50 / tier_A 287 / generated_at `2026-11-09 09:54:58`，但 **`verified_at=2026-11-07`**（硬编码残留）                                                                                                                                                                                                |
| 目录                              | `knowledge-base/` 53 个 md（50 编号 + `00-index` + `SOURCES-CHANNELS` + `PENDING-VERIFICATION`）；`reports/` 30 个文件；`backups/` 存在；根 8 个文件                                                                                                                                                                     |
| 规则与评测                           | `app/README.md` 头部口径 **109 条精编问答**；`golden_extra.json` 79 手工题；`eval_kb.py` 组装 186 题。`server.py` 中 `"q"` 键 124 处（含意图对齐选项内嵌问句），规则数**以 `/api/meta` 的 `len(RULES)` 实时为准**                                                                                                                                   |
| 服务/入口                           | 端口 8777；桌面 `财税合规问答系统.lnk` → `start-qa.bat`，冷启动实测已加载意图对齐 v2，无需更新                                                                                                                                                                                                                                         |
| 仓库                              | `git@github.com:jianhaot264-cmd/finance-tax-compliance.git`（SSH），Public，`main`；远程仅 **2 提交**：`b0d773b`（初始 feat）、`bbaf4d1`（评测报告 chore）                                                                                                                                                                    |

---

## 2. 复盘发现：导入前必须处理的四类不一致

### 2.1 v12.0 成果未固化（最高优先级，影响可回滚性）

`git status --short`：**17 个已修改 + 4 个未跟踪**，远程停在 2 提交。

- 已修改：`app/README.md`、`app/build_kb.py`、`app/concepts.json`、`app/e2e-test.py`、`app/finance-tax-compliance.db`、`app/golden_extra.json`、`app/kb.json`、`app/retrieval.py`、`app/server.py`、`app/static/app.js`、`app/static/index.html`、`app/static/polish.css`、`knowledge-base/00-index.md`、`knowledge-base/41-expiry-alerts.md`、`reports/audit-stats.json`、`reports/eval-report-v5.json`、`reports/regulations-master-2026-11-07.csv`
- 未跟踪：`knowledge-base/49-personal-tax-finance.md`、`knowledge-base/50-housing-fund-finance-rules.md`、`start-qa.bat`、`app/kb-pre-enrich-2026-11-07.json`（后者为中间备份，需判断是否入库）

结论：**49/50 两个新知识库文件 + 意图对齐 v2 + 提示词优化都还没 push**，路人视角看到的仍是 v11 状态。导入前必须先提交或先打基线包，否则大批量导入无法回滚。

### 2.2 计数漂移（v12.0 只同步了部分「6 处」）

| 位置                             | 现值                               | 应为（实测）                                                                                            |
| ------------------------------ | -------------------------------- | ------------------------------------------------------------------------------------------------- |
| `knowledge-base/00-index.md:3` | 标 v12.0 但描述沿用 v11 的「全税种复盘」       | v12.0 = 个人财税 + 公积金 + 澄清式交互 + 提示词风格                                                                |
| 同文件 `:9`                       | v11.0 写「442 条 / 50 文件」           | v11.0 实为 429 / 48；v12.0 才是 442 / 50。需补 v12 版本日志行                                                  |
| 同文件 `:17`                      | 「430 条」状态（377/44/6/2）            | **442**（387 / 47 / 6 / 2）                                                                         |
| 同文件 `:20`                      | A 281 / B1 4 / B2 144            | **A 287 / B1 4 / B2 151**                                                                         |
| 同文件 `:89`                      | `rule_reference` 323 条           | **329**                                                                                           |
| `README.md:89`                 | `/api/kb（430 条）`                 | 442                                                                                               |
| `README.md:103`                | A 层 282 / B1 4 / B2 144          | **A 287 / B1 4 / B2 151**                                                                         |
| `README.md:7`                  | CI badge 仍为 `YOUR_ORG` 占位符       | `jianhaot264-cmd`                                                                                 |
| `static/index.html:7`          | 已是 442 / v12.0                   | 正确，保留                                                                                             |
| `static/index.html:244`        | 「142 题 Golden QA（自动 91 + 手工 51）」 | 186 题（自动 + 79 手工）                                                                                 |
| `app/README.md` 头部             | 已是 v12.0 / 442 / 50 / 109        | 正确；但正文残留「98 个规则引用 / 152 条 rule_reference / A 层 22」等 v4 旧数，且把 v9 描述成「442/50/109」（v9 实为 429/48/102） |
| `app/e2e-test.py`              | 已含 `442 条法规` 断言                  | 正确；残留 `"429" in t` 旧文本检查可清理                                                                       |

### 2.3 硬编码日期与占位符

`app/enrich_kb.py:32`（CSV 固定名 `regulations-master-2026-11-07.csv`）、`:35`（备份名）、`app/build_v5.py:86/93/110`（逐字法条 `verified_at` 写死 2026-11-07、`kb_meta v5_layer`）、DB `kb_meta.verified_at=2026-11-07`。**导入后核验日会推进，这些必须改为读 `kb.json` 的 `verified_at`**，否则新条目会被盖上旧核验日，破坏 trust.py 的时效衰减判定。

### 2.4 逐字法条通道被锁死在单一文件

`build_v5.py` 只对 `file == "23"` 的条目用正则 `第X条…「原文」` 提取 → `article_text` 仅 **37 条**，来源写死「企查查法律/华宇元典/同花顺」。这既是「导入具体法规原文」的现成落点，也是必须改造的第一处硬编码。

---

## 3. 系统契约（导入必须遵守，否则评测会退化）

### 3.1 条目格式（`build_kb.py` 解析器契约）

```markdown
## 38.3 收入准则（CAS 14）：控制权转移与五步法      <- 二级标题；NN.x 决定 id

| 字段 | 内容 |                                       <- 必须是这个表头，字段名逐字匹配
| 文号 | ... |
| 发文机关 | ... |
| 效力层级 | ... |
| 公布/施行 | ... |
| 时效性 | 现行有效 / 已废止 / 修订中 / 草案阶段 / 汇编·动态 |
| 适用范围 | ... |
| 核心条款 | ... |
| 合规要点 | ... |
| 信源 | 至少 2 个官方链接 |
| 核验 | 日期 + 方式 |
```

- `id = 前缀-节号`（如 `38-38.3`）；标题含《》时取书名号内为 `title`。
- `tier` 初值由 `build_kb.py` 的 **A 层前缀集合**（当前 16–50）决定，之后由 `enrich_kb.py` 按元数据**实证重算**：A = 法规型 + 10 字段齐 + 双源 + 四态；B1 = 元数据齐但单源；B2 = 其余。
- `enrich_kb.py` 的 `entry_type`：`regulation / table_row / digest / practice`，另有 `EXPLAIN_TYPES` 把 25/26/27/28 前缀分别映射为 `concept / relation / scenario / verification` 专用模板。`audit_kb.py` 按类型分型审计，`regulation` 强制 8 项 `REG_FIELDS` + ≥2 源 + 合法状态。
- **不要手工编辑 `kb.json` 或 DB**；改 md 后按链重跑。

### 3.2 单一事实源与重建链

```
knowledge-base/*.md
  -> build_kb.py        (解析 -> kb.json)
  -> enrich_kb.py       (entry_type/tier/元数据/SQLite/CSV/视图)
  -> build_concepts.py  (概念层)
  -> build_v5.py        (article_text / citation_verification / golden_case / kb_meta)
  -> audit_kb.py        (reports/audit-stats.json)
  -> eval_kb.py         (186 题评测)
  -> build_coverage_matrix.py (reports/coverage-matrix-*.csv/.json)
```

### 3.3 新增主题文件必须同步的点（v9 的「6 处」+ 本轮补 2 处）

`build_kb.py`（**FILES 列表 + A 层前缀集合 + kb_version/generated_at/verified_at**）→ `knowledge-base/00-index.md` → `app/static/index.html` → `app/e2e-test.py` → 根 `README.md` → `app/README.md` → `server.py`（RULES 的 `refs` 指向精确条目 id）→ `PENDING-VERIFICATION.md` / `change_log`（若涉及隔离项）。

### 3.4 检索与评测红线（决定导入架构）

- `retrieval.py` **全量载入 kb.json entries** 构建 BM25（bigram/trigram）与 SQLite FTS5 trigram；`server.py` RULES 的 `refs` 是**精确条目 id 列表**，`eval_kb.py` 用 `must_refs` 判定 Recall@5。
- 若把「准则/税法逐条全文」直接塞成 `## NN.x` 条目：每条会被判 `regulation` 并强制十字段双源、被全量索引、挤占 Top5，**186 题评测必然退化**，A/B 层比例失真，引用校验漂移。
- 结论：**逐字原文与摘要卡必须分层，不能混在同一条目池**。

---

## 4. 导入缺口盘点（本轮只读比对）

### 4.1 企业会计准则

- 现有：`12-accounting-audit.md`（9 条，会计法/代理记账/档案/内控）、`38-accounting-standards.md`（8 条：制度体系、基本准则、CAS14 收入、CAS21 租赁、小企业准则、报表格式、税会差异）、`43-accounting-standards-advanced.md`（10 条：CAS22/23/24/2/33 + 四组税会差异）、`50`（会计法 2024 修正等速查）。合计约 33 条，覆盖具体准则仅 CAS 2/14/21/22/23/24/33。
- 缺口：**其余具体准则主题**（存货、长期资产/固定资产/无形资产、资产减值、职工薪酬、或有事项、政府补助、借款费用、所得税会计、外币折算、企业合并、会计政策变更与差错更正、资产负债表日后事项、财务报表列报、现金流量表、每股收益、分部报告、关联方披露、金融工具列报、公允价值计量、合营安排、持有待售等）、**应用指南与准则解释系列**、**会计科目与主要账务处理**、**财报格式后续修订**、**税会差异逐项对照表**、小企业准则全章节。
- 注意：具体准则的完整现行编号清单、各解释公告号、修订沿革 **须先按财政部会计司现行目录联网核验**，不得凭印象写文号（本项目质量红线）。

### 4.2 税法法律法规

- 现有：`44-tax-law-master-matrix.md`（8 条，14 法 + 4 暂行条例三层对照）、`08`（单行税种法律 11）、`45`（小税种 11）、`46`（征管程序 10）、`48`（指导文件体系 7）、`23-authoritative-articles.md`（15 条 / **37 条逐字法条**）。性质均为**层级表 / 汇编 / 摘要**。
- 缺口：**14 部税法 + 4 暂行条例的逐条全文**、实施条例逐条（512/707/362/826 号令等）、财政部/总局公告库（数千件）、已废止文件沿革、地方配套、逐条时效与新旧衔接。当前 `article_text` 只有 37 条，远不足以支撑「引用原文」。
- `SOURCES-CHANNELS.md` 已定义 A–E 级信源与**八步核验 SOP**（定文号 → 找原文 → 看时效 → 抓硬指标 → 查落地 → 双源交叉 → 标不确定性 → 留痕），导入原文直接复用，不另起炉灶。

### 4.3 体量判断

现有 50 文件 / 442 条是**精编摘要层**；准则 + 税法逐字原文是**数千至数万条文**量级。一次性平铺会击穿检索与评测，必须分批 + 分层 + 开关式接入。

---

## 5. 导入架构决策（建议方案，下轮按此执行）

### 5.1 三态分层

| 层                    | 载体                                                                                                             | 是否进 `FILES` / kb.json / BM25 | 作用                                                                      |
| -------------------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------- | ----------------------------------------------------------------------- |
| **L0 原文层（新增）**       | `knowledge-base/corpus/<doc-id>.md` + `corpus/manifest.json`（文号、全称、效力层级、公布/施行/失效日、官方 URL、抓取日、SHA256、条数、双源、核验日） | **否**                        | 逐字原文，唯一事实源；按条号可寻址                                                       |
| **L1 摘要层（现有 50 文件）** | `## NN.x` + 十字段卡                                                                                               | 是                            | 检索与问答主体，继续承载结论、合规要点、税会差异                                                |
| **L2 引用层（扩展）**       | SQLite `article_text`（去 `file=="23"` 硬编码，多来源）+ 摘要卡 `fields` 新增「原文锚点」                                           | 不单独建 entry                   | 把 L1 的每条结论挂到 L0 的具体条号；`provenance_block()` 输出「摘要卡 id + 原文条号 + 官方 URL」双链 |

### 5.2 导入管线（新增 `app/import_corpus.py`，纯标准库）

校验顺序：UTF-8 与编码 → 文号唯一性 → 逐字比对（SHA256 留痕）→ 时效四态 + 到期日 → 双官方源 → 按条号切分 → 去重 → 写 L0 + `manifest.json` → 增量写 `article_text` → 回写 L1 的「原文锚点」。  
**原文层默认不参与主检索**（或设独立开关 `corpus_weight=0`），先保证 186 题评测不退化为零，再逐步放开。

### 5.3 前缀与文件命名

- L1 如需新增主题文件：`51-` 起顺延，**每文件 ≤ 15 条**，同步加入 `build_kb.py` FILES 与 A 层集合（若全部达标）。
- L0 用 `corpus/` 子目录、小写英文 + 连字符 + 文号/准则号，**不占编号前缀**，避免解析器误读。
- 建议批次：① 固化基线 + 修漂移 ② 准则逐项摘要卡（51–54）③ 准则原文层 ④ 税法 14 法 + 4 条例原文层 ⑤ 实施条例与公告（按月增量）⑥ 全链回归评测。每批独立提交、独立基线包。

---

## 6. 导入前 P0 动作清单（按序执行）

1. **固化基线**：提交当前 17 M + 4 ?? 到 `main` 并 push，或先跑 `python app/backup_baseline.py v12 2026-11-09`（`ROOT_FILES` 需加入本交接单）；确认可回滚后再动知识库。
2. **修计数漂移**：按 §2.2 表逐项改；改完用 `/api/meta`、`kb.json`、`kb_meta`、`00-index.md`、`README.md`、`static/index.html` 六处交叉核对，数字只允许来自 `kb.json`。
3. **清硬编码日期**：§2.3 四处改为读 `kb.json.verified_at`；顺带修 CI badge 的 `YOUR_ORG`。
4. **改造 `build_v5.py`**：`article_text` 支持多来源与 `corpus_id / hash / official_url / verified_at`，去掉单一来源写死。
5. **联网核验目录**：按 `SOURCES-CHANNELS.md` 八步 SOP 确认「现行企业会计准则具体准则清单 + 18 税种现行法律/条例清单」，输出 `reports/import-scope-2026-11-09.md`；**不确定项一律标待核验，不猜文号/日期/比例**。
6. 上述完成后再开始第 1 批导入，并按 §3.2 全链重跑。

---

## 7. 验收标准（每批导入都要过）

1. 引用零悬空（RULES `refs` 与 `rule_reference` 全部命中现有 id）。
2. 逐字条目与官方原文 SHA256 一致、≥2 个官方直达链接、时效四态 + 到期日明确。
3. `audit_kb.py` 无新增 `pending_field`，tier 重算与实测一致。
4. **评测 186 题不退化**：Recall@5 / MRR / 弃答 / 角色 / 要点 / 禁用 / 规则 / 引用，任一退化必须诊断修复后再继续。
5. 冒烟 19/19、全量 e2e 73/73、trust 24/24、计算 9/9、三流核对与清单通过。
6. `/api/meta`、`kb.json`、`kb_meta`、`00-index.md`、两份 README、index.html 计数一致。
7. 覆盖矩阵 `build_coverage_matrix.py` 重跑无空白类；新类别有代表条目。
8. CI 绿，桌面快捷方式冷启动仍加载最新代码。

---

## 8. 关键路径与坑位速查


| 项 | 值 |
|---|---|
| Python | `C:/Users/aa152/AppData/Local/Programs/Python/Python312/python.exe`（`python` 是缺包的托管 3.13，`py` 已坏）；脚本一律用绝对路径 |
| 服务重启 | 杀全部 `*server.py 8777*`（命令行可能是相对路径），确认 0 个再启动、确认 1 个；多进程同端口会返回旧代码 |
| 评测预热 | 服务刚启动先打 3 发再跑 `eval_kb.py`，否则大面积空响应假失败 |
| 规则抢答 | 新增更具体条目会把旧 `must_refs` 挤出 Top5；改规则 refs 到更具体条目，不删旧条目 |
| 日期错配 | 中文「2027 年 12 月 31 日」由 `retrieval.expand_query` 归一为 ISO；新条目正文要含问句词 |
| 规则字段 | 每条 RULES 必带 `role/risk/conclusion/basis/tips/refs/q/must`，缺 `role` 会全服 KeyError |
| 时效正则 | `enrich_kb.py` 的 `EXPIRY_RE` 已排除「截至」语境，勿放宽 |
| 文件操作 | Write 只新建不覆盖；改已交付物起 v2 留旧；删除前先出清单；AI 产出归 `E:\workbuddy-data\`，小写英文 + 连字符 + `yyyy-mm-dd` |
| 质量红线 | 文号/日期/金额/比例进文档前必须联网核验，不确定就标待核验或进隔离清单；不承诺 100% 准确，只报验证结果 + 剩余不确定性 |

---

*本文件由财税合规专家团主理人编排汇编（本轮为工程基线复盘，未启动 6-Phase 企业合规 SOP、未下发成员专业产出）。*
