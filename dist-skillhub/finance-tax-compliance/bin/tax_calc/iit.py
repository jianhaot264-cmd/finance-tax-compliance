#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iit.py — 个人所得税确定性计算
==============================

口径来源（SNAPSHOT 核验）：
  - 《中华人民共和国个人所得税法》（2018 年第七次修正）及实施条例
  - 财政部 税务总局公告 2023 年第 30 号（年终奖单独计税，至 2027-12-31）
  - 国家税务总局公告 2018 年第 61 号（累计预扣预缴法）
  - 国发〔2023〕13 号（专项附加扣除提标：3 岁以下婴幼儿 2000 元/月/孩、
    子女教育 2000 元/月/孩、赡养老人 3000 元/月）

【红线】纯函数；七级/五级税率表为法定附表，改动须更新 SNAPSHOT。
"""

from decimal import Decimal

from . import CalcResult, _basis, money

D = Decimal

# 综合所得年度税率表（七级，月度/年度换算用）
BRACKET_MONTHLY = [
    (D("3000"), D("0.03"), D("0")),
    (D("12000"), D("0.10"), D("210")),
    (D("25000"), D("0.20"), D("1410")),
    (D("35000"), D("0.25"), D("2660")),
    (D("55000"), D("0.30"), D("4410")),
    (D("80000"), D("0.35"), D("7160")),
    (None, D("0.45"), D("15160")),
]
# 年终奖单独计税换算月度税率表
BRACKET_BONUS = BRACKET_MONTHLY
# 经营所得五级超额累进（年度）
BRACKET_BIZ = [
    (D("30000"), D("0.05"), D("0")),
    (D("90000"), D("0.10"), D("1500")),
    (D("300000"), D("0.20"), D("10500")),
    (D("500000"), D("0.30"), D("40500")),
    (None, D("0.35"), D("65500")),
]

BASIS_LAW = _basis("《中华人民共和国个人所得税法》", "第三条、第六条", "2019-01-01")
BASIS_PREPAY = _basis("国家税务总局公告 2018 年第 61 号", "累计预扣预缴法", "2019-01-01")
BASIS_BONUS = _basis("财政部 税务总局公告 2023 年第 30 号", "全年一次性奖金单独计税", "2023-01-01 至 2027-12-31")
BASIS_BIZ = _basis("《中华人民共和国个人所得税法》", "第三条（经营所得五级）", "2019-01-01")
BASIS_SPECIAL = _basis("国发〔2023〕13 号", "专项附加扣除标准", "2023-01-01")

SPECIAL_DEDUCTIONS = {
    "3岁以下婴幼儿照护": D("2000"), "子女教育": D("2000"),
    "继续教育": D("400"), "住房贷款利息": D("1000"),
    "住房租金": D("1500"), "赡养老人": D("3000"),
    "大病医疗": D("0"),   # 据实扣除，不设固定额
}


def _bracket(taxable, table):
    for cap, rate, quick in table:
        if cap is None or taxable <= cap:
            return rate, quick
    return table[-1][1], table[-1][2]


def iit_comprehensive(salary, months_paid=1, social_insurance=0,
                      special_deduction=0, other_deduction=0,
                      threshold=5000):
    """综合所得（工资薪金）累计预扣预缴。

    salary            本年度累计工资收入（元）；months_paid=1 时即当月工资
    social_insurance  累计个人负担的三险一金（元）
    special_deduction 累计专项附加扣除（元）
    threshold         每月减除费用 5000
    """
    salary = D(str(salary))
    si = D(str(social_insurance))
    sd = D(str(special_deduction))
    od = D(str(other_deduction))
    mp = max(int(months_paid), 1)
    if salary < 0:
        return CalcResult.fail("iit.comprehensive", "收入不能为负")
    cum_threshold = D(str(threshold)) * mp
    taxable = salary - cum_threshold - si - sd - od
    steps = [
        {"label": f"累计收入（{mp} 个月）", "expr": f"{salary}", "value": salary},
        {"label": f"累计减除费用 5000×{mp}", "expr": f"− {cum_threshold}", "value": -cum_threshold},
        {"label": "累计三险一金", "expr": f"− {si}", "value": -si},
        {"label": "累计专项附加扣除", "expr": f"− {sd}", "value": -sd},
    ]
    if od > 0:
        steps.append({"label": "累计其他扣除", "expr": f"− {od}", "value": -od})
    if taxable <= 0:
        steps.append({"label": "累计应纳税所得额 ≤ 0，本期不预缴", "expr": f"{taxable} ≤ 0", "value": D(0)})
        return CalcResult(
            "iit.comprehensive", D(0),
            formula=f"累计应纳税所得额 {taxable} ≤ 0，本期无需预缴",
            steps=steps,
            basis=[BASIS_LAW, BASIS_PREPAY],
            caveats=["累计应纳税所得额为负时不退不补，结转以后月份累计计算",
                     "本公式为工资薪金累计预扣法；劳务报酬/稿酬/特许权使用费另有预扣率"],
            params={"salary": str(salary), "months_paid": mp},
        )
    rate, quick = _bracket(taxable, BRACKET_MONTHLY)
    tax = money(taxable * rate - quick)
    if tax < 0:
        tax = D(0)
    steps.append({"label": f"累计应纳税所得额", "expr": f"{taxable}", "value": taxable})
    steps.append({"label": f"适用税率 {rate * 100}%、速算扣除数 {quick}",
                  "expr": f"{taxable} × {rate} − {quick}", "value": tax})
    return CalcResult(
        "iit.comprehensive", tax,
        formula=f"（{salary} − {cum_threshold} − {si} − {sd}）× {rate * 100}% − {quick} = {tax}",
        steps=steps,
        basis=[BASIS_LAW, BASIS_PREPAY],
        caveats=["累计预扣法下本期应预缴 = 累计应预缴 − 累计已预缴（本工具默认已预缴 0）",
                 "专项附加扣除标准：婴幼儿照护/子女教育 2000 元/月/孩、赡养老人 3000 元/月、"
                 "住房贷款利息 1000 元/月、住房租金 1500 元/月（以主要工作城市为准）",
                 "年度终了后 3 月 1 日至 6 月 30 日办理汇算清缴，多退少补"],
        params={"salary": str(salary), "months_paid": mp, "social_insurance": str(si),
                "special_deduction": str(sd), "threshold": threshold},
    )


def iit_annual_bonus(bonus):
    """全年一次性奖金单独计税：奖金 ÷ 12 查月度税率表，再按该税率计税。

    （财政部 税务总局公告 2023 年第 30 号，执行至 2027-12-31）
    """
    bonus = D(str(bonus))
    if bonus <= 0:
        return CalcResult.fail("iit.bonus", "奖金金额须大于 0")
    monthly = bonus / D(12)
    rate, quick = _bracket(monthly, BRACKET_BONUS)
    tax = money(bonus * rate - quick)
    return CalcResult(
        "iit.bonus", tax,
        formula=f"{bonus} × {rate * 100}% − {quick} = {tax}（换算月均 {money(monthly)} 查表）",
        steps=[
            {"label": "月均换算", "expr": f"{bonus} ÷ 12", "value": money(monthly)},
            {"label": f"查月度税率表得 {rate * 100}%、速算扣除 {quick}", "expr": f"换算 {money(monthly)}",
             "value": rate},
            {"label": "应纳税额", "expr": f"{bonus} × {rate} − {quick}", "value": tax},
        ],
        basis=[BASIS_BONUS],
        caveats=["单独计税政策执行至 2027-12-31；此后是否延续须核对官方公告",
                 "每个纳税人在一个纳税年度内只允许采用一次单独计税",
                 "若并入综合所得更有利（低收入者常见），须两种方式各算一遍取低"],
        params={"bonus": str(bonus)},
    )


def iit_business(annual_profit, cost_deduction=0):
    """经营所得（个体户/个人独资/合伙企业个人合伙人）：五级超额累进。

    annual_profit   年度收入总额 − 成本费用等（元）
    cost_deduction  另可扣除的业主费用等（默认 0，起征 60000 元/年已在表内口径）
    """
    profit = D(str(annual_profit))
    cost = D(str(cost_deduction))
    taxable = profit - cost
    if taxable <= 0:
        return CalcResult(
            "iit.business", D(0),
            formula=f"应纳税所得额 {taxable} ≤ 0，不纳税",
            steps=[{"label": "应纳税所得额", "expr": f"{profit} − {cost}", "value": taxable}],
            basis=[BASIS_BIZ],
            caveats=["经营所得不得减除生计费用 6 万/年（与综合所得减除费用重复扣除有限制）"],
            params={"annual_profit": str(profit)},
        )
    rate, quick = _bracket(taxable, BRACKET_BIZ)
    tax = money(taxable * rate - quick)
    return CalcResult(
        "iit.business", tax,
        formula=f"{taxable} × {rate * 100}% − {quick} = {tax}",
        steps=[{"label": "应纳税所得额", "expr": f"{profit} − {cost}", "value": taxable},
               {"label": f"适用 {rate * 100}%、速算扣除 {quick}",
                "expr": f"{taxable} × {rate} − {quick}", "value": tax}],
        basis=[BASIS_BIZ],
        caveats=["个体工商户年应纳税所得额 ≤200 万部分减半征收（至 2027-12-31），须另按条件判断",
                 "经营所得按年计算、分月/季预缴、次年 3 月 31 日前汇算清缴"],
        params={"annual_profit": str(profit), "cost_deduction": str(cost)},
    )
