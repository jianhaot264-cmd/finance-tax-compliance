#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
checks.py — 金额逻辑校验 + 三流一致 + 税负率预警
=================================================

确定性规则（容差 ±0.10 元，见 __init__.TOLERANCE）：
  C1 价税合计 = 不含税金额 + 税额
  C2 税额 = 不含税金额 × 税率（税率未知时跳过）
  C3 合同—发票—资金：金额可勾稽（发票累计 ≤ 合同额，回款累计 ≤ 发票累计）
  C4 税负率 = 实缴增值税 ÷ 销售收入，偏离行业参考区间则预警
"""

import re
from collections import defaultdict

from . import TOLERANCE
from .parsers import norm_field, norm_num

# 行业税负率参考区间（增值税，%）——预警用，不作申报依据
TAX_BURDEN_REF = {
    "批发零售": (0.8, 3.5), "制造业": (1.5, 5.0), "建筑业": (1.5, 4.5),
    "服务业": (1.0, 5.0), "电商": (0.5, 3.0), "default": (0.5, 6.0),
}


def _check_amount_logic(invoices):
    """C1 + C2：发票内部金额逻辑。"""
    issues = []
    for i, r in enumerate(invoices, 1):
        no = norm_field(r, "invoice_no") or f"第{i}行"
        nt = norm_num(r, "amount_no_tax")
        tx = norm_num(r, "tax_amount")
        tt = norm_num(r, "amount_total")
        rate = norm_num(r, "tax_rate")
        if rate and rate > 1:
            rate = rate / 100.0     # 兼容 13 / 13% / 0.13 三种写法
        if tt is not None and nt is not None and tx is not None:
            diff = abs(round(nt + tx, 2) - round(tt, 2))
            if diff > TOLERANCE:
                issues.append({
                    "code": "C1", "level": "error", "row": i, "ref": no,
                    "msg": f"价税合计不符：不含税 {nt} + 税额 {tx} = {round(nt + tx, 2)} "
                           f"≠ 合计 {tt}（差 {round(diff, 2)} 元，容差 {TOLERANCE}）",
                    "diff": round(diff, 2),
                })
        if rate and nt is not None and tx is not None:
            expect = round(nt * rate, 2)
            diff = abs(expect - round(tx, 2))
            if diff > TOLERANCE:
                issues.append({
                    "code": "C2", "level": "warn", "row": i, "ref": no,
                    "msg": f"税额与税率不符：{nt} × {rate * 100:g}% = {expect} ≠ 税额 {tx}"
                           f"（差 {round(diff, 2)} 元）",
                    "diff": round(diff, 2),
                })
    return issues


def _check_three_flow(invoices, bank, contracts):
    """C3：合同—发票—资金勾稽。"""
    issues = []
    inv_total = sum((norm_num(r, "amount_total") or 0) for r in invoices)
    inv_by_contract = defaultdict(float)
    for r in invoices:
        cno = norm_field(r, "contract_no") or "_未关联"
        inv_by_contract[cno] += (norm_num(r, "amount_total") or 0)
    bank_total = sum(abs(norm_num(r, "amount_paid") or 0) for r in bank)

    for c in contracts:
        cno = norm_field(c, "contract_no") or "_未知合同"
        camt = norm_num(c, "amount_total") or norm_num(c, "amount_no_tax") or 0
        inv_amt = inv_by_contract.get(cno, 0)
        if camt > 0 and inv_amt > camt + TOLERANCE:
            issues.append({
                "code": "C3", "level": "error", "ref": cno,
                "msg": f"发票金额超合同额：发票累计 {round(inv_amt, 2)} > 合同 {round(camt, 2)}"
                       f"（超 {round(inv_amt - camt, 2)} 元），涉嫌无合同开票",
            })
        if camt > 0 and 0 < inv_amt < camt - TOLERANCE:
            issues.append({
                "code": "C3", "level": "info", "ref": cno,
                "msg": f"发票累计 {round(inv_amt, 2)} 低于合同额 {round(camt, 2)}"
                       f"（差 {round(camt - inv_amt, 2)} 元），可能尚未开票完毕",
            })
    if contracts and bank:
        if bank_total > inv_total + TOLERANCE:
            issues.append({
                "code": "C3", "level": "warn", "ref": "资金流",
                "msg": f"资金收付 {round(bank_total, 2)} 超出发票总额 {round(inv_total, 2)}"
                       f"（超 {round(bank_total - inv_total, 2)} 元），存在无票收付风险",
            })
        elif inv_total > 0 and bank_total < inv_total - TOLERANCE:
            issues.append({
                "code": "C3", "level": "info", "ref": "资金流",
                "msg": f"资金收付 {round(bank_total, 2)} 小于发票总额 {round(inv_total, 2)}"
                       f"（差 {round(inv_total - bank_total, 2)} 元），可能尚未收付款",
            })
    return issues


def _check_tax_burden(invoices, vat_paid=None, sales_total=None, industry="default"):
    """C4：税负率预警。"""
    issues = []
    if vat_paid is None:
        vat_paid = sum((norm_num(r, "tax_amount") or 0) for r in invoices
                       if "进" not in (norm_field(r, "party") or ""))
    if sales_total is None:
        sales_total = sum((norm_num(r, "amount_no_tax") or 0) for r in invoices)
    if not sales_total or sales_total <= 0:
        return issues, {}
    rate = vat_paid / sales_total * 100
    lo, hi = TAX_BURDEN_REF.get(industry, TAX_BURDEN_REF["default"])
    stat = {"vat_paid": round(vat_paid, 2), "sales": round(sales_total, 2),
            "burden_rate": round(rate, 2), "ref_low": lo, "ref_high": hi,
            "industry": industry}
    if rate > hi:
        issues.append({"code": "C4", "level": "warn", "ref": "税负率",
                       "msg": f"增值税税负率 {rate:.2f}% 高于行业参考上限 {hi}%"
                              f"（{industry}），建议核查是否多缴或适用税率错误"})
    elif rate < lo:
        issues.append({"code": "C4", "level": "warn", "ref": "税负率",
                       "msg": f"增值税税负率 {rate:.2f}% 低于行业参考下限 {lo}%"
                              f"（{industry}），建议核查进项是否虚抵或收入是否完整（属预警非结论）"})
    return issues, stat


def run_checks(invoices, bank, contracts, tax_rate=None):
    """执行全部核对规则，返回结构化结果。"""
    ind = "default"
    for r in (invoices or [])[:3]:
        blob = " ".join(str(v) for v in r.values())
        if re.search(r"电商|平台|网店", blob):
            ind = "电商"; break
        if re.search(r"建|工程|施工", blob):
            ind = "建筑业"; break
        if re.search(r"制造|加工|生产", blob):
            ind = "制造业"; break
        if re.search(r"批发|零售|商贸", blob):
            ind = "批发零售"; break
        if re.search(r"服务|咨询|技术", blob):
            ind = "服务业"; break

    issues = []
    issues += _check_amount_logic(invoices)
    issues += _check_three_flow(invoices, bank, contracts)
    burden_issues, burden = _check_tax_burden(invoices, industry=ind)
    issues += burden_issues

    errors = [i for i in issues if i.get("level") == "error"]
    warns = [i for i in issues if i.get("level") == "warn"]
    infos = [i for i in issues if i.get("level") == "info"]
    ok = not errors
    return {
        "ok": ok,
        "snapshot": "2026-11-08",
        "tolerance": TOLERANCE,
        "counts": {"invoices": len(invoices), "bank": len(bank),
                   "contracts": len(contracts),
                   "errors": len(errors), "warnings": len(warns), "infos": len(infos)},
        "issues": issues,
        "burden": burden,
        "summary": ("✅ 三流核对通过，未发现金额逻辑与勾稽错误"
                    if ok else f"❌ 发现 {len(errors)} 项金额逻辑/勾稽错误，{len(warns)} 项预警"),
    }
