# 自适应外部核验 · 落地与回归报告（v13.0 + policy-v1）

> 日期：2026-11-09 ｜ 策略依据：`reports/adaptive-retrieval-reply-policy-2026-11-09.md`
> 执行顺序：用户确认「先 A 再 B」。**A** 已推送 3 个提交；**B** 按策略 §6.2 落地并按 §6.3 全量回归。

---

## 一、A：推送完成

`git push origin main` → `bbaf4d1..b1fb073 main -> main` 成功；本地与远程同步（`origin/main..main = 0`）。已上线的 3 个提交：`ae9c6d5`（v12 工程收口）、`751218e`（v13 业务事项知识层）、`b1fb073`（策略规格）。仓库 `jianhaot264-cmd/finance-tax-compliance` 为 Public，SSH Deploy Key 链路正常。

## 二、B：落地清单（对应策略 §6.2 的 8 项）

| # | 改动 | 文件 | 说明 |
|---|---|---|---|
| 1 | 新增检索适配器 | `app/external_lookup.py` | 纯标准库 `urllib`；白名单域名、超时/重试≤2、进程内按日缓存、结构化证据返回、fixtures 注入用于离线单测 |
| 2 | 决策节点 | `app/orchestrator.py` | 新增 `decide_external()`；`run_pipeline()` 增加可选 `external_decision` 参数，在 retrieve 阶段记录 `need/reason/signals`（不传时 trace 完全不变） |
| 3 | 外部证据块 | `app/server.py` `build_llm_context()` | 仅在 `need=True` 时追加 `[外部核验]` 区块或兜底话术；返回 `external` 元数据（含 `block` 便于观测） |
| 4 | 提示词条款 | `app/server.py` `SYSTEM_PROMPT` | 替换第 1/2/7 条、新增第 15 条；第 9 条核验日改为「以知识库快照为准（当前 2026-11-09）」；`build_llm_context` 的日期与免责声明改为读 `KB["verified_at"]` 动态生成 |
| 5 | L0 来源准入 | `app/trust.py` | 新增 `source_gate()`；`trust_report()` 增加可选 `external_evidence` 参数，默认 `None` 时行为与 trust-v1.0 完全一致 |
| 6 | 检索留痕 | `app/build_v5.py` + `external_lookup.log_external()` | 新增 `external_lookup_log` 表（幂等建表），记录 q / need / signals / status / sources / evidence_count / note |
| 7 | 配置开关 | `app/config.json` | `external_lookup.enabled = false`（**默认关闭**），`timeout=3.0`、`max_retries=2`；离线部署行为与未引入本模块时一致 |
| 8 | 文档同步 | `README.md`、`knowledge-base/00-index.md`、`knowledge-base/SOURCES-CHANNELS.md` | 增可选能力说明、策略索引与 A–E 级渠道分级引用 |

**新增单测**：`app/test_external_lookup.py`（37 项，纯离线，网络层用 fixtures 注入）。

## 三、关键设计：只放宽信息来源，不放宽证据标准

- **旁路设计**：开关关闭时，`build_llm_context` 只计算一次决策（立即返回 `need=False`），不调用网络、不加区块、不改提示词语义；`run_pipeline` 不传决策时 trace 不变。
- **触发判定**（策略 §1）：TIME / COVERAGE / CONFLICT 三类信号；`rule/calc/clarify`、高风险、超范围/穷举、用户要求离线、离线模式一律不触发。
- **渠道准入**：A 级双源交叉才可作补充依据；B/C 级仅参考；D 级仅定位；E 级拒绝且 `fetch_official` 不发请求。
- **动作边界**：只作更新 / 补充 / 冲突提示；证据块明确写「不改变知识库结论」「不得据此生成分录、筹划、个案裁定或税额」；单源附「不得作为确定结论或申报依据」。
- **兜底**：`miss/failed` 注入「回落知识库快照 + 以官方原文为准 + 不得把检索失败当作否定证据 + 不得猜测补全」；不把未搜到写成不存在。
- **不变约束**：三重弃答、`ABSTAIN_THRESHOLD`、`OUT_OF_SCOPE_RE`、`UNANSWERABLE_PATTERNS`、意图对齐、角色分诊、确定性计算不走 LLM、逐字法条判定 SOP、隔离项、trust 四层闸门、免责声明全部未改。

## 四、过程中修掉的两个真实准入漏洞（单测抓到）

1. **`gov.cn` 后缀泛匹配**：`host.endswith(".gov.cn")` 会把 `www.chinatax.gov.cn`（B 级）与 `12366.chinatax.gov.cn`（C 级）误判为 A 级官方原文。已改为 `gov.cn` 只做精确匹配（`gov.cn` / `www.gov.cn`），`trust.source_gate()` 同步。
2. **C 级被 B 级规则抢先**：`*.chinatax.gov.cn` 的 B 级泛匹配会先于 12366 的 C 级判定。已把 C 级检查前置。
   另修单测临时库在 Windows 上因 SQLite 连接未关而残留的问题（改用唯一临时目录 + `DROP TABLE IF EXISTS`）。

修复后 `classify_source` 返回 A/B/C/D/E 分级正确，L0 准入把 C 级证据降为线索并提示未达双源。

## 五、验证结果（§6.3 门禁）

### 5.1 默认关闭状态（生产默认）

| 验证 | 结果 |
|---|---|
| 188 题 Golden QA | **Recall@5 1.0 / MRR 0.6836 / 引用 0.6451 / 弃答 1.0 / 角色 1.0 / 规则 0.9468 / 要点 0.9714 / 禁用 1.0 / 未达标 0 题** —— 与 v12 基线逐项一致，**零退化** |
| 冒烟 / 全量 e2e | **19/19**、**73/73** |
| trust 四层 | **24/24** |
| 新增单测 | **37/37** |
| 引用零悬空 | 0 |
| `/api/meta` | v13.0 / 472 条 / 109 规则 / 2026-11-09 |
| `/api/llm-context` | `external.enabled=false`、`decision.need=false`、`status=skipped`、`block=""`；system_prompt 无外部核验区块，快照日期已动态为 2026-11-09 |

### 5.2 开启状态实证（临时打开，验证后已恢复默认关闭）

| 用例 | 结果 |
|---|---|
| 「2027 年这项优惠是否延续」 | `need=True`、4 个信号、`status=miss` → 注入兜底块（含「不得把检索失败当作否定证据」），快照日期正确 |
| 「企业会计准则第30号财务报表列报最新修订」 | `status=hit`、单源证据 → 证据块含 `[外部核验·单源]`、「不改变知识库结论」、单源限制 |
| 「财政部会计司2026年最新政策发布」 | 某源 SSL 握手超时 → `status=failed` → 兜底块生效，主链路不受影响 |
| 精编规则 / 确定性计算 / 超范围 / 用户要求离线 / 无信号 | 全部 `need=False`、`status=skipped`，`mode` 分别为 `rule` / `calc` / `abstain` / `retrieval` / `retrieval` |
| 日志留痕 | `external_lookup_log` 5 行，含 q / need / signals / status / note |

> 检测说明：直接搜 `system_prompt` 里的 `[外部核验·双源]` 字面量会假阳性（第 15 条提示词本身含这两个标记），故在 `external.block` 中直接返回生成的证据/兜底文本用于精确验证。

### 5.3 架构约束保持

- 未引入任何第三方包，仍是 Python 3.12 纯标准库；离线部署默认关闭，行为不变。
- 外部检索仅接入 `build_llm_context()`（`/api/llm-context` 与云端 LLM 生成链路）。`/api/ask` 的本地精编规则 / 确定性计算 / 检索兜底 / 弃答链路**不变**——这是策略 §1.4「精编规则与计算不触发」的刻意设计，避免影响 188 题评测的本地答案文本。

## 六、如何启用

把 `app/config.json` 的 `external_lookup.enabled` 改为 `true` 后重启 `server.py`。建议仅在具备外网访问的环境开启；离线环境保持 `false`。开启后可观测：

- `GET /api/llm-context?q=...` 的 `external` 字段（`decision` / `status` / `sources` / `evidence_count` / `block`）；
- SQLite `external_lookup_log` 表；
- `app/test_external_lookup.py` 可随时离线回归判定与兜底逻辑。

## 七、已知限制（如实标注）

1. 当前抓取的是白名单**栏目/列表页**，能做「是否有新发布、标题关键词是否出现」的线索级核验，**不是逐条法规全文比对**；证据明确标注「仅作更新/补充线索，具体条款须回查原文」。逐条全文层仍按 v10 交接单 §5 的 L0 方案待建。
2. 部分官方站点在沙箱内 SSL 握手超时（已验证走兜底，不影响主链路）；`timeout` 与 `max_retries` 可配置。
3. 单源命中一律标 `[外部核验·单源]`，不作确定结论或申报依据。
4. 双源判定按「≥2 个独立官方域名且均为 A 级」，不做语义级事实一致性比对；硬指标仍需按 `SOURCES-CHANNELS.md` 八步 SOP 人工/后续自动化逐字核对。
5. `external_lookup_log` 是运行时留痕，`enrich_kb.py` 删库重建后需按既有流程导回历史（本轮未清空，5 行验证记录保留）。

## 八、文件清单

**新增**：`app/external_lookup.py`、`app/test_external_lookup.py`、本报告。
**修改**：`app/server.py`、`app/orchestrator.py`、`app/trust.py`、`app/build_v5.py`、`app/config.json`、`README.md`、`knowledge-base/00-index.md`、`knowledge-base/SOURCES-CHANNELS.md`；生成物 `app/finance-tax-compliance.db`（新增日志表）、`reports/eval-report-v5.json`（评测快照）。

## 九、收尾：本机启用 + 别名误判更正（2026-11-09 15:30）

### 9.1 本机启用（不改变仓库默认）

用户要求「全做了」后，采用**本机覆盖**方案，兼顾启用与离线安全：

- `app/config.json` 保持 `external_lookup.enabled = false`（仓库默认，克隆/离线部署不受影响）；
- 新增 `app/config.local.json`（内容 `{"external_lookup":{"enabled":true}}`），已加入 `.gitignore`，**不入库**；
- `server.py` 启动时若发现 `config.local.json` 则按键合并覆盖 `CFG`（仅 dict 做浅合并，解析失败静默忽略）。

这样本机实例（含桌面 `start-qa.bat` 启动的服务）已启用自适应外部核验，而仓库默认值仍是关闭，策略 §6.2「默认关闭」继续成立。README 已写明本机启用方式。

### 9.2 别名构成更正（此前报告有误）

复核 SQLite `alias` 表：`synonym` 29 条（`enrich_kb.py` SYNONYMS）+ `concept_code` 30 条 + `concept_name` 30 条（`build_concepts.py` 写入）= **89 条**，**库中不存在 `short_title` 类型**。

此前 v13 升级报告与交接单 v11 中「历史 60 条短标题别名靠备份保全、重建会掉到 29」的判断有误——那 60 条其实是概念卡别名。`enrich_kb.py` 里「从 title 去书名号生成 short_title」的循环因 `build_kb.py` 早已去掉《》而从未产出记录，属死代码，现已移除并加注释说明。三份文档（v13 升级报告 §八.5、交接单 v11 §4.5/§3.6）已更正；全链重建后 alias 仍为 89 条、无需导回，需导回的只有 `query_log` / `eval_run` / `eval_result` 等运行时留痕。

### 9.3 启用状态下回归（门禁再次全过）

| 验证 | 结果 |
|---|---|
| 188 题 Golden QA（启用状态） | **Recall@5 1.0 / MRR 0.6836 / 引用 0.6451 / 弃答 1.0 / 角色 1.0 / 规则 0.9468 / 要点 0.9714 / 禁用 1.0 / 未达标 0 题** —— 与基线逐项一致 |
| 冒烟 / 全量 e2e | 19/19、73/73 |
| trust / 新单测 | 24/24、37/37 |
| `/api/llm-context` | `enabled=true`；时效问句 `need=True` 并生成兜底块；精编规则与超范围 `need=False / skipped` |
| alias / 引用 | 89 条、零悬空 |
| `/api/meta` | v13.0 / 472 条 / 109 规则 |

### 9.4 上线状态

本地提交 `2339437`（B 落地）与本次收尾提交一并推送到 `origin/main`；推送后工作区干净、`origin/main..main = 0`。`config.local.json` 不入库，因此 GitHub 上的默认配置仍是关闭。

---

*本报告只报验证结果与剩余不确定性；不承诺 100% 准确，法规立改废释频繁，以官方发布原文为准。*
