#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cit.py — 企业所得税确定性计算
==============================

口径来源（SNAPSHOT 核验）：
  - 《中华人民共和国企业所得税法》（2018 年修正）第四条：基本税率 25%
  - 《中华人民共和国企业所得税法实施条例》（国务院令第 512 号，2019、2024 两次修订）
  - 财政部 税务总局公告 2023 年第 12 号（小型微利企业优惠，至 2027-12-31）
  - 财政部 税务总局公告 2025 年第 16 号（广宣费 30%，至 2027-12-31）
  - 财税〔2018〕51 号（职工教育经费 8%）

【红线】纯函数；小微判定三条件（从业人数/资产总额/应纳税所得额）任一不符即按 25%。
"""

from decimal import Decimal

from . import CalcResult, _basis, money

D = Decimal

RATE_BASIC = D("0.25")
RATE_SMALL_EFFECTIVE = D("0.05")   # 小微实际税负（≤300 万部分）
THRESHOLD_SMALL = D("3000000")     # 年应纳税所得额 300 万

BASIS_LAW = _basis("《中华人民共和国企业所得税法》", "第四条", "2018-01-01")
BASIS_SMALL = _basis("财政部 税务总局公告 2023 年第 12 号", "小型微利企业减免", "2023-01-01 至 2027-12-31")
BASIS_REG = _basis("《中华人民共和国企业所得税法实施条例》", "第四十二条、第四十四条等",
                   "2019-01-01（512 号令两次修订）")

# 税前扣除比例（常见项，含法条依据）
DEDUCTION_LIMITS = {
    "职工教育经费": (D("0.08"), "财税〔2018〕51 号", "工资薪金总额 8%，超过部分准予结转以后纳税年度"),
    "广告费和业务宣传费": (D("0.30"), "财政部 税务总局公告 2025 年第 16 号",
                     "当年销售收入 15% 一般/30% 特定行业，超额结转（特定行业至 2027-12-31）"),
    "业务招待费": (D("0.005"), "《实施条例》第四十三条", "按发生额 60% 扣除，但最高不超过当年销售收入 5‰"),
    "公益性捐赠": (D("0.12"), "《企业所得税法》第九条", "年度利润总额 12% 以内扣除，超过部分结转 3 年"),
    "职工福利费": (D("0.14"), "《实施条例》第四十条", "工资薪金总额 14%"),
    "工会经费": (D("0.02"), "《实施条例》第四十一条", "工资薪金总额 2%"),
}


def cit_quarterly(profit, is_small=True, employees=0, assets=0):
    """企业所得税季度预缴（按实际利润额）。

    profit      本年累计实际利润额（元）
    is_small    是否符合小型微利企业条件（需同时满足从业人数≤300、资产总额≤5000万、
                应纳税所得额≤300万）
    employees   从业人数（季度平均）
    assets      资产总额（元，季度平均）
    """
    profit = D(str(profit))
    if profit < 0:
        return CalcResult("cit.quarterly", D(0),
                          formula=f"累计利润 {profit} ≤ 0，本期不预缴",
                          steps=[{"label": "累计亏损", "expr": str(profit), "value": profit}],
                          basis=[BASIS_LAW],
                          caveats=["亏损年度不预缴；亏损可按 5 年（高新/科技型中小 10 年）结转弥补"],
                          params={"profit": str(profit)})

    steps = [{"label": "本年累计实际利润额", "expr": str(profit), "value": profit}]
    caveats = []
    if is_small and profit <= THRESHOLD_SMALL and employees <= 300 and assets <= D("50000000"):
        tax = money(profit * RATE_SMALL_EFFECTIVE)
        steps.append({"label": "符合小型微利企业三条件，实际税负 5%",
                      "expr": f"{profit} × 5%", "value": tax})
        formula = f"{profit} × 5% = {tax}（小型微利企业）"
        basis = [BASIS_SMALL]
        caveats.append("小型微利企业须同时满足：① 年应纳税所得额 ≤300 万 ② 从业人数 ≤300 人 "
                       "③ 资产总额 ≤5000 万，且从事国家非限制/禁止行业")
        caveats.append("优惠执行至 2027-12-31，延续情况须核对官方公告")
    else:
        reason = []
        if profit > THRESHOLD_SMALL:
            reason.append(f"应纳税所得额 {profit} > 300 万")
        if employees > 300:
            reason.append(f"从业人数 {employees} > 300")
        if assets > D("50000000"):
            reason.append(f"资产总额 {assets} > 5000 万")
        if not is_small:
            reason.append("非小型微利企业")
        tax = money(profit * RATE_BASIC)
        steps.append({"label": "不符合小微条件，按基本税率 25%",
                      "expr": f"{profit} × 25%", "value": tax})
        formula = f"{profit} × 25% = {tax}"
        basis = [BASIS_LAW]
        caveats.append("未享受小微优惠原因：" + "；".join(reason or ["条件不符"]))
        caveats.append("小型微利企业判定为「同时满足」三项标准，任一超标即全额按 25%")
    return CalcResult(
        "cit.quarterly", tax, formula=formula, steps=steps, basis=basis,
        caveats=caveats,
        params={"profit": str(profit), "is_small": is_small,
                "employees": employees, "assets": str(assets)},
    )


def cit_deduction(name, base_amount, incurred_amount=None):
    """税前扣除限额：某项支出可扣除上限。

    name           项目名（见 DEDUCTION_LIMITS）
    base_amount    计算基数（如工资薪金总额 / 销售收入 / 利润总额）
    incurred_amount 实际发生额（可选，给出实际可扣除额）
    """
    if name not in DEDUCTION_LIMITS:
        return CalcResult.fail("cit.deduction",
                               f"未知扣除项目「{name}」，可用：{('、'.join(DEDUCTION_LIMITS))}")
    rate, ref, note = DEDUCTION_LIMITS[name]
    base = D(str(base_amount))
    limit = money(base * rate)
    steps = [{"label": f"{name}扣除限额（{rate * 100}%）", "expr": f"{base} × {rate}", "value": limit}]
    caveats = [note, f"依据：{ref}（口径核验 {__import__('tax_calc').SNAPSHOT}）"]
    if incurred_amount is not None:
        inc = D(str(incurred_amount))
        allowed = min(inc, limit)
        steps.append({"label": "实际发生额", "expr": str(inc), "value": inc})
        steps.append({"label": "准予扣除额（孰低）", "expr": f"min({inc}, {limit})", "value": allowed})
        formula = f"{base} × {rate * 100}% = {limit}；实际 {inc}，准予扣除 {allowed}"
        value = allowed
    else:
        formula = f"{base} × {rate * 100}% = {limit}"
        value = limit
    return CalcResult("cit.deduction", value, formula=formula,
                      steps=steps, basis=[BASIS_REG],
                      caveats=caveats,
                      params={"name": name, "base_amount": str(base_amount),
                              "incurred_amount": str(incurred_amount or "")})
