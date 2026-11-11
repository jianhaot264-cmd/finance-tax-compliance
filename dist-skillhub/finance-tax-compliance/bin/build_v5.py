# -*- coding: utf-8 -*-
"""build_v5.py — v5 生产级数据层（在 build_kb.py → enrich_kb.py 之后运行）。

新增：
  article_text          逐字法条（从 23 文件 + L0 corpus-articles.json 解析，供检索与引用）
  citation_verification 权威库回库核验记录
  query_log             每次问答留痕（运行时由 server.py 写入，本脚本只建表）
  golden_case           Golden 评测集（手工边界题）
  eval_run/eval_result  量化评测结果（由 eval_kb.py 写入）
幂等：可重建的表先清空再导入；留痕类表保留历史。
"""
import json
import os
import re
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(BASE, "kb.json")
DB = os.path.join(BASE, "finance-tax-compliance.db")
EXTRA = os.path.join(BASE, "golden_extra.json")
ART_RE = re.compile(r"第([一二三四五六七八九十百零\d]+)条[^\n「]{0,60}「([^」]{10,})」")
URL_RE = re.compile(r"https?://[^\s|)>）\]\"']+")


def main():
    with open(KB, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data["entries"]
    verified_at = data.get("verified_at", "")
    con = sqlite3.connect(DB)
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS article_text (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_id TEXT NOT NULL, law_name TEXT, article_no TEXT,
        verbatim TEXT NOT NULL, effect_level TEXT, validity TEXT,
        source_db TEXT, source_url TEXT, verified_at TEXT);
    CREATE TABLE IF NOT EXISTS citation_verification (
        entry_id TEXT PRIMARY KEY, law_name TEXT, article_count INTEGER,
        validity TEXT, source_db TEXT, source_url TEXT,
        official_cross TEXT, verified_at TEXT, note TEXT);
    CREATE TABLE IF NOT EXISTS query_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, q TEXT, mode TEXT, role TEXT, risk TEXT,
        confidence REAL, abstain INTEGER, top_ids TEXT, refs TEXT,
        verification_ok INTEGER, warnings TEXT, verdict TEXT, model TEXT);
    CREATE TABLE IF NOT EXISTS golden_case (
        case_id TEXT PRIMARY KEY, q TEXT, category TEXT,
        expected_role TEXT, must_refs TEXT, must_keywords TEXT,
        forbid_keywords TEXT, should_abstain INTEGER, risk TEXT, source TEXT);
    CREATE TABLE IF NOT EXISTS eval_run (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at TEXT, kb_version TEXT, total_cases INTEGER, metrics_json TEXT);
    CREATE TABLE IF NOT EXISTS eval_result (
        run_id INTEGER, metric TEXT, value REAL,
        PRIMARY KEY(run_id, metric));
    CREATE TABLE IF NOT EXISTS external_lookup_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, q TEXT, need INTEGER, signals TEXT, status TEXT,
        sources TEXT, evidence_count INTEGER, note TEXT);
    -- kb_meta 原先只在 enrich_kb.py 中创建；打包分发时若不带该脚本，
    -- build_v5.py 末尾写 kb_meta 会因缺表失败。此处补建，使其自包含。
    CREATE TABLE IF NOT EXISTS kb_meta (key TEXT PRIMARY KEY, value TEXT);
    """)

    # 可重建表清空
    cur.execute("DELETE FROM article_text")
    cur.execute("DELETE FROM citation_verification")
    cur.execute("DELETE FROM golden_case")

    n_art, n_ver, n_corpus = 0, 0, 0
    inserted_articles = set()
    # L0 逐字原文层优先（双源逐条核验的规范原文）；23 文件仅补充 L0 未覆盖者。
    # 早期顺序相反，导致 23 文件里「摘要式」的 7 条（企税条例第28/40-44/53 条）
    # 先占位，L0 规范原文反而被去重跳过，问这些条款时注入到格式不规范的版本。
    _l0_keys = set()
    _l0_path = os.path.join(BASE, "corpus-articles.json")
    if os.path.exists(_l0_path):
        try:
            with open(_l0_path, "r", encoding="utf-8") as f:
                for a in json.load(f).get("articles", []):
                    if a.get("verbatim"):
                        _l0_keys.add((str(a.get("law_name", ""))[:80],
                                      str(a.get("article_no", ""))))
        except (OSError, ValueError, KeyError):
            pass
    for e in entries:
        if e.get("file") != "23":
            continue
        title = e.get("title", "")
        body = e.get("body_md", "") or ""
        src = e.get("fields", {}).get("信源", "")
        urls = URL_RE.findall(src)
        law_name = re.sub(r"^《|》.*$", "", title) or title
        pairs = ART_RE.findall(body)
        for art_no, verbatim in pairs:
            _key = (law_name[:80], "第" + art_no + "条")
            if _key in _l0_keys:
                # L0 已有该条规范原文，跳过 23 文件的摘要式版本，避免抢位
                continue
            cur.execute("""INSERT INTO article_text
                (entry_id,law_name,article_no,verbatim,effect_level,validity,
                 source_db,source_url,verified_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (e["id"], law_name[:80], "第" + art_no + "条", verbatim.strip(),
                 e.get("level", ""), e.get("status", ""),
                 "官方双源核验（政府网/司法部法规库/部委官网）", urls[0] if urls else "",
                 verified_at))
            inserted_articles.add(_key)
            n_art += 1
        cur.execute("""INSERT OR REPLACE INTO citation_verification VALUES (?,?,?,?,?,?,?,?,?)""",
                    (e["id"], law_name[:80], len(pairs), e.get("status", ""),
                     "人大/国务院/部委官网逐条比对",
                     urls[0] if urls else "",
                     "中国政府网/司法部行政法规库/财政部/税务总局官网双源",
                     verified_at,
                     "回库确认现行有效；逐字原文见 article_text 表"))
        n_ver += 1

    # ---- L0 逐字原文层（corpus-articles.json）：多来源增量，按 (法规名, 条号) 去重 ----
    # entry_id 决定该条法条能否被 build_llm_context 注入（server.py 用 `if eid in hit` 过滤）。
    # 早期版本直接写 doc_id（如 "cit-law-2018"），与知识库条目 ID（如 "41-41.1"）永不相等，
    # 导致 L0 新增条文全部注入不到 LLM 上下文（实测 610 条全部悬空）。此处按法规名回挂条目 ID。
    #
    # 注意：知识库大量条目用「描写性标题」（如「船舶吨税：进出境船舶、定额税率、海关代征」），
    # 与法规原名不相等。故先精确匹配，再退化为「标题包含法规关键词」，
    # 并在多个候选中选标题最短者（最贴近法规本身，而非汇总/边界类条目）。
    def _law_core(law_name):
        """去掉「中华人民共和国」前缀、括号补充，并剥离法规后缀，得核心名。"""
        s = (law_name or "").strip()
        s = re.sub(r"^中华人民共和国", "", s)
        s = re.sub(r"[（(].*?[)）]", "", s).strip()
        return s

    # 核心名的候选写法：原名 / 去「法」 / 去「暂行条例」等。
    # 例：「船舶吨税法」→ 知识库标题是「船舶吨税：进出境船舶…」，需用「船舶吨税」才匹配得上。
    def _core_variants(law_name):
        core = _law_core(law_name)
        if not core:
            return []
        out = [core]
        for suf in ("暂行条例", "实施条例", "条例", "法"):
            if core.endswith(suf) and len(core) > len(suf):
                out.append(core[: -len(suf)])
        return list(dict.fromkeys(out))

    cand = {}
    for e in entries:
        t = (e.get("title") or "").strip()
        if not t or e["id"].startswith("23-"):
            continue
        cand.setdefault(t, []).append(e["id"])

    def resolve_entry_id(law_name):
        """法规名 → 知识库条目 ID（精确优先，其次按核心名包含匹配取最短标题）。"""
        name = (law_name or "").strip()
        if not name:
            return ""
        # 1) 精确相等
        ids = cand.get(name) or []
        if ids:
            return ids[0]
        # 2) 按核心名（含去后缀变体）做包含匹配，取标题最短者
        best, best_len = "", 10 ** 9
        for core in _core_variants(name):
            for t, tids in cand.items():
                if len(core) >= 2 and core in t and len(t) < best_len:
                    best, best_len = tids[0], len(t)
        return best

    corpus_path = os.path.join(BASE, "corpus-articles.json")
    if os.path.exists(corpus_path):
        try:
            with open(corpus_path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            n_unlinked = 0
            for a in cdata.get("articles", []):
                key = (str(a.get("law_name", ""))[:80], str(a.get("article_no", "")))
                if key in inserted_articles or not a.get("verbatim"):
                    continue
                eid = resolve_entry_id(key[0])
                if not eid:
                    n_unlinked += 1
                cur.execute("""INSERT INTO article_text
                    (entry_id,law_name,article_no,verbatim,effect_level,validity,
                     source_db,source_url,verified_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (eid, key[0], key[1], a["verbatim"],
                     a.get("effect_level", ""), a.get("validity", ""),
                     a.get("source_db", "官方原文层 L0"),
                     a.get("source_url", ""), a.get("verified_at", "")))
                inserted_articles.add(key)
                n_corpus += 1
            if n_unlinked:
                print("  [note] L0 中 %d 条因知识库无同名条目而未挂 entry_id"
                      "（条文仍可全文检索，但不注入 LLM 上下文）" % n_unlinked)
        except (OSError, ValueError, KeyError) as ex:
            print("  [warn] L0 原文层导入跳过:", ex)

    with open(EXTRA, "r", encoding="utf-8") as f:
        extras = json.load(f)["cases"]
    for c in extras:
        cur.execute("""INSERT INTO golden_case VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (c["id"], c["q"], c.get("category", ""), c.get("expected_role"),
                     json.dumps(c.get("must_refs") or [], ensure_ascii=False),
                     json.dumps(c.get("must_keywords") or [], ensure_ascii=False),
                     json.dumps(c.get("forbid_keywords") or [], ensure_ascii=False),
                     1 if c.get("should_abstain") is True else
                     (0 if c.get("should_abstain") is False else None),
                     c.get("risk", "low"), "manual"))

    cur.execute("""INSERT OR REPLACE INTO kb_meta(key,value) VALUES
        ('v5_layer','1.0'),('verified_at',?),
        ('authoritative_articles',?)""", (verified_at, str(n_art + n_corpus)))
    con.commit()

    print("=== v5 数据层 ===")
    print("  article_text 逐字法条:", n_art + n_corpus,
          f"（23 文件 {n_art} + L0 原文层新增 {n_corpus}）")
    print("  citation_verification 核验记录:", n_ver)
    print("  golden_case 手工边界题:", len(extras))
    print("  query_log / eval_run / eval_result: 已建表（留痕历史保留）")
    for t in ("article_text", "citation_verification", "query_log", "golden_case"):
        print(f"  {t}: {cur.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]} 行")
    con.close()


if __name__ == "__main__":
    main()
