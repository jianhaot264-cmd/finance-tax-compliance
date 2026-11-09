# -*- coding: utf-8 -*-
"""build_kb.py — 将 knowledge-base/*.md 解析为 kb.json 供后端检索使用。
用法: python build_kb.py
输出: app/kb.json (与本脚本同目录)
纯标准库实现。
"""
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.normpath(os.path.join(BASE, "..", "knowledge-base"))

FILES = [
    ("01-national-tax-administration.md", "01", "全国 · 征管与稽查"),
    ("02-national-tax-types.md", "02", "全国 · 实体税种"),
    ("03-national-invoice.md", "03", "全国 · 发票管理"),
    ("04-national-social-nontax.md", "04", "全国 · 社保与非税"),
    ("05-guangdong-local.md", "05", "广东省 · 地方法规政策"),
    ("06-incentives-quickref.md", "06", "优惠速查"),
    ("07-sme-special.md", "07", "中小企业 · 专项法规优惠"),
    ("08-other-tax-laws.md", "08", "全国 · 单行税种法律"),
    ("09-procedure-dispute.md", "09", "全国 · 程序与救济"),
    ("10-cross-border-tax.md", "10", "全国 · 跨境与国际税收"),
    ("11-digital-platform.md", "11", "全国 · 平台经济与新业态"),
    ("12-accounting-audit.md", "12", "全国 · 会计审计与代理记账"),
    ("13-incentives-industry.md", "13", "全国 · 产业与区域优惠"),
    ("14-recent-updates.md", "14", "全国 · 2025-2026 新规与立法动态"),
    ("15-sme-compliance-incentives.md", "15", "中小企业 · 合规与优惠全景"),
    ("16-vat-practice-2026.md", "16", "全国 · 增值税实操（2026 生产版）"),
    ("17-income-tax-deduction.md", "17", "全国 · 所得税扣除与汇算"),
    ("18-consumption-property-export.md", "18", "全国 · 消费税财产税出口退税非税"),
    ("19-verified-basis-corrections.md", "19", "全国 · 主干依据文号勘误"),
    ("20-verification-closings-2026.md", "20", "全国 · 隔离项核验闭环与订正"),
    ("21-vat-advanced-2026.md", "21", "全国 · 增值税进阶实操（2025-2026）"),
    ("22-income-tax-advanced.md", "22", "全国 · 所得税进阶实操"),
    ("23-authoritative-articles.md", "23", "★★权威逐字法条库（A+ 层）"),
    ("24-verified-traps-2026.md", "24", "★★权威核验订正与判定规则（A+ 层）"),
    ("25-concept-explainers.md", "25", "★★概念解读卡（A+ 解释层）"),
    ("26-relations-boundaries.md", "26", "★★关联关系与边界条件（A+ 解释层）"),
    ("27-scenario-playbooks.md", "27", "★★常见场景决策路径（A+ 解释层）"),
    ("28-authoritative-corrections-v6.md", "28", "★★权威二次核验定论（A+ 解释层）"),
    ("29-vat-methods-2026.md", "29", "全国 · 增值税计税方法与预缴（2026）"),
    ("30-social-insurance-by-type.md", "30", "广东省 · 社保分险种实操"),
    ("31-nontax-items.md", "31", "全国 · 非税收入逐项目"),
    ("32-consumption-tax-rates.md", "32", "全国 · 消费税税目税率汇编"),
    ("33-property-land-tax-gd.md", "33", "全国+广东 · 土增税/房产税/土地使用税"),
    ("34-export-tax-refund.md", "34", "全国 · 出口退（免）税实操"),
    ("35-e-invoice-rules.md", "35", "全国 · 数电票操作细则"),
    ("36-review-litigation.md", "36", "全国 · 税务行政复议与诉讼"),
    ("37-treaty-network.md", "37", "全国 · 税收协定与协定待遇"),
    ("38-accounting-standards.md", "38", "全国 · 会计准则与税会差异"),
    ("39-industry-playbooks.md", "39", "全国 · 行业专项实操"),
    ("40-legislative-tracker.md", "40", "全国 · 立法跟踪与在途修法"),
    ("41-expiry-alerts.md", "41", "全国 · 政策到期预警"),
    ("42-treaty-rates-by-country.md", "42", "全国 · 税收协定逐国税率（港澳新日德美越）"),
    ("43-accounting-standards-advanced.md", "43", "全国 · 会计准则进阶（金融工具/长投/合并）"),
    ("44-tax-law-master-matrix.md", "44", "全国 · 18 税种法律层级总表"),
    ("45-small-taxes-playbook.md", "45", "全国 · 小税种实操（关税/印花/契税/资源/环保等）"),
    ("46-collection-procedure.md", "46", "全国 · 征管程序与纳税人权利"),
    ("47-planning-space-boundaries.md", "47", "全国 · 合法操作空间与风险边界"),
    ("48-guidance-documents.md", "48", "全国 · 指导文件体系与引用规则"),
    ("49-personal-tax-finance.md", "49", "全国 · 个人与个体工商户财税"),
    ("50-housing-fund-finance-rules.md", "50", "全国 · 住房公积金与财务基础法规"),
    ("51-revenue-business-cases.md", "51", "业务事项 · 收入类（11 字段）"),
    ("52-asset-business-cases.md", "52", "业务事项 · 资产类（11 字段）"),
    ("53-expense-business-cases.md", "53", "业务事项 · 费用类（11 字段）"),
    ("54-tax-business-cases.md", "54", "业务事项 · 税费类（11 字段）"),
    ("55-intercompany-business-cases.md", "55", "业务事项 · 往来类（11 字段）"),
    ("56-closing-business-cases.md", "56", "业务事项 · 期末结转类（11 字段）"),
]

H2_RE = re.compile(r"^##\s+(.+?)\s*$")
SEC_RE = re.compile(r"^(\d+(?:\.\d+)*)")
FIELD_HEADER = "| 字段 | 内容 |"
TWO_COL_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*$")
STATUS_RE = re.compile(r"(现行有效|修订中|草案阶段|已废止|施行后|汇编·动态)")


def parse_block(block_text, prefix, idx_hint):
    """Parse one '## ' section block into an entry."""
    lines = block_text.split("\n")
    heading = lines[0].lstrip("# ").strip()
    sec_no = None
    m = SEC_RE.match(heading)
    if m:
        sec_no = m.group(1)
    # title: prefer 《...》
    m2 = re.search(r"《(.+?)》", heading)
    title = m2.group(1) if m2 else re.sub(r"^\d+(?:\.\d+)*[、.\s]*", "", heading)
    eid = f"{prefix}-{sec_no}" if sec_no else f"{prefix}-{idx_hint}"

    fields = {}
    body_lines = []
    i = 1
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == FIELD_HEADER:
            # parse two-column field table
            i += 1  # skip header
            if i < n and set(lines[i].replace("|", "").replace("-", "").strip()) == set():
                i += 1  # skip separator like |---|---|
            while i < n:
                mm = TWO_COL_RE.match(lines[i])
                if not mm:
                    break
                fields[mm.group(1).strip()] = mm.group(2).strip()
                i += 1
            continue
        body_lines.append(line)
        i += 1

    body_md = "\n".join(body_lines).strip()
    search_blob = " ".join([heading, title, " ".join(f"{k} {v}" for k, v in fields.items()), body_md])

    status = ""
    for key in ("时效性", "生效状态", "状态"):
        if key in fields:
            s = STATUS_RE.search(fields[key])
            if s:
                status = s.group(1)
                break
    if not status:
        s = STATUS_RE.search(body_md)
        if s:
            status = s.group(1)
    if not status:
        status = "未标注"

    return {
        "id": eid,
        "file": prefix,
        "heading": heading,
        "no": sec_no or "",
        "title": title,
        "fields": fields,
        "status": status,
        "body_md": body_md,
        "search_text": search_blob,
    }


def build():
    entries = []
    files_meta = []
    for fname, prefix, category in FILES:
        path = os.path.join(KB_DIR, fname)
        if not os.path.exists(path):
            print(f"[warn] missing file: {path}")
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        # split into '## ' level blocks
        blocks = []
        cur = None
        for line in text.split("\n"):
            if H2_RE.match(line):
                if cur is not None:
                    blocks.append("\n".join(cur))
                cur = [line]
            else:
                if cur is not None:
                    cur.append(line)
        if cur is not None:
            blocks.append("\n".join(cur))

        count = 0
        for bi, block in enumerate(blocks):
            first = block.split("\n", 1)[0]
            if first.lstrip("# ").strip().startswith("广东省社会保险基金监督条例 >") is False and (
                "法规知识库" in first or "索引" in first
            ):
                continue  # skip index-like headings inside content files
            e = parse_block(block, prefix, bi + 1)
            if not e["title"]:
                continue
            e["category"] = category
            e["tier"] = "A" if prefix in {"16", "17", "18", "19", "20", "21", "22", "23", "24",
                                          "25", "26", "27", "28", "29", "30", "31", "32",
                                          "33", "34", "35", "36", "37", "38", "39",
                                          "40", "41", "42", "43", "44", "45", "46", "47", "48", "49", "50",
                                          "51", "52", "53", "54", "55", "56"} else "B"  # A/A+=双源与权威库回库；enrich_kb.py 按元数据实证重算
            e["source_file"] = fname
            entries.append(e)
            count += 1
        files_meta.append({"file": prefix, "name": fname, "category": category, "entries": count})

    data = {
        "generated_at": "2026-11-09",
        "verified_at": "2026-11-09",
        "kb_version": "v14.0",
        "files": files_meta,
        "entries": entries,
    }
    out = os.path.join(BASE, "kb.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"[ok] entries={len(entries)} -> {out}")
    for fm in files_meta:
        print(f"     {fm['file']} {fm['category']}: {fm['entries']} entries")


if __name__ == "__main__":
    build()
