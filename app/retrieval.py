# -*- coding: utf-8 -*-
"""retrieval.py — 生产级检索内核（纯标准库，零第三方依赖）。

对齐 production RAG 的四层做法：
  1) Query 理解：同义词扩展、文号归一、数字门槛抽取
  2) 多路召回：BM25 全字段 / BM25 标题 / 精确文号关键词 / SQLite FTS5 trigram
  3) RRF 融合 + 可解释重排（层级、时效、tier、精确文号、数字命中）
  4) 置信度校准与弃答（abstention），全链路 trace 可留痕

同时保留 legacy 模式（复刻 server.score_entry），供 eval_kb.py 做真实前后对比。
本模块不导入 server，避免循环依赖。
"""
import json
import math
import os
import re
import sqlite3
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "finance-tax-compliance.db")
KB_PATH = os.path.join(BASE, "kb.json")

STOP = set("什么多少怎么怎样可以需要公司企业请问一下了吗是否规定标准条件时间多久哪些是不是有没有以及关于进行如何应该怎么办呢吗的了吗")
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
NUM_RE = re.compile(r"\d+(?:\.\d+)?%?|\d+万|\d+元|\d+年")
RRF_K = 60
ABSTAIN_THRESHOLD = 0.45
# 可行性判断：这类提问超出「法规检索问答」能力边界，应弃答而非硬答
UNANSWERABLE_PATTERNS = [
    r"逐一|逐国|逐条列出|穷举|全部\s*\d+\s*个[^。]{0,12}条款",
    r"精确计算[^。]{0,12}(到分|到元)|不给[^。]{0,8}数据|没有[^。]{0,8}数据|无任何[^。]{0,6}数据",
]

# 内置兜底同义词；运行时会与数据库 alias 表合并
BUILTIN_ALIAS = {
    "残保金": "残疾人就业保障金", "数电票": "全面数字化的电子发票",
    "个税": "个人所得税", "企税": "企业所得税", "社保": "社会保险",
    "小微": "小型微利企业", "小规模": "小规模纳税人",
    "征管法": "中华人民共和国税收征收管理法",
    "增值税法": "中华人民共和国增值税法",
    "发票办法": "中华人民共和国发票管理办法",
    "裁量基准": "全国税务行政处罚裁量基准",
    "首违不罚": "税务行政处罚首违不罚事项清单",
    "留抵退税": "增值税期末留抵退税", "汇算": "汇算清缴",
    "稳岗返还": "失业保险稳岗返还", "年终奖": "全年一次性奖金",
    "教育经费": "职工教育经费", "清税前置": "纳税争议清税前置",
    "专项附加": "专项附加扣除", "婴幼儿照护": "3岁以下婴幼儿照护",
    "追溯": "追征", "育儿补贴": "育儿补贴免征个人所得税",
    "扣除比例": "税前扣除比例", "背靠背": "款项支付 背靠背",
}

# 逐国协定税率已回库的 7 个法域（42 文件）：单一法域问句优先命中对应条目
JURISDICTIONS = ("香港", "澳门", "新加坡", "日本", "德国", "美国", "越南")


def tokenize(text):
    """中文 bigram + trigram + 单字 + 数字/文号原串。"""
    text = str(text or "").lower()
    toks = []
    for m in re.finditer(r"\d+(?:\.\d+)?%?|[a-z]{2,}", text):
        toks.append(m.group(0))
    han = "".join(HAN_RE.findall(text))
    for i in range(len(han)):
        if han[i] not in STOP:
            toks.append(han[i])
        if i + 1 < len(han):
            toks.append(han[i:i + 2])
        if i + 2 < len(han):
            toks.append(han[i:i + 3])
    return toks


class BM25:
    def __init__(self, docs):
        # docs: [(id, tokens)]
        self.docs = docs
        self.N = max(1, len(docs))
        self.tf, self.dl, self.df = [], [], Counter()
        for _, toks in docs:
            c = Counter(toks)
            self.tf.append(c)
            self.dl.append(len(toks))
            for t in c:
                self.df[t] += 1
        self.avgdl = sum(self.dl) / self.N
        self.k1, self.b = 1.5, 0.75

    def search(self, qtoks, limit=40):
        scores = defaultdict(float)
        qc = Counter(qtoks)
        for t, qtf in qc.items():
            if t not in self.df or len(t) > 12:
                continue
            idf = math.log(1 + (self.N - self.df[t] + 0.5) / (self.df[t] + 0.5))
            for i, (did, _) in enumerate(self.docs):
                f = self.tf[i].get(t, 0)
                if not f:
                    continue
                norm = 1 - self.b + self.b * self.dl[i] / max(1.0, self.avgdl)
                scores[did] += idf * (f * (self.k1 + 1)) / (f + self.k1 * norm) * min(qtf, 2)
        return sorted(scores.items(), key=lambda x: -x[1])[:limit]


class Retriever:
    def __init__(self, entries=None, db_path=DB_PATH):
        if entries is None:
            with open(KB_PATH, "r", encoding="utf-8") as f:
                entries = json.load(f)["entries"]
        self.entries = entries
        # v13.0：业务事项层走独立检索通道，不参与法规主检索的 IDF / RRF，
        # 避免新增语料扰动既有评测基线（扩容后排序漂移已实测）。
        self.main_entries = [e for e in entries if e.get("entry_type") != "business_case"]
        self.business_entries = [e for e in entries if e.get("entry_type") == "business_case"]
        self.main_ids = {e["id"] for e in self.main_entries}
        self.by_id = {e["id"]: e for e in entries}
        self.alias = self._load_alias(db_path)
        self.db_path = db_path
        self._build_index()

    def _load_alias(self, db_path):
        a = dict(BUILTIN_ALIAS)
        if os.path.exists(db_path):
            try:
                con = sqlite3.connect(db_path)
                for k, v in con.execute("SELECT alias,target FROM alias"):
                    a.setdefault(k, v)
                con.close()
            except sqlite3.Error:
                pass
        return a

    def _doc_text(self, e, title_only=False):
        if title_only:
            return " ".join([e.get("title", "")] * 3 +
                            [e.get("heading", ""), e.get("doc_no", "")])
        return " ".join([
            e.get("title", "") * 3,
            e.get("heading", "") * 2,
            e.get("doc_no", "") * 2,
            e.get("issuer", ""), e.get("scope", ""),
            e.get("core_clauses", ""), e.get("compliance_points", ""),
            (e.get("search_text", "") or "")[:900],
        ])

    def _build_index(self):
        m = self.main_entries
        self.bm25_all = BM25([(e["id"], tokenize(self._doc_text(e))) for e in m])
        self.bm25_title = BM25([(e["id"], tokenize(self._doc_text(e, True))) for e in m])
        self.bm25_business = BM25([(e["id"], tokenize(self._doc_text(e)))
                                   for e in self.business_entries])

    # ---------------- Query 理解 ----------------
    def expand_query(self, q):
        terms = [q]
        # 中文日期归一化：「2027 年 12 月 31 日」→「2027-12-31」，与条目内的 ISO 日期对齐
        def _norm_date(m):
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return f"{y:04d}-{mo:02d}-{d:02d}"
        q_norm = re.sub(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", _norm_date, q)
        if q_norm != q:
            terms.append(q_norm)
        for short, full in self.alias.items():
            if short in q and full not in q:
                terms.append(full)
        numbers = NUM_RE.findall(q)
        # 去停用词后的检索词（保留原串用于精确匹配）
        return {"original": q, "terms": list(dict.fromkeys(terms)), "numbers": numbers}

    # ---------------- 四路召回 ----------------
    def _recall_exact(self, q, ex, limit=40):
        out = []
        for e in self.main_entries:
            blob = " ".join([e.get("title", ""), e.get("doc_no", ""),
                             e.get("core_clauses", ""), e.get("search_text", "")[:500]])
            s = 0.0
            for t in ex["terms"]:
                if t and t in blob:
                    s += 2.0 if t in (e.get("doc_no", "") or "") else 1.0
            for n in ex["numbers"]:
                if n in blob:
                    s += 0.8
            if s > 0:
                out.append((e["id"], s))
        return sorted(out, key=lambda x: -x[1])[:limit]

    def _recall_gram(self, q, limit=40):
        """第五路：字面 bigram/trigram 信号（legacy 强项，作为 RRF 一路并入）。"""
        out = [(e["id"], float(self._legacy_gram_score(q, e))) for e in self.main_entries]
        out = [x for x in out if x[1] > 0]
        return sorted(out, key=lambda x: -x[1])[:limit]

    def _recall_fts(self, q, limit=40):
        if not os.path.exists(self.db_path):
            return []
        try:
            con = sqlite3.connect(self.db_path)
            # trigram 需 >=3 字符；用引号包裹避免 FTS5 语法错误
            rows = con.execute(
                "SELECT id FROM regulation_fts WHERE regulation_fts MATCH ? LIMIT ?",
                ('"' + q.replace('"', '""') + '"', limit)).fetchall()
            con.close()
            return [(r[0], 1.0 - i * 0.005) for i, r in enumerate(rows)
                    if r[0] in self.main_ids]
        except sqlite3.Error:
            return []

    def _rrf(self, lists):
        scores = defaultdict(float)
        for lst in lists:
            for rank, (eid, _) in enumerate(lst[:40], start=1):
                scores[eid] += 1.0 / (RRF_K + rank)
        return scores

    # ---------------- 可解释重排 ----------------
    def _rerank(self, q, ex, eid, rrf_score, rank_norm):
        e = self.by_id[eid]
        title = e.get("title", "")
        doc_no = e.get("doc_no", "") or ""
        blob = " ".join([title, doc_no, e.get("core_clauses", ""),
                         e.get("compliance_points", ""), e.get("search_text", "")[:900]])
        qh = "".join(HAN_RE.findall(q))
        cover = sum(1 for c in set(qh) if c in title) / max(1, len(set(qh)))

        f = {}
        f["rrf"] = round(rank_norm, 4)
        f["exact_term"] = 0.30 if any(t in blob for t in ex["terms"] if len(t) >= 3) else 0.0
        f["exact_doc_no"] = 0.35 if any(t in doc_no for t in ex["terms"] if len(t) >= 4) else 0.0
        f["title_cover"] = round(cover, 3)
        f["numeric"] = 0.10 if any(n in blob for n in ex["numbers"]) else 0.0
        tier = e.get("tier", "B2")
        f["tier"] = {"A": 0.14, "B1": 0.06, "B2": 0.0}.get(tier, 0.0)
        st = e.get("status", "") or e.get("status_norm", "")
        f["status"] = (0.06 if st == "现行有效" else
                       -0.30 if st == "已废止" else
                       -0.14 if st == "草案阶段" else
                       -0.04 if st == "汇编·动态" else 0.0)
        f["dual_source"] = 0.05 if e.get("source_count", 0) >= 2 else 0.0
        f["entry_type"] = {"regulation": 0.04, "practice": 0.0,
                           "digest": -0.02, "table_row": -0.04}.get(e.get("entry_type", ""), 0.0)
        f["pending"] = -0.18 if "pending" in " ".join(e.get("quality_flags", [])) else 0.0
        # 单一法域问句（如「澳门公司取得利息」）优先命中该国/地区条目：
        # 仅当问句只出现一个法域、且该法域在标题中时加分，避免多国对比题被单个国家条目抢位。
        q_juris = [j for j in JURISDICTIONS if j in q]
        f["juris"] = 0.30 if (len(q_juris) == 1 and q_juris[0] in title) else 0.0
        # 标题主词（去括号注释后）作为问句子串出现，是极强的精确指向信号
        t_core = re.split(r"[（(：:｜|·]", title)[0].strip()
        f["title_in_q"] = 0.22 if (len(t_core) >= 4 and t_core in q) else 0.0

        # 字面 gram 信号是中文法规检索的强特征，作为重排主因子（评测驱动修复）
        g_q = self._legacy_gram_score(q, e)
        if getattr(self, "_gram_alt", None):
            g_q = max(g_q, self._legacy_gram_score(self._gram_alt, e))
        gram_norm = min(1.0, g_q / 12.0)
        f["gram"] = round(gram_norm, 3)
        # 元数据/层级信号用于「展示与引用提示」，不主导排序（实测会损害首位精确性）
        feat = (0.22 + f["exact_term"] + f["exact_doc_no"] + 0.25 * f["title_cover"] +
                f["numeric"] + f["tier"] + f["status"] + f["dual_source"] +
                f["entry_type"] + f["pending"]) * 0.30
        # 实测结论：中文法规短问句下，字面 gram 匹配仍是最强基线；
        # BM25/RRF/语义通道作为补充信号，而非替代（对齐大厂 hybrid search 思路）。
        score = 1.00 * gram_norm + 0.04 * rank_norm + 0.04 * feat + f["juris"] + f["title_in_q"]
        return {
            "id": eid, "title": title, "doc_no": doc_no,
            "tier": tier, "status": st, "entry_type": e.get("entry_type", ""),
            "score": round(score, 4), "rrf": round(rrf_score, 6), "features": f,
        }

    def _query_overlap(self, q, title):
        """实义词覆盖率：去掉停用词后，问题汉字在标题中的命中比例。"""
        qs = {c for c in HAN_RE.findall(q) if c not in STOP}
        ts = set(HAN_RE.findall(title or ""))
        return len(qs & ts) / max(1, len(qs))

    def _confidence(self, hits, q):
        if not hits:
            return 0.0
        top, second = hits[0]["score"], (hits[1]["score"] if len(hits) > 1 else 0.0)
        base = min(1.0, top / 1.0)
        gap = min(1.0, 0.5 + (top - second) / max(top, 1e-6))
        e = self.by_id.get(hits[0]["id"], {})
        overlap = self._query_overlap(q, e.get("title", ""))
        return round(0.42 * base + 0.18 * gap + 0.40 * overlap, 4)

    # ---------------- 对外主接口 ----------------
    def retrieve(self, q, mode="v5", topk=8):
        q = str(q or "").strip()
        if not q:
            return {"hits": [], "confidence": 0.0, "abstain": True,
                    "trace": [{"stage": "query", "detail": "空问题"}], "expanded": {}}
        if mode == "legacy":
            return self._legacy(q, topk)

        ex = self.expand_query(q)
        # 别名扩展串参与字面召回与重排（原串仍保留在 terms[0]，精确通道不受影响）
        q_exp = " ".join(ex["terms"])
        qtoks = tokenize(q_exp)
        l1 = self.bm25_all.search(qtoks)
        l2 = self.bm25_title.search(qtoks)
        l3 = self._recall_exact(q, ex)
        l4 = self._recall_fts(q)
        l5 = self._recall_gram(q_exp)
        if q_exp != q:
            seen5 = {eid for eid, _ in l5}
            for eid, sc in self._recall_gram(q):
                if eid not in seen5:
                    l5.append((eid, sc))
        rrf = self._rrf([l1, l2, l3, l4, l5])
        maxr = max(rrf.values()) if rrf else 1.0
        cands = sorted(rrf.items(), key=lambda x: -x[1])[:topk * 4]
        # 并入字面强匹配候选，避免精确条目被 RRF 排名稀释
        seen = {eid for eid, _ in cands}
        for eid, _ in l5[:40]:
            if eid not in seen:
                cands.append((eid, 0.0))
                seen.add(eid)
        self._gram_alt = q if q_exp != q else None
        hits = [self._rerank(q_exp, ex, eid, s, s / maxr) for eid, s in cands]
        hits.sort(key=lambda x: -x["score"])
        hits = hits[:topk]
        conf = self._confidence(hits, q)
        top_feat = hits[0]["features"] if hits else {}
        top_e = self.by_id.get(hits[0]["id"], {}) if hits else {}
        overlap = self._query_overlap(q, top_e.get("title", ""))
        out_of_scope = any(re.search(p, q) for p in UNANSWERABLE_PATTERNS)
        strong = (top_feat.get("gram", 0) >= 0.22 or
                  top_feat.get("exact_doc_no", 0) > 0)
        abstain = ((not hits) or out_of_scope or (overlap < 0.15) or
                   (conf < ABSTAIN_THRESHOLD and not strong))
        trace = [
            {"stage": "query", "terms": ex["terms"], "numbers": ex["numbers"],
             "out_of_scope": out_of_scope},
            {"stage": "recall", "bm25_all": len(l1), "bm25_title": len(l2),
             "exact": len(l3), "fts": len(l4), "gram": len(l5),
             "rrf_candidates": len(rrf), "rerank_candidates": len(cands)},
            {"stage": "rerank", "top": hits[0]["id"] if hits else None,
             "features": hits[0]["features"] if hits else {}},
            {"stage": "calibrate", "confidence": conf, "abstain": abstain,
             "overlap": round(overlap, 3), "strong_signal": strong,
             "threshold": ABSTAIN_THRESHOLD},
        ]
        return {"hits": hits, "confidence": conf, "abstain": abstain,
                "trace": trace, "expanded": ex, "mode": "v5"}

    # ---------------- 业务事项层独立检索（v13.0） ----------------
    def retrieve_business_cases(self, q, topk=8):
        """业务事项层独立检索：不参与法规主检索，供 /api/business-cases 使用。

        既保证 51-56 的 30 条结构化条目可检索、可维护，又不改变法规主检索的
        BM25 IDF / RRF 排序，避免扰动既有 Golden QA 评测基线。
        """
        q = str(q or "").strip()
        if not q or not self.business_entries:
            return {"results": [], "total": len(self.business_entries), "q": q}
        ex = self.expand_query(q)
        q_exp = " ".join(ex["terms"])
        s1 = dict(self.bm25_business.search(tokenize(q_exp), limit=40))
        s2 = {e["id"]: float(self._legacy_gram_score(q_exp, e))
              for e in self.business_entries}
        s2 = {k: v for k, v in s2.items() if v > 0}
        scored = [(i, s1.get(i, 0.0) + s2.get(i, 0.0))
                  for i in set(s1) | set(s2)]
        scored.sort(key=lambda x: -x[1])
        out = []
        for i, sc in scored[:topk]:
            e = self.by_id.get(i, {})
            f = e.get("fields", {})
            out.append({
                "id": i, "no": e.get("no", ""), "title": e.get("title", ""),
                "category": e.get("category", ""), "score": round(sc, 4),
                "tier": e.get("tier", ""), "status": e.get("status", ""),
                "scope": f.get("适用范围", ""),
                "basis": f.get("参照依据与关键条款", ""),
                "diff": f.get("税会差异提示", ""),
                "boundary": f.get("适用边界", ""),
            })
        return {"results": out, "total": len(self.business_entries), "q": q}

    # ---------------- legacy 基线（复刻 server.score_entry） ----------------
    def _legacy_gram_score(self, q, e):
        grams = set()
        for i in range(len(q) - 1):
            grams.add(q[i:i + 2])
        for i in range(len(q) - 2):
            grams.add(q[i:i + 3])
        grams = {g for g in grams if g not in STOP and not re.match(r"^[\W\d]+$", g)}
        title = e.get("title", "") + e.get("heading", "")
        s = 0
        for g in grams:
            if g in title:
                s += 3
            elif g in (e.get("search_text", "") or ""):
                s += 1
        return s

    def _legacy(self, q, topk=8):
        scored = [(self._legacy_gram_score(q, e), e) for e in self.main_entries]
        scored = [x for x in scored if x[0] > 0]
        scored.sort(key=lambda x: -x[0])
        hits = [{"id": e["id"], "title": e["title"], "score": float(s),
                 "tier": e.get("tier", ""), "status": e.get("status", "")}
                for s, e in scored[:topk]]
        return {"hits": hits, "confidence": (1.0 if hits else 0.0),
                "abstain": not hits, "mode": "legacy",
                "trace": [{"stage": "legacy_bigram", "count": len(hits)}]}


if __name__ == "__main__":
    r = Retriever()
    for q in ["哪些进项税额不能抵扣", "残保金怎么算", "2026年稳岗返还还能申请吗",
              "前海15%优惠2026年还能用吗", "增值税法第十二条未分别核算"]:
        out = r.retrieve(q, topk=3)
        print(f"\nQ: {q}  conf={out['confidence']} abstain={out['abstain']}")
        for h in out["hits"]:
            print(f"   {h['id']} {h['title'][:34]} score={h.get('score')}")
