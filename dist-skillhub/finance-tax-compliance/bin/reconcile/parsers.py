#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parsers.py — 零依赖文件解析（CSV / XLSX / JSON）
================================================

XLSX 本质是 ZIP 包内 XML：用 zipfile + xml.etree 解析 sharedStrings + sheet1。
不引入 openpyxl/pandas，维持零依赖红线。
"""

import csv
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _clean(v):
    """把单元格值归一为字符串（数值去掉多余小数位）。"""
    if v is None:
        return ""
    s = str(v).strip()
    if re.fullmatch(r"-?\d+\.0+", s):
        s = s.split(".")[0]
    return s


def _to_number(v):
    s = _clean(v).replace(",", "").replace("￥", "").replace("¥", "").replace("元", "")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def parse_csv(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.reader(f):
            rows.append([_clean(c) for c in r])
    return rows


def parse_json(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("rows") or data.get("data") or [data]
    if data and isinstance(data[0], dict):
        headers = list(data[0].keys())
        rows = [headers] + [[_clean(d.get(h, "")) for h in headers] for d in data]
        return rows
    return [[_clean(c) for c in r] for r in data]


def _xlsx_col_idx(ref):
    """'AB12' → 列号 27（0-based）。"""
    letters = re.match(r"([A-Z]+)", ref or "A")
    n = 0
    for ch in (letters.group(1) if letters else "A"):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def parse_xlsx(path):
    """零依赖 XLSX 解析：取第一张 sheet，首行表头。"""
    rows = []
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
        sheet_name = next((n for n in z.namelist()
                           if re.match(r"xl/worksheets/sheet\d+\.xml", n)), None)
        if not sheet_name:
            return rows
        root = ET.fromstring(z.read(sheet_name))
        for row in root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
            cells = {}
            for c in row.findall("m:c", NS):
                ref = c.get("r", "")
                t = c.get("t", "n")
                v = c.find("m:v", NS)
                isel = c.find("m:is", NS)
                if t == "s" and v is not None and v.text:
                    val = shared[int(v.text)] if int(v.text) < len(shared) else ""
                elif t == "inlineStr" and isel is not None:
                    val = "".join(x.text or "" for x in isel.iter(
                        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
                else:
                    val = v.text if v is not None else ""
                cells[_xlsx_col_idx(ref)] = _clean(val)
            if cells:
                width = max(cells) + 1
                rows.append([cells.get(i, "") for i in range(width)])
    return rows


def parse(path, kind=None):
    """统一入口：返回 list[dict]，首行作为表头；kind 可强制指定 invoice/bank/contract。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        rows = parse_csv(path)
    elif ext in (".xlsx", ".xlsm"):
        rows = parse_xlsx(path)
    elif ext == ".json":
        rows = parse_json(path)
    else:
        raise ValueError(f"不支持的文件格式 {ext}（一期支持 CSV/XLSX/JSON）")
    if not rows:
        return []
    headers = [h or f"col{i}" for i, h in enumerate(rows[0])]
    out = []
    for r in rows[1:]:
        d = {headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))}
        d["_kind"] = kind or _guess_kind(headers)
        out.append(d)
    return out


def _guess_kind(headers):
    h = " ".join(headers)
    if re.search(r"发票|销项|进项|税额", h):
        return "invoice"
    if re.search(r"流水|借方|贷方|银行|对方户名", h):
        return "bank"
    if re.search(r"合同|甲方|乙方|合同金额", h):
        return "contract"
    return "unknown"


# ---- 字段标准化（三类表的关键字段映射）----
FIELD_ALIASES = {
    "amount_no_tax": ["不含税金额", "不含税", "金额", "货款", "销售额", "amount"],
    "tax_amount": ["税额", "税金", "tax"],
    "amount_total": ["价税合计", "合计", "总额", "total", "含税金额"],
    "tax_rate": ["税率", "rate"],
    "invoice_no": ["发票号", "发票号码", "号码", "invoice_no", "invoice"],
    "contract_no": ["合同编号", "合同号", "contract_no", "合同"],
    "date": ["日期", "开票日期", "记账日期", "签订日期", "date"],
    "party": ["对方", "对方户名", "供应商", "客户", "名称", "party"],
    "amount_paid": ["金额", "发生额", "借方", "贷方", "实付", "amount"],
}


def norm_field(row, key):
    """按别名表取字段值（字符串）。"""
    for alias in FIELD_ALIASES.get(key, [key]):
        for k, v in row.items():
            if k and alias == k.strip():
                return v
    return ""


def norm_num(row, key):
    return _to_number(norm_field(row, key))
