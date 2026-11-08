#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
router.py — 计算意图识别与参数抽取
===================================

【红线】识别到计算类问题 → 只调本地确定性脚本，LLM 不产出数值。
识别不到足够参数 → 返回「需补充参数」而非让 LLM 猜。

路由策略：
  1. 显式参数调用 calc()（前端表单/API 直传）→ 精确路由
  2. 自然语言问题 → 意图分类 + 正则抽数（金额/税率/期间/身份）
"""

import re
from decimal import Decimal

from . import CalcResult

D = Decimal

# 金额识别（支持 万/亿 单位与千分位）
AMT_RE = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(亿|万|万元|亿元|元)?")
RATE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# 意图关键词 → (tax_kind, sub)
INTENTS = [
    ("vat_small", r"(小规模|月销售额|季度销售额|起征点|10\s*万|30\s*万).{0,12}(增值税|税|缴|交|免)"),
    ("vat_general", r"(一般纳税人|销项|进项|留抵).{0,12}(增值税|税|缴|交|抵)"),
    ("vat_simple", r"(简易计税|征收率|差额征税).{0,12}(税|计算|缴)"),
    ("surcharge", r"(城建|城市维护建设|教育费附加|地方教育|附加税|两费)"),
    ("iit_bonus", r"(年终奖|全年一次性奖金|一次性奖金)"),
    ("iit_comprehensive", r"(工资|月薪|个税|个人所得税|预扣|专项附加).{0,16}(多少|缴|交|算|预扣)"),
    ("iit_business", r"(经营所得|个体户|个体工商户|个人独资).{0,12}(个税|所得税|税)"),
    ("cit_quarterly", r"(企业所得税|季度预缴|汇算|小微|小型微利).{0,14}(多少|缴|交|算|预缴|税率)"),
    ("cit_deduction", r"(扣除比例|扣除限额|职工教育经费|广宣费|广告费|业务招待费|捐赠|福利费|工会经费)"),
    ("stamp", r"(印花税|应税凭证|税目)"),
    ("deed", r"(契税|首套|二套|购房)"),
]


def _parse_amounts(text):
    """抽取金额（归一到元）与百分比。"""
    amts = []
    for m in AMT_RE.finditer(text):
        num = D(m.group(1).replace(",", ""))
        unit = m.group(2) or ""
        if unit.startswith("亿"):
            num *= D(100000000)
        elif unit.startswith("万"):
            num *= D(10000)
        # 无单位且 <100 的数字更可能是税率/数量，跳过
        if unit == "" and num < 100:
            continue
        # 无单位的 4 位数字仅在「年份/文号」语境才算年份（〔2018〕、2018年、…2018号），
        # 否则「专项附加 2000」这类金额不能被误杀
        if unit == "" and 1900 <= num <= 2100 and float(num) == int(num):
            seg_start = max(0, m.start() - 2)
            seg_end = min(len(text), m.end() + 2)
            ctx = text[seg_start:seg_end]
            import re as _re
            if _re.search(r"[〔\[（(]\s*19\d{2}|\s19\d{2}\s*[〕\]）)]|19\d{2}\s*年|19\d{2}\s*号", ctx) or                _re.search(r"[〔\[（(]\s*20\d{2}|\s20\d{2}\s*[〕\]）)]|20\d{2}\s*年|20\d{2}\s*号", ctx):
                continue
        amts.append(num)
    return amts


# 计算意图判定：必须「有金额/参数」且「有计算动词或明确税种」——
# 仅出现税种名词的解释题（如「印花税按什么法律征」）不算计算类，交回规则/检索。
CALC_VERB_RE = re.compile(
    r"(多少|怎么算|怎么缴|怎么交|算一下|算下|计算|应缴|应纳|要交|要缴|缴多少|交多少|税额多少|多少钱)")
TAX_TERM_RE = re.compile(
    r"(增值税|个税|个人所得税|企业所得税|印花税|契税|城建|教育费附加|附加税|年终奖|社保|残保金)")


def _detect_intent(text):
    text = text or ""
    # 核验/冲突裁决类问句（「听谁的」「哪个为准」「附的税率表能直接用吗」）不是计算题
    if re.search(r"听谁的|以哪个为准|哪个为准|到底听|能直接用来算税|口径冲突|冲突时听|法条写|附的税率表", text):
        return None
    has_amount = bool(_parse_amounts(text))
    has_verb = bool(CALC_VERB_RE.search(text))
    has_tax = bool(TAX_TERM_RE.search(text))
    # 严格闸门：无金额的解释题一律不算计算类（避免抢答「…是多少」类口径咨询）
    if not has_amount:
        return None
    if not (has_verb or has_tax):
        return None
    for kind, pat in INTENTS:
        if re.search(pat, text):
            return kind
    # 兜底：有金额 + 有税种
    if has_tax:
        if "增值" in text or "发票" in text:
            return "vat_small"
        if "个税" in text or "工资" in text:
            return "iit_comprehensive"
        if "企业所得税" in text or "小微" in text:
            return "cit_quarterly"
    return None


def route(question: str, params: dict | None = None):
    """路由入口：优先用显式 params，否则从 question 抽取。"""
    params = dict(params or {})
    kind = params.pop("kind", None) or _detect_intent(question or "")

    if kind is None:
        # 不是计算类：交给上层走检索/LLM（返回 None 让 server 不接管）
        return None

    from . import vat, iit, cit, stamp

    # 若自然语言里能抽数但 params 缺失，按语义顺序映射（避免「三险一金/专项附加」丢失）
    if not params:
        qtext = question or ""
        amts = _parse_amounts(qtext)
        rates = RATE_RE.findall(qtext)
        if amts:
            params.setdefault("sales", str(amts[0]))
            params.setdefault("salary", str(amts[0]))
            params.setdefault("bonus", str(amts[0]))
            params.setdefault("profit", str(amts[0]))
            params.setdefault("price", str(amts[0]))
            params.setdefault("base_amount", str(amts[0]))
        # 个税：识别「三险一金」「专项附加」并按出现顺序取后续金额
        if kind == "iit_comprehensive" and len(amts) >= 2:
            import re as _re
            si_pos = _re.search(r"三险一金|社保|个人负担", qtext)
            sd_pos = _re.search(r"专项附加|专项扣除|附加扣除", qtext)
            used = {0}
            if si_pos and len(amts) >= 2:
                params["social_insurance"] = str(amts[1]); used.add(1)
            if sd_pos and len(amts) >= 3:
                params["special_deduction"] = str(amts[2]); used.add(2)
            elif sd_pos and len(amts) >= 2 and 1 not in used:
                params["special_deduction"] = str(amts[1]); used.add(1)
        # 一般纳税人：销项额 + 进项额
        if kind == "vat_general" and len(amts) >= 2:
            params["sales"] = str(amts[0])
            params["input_tax"] = str(amts[1])
        # 小微企业：利润 + 人数/资产
        if kind == "cit_quarterly" and len(amts) >= 2:
            params["profit"] = str(amts[0])
        # 印花税多税目：取第一个金额作为计税依据
        if rates:
            params.setdefault("rate", rates[0])
        if "季度" in qtext:
            params.setdefault("period", "quarter")
        if "小规模" in qtext:
            params.setdefault("is_small", True)

    try:
        if kind == "vat_small":
            return vat.vat_small_scale(
                params.get("sales", 0),
                period=params.get("period", "month"),
                levy_rate=params.get("levy_rate", "3"),
                deemed=params.get("deemed", True),
            )
        if kind == "vat_general":
            return vat.vat_general(
                params.get("sales", 0),
                params.get("input_tax", 0),
                rate=params.get("rate", "13"),
            )
        if kind == "vat_simple":
            return vat.vat_simple(
                params.get("sales", 0),
                rate=params.get("rate", "3"),
                deduction=params.get("deduction", 0),
            )
        if kind == "surcharge":
            return vat.surcharge(
                params.get("vat_paid", 0),
                city_rate=params.get("city_rate", "7"),
                region=params.get("region", "市区"),
            )
        if kind == "iit_comprehensive":
            return iit.iit_comprehensive(
                params.get("salary", 0),
                months_paid=int(params.get("months_paid", 1)),
                social_insurance=params.get("social_insurance", 0),
                special_deduction=params.get("special_deduction", 0),
            )
        if kind == "iit_bonus":
            return iit.iit_annual_bonus(params.get("bonus", 0))
        if kind == "iit_business":
            return iit.iit_business(
                params.get("annual_profit", params.get("profit", 0)),
                cost_deduction=params.get("cost_deduction", 0),
            )
        if kind == "cit_quarterly":
            return cit.cit_quarterly(
                params.get("profit", 0),
                is_small=params.get("is_small", True),
                employees=int(params.get("employees", 0)),
                assets=params.get("assets", 0),
            )
        if kind == "cit_deduction":
            return cit.cit_deduction(
                params.get("name", "职工教育经费"),
                params.get("base_amount", 0),
                params.get("incurred_amount"),
            )
        if kind == "stamp":
            items = params.get("items")
            if not items:
                # 从问题里找税目
                from .stamp import STAMP_ITEMS
                found = [(n, params.get("amount", params.get("sales", 0)))
                         for n in STAMP_ITEMS if n in (question or "")]
                items = found or [("买卖合同", params.get("sales", params.get("amount", 0)))]
            return stamp.stamp_duty(
                [(k, v) for k, v in items],
                listed_separately=params.get("listed_separately", True),
            )
        if kind == "deed":
            return stamp.deed_tax(
                params.get("price", 0),
                is_first_home=params.get("is_first_home", True),
                area=float(params.get("area", 140)),
                region=params.get("region", "全国"),
            )
        return CalcResult.fail(kind, f"未实现的计算类型 {kind}")
    except Exception as exc:  # noqa: BLE001
        return CalcResult.fail(kind, f"计算失败：{exc}", params)
