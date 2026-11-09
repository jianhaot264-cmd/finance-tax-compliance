# -*- coding: utf-8 -*-
"""enrich_kb.py — 生产级知识库治理与数据库构建（可复现，纯标准库）。

流程：knowledge-base/*.md --build_kb.py--> kb.json --enrich_kb.py--> 增强 kb.json + SQLite + CSV

设计原则（不粉饰、不编造）：
1. 引入 entry_type：regulation / table_row / digest / practice。
   只有 regulation 才要求 10 项法规元数据；汇编/表格型按自身规则校验。
2. 补齐字段只做「从已有正文结构化提取」，绝不猜测文号、机关、日期。
   提取不到则留空并写入 quality_flags，由审计脚本如实统计。
3. 状态治理：汇编型使用第五态「汇编·动态」，不再伪装成「现行有效」。
4. 输出 SQLite（可查询、可导入企业系统）+ CSV 主数据表（UTF-8 BOM）。
"""
import csv
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BASE, ".."))
KB_JSON = os.path.join(BASE, "kb.json")
DB_PATH = os.path.join(BASE, "finance-tax-compliance.db")
CSV_PATH = os.path.join(ROOT, "reports", "regulations-master-2026-11-07.csv")
SERVER = os.path.join(BASE, "server.py")
PENDING = os.path.join(ROOT, "knowledge-base", "PENDING-VERIFICATION.md")
BACKUP = os.path.join(BASE, "kb-pre-enrich-2026-11-07.json")

# ---------------------------------------------------------------- 正则与词表
DOC_NO_PATTERNS = [
    r"国务院令第\s*\d+\s*号", r"主席令第\s*\d+\s*号",
    r"国家税务总局令第\s*\d+\s*号", r"税务总局令第\s*\d+\s*号",
    r"财政部\s*税务总局公告\s*\d{4}\s*年第\s*\d+\s*号",
    r"国家税务总局公告\s*\d{4}\s*年第\s*\d+\s*号",
    r"财政部\s*公告\s*\d{4}\s*年第\s*\d+\s*号",
    r"(?:财税|财库|财关税|国发|国办发|人社部发|粤人社发|粤财税|法释|国税发|工信部联企业|国科发火)〔\d{4}〕\s*\d+\s*号",
    r"国家税务总局令?\s*第?\s*\d+\s*号",
]
DOC_NO_RE = re.compile("|".join(DOC_NO_PATTERNS))
DATE_ISO_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
DATE_CN_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
# 到期日只认「政策有效期」语境（有效期至/延续至/执行至/优惠至…），
# 显式排除「截至/起至/起 止至」——「截至 YYYY-MM-DD」是核验截止语境，不是政策到期。
EXPIRY_STRONG = r"(?:有效期至|延续至|执行至|施行至|优惠至|免征至|减征至|征收至|执行期至|适用至|有效至)"
EXPIRY_RE = re.compile(
    r"(?<![截此起止])" + EXPIRY_STRONG + r"[\s*（(]*(\d{4})-(\d{1,2})-(\d{1,2})|"
    r"(?<![截此起止])" + EXPIRY_STRONG + r"[\s*（(]*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
# 「YYYY-MM-DD 到期 / 届满 / 止」「到期日：YYYY-MM-DD」同样视为政策到期日
EXPIRY_TAIL_RE = re.compile(
    r"(\d{4})-(\d{1,2})-(\d{1,2})[\s*）)]*(?:到期|届满|止|期满)|"
    r"(?:到期日?|有效期截止|截止日?)[：:][\s*（(]*(\d{4})-(\d{1,2})-(\d{1,2})|"
    r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日[\s*）)]*(?:到期|届满|止)")
URL_RE = re.compile(r"https?://[^\s|)>）\]\"']+")

DIGEST_WORDS = ("清单", "汇编", "对照", "速查", "全景", "动态", "矩阵", "日历",
                "自查", "索引", "地图", "SOP", "渠道", "版本日志", "沿革", "覆盖矩阵",
                "提示", "边界", "问答示例", "专题", "合计", "统计", "节点", "衔接",
                "配套", "落地", "对应关系", "附：", "关系", "适用衔接", "改革节点",
                "政策文件（", "重点优惠", "对应关系")
VALID_STATUS = {"现行有效", "已废止", "修订中", "草案阶段"}
ASSEMBLY_STATUS = "汇编·动态"

# v6.0：解释层条目按自身模板校验，不套用「单一法规 10 字段」标准
EXPLAIN_TYPES = {
    "25": ("concept", ("概念编号", "概念类别", "定义", "定义辨析", "因果逻辑", "适用条件",
                     "边界条件与例外", "易混淆点", "局限说明", "常见场景", "关联条目",
                     "关联概念", "主要依据", "时效性", "信源", "核验")),
    "26": ("relation", ("时效性", "适用范围", "核心条款", "合规要点", "信源", "核验")),
    "27": ("scenario", ("适用场景", "适用主体", "判断路径", "必须核验", "边界与例外",
                       "易错结论", "应弃答或转介", "关联概念", "关联条目", "时效性", "信源", "核验")),
    "28": ("verification", ("时效性", "适用范围", "核验动作", "核心条款", "合规要点",
                           "影响条目", "处理状态", "信源", "核验")),
}

# v13.0：业务事项结构化条目（51–56 收入/资产/费用/税费/往来/期末结转）。
# 按自身 11 字段模板校验，不套用「单一法规十字段」标准，避免把实务指引
# 误判为缺文号/缺发文机关的法规型条目。
BUSINESS_CASE_FIELDS = (
    "适用范围", "确认与计量要求", "会计分录与处理流程", "税务处理规定",
    "税会差异提示", "参照依据与关键条款", "依据层级", "生效状态",
    "适用边界", "信源", "核验",
)
for _pfx in ("51", "52", "53", "54", "55", "56"):
    EXPLAIN_TYPES[_pfx] = ("business_case", BUSINESS_CASE_FIELDS)

# 简称 / 同义词（生产检索用，前端已有一份，此处为权威主表）
SYNONYMS = {
    "残保金": "残疾人就业保障金", "数电票": "全面数字化的电子发票",
    "全电发票": "全面数字化的电子发票", "个税": "个人所得税",
    "企税": "企业所得税", "社保": "社会保险", "社保费": "社会保险费",
    "小微": "小型微利企业", "小微企业": "小型微利企业",
    "小规模": "小规模纳税人", "六税两费": "六税两费减半征收",
    "征管法": "中华人民共和国税收征收管理法",
    "增值税法": "中华人民共和国增值税法",
    "发票办法": "中华人民共和国发票管理办法",
    "企税法": "中华人民共和国企业所得税法",
    "个税法": "中华人民共和国个人所得税法",
    "裁量基准": "全国税务行政处罚裁量基准",
    "首违不罚": "税务行政处罚首违不罚事项清单",
    "加计抵减": "先进制造业企业增值税加计抵减",
    "留抵退税": "增值税期末留抵退税",
    "汇算": "汇算清缴", "稳岗返还": "失业保险稳岗返还",
    "南沙15%": "广州南沙企业所得税优惠",
    "前海15%": "前海深港现代服务业合作区企业所得税优惠",
    "横琴15%": "横琴粤澳深度合作区企业所得税优惠",
    "大湾区个税": "粤港澳大湾区个人所得税优惠",
    "810号令": "互联网平台企业涉税信息报送规定",
    "43号公告": "先进制造业企业增值税加计抵减",
    "7号公告": "完善增值税期末留抵退税政策",
}


def norm_date(m):
    if m.group(1) and m.group(2) and m.group(3):
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def extract_dates(text):
    """从正文抽取最早日期（施行日）与到期日，只做结构化提取，不推断。"""
    eff, exp = "", ""
    m = EXPIRY_RE.search(text)
    if m:
        g = m.groups()
        if g[0]:
            exp = f"{int(g[0]):04d}-{int(g[1]):02d}-{int(g[2]):02d}"
        elif g[3]:
            exp = f"{int(g[3]):04d}-{int(g[4]):02d}-{int(g[5]):02d}"
    if not exp:
        m2 = EXPIRY_TAIL_RE.search(text)
        if m2:
            g = m2.groups()
            for i in (0, 3, 6):
                if g[i]:
                    exp = f"{int(g[i]):04d}-{int(g[i+1]):02d}-{int(g[i+2]):02d}"
                    break
    # 施行日：优先「YYYY-MM-DD 施行」上下文
    for mm in re.finditer(r"(\d{4}-\d{1,2}-\d{1,2})\s*(?:起)?(?:施行|生效|执行|起执行)", text):
        d = norm_date(DATE_ISO_RE.search(mm.group(1)))
        if d:
            eff = d
            break
    if not eff:
        for mm in re.finditer(r"(?:自|于)?\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(?:起)?(?:施行|生效|执行)", text):
            eff = f"{int(mm.group(1)):04d}-{int(mm.group(2)):02d}-{int(mm.group(3)):02d}"
            break
    return eff, exp


def classify(e):
    """判定条目类型：不把汇编型伪装成单一法规。

    注意：e['no'] 是条目编号（如 1.5），不是法条文号，绝不可用于判定。
    """
    f = e.get("fields", {})
    title = e.get("title", "")
    file = e.get("file", "")
    if file in EXPLAIN_TYPES:
        return EXPLAIN_TYPES[file][0]  # v6 解释层：concept / relation / scenario / verification
    if file == "06":
        return "table_row"
    if any(w in title for w in DIGEST_WORDS):
        return "digest"
    if f.get("文号") or f.get("主要依据"):
        return "regulation"
    # 有法规元数据特征 → 法规型（缺项如实记录）
    if any(k in f for k in ("时效性", "生效状态", "发文机关", "效力层级", "核心条款")):
        return "regulation"
    # 早期表格/清单型条目：正文含多个法规名且无单一文号 → 汇编型
    body = e.get("body_md", "") or ""
    if body.count("《") >= 3 and not f.get("文号"):
        return "digest"
    return "practice"


def pick(f, *keys):
    for k in keys:
        v = f.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def main():
    with open(KB_JSON, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    entries = data["entries"]

    if not os.path.exists(BACKUP):
        shutil.copy2(KB_JSON, BACKUP)

    enriched = []
    for e in entries:
        f = e.get("fields", {})
        body = e.get("body_md", "") or ""
        blob = " ".join([e.get("title", ""), e.get("heading", ""), body,
                         json.dumps(f, ensure_ascii=False)])

        etype = classify(e)
        # 结构化字段：优先字段表，其次从正文提取文号（不猜测）
        doc_no = pick(f, "文号", "主要依据")
        if not doc_no:
            m = DOC_NO_RE.search(blob)
            if m:
                doc_no = m.group(0).strip()
                f.setdefault("_derived_doc_no", doc_no)
        issuer = pick(f, "发文机关")
        level = pick(f, "效力层级")
        pub = pick(f, "公布/施行", "公布施行", "公布施行日期")
        scope = pick(f, "适用范围", "适用条件", "适用主体")
        core = pick(f, "核心条款", "核心义务/优惠", "主要内容")
        comp = pick(f, "合规要点", "风险提示")
        src_text = pick(f, "信源", "官方信源")
        sources = URL_RE.findall(src_text) or URL_RE.findall(blob)
        # 去重保序
        seen, srcs = set(), []
        for u in sources:
            u = u.rstrip(".,;；。")
            if u not in seen:
                seen.add(u)
                srcs.append(u)
        # 到期日只信「显式字段」或「时效性/核心条款」语境，不扫整篇正文——
        # 正文常引用其他文件的到期日（历史文件/对照表），会污染本条目时效判定。
        exp = ""
        exp_field = pick(f, "到期日", "有效期", "执行期限", "执行期")
        if exp_field:
            mm = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", exp_field) or DATE_CN_RE.search(exp_field)
            if mm:
                exp = f"{int(mm.group(1)):04d}-{int(mm.group(2)):02d}-{int(mm.group(3)):02d}"
        if not exp:
            scoped = " ".join([e.get("title", ""),
                               pick(f, "时效性", ""), pick(f, "核心条款", ""),
                               pick(f, "核心义务/优惠", ""), pick(f, "主要内容", "")])
            _, exp = extract_dates(scoped)
        eff, _ = extract_dates(blob[:600])   # 施行日仍可从正文头部取
        if not eff:
            eff, _ = extract_dates(blob)

        status = e.get("status", "") or ""
        status_norm = status if status in (VALID_STATUS | {ASSEMBLY_STATUS}) else ""
        if not status_norm:
            if etype in ("table_row", "digest", "relation", "scenario", "verification"):
                status_norm = ASSEMBLY_STATUS
            elif "现行有效" in blob:
                status_norm = "现行有效"
            elif "草案" in blob or "征求意见" in blob:
                status_norm = "草案阶段"
            elif "已废止" in blob or "已到期" in blob:
                status_norm = "已废止"
            elif etype in ("regulation", "practice", "concept"):
                # 无法判定单一法规时效 → 明确标为汇编动态，不伪装成现行有效
                status_norm = ASSEMBLY_STATUS

        # v6：解释层按自身模板校验，不把「无单一文号 / 无发文机关」误报为数据缺陷
        explain = EXPLAIN_TYPES.get(e.get("file", ""))
        if explain:
            required = explain[1]
            missing = [k for k in required if not str(f.get(k, "")).strip()]
            flags = ["missing_explain_field:" + k for k in missing]
            if not src_text and not srcs:
                flags.append("missing_source")
            elif len(srcs) < 2:
                flags.append("missing_dual_source")
            if not status_norm:
                flags.append("status_unlabeled")
            fields_blob = json.dumps(f, ensure_ascii=False)
            if re.search(r"待核验|凭既有知识|待复核|文号待", fields_blob):
                flags.append("pending_field")
            tier = "A" if (not flags and len(srcs) >= 2 and
                           status_norm in (VALID_STATUS | {ASSEMBLY_STATUS})) else "B2"
            concept_complete = not missing
        else:
            flags = []
            if not doc_no:
                flags.append("missing_doc_no")
            if not issuer:
                flags.append("missing_issuer")
            if not level:
                flags.append("missing_level")
            if not pub and not eff:
                flags.append("missing_dates")
            if not scope:
                flags.append("missing_scope")
            # 区分「有信源描述但无 URL」与「完全无信源」：两者风险不同
            if not src_text and not srcs:
                flags.append("missing_source")
            elif src_text and not srcs:
                flags.append("missing_source_url")
            if len(srcs) == 1:
                flags.append("single_source")
            if not status_norm:
                flags.append("status_unlabeled")
            # 只检查字段值中的待核验标注；正文里「订正/清零」等描述性字样不算
            fields_blob = json.dumps(f, ensure_ascii=False)
            if re.search(r"待核验|凭既有知识|待复核|文号待", fields_blob):
                flags.append("pending_field")

            # tier：A = 法规型 + 10 字段齐 + 双源 + 四态；B1 = 法规型元数据齐单源；B2 = 其余
            full = all([doc_no, issuer, level, (pub or eff), scope, core, comp, srcs])
            if etype == "regulation" and full and len(srcs) >= 2 and status_norm in VALID_STATUS:
                tier = "A"
            elif etype == "regulation" and not flags:
                tier = "B1"
            else:
                tier = "B2"
            concept_complete = None

        out = dict(e)
        out["concept_complete"] = concept_complete
        out.update({
            "entry_type": etype,
            "tier": tier,
            "doc_no": doc_no,
            "issuer": issuer,
            "level": level,
            "publish_date": pub,
            "effective_date": eff,
            "expiry_date": exp,
            "status": status_norm or status,
            "status_norm": status_norm,
            "scope": scope,
            "core_clauses": core,
            "compliance_points": comp,
            "sources": srcs,
            "source_text": src_text,
            "source_count": len(srcs),
            "verified_at": pick(f, "核验") or data.get("verified_at", ""),
            "quality_flags": flags,
        })
        enriched.append(out)

    data["entries"] = enriched
    data["enriched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["enrichment_version"] = "1.0"
    data["entry_types"] = sorted({e["entry_type"] for e in enriched})
    data["tiers"] = {t: sum(1 for e in enriched if e["tier"] == t)
                     for t in ("A", "B1", "B2")}
    with open(KB_JSON, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=1)

    # ---------------------------------------------------------------- SQLite
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    cur = con.cursor()
    cur.execute("""CREATE TABLE regulation (
        id TEXT PRIMARY KEY, entry_type TEXT NOT NULL, tier TEXT NOT NULL,
        title TEXT NOT NULL, doc_no TEXT, issuer TEXT, level TEXT,
        publish_date TEXT, effective_date TEXT, expiry_date TEXT,
        status TEXT, status_norm TEXT, scope TEXT, core_clauses TEXT,
        compliance_points TEXT, category TEXT, source_file TEXT,
        sources TEXT, source_text TEXT, source_count INTEGER, verified_at TEXT,
        body_md TEXT, search_text TEXT, quality_flags TEXT)""")
    for e in enriched:
        cur.execute("""INSERT INTO regulation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            e["id"], e["entry_type"], e["tier"], e["title"], e["doc_no"], e["issuer"],
            e["level"], e["publish_date"], e["effective_date"], e["expiry_date"],
            e["status"], e["status_norm"], e["scope"], e["core_clauses"],
            e["compliance_points"], e.get("category", ""), e.get("source_file", ""),
            json.dumps(e["sources"], ensure_ascii=False), e["source_text"], e["source_count"],
            e["verified_at"], e.get("body_md", ""), e.get("search_text", ""),
            json.dumps(e["quality_flags"], ensure_ascii=False)))

    cur.execute("CREATE TABLE alias (alias TEXT NOT NULL, target TEXT NOT NULL, kind TEXT, "
                "PRIMARY KEY(alias, target))")
    for a, t in SYNONYMS.items():
        cur.execute("INSERT OR IGNORE INTO alias VALUES (?,?,?)", (a, t, "synonym"))
    # 从标题自动生成简称（去掉书引号与前缀）
    for e in enriched:
        t = e["title"].strip()
        short = re.sub(r"^《|》$", "", t)
        if short and short != t:
            cur.execute("INSERT OR IGNORE INTO alias VALUES (?,?,?)", (short, t, "short_title"))

    cur.execute("CREATE TABLE rule_reference (rule_id TEXT NOT NULL, regulation_id TEXT NOT NULL, "
                "PRIMARY KEY(rule_id, regulation_id))")
    if os.path.exists(SERVER):
        valid_ids = {e["id"] for e in enriched}
        rules = None
        try:
            # 权威来源：直接导入 server.RULES（正则跨块匹配会漏记与错配，v7 起改用导入）
            sys.path.insert(0, BASE)
            import server as _srv  # noqa
            rules = _srv.RULES
        except Exception as exc:  # 导入失败时回退正则，并打印告警
            print("  [warn] 导入 server.RULES 失败，回退正则提取:", exc)
        if rules:
            for r in rules:
                rid = r.get("id")
                for ref in (r.get("refs") or []):
                    if rid and ref in valid_ids:
                        cur.execute("INSERT OR IGNORE INTO rule_reference VALUES (?,?)", (rid, ref))
        else:
            src = open(SERVER, encoding="utf-8").read()
            for block in re.findall(r'\{\s*"id":\s*"([a-z0-9-]+)".*?"refs":\s*\[(.*?)\]', src, re.S):
                rid, refblock = block
                for ref in re.findall(r'"(\d{2}-[\d.\-]+)"', refblock):
                    if ref in valid_ids:
                        cur.execute("INSERT OR IGNORE INTO rule_reference VALUES (?,?)", (rid, ref))

    cur.execute("""CREATE TABLE pending_item (
        code TEXT PRIMARY KEY, state TEXT, location TEXT, content TEXT, risk TEXT, action TEXT)""")
    cur.execute("INSERT INTO pending_item VALUES (?,?,?,?,?,?)", (
        "P-05b", "RESOLVED", "05-5.6 / 06-2 / 41-41.2",
        "前海 15% 企业所得税优惠 2027 年是否延续（原名「2026 年是否延续」）",
        "已延续：财税〔2026〕3 号，执行期延长至 2027-12-31，条件不变（鼓励类目录 + 收入占比 60% + 实质性运营）",
        "可按 15% 测算 2027 年度；到期前 90 天由政策雷达再次提醒"))
    cur.execute("INSERT INTO pending_item VALUES (?,?,?,?,?,?)", (
        "P-06b", "BLOCKED", "05-5.7",
        "广东省工伤保险条例修订状态、省级非税收入管理规定、地市级税费征管保障办法、省级社保自行申报统一公告",
        "地方细则分散，本轮未取得可双源核验的官方原文",
        "涉及个案时按 SOURCES-CHANNELS.md SOP 回查广东人大网/省财政厅/省人社厅"))
    cur.execute("INSERT INTO pending_item VALUES (?,?,?,?,?,?)", (
        "P-10b", "SCOPE", "08 / 21-21.4",
        "差额征税、简易计税逐项目清单在 2026 年增值税法施行后的配套衔接",
        "属项目级清单，未逐项核验，不写入结论",
        "生产系统不得硬编码旧项目表；按官方现行目录逐项回查"))
    cur.execute("INSERT INTO pending_item VALUES (?,?,?,?,?,?)", (
        "P-23", "SCOPE", "37-37.5 / 42-42.10",
        "逐国协定限制税率：港澳新日德美越 7 地已逐条回库（42 文件），其余 100 余个协定未逐条收录",
        "七地之外仍属覆盖范围边界，禁止凭印象报数",
        "查 42-42.10 三步法：协定一览表 → 协定原文第十/十一/十二条 → 议定书/MLI"))
    cur.execute("INSERT INTO pending_item VALUES (?,?,?,?,?,?)", (
        "P-24", "EXPIRING", "41-41.1 / 20-20.16",
        "南沙先行启动区 15% 企业所得税执行至 2026-12-31，2027 年是否延续未见文件",
        "若未延续，南沙企业 2027 年税负由 15% 跳至 25%",
        "2026Q4 前复核财政部/广东省文件；未确认前不得按 15% 测算 2027 年度"))

    cur.execute("""CREATE TABLE change_log (ts TEXT, version TEXT, note TEXT)""")
    changes = [
        ("2026-11-06", "v4.0", "隔离项 16 项复核：14 项闭环/归档，2 项仍阻断"),
        ("2026-11-06", "v4.0", "重大订正：稳岗返还 2026 已延续（人社部发〔2026〕39 号）"),
        ("2026-11-06", "v4.0", "重大订正：先进制造业加计抵减 5% 主文件＝2023 年第 43 号"),
        ("2026-11-06", "v4.0", "新增 20/21/22 三个 A 层主题文件"),
        ("2026-11-06", "v4.0", "建立 entry_type 数据模型与 A/B1/B2 三层质量分级"),
        ("2026-11-06", "v4.0", "构建 SQLite 生产数据库与 CSV 主数据表"),
        ("2026-11-07", "v5.0", "权威库回库核验 37 条逐字法条；五路召回 + 五阶段编排 + 100 题量化评测"),
        ("2026-11-07", "v6.0", "新增概念解读层：30 张概念卡、8 张关系边界卡、14 张场景卡、10 条权威定论"),
        ("2026-11-07", "v6.0", "解释层按 concept/relation/scenario/verification 四类分型建模，不套用单一法规元数据标准"),
        ("2026-11-07", "v6.0", "权威二次核验：17 条法条回库 + 官网双源；订正广宣费 2020 年第 43 号已废止等口径"),
        ("2026-11-07", "v7.0", "P0 补库：增值税计税方法、社保分险种、非税逐项、消费税税率、土增房产广东、出口退税（29–34）"),
        ("2026-11-07", "v8.0", "P1 补库：数电票、复议诉讼、协定网络、会计准则、行业专项（35–39）"),
        ("2026-11-07", "v9.0", "P2 机制：立法跟踪、到期预警、到期雷达脚本、评测 165 题、规则 94→98"),
        ("2026-11-07", "v10.0", "P3 补库：逐国协定税率 7 地（42）、会计准则进阶 CAS22-24/2/33（43）；规则 98→100；新增月度政策雷达"),
        ("2026-11-07", "v10.0", "P-05b 由 BLOCKED 改为 RESOLVED（财税〔2026〕3 号延至 2027-12-31）；P-23 细分为「七地已回库 + 其余 SCOPE」"),
        ("2026-11-08", "v11.0", "全税种复盘：新增 44 税种层级总表、45 小税种、46 征管程序、47 操作空间、48 指导文件；规则 100→102；新增覆盖矩阵 CSV"),
    ]
    cur.executemany("INSERT INTO change_log VALUES (?,?,?)", changes)

    cur.execute("CREATE TABLE kb_meta (key TEXT PRIMARY KEY, value TEXT)")
    meta = {
        "kb_version": data.get("kb_version", ""), "verified_at": data.get("verified_at", ""),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "entries": str(len(enriched)), "files": str(len(data.get("files", []))),
        "tier_A": str(data["tiers"]["A"]), "tier_B1": str(data["tiers"]["B1"]),
        "tier_B2": str(data["tiers"]["B2"]),
        "source_of_truth": "knowledge-base/*.md -> build_kb.py -> enrich_kb.py",
    }
    cur.executemany("INSERT INTO kb_meta VALUES (?,?)", meta.items())

    try:
        # trigram 分词：中文按 3 字子串索引，避免 unicode61 把整句当单 token 导致中文检索失效
        cur.execute("""CREATE VIRTUAL TABLE regulation_fts USING fts5(
            id UNINDEXED, title, doc_no, scope, core_clauses, compliance_points, search_text,
            content='regulation', content_rowid='rowid', tokenize='trigram')""")
        cur.execute("""INSERT INTO regulation_fts(rowid,id,title,doc_no,scope,core_clauses,
            compliance_points,search_text) SELECT rowid,id,title,doc_no,scope,core_clauses,
            compliance_points,search_text FROM regulation""")
    except sqlite3.OperationalError as ex:
        print(f"[warn] FTS5 不可用，跳过全文索引：{ex}")

    cur.execute("""CREATE VIEW v_current_law AS SELECT id,title,doc_no,issuer,level,
        effective_date,expiry_date,status,tier,source_count,category FROM regulation
        WHERE entry_type='regulation' AND status_norm IN ('现行有效','修订中','草案阶段')""")
    cur.execute("""CREATE VIEW v_verified_a AS SELECT * FROM regulation WHERE tier='A'""")
    cur.execute("""CREATE VIEW v_expiring AS SELECT id,title,doc_no,expiry_date,status FROM regulation
        WHERE expiry_date<>'' ORDER BY expiry_date""")
    con.commit()

    # ---------------------------------------------------------------- CSV
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    cols = ["id", "entry_type", "tier", "title", "doc_no", "issuer", "level",
            "publish_date", "effective_date", "expiry_date", "status", "scope",
            "category", "source_file", "source_count", "sources", "source_text", "verified_at",
            "core_clauses", "compliance_points", "quality_flags"]
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for e in enriched:
            row = dict(e)
            row["sources"] = " | ".join(e["sources"])
            row["quality_flags"] = " | ".join(e["quality_flags"])
            w.writerow(row)

    n_alias = con.execute("SELECT COUNT(*) FROM alias").fetchone()[0]
    n_ref = con.execute("SELECT COUNT(*) FROM rule_reference").fetchone()[0]
    con.close()

    print("=== 治理摘要 ===")
    print("  条目总数:", len(enriched))
    print("  条目类型:", {t: sum(1 for e in enriched if e["entry_type"] == t) for t in data["entry_types"]})
    print("  质量分层:", data["tiers"])
    print("  状态有效:", sum(1 for e in enriched if e["status_norm"]))
    print("  双源条目:", sum(1 for e in enriched if e["source_count"] >= 2))
    print("  别名映射:", n_alias, "| 规则引用:", n_ref)
    print("  输出:", DB_PATH)
    print("  输出:", CSV_PATH)
    print("  备份:", BACKUP)


if __name__ == "__main__":
    main()
