# -*- coding: utf-8 -*-
"""build_coverage_matrix.py — 生成「税种/主题 × 覆盖度」矩阵（CSV + JSON）。

用法：python build_coverage_matrix.py
输出：reports/coverage-matrix-2026-11-08.csv（UTF-8 BOM）
      reports/coverage-matrix-2026-11-08.json
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
KB = os.path.join(BASE, "kb.json")
OUT_DIR = os.path.join(ROOT, "reports")

# (类别, 标题/正文关键词, 备注)
CATS = [
    ("税种法律层级总表", [], "44"),
    ("小税种实操手册", [], "45"),
    ("征管程序与权利", [], "46"),
    ("增值税", ["增值税"], ""),
    ("消费税", ["消费税"], ""),
    ("企业所得税", ["企业所得税"], ""),
    ("个人所得税", ["个人所得税"], ""),
    ("关税", ["关税"], ""),
    ("印花税", ["印花税"], ""),
    ("契税", ["契税"], ""),
    ("城市维护建设税", ["城市维护建设税", "城建税"], ""),
    ("资源税", ["资源税"], ""),
    ("环境保护税", ["环境保护税", "环保税"], ""),
    ("车船税", ["车船税"], ""),
    ("车辆购置税", ["车辆购置税", "车购税"], ""),
    ("耕地占用税", ["耕地占用税"], ""),
    ("烟叶税", ["烟叶税"], ""),
    ("船舶吨税", ["船舶吨税", "吨税"], ""),
    ("土地增值税", ["土地增值税", "土增税"], ""),
    ("房产税", ["房产税"], ""),
    ("城镇土地使用税", ["城镇土地使用税", "土地使用税"], ""),
    ("征管与稽查", ["税收征收管理", "征管", "稽查", "税务登记", "纳税申报", "强制执行", "欠税"], ""),
    ("发票管理", ["发票"], ""),
    ("社保费", ["社会保险", "社保", "养老", "失业", "工伤", "医保", "生育"], ""),
    ("非税收入", ["非税", "教育费附加", "地方教育附加", "残保金", "文化事业建设费", "工会经费", "水利建设基金"], ""),
    ("会计与审计", ["会计", "审计", "代理记账", "会计准则", "CAS"], ""),
    ("跨境与国际税收", ["跨境", "协定", "非居民", "转让定价", "CRS", "出口退"], ""),
    ("税收优惠", ["优惠", "减免", "加计", "免税", "减按", "即征即退", "留抵"], ""),
    ("广东地方", ["广东", "南沙", "前海", "横琴", "大湾区", "粤"], ""),
    ("程序与救济", ["复议", "诉讼", "听证", "处罚", "裁量", "赔偿"], ""),
    ("解释层", ["概念", "关系", "边界", "场景", "定论"], ""),
    ("操作空间与边界", ["操作空间", "风险边界", "红线", "选择权"], "47"),
    ("指导文件体系", ["指导文件", "效力层级", "公告解读", "批复", "政策法规库"], "48"),
    ("业务事项·收入类", [], "51"),
    ("业务事项·资产类", [], "52"),
    ("业务事项·费用类", [], "53"),
    ("业务事项·税费类", [], "54"),
    ("业务事项·往来类", [], "55"),
    ("业务事项·期末结转类", [], "56"),
]


def main():
    with open(KB, encoding="utf-8") as f:
        kb = json.load(f)
    entries = kb["entries"]
    rows = []
    for cat, kws, note in CATS:
        hit = []
        for e in entries:
            if note and e.get("file") == note:
                hit.append(e)
                continue
            blob = " ".join([e.get("heading", ""), e.get("title", ""),
                             e.get("fields", {}).get("文号", ""), e.get("body_md", "")[:400]])
            if any(k in blob for k in kws):
                hit.append(e)
        tier = Counter(e.get("tier", "") for e in hit)
        stat = Counter(e.get("status", "") for e in hit)
        rows.append({
            "category": cat, "entries": len(hit),
            "A": tier.get("A", 0), "B1": tier.get("B1", 0), "B2": tier.get("B2", 0),
            "valid": stat.get("现行有效", 0), "digest": stat.get("汇编·动态", 0),
            "draft": stat.get("草案阶段", 0), "repealed": stat.get("已废止", 0),
            "top_ids": [e["id"] for e in hit[:6]],
            "note": note,
        })

    # 缺口：条目数 < 3 的税种
    gaps = [r for r in rows if r["entries"] < 3]

    os.makedirs(OUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUT_DIR, "coverage-matrix-2026-11-08.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("类别,条目数,A层,B1,B2,现行有效,汇编动态,草案,已废止,代表条目,说明\n")
        for r in rows:
            f.write(f"{r['category']},{r['entries']},{r['A']},{r['B1']},{r['B2']},"
                    f"{r['valid']},{r['digest']},{r['draft']},{r['repealed']},"
                    f"{'|'.join(r['top_ids'])},{r['note']}\n")

    payload = {
        "generated_at": "2026-11-08",
        "kb_version": kb.get("kb_version"), "entries": len(entries),
        "rows": rows, "gaps": [g["category"] for g in gaps],
    }
    json_path = os.path.join(OUT_DIR, "coverage-matrix-2026-11-08.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"[ok] entries={len(entries)} categories={len(rows)} gaps={len(gaps)}")
    for r in rows:
        print(f"  {r['category']}: {r['entries']} (A{r['A']}/B1 {r['B1']}/B2 {r['B2']})")
    print(f"  -> {csv_path}")


if __name__ == "__main__":
    main()
