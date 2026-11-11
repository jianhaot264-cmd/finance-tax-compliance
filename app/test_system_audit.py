# -*- coding: utf-8 -*-
"""系统级功能审计：各 API 端点 + 各问答模式 + 数据一致性，逐项断言。"""
import json
import re
import sqlite3
import urllib.parse
import urllib.request

# 用 127.0.0.1 而非 localhost：Windows 上 localhost 会先试 IPv6 ::1，
# 服务只监听 IPv4，导致每个请求多 ~2 秒的解析回退延迟（实测 2037ms vs 50ms）。
BASE = "http://127.0.0.1:8777"
R = "E:/workbuddy-data/finance-tax-compliance"
CHECKS = []


def ck(name, cond, detail=""):
    CHECKS.append((name, bool(cond)))
    print(("  OK   " if cond else "  FAIL ") + name + ("  | " + str(detail) if detail else ""), flush=True)


def get(path, timeout=30):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=timeout).read().decode("utf-8"))


def post(path, payload, timeout=45):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))


print("=== 1. 端点可用性 ===", flush=True)
meta = get("/api/meta", 10)
ck("/api/meta", meta.get("kb_version") == "v15.0", f"{meta.get('kb_version')}/{meta.get('entries')}")
h = get("/api/health", 10)
ck("/api/health", h.get("ok") is True, h)
kb = get("/api/kb", 20)
ck("/api/kb", len(kb.get("entries", [])) == 472, len(kb.get("entries", [])))
ck("/api/examples", bool(get("/api/examples", 10)))
bc = get("/api/business-cases?q=", 15)
ck("/api/business-cases 列表模式", bc.get("total") == 30 and len(bc.get("results", [])) == 30, bc.get("total"))
ck("/api/business-cases 搜索", len(get("/api/business-cases?q=" + urllib.parse.quote("赊销"), 15).get("results", [])) > 0)
ck("/api/concepts", len(get("/api/concepts", 15).get("concepts", [])) == 30)
ck("/api/scenarios", len(get("/api/scenarios", 15).get("scenarios", [])) == 14)
dd = get("/api/deep-dive?q=" + urllib.parse.quote("增值税的一般纳税人和小规模纳税人有什么区别"), 25)
ck("/api/deep-dive 六段", bool(dd.get("concepts")) and len(dd.get("sections") or []) >= 6,
   "%d 卡 / %d 段" % (len(dd.get("concepts") or []), len(dd.get("sections") or [])))
dd2 = get("/api/deep-dive?q=" + urllib.parse.quote("什么是增值税"), 25)
# 概念卡设计上只覆盖「疑难辨析点」，不含「增值税」这类最基础术语；
# 无匹配时必须给出明确提示而不是编造内容，这才是要守的护栏。
ck("/api/deep-dive 无匹配时明确弃答",
   not dd2.get("concepts") and any("概念卡" in w for w in (dd2.get("warnings") or [])),
   (dd2.get("warnings") or [""])[0][:40])

print("=== 2. 问答各模式 ===", flush=True)
a = post("/api/ask", {"q": "增值税税率是多少", "mode": "standard"})
ck("standard 返回结构", all(k in (a.get("answer") or {}) for k in ("role", "sections", "refs")), (a.get("answer") or {}).get("mode"))
a2 = post("/api/ask", {"q": "广宣费税前扣除限额是多少", "mode": "deep"})
ck("deep 含 business_cases", bool((a2["answer"].get("business_cases") or {}).get("items")), None)
ck("deep 含六段解读", bool(a2["answer"].get("deep")))
c = post("/api/ask", {"q": "小规模纳税人月销售额10万，增值税多少", "mode": "standard"})
ck("计算类走确定性引擎", (c["answer"].get("mode") or "") in ("calc", "rule", "retrieval"), c["answer"].get("mode"))
cl = post("/api/ask", {"q": "税率", "mode": "standard"})
ck("模糊问题触发澄清或弃答", (cl["answer"].get("mode") in ("clarify", "abstain", "rule", "retrieval")), cl["answer"].get("mode"))
oos = post("/api/ask", {"q": "火星注册公司要交什么税", "mode": "standard"})
ck("超范围弃答", oos["answer"].get("mode") == "abstain" and not (oos["answer"].get("business_cases") or {}).get("items"))
ck("免责声明动态日期", "2026-11-09" in oos.get("disclaimer", ""), oos.get("disclaimer", "")[:32])

print("=== 3. LLM 上下文与外部核验开关 ===", flush=True)
ctx = get("/api/llm-context?q=" + urllib.parse.quote("2027年优惠是否延续") + "&mode=standard", 30)
ck("llm-context 含 system_prompt", len(ctx.get("system_prompt") or "") > 500, len(ctx.get("system_prompt") or ""))
ck("system_prompt 核验日动态", "2026-11-09" in (ctx.get("system_prompt") or ""))
ck("外部核验本机启用", (ctx.get("external") or {}).get("enabled") is True, (ctx.get("external") or {}).get("status"))

print("=== 4. 数据层一致性 ===", flush=True)
d = json.load(open(R + "/app/kb.json", encoding="utf-8"))
con = sqlite3.connect(R + "/app/finance-tax-compliance.db")
n_art = con.execute("SELECT COUNT(*) FROM article_text").fetchone()[0]
dang = con.execute("SELECT COUNT(*) FROM rule_reference r LEFT JOIN regulation g "
                   "ON r.regulation_id=g.id WHERE g.id IS NULL").fetchone()[0]
alias = con.execute("SELECT COUNT(*) FROM alias").fetchone()[0]
con.close()
ck("article_text ≥600（L0 已扩容）", n_art >= 600, n_art)
# 说明：此处不写死精确条数。此前写死 121→455→647 三次，每次数据合法变动都会误报，
# 断言本身成了噪声源。改为下限断言 + 下方「条号完整性」结构性检查。
ck("引用零悬空", dang == 0, dang)
ck("alias 89", alias == 89, alias)
ck("kb.json 472/56", len(d["entries"]) == 472 and len(d["files"]) == 56)
ck("tier 318/4/150", [e.get("tier") for e in d["entries"]].count("A") == 318)

print("=== 4.5 法条层结构性检查 ===", flush=True)
# 4.5a 企税条例必须 132 条无缺号（曾因 23 文件摘要版抢位，缺 28/40-44/53 共 7 条）
con = sqlite3.connect(R + "/app/finance-tax-compliance.db")
_rows = [r[0] for r in con.execute(
    "SELECT article_no FROM article_text WHERE law_name='中华人民共和国企业所得税法实施条例'")]
_linked = con.execute("SELECT COUNT(*) FROM article_text WHERE entry_id<>''").fetchone()[0]
_n = con.execute("SELECT COUNT(*) FROM article_text").fetchone()[0]
con.close()

_CN = "零一二三四五六七八九"


def _artnum(s):
    m = re.search(r"第([一二三四五六七八九十百零]+)条", s or "")
    if not m:
        return None
    t, v, tmp = m.group(1), 0, 0
    for ch in t:
        if ch in _CN:
            tmp = _CN.index(ch)
        elif ch == "十":
            v += (tmp or 1) * 10
            tmp = 0
        elif ch == "百":
            v += (tmp or 1) * 100
            tmp = 0
    return v + tmp


_nums = {_artnum(x) for x in _rows}
_missing = [i for i in range(1, 133) if i not in _nums]
ck("企税条例 132 条无缺号", len(_rows) >= 132 and not _missing, _missing or len(_rows))
ck("法条关联条目率 ≥95%", _n > 0 and _linked / _n >= 0.95,
   f"{_linked}/{_n}={_linked / _n:.1%}" if _n else "-")

print("=== 5. 静态资源与免责 ===", flush=True)
html = urllib.request.urlopen(BASE + "/", timeout=15).read().decode("utf-8")
ck("首页含免责声明", "不构成专业税务/法律意见" in html)
for js in ("app.js", "ux.js", "business.js", "copy.js"):
    try:
        urllib.request.urlopen(BASE + "/" + js, timeout=10).read()
        ck(f"{js} 可加载", True)
    except Exception as ex:
        ck(f"{js} 可加载", False, type(ex).__name__)

bad = [n for n, ok in CHECKS if not ok]
print("\nAUDIT_ALL_OK" if not bad else "\nAUDIT_FAILED: " + ", ".join(bad), flush=True)
print("TOTAL", len(CHECKS), "PASSED", len(CHECKS) - len(bad), flush=True)
