#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stamp.py — 印花税 + 契税确定性计算
===================================

口径来源（SNAPSHOT 核验）：
  - 《中华人民共和国印花税法》（2022-07-01 施行）所附《税目税率表》
  - 印花税法第三条：同一应税凭证载有两个以上税目事项并分别列明的，分别计税；
    未分别列明的，从高适用税率
  - 《中华人民共和国契税法》（2021-09-01 施行）第三条：税率 3%—5%
  - 财政部 税务总局 住房城乡建设部公告 2024 年第 14 号（住房交易契税优惠，
    2024-12-01 起）：≤140㎡ 首套/二套 1%；>140㎡ 首套 1.5%、二套 2%

【红线】纯函数；13 税目税率为法定附表，禁止按旧暂行条例硬编码。
"""

from decimal import Decimal

from . import CalcResult, _basis, money

D = Decimal

# 印花税 13 税目（税率均为万分之、千分之）
STAMP_ITEMS = {
    "借款合同": D("0.00005"),        # 万分之零点五
    "融资租赁合同": D("0.00005"),
    "买卖合同": D("0.0003"),         # 万分之三
    "承揽合同": D("0.0003"),
    "建设工程合同": D("0.0003"),
    "运输合同": D("0.0003"),
    "技术合同": D("0.0003"),
    "租赁合同": D("0.001"),          # 千分之一
    "保管合同": D("0.001"),
    "仓储合同": D("0.001"),
    "财产保险合同": D("0.001"),
    "产权转移书据": D("0.0005"),     # 万分之五
    "营业账簿": D("0.00025"),        # 万分之二点五（实收资本+资本公积）
    "证券交易": D("0.001"),          # 千分之一（出让方）
}
# 合同同时载明多事项时未列明从高
HIGH_RATE = D("0.001")

BASIS_STAMP = _basis("《中华人民共和国印花税法》", "《税目税率表》及第三条", "2022-07-01")
BASIS_DEED = _basis("《中华人民共和国契税法》", "第三条", "2021-09-01")
BASIS_HOUSE = _basis("财政部 税务总局 住房城乡建设部公告 2024 年第 14 号",
                     "住房交易契税优惠", "2024-12-01")


def stamp_duty(items, listed_separately=True):
    """印花税：分税目计税；同一凭证多税目未分别列明的从高。

    items               [(税目, 计税金额), ...]，税目须为 STAMP_ITEMS 的键
    listed_separately   合同是否分别列明各税目金额
    """
    if not items:
        return CalcResult.fail("stamp", "未提供税目与计税金额")
    steps = []
    detail = []
    if not listed_separately:
        total = sum((D(str(a)) for _, a in items), D(0))
        rate = HIGH_RATE
        tax = money(total * rate)
        steps.append({"label": "多税目未分别列明，从高适用税率",
                      "expr": f"{total} × {rate}（{rate * 1000}‰）", "value": tax})
        return CalcResult(
            "stamp", tax,
            formula=f"{total} × {rate * 1000}‰ = {tax}（未分别列明，从高）",
            steps=steps,
            basis=[BASIS_STAMP],
            caveats=["同一应税凭证载有两个以上税目但未分别列明金额的，从高适用税率",
                     "分别列明的可分税目计税，建议在合同中分项写明金额以降低税负",
                     "小规模纳税人、小型微利企业、个体工商户「六税两费」减半含印花税"
                     "（不含证券交易印花税），须另按条件判断"],
            params={"items": [[k, str(v)] for k, v in items], "listed_separately": False},
        )
    total_tax = D(0)
    for name, amount in items:
        if name not in STAMP_ITEMS:
            return CalcResult.fail("stamp", f"未知税目「{name}」，可用：{('、'.join(STAMP_ITEMS))}")
        amt = D(str(amount))
        rate = STAMP_ITEMS[name]
        t = money(amt * rate)
        total_tax += t
        detail.append({"item": name, "amount": str(amt), "rate": str(rate), "tax": str(t)})
        steps.append({"label": f"{name}（{rate * 10000 / 100:g}‱）",
                      "expr": f"{amt} × {rate}", "value": t})
    total_tax = money(total_tax)
    steps.append({"label": "合计应纳税额", "expr": " + ".join(d["tax"] for d in detail),
                  "value": total_tax})
    return CalcResult(
        "stamp", total_tax,
        formula=" + ".join(f"{d['item']} {d['amount']}×{d['rate']}={d['tax']}" for d in detail)
                + f" → 合计 {total_tax}",
        steps=steps,
        basis=[BASIS_STAMP],
        caveats=["税目税率按《印花税法》所附税目税率表（2022-07-01 起），旧暂行条例税目不得沿用",
                 "应税合同的计税依据为合同所列的金额（不含列明的增值税税款）",
                 "未履行的应税合同仍需缴纳印花税（合同签订即纳税义务发生）"],
        params={"items": [[k, str(v)] for k, v in items], "listed_separately": True},
    )


def deed_tax(price, is_first_home=True, area=140, region="全国", is_residential=True):
    """契税：住房 2024-12-01 起分档；非住房按 3%—5% 幅度（本工具默认 3%）。

    price         成交价格（元，不含增值税）
    is_first_home 是否首套（家庭唯一住房）
    area          建筑面积（㎡）
    """
    price = D(str(price))
    if price <= 0:
        return CalcResult.fail("deed", "成交价格须大于 0")
    area = D(str(area))
    steps = [{"label": "计税依据（成交价格）", "expr": str(price), "value": price}]
    caveats = []
    if is_residential:
        if area <= 140:
            rate = D("0.01")
            tier = f"≤140㎡（{'首套' if is_first_home else '二套'}）1%"
        else:
            rate = D("0.015") if is_first_home else D("0.02")
            tier = f">140㎡（{'首套' if is_first_home else '二套'}）{rate * 100}%"
        basis = [BASIS_DEED, BASIS_HOUSE]
        caveats.append(f"适用 {tier}（财政部 税务总局 住建部公告 2024 年第 14 号，2024-12-01 起）")
        caveats.append("家庭唯一住房以家庭（购房人、配偶及未成年子女）为单位认定")
    else:
        rate = D("0.03")
        steps.append({"label": "非住宅按 3%—5% 幅度，本工具按 3%", "expr": "幅度下限", "value": rate})
        basis = [BASIS_DEED]
        caveats.append("非住宅契税税率 3%—5%，具体由省级人民政府在幅度内确定，须核对属地口径")
    tax = money(price * rate)
    steps.append({"label": f"应纳契税（{rate * 100}%）", "expr": f"{price} × {rate}", "value": tax})
    return CalcResult(
        "deed", tax,
        formula=f"{price} × {rate * 100}% = {tax}",
        steps=steps,
        basis=basis,
        caveats=caveats + [f"地区口径：{region}；本工具未做属地差异调整，"
                          "省级具体税率与减免须核对当地财政/税务部门公告"],
        params={"price": str(price), "is_first_home": is_first_home,
                "area": str(area), "region": region},
    )
