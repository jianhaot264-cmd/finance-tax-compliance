#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trust.py — 可信度引擎 v1（生产级）
=================================

目标：解决「法规时效性、幻觉、数据权威性、更新机制」四大生产级难题。

四层防线：
  L1 时效性（Timeliness）  核验过期衰减 + 到期硬闸 + 复核期限
  L2 权威性（Authority）   效力层级排序 + 新旧冲突裁决（后法优于前法）
  L3 幻觉检测（Grounding） 生成文本逐「数字 / 文号 / 条号 / 百分比」溯源
  L4 聚合（Aggregate）     信任分 + 分级告警 + 不可引用闸门

设计原则：
  - 只读不改知识库本体，所有判定都是纯函数，可单测、可复现
  - 「无法证明为真」≠「证伪」，ungrounded 是「需人工复核」而非「错误」
  - 过期与废止是硬闸（不作现行依据）；其他问题降置信度 + 注明
  - 不承诺 100%：输出 trust_report 带 confidence 与 evidence 字段

用法：
  from trust import trust_report
  report = trust_report(q, answer_text, cited_entries, today="2026-11-08")
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

__all__ = [
    "parse_verified_date", "staleness_days", "authority_rank", "expiry_state",
    "extract_claims", "ground_claims", "conflict_scan", "trust_report",
    "AUTHORITY_LEVELS", "TRUST_VERSION",
]

TRUST_VERSION = "trust-v1.0"

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 效力层级：数值越小越权威（1=法律 … 6=解释层）
AUTHORITY_LEVELS = {
    "宪法": 1,
    "法律": 1,
    "行政法规": 2,
    "司法解释": 2,
    "部门规章": 3,
    "地方性法规": 3,
    "地方政府规章": 4,
    "规范性文件": 5,
    "税务规范性文件": 5,
    "部门规范性文件": 5,
    "通知": 5,
    "公告": 5,
    "解释层": 6,
    "概念层": 6,
    "汇编": 6,
}

# 核验保鲜期（天）：超过则衰减置信度；超过硬期限则强制标注「需复核」
FRESH_DAYS = 30          # 30 天内视为新鲜
STALE_DAYS = 90          # 90 天以上显著衰减
HARD_RECHECK_DAYS = 180  # 180 天未复核强制标注

# 到期预警阈值
EXPIRY_WARN_DAYS = 90    # 90 天内到期 → 预警

# 数字 / 文号 / 条号抽取
DOC_NO_RE = re.compile(
    r"(?:财政部|国家税务总局|税务总局|国务院|人力资源社会保障部|人社部|海关总署|发改委|工信部|住建部)?"
    r"(?:\s*(?:、|和|及)\s*(?:国家税务总局|财政部))?"
    r"\s*(?:公告|通知|函|批复|决定|令|发)"
    r"[\s〔\[]*\d{4}[\s〕\]]*年第?\s*\d+\s*号"
    r"|国发〔\d{4}〕\d+\s*号"
    r"|财税〔\d{4}〕\d+\s*号"
    r"|国办发〔\d{4}〕\d+\s*号"
    r"|人社部发〔\d{4}〕\d+\s*号"
    r"|第\s*\d+\s*号令"
    r"|\d+\s*号令"
)
DOC_NO_CLEAN_RE = re.compile(r"[\s　]+")

PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
AMOUNT_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:元|万元|亿元)")
ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百千0-9]+条")
LAW_NAME_RE = re.compile(
    r"《[^》]{4,60}》"
)

# 停用数字（容易误报的通用数字）
NUM_STOPWORDS = {"18", "10", "5", "3", "1", "2", "4", "6", "7", "8", "9", "2026", "2025", "2027", "2024", "0", "12", "100"}


# ---------------------------------------------------------------------------
# L1 时效性
# ---------------------------------------------------------------------------

def parse_verified_date(entry: dict) -> date | None:
    """从 verified_at 字段解析核验日期（支持 '2026-11-07 权威库回库…' 形式）。"""
    raw = entry.get("verified_at") or ""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_expiry_date(entry: dict) -> date | None:
    """解析到期日（expiry_date 顶层字段）。"""
    raw = entry.get("expiry_date") or entry.get("fields", {}).get("到期日") or ""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(raw))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def staleness_days(entry: dict, today: date | None = None) -> int | None:
    """距上次核验的天数；无核验日期返回 None。"""
    today = today or date.today()
    vd = parse_verified_date(entry)
    if vd is None:
        return None
    return (today - vd).days


def freshness_factor(entry: dict, today: date | None = None) -> float:
    """新鲜度系数 1.0 → 0.4：线性衰减，90 天内 1.0→0.7，180 天 0.4 封底。"""
    sd = staleness_days(entry, today)
    if sd is None:
        return 0.5      # 无核验日期 → 中性偏弱
    if sd <= FRESH_DAYS:
        return 1.0
    if sd >= HARD_RECHECK_DAYS:
        return 0.4
    # 线性：FRESH(30)→1.0，HARD(180)→0.4
    return round(1.0 - 0.6 * (sd - FRESH_DAYS) / (HARD_RECHECK_DAYS - FRESH_DAYS), 3)


def expiry_state(entry: dict, today: date | None = None) -> str:
    """
    到期状态：
      'expired'  已过到期日（硬闸，不得作现行依据）
      'expiring' 90 天内到期（预警）
      'valid'    有效期内
      'unknown'  无到期日
    """
    today = today or date.today()
    # 解释层/关系卡/场景卡是「说明到期规则」的元条目，其日期是被描述对象的到期日，
    # 不是本条目自身的政策有效期 → 不做硬闸。
    etype = (entry.get("entry_type") or "").lower()
    if etype in ("concept", "relation", "scenario", "verification", "digest"):
        return "unknown"
    ed = parse_expiry_date(entry)
    if ed is None:
        return "unknown"
    if ed < today:
        return "expired"
    if (ed - today).days <= EXPIRY_WARN_DAYS:
        return "expiring"
    return "valid"


# ---------------------------------------------------------------------------
# L2 权威性
# ---------------------------------------------------------------------------

def authority_rank(entry: dict) -> tuple[int, str]:
    """
    返回 (rank, matched_label)：rank 1 最权威。
    level 字段可能含多个（如「法律 + 行政法规」），取最权威者。
    解释层 / 概念层 / 汇编型强制为 6。
    """
    # 条目类型先验
    etype = (entry.get("entry_type") or "").lower()
    if etype in ("concept", "relation", "scenario", "verification"):
        return 6, "解释层"
    if etype == "digest":
        return 6, "汇编"
    level_raw = entry.get("level") or entry.get("fields", {}).get("效力层级") or ""
    best, label = 6, "未知层级"
    for key, rank in AUTHORITY_LEVELS.items():
        if key in level_raw and rank < best:
            best, label = rank, key
    if best == 6 and level_raw.strip():
        # 有层级文字但未命中词表 → 给 5（保守）
        return 5, level_raw[:12]
    return best, label


def tier_authority_boost(tier: str) -> float:
    """tier A/B1/B2 的权威性加成（与层级互补）。"""
    return {"A": 1.0, "B1": 0.85, "B2": 0.7}.get(tier or "", 0.6)


# ---------------------------------------------------------------------------
# L3 幻觉检测（生成文本逐项溯源）
# ---------------------------------------------------------------------------

def extract_claims(text: str) -> dict:
    """
    从生成文本抽取「可核验断言」：
      numbers     百分比（不含纯年份）
      amounts     金额
      doc_nos     文号（归一化空白）
      articles    条号
      law_names   法规名称
    """
    t = str(text or "")
    percents = [p.replace(" ", "") for p in PERCENT_RE.findall(t)]
    amounts = AMOUNT_RE.findall(t)
    doc_nos = [DOC_NO_CLEAN_RE.sub("", d) for d in DOC_NO_RE.findall(t)]
    articles = list(dict.fromkeys(ARTICLE_RE.findall(t)))
    law_names = list(dict.fromkeys(LAW_NAME_RE.findall(t)))
    return {
        "percentages": list(dict.fromkeys(percents)),
        "amounts": list(dict.fromkeys(amounts)),
        "doc_nos": list(dict.fromkeys(doc_nos)),
        "articles": articles,
        "law_names": law_names,
    }


def _entry_text_blob(entry: dict) -> str:
    """条目的可检索全文（字段 + 正文）。"""
    f = entry.get("fields") or {}
    parts = [
        entry.get("title", ""), entry.get("body_md", "") or "",
        entry.get("search_text", "") or "", entry.get("doc_no", "") or "",
        f.get("核心条款", ""), f.get("合规要点", ""), f.get("文号", ""),
        entry.get("source_text", "") or "",
    ]
    return "\n".join(parts)


def ground_claims(answer_text: str, cited_entries: list[dict],
                  all_entries: list[dict] | None = None) -> dict:
    """
    把生成文本中的每个「数字/文号/条号/法规名」映射到出处。

    三档结果：
      grounded      在「被引条目」全文中找到
      kb_grounded   不在被引条目，但在知识库其他条目中找到（引用遗漏，可补）
      ungrounded    知识库中完全找不到（疑似幻觉，必须人工复核）

    覆盖率 coverage = grounded / total_claims（不含金额，金额常来自题目）
    """
    claims = extract_claims(answer_text)
    cited_blob = "\n".join(_entry_text_blob(e) for e in cited_entries)
    kb_blob = cited_blob
    if all_entries is not None:
        kb_blob = "\n".join(_entry_text_blob(e) for e in all_entries)

    def classify(val: str, kind: str) -> str:
        v = val.replace(" ", "")
        if not v:
            return "skip"
        if kind == "percentage" and v.rstrip("%") in NUM_STOPWORDS:
            return "skip"
        if v in cited_blob.replace(" ", ""):
            return "grounded"
        if v in kb_blob.replace(" ", ""):
            return "kb_grounded"
        return "ungrounded"

    result = {"grounded": [], "kb_grounded": [], "ungrounded": [], "skipped": 0}
    checked = 0
    for kind, key in [("percentage", "percentages"), ("doc_no", "doc_nos"),
                      ("article", "articles"), ("law_name", "law_names")]:
        for v in claims[key]:
            st = classify(v, kind)
            if st == "skip":
                result["skipped"] += 1
                continue
            checked += 1
            result[st].append({"kind": kind, "value": v})
    result["total_checked"] = checked
    result["coverage"] = round(
        len(result["grounded"]) / checked, 3) if checked else 1.0
    result["kb_coverage"] = round(
        (len(result["grounded"]) + len(result["kb_grounded"])) / checked, 3
    ) if checked else 1.0
    return result


# ---------------------------------------------------------------------------
# L2b 冲突裁决
# ---------------------------------------------------------------------------

def conflict_scan(cited_entries: list[dict]) -> list[dict]:
    """
    检测被引条目间的潜在冲突：
      - 同一主题（标题高度重叠）但不同文号/不同到期状态
      - 已废止条目与现行条目并列引用
      - 低层级（5/6）条目与高层级（1/2）条目对同一数字给出不同口径
    输出告警列表，不自动裁决（裁决规则：后法优于前法、上位法优于下位法——由调用方提示用户）。
    """
    warnings = []
    n = len(cited_entries)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = cited_entries[i], cited_entries[j]
            # 状态冲突：一废一现
            sa = (a.get("status") or a.get("status_norm") or "")
            sb = (b.get("status") or b.get("status_norm") or "")
            if (sa == "已废止") != (sb == "已废止"):
                warnings.append({
                    "type": "status_conflict",
                    "entries": [a["id"], b["id"]],
                    "msg": f"条目 {a['id']}（{sa or '状态未知'}）与 {b['id']}（{sb or '状态未知'}）并列引用，"
                           f"须以现行有效者为准（后法优于前法）",
                })
            # 文号冲突：同题不同文号
            ta = re.sub(r"[（(].*?[）)]", "", a.get("title", ""))
            tb = re.sub(r"[（(].*?[）)]", "", b.get("title", ""))
            if ta == tb:
                na = a.get("doc_no") or a.get("fields", {}).get("文号", "") or ""
                nb = b.get("doc_no") or b.get("fields", {}).get("文号", "") or ""
                if na and nb and DOC_NO_CLEAN_RE.sub("", na) != DOC_NO_CLEAN_RE.sub("", nb):
                    warnings.append({
                        "type": "doc_no_conflict",
                        "entries": [a["id"], b["id"]],
                        "msg": f"同名条目 {a['id']} 与 {b['id']} 文号不一致（{na} vs {nb}），"
                               f"须核对是否为修订版本",
                    })
            # 层级冲突：数字口径可能不同（百分比集合不一致）
            pa = set(extract_claims(_entry_text_blob(a))["percentages"])
            pb = set(extract_claims(_entry_text_blob(b))["percentages"])
            ra, _ = authority_rank(a)
            rb, _ = authority_rank(b)
            if pa and pb and not (pa & pb) and abs(ra - rb) >= 2 and (ra <= 3 or rb <= 3):
                warnings.append({
                    "type": "rate_divergence",
                    "entries": [a["id"], b["id"]],
                    "msg": f"条目 {a['id']} 与 {b['id']} 的百分比口径不重叠（{sorted(pa)[:3]} vs {sorted(pb)[:3]}），"
                           f"上位法/后法优先，回答时须说明依据哪一条",
                })
    return warnings


# ---------------------------------------------------------------------------
# L4 聚合信任分
# ---------------------------------------------------------------------------

def trust_report(q: str, answer_text: str, cited_entries: list[dict],
                 all_entries: list[dict] | None = None,
                 today: date | None = None, mode: str = "") -> dict:
    """
    聚合四层判定，产出：

    {
      "version": "trust-v1.0",
      "trust_score": 0.0-1.0,
      "gate": "allow" | "warn" | "block",
      "timeliness": {...},
      "authority": {...},
      "grounding": {...},
      "conflicts": [...],
      "warnings": [str],          # 面向用户的中文提示
      "ungrounded_claims": [...], # 疑似幻觉，必须人工复核
    }

    gate 语义：
      allow  可正常引用
      warn   可引用但须附限制说明（过期核验 / B 层 / 覆盖率偏低 / 冲突）
      block  硬闸：引用了已废止或已过期条目，或 ungrounded 数字/文号
    """
    today = today or date.today()
    warnings: list[str] = []
    ungrounded: list[dict] = []

    # ---- L1 时效性 ----
    expired, expiring, stale = [], [], []
    for e in cited_entries:
        es = expiry_state(e, today)
        st = (e.get("status") or e.get("status_norm") or "")
        if es == "expired" or st == "已废止":
            expired.append(e["id"])
        elif es == "expiring":
            expiring.append(e["id"])
        sd = staleness_days(e, today)
        if sd is not None and sd > HARD_RECHECK_DAYS:
            stale.append((e["id"], sd))
        elif sd is None and (e.get("tier") == "A"):
            stale.append((e["id"], -1))   # A 层无核验日期也提示
    timeliness = {
        "expired": expired, "expiring": expiring, "stale": stale,
        "freshness": round(sum(freshness_factor(e, today) for e in cited_entries) / len(cited_entries), 3)
        if cited_entries else 1.0,
    }
    if expired:
        warnings.append(
            f"⚠️ 引用条目含已废止/已过期依据（{('、'.join(expired[:3]))}），不得作为现行规定，"
            f"须核对是否有延续/替代文件（后法优于前法）")
    if expiring:
        warnings.append(
            f"⏳ 引用条目即将到期（{('、'.join(expiring[:3]))}），适用期须核对官方最新公告")
    if stale:
        warnings.append(
            f"🕐 {len(stale)} 条引用距上次核验已超 {HARD_RECHECK_DAYS} 天，建议按 SOURCES-CHANNELS.md 回查原文")

    # ---- L2 权威性 ----
    ranks = []
    for e in cited_entries:
        r, label = authority_rank(e)
        ranks.append({"id": e["id"], "rank": r, "level": label,
                      "tier": e.get("tier", "")})
    min_rank = min((r["rank"] for r in ranks), default=6)
    authority = {
        "ranks": ranks,
        "min_rank": min_rank,
        "has_authoritative": min_rank <= 2,   # 有法律/行政法规级引用
        "tier_mix": {t: sum(1 for r in ranks if r["tier"] == t) for t in ("A", "B1", "B2")},
    }
    if min_rank >= 5:
        warnings.append("📄 回答仅有规范性文件/解释层依据，未引用法律或行政法规，建议补充上位法依据")

    # ---- L3 幻觉检测 ----
    grounding = ground_claims(answer_text, cited_entries, all_entries)
    ungrounded = grounding["ungrounded"]
    if ungrounded:
        warnings.append(
            f"🔴 有 {len(ungrounded)} 处数字/文号/条号未能在知识库中找到出处"
            f"（{('、'.join(u['value'][:16] for u in ungrounded[:3]))} 等），"
            f"疑似生成幻觉，请人工复核或以官方原文为准")
    if grounding["kb_grounded"] and mode != "rule":
        warnings.append(
            f"📎 有 {len(grounding['kb_grounded'])} 处断言的依据在知识库中存在但未列入本次引用，已可补引")

    # ---- L2b 冲突 ----
    conflicts = conflict_scan(cited_entries)
    for c in conflicts:
        warnings.append("⚔️ " + c["msg"])

    # ---- 聚合信任分 ----
    # 权重：grounding 0.40 + 时效 0.25 + 权威 0.20 + 无冲突 0.15
    g_score = grounding["coverage"]
    t_score = timeliness["freshness"]
    a_score = {1: 1.0, 2: 0.92, 3: 0.8, 4: 0.7, 5: 0.58, 6: 0.45}.get(min_rank, 0.5)
    c_score = 1.0 if not conflicts else max(0.4, 1.0 - 0.18 * len(conflicts))
    trust_score = round(0.40 * g_score + 0.25 * t_score + 0.20 * a_score + 0.15 * c_score, 3)

    # ---- gate ----
    if expired or ungrounded or any(c["type"] == "status_conflict" for c in conflicts):
        gate = "block"
    elif (expiring or stale or grounding["coverage"] < 0.85 or conflicts
          or authority["tier_mix"].get("B1", 0) + authority["tier_mix"].get("B2", 0) > 0):
        gate = "warn"
    else:
        gate = "allow"

    return {
        "version": TRUST_VERSION,
        "trust_score": trust_score,
        "gate": gate,
        "timeliness": timeliness,
        "authority": authority,
        "grounding": grounding,
        "conflicts": conflicts,
        "warnings": warnings,
        "ungrounded_claims": ungrounded,
    }


# ---------------------------------------------------------------------------
# CLI：抽查知识库条目的可信度画像
# ---------------------------------------------------------------------------

def _cli():
    import json, os, sys
    base = os.path.dirname(os.path.abspath(__file__))
    kb_path = os.path.join(base, "kb.json")
    if not os.path.isfile(kb_path):
        print("kb.json not found"); return
    kb = json.load(open(kb_path, encoding="utf-8"))
    entries = kb["entries"]
    today = date.today()
    print(f"=== trust 可信度画像  {today}  条目 {len(entries)} ===")
    expired = [e for e in entries if expiry_state(e, today) == "expired"]
    expiring = [e for e in entries if expiry_state(e, today) == "expiring"]
    stale = [e for e in entries if (staleness_days(e, today) or 0) > HARD_RECHECK_DAYS]
    no_src = [e for e in entries if len(e.get("sources") or []) == 0 and e.get("tier") == "A"]
    print(f"  已过期(硬闸)  {len(expired)}: {[e['id'] for e in expired][:8]}")
    print(f"  即将到期      {len(expiring)}: {[e['id'] for e in expiring][:8]}")
    print(f"  核验超期      {len(stale)}")
    print(f"  A层无信源     {len(no_src)}: {[e['id'] for e in no_src][:8]}")
    # 权威层级分布
    from collections import Counter
    dist = Counter(authority_rank(e)[1] for e in entries)
    print("  层级分布:", dict(dist.most_common(10)))


if __name__ == "__main__":
    _cli()
