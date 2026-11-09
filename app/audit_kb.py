# -*- coding: utf-8 -*-
"""audit_kb.py — 生产级知识库审计 v2（可复现，纯标准库）。

v2 变化：按 entry_type 分型审计，不再把「汇编/表格型」条目强行套用单一法规的
10 字段标准；明确区分「数据缺口」「需人工回查」「已隔离阻断」三类。
输出 reports/audit-stats.json；同时读取 SQLite 的隔离项表。
"""
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(BASE, "kb.json")
DB = os.path.join(BASE, "finance-tax-compliance.db")
OUT = os.path.normpath(os.path.join(BASE, "..", "reports", "audit-stats.json"))

VALID_STATUS = {"现行有效", "已废止", "修订中", "草案阶段"}
ASSEMBLY_STATUS = "汇编·动态"
ALL_STATUS = VALID_STATUS | {ASSEMBLY_STATUS}
# 单一法规型必备字段
REG_FIELDS = ["doc_no", "issuer", "level", "publish_date", "scope",
              "core_clauses", "compliance_points", "verified_at"]
# v6 解释层：按自身模板校验，不套用单一法规元数据
EXPLAIN_TYPES = {"concept", "relation", "scenario", "verification", "business_case"}


def main():
    with open(KB, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data["entries"]

    rows = []
    for e in entries:
        f = e.get("fields", {})
        etype = e.get("entry_type", "regulation")
        flags = e.get("quality_flags", [])
        srcs = e.get("sources", [])
        status = e.get("status_norm", "") or e.get("status", "")
        # 单一法规型才校验 10 字段；汇编/表格型字段「不适用」而非「缺失」
        if etype == "regulation":
            missing = [k for k in REG_FIELDS if not e.get(k)]
            if not (e.get("publish_date") or e.get("effective_date")):
                if "publish_date" not in missing:
                    missing.append("publish_date")
        elif etype in EXPLAIN_TYPES:
            missing = [x for x in flags if x.startswith("missing_explain_field:")]
        else:
            missing = []

        if etype == "regulation":
            compliant = (not missing and len(srcs) >= 2 and status in VALID_STATUS
                         and "pending_field" not in flags)
        elif etype in EXPLAIN_TYPES:
            # 解释层达标 = 模板字段齐 + 双官方链接 + 状态明确 + 无待核验字段
            compliant = (e.get("concept_complete") is True and len(srcs) >= 2
                         and status in ALL_STATUS and "pending_field" not in flags)
        else:
            # 汇编/表格型：有明确状态、有信源（描述或链接）、有核验日期即可
            compliant = (status in ALL_STATUS and
                         bool(srcs or e.get("source_text")) and
                         bool(e.get("verified_at")) and
                         "status_unlabeled" not in flags)

        rows.append({
            "id": e["id"], "file": e.get("file", ""), "title": e.get("title", ""),
            "entry_type": etype, "tier": e.get("tier", "B2"),
            "status": status, "valid_status": status in ALL_STATUS,
            "missing": missing, "flags": flags,
            "url_count": len(srcs), "dual_source": len(srcs) >= 2,
            "compliant": compliant,
        })

    by_type = defaultdict(lambda: {"total": 0, "compliant": 0})
    for r in rows:
        by_type[r["entry_type"]]["total"] += 1
        by_type[r["entry_type"]]["compliant"] += int(r["compliant"])

    # 隔离项（来自数据库）
    pending = []
    if os.path.exists(DB):
        con = sqlite3.connect(DB)
        for row in con.execute("SELECT code,state,location,content,risk,action FROM pending_item"):
            pending.append(dict(zip(("code", "state", "location", "content", "risk", "action"), row)))
        n_alias = con.execute("SELECT COUNT(*) FROM alias").fetchone()[0]
        n_ref = con.execute("SELECT COUNT(*) FROM rule_reference").fetchone()[0]
        n_changes = con.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
        con.close()
    else:
        n_alias = n_ref = n_changes = 0

    flags_count = Counter(fl for r in rows for fl in r["flags"])
    summary = {
        # 兼容旧报告键
        "kb_version": data.get("kb_version", ""), "verified_at": data.get("verified_at", ""),
        "entries": len(entries), "files": len(data.get("files", [])),
        "complete_metadata": sum(1 for r in rows if r["entry_type"] == "regulation" and not r["missing"]),
        "valid_status": sum(1 for r in rows if r["valid_status"]),
        "flagged_entries": sum(1 for r in rows if "pending_field" in r["flags"]),
        "dual_source_entries": sum(1 for r in rows if r["dual_source"]),
        # v2 新增：按类型拆分的真实达标率
        "regulation_total": by_type["regulation"]["total"],
        "regulation_compliant": by_type["regulation"]["compliant"],
        "assembly_total": sum(v["total"] for k, v in by_type.items() if k != "regulation"),
        "assembly_compliant": sum(v["compliant"] for k, v in by_type.items() if k != "regulation"),
        "na_field_entries": sum(1 for r in rows if r["entry_type"] != "regulation"),
        "pending_field_entries": sum(1 for r in rows if "pending_field" in r["flags"]),
        "enriched_at": data.get("enriched_at", ""),
        "tiers": data.get("tiers", {}),
        "by_entry_type": dict(by_type),
        "explain_types": {k: dict(v) for k, v in by_type.items() if k in EXPLAIN_TYPES},
        "explain_total": sum(v["total"] for k, v in by_type.items() if k in EXPLAIN_TYPES),
        "explain_compliant": sum(v["compliant"] for k, v in by_type.items() if k in EXPLAIN_TYPES),
        "concept_complete": sum(1 for e in entries
                                if e.get("entry_type") == "concept" and e.get("concept_complete") is True),
        "compliant_total": sum(1 for r in rows if r["compliant"]),
        "status_breakdown": dict(Counter(r["status"] for r in rows)),
        "flag_breakdown": dict(flags_count),
        "blocked_items": [p for p in pending if p["state"] == "BLOCKED"],
        "scope_items": [p for p in pending if p["state"] == "SCOPE"],
        "alias_count": n_alias, "rule_reference_count": n_ref, "change_log_count": n_changes,
        "database": os.path.basename(DB) if os.path.exists(DB) else "NONE",
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows, "pending_items": pending},
                  f, ensure_ascii=False, indent=1)

    print("=== 生产级审计 v2 ===")
    for k in ("kb_version", "entries", "files", "enriched_at", "tiers",
              "compliant_total", "valid_status", "dual_source_entries"):
        print(f"  {k}: {summary[k]}")
    print("  by_entry_type:", {k: f"{v['compliant']}/{v['total']}" for k, v in by_type.items()})
    print("  status:", summary["status_breakdown"])
    print("  flags:", flags_count.most_common())
    print("  blocked:", [p["code"] for p in summary["blocked_items"]])
    print("\n=== 仍需人工回查的字段（pending_field） ===")
    for r in rows:
        if "pending_field" in r["flags"]:
            print(f"  {r['id']} {r['title'][:36]}")
    print("\n=== 隔离/边界项 ===")
    for p in pending:
        print(f"  [{p['state']}] {p['code']} {p['content'][:50]}")
    print(f"\n[ok] -> {OUT}")


if __name__ == "__main__":
    main()
