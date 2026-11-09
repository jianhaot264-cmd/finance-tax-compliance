# -*- coding: utf-8 -*-
"""test_external_lookup.py — 自适应检索策略 v1 的离线回归测试（不依赖网络）。

覆盖：渠道准入、触发/不触发判定、fixture 检索、双源交叉、证据块、
      失败兜底、冲突留痕、检索日志。网络层用 fixtures 注入，可完全离线运行。
"""
import os
import sqlite3
import sys
import tempfile
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import external_lookup as ex

RESULTS = []


def check(name, cond, detail=""):
    ok = bool(cond)
    RESULTS.append(ok)
    print(("  PASS " if ok else "  FAIL ") + name + (("  | " + str(detail)) if detail else ""), flush=True)


def main():
    today = date(2026, 11, 9)
    off = {"enabled": False}
    on = {"enabled": True, "timeout": 3.0}
    empty_local = {"mode": "retrieval", "risk": "low"}
    good_retrieval = {"abstain": False, "confidence": 0.82, "hits": [{"id": "16-16.3"}]}
    hit = [{"id": "16-16.3", "tier": "A", "status": "现行有效",
            "verified_at": "2026-11-09", "expiry_date": "", "fields": {}}]

    print("=== [L0] 渠道白名单准入 ===")
    check("A 级：财政部会计司", ex.classify_source("https://kjs.mof.gov.cn/zhengcefabu/") == "A")
    check("A 级：税务总局政策法规库", ex.classify_source("https://fgk.chinatax.gov.cn/zcfgk/index.html") == "A")
    check("A 级：国家法律法规数据库", ex.classify_source("https://flk.npc.gov.cn/") == "A")
    check("B 级：税务总局解读", ex.classify_source("https://www.chinatax.gov.cn/chinatax/n810341/") == "B")
    check("C 级：12366", ex.classify_source("https://12366.chinatax.gov.cn/") == "C")
    check("E 级：非白名单来源被拒", ex.classify_source("https://example.com/fake") == "E")
    r = ex.fetch_official("https://example.com/fake", timeout=1, retries=1)
    check("非白名单 URL 不发请求", r.get("ok") is False and "拒绝" in r.get("error", ""))
    import trust
    gate = trust.source_gate([
        {"url": "https://www.gov.cn/zhengce/", "excerpt": "A 级官方"},
        {"url": "https://12366.chinatax.gov.cn/", "excerpt": "C 级执行口径"},
    ])
    check("L0：C 级渠道不进结论", len(gate["rejected"]) == 1 and gate["dual"] is False)
    check("L0：未达双源给出提示", any("双源" in w for w in gate["warnings"]))

    print("\n=== [决策] 不触发（NEVER） ===")
    check("开关关闭默认不检索",
          ex.should_lookup("最新增值税税率", empty_local, good_retrieval, hit, off, today)["need"] is False)
    for m in ("rule", "calc", "clarify"):
        d = ex.should_lookup("最新税率", {"mode": m, "risk": "low"}, good_retrieval, hit, on, today)
        check(f"{m} 类直接走既有链路", d["need"] is False, d["reason"])
    for q in ("火星注册公司要交什么税", "逐一列出全部条款", "只按知识库回答，不要联网"):
        d = ex.should_lookup(q, empty_local, good_retrieval, hit, on, today)
        check(f"超范围/穷举/离线要求不触发：{q[:8]}", d["need"] is False)
    d = ex.should_lookup("虚开怎么补救", {"mode": "retrieval", "risk": "high"},
                         good_retrieval, hit, on, today)
    check("高风险事项不检索", d["need"] is False)

    print("\n=== [决策] 三类触发信号 ===")
    d = ex.should_lookup("2027 年这项优惠是否延续", empty_local, good_retrieval, hit, on, today)
    check("TIME：时效词触发", d["need"] and any(s.startswith("TIME") for s in d["signals"]), d["signals"])
    d = ex.should_lookup("常规问题", empty_local, {"abstain": True, "confidence": 0.2, "hits": []},
                         [], on, today)
    check("COVERAGE：弃答 + 无命中触发", d["need"] and any(s.startswith("COVERAGE") for s in d["signals"]))
    d = ex.should_lookup("这项政策不是已经取消了吗", empty_local, good_retrieval, hit, on, today)
    check("CONFLICT：用户异说触发", d["need"] and any(s.startswith("CONFLICT") for s in d["signals"]))
    draft = [{"tier": "B2", "status": "草案阶段", "verified_at": "2026-01-01",
              "expiry_date": "2026-12-31", "fields": {"时效性": "待核验"}}]
    d = ex.should_lookup("常规问题", empty_local, good_retrieval, draft, on, today)
    check("TIME+COVERAGE：草案/到期/待核验/超 30 天", len(d["signals"]) >= 3, d["signals"])
    d = ex.should_lookup("增值税进项抵扣", empty_local, good_retrieval, hit, on, today)
    check("无信号时不检索（行为不变）", d["need"] is False, d["reason"])

    print("\n=== [核验] fixture 注入与双源交叉 ===")
    decision = {"need": True, "signals": ["TIME:时效词"], "reason": "test"}
    fixtures = [
        {"source": "财政部会计司政策发布", "url": "https://kjs.mof.gov.cn/zhengcefabu/",
         "excerpt": "关于印发《企业会计准则第30号——财务报表列报》的通知 2026-08-05"},
        {"source": "中国政府网政策文件库", "url": "https://www.gov.cn/zhengce/",
         "excerpt": "企业会计准则第30号 财务报表列报 财会〔2026〕11号"},
    ]
    res = ex.lookup("企业会计准则第30号最新", decision, fixtures=fixtures)
    check("fixture 检索命中", res["status"] == "hit" and len(res["evidence"]) == 2)
    check("两个独立官方域名 → 双源", res["cross"]["dual"] is True, res["cross"])
    res1 = ex.lookup("企业会计准则第30号", decision, fixtures=fixtures[:1])
    check("单源不判双源", res1["cross"]["dual"] is False and res1["status"] == "hit")
    check("单源 note 明确不得作确定结论", "单源" in res1["note"] and "不得" in res1["note"])

    print("\n=== [组装] 证据块 / 兜底 / 冲突 ===")
    block = ex.build_evidence_block(res, "2026-11-09")
    check("双源标记正确", "[外部核验·双源]" in block)
    check("证据块含来源与链接", "kjs.mof.gov.cn" in block and "核验" in block)
    check("证据块声明不改变知识库结论", "不改变知识库结论" in block)
    check("证据块禁止生成分录/筹划/税额", "不得据此生成分录" in block)
    block1 = ex.build_evidence_block(res1, "2026-11-09")
    check("单源证据块带限制", "[外部核验·单源]" in block1 and "不得作为确定结论" in block1)
    fb = ex.fallback_note("2026-11-09", {"status": "failed", "note": "网络不可达"})
    check("失败兜底：回落知识库", "回落到知识库快照" in fb)
    check("失败兜底：不作为否定证据", "不得把检索失败当作" in fb)
    check("失败兜底：不猜测补全", "不得猜测补全" in fb)
    cn = ex.conflict_note("知识库口径 A", "外部口径 B", "2026-11-09")
    check("冲突并列留痕", "不改写知识库结论" in cn and "回查官方原文" in cn)
    skip = ex.lookup("x", {"need": False, "reason": "开关关闭"}, fixtures=[])
    check("未触发时 lookup 跳过", skip["status"] == "skipped")

    print("\n=== [留痕] external_lookup_log ===")
    import shutil
    tmp_dir = tempfile.mkdtemp(prefix="wb-ext-lookup-")
    tmp = os.path.join(tmp_dir, "t.db")
    try:
        con = sqlite3.connect(tmp)
        con.execute("DROP TABLE IF EXISTS external_lookup_log")
        con.execute("""CREATE TABLE external_lookup_log
            (ts TEXT,q TEXT,need INTEGER,signals TEXT,status TEXT,sources TEXT,
             evidence_count INTEGER,note TEXT)""")
        con.commit()
        con.close()
        ex.log_external(tmp, "测试问题", decision, res)
        c2 = sqlite3.connect(tmp)
        n = c2.execute("SELECT COUNT(*) FROM external_lookup_log").fetchone()[0]
        c2.close()
        check("检索动作写入日志表", n == 1)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"\n=== 测试汇总: {sum(RESULTS)} 通过 / {len(RESULTS) - sum(RESULTS)} 失败 ===")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
