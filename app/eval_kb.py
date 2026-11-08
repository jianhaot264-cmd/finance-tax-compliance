# -*- coding: utf-8 -*-
"""eval_kb.py — Golden QA 量化评测（可复现、纳入回归门禁）。

评测集 = 自动从 server.RULES 生成（随规则库增长）+ golden_extra.json 手工边界题。
基线 = 真实旧代码 server.retrieve() / server.score_entry()；对照 = retrieval.Retriever v5。

指标：
  Recall@5      期望引用条目至少 1 个出现在 Top5 的题占比
  MRR           第一个正确条目的排名倒数均值
  引用正确率     /api/ask 返回 refs 中出现在 v5 Top8 的比例（引用对齐）
  弃答正确率     标注 should_abstain 的题，v5 弃答判定一致的比例
  角色分诊准确率 route_role 与 expected_role 一致的比例
  规则命中率     /api/ask 命中精编规则（mode=rule）的比例
输出 reports/eval-report-v5.json，并把汇总写入 SQLite eval_run/eval_result。
"""
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime

# server.py 顶层会读 sys.argv[1] 作为 PORT；导入前清理，避免误解析
sys.argv = [sys.argv[0]]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server  # noqa: E402
from retrieval import Retriever  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BASE, ".."))
OUT = os.path.join(ROOT, "reports", "eval-report-v5.json")
DB_PATH = os.path.join(BASE, "finance-tax-compliance.db")
EXTRA = os.path.join(BASE, "golden_extra.json")
API = "http://localhost:8777/api/ask"


def build_cases():
    cases = []
    for r in server.RULES:
        q = r.get("q")
        if not q:
            continue
        cases.append({
            "id": "A-" + r["id"], "q": q, "source": "auto",
            "expected_role": r.get("role"), "must_refs": list(r.get("refs") or []),
            "forbid_refs": [], "must_keywords": [], "forbid_keywords": [],
            "should_abstain": None, "risk": r.get("risk", "low"),
        })
    with open(EXTRA, "r", encoding="utf-8") as f:
        for c in json.load(f)["cases"]:
            c["source"] = "manual"
            cases.append(c)
    return cases


def mrr(expected, ids):
    for i, x in enumerate(ids[:5], start=1):
        if x in expected:
            return 1.0 / i
    return 0.0


def forbidden_hit(term, text):
    """禁用表述判定：带显式否定前缀（「不是 / 并非 / 而非 / ≠ / 不等于」）的
    引用属于正确澄清，不计为违规。避免把「而非永久免税」误判成输出了错误结论。
    """
    neg = re.compile(r"(不是|并非|不等于|而非|≠|不得|不能|不能算|不可|非|不等于)[^，。；、]{0,8}$")
    for m in re.finditer(re.escape(term), text):
        prefix = text[max(0, m.start() - 16):m.start()]
        if neg.search(prefix):
            continue
        return True
    return False


def ask_api(q):
    try:
        body = json.dumps({"q": q}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(API, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            a = d.get("answer", {})
            parts = []
            for s in a.get("sections", []) or []:
                if not isinstance(s, dict):
                    continue
                if s.get("text"):
                    parts.append(str(s["text"]))
                for it in s.get("items", []) or []:
                    if isinstance(it, dict):
                        parts.append(str(it.get("text") or ""))
                        # 检索型 section 的 items 是条目卡（title+snippet），此前未计入，
                        # 导致 retrieval 模式的关键词覆盖恒为 0；此处纳入，与前端可见内容对齐。
                        parts.append(str(it.get("title") or ""))
                        parts.append(str(it.get("snippet") or ""))
                    elif it:
                        parts.append(str(it))
            return {"mode": a.get("mode"), "role": a.get("routed"),
                    "refs": a.get("refs", []), "risk": a.get("risk"),
                    "text": " ".join(parts)}
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None


def main():
    cases = build_cases()
    retr = Retriever(entries=server.KB["entries"])
    valid_ids = set(server.ENTRY_MAP)

    rows = []
    kw_failures = []
    agg = {"cases": len(cases), "recall5_legacy": [], "recall5_v5": [],
           "mrr_legacy": [], "mrr_v5": [], "abstain": [], "role": [],
           "rule_hit": [], "citation_align": [], "api_available": 0,
           "kw_cover": [], "kw_avoid": []}

    for c in cases:
        q, exp = c["q"], [x for x in c.get("must_refs") or [] if x in valid_ids]
        legacy = [e["id"] for e in server.retrieve(q, top=5)]
        v5 = retr.retrieve(q, mode="v5", topk=8)
        v5_ids = [h["id"] for h in v5["hits"]]
        v5_5 = v5_ids[:5]

        row = {"id": c["id"], "q": q, "source": c["source"],
               "must_refs": c.get("must_refs") or [], "legacy_top5": legacy,
               "v5_top5": v5_5, "confidence": v5["confidence"],
               "abstain": v5["abstain"]}
        if exp:
            rl = 1.0 if any(x in legacy for x in exp) else 0.0
            rv = 1.0 if any(x in v5_5 for x in exp) else 0.0
            agg["recall5_legacy"].append(rl)
            agg["recall5_v5"].append(rv)
            agg["mrr_legacy"].append(mrr(exp, legacy))
            agg["mrr_v5"].append(mrr(exp, v5_ids))
            row.update({"recall_legacy": rl, "recall_v5": rv,
                        "mrr_legacy": mrr(exp, legacy), "mrr_v5": mrr(exp, v5_ids)})

        api = ask_api(q)
        if api:
            agg["api_available"] += 1
            agg["rule_hit"].append(1.0 if api["mode"] == "rule" else 0.0)
            refs = [x for x in api["refs"] if x in valid_ids]
            if refs:
                agg["citation_align"].append(
                    sum(1 for x in refs if x in v5_ids) / len(refs))
            row["api"] = api

        # v6：按 /api/ask 实际回答文本给要点覆盖率与禁用表述规避率打分
        mk, fk = c.get("must_keywords") or [], c.get("forbid_keywords") or []
        if mk or fk:
            atext = (api or {}).get("text", "")
            miss = [k for k in mk if k not in atext]
            bad = [k for k in fk if forbidden_hit(k, atext)]
            if mk:
                agg["kw_cover"].append((len(mk) - len(miss)) / len(mk))
            agg["kw_avoid"].append(0.0 if bad else 1.0)
            row.update({"kw_missing": miss, "kw_forbidden_hit": bad})
            if miss or bad:
                kw_failures.append({"id": c["id"], "q": q,
                                    "missing_keywords": miss, "forbidden_hits": bad})

        # 弃答口径对齐线上：ask_local 仅在「未命中精编规则」时才采用检索器的 abstain
        if c.get("should_abstain") is not None:
            # v6：以线上实际行为为准（含 force_abstain 的穷举 / 缺数据意图）
            effective_abstain = (api or {}).get("mode") == "abstain"
            ok = 1.0 if effective_abstain == bool(c["should_abstain"]) else 0.0
            agg["abstain"].append(ok)
            row["abstain_correct"] = ok
            row["effective_abstain"] = effective_abstain

        # 角色分诊以线上实际返回的 routed 为准（规则命中时采用规则指定角色）
        expected_role = c.get("expected_role")
        if expected_role:
            got = (api or {}).get("role") or server.route_role(q)
            ok = 1.0 if got == expected_role else 0.0
            agg["role"].append(ok)
            row.update({"role_expected": expected_role, "role_got": got, "role_correct": ok})
        rows.append(row)

    def avg(key):
        v = agg[key]
        return round(sum(v) / len(v), 4) if v else None

    summary = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "kb_version": server.KB.get("kb_version"),
        "total_cases": len(cases),
        "auto_cases": sum(1 for c in cases if c["source"] == "auto"),
        "manual_cases": sum(1 for c in cases if c["source"] == "manual"),
        "graded_recall_cases": len(agg["recall5_v5"]),
        "api_available": agg["api_available"],
        "metrics": {
            "Recall@5 (legacy)": avg("recall5_legacy"),
            "Recall@5 (v5)": avg("recall5_v5"),
            "MRR (legacy)": avg("mrr_legacy"),
            "MRR (v5)": avg("mrr_v5"),
            "引用正确率(refs 在 v5 Top8)": avg("citation_align"),
            "弃答正确率": avg("abstain"),
            "角色分诊准确率": avg("role"),
            "规则命中率": avg("rule_hit"),
            "要点覆盖率": avg("kw_cover"),
            "禁用表述规避率": avg("kw_avoid"),
        },
    }
    r0, r1 = summary["metrics"]["Recall@5 (legacy)"], summary["metrics"]["Recall@5 (v5)"]
    m0, m1 = summary["metrics"]["MRR (legacy)"], summary["metrics"]["MRR (v5)"]
    summary["delta"] = {
        "Recall@5": round((r1 - r0), 4) if r0 is not None and r1 is not None else None,
        "MRR": round((m1 - m0), 4) if m0 is not None and m1 is not None else None,
    }
    # 未达标清单（Recall@5 未命中或弃答/角色误判）
    failures = []
    for row in rows:
        why = []
        if row.get("recall_v5") == 0.0:
            why.append("检索 Top5 未命中期望条目")
        if row.get("abstain_correct") == 0.0:
            why.append("弃答判定与标注不符")
        if row.get("role_correct") == 0.0:
            why.append(f"角色分诊 {row.get('role_got')} ≠ 期望 {row.get('role_expected')}")
        if why:
            failures.append({"id": row["id"], "q": row["q"], "issues": why,
                             "v5_top5": row["v5_top5"], "must_refs": row["must_refs"]})
    summary["failure_count"] = len(failures)
    summary["failures"] = failures
    summary["keyword_failure_count"] = len(kw_failures)
    summary["keyword_failures"] = kw_failures

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, ensure_ascii=False, indent=1)

    # 落库（表由 build_v5.py 创建）
    if os.path.exists(DB_PATH):
        try:
            con = sqlite3.connect(DB_PATH)
            cur = con.execute(
                "INSERT INTO eval_run(run_at,kb_version,total_cases,metrics_json) VALUES (?,?,?,?)",
                (summary["run_at"], summary["kb_version"], len(cases),
                 json.dumps(summary, ensure_ascii=False)))
            rid = cur.lastrowid
            for k, v in summary["metrics"].items():
                if v is not None:
                    con.execute(
                        "INSERT INTO eval_result(run_id,metric,value) VALUES (?,?,?)", (rid, k, v))
            con.commit()
            con.close()
        except sqlite3.Error as ex:
            print(f"[warn] 评测结果落库失败：{ex}")

    print("=== Golden QA 量化评测 ===")
    print(f"  评测集 {len(cases)} 题（自动 {summary['auto_cases']} + 手工 {summary['manual_cases']}）")
    print(f"  可评分检索题 {summary['graded_recall_cases']} 题 | API 可用 {summary['api_available']} 题")
    for k, v in summary["metrics"].items():
        print(f"  {k}: {v}")
    print(f"  前后提升：Recall@5 {summary['delta']['Recall@5']} | MRR {summary['delta']['MRR']}")
    print(f"  未达标 {len(failures)} 题 -> 见报告 failures 明细")
    print(f"[ok] -> {OUT}")
    return summary


if __name__ == "__main__":
    main()
