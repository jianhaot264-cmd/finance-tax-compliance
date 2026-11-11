#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vat.py — 增值税 + 附加税确定性计算
==================================

口径来源（2026-01-01 起增值税法 + 配套公告，SNAPSHOT 核验）：
  - 《中华人民共和国增值税法》（2026-01-01 施行）
  - 财政部 税务总局公告 2026 年第 10 号（简易计税 15 项/5% 6 项、差额扣除 12 项）
  - 财政部 税务总局公告 2023 年第 19 号（小规模月 10 万免征；3% 减按 1%，至 2027-12-31）
  - 财政部 税务总局公告 2025 年第 7 号（期末留抵退税）
  - 附加税：城建税法（市区 7% / 县城镇 5% / 其他 1%）+ 教育费附加 3% + 地方教育附加 2%

【红线】本模块为纯函数；任何税率/门槛改动必须改这里并更新 SNAPSHOT，禁止在 LLM 侧计算。
"""

from decimal import Decimal

from . import CalcResult, _basis, money

D = Decimal

# ---- 税率表（含法条依据）----
RATE_STANDARD = {"13": D("0.13"), "9": D("0.09"), "6": D("0.06")}
RATE_SIMPLE = {"3": D("0.03"), "5": D("0.05")}
DEEMED_1PCT = D("0.01")          # 小规模 3% 减按 1%（2023 年 19 号，至 2027-12-31）
THRESHOLD_MONTH = D("100000")    # 月销售额 10 万（小规模免征）
THRESHOLD_QUARTER = D("300000")  # 季度 30 万

BASIS_VAT = _basis("《中华人民共和国增值税法》", "第十条至第二十条", "2026-01-01")
BASIS_SIMPLE = _basis("财政部 税务总局公告 2026 年第 10 号", "简易计税项目与征收率", "2026-01-01 至 2027-12-31")
BASIS_SMALL = _basis("财政部 税务总局公告 2023 年第 19 号", "小规模纳税人免征与减征", "2023-01-01 至 2027-12-31")
BASIS_CREDIT = _basis("财政部 税务总局公告 2025 年第 7 号", "期末留抵退税", "2025-01-01")
BASIS_SUR = [
    _basis("《中华人民共和国城市维护建设税法》", "第四条", "2021-09-01"),
    _basis("《征收教育费附加的暂行规定》", "第三条", "2011-01-01"),
    _basis("财政部关于统一地方教育附加政策有关问题的通知", "第一条", "2010-01-01"),
]


def vat_small_scale(sales, period="month", levy_rate="3", deemed=True):
    """小规模纳税人增值税：月/季销售额未超门槛免征；超过全额按征收率，3% 可减按 1%。

    sales      不含税销售额（元）
    period     'month' | 'quarter'
    levy_rate  '3' | '5'
    deemed     是否适用 3% 减按 1%
    """
    sales = D(str(sales))
    if sales < 0:
        return CalcResult.fail("vat.small", "销售额不能为负", {"sales": str(sales)})
    threshold = THRESHOLD_MONTH if period == "month" else THRESHOLD_QUARTER
    rate = D("0.01") if (deemed and levy_rate == "3") else RATE_SIMPLE[levy_rate]
    steps = []
    if sales <= threshold:
        steps.append({"label": f"月/季销售额 {sales} ≤ 起征点 {threshold}，适用免征",
                      "expr": f"{sales} ≤ {threshold}", "value": D(0)})
        return CalcResult(
            "vat.small", D(0),
            formula=f"销售额 {sales} 未超起征点 {threshold}，免征增值税",
            steps=steps,
            basis=[BASIS_SMALL],
            caveats=[f"起征点：月 {THRESHOLD_MONTH} / 季 {THRESHOLD_QUARTER}（不含税销售额）",
                     "免征则城建税及两项附加同步免除（以实际缴纳增值税为计税依据）",
                     "3% 减按 1% 执行至 2027-12-31，此后是否延续须核对官方公告"],
            params={"sales": str(sales), "period": period, "levy_rate": levy_rate,
                    "deemed": deemed},
        )
    tax = money(sales * rate)
    steps.append({"label": f"适用征收率 {rate * 100}%", "expr": f"{sales} × {rate}",
                  "value": tax})
    if deemed and levy_rate == "3":
        steps.append({"label": "3% 减按 1% 优惠（2023 年 19 号）",
                      "expr": f"原 3% 应纳 {money(sales * D('0.03'))} → 减按 1%",
                      "value": tax})
    return CalcResult(
        "vat.small", tax,
        formula=f"{sales} × {rate * 100}% = {tax}",
        steps=steps,
        basis=[BASIS_SMALL, BASIS_SIMPLE],
        caveats=["此处为销售额全额计税；差额征税项目须先扣除可扣减额再按征收率计税",
                 "月/季销售额超起征点后为全额征税，不设分段减免",
                 "开具增值税专用发票的销售额部分不得免征"],
        params={"sales": str(sales), "period": period, "levy_rate": levy_rate,
                "deemed": deemed},
    )


def vat_general(sales, input_tax, rate="13", sales_tax=None):
    """一般纳税人增值税：应纳税额 = 销项税额 − 进项税额。

    sales      不含税销售额（元）
    input_tax  可抵扣进项税额（元）
    rate       '13' | '9' | '6'
    sales_tax  可选：已知销项税额时直接使用（用于反算校验）
    """
    sales = D(str(sales))
    input_tax = D(str(input_tax))
    if rate not in RATE_STANDARD:
        return CalcResult.fail("vat.general", f"无效税率 {rate}", {"rate": rate})
    if input_tax < 0:
        return CalcResult.fail("vat.general", "进项税额不能为负")
    r = RATE_STANDARD[rate]
    output = D(str(sales_tax)) if sales_tax is not None else money(sales * r)
    steps = [
        {"label": f"销项税额（{rate}%）", "expr": f"{sales} × {r}", "value": output},
        {"label": "进项税额（可抵扣）", "expr": f"− {input_tax}", "value": -input_tax},
    ]
    payable = money(output - input_tax)
    if payable < 0:
        steps.append({"label": "进项大于销项，形成留抵", "expr": f"{output} − {input_tax} < 0",
                      "value": payable})
        return CalcResult(
            "vat.general", D(0),
            formula=f"{output} − {input_tax} = {payable}（留抵，不退税时结转下期继续抵扣）",
            steps=steps,
            basis=[BASIS_VAT, BASIS_CREDIT],
            caveats=["当期进项大于销项形成期末留抵；是否适用留抵退税（2025 年第 7 号）须另按条件判断",
                     "不得抵扣进项（如集体福利、简易计税项目、非正常损失）须先剔除后再计算"],
            params={"sales": str(sales), "input_tax": str(input_tax), "rate": rate},
        )
    steps.append({"label": "应纳税额", "expr": f"{output} − {input_tax}", "value": payable})
    return CalcResult(
        "vat.general", payable,
        formula=f"{output} − {input_tax} = {payable}",
        steps=steps,
        basis=[BASIS_VAT],
        caveats=["销项 − 进项为一般计税基本公式；进项须取得合规扣税凭证并在用途确认后抵扣",
                 "适用 9%（交通运输/建筑/不动产租赁等）或 6%（现代服务/金融等）须先判断税目"],
        params={"sales": str(sales), "input_tax": str(input_tax), "rate": rate},
    )


def vat_simple(sales, rate="3", deduction=0):
    """简易计税：应纳税额 =（销售额 − 可扣除额）× 征收率。

    deduction  差额征税可扣除额（元），默认 0
    """
    sales = D(str(sales))
    deduction = D(str(deduction))
    if rate not in RATE_SIMPLE:
        return CalcResult.fail("vat.simple", f"无效征收率 {rate}")
    if deduction > sales:
        return CalcResult.fail("vat.simple", "扣除额不得超过销售额")
    base = sales - deduction
    r = RATE_SIMPLE[rate]
    tax = money(base * r)
    expr = f"({sales} − {deduction}) × {r}"
    return CalcResult(
        "vat.simple", tax,
        formula=f"{expr} = {tax}",
        steps=[{"label": f"计税依据（差额后）", "expr": f"{sales} − {deduction}", "value": base},
               {"label": f"应纳税额（{rate}%）", "expr": expr, "value": tax}],
        basis=[BASIS_SIMPLE],
        caveats=["差额扣除仅限 2026 年第 10 号公告列举的 12 项，未列举不得扣除",
                 "5% 征收率适用于不动产销售/租赁、劳务派遣差额等 6 个项目"],
        params={"sales": str(sales), "rate": rate, "deduction": str(deduction)},
    )


def surcharge(vat_paid, city_rate="7", region="市区"):
    """附加税：城建税 + 教育费附加 + 地方教育附加（以实际缴纳的增值税为计税依据）。

    city_rate  '7' 市区 / '5' 县城镇 / '1' 其他
    """
    vat_paid = D(str(vat_paid))
    if vat_paid < 0:
        return CalcResult.fail("surcharge", "实缴增值税不能为负")
    cr = {"7": D("0.07"), "5": D("0.05"), "1": D("0.01")}.get(city_rate)
    if cr is None:
        return CalcResult.fail("surcharge", f"无效城建税率 {city_rate}")
    city = money(vat_paid * cr)
    edu = money(vat_paid * D("0.03"))
    local = money(vat_paid * D("0.02"))
    total = money(city + edu + local)
    return CalcResult(
        "surcharge", total,
        formula=f"{vat_paid} ×（{cr} + 3% + 2%）= {city} + {edu} + {local} = {total}",
        steps=[
            {"label": f"城建税（{region} {cr * 100}%）", "expr": f"{vat_paid} × {cr}", "value": city},
            {"label": "教育费附加（3%）", "expr": f"{vat_paid} × 0.03", "value": edu},
            {"label": "地方教育附加（2%）", "expr": f"{vat_paid} × 0.02", "value": local},
            {"label": "附加税合计", "expr": f"{city} + {edu} + {local}", "value": total},
        ],
        basis=BASIS_SUR,
        caveats=[f"城建税税率按地区：市区 7% / 县城镇 5% / 其他 1%；本次按「{region}」",
                 "进口环节不征城建税；出口退还增值税时城建税不退",
                 "小规模纳税人及小型微利企业等「六税两费」减半（至 2027-12-31）须另按条件判断",
                 "月销售额 10 万以下免征增值税的，两项附加同步免征"],
        params={"vat_paid": str(vat_paid), "city_rate": city_rate, "region": region},
    )
