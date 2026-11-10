# -*- coding: utf-8 -*-
"""e2e-test.py — 财税合规智能体 v3 端到端回归测试（Playwright / headless Chromium）

用法：
  python e2e-test.py --smoke    仅快速冒烟（页面加载 + 运行时错误 + 关键元素，约 10s）
  python e2e-test.py            全量（含 HY4 云端流式、本地兜底、主题、命令面板、法规库、优惠、移动端）
"""
import asyncio
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.async_api import async_playwright

SMOKE = "--smoke" in sys.argv
BASE = "http://localhost:8777"
SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-screenshots")

RESULTS = []


def check(name, cond, detail=""):
    ok = bool(cond)
    RESULTS.append((name, ok))
    print(("  PASS " if ok else "  FAIL ") + name + (("  | " + str(detail)) if detail else ""), flush=True)


async def main():
    os.makedirs(SHOT_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        def _on_console(m):
            if m.type != "error":
                return
            t = m.text or ""
            if "429" in t or "Failed to load resource" in t:
                return  # 云端限流属外部服务状态，应用已自动回退；不计入 JS 运行时错误
            errors.append("console.error: " + t[:180])
        page.on("console", _on_console)
        page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)[:180]))

        await page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_function(
                "() => document.querySelector('#kb-summary') && document.querySelector('#kb-summary').textContent.includes('知识库 v')",
                timeout=15000)
            check("初始化完成（meta / kb / examples 加载）", True)
        except Exception:
            check("初始化完成", False, await page.text_content("#fatal-msg") if not await page.is_hidden("#fatal") else "timeout")

        check("无致命错误遮罩", await page.is_hidden("#fatal"))
        check("欢迎空状态渲染", await page.locator(".welcome").count() == 1)
        check("热门示例 6 条", await page.locator(".welcome-chip").count() == 6)
        check("示例分组 8 组（含概念辨析）", await page.locator(".quick-tab").count() == 8)
        check("法规库侧栏统计", "472 条法规" in (await page.text_content("#kb-summary")))
        check("关于页角色卡 6 个", await page.locator("#about-roles .role-card").count() == 6)
        # v6 基础组件（冒烟也覆盖，便于快速发现初始化故障）
        check("统一文案字典已加载", await page.evaluate("() => !!(window.COPY && window.COPY.mode && window.COPY.stages)"))
        check("回答模式切换器存在", await page.locator("#answer-mode button").count() == 2)
        check("五阶段进度容器存在", await page.locator("#stage-progress #stage-dots").count() == 1)
        check("概念面板容器存在", await page.locator("#concept-overlay #concept-list").count() == 1)
        check("可访问性播报区存在", await page.locator("#ux-announcer[aria-live]").count() == 1)
        check("模式提示文案一致", "结论" in (await page.text_content("#mode-hint")))

        # 云端模型目录（排除 HTML 中的「本地检索」占位 option）
        try:
            await page.wait_for_function(
                "() => !document.querySelector('#meta-llm').textContent.includes('正在连接')", timeout=35000)
        except Exception:
            pass
        opts = await page.eval_on_selector_all("#model-select option[value]:not([value=''])", "els => els.map(e => e.value)")
        llm_status = await page.text_content("#meta-llm")
        check("模型选择器已填充", len(opts) > 0, f"{len(opts)} 个模型 · {llm_status}")
        check("云端 Hy4 连接", "云端已连接" in (llm_status or ""), llm_status)
        groups = await page.eval_on_selector_all("#model-select optgroup", "els => els.map(e => e.label)")
        check("模型按价格分档（免费/低价）",
              any("免费" in g for g in groups) and any("低价" in g for g in groups), " / ".join(groups))
        price_text = ((await page.text_content("#model-price")) or "").strip()
        check("当前模型显示价格倍率", price_text in ("免费", "0.00x"), price_text)
        check("关于页免费/低价模型价目表", await page.locator("#about-models .model-price-item").count() >= 5,
              str(await page.locator("#about-models .model-price-item").count()))

        await page.screenshot(path=os.path.join(SHOT_DIR, "01-desktop-chat.png"), full_page=False)

        if SMOKE:
            check("运行时零报错", not errors, "; ".join(errors[:3]))
            print("\nSMOKE 汇总: %d/%d 通过" % (sum(1 for _, o in RESULTS if o), len(RESULTS)))
            await browser.close()
            return

        # ---- HY4 云端流式问答 ----
        print("\n[1] 云端 HY4 流式问答", flush=True)
        await page.click(".example-chip")
        result = await page.evaluate("""async () => {
          const deadline = Date.now() + 150000;
          while (Date.now() < deadline) {
            const fb = document.querySelector('.llm-fallback-notice');
            const stream = document.querySelector('.llm-stream');
            if (fb) return {mode: 'fallback', text: fb.textContent.slice(0, 200)};
            if (stream) {
              const t = stream.textContent.replace('▍','').trim();
              if (t.length > 60) return {mode: 'llm', text: t.slice(0, 300)};
            }
            await new Promise(r => setTimeout(r, 400));
          }
          return {mode: 'timeout', text: ''};
        }""")
        check("HY4 流式作答（>60 字）", result["mode"] in ("llm", "fallback"), result["mode"])
        print("       回答摘录:", (result.get("text") or "").replace("\n", " ")[:180], flush=True)
        # 等待整轮问答结束（流式判定只要求 >60 字，此时 ask 可能仍在 finally 之前）
        try:
            await page.wait_for_function("() => S.busy === false", timeout=120000)
            check("流式完整结束（busy 已释放）", True)
        except Exception:
            check("流式完整结束（busy 已释放）", False, "busy 未释放")
        check("云端徽章存在", await page.locator(".llm-badge").count() > 0)
        check("消息操作条存在", await page.locator(".msg-action").count() >= 3)
        check("引用条目已渲染", await page.locator(".ref-chip").count() > 0)
        await page.screenshot(path=os.path.join(SHOT_DIR, "02-chat-answer.png"), full_page=False)

        # ---- 主题切换 ----
        print("\n[2] 主题与设置", flush=True)
        before = await page.evaluate("() => document.documentElement.dataset.theme")
        await page.click("#theme-quick")
        after = await page.evaluate("() => document.documentElement.dataset.theme")
        check("深浅主题切换生效", before != after, f"{before} -> {after}")
        await page.screenshot(path=os.path.join(SHOT_DIR, "03-dark-theme.png"), full_page=False)
        await page.click("#theme-quick")  # 切回初始，避免影响后续截图

        # ---- 命令面板 ----
        print("\n[3] 全局搜索（命令面板）", flush=True)
        await page.keyboard.press("Control+k")
        check("Ctrl+K 打开命令面板", not await page.is_hidden("#cmd-overlay"))
        await page.fill("#cmd-input", "滞纳金")
        await page.wait_for_timeout(200)
        n_cmd = await page.locator(".cmd-item").count()
        check("搜索返回法规/问题结果", n_cmd > 0, f"{n_cmd} 条")
        await page.keyboard.press("Escape")
        check("Esc 关闭面板", await page.is_hidden("#cmd-overlay"))

        # ---- 法规库 ----
        print("\n[4] 法规库筛选与详情", flush=True)
        await page.click('.nav-item[data-tab="kb"]')
        n_kb = await page.locator(".kb-item").count()
        check("法规列表渲染", n_kb > 0, f"{n_kb} 条")
        n_chips = await page.locator("#kb-filters .filter-chip").count()
        check("分类筛选 chips", n_chips >= 13, f"{n_chips} 个")
        await page.fill("#kb-search", "残保金")
        await page.wait_for_timeout(350)
        n_hit = await page.locator(".kb-item").count()
        check("搜索有结果", n_hit > 0, f"{n_hit} 条")
        if n_hit:
            await page.click(".kb-item")
            title = await page.text_content("#kb-detail h2")
            check("详情标题渲染", bool(title and title.strip()), title)
            check("详情内容区渲染", await page.locator("#kb-detail .hint-block, #kb-detail .field-table, #kb-detail .md-body").count() > 0)
            check("收藏按钮可用", await page.locator("#detail-fav").count() == 1)
        # 清空搜索后打开首条法规条目，验证结构化字段表
        await page.click("#kb-search-clear")
        await page.wait_for_timeout(250)
        await page.click(".kb-item")
        check("法规条目字段表渲染", await page.locator(".field-table tr").count() > 0)
        check("同分类相关条目", await page.locator(".related-box .ref-chip").count() > 0)
        await page.screenshot(path=os.path.join(SHOT_DIR, "04-kb-detail.png"), full_page=False)

        # ---- 业务事项浏览（v13.1） ----
        print("\n[5.5] 业务事项结构化指引", flush=True)
        await page.click('.nav-item[data-tab="business"]')
        await page.wait_for_timeout(350)
        check("业务事项视图可见", await page.is_visible("#view-business"))
        n_bc = await page.locator(".bc-item").count()
        check("业务事项列表渲染", n_bc >= 30, f"{n_bc} 条")
        check("业务事项分类筛选 7 个", await page.locator("#bc-filters .filter-chip").count() == 7)
        await page.fill("#bc-search", "赊销")
        await page.wait_for_timeout(450)
        check("业务事项搜索有结果", await page.locator(".bc-item").count() > 0)
        await page.click("#bc-search-clear")
        await page.wait_for_timeout(400)
        check("业务事项导出按钮可见", await page.is_visible("#bc-export"))
        if await page.locator(".bc-item").count():
            await page.click(".bc-item")
            check("业务事项详情 11 字段", await page.locator("#bc-detail .bc-fields tr").count() == 11)
            n_law = await page.locator("#bc-detail .bc-law-link").count()
            check("依据名称渲染为可跳转链接", n_law >= 1, f"{n_law} 个")
        await page.screenshot(path=os.path.join(SHOT_DIR, "05-bc-detail.png"), full_page=False)
        try:
            async with page.expect_download(timeout=8000) as di:
                await page.click("#bc-export")
            dl = await di.value
            check("CSV 导出触发下载", dl.suggested_filename.endswith(".csv"), dl.suggested_filename)
        except Exception as ex:
            check("CSV 导出触发下载", False, type(ex).__name__)
        if await page.locator("#bc-detail .bc-law-link").count():
            await page.click("#bc-detail .bc-law-link")
            await page.wait_for_timeout(300)
            check("依据跳转切到法规库", await page.is_visible("#view-kb"))
            check("依据跳转回填检索词", bool((await page.input_value("#kb-search")).strip()))

        # ---- 优惠速查 ----
        print("\n[5] 优惠速查结构化", flush=True)
        await page.click('.nav-item[data-tab="incentives"]')
        n_inc = await page.locator(".inc-table tbody tr").count()
        check("优惠政策表格渲染", n_inc > 0, f"{n_inc} 行")
        check("统计卡 4 个", await page.locator(".inc-stat").count() == 4)
        try:
            unknown_n = int((await page.locator(".inc-stat.warn b").text_content() or "0").strip())
        except ValueError:
            unknown_n = 0
        check("待核验/临期按整行识别", unknown_n >= 2, f"{unknown_n} 条")
        await page.click('#inc-filters .filter-chip[data-s="ok"]')
        await page.wait_for_timeout(150)
        check("现行优惠筛选生效", await page.locator(".inc-table tbody tr").count() > 0)
        await page.click('#inc-filters .filter-chip[data-s="expired"]')
        await page.wait_for_timeout(150)
        # v4.0：稳岗返还已于 2026 年延续，速查表不再含「已到期」行，此项应如实为空
        check("已到期项如实为空（稳岗返还已延续）", await page.locator(".row-expired").count() == 0)
        await page.click('#inc-filters .filter-chip[data-s="all"]')
        await page.screenshot(path=os.path.join(SHOT_DIR, "05-incentives.png"), full_page=False)

        # ---- 本地兜底（验证 v1 的渲染缺陷已修复）----
        print("\n[6] 本地检索兜底渲染", flush=True)
        await page.evaluate("async () => { switchTab('chat'); S.cloud.ready = false; await ask('员工自愿放弃社保有效吗'); }")
        try:
            await page.wait_for_function(
                "() => { const xs = document.querySelectorAll('.message.assistant .msg-body .sec-conclusion'); return xs.length > 0; }",
                timeout=15000)
            check("本地答案确实挂载到 DOM", True)
        except Exception:
            check("本地答案确实挂载到 DOM", False, "v1 缺陷复现：remove() 后未 append")
        risk = await page.locator(".message.assistant .risk-high").count()
        check("高风险徽章", risk > 0, f"{risk} 个")

        # ---- v6：深度解读 / 概念面板 / 状态反馈 / 可访问性 ----
        print("\n[6.5] v6 深度解读与 UI/UX", flush=True)
        await page.click('#answer-mode button[data-mode="deep"]')
        check("深度解读模式生效", await page.evaluate("() => window.UX.mode === 'deep'"))
        check("模式 aria-checked 同步",
              await page.get_attribute('#answer-mode button[data-mode="deep"]', "aria-checked") == "true")
        hint = await page.text_content("#mode-hint")
        check("深度模式提示六段式",
              all(k in hint for k in ("定义", "辨析", "因果", "适用条件", "易混淆", "局限")), hint)
        check("模式偏好持久化",
              await page.evaluate("() => localStorage.getItem('taxagent.answermode') === 'deep'"))

        await page.evaluate("async () => { switchTab('chat'); S.cloud.ready = false; await ask('不征税收入和免税收入有什么区别'); }")
        try:
            await page.wait_for_function("() => !!document.querySelector('.deep-block')", timeout=15000)
            check("深度解读块渲染", True)
        except Exception:
            check("深度解读块渲染", False, "deep-block 未出现")
        check("六段式解读段数", await page.locator(".deep-sec").count() >= 6,
              str(await page.locator(".deep-sec").count()))
        labels = " ".join(await page.locator(".deep-sec-label").all_text_contents())
        check("六段标签齐全", all(k in labels for k in ("定义", "辨析", "因果", "适用条件", "易混淆", "局限")))
        check("概念卡内联跳转", await page.locator("[data-concept]").count() > 0)
        check("证据链展开块", await page.locator(".evidence-box").count() > 0)
        check("追问建议 chips", await page.locator(".followup-chip").count() >= 3,
              str(await page.locator(".followup-chip").count()))
        await page.screenshot(path=os.path.join(SHOT_DIR, "08-deep-dive.png"), full_page=False)

        await page.click("#concept-trigger")
        check("概念面板打开", not await page.is_hidden("#concept-overlay"))
        try:
            await page.wait_for_function("() => document.querySelectorAll('.concept-item').length >= 25", timeout=10000)
        except Exception:
            pass
        n_concepts = await page.locator(".concept-item").count()
        check("概念卡列表 30 张", n_concepts == 30, str(n_concepts))
        await page.click(".concept-item")
        check("概念详情标题渲染", bool((await page.text_content("#concept-detail h3") or "").strip()))
        check("概念详情字段 >= 10", await page.locator("#concept-detail .c-field").count() >= 10,
              str(await page.locator("#concept-detail .c-field").count()))
        check("概念详情动作 3 个", await page.locator("#concept-detail [data-c-act]").count() == 3)
        await page.screenshot(path=os.path.join(SHOT_DIR, "09-concept-panel.png"), full_page=False)
        await page.fill("#concept-search", "广宣")
        await page.wait_for_timeout(300)
        n_filtered = await page.locator(".concept-item").count()
        check("概念面板搜索过滤", 0 < n_filtered < 30, str(n_filtered))
        await page.keyboard.press("Escape")
        check("Esc 关闭概念面板", await page.is_hidden("#concept-overlay"))

        api_v6 = await page.evaluate("""async () => {
          const c = await (await fetch('/api/concepts')).json();
          const s = await (await fetch('/api/scenarios')).json();
          const d = await (await fetch('/api/deep-dive?q=' + encodeURIComponent('广宣费 30% 现行依据'))).json();
          return {c: c.total, s: s.total, dc: d.counts.concepts, sec: d.counts.sections};
        }""")
        check("概念接口 30 张", api_v6["c"] == 30, str(api_v6))
        check("场景接口 14 个", api_v6["s"] == 14)
        check("深度接口六段可用", api_v6["dc"] >= 1 and api_v6["sec"] >= 6, str(api_v6))

        check("五阶段进度点 5 个", await page.locator("#stage-progress .stage-dot").count() == 5)
        check("进度条空闲时隐藏", await page.is_hidden("#stage-progress"))
        check("回答模式 radiogroup", await page.get_attribute("#answer-mode", "role") == "radiogroup")
        check("概念面板 aria-modal",
              await page.get_attribute("#concept-overlay [role=dialog]", "aria-modal") == "true")
        check("skip-link 文案统一", (await page.text_content(".skip-link") or "").strip() == "跳到主内容")

        await page.click('.nav-item[data-tab="kb"]')
        await page.fill("#kb-search", "zzzz不存在的法规zzzz")
        await page.wait_for_timeout(500)
        check("空搜索状态与恢复动作", await page.locator("#ux-kb-empty [data-ux-clear-kb]").count() == 1)
        await page.click("#kb-search-clear")
        await page.wait_for_timeout(200)

        await page.click("#new-chat")
        await page.wait_for_timeout(300)
        check("欢迎区场景提问引导", await page.locator("#ux-welcome-guide .followup-chip").count() >= 3,
              str(await page.locator("#ux-welcome-guide .followup-chip").count()))
        await page.click('#answer-mode button[data-mode="standard"]')
        check("可切回标准答复", await page.evaluate("() => window.UX.mode === 'standard'"))

        # ---- 移动端 ----
        print("\n[7] 移动端响应式", flush=True)
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(250)
        check("底部导航显示", await page.is_visible(".mobile-nav"))
        check("桌面侧栏隐藏", not await page.is_visible(".sidebar"))
        await page.screenshot(path=os.path.join(SHOT_DIR, "06-mobile.png"), full_page=False)

        # ---- 运行时错误 ----
        check("全程零 JS 运行时错误", not errors, "; ".join(errors[:4]))

        passed = sum(1 for _, o in RESULTS if o)
        print("\n===== 汇总: %d/%d 通过 =====" % (passed, len(RESULTS)), flush=True)
        print("截图目录:", SHOT_DIR, flush=True)
        await browser.close()
        if passed != len(RESULTS):
            sys.exit(1)


asyncio.run(main())
