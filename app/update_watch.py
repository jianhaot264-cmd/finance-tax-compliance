#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_watch.py — 官方信源更新巡检 v1
=====================================

解决「数据层更新机制」：对知识库 A 层条目的官方信源做可达性与内容变更巡检，
配合月度政策雷达（expiry_scan.py --monthly）形成「时效 + 来源」双通道更新闭环。

巡检维度：
  1. 可达性   HEAD/GET 请求信源 URL，记录 HTTP 状态
  2. 变更     对可抓取页面做内容指纹（SHA-256 前 16 位），与上次指纹对比
  3. 陈旧     信源无指纹 / 长期未巡检的条目单列

输出：
  reports/source-watch-YYYY-MM-DD.json   机器可读巡检结果
  reports/source-watch-YYYY-MM-DD.md     人工可读报告

用法：
  python update_watch.py                # 巡检全部 A 层信源（采样上限 60）
  python update_watch.py --limit 20     # 只巡检 20 个 URL
  python update_watch.py --full         # 不限采样（慎用，全量耗时长）

注意：
  - 只读巡检，不修改知识库；指纹存 reports/source-watch-state.json 供下次 diff
  - 沙箱可能禁网：网络失败记录为 'unreachable'，不视为内容变更
  - 本工具不替代人工核验，只提示「哪些信源需要人工复查」
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from datetime import date, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
KB_PATH = os.path.join(BASE, "kb.json")
REPORT_DIR = os.path.join(os.path.dirname(BASE), "reports")
STATE_PATH = os.path.join(REPORT_DIR, "source-watch-state.json")

UA = ("Mozilla/5.0 (compatible; FinanceTaxKB-Watch/1.0; +compliance-source-check)")
TIMEOUT = 8


def load_entries():
    with open(KB_PATH, encoding="utf-8") as f:
        return json.load(f)["entries"]


def collect_targets(entries, limit=60):
    """收集 A 层条目的官方信源 URL（每条目最多 1 个，优先 gov.cn / chinatax / mof）。"""
    targets, seen = [], set()
    prefer = ("gov.cn", "chinatax.gov.cn", "mof.gov.cn", "mohrss.gov.cn",
              "customs.gov.cn", "npc.gov.cn", "ndrc.gov.cn")
    for e in entries:
        if e.get("tier") != "A":
            continue
        srcs = e.get("sources") or []
        if not srcs:
            continue
        # 优先官方域名
        srcs_sorted = sorted(srcs, key=lambda u: 0 if any(d in u for d in prefer) else 1)
        url = srcs_sorted[0].strip()
        # 只巡检 http(s)，剔除带中文备注的尾巴
        m = re.match(r"https?://[^\s（(｜|]+", url)
        if not m:
            continue
        url = m.group(0)
        if url in seen:
            continue
        seen.add(url)
        targets.append({"entry_id": e["id"], "title": e["title"][:48], "url": url})
        if limit and len(targets) >= limit:
            break
    return targets


def fetch_fingerprint(url):
    """抓取页面并计算内容指纹；返回 (status, fingerprint, length)。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            status = resp.status
            data = resp.read(512 * 1024)   # 上限 512KB
            fp = hashlib.sha256(data).hexdigest()[:16]
            return status, fp, len(data)
    except urllib.error.HTTPError as exc:
        return exc.code, None, 0
    except Exception as exc:  # noqa: BLE001
        return f"unreachable:{type(exc).__name__}", None, 0


def load_state():
    if os.path.isfile(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_state(state):
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def run(limit=60, full=False):
    entries = load_entries()
    targets = collect_targets(entries, limit=0 if full else limit)
    state = load_state()
    today = date.today().isoformat()
    print(f"=== 来源更新巡检  {today}  目标 {len(targets)} 个 URL ===")

    rows, changed, broken, stale = [], [], [], []
    for i, t in enumerate(targets, 1):
        status, fp, n = fetch_fingerprint(t["url"])
        prev = state.get(t["url"], {})
        prev_fp = prev.get("fp")
        changed_flag = bool(fp and prev_fp and fp != prev_fp)
        first_seen = prev.get("first_seen", today)
        last_ok = today if fp else prev.get("last_ok", "")
        state[t["url"]] = {"fp": fp, "first_seen": first_seen,
                           "last_ok": last_ok, "last_check": today}
        row = {**t, "status": status, "fp": fp, "length": n,
               "changed": changed_flag, "prev_fp": prev_fp,
               "first_seen": first_seen, "last_ok": last_ok}
        rows.append(row)
        if changed_flag:
            changed.append(row)
        if isinstance(status, str) and status.startswith("unreachable"):
            broken.append(row)
        elif isinstance(status, int) and status >= 400:
            broken.append(row)
        if not prev_fp:
            stale.append(row)
        mark = "≠" if changed_flag else ("✗" if row in broken else "·")
        print(f"  [{i}/{len(targets)}] {mark} {status} {t['url'][:70]}")

    save_state(state)

    # ---- 报告 ----
    os.makedirs(REPORT_DIR, exist_ok=True)
    stem = f"source-watch-{today}"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "date": today,
        "targets": len(targets),
        "reachable": sum(1 for r in rows if isinstance(r["status"], int) and r["status"] < 400),
        "changed": len(changed),
        "broken": len(broken),
        "first_watch": len(stale),
        "rows": rows,
    }
    with open(os.path.join(REPORT_DIR, stem + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    L = [
        f"# 官方信源更新巡检  {today}",
        "",
        f"> 巡检目标 **{len(targets)}** 个 A 层官方信源 URL ｜ "
        f"可达 {payload['reachable']} ｜ **内容变更 {len(changed)}** ｜ "
        f"不可达 {len(broken)} ｜ 首次巡检 {len(stale)}",
        "",
        "## 一、内容变更（须人工复查是否出台新规/修订）",
        "",
    ]
    if changed:
        L.append("| 条目 | 标题 | URL | 上次指纹 | 本次指纹 |")
        L.append("|---|---|---|---|---|")
        for r in changed:
            L.append(f"| `{r['entry_id']}` | {r['title']} | {r['url'][:60]} | "
                     f"`{r['prev_fp']}` | `{r['fp']}` |")
    else:
        L.append("本期无内容变更。")
    L += ["", "## 二、不可达信源（需替换或人工确认）", ""]
    if broken:
        L.append("| 条目 | 状态 | URL |")
        L.append("|---|---|---|")
        for r in broken:
            L.append(f"| `{r['entry_id']}` | {r['status']} | {r['url'][:70]} |")
    else:
        L.append("本期全部可达。")
    L += ["", "## 三、巡检纪律", "",
          "1. 内容变更 ≠ 法规变更：页面改版、导航调整也会触发指纹变化，须人工打开确认；",
          "2. 不可达 ≠ 废止：网站迁移、临时故障都可能导致 404，须走 SOURCES-CHANNELS.md SOP 换源复核；",
          "3. 本巡检只覆盖 A 层条目的首个官方信源（每条 1 个），不是全量覆盖；",
          "4. 巡检结果与到期雷达（expiry-radar）共同构成「时效 + 来源」双通道，月度自动化并行运行。"]
    with open(os.path.join(REPORT_DIR, stem + ".md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(f"\n=== 巡检完成 ===  可达 {payload['reachable']}  变更 {len(changed)}  "
          f"不可达 {len(broken)}\n报告: reports/{stem}.md")
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60, help="采样 URL 上限")
    ap.add_argument("--full", action="store_true", help="全量巡检（不限采样）")
    args = ap.parse_args()
    run(limit=args.limit, full=args.full)


if __name__ == "__main__":
    main()
