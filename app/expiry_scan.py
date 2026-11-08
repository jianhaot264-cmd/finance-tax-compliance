#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""expiry_scan.py — 政策到期雷达（可复现，纯标准库）。

用途：扫描 kb.json 中带「至/截至/执行至/有效期至/止于/到期」等提示的有效期日期，
按到期日分组输出 JSON + Markdown，用于 90/60/30 天三档预警。

用法：
    python expiry_scan.py                # 默认未来 800 天
    python expiry_scan.py --days 400     # 只看 400 天内
    python expiry_scan.py --all          # 含已到期
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
KB = os.path.join(BASE, "kb.json")
OUT_DIR = os.path.join(ROOT, "reports")

CUE = r"(?:至|截至|延长至|延至|执行至|执行期至|有效期至|有效至|止于|到期日?|截止)"
DATE = r"(20\d{2})\s*[-年/.]\s*(\d{1,2})\s*[-月/.]\s*(\d{1,2})"
PAT = re.compile(CUE + r"\s*[:：]?\s*" + DATE)
BARE_YEAREND = re.compile(r"(20\d{2})-12-31")
STATUS_FIELD_HINT = ("时效性", "生效状态")


def norm(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def snippet(text, start, end, pad=26):
    a = max(0, start - pad)
    b = min(len(text), end + pad)
    s = text[a:b].replace("\n", " ").replace("|", "/")
    s = re.sub(r"\s+", " ", s).strip()
    return ("…" if a > 0 else "") + s + ("…" if b < len(text) else "")


def collect(entry):
    """返回 [(date, snippet, source_field)]"""
    out, seen = [], set()
    fields = entry.get("fields", {}) or {}
    for k, v in fields.items():
        if not isinstance(v, str):
            continue
        # 「截至」是「截至某日的情况」而非到期日，等长替换后再匹配，避免误报
        vt = v.replace("截至", "□□")
        # 时效性字段：任何 YYYY-MM-DD 都算候选
        if any(h in k for h in STATUS_FIELD_HINT):
            for m in re.finditer(DATE, vt):
                d = norm(*m.groups())
                if d and (d, "时效性") not in seen:
                    seen.add((d, "时效性"))
                    out.append((d, snippet(v, m.start(), m.end()), "时效性"))
            continue
        for m in PAT.finditer(vt):
            g = m.groups()
            d = norm(g[0], g[1], g[2])
            if d and (d, k) not in seen:
                seen.add((d, k))
                out.append((d, snippet(v, m.start(), m.end()), k))
    # 兜底：正文里显著的「YYYY-12-31」且带 2027/2026 年份
    body = entry.get("body_md", "") or ""
    for m in BARE_YEAREND.finditer(body[:4000]):
        d = norm(m.group(1), 12, 31)
        if d and (d, "正文") not in seen and re.search(r"(至|到|止|期)", body[max(0, m.start() - 8):m.start()]):
            seen.add((d, "正文"))
            out.append((d, snippet(body, m.start(), m.end()), "正文"))
    return out


def bucket(days):
    if days < 0:
        return "已到期"
    if days <= 90:
        return "90 天内"
    if days <= 180:
        return "91–180 天"
    if days <= 365:
        return "181–365 天"
    return "365 天以上"


def action_for(days):
    if days < 0:
        return "已到期：核对是否仍有过渡期或已续期"
    if days <= 30:
        return "**本月内**确认是否延续（查财政部/总局/省政府最新文件）"
    if days <= 60:
        return "启动税负测算与替代方案，锁定合同条款"
    if days <= 90:
        return "列入下一年度预算与合同评审"
    return "跟踪即可，季度复核"


def keyset(payload):
    return {(it["id"], it["date"]) for g in payload.get("groups", []) for it in g.get("items", [])}


def find_prev(monthly_dir, stem):
    """上一个月的快照（文件名 < 当前 stem 的最大者）。"""
    cands = [f for f in os.listdir(monthly_dir)
             if f.endswith(".json") and f[:-5] < stem]
    if not cands:
        return None, None
    fn = sorted(cands)[-1]
    try:
        with open(os.path.join(monthly_dir, fn), encoding="utf-8") as f:
            return json.load(f), fn
    except Exception:
        return None, None


def uniq_rows(rows):
    """同一 (条目, 日期) 只保留一条：优先 A 层、现行有效、摘录更长者。"""
    def rank(r):
        return (r["tier"] == "A", r["status"] == "现行有效", len(r["snippet"]))
    best = {}
    for r in rows:
        k = (r["id"], r["date"])
        if k not in best or rank(r) > rank(best[k]):
            best[k] = r
    return sorted(best.values(), key=lambda r: (r["date"], r["id"]))


def write_monthly(payload, rows, today, label=""):
    m_dir = os.path.join(OUT_DIR, "policy-radar")
    os.makedirs(m_dir, exist_ok=True)
    stem = f"policy-radar-{today:%Y-%m}"
    prev, prev_name = find_prev(m_dir, stem)

    raw_n = len(rows)
    rows = [r for r in uniq_rows(rows) if r["status"] != "已废止"]
    cur_keys = keyset(payload)
    if prev:
        prev_keys = keyset(prev)
        new_items = [r for r in rows if (r["id"], r["date"]) not in prev_keys]
        gone_keys = prev_keys - cur_keys
        gone_items = [it for g in prev.get("groups", []) for it in g.get("items", [])
                      if (it["id"], it["date"]) in gone_keys]
    else:
        new_items, gone_items = rows, []

    soon = [r for r in rows if 0 <= r["days"] <= 90 and r["status"] != "汇编·动态"]
    month_urgent = [r for r in soon if r["days"] <= 30]

    L = [f"# 政策雷达月报 · {today:%Y-%m}{(' · ' + label) if label else ''}", "",
         f"> 生成：{payload['generated_at']} ｜ 基准日：{today.isoformat()} ｜ "
         f"知识库 {payload['kb_version']} / {payload['entries']} 条 ｜ "
         f"原始命中 {raw_n} 条，按「条目+日期」去重后 {len(rows)} 条（已排除已废止历史条目）", "",
         "## 一、本月结论", "",
         f"- **90 天内到期 {len(soon)} 条**，其中 **30 天内 {len(month_urgent)} 条**需要本月内启动确认。",
         f"- 与上一期（{prev_name or '无'}）相比：**新增 {len(new_items)} 条、移出 {len(gone_items)} 条**。",
         f"- 分档：" + "；".join(
             f"{b} {len([r for r in rows if r['bucket'] == b and (b != '90 天内' or r['status'] != '汇编·动态')])} 条"
             for b in ["已到期", "90 天内", "91–180 天", "181–365 天", "365 天以上"]
             if any(r["bucket"] == b and (b != "90 天内" or r["status"] != "汇编·动态") for r in rows))
         + "（去重后口径；90 天内已排除汇编型）。",
         "", "## 二、90 天内到期（按到期日排序）", "",
         "| 剩余天数 | 到期日 | 条目 | 层级 | 时效性 | 建议动作 |", "|---|---|---|---|---|---|"]
    if soon:
        for r in soon:
            act = ("施行日（非政策到期），核对配套准备" if ("施行" in r["snippet"] and "到期" not in r["snippet"])
                   else action_for(r["days"]))
            L.append(f"| {r['days']} | {r['date']} | `{r['id']}` {r['title']} | {r['tier']} | "
                     f"{r['status']} | {act} |")
    else:
        L.append("| - | - | 本期无 90 天内到期项 | - | - | - |")
    L += ["", "> 口径：本表只列**单一法规型**到期项；概念卡/关系卡/场景卡（26、27 文件等「汇编·动态」）不列入，"
              "其日期为所引政策的到期日，效力须回查关联法规条目。施行日与到期日已分开标注。", ""]

    L += ["", "## 三、91–365 天（提前布局）", "",
          "| 剩余天数 | 到期日 | 条目 | 层级 | 时效性 |", "|---|---|---|---|---|"]
    mid = [r for r in rows if 90 < r["days"] <= 365]
    if mid:
        for r in mid:
            L.append(f"| {r['days']} | {r['date']} | `{r['id']}` {r['title']} | {r['tier']} | {r['status']} |")
    else:
        L.append("| - | - | 本期无 | - | - |")

    L += ["", "## 四、365 天以上（2027 集中到期组等）", "",
          "| 到期日 | 条数 | 条目（前 3 条） |", "|---|---|---|"]
    far = {}
    for r in rows:
        if r["days"] > 365:
            far.setdefault(r["date"], []).append(r)
    if far:
        for d in sorted(far):
            items = far[d]
            names = "、".join(f"`{x['id']}` {x['title']}" for x in items[:3])
            more = f" 等 {len(items)} 条" if len(items) > 3 else ""
            L.append(f"| {d} | {len(items)} | {names}{more} |")
    else:
        L.append("| - | - | 本期无 |")

    L += ["", "## 五、本月变化明细", "",
          "### 新增（上一期未出现）", ""]
    if new_items:
        for r in new_items[:40]:
            L.append(f"- `{r['id']}` {r['title']} — {r['date']}（{r['days']} 天，{r['bucket']}）")
        if len(new_items) > 40:
            L.append(f"- …… 另有 {len(new_items) - 40} 条")
    else:
        L.append("- 无")
    L += ["", "### 移出（上一期有、本期无）", ""]
    if gone_items:
        for it in gone_items[:40]:
            L.append(f"- `{it['id']}` {it['title']} — 原到期日 {it['date']}")
        if len(gone_items) > 40:
            L.append(f"- …… 另有 {len(gone_items) - 40} 条")
    else:
        L.append("- 无")

    L += ["", "## 六、口径与限制", "",
          "- 本报告由 `expiry_scan.py` 扫描 `kb.json` 中的有效期表述自动生成，**只做提示，不构成政策是否延续的结论**。",
          "- 「截至某日」类表述已排除，不视为到期日；同一文件多个日期的，按条目分别计。",
          "- 到期政策**不会自动续期**：未见官方延续文件前，不得按原政策测算下一年度税负。",
          "- 需人工确认的优先级：30 天内 > 90 天内 > 2027 集中到期组；确认结果回写 `41-expiry-alerts.md` 与 `PENDING-VERIFICATION.md`。",
          ""]

    mp = os.path.join(m_dir, stem + ".md")
    with open(mp, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    with open(os.path.join(m_dir, stem + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return mp, len(soon), len(month_urgent)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=800)
    ap.add_argument("--all", action="store_true", help="包含已到期项")
    ap.add_argument("--today", default="", help="覆盖今天（YYYY-MM-DD），用于复现")
    ap.add_argument("--monthly", action="store_true", help="生成月度政策雷达报告（reports/policy-radar/）")
    ap.add_argument("--label", default="", help="月度报告标题后缀，如「P3 首期」")
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    with open(KB, encoding="utf-8") as f:
        kb = json.load(f)

    rows = []
    for e in kb["entries"]:
        for d, snip, field in collect(e):
            days = (d - today).days
            if not args.all and days < 0:
                continue
            if days > args.days:
                continue
            rows.append({
                "date": d.isoformat(), "days": days, "bucket": bucket(days),
                "id": e["id"], "title": e["title"][:60], "tier": e.get("tier", ""),
                "status": e.get("status", ""), "field": field, "snippet": snip,
            })

    rows.sort(key=lambda r: (r["date"], r["id"]))
    groups = {}
    for r in rows:
        groups.setdefault(r["date"], []).append(r)

    counts = {}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "today": today.isoformat(), "kb_version": kb.get("kb_version"),
        "entries": len(kb["entries"]), "hits": len(rows), "counts": counts,
        "groups": [{"date": k, "count": len(v), "items": v} for k, v in sorted(groups.items())],
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    jp = os.path.join(OUT_DIR, "expiry-radar.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # Markdown
    lines = ["# 政策到期雷达（自动生成）", "",
             f"> 生成：{payload['generated_at']} ｜ 基准日：{today.isoformat()} ｜ "
             f"知识库 {payload['kb_version']} / {payload['entries']} 条 ｜ 命中 {len(rows)} 条", "",
             "| 分档 | 条目数 |", "|---|---|"]
    for b in ["已到期", "90 天内", "91–180 天", "181–365 天", "365 天以上"]:
        if counts.get(b):
            lines.append(f"| {b} | {counts[b]} |")
    lines.append("")
    for g in payload["groups"]:
        lines.append(f"## {g['date']}（{g['count']} 条）")
        lines.append("")
        lines.append("| 剩余天数 | 条目 | 层级 | 时效性 | 原文摘录 |")
        lines.append("|---|---|---|---|---|")
        for it in g["items"]:
            lines.append(f"| {it['days']} | `{it['id']}` {it['title']} | {it['tier']} | "
                         f"{it['status']} | {it['snippet'][:120]} |")
        lines.append("")
    mp = os.path.join(OUT_DIR, "expiry-radar.md")
    with open(mp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    if args.monthly:
        mmp, n90, n30 = write_monthly(payload, rows, today, args.label)
        print(f"  月报: {mmp}（90 天内 {n90} 条 / 30 天内 {n30} 条）")

    print(f"=== 到期雷达 ===\n  基准日 {today} ｜ 条目 {len(kb['entries'])} ｜ 命中 {len(rows)}")
    for b in ["已到期", "90 天内", "91–180 天", "181–365 天", "365 天以上"]:
        if counts.get(b):
            print(f"  {b}: {counts[b]}")
    print(f"  输出: {jp}")
    print(f"  输出: {mp}")


if __name__ == "__main__":
    main()
