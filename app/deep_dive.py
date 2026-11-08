# -*- coding: utf-8 -*-
"""deep_dive.py — v6.0 知识深度解读引擎（纯标准库，零依赖）。

职责：把 concepts.json 的概念卡、关系/边界矩阵、场景决策路径组织成
「定义 → 辨析 → 因果逻辑 → 适用条件 → 易混淆点 → 局限说明」六段式输出，
每段强制附法规条目引用；并由赵审计复核给出不确定性提示。

与检索/规则库的关系：
  - 不替代精编答案库（规则仍是最高置信结论来源）；
  - 不编造任何文号/数字，所有内容来自已核验的 concepts.json；
  - 相关概念、边界、场景按字面匹配 + 关联关系扩展，扩展结果标注来源。
"""
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
CONCEPT_FILE = os.path.join(BASE, "concepts.json")

SECTIONS = [
    ("definition", "定义", "definition"),
    ("distinction", "定义辨析", "distinctions"),
    ("causal", "因果逻辑", "causal"),
    ("conditions", "适用条件", "conditions"),
    ("confusion", "易混淆点", "confusions"),
    ("limitation", "局限说明", "limitations"),
]

# 口语 → 概念编号的引导词（只用于召回，不产生结论）
HINTS = {
    "C01": ["小规模", "500万", "500 万", "简易计税", "小规模纳税人", "征收率"],
    "C02": ["小型微利", "小微", "5%", "300万", "300 万"],
    "C03": ["划型", "中小企业", "中型企业", "微型企业", "声明函"],
    "C04": ["个体户", "个体工商户", "经营所得", "200 万"],
    "C05": ["一般纳税人", "超标", "登记", "当期 1 日"],
    "C06": ["不得抵扣", "进项", "第二十二条", "抵扣"],
    "C07": ["进项转出", "转出", "非正常损失", "用途改变"],
    "C08": ["留抵退税", "留抵", "退税", "1 亿"],
    "C09": ["加计抵减", "先进制造", "工业母机", "集成电路"],
    "C10": ["纳税义务发生时间", "先开票", "收款", "开票当日"],
    "C11": ["不征税收入", "财政性资金", "专项用途", "70号", "政府补助", "财政补贴", "补贴收入", "单独核算"],
    "C12": ["免税收入", "国债利息", "股息红利", "分红"],
    "C13": ["税前扣除凭证", "扣除凭证", "28号", "无票", "小额零星", "没有发票", "没发票",
            "发票未到", "跨年发票", "收据", "收款凭证", "税前扣除", "汇算清缴", "补开换开", "起征点"],
    "C14": ["应纳税所得额", "会计利润", "税会差异", "纳税调整", "利润总额"],
    "C15": ["职工教育经费", "2.5%", "8%", "培训费"],
    "C16": ["广宣费", "广告费", "业务宣传费", "30%", "15%", "2020 年第 43 号",
            "2025 年第 16 号", "2020年第43号", "2025年第16号", "三类行业"],
    "C17": ["业务招待费", "招待费", "5‰", "60%", "双限"],
    "C18": ["公益性捐赠", "捐赠", "12%", "结转三年"],
    "C19": ["亏损弥补", "亏损", "结转", "10年", "10 年", "弥补亏损", "境外亏损"],
    "C20": ["追补", "以前年度", "应扣未扣", "5年", "5 年", "专项申报", "跨年", "汇缴期"],
    "C21": ["专项附加扣除", "婴幼儿照护", "赡养老人", "子女教育", "7 项", "六项", "提标"],
    "C22": ["年终奖", "全年一次性奖金", "单独计税", "并入综合所得"],
    "C23": ["社保", "缴费基数", "自行申报", "30日", "30 日", "放弃社保", "承诺书", "参保"],
    "C24": ["首违不罚", "不予处罚", "初次违法", "第一次违法", "一律不罚", "可以不予", "裁量"],
    "C25": ["追征期", "滞纳金", "3年", "5年", "3 年", "5 年", "补税", "少缴", "追缴", "万分之五", "无限期"],
    "C26": ["善意取得", "异常凭证", "虚开", "协查", "进项转出", "上游", "走逃", "10 个工作日"],
    "C27": ["清税前置", "复议", "纳税争议", "先缴税", "税务处理决定书", "60 日"],
    "C28": ["核定征收", "查账", "账目混乱", "定期定额", "计税依据明显偏低"],
    "C29": ["时效性", "汇编·动态", "草案", "已废止", "现行有效", "到期"],
    "C30": ["置信度", "弃答", "证据层级", "A层", "B2", "幻觉", "低置信", "不知道"],
}


def load():
    try:
        with open(CONCEPT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"concepts": [], "relations": [], "scenarios": [],
                "confusions": [], "thresholds": [], "corrections": [], "counts": {}}


DATA = load()
BY_CODE = {c["code"]: c for c in DATA.get("concepts", [])}
BY_ID = {c["id"]: c for c in DATA.get("concepts", [])}


def _score(q, c):
    """字面召回：名称、别名提示词、定义/辨析正文，长词优先。"""
    text = q or ""
    s = 0
    name = c.get("name", "")
    if name and name in text:
        s += 12 + len(name)
    for h in HINTS.get(c.get("code", ""), []):
        if h in text:
            s += len(h) * 2
    blob = " ".join(str(c.get(k, "")) for k in
                    ("definition", "distinctions", "conditions", "confusions", "category"))
    for h in HINTS.get(c.get("code", ""), []):
        if len(h) >= 3 and h in blob and h in text:
            s += 2
    return s


def match_concepts(q, topk=3):
    scored = [(_score(q, c), c) for c in DATA.get("concepts", [])]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:topk]]


def _related(q, concepts):
    """按关联关系扩展：命中概念 → 关联概念 / 场景 / 易混淆 / 边界门槛。"""
    codes = {c["code"] for c in concepts}
    names = {c["name"] for c in concepts}
    out = {"suggestions": [], "scenarios": [], "confusions": [], "thresholds": []}
    for c in DATA.get("scenarios", []):
        sc = set(re.findall(r"C\d{2}", c.get("related_concepts", "")))
        hay = (c.get("scene", "") + c.get("name", "") + c.get("path", "") +
               c.get("must_check", "") + c.get("actors", ""))
        if sc & codes or any(n in hay for n in names):
            out["scenarios"].append({"id": c["id"], "name": c["name"],
                                     "path": c.get("steps", []), "must_check": c.get("must_check", ""),
                                     "pitfalls": c.get("pitfalls", ""),
                                     "escalate": c.get("escalate", "")})
    for cf in DATA.get("confusions", []):
        if any(code in cf.get("a", "") + cf.get("b", "") for code in codes) or \
           any(n in cf.get("a", "") + cf.get("b", "") for n in names):
            out["confusions"].append(cf)
    for th in DATA.get("thresholds", []):
        if any(code in th.get("ref_entry", "") for code in codes) or \
           (th.get("value", "") and th["value"] in q):
            out["thresholds"].append(th)
    for c in concepts:
        for rc in re.findall(r"C\d{2}", c.get("related_concepts", "")):
            if rc not in codes and rc in BY_CODE and rc not in [x["code"] for x in out["suggestions"]]:
                out["suggestions"].append({"code": rc, "name": BY_CODE[rc]["name"],
                                           "why": "与「%s」存在关联关系" % c["name"]})
    return out


def deep_payload(q, entry_map=None, topk=3):
    """生成六段式深度解读。每段附引用条目 ID（已过滤不存在的条目）。"""
    concepts = match_concepts(q, topk)
    valid = set((entry_map or {}).keys())
    sections, refs = [], []
    for c in concepts:
        # 同一张概念卡的六段共享一组依据：按段去重，避免每段重复挂相同 chip；
        # 「局限说明」若无新引用则回填 2 条，保证该段仍有可回查出处。
        shown = set()
        for key, label, field in SECTIONS:
            text = str(c.get(field, "")).strip()
            if not text:
                continue
            crefs = [r for r in c.get("entry_refs", []) if not valid or r in valid]
            fresh = [r for r in crefs if r not in shown][:3]
            if not fresh:
                # 每段至少保留 1 条可回查出处（局限说明回填 2 条），避免空段
                fresh = crefs[:2] if key == "limitation" else crefs[:1]
            shown.update(fresh)
            for r in fresh:
                if r not in refs:
                    refs.append(r)
            sections.append({
                "type": key, "label": label, "text": text,
                "concept": c["code"] + " " + c["name"], "concept_id": c["id"],
                "refs": fresh, "tier": c.get("tier", ""),
                "status": c.get("status", ""),
            })
    rel = _related(q, concepts)
    # 六段式缺段时如实说明，不编造补齐
    present = {s["type"] for s in sections}
    missing = [label for key, label, _ in SECTIONS if key not in present]
    warnings = []
    if not concepts:
        warnings.append("知识库暂无可匹配的概念卡：本轮深度解读无内容，建议改用标准问答或补充术语后重试。")
    if missing and concepts:
        warnings.append("以下解读段在已核验概念卡中无对应内容：" + "、".join(missing) + "；不作推测补全。")
    if any("关联" in c.get("name", "") for c in concepts):
        warnings.append("概念卡属解释层，不是单一法规；判断法规效力请回查「关联条目」中的法规条目。")
    return {
        "q": q, "mode": "deep", "concepts": [
            {"id": c["id"], "code": c["code"], "name": c["name"],
             "category": c.get("category", ""), "tier": c.get("tier", ""),
             "basis": c.get("basis", ""), "status": c.get("status", ""),
             "sources": c.get("source_urls", []), "verified": c.get("verified", "")}
            for c in concepts],
        "sections": sections, "refs": refs[:12],
        "suggestions": rel["suggestions"][:6], "scenarios": rel["scenarios"][:4],
        "confusions": rel["confusions"][:6], "thresholds": rel["thresholds"][:8],
        "warnings": warnings,
        "counts": {"concepts": len(concepts), "sections": len(sections),
                   "relations": len(rel["suggestions"]), "scenarios": len(rel["scenarios"])},
    }


def deep_system_prompt(base_prompt, payload):
    """深度解读模式的模型指令：六段式 + 引用约束 + 不确定即承认。"""
    if not payload or not payload.get("concepts"):
        return base_prompt + "\n\n【深度解读模式】知识库未匹配到概念卡，请如实说明无法深度解读，不得编造。"
    lines = ["\n\n【深度解读模式 · 必须遵守】",
             "用户要求深入理解，输出严格按六段式：定义 → 定义辨析 → 因果逻辑 → 适用条件 → 易混淆点 → 局限说明。",
             "每段必须：① 只依据下方知识库概念卡内容；② 写出所依据的法规名称/文号/条号（来自卡片「主要依据」与「关联条目」）；"
             "③ 卡片标注「不适用/须属地确认/以官方原文为准」的，必须原样提示限制。",
             "禁止：编造文号、数字门槛、日期；把法条原文当作现行执行口径（须检查但书与后续公告）；把解释层概念卡当作单一法规判断效力。",
             "若某段在概念卡中无内容，明确写「知识库暂无该项解读」，不得用常识补全。",
             "\n=== 本轮概念卡内容（核验日期 2026-11-07） ==="]
    for c in payload["concepts"]:
        card = BY_ID.get(c["id"], {})
        lines.append(
            f"【{c['code']} {c['name']}】（{c['status']}；层级 {c['tier']}）\n"
            f"定义：{card.get('definition','')}\n"
            f"辨析：{card.get('distinctions','')}\n"
            f"因果：{card.get('causal','')}\n"
            f"适用条件：{card.get('conditions','')}\n"
            f"边界与例外：{card.get('boundaries','')}\n"
            f"易混淆点：{card.get('confusions','')}\n"
            f"局限说明：{card.get('limitations','')}\n"
            f"主要依据：{card.get('basis','')}\n"
            f"关联条目：{card.get('related_entries','')}")
    if payload.get("confusions"):
        lines.append("\n=== 易混淆对照 ===")
        for cf in payload["confusions"][:4]:
            lines.append(f"{cf.get('a','')} vs {cf.get('b','')}：{cf.get('difference','')}；"
                         f"判断顺序：{cf.get('order','')}；答错后果：{cf.get('cost','')}")
    if payload.get("thresholds"):
        lines.append("\n=== 数字门槛（含边界） ===")
        for t in payload["thresholds"][:6]:
            lines.append(f"{t.get('value','')}｜{t.get('scope','')}｜生效 {t.get('effective','')}｜"
                         f"例外 {t.get('edge','')}")
    return base_prompt + "\n".join(lines)


def concepts_payload():
    """概念面板数据：列表 + 统计，脱去正文字段以控制体积。"""
    cs = [{
        "id": c["id"], "code": c["code"], "name": c["name"],
        "category": c.get("category", ""), "definition": c.get("definition", ""),
        "tier": c.get("tier", ""), "status": c.get("status", ""),
        "related_entries": c.get("related_entries", ""),
        "related_concepts": c.get("related_concepts", ""),
        "basis": c.get("basis", ""), "sources": c.get("source_urls", []),
    } for c in DATA.get("concepts", [])]
    return {"version": DATA.get("version", ""), "counts": DATA.get("counts", {}),
            "concepts": cs, "total": len(cs)}


def scenarios_payload():
    return {"scenarios": [
        {"id": s["id"], "name": s["name"], "scene": s.get("scene", ""),
         "actors": s.get("actors", ""), "steps": s.get("steps", []),
         "must_check": s.get("must_check", ""), "boundaries": s.get("boundaries", ""),
         "pitfalls": s.get("pitfalls", ""), "escalate": s.get("escalate", ""),
         "related_entries": s.get("related_entries", "")}
        for s in DATA.get("scenarios", [])], "total": len(DATA.get("scenarios", []))}


def concept_detail(cid):
    c = BY_ID.get(cid) or next((x for x in DATA.get("concepts", []) if x.get("code") == cid), None)
    if not c:
        return None
    out = dict(c)
    out["relations"] = [r for r in DATA.get("relations", [])
                        if r.get("from") == c["id"] or r.get("source", "").startswith(c["code"])]
    out["scenarios"] = [{"id": s["id"], "name": s["name"]} for s in DATA.get("scenarios", [])
                        if c["code"] in s.get("related_concepts", "")]
    out["confusions"] = [x for x in DATA.get("confusions", [])
                         if c["code"] in x.get("a", "") + x.get("b", "")]
    return out
