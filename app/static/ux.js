/* ==========================================================================
   ux.js — v6.0 交互增强层（依赖 app.js 的全局函数，不重写原有逻辑）
   模块：回答模式 / 五阶段状态 / 深度解读与证据链 / 概念面板 / 追问引导 /
         空·错误·异常态 / 网络状态 / 文案一致性 / 可访问性。
   ========================================================================== */
(function () {
  "use strict";
  const C = window.COPY || {};
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const toast = (m, t) => { try { window.toast(m, t || "ok"); } catch (e) { /* noop */ } };
  const CX = (o, k, d) => (o && o[k] != null ? o[k] : d);

  const UX = {
    mode: "standard",
    concepts: [], scenarios: [], conceptDetail: null,
    activeConcept: "", progressTimer: null, progressIdx: 0,
    observer: null, welcomeObserver: null,
  };
  window.UX = UX;

  /* ---------------- 回答模式 ---------------- */
  function setMode(mode, silent) {
    if (mode !== "deep" && mode !== "standard") mode = "standard";
    UX.mode = mode;
    try { localStorage.setItem("taxagent.answermode", mode); } catch (e) { /* noop */ }
    $$("#answer-mode button").forEach(b => {
      const on = b.dataset.mode === mode;
      b.classList.toggle("active", on);
      b.setAttribute("aria-checked", on ? "true" : "false");
    });
    const hint = $("#mode-hint");
    if (hint) hint.textContent = mode === "deep" ? C.mode.deepHint : C.mode.standardHint;
    const input = $("#chat-input");
    if (input) input.setAttribute("aria-label", mode === "deep" ? "输入问题（深度解读模式）" : "输入问题（标准答复模式）");
    if (!silent) toast(C.mode.switched(mode === "deep" ? C.mode.deep : C.mode.standard));
  }
  function bindMode() {
    const seg = $("#answer-mode");
    if (!seg) return;
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-mode]");
      if (b) setMode(b.dataset.mode);
    });
    let saved = "standard";
    try { saved = localStorage.getItem("taxagent.answermode") || "standard"; } catch (e) { /* noop */ }
    setMode(saved, true);
  }

  /* ---------------- 五阶段实时状态 ---------------- */
  UX.setProgress = function (on, mode) {
    const box = $("#stage-progress");
    if (!box) return;
    if (UX.progressTimer) { clearInterval(UX.progressTimer); UX.progressTimer = null; }
    if (!on) { box.hidden = true; $$(".stage-dot", box).forEach(d => d.className = "stage-dot"); return; }
    box.hidden = false;
    UX.progressIdx = 0;
    const stages = C.stages || [];
    const dots = $("#stage-dots");
    if (dots) dots.innerHTML = stages.map(() => '<span class="stage-dot"></span>').join("");
    const text = $("#stage-progress-text");
    const tick = () => {
      const dots2 = $$(".stage-dot", box);
      dots2.forEach((d, i) => d.className = "stage-dot" + (i < UX.progressIdx ? " done" : i === UX.progressIdx ? " on" : ""));
      if (text) {
        const st = stages[Math.min(UX.progressIdx, stages.length - 1)];
        text.textContent = (st ? st.label + " · " : "") +
          (UX.progressIdx >= 3 ? (mode === "deep" ? C.progress.deep : C.progress.streaming) : C.progress.start);
      }
      UX.progressIdx = Math.min(UX.progressIdx + 1, stages.length - 1);
    };
    tick();
    UX.progressTimer = setInterval(tick, 1400);
  };

  /* ---------------- 深度解读 / 证据链 / 追问 ---------------- */
  function deepHTML(dp) {
    if (!dp || !dp.concepts || !dp.concepts.length) {
      return `<div class="deep-block"><div class="deep-head"><b>${esc(C.label.deepBlock)}</b>
        <span class="deep-meta">0 张概念卡</span></div>
        <div class="deep-body"><div class="deep-empty">${esc(CX(dp, "warnings", [])[0] || C.empty.concepts)}</div></div></div>`;
    }
    let h = `<div class="deep-block"><div class="deep-head"><b>${esc(C.label.deepBlock)}</b>
      <span class="deep-meta">${dp.concepts.length} 张概念卡 · ${dp.sections.length} 段解读 · 核验日期 2026-11-07</span></div><div class="deep-body">`;
    const order = ["definition", "distinction", "causal", "conditions", "confusion", "limitation"];
    const byConcept = {};
    (dp.sections || []).forEach(s => { (byConcept[s.concept_id] = byConcept[s.concept_id] || []).push(s); });
    dp.concepts.forEach(c => {
      h += `<div class="deep-sec-text" style="margin-top:10px"><span class="deep-concept" data-concept="${esc(c.id)}">${esc(c.code)} ${esc(c.name)} · ${esc(c.category)} · ${esc(c.tier)} 层</span></div>`;
      const secs = (byConcept[c.id] || []).slice().sort((a, b) => order.indexOf(a.type) - order.indexOf(b.type));
      secs.forEach((s, i) => {
        h += `<div class="deep-sec"><div class="deep-sec-label"><i>${i + 1}</i>${esc(s.label)}</div>
          <div class="deep-sec-text">${esc(s.text)}<div>` +
          (s.refs || []).map(r => `<span class="deep-ref" data-ref="${esc(r)}">${esc(r)} ↗</span>`).join("") +
          `</div></div></div>`;
      });
    });
    if (dp.warnings && dp.warnings.length) {
      h += `<div class="ux-warn">${dp.warnings.map(w => `<div>· ${esc(w)}</div>`).join("")}</div>`;
    }
    if (dp.confusions && dp.confusions.length) {
      h += `<div class="ux-subhead">${esc(C.label.confusions)}</div><table class="ux-matrix"><thead><tr>
        <th>概念 A</th><th>概念 B</th><th>关键不同点</th><th>判断顺序</th><th>答错后果</th></tr></thead><tbody>` +
        dp.confusions.slice(0, 5).map(x => `<tr><td>${esc(x.a)}</td><td>${esc(x.b)}</td><td>${esc(x.difference)}</td><td>${esc(x.order)}</td><td>${esc(x.cost)}</td></tr>`).join("") +
        `</tbody></table>`;
    }
    if (dp.thresholds && dp.thresholds.length) {
      h += `<div class="ux-subhead">${esc(C.label.boundaries)}</div><table class="ux-matrix"><thead><tr>
        <th>数字</th><th>口径</th><th>生效时点</th><th>例外 / 边界</th><th>依据条目</th></tr></thead><tbody>` +
        dp.thresholds.slice(0, 8).map(x => `<tr><td>${esc(x.value)}</td><td>${esc(x.scope)}</td><td>${esc(x.effective)}</td><td>${esc(x.edge)}</td><td>${esc(x.ref_entry)}</td></tr>`).join("") +
        `</tbody></table>`;
    }
    if (dp.scenarios && dp.scenarios.length) {
      h += `<div class="ux-subhead">${esc(C.label.scenarios)}</div>`;
      dp.scenarios.slice(0, 3).forEach(s => {
        h += `<div class="deep-sec-text" style="margin-bottom:8px"><b>${esc(s.name)}</b><br>` +
          (s.path || []).slice(0, 5).map((p, i) => `${i + 1}. ${esc(p)}`).join("<br>") +
          (s.pitfalls ? `<br><span style="color:var(--risk-mid)">易错：${esc(s.pitfalls)}</span>` : "") + `</div>`;
      });
    }
    h += `</div></div>`;
    return h;
  }

  function followupHTML(meta, dp) {
    const items = [];
    if (dp && dp.suggestions) dp.suggestions.slice(0, 3).forEach(s =>
      items.push(`${s.name}是什么？适用条件和边界是什么？`));
    if (dp && dp.concepts && dp.concepts.length) {
      const n = dp.concepts[0].name;
      items.push(`${n}和相近概念有什么区别？`);
      items.push(`${n}常见的错误结论有哪些？`);
    }
    if (!items.length) items.push("中小企业有哪些税收优惠", "小规模纳税人超过 500 万怎么办", "员工自愿放弃社保有效吗");
    return `<div class="followup-bar"><div class="ux-subhead">${esc(C.action.followup)}</div>` +
      items.slice(0, 4).map(q => `<button class="followup-chip" data-q="${esc(q)}">${esc(q)} ↗</button>`).join("") +
      `</div>`;
  }

  function evidenceHTML(refs) {
    if (!refs || !refs.length) return "";
    const idx = (typeof S !== "undefined" && S.kbIndex) ? S.kbIndex : {};
    return `<details class="evidence-box"><summary>${esc(C.label.evidence)} · ${refs.length} 条</summary>` +
      refs.slice(0, 8).map(r => {
        const e = idx[r];
        return `<div class="evidence-row"><span class="ref-chip" data-ref="${esc(r)}">${esc(r)} ↗</span>
          <span>${esc(e ? e.title : "知识库条目")}</span>
          <span>${esc(e ? (e.status || "") : "")}</span>
          <span>${esc(e ? (e.tier || "") + " 层" : "")}</span></div>`;
      }).join("") + `</details>`;
  }

  UX.decorateLastMessage = function (meta) {
    meta = meta || {};
    const msgs = $$(".message.assistant");
    const wrap = msgs[msgs.length - 1];
    if (!wrap) return;
    const body = $(".msg-body", wrap);
    if (!body || body.dataset.uxDecorated === "1") return;
    body.dataset.uxDecorated = "1";
    const dp = meta.deep || (meta.answer && meta.answer.deep);
    let html = "";

    // 异常态：云端回退/错误 → 明确原因 + 可操作动作
    if (meta.fallbackNotice) {
      html += `<div class="ux-state warn"><b>${esc(C.error.cloud)}</b><span>${esc(meta.fallbackNotice)}</span>
        <div class="ux-actions">
          <button data-ux-act="retry">${esc(C.error.retry)}</button>
          <button data-ux-act="switch-model">${esc(C.error.switchModel)}</button>
          <button data-ux-act="view-local">${esc(C.error.viewLocal)}</button>
        </div></div>`;
    }
    const errNode = $(".ux-raw-error", body);
    if (errNode) {
      html += `<div class="ux-state error"><b>${esc(C.error.local)}</b><span>${esc(errNode.textContent)}</span>
        <div class="ux-actions"><button data-ux-act="retry">${esc(C.error.retry)}</button>
        <button data-ux-act="browse">${esc(C.action.browseAll)}</button></div></div>`;
      errNode.classList.add("ux-raw-error");
      errNode.style.display = "none";
    }
    if (dp) html += deepHTML(dp);
    html += followupHTML(meta, dp);
    html += evidenceHTML(meta.refs || (meta.answer && meta.answer.refs));
    body.insertAdjacentHTML("beforeend", html);
    bindDecorations(body, meta);
    const an = $("#ux-announcer");
    if (an) an.textContent = C.a11y.newAnswer;
  };

  function bindDecorations(root, meta) {
    $$(".deep-ref, .evidence-row .ref-chip", root).forEach(ch =>
      ch.addEventListener("click", () => { try { window.openDetail(ch.dataset.ref); } catch (e) { /* noop */ } }));
    $$("[data-concept]", root).forEach(ch =>
      ch.addEventListener("click", () => openConceptPanel(ch.dataset.concept)));
    $$(".followup-chip", root).forEach(ch =>
      ch.addEventListener("click", () => {
        const inp = $("#chat-input");
        if (inp) { inp.value = ch.dataset.q; inp.focus(); inp.dispatchEvent(new Event("input", { bubbles: true })); }
        try { window.switchTab("chat"); } catch (e) { /* noop */ }
      }));
    $$("[data-ux-act]", root).forEach(b => b.addEventListener("click", () => {
      const act = b.dataset.uxAct;
      if (act === "retry") { toast(C.error.retry); try { window.ask(meta.q || "", { reuse: true }); } catch (e) { /* noop */ } }
      else if (act === "switch-model") { $("#model-select") && $("#model-select").focus(); toast("请在输入框左侧切换作答模型"); }
      else if (act === "view-local") { $(".llm-stream", root) && $(".llm-stream", root).scrollIntoView({ block: "nearest" }); }
      else if (act === "browse") { try { window.switchTab("kb"); } catch (e) { /* noop */ } }
    }));
  }

  /* ---------------- 概念面板 ---------------- */
  async function loadConceptData() {
    try {
      const [c, s] = await Promise.all([
        fetch("/api/concepts").then(r => r.json()),
        fetch("/api/scenarios").then(r => r.json()),
      ]);
      UX.concepts = c.concepts || [];
      UX.scenarios = s.scenarios || [];
      const cnt = $("#concept-count");
      if (cnt) cnt.textContent = UX.concepts.length + " 张卡 · " + UX.scenarios.length + " 个场景";
      renderConceptList();
      ensureWelcomeGuide();
    } catch (e) { /* 服务不可用时保持静默，概念面板显示加载失败态 */ }
  }

  function renderConceptList(q) {
    const list = $("#concept-list");
    if (!list) return;
    const kw = (q || "").trim().toLowerCase();
    const items = UX.concepts.filter(c => !kw ||
      (c.name + c.code + c.category + c.definition).toLowerCase().includes(kw));
    if (!items.length) {
      list.innerHTML = `<div class="ux-state" style="margin:8px"><b>${esc(C.empty.concepts)}</b>
        <div class="ux-actions"><button data-ux-clear="1">${esc(C.action.clearFilter)}</button></div></div>`;
      $$("[data-ux-clear]", list).forEach(b => b.addEventListener("click", () => {
        const inp = $("#concept-search"); if (inp) { inp.value = ""; renderConceptList(); }
      }));
      return;
    }
    list.innerHTML = items.map(c => `<button class="concept-item${c.id === UX.activeConcept ? " active" : ""}"
      data-id="${esc(c.id)}" role="option" aria-selected="${c.id === UX.activeConcept}">
      <span class="c-code">${esc(c.code)}</span><span>${esc(c.name)}</span></button>`).join("");
    $$(".concept-item", list).forEach(b => b.addEventListener("click", () => showConcept(b.dataset.id)));
  }

  async function showConcept(id) {
    const detail = $("#concept-detail");
    if (!detail) return;
    UX.activeConcept = id;
    renderConceptList($("#concept-search") ? $("#concept-search").value : "");
    detail.innerHTML = `<div class="deep-empty">正在加载概念卡…</div>`;
    let c;
    try { c = await fetch("/api/concept?id=" + encodeURIComponent(id)).then(r => r.json()); }
    catch (e) { detail.innerHTML = `<div class="ux-state error"><b>概念卡加载失败</b><span>请确认本地服务已启动后重试。</span></div>`; return; }
    if (!c || c.error) { detail.innerHTML = `<div class="ux-state error"><b>未找到概念卡</b></div>`; return; }
    UX.conceptDetail = c;
    const fields = [
      ["定义", "definition"], ["定义辨析", "distinctions"], ["因果逻辑", "causal"],
      ["适用条件", "conditions"], ["边界条件与例外", "boundaries"],
      ["易混淆点", "confusions"], ["局限说明", "limitations"],
      ["常见场景", "scenarios"], ["主要依据", "basis"], ["关联条目", "related_entries"],
      ["关联概念", "related_concepts"], ["核验", "verified"],
    ];
    detail.innerHTML = `<h3>${esc(c.code)} ${esc(c.name)}</h3>
      <div class="c-meta"><span class="c-pill">${esc(c.category)}</span>
        <span class="c-pill">${esc(c.tier)} 层</span>
        <span class="c-pill" title="${esc(C.label.statusHint(c.status))}">${esc(c.status)}</span>
        <span class="c-pill">${(c.sources || []).length} 个官方信源</span></div>` +
      fields.map(([label, key]) => c[key] ? `<div class="c-field"><b>${esc(label)}</b><span>${esc(c[key])}</span></div>` : "").join("") +
      (c.confusions && c.confusions.length ? `<div class="c-field"><b>易混淆对照</b><span>` +
        c.confusions.slice(0, 3).map(x => `${esc(x.a)} vs ${esc(x.b)}：${esc(x.difference)}`).join("<br>") + `</span></div>` : "") +
      (c.scenarios && c.scenarios.length ? `<div class="c-field"><b>关联场景</b><span>` +
        c.scenarios.map(x => esc(x.name)).join("、") + `</span></div>` : "") +
      `<div class="c-actions">
        <button data-c-act="ask">用深度解读提问</button>
        <button data-c-act="refs">查看法规依据</button>
        <button data-c-act="copy">复制概念卡</button>
      </div>`;
    $$("[data-c-act]", detail).forEach(b => b.addEventListener("click", async () => {
      const act = b.dataset.cAct;
      if (act === "ask") {
        setMode("deep"); closeConceptPanel();
        const inp = $("#chat-input");
        if (inp) { inp.value = `${c.name}的定义、适用条件、易混淆点和局限是什么？`; inp.focus(); inp.dispatchEvent(new Event("input", { bubbles: true })); }
        toast("已切换为深度解读，按 Enter 发送");
      } else if (act === "refs") {
        const first = (c.entry_refs || []).length ? c.entry_refs[0] : (c.related_entries || "").match(/\d{2}-[\d.\-]+/);
        const rid = Array.isArray(first) ? first[0] : first;
        if (rid) { closeConceptPanel(); try { window.openDetail(rid); } catch (e) { /* noop */ } }
        else toast(C.empty.refs, "warn");
      } else if (act === "copy") {
        const txt = `${c.code} ${c.name}\n` + fields.map(([l, k]) => c[k] ? `${l}：${c[k]}` : "").filter(Boolean).join("\n");
        try { await navigator.clipboard.writeText(txt); toast("概念卡已复制"); } catch (e) { toast("复制失败", "warn"); }
      }
    }));
  }

  function openConceptPanel(id) {
    const ov = $("#concept-overlay");
    if (!ov) return;
    ov.hidden = false;
    const inp = $("#concept-search");
    if (inp) { inp.value = ""; renderConceptList(); setTimeout(() => inp.focus(), 30); }
    if (id) showConcept(id);
    else if (!UX.activeConcept && UX.concepts.length) showConcept(UX.concepts[0].id);
  }
  function closeConceptPanel() { const ov = $("#concept-overlay"); if (ov) ov.hidden = true; }
  UX.openConceptPanel = openConceptPanel;

  function bindConceptPanel() {
    const trig = $("#concept-trigger");
    if (trig) trig.addEventListener("click", () => openConceptPanel());
    const close = $("#concept-close");
    if (close) close.addEventListener("click", closeConceptPanel);
    const ov = $("#concept-overlay");
    if (ov) ov.addEventListener("click", (e) => { if (e.target === ov) closeConceptPanel(); });
    const inp = $("#concept-search");
    if (inp) {
      let t;
      inp.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => renderConceptList(inp.value), 160); });
      inp.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          const items = $$(".concept-item");
          if (!items.length) return;
          const i = items.findIndex(x => x.classList.contains("active"));
          const n = e.key === "ArrowDown" ? Math.min(i + 1, items.length - 1) : Math.max(i - 1, 0);
          items[n].click(); items[n].scrollIntoView({ block: "nearest" });
        }
      });
    }
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && ov && !ov.hidden) { closeConceptPanel(); return; }
      // 概念面板焦点约束（简易 focus trap）
      if (e.key === "Tab" && ov && !ov.hidden) {
        const focusables = $$('button, input, [tabindex]:not([tabindex="-1"])', ov).filter(x => !x.disabled);
        if (!focusables.length) return;
        const first = focusables[0], last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
  }

  /* ---------------- 提问引导（欢迎区） ---------------- */
  function ensureWelcomeGuide() {
    const w = $(".welcome");
    if (!w || $("#ux-welcome-guide")) return;
    const picks = UX.scenarios.filter(s => /新设企业|汇算清缴前|异常凭证|优惠适用/.test(s.name)).slice(0, 4);
    const labels = picks.length ? picks : UX.scenarios.slice(0, 4);
    const qs = [
      "新设企业怎么判断增值税身份和首个申报期？",
      "汇算清缴前发票没到，应该补票还是追补扣除？",
      "收到异常凭证通知被要求进项转出怎么办？",
      "我们公司能享受哪些税收优惠，能叠加吗？",
    ];
    const box = document.createElement("div");
    box.id = "ux-welcome-guide";
    box.className = "followup-bar";
    box.innerHTML = `<div class="ux-subhead">按常见场景开始（点击后可编辑再发送）</div>` +
      (labels.length ? labels : qs.map(q => ({ name: q }))).slice(0, 4).map((s, i) =>
        `<button class="followup-chip" data-q="${esc(qs[i] || s.name)}">${esc(s.name)} ↗</button>`).join("");
    w.appendChild(box);
    $$(".followup-chip", box).forEach(b => b.addEventListener("click", () => {
      const inp = $("#chat-input");
      if (inp) { inp.value = b.dataset.q; inp.focus(); inp.dispatchEvent(new Event("input", { bubbles: true })); }
    }));
  }

  /* ---------------- 空态 / 网络 / 文案一致性 / a11y ---------------- */
  function bindEmptyStates() {
    const target = $("#kb-list");
    if (!target) return;
    let busy = false;
    const check = () => {
      if (busy) return;
      busy = true;
      const existing = $("#ux-kb-empty");
      const hasItems = $$(".kb-item", target).length > 0;
      const search = $("#kb-search") ? $("#kb-search").value.trim() : "";
      if (!hasItems && search && !existing) {
        const box = document.createElement("div");
        box.id = "ux-kb-empty"; box.className = "ux-state";
        box.style.margin = "10px";
        box.innerHTML = `<b>${esc(C.empty.search)}</b><div class="ux-actions">
          <button data-ux-clear-kb="1">${esc(C.action.clearFilter)}</button>
          <button data-ux-browse="1">${esc(C.action.browseAll)}</button></div>`;
        target.appendChild(box);
        $$("[data-ux-clear-kb]", box).forEach(b => b.addEventListener("click", () => {
          const inp = $("#kb-search"); if (inp) { inp.value = ""; inp.dispatchEvent(new Event("input", { bubbles: true })); }
          const clr = $("#kb-search-clear"); if (clr) clr.click();
        }));
        $$("[data-ux-browse]", box).forEach(b => b.addEventListener("click", () => {
          $$("#kb-filters .filter-chip").forEach(c => { if (c.dataset.cat === "all") c.click(); });
        }));
      } else if (hasItems && existing) existing.remove();
      busy = false;
    };
    const mo = new MutationObserver(check);
    mo.observe(target, { childList: true });
    UX.observer = mo;
    const wmo = new MutationObserver(() => { ensureWelcomeGuide(); });
    const scroll = $("#chat-scroll");
    if (scroll) { wmo.observe(scroll, { childList: true }); UX.welcomeObserver = wmo; }
    setTimeout(check, 600);
  }

  function bindNetwork() {
    const banner = () => {
      let el = $("#ux-offline");
      if (!navigator.onLine) {
        if (!el) {
          el = document.createElement("div");
          el.id = "ux-offline"; el.className = "ux-offline"; el.setAttribute("role", "status");
          document.body.appendChild(el);
        }
        el.textContent = C.error.offline;
      } else if (el) {
        el.textContent = C.error.online;
        setTimeout(() => el.remove(), 1800);
      }
    };
    window.addEventListener("offline", banner);
    window.addEventListener("online", banner);
  }

  function applyCopyConsistency() {
    const note = $(".composer-note");
    if (note) note.innerHTML = `<kbd>Enter</kbd> 发送 · <kbd>Shift + Enter</kbd> 换行 · <kbd>Ctrl K</kbd> 全局检索 · 回答受知识库约束，${esc("重要事项请以官方原文复核")}`;
    const skip = $(".skip-link");
    if (skip) skip.textContent = C.a11y.skip;
    const trigger = $("#concept-trigger");
    if (trigger) trigger.setAttribute("aria-label", C.a11y.conceptDialog);
    const list = $("#concept-list");
    if (list) { list.setAttribute("role", "listbox"); list.setAttribute("aria-label", C.a11y.conceptList); }
    const detail = $("#concept-detail");
    if (detail) detail.setAttribute("aria-label", C.a11y.conceptDetail);
    const prog = $("#stage-progress");
    if (prog) { prog.setAttribute("role", "status"); prog.setAttribute("aria-label", C.a11y.progress); }
    const seg = $("#answer-mode");
    if (seg) seg.setAttribute("aria-label", C.a11y.modeGroup);
    let an = $("#ux-announcer");
    if (!an) {
      an = document.createElement("div");
      an.id = "ux-announcer"; an.className = "sr-only";
      an.setAttribute("aria-live", "polite"); an.setAttribute("aria-atomic", "true");
      document.body.appendChild(an);
    }
  }

  /* ---------------- 启动 ---------------- */
  function init() {
    bindMode();
    bindConceptPanel();
    bindEmptyStates();
    bindNetwork();
    applyCopyConsistency();
    loadConceptData();
    setTimeout(ensureWelcomeGuide, 400);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
