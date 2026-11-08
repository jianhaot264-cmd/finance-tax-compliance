# -*- coding: utf-8 -*-
"""orchestrator.py — 专家团多阶段编排（纯标准库）。

对齐 6-Phase SOP 的角色分工，把单次问答改造成可观测的 5 阶段流水线：

  Stage 1 分诊（钱合规 lead）      : 意图分类、角色路由、风险预判
  Stage 2 检索（retrieval）        : 四路召回 + RRF + rerank + 置信度
  Stage 3 精编（按角色）           : 本地精编答案 / 云端 LLM 上下文注入
  Stage 4 引用校验（verify）       : 引用对齐、时效过滤、阻断项拦截
  Stage 5 合规复核（赵审计）       : 风险分级、弃答裁定、B2 回查提示

所有跨阶段信息经本模块中转，输出 stage_trace 供前端展示与数据库留痕。
"""
import re

ROLE_LABEL = {
    "lead": "钱合规 · 分诊",
    "invoice-processor": "李票务 · 发票",
    "voucher-accountant": "张记账 · 核算",
    "financial-reporter": "王报表 · 报表",
    "tax-filing-specialist": "孙申报 · 税种",
    "compliance-auditor": "赵审计 · 合规",
}

# 阻断项关键词（PENDING-VERIFICATION.md v2）
BLOCKED_PATTERNS = [
    (r"前海.{0,8}15%|前海.{0,8}延续|前海.{0,6}所得税优惠",
     "前海 15% 优惠 2026 年延续状态未获官方确认，不得按 15% 测算"),
    (r"广东.{0,6}工伤保险条例|省级非税收入管理规定|地市级税费征管保障办法",
     "广东省地方细则修订状态未闭环，涉及个案须属地确认"),
]
LAW_REF_RE = re.compile(r"《([^》]{2,40})》")
ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百零\d]+条")

STAGE_ORDER = ["triage", "retrieve", "compose", "verify", "audit"]


def verify_citations(answer_text, refs, retrieved_ids, entry_map, retrieved, mode=""):
    """Stage 4：引用对齐校验 —— 防引用幻觉的核心护栏。

    mode="rule" 时跳过「未出现在检索 Top-K」提示：精编答案的 refs 是预先核定的
    法规依据，不依赖本轮检索命中，否则会把正确引用误报成风险、制造噪音。
    B1/B2 层级提示合并为一条汇总，避免同一回答重复 5-8 行。
    """
    warnings, checked = [], 0
    hit_set = set(retrieved_ids)
    invalid, weak_tier = [], []
    for rid in refs or []:
        checked += 1
        if rid not in entry_map:
            invalid.append(rid)
            warnings.append(f"引用条目 {rid} 不存在（悬空引用）")
            continue
        if rid not in hit_set and mode != "rule":
            warnings.append(f"引用条目 {rid} 未出现在本轮检索 Top-K 中，可能未经上下文支撑")
        e = entry_map[rid]
        st = e.get("status") or e.get("status_norm") or ""
        if st == "已废止":
            warnings.append(f"引用条目 {rid} 已废止，不得作为现行依据")
        elif st == "草案阶段":
            warnings.append(f"引用条目 {rid} 仍为草案，不得表述为现行规定")
        elif st == "汇编·动态":
            warnings.append(f"引用条目 {rid} 为汇编型，不得据此判断时效性")
        if e.get("tier") in ("B1", "B2"):
            weak_tier.append(rid)
    if weak_tier:
        warnings.append(f"引用条目中有 {len(weak_tier)} 条属 B1/B2 参考层（{('、'.join(weak_tier[:3]))}"
                        f"{' 等' if len(weak_tier) > 3 else ''}），数字/文号请回查官方原文")

    text = str(answer_text or "")
    laws = LAW_REF_RE.findall(text)
    articles = ARTICLE_RE.findall(text)
    for pat, msg in BLOCKED_PATTERNS:
        if re.search(pat, text) and not re.search(r"未获官方确认|未确认|不得按|须属地确认|未闭环", text):
            warnings.append(f"触及阻断项但未提示限制：{msg}")

    # 去重保序
    warnings = list(dict.fromkeys(warnings))
    return {
        "checked": checked,
        "invalid_refs": invalid,
        "law_refs": len(laws),
        "article_refs": len(articles),
        "warnings": warnings,
        "ok": not invalid and not any("不得" in w or "悬空" in w for w in warnings),
        "retrieved_ids": retrieved_ids[:10],
    }


def audit_answer(q, risk, abstain, confidence, verify_result, role):
    """Stage 5：赵审计合规复核 —— 必须给出明确裁定，不回避。"""
    findings = []
    if risk == "high":
        findings.append("高风险事项（虚开/偷税/骗税/重大补税）：必须转介执业税务师或律师")
    if abstain:
        findings.append("检索置信度不足：应明确回答「知识库暂无收录」，不得猜测补全")
    if confidence and confidence < 0.5:
        findings.append(f"置信度 {confidence} 偏低：结论须标注「建议回查官方原文」")
    if verify_result.get("warnings"):
        findings.append(f"引用校验发现 {len(verify_result['warnings'])} 项提示，须在回答中披露")

    if not findings:
        verdict = "通过"
    elif risk == "high" or abstain or verify_result.get("invalid_refs"):
        verdict = "需人工复核"
    else:
        verdict = "通过（附提示）"
    return {
        "auditor": ROLE_LABEL["compliance-auditor"],
        "verdict": verdict,
        "findings": findings,
        "risk": risk,
        "role": ROLE_LABEL.get(role, role),
    }


def run_pipeline(q, retrieval_result, answer_text, refs, role, risk, entry_map):
    """把各阶段产出串成一条可回放的 trace。"""
    hits = retrieval_result.get("hits", [])
    retrieved_ids = [h["id"] for h in hits]

    t1 = {
        "stage": "triage", "order": 1, "owner": ROLE_LABEL["lead"],
        "role": role, "role_label": ROLE_LABEL.get(role, role),
        "risk": risk, "query": q,
    }
    t2 = {
        "stage": "retrieve", "order": 2, "owner": "检索引擎",
        "mode": retrieval_result.get("mode", "v5"),
        "confidence": retrieval_result.get("confidence", 0.0),
        "abstain": retrieval_result.get("abstain", False),
        "top_ids": retrieved_ids[:5],
        "internal": retrieval_result.get("trace", []),
    }
    t3 = {
        "stage": "compose", "order": 3,
        "owner": ROLE_LABEL.get(role, "精编答案库"),
        "mode": answer_text.get("mode") if isinstance(answer_text, dict) else "local",
        "ref_count": len(refs or []),
    }
    ver = verify_citations(
        answer_text.get("text", "") if isinstance(answer_text, dict) else str(answer_text or ""),
        refs, retrieved_ids, entry_map, hits,
        mode=answer_text.get("mode", "") if isinstance(answer_text, dict) else "")
    t4 = {"stage": "verify", "order": 4, "owner": "引用校验器", **ver}
    t5 = {"stage": "audit", "order": 5,
          **audit_answer(q, risk, retrieval_result.get("abstain", False),
                         retrieval_result.get("confidence", 0.0), ver, role)}
    return {
        "stages": [t1, t2, t3, t4, t5],
        "verification": ver,
        "audit": t5,
        "abstain": retrieval_result.get("abstain", False),
        "confidence": retrieval_result.get("confidence", 0.0),
    }


def stage_system_prompt(base_prompt, role, stage_hint=""):
    """按角色分阶段构造 system prompt（供 /api/llm-context 使用）。"""
    role_focus = {
        "invoice-processor": "你负责发票相关问题：优先依据发票管理办法、数电票公告与裁量基准，关注票面合规与真伪。",
        "voucher-accountant": "你负责核算相关问题：优先依据会计法、小企业会计准则、档案管理与账簿设置要求。",
        "financial-reporter": "你负责报表相关问题：优先依据企业会计准则与财务报告条例，关注勾稽与列报。",
        "tax-filing-specialist": "你负责税种计算与申报：必须写清计税依据、税率/征收率、期限与优惠适用条件。",
        "compliance-auditor": "你负责合规判断：必须给出明确的合规/不合规裁定，不得回避；量化风险并给整改建议。",
        "lead": "你负责分诊与总括：先判断问题属于哪个专业域，再给出结构化结论。",
    }
    return (base_prompt + "\n\n【本轮分诊角色】" + ROLE_LABEL.get(role, role) +
            "\n【角色聚焦】" + role_focus.get(role, role_focus["lead"]) +
            "\n【阶段要求】" + (stage_hint or "按结论→依据→风险与合规提示三段式输出。"))
