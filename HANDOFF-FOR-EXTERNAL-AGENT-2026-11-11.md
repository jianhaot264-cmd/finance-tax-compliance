# 财税合规智能体 · 外部协作交接单（2026-11-11）

> 面向：需要基于本项目继续编写代码的外部 Agent（Gemini4 argon 等）。
> 生成：WorkBuddy（本地环境，拥有项目完整文件系统访问权，可直接读写与执行）。
> 用途：校正版本事实、说明 3 项收尾工作的**最新**状态、给出剩余工作的一次性执行方案。
> 本文件即当前基线；`context-handoff-v14-2026-11-10.md` 为上一版历史快照，保留不覆盖。

---

## 0. 先校正截图里的三个事实（重要）

| 截图/来函说法 | 本地实测 |
|---|---|
| 提交 `de0afc9` | **本仓库不存在该对象**（`git cat-file -t de0afc9` → `Not a valid object name`）。`git log` HEAD = **`4e0efd9`**（v15.0），`origin/main` 同步、ahead 0 |
| 「因积分耗尽中断，3 项收尾待完成」 | v15.0 已完整交付并推送；本轮又闭环了其中 **2 项**，目前**只剩 ①** |
| 「当前对话只有截图、未挂载代码文件」 | 代码完整在 `E:\workbuddy-data\finance-tax-compliance\`，**无需上传**；可直接取基线包或读文件 |

> 结论：不要按 `de0afc9` 或「3 项都还没做」来编写代码，会与当前仓库不一致。

## 1. 精确版本与计数（实测）

| 项 | 值 |
|---|---|
| 知识库 | **v15.0** / 472 条 / 56 文件 / A 317 · B1 4 · B2 151 |
| `article_text` | **121 条**（23 文件 37 + L0 原文层 84） |
| L0 corpus | 5 份文档、119 条唯一逐字条文；`business_case` 30 条全 A |
| `verified_at` | 2026-11-09（全库基线；本轮变动条目单条标 2026-11-10/11） |
| 引用 | 329 条，零悬空；alias 89；规则 109 |
| 服务 | `http://localhost:8777`，由计划任务 `TaxQA-Server`（`pythonw.exe` 无控制台）托管；`schtasks /run /tn "TaxQA-Server"` 启动 |

## 2. 三项收尾工作 · 最新状态

| # | 工作 | 状态 | 证据 |
|---|---|---|---|
| ① | L0 补齐剩余 16 个税种 | **2 / 18 完成，剩余 16 部待入**（本轮未虚报完成） | 已入《增值税法》38 条、《增值税法实施条例》54 条；`corpus/IMPORT-BACKLOG.md` 逐项标「待入」 |
| ② | 前端渲染 `answer.business_cases` | **已闭环** | `ux.js` 新增 `businessCasesHTML()` + 幂等增量补挂；`app.js` 云端分支补传 `answer: ctx.fallback`；`polish.css` 加 `.bcx-*`；`app/test_business_deep.py` 9/9 通过 |
| ③ | 业务事项法源精确跳转 | **已闭环** | `business.js` 的 `resolveLawId()`：归一化 + 「第N号 → CAS N」+ 精确/包含匹配 → `window.openDetail(id)`；解析不到才回退关键词检索并 toast 明提示 |

②③ 已不需要再写代码；如需复核，见 §5。

## 3. 剩余 ① 的完整执行方案（可直接运行，不需要重写抓取逻辑）

### 3.1 已具备的工具（都在仓库里）

| 文件 | 作用 |
|---|---|
| `app/fetch_corpus.py` | 双官方源抓取 → 段首拆条 → 条号连续性 → **NFKC 归一化逐条比对** → 全一致才写 corpus md 并登记 manifest；不一致退出码 2、不落盘 |
| `app/batch_import_corpus.py` | **批量驱动器**（本轮新增）：读 `corpus/batch-sources.json`，逐部 dry-run → 写入 → 统一 `import_corpus.py` → 输出 `reports/corpus-batch-report.json`；任一失败不阻断其余 |
| `app/import_corpus.py` | 校验 manifest（双源 ≥2、时效四态、条数、文号唯一、SHA256）→ `corpus-articles.json` |
| `app/build_v5.py` | 把逐字条文写入 SQLite `article_text` |
| `knowledge-base/corpus/IMPORT-BACKLOG.md` | 18 税种进度表、**§五 批量流程**、**§六 16 部检索词表**、验收标准、六类坑位 |

### 3.2 唯一还需要补的：双源 URL 清单

新建 `knowledge-base/corpus/batch-sources.json`：

```json
{
  "documents": [
    {
      "law": "中华人民共和国印花税法",
      "level": "法律",
      "status": "现行有效",
      "effective_date": "2022-07-01",
      "expiry_date": "",
      "doc_no": "",
      "expect": 20,
      "out": "stamp-duty-law-2021.md",
      "url_a": "https://www.gov.cn/...",
      "url_b": "https://fgk.chinatax.gov.cn/...",
      "note": "2021-06-10 通过，2022-07-01 施行"
    }
  ]
}
```

- `expect` 用**官方公布的章条数**，不预估；
- 源 A 优先 `www.gov.cn`，源 B 优先 `fgk.chinatax.gov.cn`；**不用 `big5.` 繁体镜像**，不接受同一站点两个栏目充当双源；
- 每部导入前核实现行性（是否被修订/废止），见 §6。

### 3.3 命令

```bash
cd E:\workbuddy-data\finance-tax-compliance
python app/batch_import_corpus.py --dry-run     # 先看 16 部双源比对结果
python app/batch_import_corpus.py                # 正式写入并统一 import_corpus
python app/build_v5.py                          # article_text 落库
python app/audit_kb.py && python app/build_coverage_matrix.py
```

### 3.4 验收（四项全过才认）

1. 双源逐条一致：条数相同、条号从第一条连续、每条 NFKC 归一化后完全相同；
2. manifest：`sources ≥2`、`article_count` 与实际一致、`status` 属四态；
3. `import_corpus.py` 通过；
4. 全链回归：188 题评测与基线逐项一致、e2e 83/83、引用零悬空。

### 3.5 已知坑位（已在工具中处理，勿重复踩）

| 坑 | 已内置处理 |
|---|---|
| 页脚版权/导航被并入末条 | `PAGE_NOISE` 过滤 + 末条按「施行」句截断 |
| 章节标题并入上一条 | `CHAPTER_HEAD` 跳过 |
| 全角「＋」vs 半角「+」伪差异 | 比对用 `unicodedata.normalize("NFKC", ...)`（只影响比对，不改正文） |
| 条文内「增值税法第三条所称…」被误当新条 | 只认段首「第X条」 |
| 繁体镜像 / 同站双栏目 | 验收规则明确排除 |
| 多行字符串拼接漏换行 | 曾导致 `53.2` 变成 `口径 \|\| 信源 \|`、条目降 B2；替换后务必 `audit_kb.py` 复核 tier |

## 4. 核心文件清单（绝对路径，用户点名的 5 个已含）

| 文件 | 路径 |
|---|---|
| 前端页面 | `E:\workbuddy-data\finance-tax-compliance\app\static\index.html` |
| 后端 | `E:\workbuddy-data\finance-tax-compliance\app\server.py` |
| L0 抓取器 | `E:\workbuddy-data\finance-tax-compliance\app\fetch_corpus.py` |
| 批量驱动器 | `E:\workbuddy-data\finance-tax-compliance\app\batch_import_corpus.py` |
| 回库清单 | `E:\workbuddy-data\finance-tax-compliance\knowledge-base\corpus\IMPORT-BACKLOG.md` |
| 上一版交接单 | `E:\workbuddy-data\finance-tax-compliance\context-handoff-v14-2026-11-10.md` |
| ②③ 相关 | `app\static\ux.js`、`app\static\business.js`、`app\static\app.js`、`app\static\polish.css` |
| 回归 | `app\e2e-test.py`、`app\test_business_deep.py`、`app\eval_kb.py`、`app\test_trust.py` |
| 完整交付包 | `E:\workbuddy-data\finance-tax-compliance\backups\baseline-v15-2026-11-11.zip` |

## 5. ②③ 实现摘要（供复核，无需重写）

**②** `ux.js` 的 `businessCasesHTML(bc)` 把 ≤3 条业务事项渲染成 `<details>` 折叠块，每块 11 字段表格 + 免责 note；挂在 `decorateLastMessage` 的 `if (dp) html += deepHTML(dp)` 之后。云端链路 `app.js` 原先只传 `deep/refs/mode`，本轮补 `answer: ctx.fallback`（`build_llm_context` 用 `ask_local(mode=deep)`，其 fallback 已含 `business_cases`）。另修了 `uxDecorated` 早退导致的竞态：已装饰时允许把后到的 business_cases 增量补挂且不重复。顺带去掉 `ux.js` 写死的「核验日期 2026-11-07」。

**③** `business.js` 的 `resolveLawId(name)`：
1. `normLaw()` 去书名号/「中华人民共和国」前缀/括号年份/标点；
2. 准则类匹配「第N号 → 条目里的 `CAS N`」（如《企业会计准则第14号——收入》→ `38-38.3`）；
3. 依次 `title` 完全相等(100) → `doc_no` 相等(95) → 前缀包含(80) → `heading` 包含(65)；
4. ≥65 分才 `window.openDetail(id)` 精确跳转；否则回退关键词检索并 toast 明提示「未找到精确法源条目」。

实测：点击《企业会计准则第14号——收入》→ 落到 `38-38.3`「收入准则（CAS 14）」，`#kb-search` 为空（未走回退）。

## 6. 已核验事实（不要重新猜，也不要改）

| 事实 | 结论 | 双源 |
|---|---|---|
| 广宣费三类行业 | 财政部 税务总局公告 **2025 年第 16 号**：化妆品制造或销售、医药制造、饮料制造（不含酒类制造）30%，2026-01-01 至 2027-12-31；2020 年第 43 号同日废止；一般企业 15% 出自企税条例第四十四条 | 税务总局政策法规库原文 + 深圳市税务局答复 |
| CAS11 / CAS36 文号 | **财会〔2006〕3号**（2006-02-15、2007-01-01 施行） | 陕西省财政厅会计网 + 中国会计学会 |
| 权益性交易 | **财会函〔2008〕60号**第（三）8 项（**不是**「财会〔2008〕11 号」） | 财政部会计司原文页 + 证监会 2025 年报会计监管报告 |
| 增值税法系 | 《增值税法》38 条（主席令第四十一号，2026-01-01 施行，暂行条例同时废止）；《实施条例》国务院令第 826 号 54 条 | gov.cn + fgk.chinatax.gov.cn |
| 立法状态 | 18 税种中 **14 已立法 / 4 暂行条例**（消费税、土地增值税、房产税、城镇土地使用税），口径见 `44-tax-law-master-matrix.md` | 库内 2026-11-08 核验 |

业务招待费 60%/5‰ 未独立核验，条目仍写「按现行规定限额扣除」，不要顺手补未核数字。

## 7. 重建链与回归门禁

```
build_kb.py → enrich_kb.py → build_concepts.py → import_corpus.py → build_v5.py
→ audit_kb.py → build_coverage_matrix.py → eval_kb.py
```

- **`import_corpus.py` 必须在 `build_v5.py` 之前**；`enrich_kb.py` 会删库重建，之后需从备份导回 `query_log / eval_run / eval_result / external_lookup_log`；alias 自动重建为 89。
- 回归命令：`eval_kb.py`（188 题约 7 分钟）、`e2e-test.py --smoke`（19/19）、`e2e-test.py`（83/83）、`test_business_deep.py`（9/9）、`test_trust.py`（24/24）、`test_external_lookup.py`（37/37）。
- 基线：`reports/eval-report-baseline-2026-11-10-pre-s2s3.json`；当前指标 Recall@5 1.0 / MRR 0.6836 / 引用 0.6451 / 弃答·角色·禁用 1.0 / 未达标 0。

## 8. 关于「把文件给 Gemini4 argon」

WorkBuddy 没有跨 AI 直传通道；文件都在上述本地路径，**完整基线包 `backups\baseline-v15-2026-11-11.zip` 可直接拖给对方**（含代码/知识库/语料/报告/交接单）。若需邮件发送，请给出收件地址（Agent Mail 已连接）。

---

*本交接单只报验证结果与剩余不确定性；不承诺 100% 准确，法规立改废释频繁，结论以官方发布原文为准。*
