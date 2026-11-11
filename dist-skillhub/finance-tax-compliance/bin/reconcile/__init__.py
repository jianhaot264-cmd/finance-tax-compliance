#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reconcile — 三流一致核对（零依赖）
===================================

输入（一期：结构化文件，CSV / XLSX / JSON）：
  发票明细、银行流水、合同台账
处理：
  1. 金额逻辑校验：价税合计 = 不含税金额 + 税额；税额 = 不含税 × 税率（容差 ±0.10 元）
  2. 合同—发票—资金三流一致性核对
  3. 税负率异常预警
输出：
  可视化核对报告（HTML + 结构化 dict）

【红线】全部确定性规则计算，不调用 LLM；容差口径写死在 CHECKS 中。
"""

__all__ = ["reconcile", "parse_file", "render_report"]
TOLERANCE = 0.10   # 金额容差（元）
SNAPSHOT = "2026-11-08"


def parse_file(path, kind=None):
    """按扩展名解析 CSV/XLSX/JSON → list[dict]（首行为表头）。"""
    from .parsers import parse as _p
    return _p(path, kind)


def reconcile(invoices=None, bank=None, contracts=None, tax_rate=None):
    """执行三流核对，返回结构化结果。"""
    from .checks import run_checks
    return run_checks(invoices or [], bank or [], contracts or [], tax_rate)


def render_report(result, out_path):
    """生成 HTML 可视化核对报告。"""
    from .report import render
    return render(result, out_path)
