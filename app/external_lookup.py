# -*- coding: utf-8 -*-
"""external_lookup.py — 自适应外部核验适配器（策略 v1，纯标准库）。

对应 reports/adaptive-retrieval-reply-policy-2026-11-09.md。

设计原则（只放宽信息来源，不放宽证据标准）：
  1. 只在 config.json 的 external_lookup.enabled=true 且触发条件成立时联网；
     默认关闭，离线部署行为与未引入本模块时完全一致。
  2. 只访问白名单官方渠道；只核验「现行性 / 文号与施行到期日 / 门槛比例税率 /
     最新公告衔接」四类硬事实，不生成分录、筹划、个案裁定或税额。
  3. 检索失败（超时/不可达/无匹配）立即回落知识库，不把失败当否定证据。
  4. 外部证据只作更新 / 补充 / 冲突提示，不静默改写知识库结论。
  5. 网络层与判定层分离：should_lookup / cross_check / build_evidence_block /
     fallback_note 都是纯函数，可离线单测；lookup() 支持 fixtures 注入。

用法：
    decision = should_lookup(q, local, retrieval, hit_entries, cfg)
    result = lookup(q, decision)               # 或 lookup(q, decision, fixtures=[...])
    block = build_evidence_block(result, "2026-11-09")
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

__all__ = [
    "SOURCES", "classify_source", "should_lookup", "lookup", "fetch_official",
    "cross_check", "build_evidence_block", "fallback_note", "conflict_note",
    "log_external", "POLICY_VERSION",
]

POLICY_VERSION = "adaptive-retrieval-reply-policy-v1"

# ---------------------------------------------------------------------------
# 渠道白名单（继承 knowledge-base/SOURCES-CHANNELS.md 的 A-E 分级）
# ---------------------------------------------------------------------------
SOURCES = [
    {"id": "npc", "name": "国家法律法规数据库", "level": "A",
     "domain": "flk.npc.gov.cn", "url": "https://flk.npc.gov.cn/", "topic": "law"},
    {"id": "gov", "name": "中国政府网国务院政策文件库", "level": "A",
     "domain": "gov.cn", "url": "https://www.gov.cn/zhengce/", "topic": "law"},
    {"id": "chinatax", "name": "国家税务总局政策法规库", "level": "A",
     "domain": "fgk.chinatax.gov.cn", "url": "https://fgk.chinatax.gov.cn/zcfgk/index.html", "topic": "tax"},
    {"id": "mof_kjs", "name": "财政部会计司政策发布", "level": "A",
     "domain": "kjs.mof.gov.cn", "url": "https://kjs.mof.gov.cn/zhengcefabu/", "topic": "accounting"},
    {"id": "mof_fgk", "name": "财政部法规库", "level": "A",
     "domain": "fgk.mof.gov.cn", "url": "https://fgk.mof.gov.cn/", "topic": "accounting"},
    {"id": "mohrss", "name": "人力资源社会保障部", "level": "A",
     "domain": "mohrss.gov.cn", "url": "https://www.mohrss.gov.cn/", "topic": "social"},
    {"id": "gd_gov", "name": "广东省人民政府", "level": "A",
     "domain": "gd.gov.cn", "url": "https://www.gd.gov.cn/", "topic": "local"},
    {"id": "gd_tax", "name": "国家税务总局广东省税务局", "level": "A",
     "domain": "guangdong.chinatax.gov.cn", "url": "https://guangdong.chinatax.gov.cn/", "topic": "local"},
]
# B 级（官方解读）仅作理解与交叉核对，不单独作结论依据
B_DOMAINS = ("chinatax.gov.cn", "mof.gov.cn", "ctaxnews.net.cn")
# C 级执行口径仅作参考；D 级商业库只用于定位；E 级禁用
C_DOMAINS = ("12366.chinatax.gov.cn",)
D_DOMAINS = ("pkulaw.com", "lawinfochina.com", "chineselaw.com", "wkinfo.com.cn")

_CACHE: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# 触发 / 不触发判定（策略 §1）
# ---------------------------------------------------------------------------
NEVER_MODE = {"calc", "rule", "clarify"}
NEVER_RE = re.compile(
    r"火星|月球|外太空|外星|虚拟国家|不存在的国家|公海|南极洲|逐一|逐条列出|穷举|"
    r"不给.{0,8}数据|无任何.{0,8}数据|只按知识库|只依据知识库|不要联网|不要检索|离线|不检索")
TIME_RE = re.compile(
    r"最新|现行|目前|今年|刚发布|新发布|是否延续|还有效|到期|废止|修订|新规|施行|生效|"
    r"过渡|衔接|之后|2026|2027|2028|取消了吗|改了吗")
CONFLICT_RE = re.compile(r"不是已经|听说|改成|取消了|不是取消|变了|不一致|冲突|到底听谁的|以哪个为准")
COVERAGE_RE = re.compile(
    r"各省|地方配套|核定征收|逐国|协定税率|差额征税|全部公告|地市|属地|省级非税|未收录")
PENDING_RE = re.compile(r"待核验|凭既有知识|文号待|待复核|以官方原文为准")
WEAK_STATUS = {"草案阶段", "修订中", "已废止", "汇编·动态"}
HARD_FACT_HINT = ("现行性 / 文号与施行到期日 / 门槛比例税率 / 最新公告衔接")


def classify_source(url: str) -> str:
    """返回渠道级别 A/B/C/D/E；非白名单一律 E（不得进入结论）。"""
    host = (urlparse(str(url or "")).hostname or "").lower()
    if not host:
        return "E"
    for s in SOURCES:
        d = s["domain"]
        # gov.cn 是顶级后缀，不能用 endswith(".gov.cn") 泛匹配，
        # 否则会把 chinatax.gov.cn / 12366 等 B、C 级渠道误判为 A 级。
        if d == "gov.cn":
            if host in ("gov.cn", "www.gov.cn"):
                return "A"
            continue
        if host == d or host.endswith("." + d):
            return "A"
    # C 级（12366 等执行口径）先于 B 级判定，避免被 *.chinatax.gov.cn 抢先归为 B
    for d in C_DOMAINS:
        if host == d or host.endswith("." + d):
            return "C"
    for d in B_DOMAINS:
        if host == d or host.endswith("." + d):
            return "B"
    for d in D_DOMAINS:
        if host == d or host.endswith("." + d):
            return "D"
    return "E"


def _parse_day(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def should_lookup(q, local, retrieval, hit_entries, cfg, today=None):
    """按策略 §1 判定是否允许自主检索；返回 need / signals / reason。

    q            用户问题
    local        ask_local() 的结果（用 mode / risk 判定不触发）
    retrieval    Retriever.retrieve() 的结果（abstain / confidence / hits）
    hit_entries  本轮命中的知识库条目对象列表
    cfg          config.json 的 external_lookup 段
    today        可注入日期，便于离线单测
    """
    today = today or date.today()
    q = str(q or "")
    signals: list[str] = []

    if not (cfg or {}).get("enabled", False):
        return {"need": False, "signals": [], "reason": "开关关闭（默认离线模式）"}
    mode = (local or {}).get("mode", "")
    if mode in NEVER_MODE:
        return {"need": False, "signals": [], "reason": f"不触发：{mode} 类问题直接走既有链路"}
    if NEVER_RE.search(q):
        return {"need": False, "signals": [], "reason": "不触发：超范围/穷举/用户要求离线"}
    if (local or {}).get("risk") == "high":
        return {"need": False, "signals": [], "reason": "不触发：高风险事项仍强制转介"}

    # --- 时效信号 TIME ---
    if TIME_RE.search(q):
        signals.append("TIME:问句含时效词")
    statuses = {(e.get("status") or e.get("status_norm") or "") for e in (hit_entries or [])}
    if statuses & WEAK_STATUS:
        signals.append("TIME:命中草案/修订中/已废止/汇编动态条目")
    for e in hit_entries or []:
        exp = _parse_day(e.get("expiry_date"))
        if exp and today <= exp <= today + timedelta(days=90):
            signals.append("TIME:命中条目 90 天内到期")
            break
    for e in hit_entries or []:
        ver = _parse_day(e.get("verified_at"))
        if ver and (today - ver).days > 30:
            signals.append("TIME:条目核验超过 30 天")
            break

    # --- 覆盖信号 COVERAGE ---
    if (retrieval or {}).get("abstain"):
        signals.append("COVERAGE:主检索弃答")
    if float((retrieval or {}).get("confidence") or 0) < 0.45:
        signals.append("COVERAGE:置信度低于阈值")
    if any((e.get("tier") in ("B1", "B2")) for e in (hit_entries or [])):
        signals.append("COVERAGE:命中 B1/B2 参考层")
    blob = " ".join(json.dumps(e.get("fields", {}), ensure_ascii=False) for e in (hit_entries or []))
    if PENDING_RE.search(blob):
        signals.append("COVERAGE:条目含待核验/以官方原文为准")
    if COVERAGE_RE.search(q):
        signals.append("COVERAGE:问题落在知识库已明示未覆盖清单")
    if not hit_entries:
        signals.append("COVERAGE:本轮无知识库命中")

    # --- 冲突信号 CONFLICT ---
    if CONFLICT_RE.search(q):
        signals.append("CONFLICT:用户提出与知识库不同的说法")
    if "已废止" in statuses and "现行有效" in statuses:
        signals.append("CONFLICT:命中条目同时存在已废止与现行有效")

    signals = list(dict.fromkeys(signals))
    return {
        "need": bool(signals),
        "signals": signals,
        "reason": "；".join(signals) if signals else "无触发信号，直接走知识库",
    }


# ---------------------------------------------------------------------------
# 网络层（可失败、可缓存、可注入 fixture）
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>|<[^>]+>", re.S | re.I)
_WS_RE = re.compile(r"\s+")


def _html_to_text(raw: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", raw or "")).strip()


def fetch_official(url: str, timeout: float = 3.0, retries: int = 2):
    """抓取白名单官方页面；任何失败都返回 ok=False，由调用方兜底。"""
    if classify_source(url) not in ("A", "B"):
        return {"ok": False, "url": url, "error": "非白名单来源，已拒绝"}
    key = f"{url}|{date.today().isoformat()}"
    if key in _CACHE:
        return dict(_CACHE[key])
    last_err = ""
    for _ in range(max(1, min(retries, 2)) + 1):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 (finance-tax-compliance/1.0)"})
            with urlopen(req, timeout=timeout) as resp:
                body = resp.read(300000)
                for enc in ("utf-8", "gb18030"):
                    try:
                        text = body.decode(enc)
                        break
                    except UnicodeDecodeError:
                        text = body.decode("utf-8", errors="replace")
                out = {"ok": True, "url": url, "status": resp.status,
                       "text": _html_to_text(text),
                       "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                _CACHE[key] = out
                return out
        except (HTTPError, URLError, TimeoutError, OSError) as ex:
            last_err = f"{type(ex).__name__}: {str(ex)[:80]}"
        except Exception as ex:  # 兜底：绝不因抓取异常影响主链路
            last_err = f"{type(ex).__name__}: {str(ex)[:80]}"
    out = {"ok": False, "url": url, "error": last_err or "unknown",
           "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    _CACHE[key] = out
    return out


def _pick_sources(q, limit=2):
    """按问题主题优先选渠道；最多 2 个，控制时延与噪声。"""
    q = str(q or "")
    if re.search(r"准则|会计|财务|报表|CAS|解释第", q):
        order = ["mof_kjs", "mof_fgk", "gov", "chinatax"]
    elif re.search(r"广东|南沙|前海|横琴|大湾区|粤", q):
        order = ["gd_tax", "gd_gov", "chinatax", "gov"]
    elif re.search(r"社保|公积金|工资|个税|劳动", q):
        order = ["mohrss", "gov", "chinatax", "mof_fgk"]
    else:
        order = ["chinatax", "gov", "npc", "mof_fgk"]
    by_id = {s["id"]: s for s in SOURCES}
    return [by_id[i] for i in order if i in by_id][:limit]


def _keywords(q):
    """从问句抽取用于页面比对的中文词（>=2 字），不含停用词。"""
    stops = {"什么", "怎么", "是否", "可以", "需要", "请问", "一下", "关于", "规定", "标准",
             "条件", "时间", "哪些", "如何", "应该", "最新", "目前", "现行"}
    return [w for w in re.findall(r"[\u4e00-\u9fff]{2,8}", str(q or "")) if w not in stops][:8]


def lookup(q, decision, fixtures=None, timeout=3.0, retries=2):
    """执行外部核验。fixtures 用于离线单测/回放，跳过网络。

    返回 status = hit / miss / failed，evidence 列表每项含
    source / level / url / excerpt / fetched_at / note。
    """
    if not (decision or {}).get("need"):
        return {"status": "skipped", "evidence": [], "tried": [], "note": decision.get("reason", "")}

    evidence, tried, errors = [], [], []
    if fixtures is not None:
        for f in fixtures:
            ev = dict(f)
            ev.setdefault("level", classify_source(ev.get("url", "")))
            ev.setdefault("fetched_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            evidence.append(ev)
            tried.append(ev.get("source", ev.get("url", "")))
    else:
        kws = _keywords(q)
        for s in _pick_sources(q):
            tried.append(s["name"])
            r = fetch_official(s["url"], timeout=timeout, retries=retries)
            if not r.get("ok"):
                errors.append(f"{s['name']}:{r.get('error', '')}")
                continue
            text = r.get("text", "")
            matched = [k for k in kws if k in text]
            if not matched:
                continue
            # 只截取命中词附近的短摘录，避免把整页塞进上下文
            pos = text.find(matched[0])
            excerpt = text[max(0, pos - 60): pos + 180]
            evidence.append({
                "source": s["name"], "level": s["level"], "url": s["url"],
                "excerpt": excerpt, "matched": matched[:4],
                "fetched_at": r.get("fetched_at", ""),
                "note": "官方栏目页命中；仅作更新/补充线索，具体条款须回查原文",
            })

    cross = cross_check(evidence)
    if not evidence and errors:
        status, note = "failed", "；".join(errors[:2])
    elif not evidence:
        status, note = "miss", "白名单渠道未匹配到与问题相关的可核验内容"
    else:
        status = "hit"
        note = ("双源一致，可作补充依据" if cross["dual"]
                else "单源命中，仅作线索，不得作为确定结论或申报依据")
    return {"status": status, "evidence": evidence, "tried": tried,
            "errors": errors, "cross": cross, "note": note}


def cross_check(evidence):
    """双源交叉：>=2 个独立官方域名且均为 A 级才算「双源一致」。"""
    domains, levels, dual_items = set(), set(), []
    for e in evidence or []:
        host = (urlparse(e.get("url", "")).hostname or "").lower()
        lvl = e.get("level") or classify_source(e.get("url", ""))
        levels.add(lvl)
        if lvl == "A":
            domains.add(host)
            dual_items.append(e)
    return {"dual": len(domains) >= 2, "domains": sorted(domains),
            "levels": sorted(levels), "a_level_count": len(dual_items)}


# ---------------------------------------------------------------------------
# 上下文组装与兜底话术（策略 §2.3 / §4）
# ---------------------------------------------------------------------------
def build_evidence_block(result, snapshot=""):
    """生成注入 LLM 上下文的 [外部核验] 区块。"""
    ev = result.get("evidence") or []
    if not ev:
        return ""
    cross = result.get("cross") or cross_check(ev)
    tag = "[外部核验·双源]" if cross.get("dual") else "[外部核验·单源]"
    lines = [f"【外部核验 · 可选补充】{tag}（知识库快照 {snapshot}；核验时间见各条）"]
    for e in ev[:2]:
        lines.append(f"- 来源：{e.get('source','')}（{e.get('level','')} 级）｜{e.get('url','')}｜"
                     f"核验 {e.get('fetched_at','')}")
        lines.append(f"  摘录：{str(e.get('excerpt',''))[:220]}")
    lines.append("说明：以上仅作更新 / 补充 / 冲突提示，不改变知识库结论；不得据此生成分录、筹划、"
                 "个案裁定或税额。若与上文知识库口径不一致，须并列展示两者并提示「回查官方原文」，"
                 "不得静默改写知识库。")
    if not cross.get("dual"):
        lines.append("限制：单源结果不得作为确定结论或申报依据，须标 [外部核验·单源]。")
    return "\n".join(lines)


def fallback_note(snapshot="", result=None):
    """检索失败 / 无匹配时的保守兜底（策略 §4.2）。"""
    reason = (result or {}).get("note", "") or "官方渠道未返回可核验内容"
    return (
        f"【外部核验结果】本次未能通过官方渠道核验其现行性（{reason}）。"
        f"请回落到知识库快照（{snapshot}）的结论并如实提示「法规立改废释频繁，以官方发布原文为准」；"
        "不得把检索失败当作「该规定不存在 / 已废止」的否定证据，不得猜测补全。"
        "涉及申报或对外依据时建议咨询 12366 或主管税务机关。"
    )


def conflict_note(kb_text, external_text, snapshot=""):
    """信息冲突时并列留痕（策略 §4.3）。"""
    return (f"【版本/口径冲突提示】（知识库快照 {snapshot}）"
            f"知识库口径：{str(kb_text)[:160]}；外部核验口径：{str(external_text)[:160]}。"
            "两者时点或效力层级可能不同，本次不改写知识库结论；请按上位法优先、后法优于前法、"
            "特别法优于一般法判断，并回查官方原文。已写入 change_log / 待核验清单。")


def log_external(db_path, q, decision, result):
    """把检索动作落到 external_lookup_log（失败静默，不影响问答）。"""
    try:
        con = sqlite3.connect(db_path)
        con.execute("""INSERT INTO external_lookup_log
            (ts,q,need,signals,status,sources,evidence_count,note) VALUES (?,?,?,?,?,?,?,?)""",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(q)[:300],
             1 if decision.get("need") else 0,
             json.dumps(decision.get("signals", []), ensure_ascii=False),
             result.get("status", ""),
             json.dumps(result.get("tried", []), ensure_ascii=False),
             len(result.get("evidence") or []), str(result.get("note", ""))[:300]))
        con.commit()
        con.close()
    except Exception:
        pass
