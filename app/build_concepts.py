# -*- coding: utf-8 -*-
"""build_concepts.py — v6.0 概念解读层结构化（纯标准库）。

流程：knowledge-base/25..28.md --build_kb.py--> kb.json --enrich_kb.py--> 增强 kb.json
      --build_concepts.py--> concepts.json + SQLite 概念/关系/场景/边界/勘误表 + CSV

设计原则：md 仍是唯一事实源；本脚本只做提取与建表，不新增结论、不猜测字段。
必须在 enrich_kb.py 之后、audit_kb.py 之前运行。
"""
import csv
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
ROOT = os.path.normpath(os.path.join(BASE, ".."))
KB_JSON = os.path.join(BASE, "kb.json")
DB = os.path.join(BASE, "finance-tax-compliance.db")
OUT_JSON = os.path.join(BASE, "concepts.json")
OUT_CSV = os.path.join(ROOT, "reports", "concept-map-2026-11-07.csv")

FIELD_MAP = [
    ("code", "概念编号"), ("category", "概念类别"), ("definition", "定义"),
    ("distinctions", "定义辨析"), ("causal", "因果逻辑"), ("conditions", "适用条件"),
    ("boundaries", "边界条件与例外"), ("confusions", "易混淆点"),
    ("limitations", "局限说明"), ("scenarios", "常见场景"),
    ("related_entries", "关联条目"), ("related_concepts", "关联概念"),
    ("basis", "主要依据"), ("status", "时效性"), ("sources", "信源"), ("verified", "核验"),
]
URL_RE = re.compile(r"https?://[^\s|)>）\]\"']+")
ID_RE = re.compile(r"\d{2}-[\d.\-]+")
TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")


def parse_md_tables(text):
    """解析 markdown 表格为 [{header: value}]，用于 26 文件的机器可读矩阵。"""
    out, header, rows = [], None, []
    for line in text.split("\n"):
        m = TABLE_ROW.match(line.strip())
        if not m:
            if header and rows:
                for r in rows:
                    out.append({header[i]: r[i] for i in range(min(len(header), len(r)))})
            header, rows = None, []
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if header is None:
            header = cells
        else:
            rows.append(cells)
    if header and rows:
        for r in rows:
            out.append({header[i]: r[i] for i in range(min(len(header), len(r)))})
    return out


def urls(s):
    return [u.rstrip(".,;；。") for u in URL_RE.findall(s or "")]


def main():
    with open(KB_JSON, "r", encoding="utf-8") as f:
        kb = json.load(f)
    entries = kb["entries"]
    by_file = {}
    for e in entries:
        by_file.setdefault(e.get("file", ""), []).append(e)

    concepts, scenarios, corrections = [], [], []
    for e in by_file.get("25", []):
        f = e.get("fields", {})
        c = {"id": e["id"], "name": e["title"], "tier": e.get("tier", ""),
             "entry_type": e.get("entry_type", ""), "search_text": e.get("search_text", ""),
             "source_file": e.get("source_file", "")}
        for k, cn in FIELD_MAP:
            c[k] = str(f.get(cn, "")).strip()
        c["source_urls"] = urls(c["sources"])
        c["entry_refs"] = ID_RE.findall(c["related_entries"])
        c["concept_refs"] = re.findall(r"C\d{2}", c["related_concepts"])
        c["complete"] = all(c[k] for k, _ in FIELD_MAP)
        concepts.append(c)

    for e in by_file.get("27", []):
        f = e.get("fields", {})
        s = {"id": e["id"], "name": re.sub(r"》?场景卡$", "", e["title"]).replace("《", ""),
             "tier": e.get("tier", ""), "source_file": e.get("source_file", "")}
        for k, cn in (("scene", "适用场景"), ("actors", "适用主体"), ("path", "判断路径"),
                      ("must_check", "必须核验"), ("boundaries", "边界与例外"),
                      ("pitfalls", "易错结论"), ("escalate", "应弃答或转介"),
                      ("related_concepts", "关联概念"), ("related_entries", "关联条目"),
                      ("status", "时效性"), ("sources", "信源"), ("verified", "核验")):
            s[k] = str(f.get(cn, "")).strip()
        s["steps"] = [x.strip() for x in re.split(r"[①②③④⑤⑥⑦]", s["path"]) if x.strip()]
        s["entry_refs"] = ID_RE.findall(s["related_entries"])
        s["concept_refs"] = re.findall(r"C\d{2}", s["related_concepts"])
        scenarios.append(s)

    for e in by_file.get("28", []):
        f = e.get("fields", {})
        v = {"id": e["id"], "name": e["title"], "tier": e.get("tier", ""),
             "source_file": e.get("source_file", "")}
        for k, cn in (("doc_no", "文号"), ("issuer", "发文机关"), ("level", "效力层级"),
                      ("pub", "公布/施行"), ("status", "时效性"), ("scope", "适用范围"),
                      ("action", "核验动作"), ("clauses", "核心条款"),
                      ("compliance", "合规要点"), ("impact", "影响条目"),
                      ("state", "处理状态"), ("sources", "信源"), ("verified", "核验")):
            v[k] = str(f.get(cn, "")).strip()
        v["source_urls"] = urls(v["sources"])
        corrections.append(v)

    # 26 文件：关系明细 / 易混淆对照 / 数字门槛 → 三类结构化矩阵
    relations, confusions, thresholds = [], [], []
    for e in by_file.get("26", []):
        rows = parse_md_tables(e.get("body_md", "") or "")
        for r in rows:
            keys = set(r.keys())
            if {"源概念", "关系", "目标"} <= keys:
                relations.append({"source": r.get("源概念", ""), "relation": r.get("关系", ""),
                                  "target": r.get("目标", ""), "condition": r.get("条件或说明", ""),
                                  "ref_entry": r.get("依据条目", ""), "from": e["id"]})
            elif {"概念 A", "概念 B"} <= keys:
                confusions.append({"a": r.get("概念 A", ""), "b": r.get("概念 B", ""),
                                   "difference": r.get("关键不同点", ""),
                                   "order": r.get("判断顺序", ""), "cost": r.get("答错后果", ""),
                                   "from": e["id"]})
            elif {"数字", "口径"} <= keys:
                thresholds.append({"value": r.get("数字", ""), "scope": r.get("口径", ""),
                                   "effective": r.get("生效时点", ""),
                                   "edge": r.get("例外 / 边界", ""), "ref_entry": r.get("依据条目", ""),
                                   "from": e["id"]})
    # 概念卡内的「关联概念 / 关联条目」也生成关系边，保证双向可查
    for c in concepts:
        for rid in c["entry_refs"]:
            relations.append({"source": c["code"] + " " + c["name"], "relation": "关联条目",
                              "target": rid, "condition": "概念卡引用", "ref_entry": rid,
                              "from": c["id"]})
        for code in c["concept_refs"]:
            relations.append({"source": c["code"], "relation": "关联概念", "target": code,
                              "condition": "概念卡引用", "ref_entry": "", "from": c["id"]})

    payload = {
        "version": "v6.0", "generated_at": "2026-11-07",
        "verified_at": kb.get("verified_at", ""),
        "counts": {"concepts": len(concepts), "relations": len(relations),
                   "scenarios": len(scenarios), "confusions": len(confusions),
                   "thresholds": len(thresholds), "corrections": len(corrections)},
        "concepts": concepts, "relations": relations, "scenarios": scenarios,
        "confusions": confusions, "thresholds": thresholds, "corrections": corrections,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # CSV 概念主数据表（UTF-8 BOM，便于 Excel / 企业系统导入）
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    cols = ["id", "code", "name", "category", "definition", "distinctions", "causal",
            "conditions", "boundaries", "confusions", "limitations", "scenarios",
            "related_entries", "related_concepts", "basis", "status", "tier", "complete",
            "source_urls", "verified"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for c in concepts:
            w.writerow({k: (" ; ".join(c.get(k, [])) if isinstance(c.get(k), list)
                            else c.get(k, "")) for k in cols})

    # ---------------------------------------------------------------- SQLite
    if not os.path.exists(DB):
        print("[warn] SQLite 不存在，请先运行 enrich_kb.py")
        return
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS concept (
        id TEXT PRIMARY KEY, code TEXT, name TEXT, category TEXT, definition TEXT,
        distinctions TEXT, causal TEXT, conditions TEXT, boundaries TEXT,
        confusions TEXT, limitations TEXT, scenarios TEXT, related_entries TEXT,
        related_concepts TEXT, basis TEXT, status TEXT, tier TEXT, complete INTEGER,
        source_urls TEXT, source_count INTEGER, verified_at TEXT, search_text TEXT);
    CREATE TABLE IF NOT EXISTS concept_relation (
        id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, relation TEXT, target TEXT,
        condition TEXT, ref_entry TEXT, from_entry TEXT);
    CREATE TABLE IF NOT EXISTS scenario (
        id TEXT PRIMARY KEY, name TEXT, scene TEXT, actors TEXT, path TEXT, steps TEXT,
        must_check TEXT, boundaries TEXT, pitfalls TEXT, escalate TEXT,
        related_concepts TEXT, related_entries TEXT, status TEXT, tier TEXT);
    CREATE TABLE IF NOT EXISTS boundary_item (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, col1 TEXT, col2 TEXT,
        col3 TEXT, col4 TEXT, col5 TEXT, from_entry TEXT);
    CREATE TABLE IF NOT EXISTS verification_item (
        id TEXT PRIMARY KEY, name TEXT, doc_no TEXT, issuer TEXT, level TEXT,
        pub TEXT, status TEXT, scope TEXT, action TEXT, clauses TEXT,
        compliance TEXT, impact TEXT, state TEXT, sources TEXT, verified_at TEXT);
    """)
    for t in ("concept", "concept_relation", "scenario", "boundary_item", "verification_item"):
        cur.execute(f"DELETE FROM {t}")

    for c in concepts:
        cur.execute("""INSERT INTO concept VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            c["id"], c["code"], c["name"], c["category"], c["definition"], c["distinctions"],
            c["causal"], c["conditions"], c["boundaries"], c["confusions"], c["limitations"],
            c["scenarios"], c["related_entries"], c["related_concepts"], c["basis"], c["status"],
            c["tier"], 1 if c["complete"] else 0, json.dumps(c["source_urls"], ensure_ascii=False),
            len(c["source_urls"]), c["verified"], c["search_text"]))
        # 概念名与编号写入 alias，支持简称 / 编号检索
        cur.execute("INSERT OR IGNORE INTO alias VALUES (?,?,?)", (c["code"], c["name"], "concept_code"))
        cur.execute("INSERT OR IGNORE INTO alias VALUES (?,?,?)", (c["name"], c["id"], "concept_name"))

    for r in relations:
        cur.execute("""INSERT INTO concept_relation (source,relation,target,condition,ref_entry,from_entry)
                       VALUES (?,?,?,?,?,?)""",
                    (r["source"], r["relation"], r["target"], r["condition"],
                     r["ref_entry"], r["from"]))
    for s in scenarios:
        cur.execute("""INSERT INTO scenario VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            s["id"], s["name"], s["scene"], s["actors"], s["path"],
            json.dumps(s["steps"], ensure_ascii=False), s["must_check"], s["boundaries"],
            s["pitfalls"], s["escalate"], s["related_concepts"], s["related_entries"],
            s["status"], s["tier"]))
    for kind, rows, keys in (
        ("confusion", confusions, ("a", "b", "difference", "order", "cost")),
        ("threshold", thresholds, ("value", "scope", "effective", "edge", "ref_entry")),
    ):
        for r in rows:
            cur.execute("""INSERT INTO boundary_item (kind,col1,col2,col3,col4,col5,from_entry)
                           VALUES (?,?,?,?,?,?,?)""",
                        (kind, *(r.get(k, "") for k in keys), r["from"]))
    for v in corrections:
        cur.execute("""INSERT INTO verification_item VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            v["id"], v["name"], v["doc_no"], v["issuer"], v["level"], v["pub"], v["status"],
            v["scope"], v["action"], v["clauses"], v["compliance"], v["impact"], v["state"],
            json.dumps(v["source_urls"], ensure_ascii=False), v["verified"]))

    cur.execute("INSERT OR REPLACE INTO kb_meta VALUES (?,?)", ("concept_count", str(len(concepts))))
    cur.execute("INSERT OR REPLACE INTO kb_meta VALUES (?,?)", ("concept_version", "v6.0"))
    con.commit()
    con.close()

    print("[ok] concepts.json ->", OUT_JSON)
    print("[ok] CSV ->", OUT_CSV)
    for k, v in payload["counts"].items():
        print(f"     {k}: {v}")
    complete = sum(1 for c in concepts if c["complete"])
    print(f"     概念卡 16 字段完整: {complete}/{len(concepts)}")


if __name__ == "__main__":
    main()
