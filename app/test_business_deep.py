# -*- coding: utf-8 -*-
"""test_business_deep.py — 业务事项前端能力回归（Playwright / headless Chromium）。

覆盖：
  ③ 依据名称《法规名》精确跳转到对应法源条目（不再是关键词回填）
  ② 深度解读模式渲染 answer.business_cases（3 条 × 11 字段）

用法：python test_business_deep.py   （需服务已启动在 8777）
"""
import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request
from playwright.async_api import async_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "http://localhost:8777"
Q = "广宣费税前扣除限额是多少"
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("  PASS " if cond else "  FAIL ") + name + ("  | " + str(detail) if detail else ""), flush=True)


async def main():
    url = BASE + "/api/llm-context?q=" + urllib.parse.quote(Q) + "&mode=deep"
    ctx = json.loads(urllib.request.urlopen(url, timeout=25).read().decode("utf-8"))
    bc = (ctx.get("fallback") or {}).get("business_cases") or {}
    check("后端 deep 上下文含 business_cases", bool(bc.get("items")), f"{len(bc.get('items') or [])} 条")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        # 云端 LLM 生成耗时不受控，会让「装饰何时执行」变成竞态；
        # 拦截所有非本机请求，强制走 sendViaCloud 的本地兜底分支，保证回归可复现。
        async def route_handler(route):
            u = route.request.url
            if u.startswith(BASE) or u.startswith("http://127.0.0.1:8777"):
                await route.continue_()
            else:
                await route.abort()
        await page.route("**/*", route_handler)

        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:160]))
        await page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(700)

        # ---- ③ 精确跳转 ----
        await page.click('.nav-item[data-tab="business"]')
        await page.wait_for_timeout(500)
        await page.click(".bc-item")
        await page.wait_for_timeout(250)
        links = page.locator("#bc-detail .bc-law-link")
        n = await links.count()
        check("依据名称渲染为可跳转链接", n >= 1, f"{n} 个")
        if n:
            await links.first.click()
            await page.wait_for_timeout(600)
            detail = await page.locator("#kb-detail").inner_text()
            search = await page.input_value("#kb-search")
            check("切到法规库", await page.is_visible("#view-kb"))
            check("精确命中 CAS 14 条目", "CAS 14" in detail or "收入准则" in detail, detail[:48].replace("\n", " "))
            check("未回退为关键词检索", not search.strip(), repr(search))

        # ---- ② 深度块 ----
        await page.click('.nav-item[data-tab="chat"]')
        await page.wait_for_timeout(300)
        await page.click('[data-mode="deep"]')
        await page.wait_for_timeout(200)
        await page.fill("#chat-input", Q)
        await page.locator("#chat-input").press("Enter")
        try:
            await page.wait_for_selector(".bcx-block", timeout=60000)
            items = await page.locator(".bcx-item").count()
            rows = await page.locator(".bcx-item .bcx-fields tr").count()
            check("深度模式渲染业务事项块", await page.locator(".bcx-block").count() >= 1)
            check("业务事项条目数 >= 1", items >= 1, f"{items} 条")
            check("每条 11 字段", rows == items * 11, f"{rows} 行 / {items} 条")
        except Exception as ex:
            check("深度模式渲染业务事项块", False, type(ex).__name__)
        check("全程零 JS 运行时错误", not errs, errs[:2])
        await browser.close()

    bad = [n for n, ok in RESULTS if not ok]
    print(f"\n===== 汇总: {len(RESULTS) - len(bad)}/{len(RESULTS)} 通过 =====", flush=True)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
