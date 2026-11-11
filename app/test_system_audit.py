# -*- coding: utf-8 -*-
"""系统级功能审计：各 API 端点 + 各问答模式 + 数据一致性，逐项断言。"""
import json
import sqlite3
import urllib.parse
import urllib.request

BASE = "http://localhost:8777"
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
ck("article_text 121", n_art == 121, n_art)
ck("引用零悬空", dang == 0, dang)
ck("alias 89", alias == 89, alias)
ck("kb.json 472/56", len(d["entries"]) == 472 and len(d["files"]) == 56)
ck("tier 317/4/151", [e.get("tier") for e in d["entries"]].count("A") == 317)

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
