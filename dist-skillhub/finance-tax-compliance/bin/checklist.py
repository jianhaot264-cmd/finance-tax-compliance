#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
checklist.py — 合规检查清单生成器（确定性）
============================================

按企业类型 / 税种生成：申报时间线 + 资料清单 + 风险点。
全部数据为规则内置（SNAPSHOT 核验），不调用 LLM、不猜测属地差异。

用法：
  from checklist import generate
  out = generate(enterprise_type="一般纳税人", tax_types=["增值税","企业所得税"])
"""

import json as _json
import os as _os


def _snapshot():
    """核验日期取知识库快照（kb.json.verified_at），避免写死导致过期口径。"""
    try:
        p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "kb.json")
        with open(p, "r", encoding="utf-8") as f:
            return _json.load(f).get("verified_at") or "以官方原文为准"
    except Exception:
        return "以官方原文为准"


SNAPSHOT = _snapshot()

# ---- 申报时间线（法定/常规）----
FILINGS = {
    "增值税": [
        ("每月/季终了 15 日内", "增值税及附加税费申报（小规模可季报）", "电子税务局"),
        ("每年 5 月 31 日前", "一般纳税人资格登记/变更（如需）", "主管税务机关"),
    ],
    "企业所得税": [
        ("每季度终了 15 日内", "季度预缴申报（A 类）", "电子税务局"),
        ("次年 5 月 31 日前", "年度汇算清缴（含纳税调整）", "电子税务局"),
    ],
    "个人所得税": [
        ("每月 15 日前", "工资薪金所得扣缴申报", "自然人电子税务局（扣缴端）"),
        ("次年 3 月 1 日—6 月 30 日", "综合所得汇算清缴（个人办理）", "个税 APP / 电子税务局"),
        ("次年 3 月 31 日前", "经营所得汇算清缴", "电子税务局"),
    ],
    "印花税": [
        ("按季/按次/按年", "印花税申报（按核定征收方式）", "电子税务局"),
    ],
    "社保非税": [
        ("每月 25 日前", "社会保险费自行申报缴纳（广东为自行申报模式）", "电子税务局/社保费管理客户端"),
        ("每年 3 月 31 日前", "残疾人就业保障金年审（如适用）", "残联年审系统"),
    ],
    "发票": [
        ("按月/按季", "发票领用与额度调整（数电票为授信额度制）", "电子税务局/税务数字账户"),
        ("开具红字发票时", "红字信息确认与红冲操作", "税务数字账户"),
    ],
}

# ---- 资料清单（按企业类型）----
DOCS_COMMON = [
    "营业执照、银行开户许可证",
    "会计账簿与凭证（含总账、明细账、日记账）",
    "发票与完税凭证（电子发票留存 XML/OFD）",
    "合同台账（含采购、销售、租赁、借款）",
    "工资表与社保缴费记录",
    "资产清单（固定资产折旧表、无形资产摊销表）",
]
DOCS_BY_TYPE = {
    "一般纳税人": [
        "进项发票认证/勾选确认记录",
        "进项税额转出台账（集体福利、简易计税项目）",
        "销项发票明细与开票汇总表",
        "一般纳税人资格登记文件",
    ] + DOCS_COMMON,
    "小规模纳税人": [
        "季度销售额台账（判断起征点 10 万/月、30 万/季）",
        "增值税专用发票开具记录（专票不免税）",
    ] + DOCS_COMMON,
    "个体工商户": [
        "经营所得收支账（查账征收）或核定征收通知书",
        "业主费用扣除与专项附加扣除记录",
    ] + DOCS_COMMON,
    "小微企业": [
        "小型微利企业三条件测算表（从业人数/资产总额/应纳税所得额）",
        "研发费用辅助账（如享受加计扣除）",
    ] + DOCS_COMMON,
}

# ---- 风险点（按税种）----
RISKS = {
    "增值税": [
        ("高", "进项税额转出不完整（集体福利、非正常损失、简易计税项目未剔除）"),
        ("高", "差额征税扣除额超出 2026 年第 10 号公告列举范围"),
        ("中", "小规模超起征点后未全额计税，误按分段减免"),
        ("中", "发票开具与收入确认时点不一致（跨期）"),
    ],
    "企业所得税": [
        ("高", "小型微利企业三条件（人数/资产/所得额）任一超标仍按 5% 缴纳"),
        ("高", "税前扣除凭证不合规（白条、不合规发票）"),
        ("中", "业务招待费 60% 与 5‰ 双限额取低未执行"),
        ("中", "广宣费 30% 特定行业口径误用（2025 年第 16 号，非所有行业）"),
    ],
    "个人所得税": [
        ("高", "年终奖单独计税与并入综合所得未取优（一个年度只能选一次）"),
        ("中", "专项附加扣除重复扣除（夫妻双方重复填报子女教育）"),
        ("中", "劳务报酬按工资薪金代扣，预扣率适用错误"),
    ],
    "印花税": [
        ("高", "合同未分别列明税目金额，被从高适用税率"),
        ("中", "应税合同未列明增值税税款导致计税依据含税"),
    ],
    "社保非税": [
        ("高", "自愿放弃社保协议无效，未足额缴纳被追缴+滞纳金"),
        ("中", "残保金未按安排比例分档计算"),
    ],
    "发票": [
        ("高", "虚开发票（无真实业务、资金回流）"),
        ("中", "红字发票处理不当导致税额重复转出"),
        ("中", "数电票用途确认未做导致进项无法抵扣"),
    ],
}

BASIS = "《中华人民共和国税收征收管理法》《增值税法》《企业所得税法》《个人所得税法》《印花税法》及配套公告（快照 " + SNAPSHOT + "）"
DISCLAIMER = ("本清单仅用于辅助合规自查与申报前准备，不构成专业税务/法律意见；"
              "具体申报口径以主管税务机关与官方最新公告为准。")


def generate(enterprise_type="一般纳税人", tax_types=None, region="全国"):
    """生成合规检查清单（结构化 dict）。"""
    tax_types = tax_types or ["增值税", "企业所得税", "个人所得税", "印花税", "社保非税", "发票"]
    timeline = []
    for t in tax_types:
        for when, what, channel in FILINGS.get(t, []):
            timeline.append({"tax": t, "when": when, "what": what, "channel": channel})
    docs = DOCS_BY_TYPE.get(enterprise_type, DOCS_COMMON)
    risks = []
    for t in tax_types:
        for level, desc in RISKS.get(t, []):
            risks.append({"tax": t, "level": level, "risk": desc})
    risks.sort(key=lambda r: {"高": 0, "中": 1, "低": 2}.get(r["level"], 3))
    return {
        "enterprise_type": enterprise_type,
        "region": region,
        "tax_types": tax_types,
        "snapshot": SNAPSHOT,
        "basis": BASIS,
        "timeline": timeline,
        "documents": docs,
        "risks": risks,
        "disclaimer": DISCLAIMER,
        "counts": {"filings": len(timeline), "documents": len(docs),
                   "risks_high": sum(1 for r in risks if r["level"] == "高"),
                   "risks_mid": sum(1 for r in risks if r["level"] == "中")},
    }


def render_html(out, out_path):
    import html
    from datetime import datetime

    def e(v):
        return html.escape(str(v if v is not None else ""))
    tl = "".join(
        f"<tr><td><span class='tag'>{e(x['tax'])}</span></td><td class='mono'>{e(x['when'])}</td>"
        f"<td>{e(x['what'])}</td><td class='mono'>{e(x['channel'])}</td></tr>"
        for x in out["timeline"])
    docs = "".join(f"<li>{e(d)}</li>" for d in out["documents"])
    risks = "".join(
        f"<tr><td><span class='tag {'high' if x['level']=='高' else 'mid'}'>{e(x['level'])}</span></td>"
        f"<td>{e(x['tax'])}</td><td>{e(x['risk'])}</td></tr>"
        for x in out["risks"])
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>合规检查清单</title><style>
*{{box-sizing:border-box}}body{{margin:0;font:14px/1.7 -apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;color:#1b324b;background:#f5f7fb}}
.wrap{{max-width:920px;margin:0 auto;padding:28px 20px 60px}}
h1{{font-size:22px;margin:0 0 6px;color:#102a43}}h2{{font-size:16px;margin:26px 0 12px;border-left:3px solid #2f6feb;padding-left:10px;color:#102a43}}
.sub{{color:#4a6580;font-size:13px}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin:16px 0}}
.card{{background:#fff;border:1px solid #dde5ef;border-radius:10px;padding:13px 15px}}.card b{{display:block;font-size:22px}}.card span{{font-size:11px;color:#8299b1}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #dde5ef;border-radius:10px;overflow:hidden;font-size:13px}}
th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid #e7eef7;vertical-align:top}}th{{background:#f1f5fa;font-size:11.5px;letter-spacing:.5px;color:#4a6580}}
.tag{{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600;background:#eaf1ff;color:#2f6feb}}
.tag.high{{background:#fdf0ee;color:#c0392b}}.tag.mid{{background:#fdf6e7;color:#a97013}}
ul{{margin:8px 0;padding-left:22px}}li{{margin:5px 0;font-size:13px}}
.mono{{font-family:Consolas,monospace;font-size:12px}}.fine{{margin-top:26px;padding-top:14px;border-top:1px solid #dde5ef;color:#8299b1;font-size:11.5px}}
</style></head><body><div class="wrap">
<h1>合规检查清单 · {e(out['enterprise_type'])}</h1>
<div class="sub">适用税种 {e('、'.join(out['tax_types']))} ｜ 地区 {e(out['region'])} ｜ 政策快照 {e(out['snapshot'])} ｜ 确定性规则生成（非大模型）</div>
<div class="cards">
  <div class="card"><b>{e(out['counts']['filings'])}</b><span>申报事项</span></div>
  <div class="card"><b>{e(out['counts']['documents'])}</b><span>资料清单</span></div>
  <div class="card"><b style="color:#c0392b">{e(out['counts']['risks_high'])}</b><span>高风险点</span></div>
  <div class="card"><b style="color:#a97013">{e(out['counts']['risks_mid'])}</b><span>中风险点</span></div>
</div>
<h2>一、申报时间线</h2>
<table><tr><th>税种</th><th style="width:190px">时间</th><th>事项</th><th style="width:170px">渠道</th></tr>{tl}</table>
<h2>二、资料清单</h2>
<ul>{docs}</ul>
<h2>三、风险点（按级别排序）</h2>
<table><tr><th style="width:70px">级别</th><th style="width:100px">税种</th><th>风险点</th></tr>{risks}</table>
<div class="fine"><b>本工具仅用于辅助合规自查，不构成专业税务/法律意见。</b> 依据：{e(out['basis'])}<br>{e(out['disclaimer'])}</div>
</div></body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path
