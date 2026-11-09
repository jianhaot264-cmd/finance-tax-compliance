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
    """)

    # 可重建表清空
    cur.execute("DELETE FROM article_text")
    cur.execute("DELETE FROM citation_verification")
    cur.execute("DELETE FROM golden_case")

    n_art, n_ver, n_corpus = 0, 0, 0
    inserted_articles = set()
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
            cur.execute("""INSERT INTO article_text
                (entry_id,law_name,article_no,verbatim,effect_level,validity,
                 source_db,source_url,verified_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (e["id"], law_name[:80], "第" + art_no + "条", verbatim.strip(),
                 e.get("level", ""), e.get("status", ""),
                 "企查查法律/华宇元典/同花顺法律", urls[0] if urls else "",
                 verified_at))
            inserted_articles.add((law_name[:80], "第" + art_no + "条"))
            n_art += 1
        cur.execute("""INSERT OR REPLACE INTO citation_verification VALUES (?,?,?,?,?,?,?,?,?)""",
                    (e["id"], law_name[:80], len(pairs), e.get("status", ""),
                     "企查查法律 get_legal_citation_verify + 华宇元典语义检索",
                     urls[0] if urls else "",
                     "中国政府网/司法部行政法规库/财政部/税务总局官网双源",
                     verified_at,
                     "回库确认现行有效；逐字原文见 article_text 表"))
        n_ver += 1

    # ---- L0 逐字原文层（corpus-articles.json）：多来源增量，按 (法规名, 条号) 去重 ----
    corpus_path = os.path.join(BASE, "corpus-articles.json")
    if os.path.exists(corpus_path):
        try:
            with open(corpus_path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            for a in cdata.get("articles", []):
                key = (str(a.get("law_name", ""))[:80], str(a.get("article_no", "")))
                if key in inserted_articles or not a.get("verbatim"):
                    continue
                cur.execute("""INSERT INTO article_text
                    (entry_id,law_name,article_no,verbatim,effect_level,validity,
                     source_db,source_url,verified_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (a.get("doc_id", "L0"), key[0], key[1], a["verbatim"],
                     a.get("effect_level", ""), a.get("validity", ""),
                     a.get("source_db", "官方原文层 L0"),
                     a.get("source_url", ""), a.get("verified_at", "")))
                inserted_articles.add(key)
                n_corpus += 1
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
