#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_trust.py — 可信度引擎回归测试
=================================

覆盖 trust.py 四层防线的核心行为：
  L1 到期/废止硬闸、核验衰减
  L2 权威层级排序、冲突检测
  L3 数字/文号/条号幻觉溯源
  L4 信任分与 gate 分级

运行：python test_trust.py   （全部通过 exit 0，任一失败 exit 1）
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trust import (  # noqa: E402
    authority_rank, conflict_scan, expiry_state, extract_claims,
    freshness_factor, ground_claims, parse_verified_date, staleness_days,
    trust_report,
)

BASE = os.path.dirname(os.path.abspath(__file__))
KB = json.load(open(os.path.join(BASE, "kb.json"), encoding="utf-8"))
ENTRIES = KB["entries"]
BY_ID = {e["id"]: e for e in ENTRIES}

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def main():
    today = date.today()
    print("=== trust 引擎回归测试 ===")

    # ---------- L1 时效性 ----------
    print("[L1 时效性]")
    e_expired = BY_ID["07-7.8"]           # 2025 历史文件，status 已废止
    r = trust_report("稳岗返还", "中小微返还比例 60%。", [e_expired], ENTRIES, today=today)
    check("废止条目触发 block 硬闸", r["gate"] == "block", f"gate={r['gate']}")
    check("废止条目列入 expired 名单", "07-7.8" in r["timeliness"]["expired"])

    # 南沙 15%（expiring，2026-12-31）
    e_nansha = BY_ID.get("20-20.16")
    if e_nansha:
        es = expiry_state(e_nansha, today)
        check("南沙条目识别为 expiring/valid", es in ("expiring", "valid"), f"state={es}")

    # 核验衰减：伪造 200 天前核验
    e_stale = dict(BY_ID["01-1.1"], verified_at="2026-03-01 测试")
    check("200 天前核验 freshness<0.5", freshness_factor(e_stale, today) < 0.5,
          f"f={freshness_factor(e_stale, today)}")
    check("staleness_days>180", (staleness_days(e_stale, today) or 0) > 180)

    # 解释层不做硬闸
    e_meta = next((e for e in ENTRIES if e.get("entry_type") in ("concept", "relation")), None)
    if e_meta:
        check("解释层条目 expiry_state=unknown", expiry_state(e_meta, today) == "unknown")

    # ---------- L2 权威性 ----------
    print("[L2 权威性]")
    r1, _ = authority_rank(BY_ID["01-1.1"])       # 法律
    r2, _ = authority_rank(BY_ID.get("24-24.3", BY_ID["01-1.1"]))   # 行政法规+规范性
    check("法律层级 rank=1", r1 == 1, f"rank={r1}")
    check("行政法规 rank<=2", r2 <= 2, f"rank={r2}")
    e_concept = next((e for e in ENTRIES if e.get("entry_type") == "concept"), None)
    if e_concept:
        rc, _ = authority_rank(e_concept)
        check("概念层 rank=6", rc == 6, f"rank={rc}")

    # 冲突检测：同名不同文号
    fake_a = {"id": "T-A", "title": "测试文件", "doc_no": "财税〔2020〕1 号",
              "status": "现行有效", "entry_type": "regulation", "fields": {}}
    fake_b = {"id": "T-B", "title": "测试文件", "doc_no": "财税〔2022〕2 号",
              "status": "现行有效", "entry_type": "regulation", "fields": {}}
    cw = conflict_scan([fake_a, fake_b])
    check("同名不同文号触发 doc_no_conflict",
          any(c["type"] == "doc_no_conflict" for c in cw), f"conflicts={cw}")

    # 状态冲突：一废一现
    fake_c = {"id": "T-C", "title": "另一文件", "doc_no": "", "status": "已废止",
              "entry_type": "regulation", "fields": {}}
    fake_d = {"id": "T-D", "title": "另一文件", "doc_no": "", "status": "现行有效",
              "entry_type": "regulation", "fields": {}}
    cw2 = conflict_scan([fake_c, fake_d])
    check("一废一现触发 status_conflict",
          any(c["type"] == "status_conflict" for c in cw2))

    # ---------- L3 幻觉检测 ----------
    print("[L3 幻觉检测]")
    claims = extract_claims("适用 13% 税率，依据财税〔2024〕1 号公告第三条")
    check("抽取百分比 13%", "13%" in claims["percentages"], str(claims["percentages"]))
    check("抽取文号", any("2024" in d for d in claims["doc_nos"]), str(claims["doc_nos"]))
    check("抽取条号 第三条", "第三条" in claims["articles"])

    # 伪造数字必须 ungrounded
    e_vat = BY_ID["23-23.1"] if "23-23.1" in BY_ID else ENTRIES[0]
    g = ground_claims("税率 99.9%，另见财税〔2019〕999 号", [e_vat], ENTRIES)
    check("伪造百分比 99.9% 判 ungrounded",
          any(u["value"] == "99.9%" for u in g["ungrounded"]), str(g["ungrounded"]))
    check("伪造文号判 ungrounded",
          any("999" in u["value"] for u in g["ungrounded"]))

    # 真实数字必须 grounded 或 kb_grounded
    g2 = ground_claims("一般纳税人适用 13% 税率", [e_vat], ENTRIES)
    check("13% 能溯源（grounded 或 kb_grounded）",
          g2["coverage"] + g2["kb_coverage"] >= 1.0 or
          all(x["value"] != "13%" for x in g2["ungrounded"]),
          f"cov={g2['coverage']} kbcov={g2['kb_coverage']}")

    # coverage 计算
    g3 = ground_claims("增值税税率 13%。", [e_vat], ENTRIES)
    check("coverage 在 [0,1]", 0.0 <= g3["coverage"] <= 1.0)

    # ---------- L4 聚合 ----------
    print("[L4 聚合 gate]")
    # 幻觉文本 → block
    r_hallu = trust_report("增值税", "适用 37.5% 加计抵减，依据财税〔2019〕99 号。",
                           [e_vat], ENTRIES, today=today)
    check("幻觉文本触发 block", r_hallu["gate"] == "block", f"gate={r_hallu['gate']}")
    check("ungrounded_claims 非空", len(r_hallu["ungrounded_claims"]) > 0)

    # 正常文本（无幻觉、A 层引用）→ allow 或 warn
    e_a = next((e for e in ENTRIES if e.get("tier") == "A" and e.get("sources")
                and e.get("status") == "现行有效"
                and expiry_state(e, today) == "unknown"), None)
    if e_a:
        safe_text = f"依据《{e_a['title'][:20]}》相关规定执行。"
        r_ok = trust_report("一般规定", safe_text, [e_a], ENTRIES, today=today)
        check("正常回答 gate 非 block", r_ok["gate"] in ("allow", "warn"),
              f"gate={r_ok['gate']} score={r_ok['trust_score']}")
        check("正常回答信任分 >= 0.6", r_ok["trust_score"] >= 0.6,
              f"score={r_ok['trust_score']}")

    # 空引用
    r_none = trust_report("任意", "没有引用任何条目。", [], ENTRIES, today=today)
    check("空引用不崩溃", isinstance(r_none["trust_score"], float))

    # trust_report 字段完整性
    keys = {"version", "trust_score", "gate", "timeliness", "authority",
            "grounding", "conflicts", "warnings", "ungrounded_claims"}
    check("trust_report 字段齐全", keys.issubset(r_hallu.keys()),
          str(set(r_hallu.keys()) ^ keys))

    print(f"\n=== 测试汇总: {PASS} 通过 / {FAIL} 失败 ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
