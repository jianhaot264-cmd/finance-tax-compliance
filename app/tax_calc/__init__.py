#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tax_calc — 确定性涉税计算引擎（零依赖）
========================================

【红线】涉税数值一律由本引擎确定性算出，LLM 禁止直接产出数值结果。
      本包内所有函数为纯函数：同输入必同输出，可单测、可复现。

输出契约（每个 CalcResult）：
  value       税额/应纳税额（Decimal，保留 2 位）
  formula     人类可读算式（含代入数值）
  steps       分步明细 [{label, expr, value}]
  basis       法条/文件依据 [{name, article, effective, region}]
  caveats     适用条件与限制（必须随结果展示）
  snapshot    政策快照日期（本引擎内置税率表的核验截止日）

四类税种模块：
  vat     增值税 + 附加税（一般计税 / 简易计税 / 差额 / 留抵 / 小微免征）
  iit     个人所得税（综合所得累计预扣 / 年终奖单独计税 / 经营所得）
  cit     企业所得税（小型微利季度预缴 / 25% 基本 / 汇算）
  stamp   印花税（13 税目 + 合同分别列明）+ 契税（2024 住房分档）

用法：
  from tax_calc import calc
  r = calc("小规模纳税人月销售额 8 万，增值税多少？")
  # 或直接：from tax_calc.vat import vat_small_scale
"""

from decimal import Decimal, ROUND_HALF_UP

SNAPSHOT = "2026-11-08"   # 税率表核验截止日；政策变动须重算并更新

__all__ = ["CalcResult", "money", "SNAPSHOT", "calc"]


def money(x) -> Decimal:
    """统一金额精度：四舍五入到分。"""
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CalcResult(dict):
    """计算结果（dict 子类，便于 JSON 序列化）。"""

    def __init__(self, kind, value, formula, steps, basis, caveats=None,
                 params=None, ok=True, error=""):
        super().__init__(
            kind=kind, ok=ok, error=error,
            value=str(money(value)) if ok else None,
            formula=formula,
            steps=[{**s, "value": str(money(s["value"]))} if isinstance(s.get("value"), (int, float, Decimal))
                   else s for s in steps],
            basis=basis,
            caveats=caveats or [],
            params=params or {},
            snapshot=SNAPSHOT,
            engine="tax_calc/1.0",
        )

    @classmethod
    def fail(cls, kind, error, params=None):
        return cls(kind, Decimal(0), "", [], [], ok=False, error=error, params=params)


def _basis(name, article="", effective="", region="全国"):
    return {"name": name, "article": article, "effective": effective,
            "region": region, "snapshot": SNAPSHOT}


def calc(question: str, params: dict | None = None):
    """统一入口：按问题/参数路由到具体税种模块。见 router.py。"""
    from .router import route
    return route(question, params or {})
