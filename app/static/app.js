/* =============================================================================
   app.js — 财税合规智能体 v3 前端
   云端 LLM 流式（WorkBuddy Cloud SDK）+ 本地检索兜底 + 多会话 + 全局搜索
   零框架 / 零第三方依赖（SDK 由 index.html 引入）
   ============================================================================= */
"use strict";

/* ---------------- 基础工具 ---------------- */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const NON_CHAT_IDS = new Set(["kling-video-v3", "minimax-video-h3", "hunyuan-image-alpha",
  "hunyuan-image-alpha-edit", "hunyuan-chat"]);
const TAB_META = {
  chat: ["合规对话", "专家团分诊 · 结论 → 依据 → 风险提示"],
  kb: ["法规库", "结构化法规条目 · 分类检索与出处留痕"],
  incentives: ["优惠速查", "有效期 + 适用条件双字段核对"],
  about: ["关于与帮助", "运行架构、准确性机制与免责声明"],
  business: ["业务事项", "按业务场景组织的确认计量 · 分录流程 · 税会差异 · 依据边界"],
};
const esc = (v) => String(v == null ? "" : v)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const uid = (p) => p + "-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 7);
const nowTime = () => new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

/* 检索同义词：财税领域常用简称 → 法定全称，避免「残保金」「数电票」等口语检索漏召回 */
const SEARCH_SYNONYMS = {
  "残保金": ["残疾人就业保障金", "保障金"],
  "数电票": ["全面数字化的电子发票", "电子发票"],
  "全电发票": ["全面数字化的电子发票"],
  "个税": ["个人所得税"],
  "企税": ["企业所得税"],
  "社保": ["社会保险"],
  "高新": ["高新技术企业"],
  "复议": ["行政复议"],
  "稽查": ["税务稽查"],
  "小微": ["小型微利", "小微企业"],
  "两费": ["六税两费"],
  "背靠背": ["款项支付", "账款"],
  "加计": ["加计扣除"],
};
function expandQuery(q) {
  const out = [q];
  Object.keys(SEARCH_SYNONYMS).forEach(k => {
    if (k.includes(q) || q.includes(k)) out.push(...SEARCH_SYNONYMS[k]);
  });
  return Array.from(new Set(out.filter(Boolean)));
}
function kbBlob(e) {
  return (e.title + " " + e.heading + " " + e.search_text + " " + (e.no || "") + " " +
    e.body_md + " " + JSON.stringify(e.fields)).toLowerCase();
}
function kbMatches(e, q) {
  if (!q) return true;
  const blob = e._blob || kbBlob(e);
  return expandQuery(q).some(t => blob.includes(String(t).toLowerCase()));
}

/* ---------------- 全局状态 ---------------- */
const S = {
  meta: null, kb: null, kbIndex: {}, examples: null,
  tab: "chat", quickGroup: "hot",
  sessions: [], activeId: "", favorites: new Set(),
  settings: { theme: "system", fontsize: "normal", stream: true, autoscroll: true },
  cloud: { client: null, ready: false, models: [], current: "" },
  history: [], conversationId: "", abort: null, busy: false,
  stick: true,
  kbView: { q: "", cat: "all", fav: false, sort: "default", items: [] },
  inc: { q: "", status: "all", tables: [] },
  lastAnswerFor: "",
};

/* ---------------- 本地存储 ---------------- */
function lsGet(key, fallback) {
  try { const v = localStorage.getItem("taxagent." + key); return v == null ? fallback : JSON.parse(v); }
  catch (e) { return fallback; }
}
function lsSet(key, val) {
  try { localStorage.setItem("taxagent." + key, JSON.stringify(val)); return true; }
  catch (e) { return false; }
}
function loadLocal() {
  S.settings = Object.assign(S.settings, lsGet("settings", {}));
  S.favorites = new Set(lsGet("favorites", []));
  const saved = lsGet("sessions", []);
  S.sessions = Array.isArray(saved) ? saved.filter(x => x && Array.isArray(x.messages)) : [];
  S.activeId = lsGet("active", "") || "";
  if (!S.sessions.some(s => s.id === S.activeId)) S.activeId = S.sessions.length ? S.sessions[0].id : "";
  if (!S.activeId) newSession(false);
}
function saveSessions() {
  let list = S.sessions.slice(-12);
  while (!lsSet("sessions", list) && list.length > 1) list = list.slice(1);
  lsSet("active", S.activeId);
}

/* ---------------- 空态引导 ---------------- */
function emptyState(title, desc, actionLabel, actionId) {
  return `<div class="kb-empty rich">
    <svg class="ico" aria-hidden="true"><use href="#i-search"/></svg>
    <b>${esc(title)}</b>
    <span>${esc(desc)}</span>
    ${actionLabel ? `<button class="ghost-btn" id="${esc(actionId)}">${esc(actionLabel)}</button>` : ""}
  </div>`;
}

/* ---------------- Toast ---------------- */
function toast(msg, type = "ok", ms = 2800) {
  const root = $("#toast-root");
  while (root.children.length >= 3) root.firstElementChild.remove();
  const el = document.createElement("div");
  el.className = "toast " + type;
  el.innerHTML = `<svg class="ico"><use href="#i-${type === "err" ? "warn" : type === "warn" ? "warn" : "check"}"/></svg><span>${esc(msg)}</span><button class="toast-x" aria-label="关闭提示">×</button>`;
  root.appendChild(el);
  let timer = setTimeout(dismiss, ms);
  function dismiss() {
    el.style.opacity = "0"; el.style.transform = "translateX(12px)";
    setTimeout(() => el.remove(), 220);
  }
  /* hover 暂停自动消失；点击 × 立即关闭 */
  el.addEventListener("mouseenter", () => clearTimeout(timer));
  el.addEventListener("mouseleave", () => { timer = setTimeout(dismiss, 1400); });
  el.querySelector(".toast-x").addEventListener("click", dismiss);
}

/* ---------------- 主题与设置 ---------------- */
function effectiveDark() {
  return S.settings.theme === "dark" ||
    (S.settings.theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
}
function applySettings() {
  document.documentElement.dataset.theme = effectiveDark() ? "dark" : "light";
  document.documentElement.dataset.fontsize = S.settings.fontsize;
  $$("#theme-seg button").forEach(b => {
    const on = b.dataset.val === S.settings.theme;
    b.classList.toggle("active", on); b.setAttribute("aria-checked", on ? "true" : "false");
  });
  $$("#font-seg button").forEach(b => {
    const on = b.dataset.val === S.settings.fontsize;
    b.classList.toggle("active", on); b.setAttribute("aria-checked", on ? "true" : "false");
  });
  $("#opt-stream").checked = S.settings.stream;
  $("#opt-autoscroll").checked = S.settings.autoscroll;
  const icon = effectiveDark() ? "#i-moon" : "#i-sun";
  $("#theme-quick").querySelector("use").setAttribute("href", icon);
  lsSet("settings", S.settings);
}
function setTheme(v) { S.settings.theme = v; applySettings(); toast("外观已切换为" + ({ light: "浅色", dark: "深色", system: "跟随系统" })[v]); }

/* ---------------- 视图切换 ---------------- */
function switchTab(name, opts = {}) {
  if (!TAB_META[name]) return;
  S.tab = name;
  $$(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  $$(".mobile-nav-item").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  $$(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + name));
  $("#view-title").textContent = TAB_META[name][0];
  $("#view-sub").textContent = TAB_META[name][1];
  closeOverlays();
  if (name === "chat") requestAnimationFrame(() => scrollChat(true));
  if (name === "kb" && opts.detail) openDetail(opts.detail);
}

/* ---------------- 会话管理 ---------------- */
function currentSession() {
  let s = S.sessions.find(x => x.id === S.activeId);
  if (!s) { s = S.sessions[S.sessions.length - 1]; if (s) S.activeId = s.id; }
  return s;
}
function newSession(notify = true) {
  const cur = currentSession();
  if (cur && cur.messages.length === 0) { if (notify) toast("已经是新会话了"); return; }
  const s = { id: uid("s"), title: "新会话", created: Date.now(), updated: Date.now(), messages: [] };
  S.sessions.push(s); S.activeId = s.id; S.history = []; S.conversationId = "";
  saveSessions(); renderSessions(); renderChat();
  if (notify) { toast("已新建会话"); $("#chat-input").focus(); }
}
function loadSession(id) {
  const s = S.sessions.find(x => x.id === id);
  if (!s) return;
  S.activeId = id; S.history = []; S.conversationId = "";
  saveSessions(); renderSessions(); renderChat(); switchTab("chat");
}
function deleteSession(id, ev) {
  ev.stopPropagation();
  S.sessions = S.sessions.filter(s => s.id !== id);
  if (!S.sessions.length) S.sessions.push({ id: uid("s"), title: "新会话", created: Date.now(), updated: Date.now(), messages: [] });
  if (S.activeId === id) { S.activeId = S.sessions[S.sessions.length - 1].id; renderChat(); }
  saveSessions(); renderSessions(); toast("会话已删除");
}
function clearSession() {
  const s = currentSession(); if (!s) return;
  s.messages = []; s.title = "新会话"; s.updated = Date.now();
  S.history = []; S.conversationId = "";
  saveSessions(); renderSessions(); renderChat(); toast("当前会话已清空");
}
function renderSessions() {
  const box = $("#session-list");
  const list = S.sessions.slice().sort((a, b) => b.updated - a.updated).slice(0, 10);
  if (!list.length || (list.length === 1 && !list[0].messages.length)) {
    box.innerHTML = `<div class="session-empty">还没有历史会话。<br>开始提问后会自动保存在本机。</div>`;
    return;
  }
  box.innerHTML = list.map(s => `
    <div class="session-item ${s.id === S.activeId ? "active" : ""}" data-id="${esc(s.id)}" role="listitem" tabindex="0">
      <svg class="ico" style="width:13px;height:13px"><use href="#i-chat"/></svg>
      <span class="s-title">${esc(s.title)}</span>
      <button class="s-del" title="删除会话" aria-label="删除会话"><svg class="ico"><use href="#i-trash"/></svg></button>
    </div>`).join("");
  box.querySelectorAll(".session-item").forEach(el => {
    el.addEventListener("click", () => loadSession(el.dataset.id));
    el.addEventListener("keydown", e => { if (e.key === "Enter") loadSession(el.dataset.id); });
    el.querySelector(".s-del").addEventListener("click", e => deleteSession(el.dataset.id, e));
  });
}
function sessionTitle(s, q) {
  if (s.messages.filter(m => m.role === "user").length <= 1) s.title = q.slice(0, 22) + (q.length > 22 ? "…" : "");
}

/* ---------------- 欢迎空状态 ---------------- */
function welcomeHTML() {
  const hot = (S.examples && S.examples.groups.find(g => g.id === "hot")) || { items: [] };
  const caps = [
    ["i-book", "可溯源的法规库", (S.meta ? S.meta.entries : "—") + " 条结构化条目，每条附文号、时效性与合规要点"],
    ["i-route", "专家团智能分诊", "按问题类型路由到票务、记账、申报或审计角色"],
    ["i-shield", "五道准确性护栏", "强制引用、时效过滤、不确定即承认、高风险转介"],
  ];
  return `<div class="welcome">
    <div class="welcome-eyebrow"><svg class="ico" style="width:13px;height:13px"><use href="#i-shield"/></svg> 财税合规工作台 · 知识库 ${esc(S.meta ? S.meta.kb_version : "—")}</div>
    <h2>把财税问题，<em>问到有出处</em>。</h2>
    <p>描述你的合规疑问，智能体会先检索已核验的法规知识库，再由专家团对应角色给出「结论 → 依据 → 风险提示」，并附可点击的原文条目。</p>
    <div class="cap-grid">${caps.map(c => `<div class="cap-card"><div class="cap-ico"><svg class="ico"><use href="#${c[0]}"/></svg></div><div><b>${c[1]}</b><span>${esc(c[2])}</span></div></div>`).join("")}</div>
    <div class="welcome-label">试试这些问题</div>
    <div class="welcome-chips">${hot.items.slice(0, 6).map(it =>
      `<button class="welcome-chip" data-q="${esc(it.q)}">${esc(it.q)}<span class="arrow">↗</span></button>`).join("")}</div>
    <p class="welcome-fine"><b>本工具仅用于辅助合规自查，不构成专业税务/法律意见。</b>回答基于知识库核验日期 ${esc(S.meta ? S.meta.verified_at : "—")}，全部结论以官方发布原文为准；涉税计算由本地确定性引擎产出，大模型不直接算税。</p>
  </div>`;
}

/* ---------------- 消息渲染 ---------------- */
function renderChat() {
  const box = $("#chat-scroll");
  const s = currentSession();
  box.innerHTML = "";
  if (!s || !s.messages.length) {
    box.classList.add("is-empty"); box.innerHTML = welcomeHTML(); bindWelcome();
  } else {
    box.classList.remove("is-empty"); s.messages.forEach(m => appendMessage(m));
  }
  S.stick = true;
  requestAnimationFrame(() => scrollChat(true));
}
function bindWelcome() {
  $$(".welcome-chip").forEach(b => b.addEventListener("click", () => ask(b.dataset.q)));
}
function scrollChat(force) {
  const sc = $("#chat-scroll");
  if (!sc) return;
  if (force || (S.settings.autoscroll && S.stick)) sc.scrollTop = sc.scrollHeight;
  updateScrollBtn();
}
function updateScrollBtn() {
  const sc = $("#chat-scroll"), btn = $("#scroll-bottom");
  if (!sc || !btn) return;
  const far = sc.scrollHeight - sc.scrollTop - sc.clientHeight > 110;
  btn.hidden = !far;
}

function appendMessage(m) {
  const box = $("#chat-scroll");
  const welcome = box.querySelector(".welcome");
  if (welcome) { welcome.remove(); box.classList.remove("is-empty"); }
  const wrap = document.createElement("div");
  wrap.className = "message " + (m.role === "user" ? "user" : "assistant");
  wrap.dataset.mid = m.id;
  if (m.role === "user") {
    wrap.innerHTML = `<div class="avatar">我</div><div class="msg-col">
      <div class="msg-head"><span class="msg-time">${esc(m.ts || nowTime())}</span></div>
      <div class="msg-body">${esc(m.text)}</div>
      <div class="msg-actions"><button class="msg-action" data-act="copy" data-text="${esc(m.text)}"><svg class="ico"><use href="#i-copy"/></svg> 复制</button></div>
    </div>`;
  } else {
    const p = m.payload || {};
    const role = p.role || { emoji: "🧭", name: "钱合规" };
    const routed = p.routed || "lead";
    const risk = p.risk || "low";
    const mode = p.mode || (p.kind === "llm" ? "云端大模型" : "精编答案库");
    wrap.innerHTML = `<div class="avatar">${esc((role.name || "钱合规").slice(0, 1))}</div><div class="msg-col">
      <div class="msg-head">
        <span class="role-chip ${esc(routed)}">${esc(role.emoji || "")} ${esc(role.name || "钱合规")}</span>
        ${riskBadge(risk)}
        <span class="mode-badge ${p.kind === "llm" ? "llm-badge" : ""}">${esc(mode)}</span>
        <span class="msg-time">${esc(m.ts || nowTime())}</span>
      </div>
      <div class="msg-body"></div>
      <div class="msg-actions">
        <button class="msg-action" data-act="copy"><svg class="ico"><use href="#i-copy"/></svg> 复制</button>
        <button class="msg-action" data-act="regen"><svg class="ico"><use href="#i-retry"/></svg> 重新生成</button>
        <button class="msg-action" data-act="refs"><svg class="ico"><use href="#i-book"/></svg> 查看依据</button>
      </div>
    </div>`;
    const body = wrap.querySelector(".msg-body");
    if (p.kind === "structured") renderStructured(p.answer, p.disclaimer, body);
    else if (p.kind === "llm") renderLLMAnswer(p, body);
    else if (p.kind === "error") body.innerHTML = `<div class="ux-raw-error" style="color:var(--risk-high)">${esc(p.text)}</div>`;
  }
  box.appendChild(wrap);
  bindMsgActions(wrap, m);
  return wrap;
}
function riskBadge(risk) {
  const map = { high: ["🔴 高风险", "risk-high"], mid: ["🟡 中风险", "risk-mid"], low: ["🟢 低风险", "risk-low"] };
  const v = map[risk] || map.low;
  return `<span class="risk-badge ${v[1]}">${v[0]}</span>`;
}
function bindMsgActions(wrap, m) {
  wrap.querySelectorAll(".msg-action").forEach(btn => {
    btn.addEventListener("click", async () => {
      const act = btn.dataset.act;
      if (act === "copy") {
        const text = btn.dataset.text || wrap.querySelector(".msg-body").innerText;
        try { await navigator.clipboard.writeText(text); }
        catch (e) {
          const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta);
          ta.select(); try { document.execCommand("copy"); } catch (_) {} ta.remove();
        }
        btn.classList.add("done"); toast("已复制到剪贴板");
        setTimeout(() => btn.classList.remove("done"), 1600);
      } else if (act === "regen") {
        regenerate(m.id);
      } else if (act === "refs") {
        const p = m.payload || {};
        const refs = (p.refs || (p.answer && p.answer.refs) || []);
        if (refs.length) openDetail(refs[0]); else toast("本条回答未附法规条目", "warn");
      }
    });
  });
}
function pushMessage(m, render = true) {
  const s = currentSession(); if (!s) return null;
  m.id = m.id || uid("m"); m.ts = m.ts || nowTime();
  s.messages.push(m); s.updated = Date.now();
  if (m.role === "user") sessionTitle(s, m.text || "");
  if (s.messages.length > 60) s.messages = s.messages.slice(-60);
  saveSessions(); renderSessions();
  return render ? appendMessage(m) : null;
}
document.addEventListener("click", (ev) => {
  const free = ev.target.closest("[data-clarify-free]");
  if (free) {
    ev.preventDefault();
    const inp = document.getElementById("chat-input") || document.querySelector("textarea");
    if (inp) { inp.focus(); inp.scrollIntoView({ block: "center" }); }
    return;
  }
  const btn = ev.target.closest("[data-clarify]");
  if (!btn) return;
  ev.preventDefault();
  const q = btn.getAttribute("data-clarify");
  if (q) ask(q);
});

function pushError(text) {
  pushMessage({ role: "assistant", payload: { kind: "error", text } });
  if (window.UX) window.UX.decorateLastMessage({ q: S.lastAnswerFor || "" });
}

/* 结构化答案（本地规则 / 检索兜底共用） */
function renderStructured(a, disclaimer, container) {
  if (!a) { container.textContent = "暂无可用答案"; return; }
  let html = "";
  if (a.matched_q && a.mode === "rule") html += `<div class="hint-block">识别为示例问题：${esc(a.matched_q)}</div>`;
  (a.sections || []).forEach(sec => {
    if (sec.type === "conclusion") html += `<div class="sec-title">结论</div><div class="sec-conclusion">${esc(sec.text)}</div>`;
    else if (sec.type === "basis") {
      html += `<div class="sec-title">法规依据</div><ul class="sec-basis">`;
      (sec.items || []).forEach(it => html += `<li>${esc(it.text)}${it.ref ? ` <span class="ref-chip" data-ref="${esc(it.ref)}">原文 ↗</span>` : ""}</li>`);
      html += `</ul>`;
    } else if (sec.type === "tips") {
      html += `<div class="sec-title">风险与合规提示</div><ul class="sec-tips">${(sec.items || []).map(t => `<li>${esc(t)}</li>`).join("")}</ul>`;
    } else if (sec.type === "retrieval") {
      html += `<div class="sec-title">${esc(sec.title || "检索结果")}</div><ul class="sec-retrieval">`;
      (sec.items || []).forEach(it => html += `<li><b>${esc(it.title)}</b>｜${esc(it.status)}｜${esc(it.category)}${it.id ? ` <span class="ref-chip" data-ref="${esc(it.id)}">详情 ↗</span>` : ""}<br><span style="color:var(--text-3);font-size:12.4px">${esc(it.snippet || it.preview || "")}</span></li>`);
      html += `</ul>`;
    } else if (sec.type === "clarify") {
      html += `<div class="sec-title">${esc(sec.title || "请先选择方向")}</div><div class="sec-conclusion">${esc(sec.text || "")}</div>`;
      html += `<div class="clarify-row">`;
      (sec.options || []).forEach((op, i) => {
        html += `<button class="clarify-opt" data-clarify="${esc(op.q || op.label)}" data-idx="${i}">${esc(op.label || op.q)}</button>`;
      });
      html += `<button class="clarify-opt clarify-free" data-clarify-free="1">都不匹配，我直接描述</button>`;
      html += `</div>`;
    } else if (sec.type === "escalate") html += `<div class="sec-escalate">${esc(sec.text)}</div>`;
  });
  if (a.refs && a.refs.length) {
    html += `<div class="sec-title">知识库条目</div>`;
    a.refs.forEach(rid => {
      const e = S.kbIndex[rid];
      if (e) html += `<span class="ref-chip" data-ref="${esc(rid)}">${esc(e.no || "")} ${esc(e.title)}</span>`;
    });
  }
  if (a.stage_trace && a.stage_trace.length) {
    const labels = { triage: "① 分诊", retrieve: "② 检索", compose: "③ 精编", verify: "④ 引用校验", audit: "⑤ 合规复核" };
    const aud = a.audit || {}, ver = a.verification || {};
    html += `<details class="stage-trace"><summary>专家团编排轨迹 · ${a.stage_trace.length} 阶段 · 置信度 ${esc(String(a.confidence ?? "—"))} · 复核：${esc(aud.verdict || "—")}</summary><div class="stage-body">`;
    a.stage_trace.forEach(s => {
      let d = "";
      if (s.stage === "triage") d = `${s.role_label || s.role}｜风险 ${s.risk}`;
      else if (s.stage === "retrieve") d = `${s.mode}｜置信度 ${s.confidence}｜命中 ${(s.top_ids || []).slice(0, 5).join("、") || "无"}${s.abstain ? "｜触发弃答" : ""}`;
      else if (s.stage === "compose") d = `${s.owner}｜引用 ${s.ref_count} 条`;
      else if (s.stage === "verify") d = `校验 ${s.checked} 个引用｜法规名 ${s.law_refs}｜条号 ${s.article_refs}｜${s.ok ? "通过" : "有提示"}`;
      else if (s.stage === "audit") d = `${s.auditor || "赵审计"}｜裁定 ${s.verdict}`;
      html += `<div class="stage-row"><b>${esc(labels[s.stage] || s.stage)}</b><span>${esc(d)}</span></div>`;
    });
    if (ver.warnings && ver.warnings.length) {
      html += `<div class="stage-warn">${ver.warnings.map(w => `<div>· ${esc(w)}</div>`).join("")}</div>`;
    }
    html += `</div></details>`;
  }
  if (disclaimer) html += `<div class="disclaimer">${esc(disclaimer)}</div>`;
  container.innerHTML = html;
  bindRefs(container);
}
function bindRefs(root) {
  root.querySelectorAll(".ref-chip").forEach(ch => ch.addEventListener("click", () => openDetail(ch.dataset.ref)));
}

/* LLM 答案（含流式容器） */
function renderLLMAnswer(p, container) {
  let html = "";
  if (p.fallbackNotice) html += `<div class="llm-fallback-notice">${esc(p.fallbackNotice)}</div>`;
  if (p.reasoning) html += `<details class="reasoning-box"><summary>思考过程（点击展开）</summary><div class="reasoning-text">${esc(p.reasoning.slice(-1500))}</div></details>`;
  if (p.stopped) html += `<div class="hint-block">已手动停止生成，以上为已输出内容。</div>`;
  html += `<div class="md-out llm-stream">${p.content ? renderLLMText(p.content, false) : `<span class="typing"><i></i><i></i><i></i></span>`}</div>`;
  html += `<div class="llm-extra"></div>`;
  container.innerHTML = html;
  const extra = container.querySelector(".llm-extra");
  let e = "";
  if (p.refs && p.refs.length) {
    e += `<div class="sec-title">知识库条目</div>`;
    p.refs.forEach(rid => {
      const ent = S.kbIndex[rid];
      if (ent) e += `<span class="ref-chip" data-ref="${esc(rid)}">${esc(ent.no || "")} ${esc(ent.title)}</span>`;
    });
  }
  if (p.risk === "high") e += `<div class="sec-escalate">🔴 本问题涉及高风险事项，请转介执业税务师 / 律师处理；本应用输出仅供参考。</div>`;
  if (p.disclaimer) e += `<div class="disclaimer">${esc(p.disclaimer)}</div>`;
  extra.innerHTML = e;
  bindRefs(container);
}

/* 轻量 Markdown（LLM 输出） */
function renderLLMText(text, streaming) {
  const lines = String(text || "").split("\n");
  let html = "", listOpen = false;
  const closeList = () => { if (listOpen) { html += "</ul>"; listOpen = false; } };
  lines.forEach((raw, i) => {
    const line = raw.replace(/&nbsp;/g, " ").trimEnd();
    if (/^\s*[-*]\s+/.test(line) || /^\s*\d+[.)、]\s+/.test(line)) {
      if (!listOpen) { html += "<ul>"; listOpen = true; }
      html += `<li>${inlineMD(line.replace(/^\s*(?:[-*]|\d+[.)、])\s+/, ""))}</li>`;
      return;
    }
    closeList();
    if (/^#{1,4}\s+/.test(line)) {
      const lv = (line.match(/^#+/) || ["#"])[0].length;
      const t = line.replace(/^#{1,4}\s+/, "");
      html += `<h${lv <= 2 ? 3 : 4}>${inlineMD(t)}</h${lv <= 2 ? 3 : 4}>`;
    } else if (/^>\s?/.test(line)) html += `<div class="md-quote">${inlineMD(line.replace(/^>\s?/, ""))}</div>`;
    else if (/^---+$/.test(line.trim())) html += `<hr class="md-hr">`;
    else if (line.trim() === "") html += "";
    else html += `<div class="md-line">${inlineMD(line)}</div>`;
  });
  closeList();
  if (streaming) html += `<span class="cursor"></span>`;
  return html;
}
function inlineMD(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

/* 迷你 Markdown（法规原文） */
function renderMD(md) {
  if (!md) return "";
  const lines = String(md).split("\n");
  let html = "", rows = [], inTable = false;
  const flush = () => {
    if (!rows.length) { inTable = false; return; }
    html += "<table>";
    rows.forEach((row, ri) => {
      const cells = row.split("|").slice(1, -1).map(c => c.trim());
      if (cells.every(c => /^:?-{2,}:?$/.test(c) || c === "")) return;
      const tag = ri === 0 ? "th" : "td";
      html += "<tr>" + cells.map(c => `<${tag}>${inlineMD(c)}</${tag}>`).join("") + "</tr>";
    });
    html += "</table>"; rows = []; inTable = false;
  };
  lines.forEach(raw => {
    const line = raw.replace(/\s+$/, "");
    if (line.trim().startsWith("|")) { inTable = true; rows.push(line.trim()); return; }
    if (inTable) flush();
    if (/^###\s+/.test(line)) html += `<h4>${inlineMD(line.replace(/^###\s+/, ""))}</h4>`;
    else if (/^##\s+/.test(line)) html += `<h3>${inlineMD(line.replace(/^##\s+/, ""))}</h3>`;
    else if (/^#\s+/.test(line)) html += `<h3>${inlineMD(line.replace(/^#\s+/, ""))}</h3>`;
    else if (/^>\s?/.test(line)) html += `<blockquote>${inlineMD(line.replace(/^>\s?/, ""))}</blockquote>`;
    else if (/^[-*]\s+/.test(line)) html += `<div style="margin:2px 0 2px 14px">• ${inlineMD(line.replace(/^[-*]\s+/, ""))}</div>`;
    else if (/^---+$/.test(line.trim())) html += "<hr>";
    else if (line.trim() !== "") html += `<div>${inlineMD(line)}</div>`;
  });
  if (inTable) flush();
  return html;
}

/* ---------------- 问答主流程 ---------------- */
/* 意图对齐：缺关键要素的问题走本地澄清通道（与后端 analyze_intent 同规则镜像） */
function isVagueQuestion(q) {
  const text = String(q || "").trim();
  if (!text || text.length > 60) return false;
  const SPECIFIC = /增值税|企业所得税|个人所得税|个税|印花税|契税|消费|社保|公积金|残保|发票|年终奖|工资|小微|小规模|一般纳税人|个体|汇算|申报|退税|滞纳金|复议|注销/;
  const VAGUE = /^(怎么|如何|怎样|咋)(缴|交|报|弄|搞|做|办)|^(有什么|有哪些)(优惠|政策|补贴|好处)|^(要交多少|多少钱|合规吗|合法吗|怎么办|注意什么|需要注意什么)|^(我是|我是做).{0,8}(要交|怎么交|有什么)|^交(什么|哪些)税$/;
  if (text.length <= 24 && !SPECIFIC.test(text) && VAGUE.test(text)) return true;
  const ENTITY = /小规模|一般纳税人|小微企业|小型微利|个体工商户|个体户|个人独资|合伙企业|灵活就业|自由职业|员工|个人(?!所得税)/;
  const COMPUTE = /要交多少|缴多少|交多少|怎么算|怎么缴|怎么交|税率(是)?多少|按多少|应纳税额|税负/;
  const TAX = /增值税|企业所得税|个人所得税|个税|印花税|契税|消费税|附加税|社保|公积金|残保|发票|年终奖|工资|经营所得/;
  const INCENTIVE = /优惠|减免|补贴|退税|加计|免征|减征|即征即退/;
  const REGION = /广东|广州|深圳|大湾区|横琴|前海|南沙|全国|北京|上海|浙江|江苏/;
  const GATE_A = /需要什么|需要哪些|什么条件|什么材料|什么证书|什么手续|哪些条件|哪些资料/;
  const GATE_B = /首套|二套|买房|购房|房贷|房租|工资|月薪|年薪|年终奖|劳务报酬|离职|跳槽|公积金贷款/;
  if (text.length <= 30 && COMPUTE.test(text) && TAX.test(text) && !ENTITY.test(text) && !GATE_A.test(text) && !GATE_B.test(text)) return true;
  if (text.length <= 30 && INCENTIVE.test(text) && TAX.test(text) && !REGION.test(text)) return true;
  return false;
}

/* P0 红线：计算类问题只走本地确定性引擎，禁止 LLM 出数值 */
function isCalcQuestion(q) {
  const INTENTS = [
    /(小规模|月销售额|季度销售额|起征点|10\s*万|30\s*万).{0,12}(增值税|税|缴|交|免)/,
    /(一般纳税人|销项|进项|留抵).{0,12}(增值税|税|缴|交|抵)/,
    /(简易计税|征收率|差额征税).{0,12}(税|计算|缴)/,
    /(城建|城市维护建设|教育费附加|地方教育|附加税|两费)/,
    /(年终奖|全年一次性奖金|一次性奖金)/,
    /(工资|月薪|个税|个人所得税|预扣|专项附加).{0,16}(多少|缴|交|算|预扣)/,
    /(经营所得|个体户|个体工商户|个人独资).{0,12}(个税|所得税|税)/,
    /(企业所得税|季度预缴|汇算|小微|小型微利).{0,14}(多少|缴|交|算|预缴|税率)/,
    /(扣除比例|扣除限额|职工教育经费|广宣费|广告费|业务招待费|捐赠|福利费|工会经费)/,
    /(印花税|应税凭证|税目)/, /(契税|首套|二套|购房)/,
  ];
  const hasAmount = /\d[\d,]*(?:\.\d+)?\s*(?:亿|万|万元|亿元|元)/.test(q);
  const hasVerb = /(多少|怎么算|怎么缴|算一下|计算|应缴|应纳|要交|要缴|缴多少|交多少)/.test(q);
  const hasTax = /(增值税|个税|个人所得税|企业所得税|印花税|契税|城建|教育费附加|附加税|年终奖)/.test(q);
  return hasAmount && (hasVerb || hasTax);
}
async function ask(q, opts = {}) {
  q = String(q || "").trim();
  if (!q) return;
  if (S.busy) { toast("正在生成回答，请稍候或点击「停止」", "warn"); return; }
  S.busy = true;
  setBusy(true);
  if (!opts.reuse) {
    pushMessage({ role: "user", text: q });
    $("#chat-input").value = ""; autoGrow(); updateCount();
  }
  S.lastAnswerFor = q;
  scrollChat(true);
  try {
    const mode = (window.UX && window.UX.mode) || opts.mode || "standard";
    if (isCalcQuestion(q) || isVagueQuestion(q)) await sendLocal(q, { mode });  /* 计算/模糊意图强制本地 */
    else if (S.cloud.ready && S.cloud.current) await sendViaCloud(q, { mode });
    else await sendLocal(q, { mode });
  } catch (err) {
    pushError("请求失败：" + (err && err.message ? err.message : String(err)));
  } finally {
    S.busy = false; setBusy(false);
    $("#chat-input").focus();
  }
}
function setBusy(on) {
  const btn = $("#chat-send");
  btn.disabled = on;
  btn.classList.toggle("is-loading", on);
  btn.hidden = on;              /* 生成中隐藏「发送」，红色「停止」接管 */
  $("#chat-stop").hidden = !on;
  if (window.UX && window.UX.setProgress) window.UX.setProgress(on, window.UX.mode || "standard");
}
function structuredToText(a) {
  let t = "";
  (a.sections || []).forEach(s => {
    if (s.type === "conclusion") t += s.text + "\n";
    else if (s.type === "retrieval" && s.items) t += s.items.map(i => i.title).join("；");
  });
  return t.slice(0, 800);
}
function pushHistory(q, a) {
  S.history.push({ role: "user", content: q }, { role: "assistant", content: a });
  if (S.history.length > 8) S.history = S.history.slice(-8);
}
function regenerate(mid) {
  if (S.busy) { toast("请等待当前回答完成", "warn"); return; }
  const s = currentSession(); if (!s) return;
  const idx = s.messages.findIndex(m => m.id === mid);
  if (idx < 0) return;
  let q = "";
  for (let i = idx - 1; i >= 0; i--) if (s.messages[i].role === "user") { q = s.messages[i].text; break; }
  if (!q) return;
  s.messages = s.messages.slice(0, idx);
  S.history = []; saveSessions(); renderSessions(); renderChat();
  ask(q, { reuse: true });
  toast("正在重新生成回答");
}

/* 路径 A：本地检索（云端不可用或失败兜底） */
async function sendLocal(q, opts = {}) {
  try {
    const resp = await fetch("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q, mode: opts.mode || "standard" }),
    });
    const data = await resp.json();
    if (data.error) { pushError("出错了：" + data.error); return; }
    // 修复 v1 缺陷：直接把结构化消息加入会话并渲染，不再操作已移除的临时节点
    pushMessage({
      role: "assistant",
      payload: { kind: "structured", answer: data.answer, disclaimer: data.disclaimer,
        role: data.answer.role, routed: data.answer.routed, risk: data.answer.risk,
        mode: data.answer.mode === "calc" ? "确定性计算引擎"
             : data.answer.mode === "clarify" ? "意图澄清"
             : data.answer.mode === "rule" ? "精编答案库" : "知识库检索" },
    });
    if (window.UX) window.UX.decorateLastMessage({
      q, deep: data.answer.deep, refs: data.answer.refs, answer: data.answer, mode: "local",
    });
    pushHistory(q, structuredToText(data.answer));
    scrollChat();
  } catch (err) {
    pushError("本地检索失败：" + err.message);
  }
}

/* 路径 B：云端 LLM 流式（HY4 等） */
async function sendViaCloud(q, opts = {}) {
  const mode = opts.mode || "standard";
  let ctx;
  try {
    const resp = await fetch("/api/llm-context?q=" + encodeURIComponent(q) + "&mode=" + encodeURIComponent(mode));
    ctx = await resp.json();
    if (ctx.error) throw new Error(ctx.error);
  } catch (err) {
    toast("获取知识库上下文失败，已转本地检索", "warn");
    await sendLocal(q, { mode }); return;
  }
  const deep = ctx.deep || null;

  if (!S.conversationId) S.conversationId = uid("taxagent");
  const payload = {
    kind: "llm", content: "", reasoning: "", refs: ctx.refs || [], risk: ctx.risk,
    role: ctx.role, routed: ctx.routed, mode: "云端大模型 · " + currentModelLabel(),
    disclaimer: ctx.disclaimer || "",
  };
  const msg = { role: "assistant", payload };
  const wrap = pushMessage(msg);
  const body = wrap.querySelector(".msg-body");
  const streamEl = body.querySelector(".llm-stream");
  const reBox = () => body.querySelector(".reasoning-box");
  let content = "", reasoning = "";

  const controller = new AbortController();
  S.abort = controller;
  scrollChat(true);

  let ok = true, errMsg = "", usedModel = S.cloud.current;
  const messages = [
    { role: "system", content: ctx.system_prompt },
    ...S.history,
    { role: "user", content: q },
  ];
  /* 限流自动换模型：优先另一个免费档，其次最低价模型，仅重试一次 */
  const candidates = [S.cloud.current];
  const altFree = S.cloud.models.find(m => m.id !== S.cloud.current && m._rate === 0);
  const altCheap = S.cloud.models.find(m => m.id !== S.cloud.current && m._rate != null && m._rate <= 0.15);
  if (altFree) candidates.push(altFree.id);
  else if (altCheap) candidates.push(altCheap.id);

  try {
    for (let attempt = 0; attempt < candidates.length; attempt++) {
      usedModel = candidates[attempt];
      try {
        const stream = await S.cloud.client.llm.chat.completions.create({
          model: usedModel, messages, stream: true, temperature: 0.4, signal: controller.signal,
        });
        for await (const chunk of stream) {
          const d = chunk.choices && chunk.choices[0] ? chunk.choices[0].delta : null;
          if (d && d.content) {
            content += d.content;
            if (S.settings.stream) {
              streamEl._text = content;
              if (!streamEl._raf) streamEl._raf = requestAnimationFrame(() => {
                streamEl._raf = null;
                streamEl.innerHTML = renderLLMText(streamEl._text, true);
                scrollChat();
              });
            }
          }
          if (d && d.reasoning_content) {
            reasoning += d.reasoning_content;
            let box = reBox();
            if (!box) {
              body.insertAdjacentHTML("afterbegin", `<details class="reasoning-box"><summary>思考过程（点击展开）</summary><div class="reasoning-text"></div></details>`);
              box = reBox();
            }
            box.querySelector(".reasoning-text").textContent = reasoning.slice(-1500);
          }
        }
        ok = true;
        break;
      } catch (err) {
        errMsg = (err && err.error && err.error.code) ? err.error.code : (err && err.message) || String(err);
        const retryable = /429|rate|limit|quota|too many/i.test(errMsg) || /限流|配额/.test(errMsg);
        if (retryable && attempt < candidates.length - 1 && !controller.signal.aborted) {
          content = ""; reasoning = "";
          if (streamEl) streamEl.innerHTML = "";
          const nextName = modelName(candidates[attempt + 1]);
          toast("当前模型限流，已自动切换 " + nextName + " 重试", "warn", 3200);
          continue;
        }
        ok = false;
        break;
      }
    }
  } finally {
    S.abort = null;
    if (streamEl && streamEl._raf) { cancelAnimationFrame(streamEl._raf); streamEl._raf = null; }
  }
  payload.mode = "云端大模型 · " + modelName(usedModel);

  const aborted = controller.signal.aborted;
  if (aborted) {
    // 用户主动停止：保留已输出内容，不强塞兜底答案
    if (content.trim()) {
      payload.content = content; payload.reasoning = reasoning; payload.stopped = true;
      renderLLMAnswer(payload, body); pushHistory(q, content.slice(0, 1200));
      if (window.UX) window.UX.decorateLastMessage({
        q, deep, refs: ctx.refs || [], mode: "cloud", stopped: true,
      });
      saveSessions(); toast("已停止生成，保留已输出内容", "warn");
    } else {
      const s = currentSession();
      s.messages = s.messages.filter(m => m.id !== msg.id);
      saveSessions(); renderChat(); toast("已停止生成");
    }
    scrollChat(); return;
  }

  if (ok && content.trim()) {
    payload.content = content; payload.reasoning = reasoning;
    renderLLMAnswer(payload, body);
    pushHistory(q, content.slice(0, 1200));
    /* 可信度事后溯源：数字/文号/条号逐项对照知识库，疑似幻觉即时标注 */
    (async () => {
      try {
        const resp = await fetch("/api/trust-check", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ q, text: content, refs: ctx.refs || [] }),
        });
        const tr = await resp.json();
        if (!tr || tr.error) return;
        payload.trust = tr;
        const label = tr.gate === "block" ? "🛑 溯源硬闸"
          : tr.gate === "warn" ? "⚠️ 溯源提示" : "✅ 溯源通过";
        const detail = tr.grounding
          ? `数字/文号溯源 ${Math.round((tr.grounding.coverage || 0) * 100)}%` +
            (tr.ungrounded_claims && tr.ungrounded_claims.length
              ? `，${tr.ungrounded_claims.length} 处未溯源` : "") : "";
        const bar = document.createElement("div");
        bar.className = "trust-bar " + tr.gate;
        bar.innerHTML = `<b>${label}</b><span>${esc(detail)} · 信任分 ${(tr.trust_score ?? 0).toFixed(2)}</span>`;
        body.appendChild(bar);
        if (tr.warnings && tr.warnings.length) {
          const tip = document.createElement("div");
          tip.className = "hint-block trust-warn";
          tip.textContent = tr.warnings.slice(0, 3).join("；");
          body.appendChild(tip);
        }
      } catch (e) { /* 网络失败不阻塞回答展示 */ }
    })();
  } else {
    // 真失败：显示原因 + 回退本地精编答案（同一气泡内）
    payload.fallbackNotice = "⚠️ 云端模型调用失败（" + errText(errMsg) + "），已回退本地知识库答案。";
    const fb = ctx.fallback || {};
    payload.content = "";
    renderLLMAnswer(payload, body);
    const holder = document.createElement("div");
    body.querySelector(".llm-stream").replaceWith(holder);
    renderStructured(Object.assign({ role: ctx.role, routed: ctx.routed, risk: ctx.risk }, fb),
      ctx.fallback_disclaimer || "本地知识库答案，仅供合规参考。", holder);
    pushHistory(q, structuredToText(fb));
    toast("云端不可用，已回退本地答案", "warn");
  }
  if (window.UX) window.UX.decorateLastMessage({
    q, deep, refs: ctx.refs || [], mode: "cloud",
    fallbackNotice: payload.fallbackNotice || null,
  });
  saveSessions(); scrollChat();
}
function errText(code) {
  const map = {
    auth_origin_mismatch: "页面来源未在云端白名单", quota_exceeded: "模型配额已用尽",
    quota_rate_limited: "触发限流，请稍后重试",
  };
  if (map[code]) return map[code];
  if (code && code.startsWith("auth_")) return "云端鉴权未通过（" + code + "）";
  if (code && code.startsWith("quota_")) return "配额受限（" + code + "）";
  if (code && (code.startsWith("gateway_") || code.startsWith("model_"))) return "模型服务暂时不可用（" + code + "）";
  return code || "未知错误";
}
function currentModelLabel() {
  const m = S.cloud.models.find(x => x.id === S.cloud.current);
  return m ? m.name : S.cloud.current;
}
function modelName(id) {
  const m = S.cloud.models.find(x => x.id === id);
  return m ? m.name : id;
}
/* ---- 模型价格分档：云端 credits 字段形如 "x0.00 credits" / "x0.08" ---- */
function modelRate(m) {
  if (!m) return null;
  const hit = String(m.credits || "").match(/x\s*([\d.]+)/i);
  return hit ? parseFloat(hit[1]) : null;
}
function rateText(r) {
  if (r == null) return "—";
  if (r === 0) return "免费";
  return r.toFixed(2) + "x";
}
function rateTier(r) {
  if (r === 0) return "free";
  if (r != null && r <= 0.15) return "cheap";
  if (r != null && r <= 0.6) return "std";
  return "premium";
}
const MODEL_TIERS = [
  ["free", "免费模型 · 0.00x"],
  ["cheap", "低价模型 · ≤0.15x"],
  ["std", "标准 · 0.16–0.60x"],
  ["premium", "旗舰 · >0.60x"],
];
function modelPriceTag(id) {
  const m = S.cloud.models.find(x => x.id === id);
  const r = m ? modelRate(m) : null;
  const t = rateTier(r);
  const cls = t === "free" ? "free" : t === "cheap" ? "cheap" : "";
  return `<span class="model-price ${cls}" id="model-price">${esc(rateText(r))}</span>`;
}

/* ---------------- 云端初始化 ---------------- */
function cloudStatus(text, kind) {
  $("#meta-llm").textContent = text;
  const dot = $("#model-dot");
  dot.className = "model-dot" + (kind === "ok" ? " ok" : kind === "err" ? " err" : "");
  $("#net-dot").className = "pulse-dot" + (kind === "ok" ? " ok" : kind === "err" ? " err" : "");
}
async function initCloud() {
  try {
    if (!window.PUBLIC_CONFIG || !window.WorkBuddyCloud || !window.WorkBuddyCloud.createWorkBuddyCloud) {
      cloudStatus("本地检索模式", "idle"); return;
    }
    const client = window.WorkBuddyCloud.createWorkBuddyCloud({
      endpoint: window.PUBLIC_CONFIG.endpoint,
      publishableKey: window.PUBLIC_CONFIG.publishableKey,
    });
    const models = await client.llm.models.list();
    if (!models || !models.length) { cloudStatus("模型目录为空 · 本地检索", "idle"); return; }
    const list = models
      .filter(m => m.disabled !== true && m.enabled !== false && !NON_CHAT_IDS.has(m.id))
      .map(m => ({ ...m, _rate: modelRate(m) }))
      .sort((a, b) => (a._rate == null ? 9 : a._rate) - (b._rate == null ? 9 : b._rate) ||
        String(a.name).localeCompare(String(b.name)));
    const saved = lsGet("model", "");
    const pick = (id) => list.find(m => m.id === id);
    const preferred = (saved && pick(saved) ? saved : "")
      || (pick(window.CLOUD_PREF_MODEL) ? window.CLOUD_PREF_MODEL : "")
      || (list.find(m => m._rate === 0) || list[0]).id;
    S.cloud.client = client; S.cloud.models = list; S.cloud.current = preferred;
    const sel = $("#model-select");
    sel.innerHTML = MODEL_TIERS.map(([tier, label]) => {
      const group = list.filter(m => rateTier(m._rate) === tier);
      if (!group.length) return "";
      return `<optgroup label="${label}">` + group.map(m => {
        const r = m._rate;
        const tail = r === 0 ? " · 免费" : (r != null ? " · " + r.toFixed(2) + "x" : "");
        return `<option value="${esc(m.id)}">${esc(m.name)}${tail}${m.id === window.CLOUD_PREF_MODEL ? " · 推荐" : ""}</option>`;
      }).join("") + "</optgroup>";
    }).join("");
    sel.value = S.cloud.current;
    const syncPrice = () => {
      const m = list.find(x => x.id === S.cloud.current);
      const r = m ? m._rate : null;
      const el = $("#model-price");
      if (el) {
        el.textContent = rateText(r);
        el.className = "model-price " + (r === 0 ? "free" : r != null && r <= 0.15 ? "cheap" : "");
        el.title = r === 0 ? "当前模型限时免费（0.00x）" : r != null ? "积分倍率 " + r.toFixed(2) + "x" : "";
      }
      cloudStatus((m ? m.name : S.cloud.current) + " · 云端已连接" + (r === 0 ? " · 免费" : r != null ? " · " + r.toFixed(2) + "x" : ""), "ok");
    };
    sel.addEventListener("change", () => {
      S.cloud.current = sel.value;
      lsSet("model", sel.value);
      syncPrice();
      const m = list.find(x => x.id === sel.value);
      toast("已切换模型：" + (m ? m.name : sel.value) + (m && m._rate === 0 ? "（免费）" : m && m._rate != null ? "（" + m._rate.toFixed(2) + "x）" : ""));
    });
    S.cloud.ready = list.length > 0;
    syncPrice();
    renderModelPrices();
  } catch (err) {
    console.warn("cloud init failed:", err);
    cloudStatus("云端未连接 · 本地检索", "err");
    S.cloud.ready = false;
  }
}

/* ---------------- 示例问题分组 ---------------- */
function renderExamples() {
  const groups = (S.examples && S.examples.groups) || [];
  $("#quick-tabs").innerHTML = groups.map(g =>
    `<button class="quick-tab ${g.id === S.quickGroup ? "active" : ""}" data-g="${esc(g.id)}" role="tab" title="${esc(g.desc)}">${esc(g.icon)} ${esc(g.label)}</button>`).join("");
  $$(".quick-tab").forEach(b => b.addEventListener("click", () => {
    S.quickGroup = b.dataset.g; renderExamples();
  }));
  const g = groups.find(x => x.id === S.quickGroup) || groups[0];
  $("#examples").innerHTML = (g ? g.items : []).slice(0, 8).map(it =>
    `<button class="example-chip" data-q="${esc(it.q)}" title="${esc(it.q)}">${esc(it.q)}</button>`).join("");
  $$(".example-chip").forEach(b => b.addEventListener("click", () => ask(b.dataset.q)));
}

/* ---------------- 法规库 ---------------- */
function statusClass(st) {
  if (st === "现行有效") return "st-ok";
  if (st === "修订中" || st === "已废止") return "st-warn";
  if (st === "草案阶段" || st === "施行后") return "st-draft";
  if (st === "汇编·动态") return "st-assembly";
  return "st-unknown";
}
const ENTRY_TYPE_LABEL = { regulation: "单一法规", digest: "汇编", table_row: "速查表行", practice: "实务指引" };
function highlight(text, q) {
  const safe = esc(text);
  if (!q) return safe;
  const needle = esc(q);
  const i = safe.toLowerCase().indexOf(needle.toLowerCase());
  if (i < 0) return safe;
  return safe.slice(0, i) + "<mark>" + safe.slice(i, i + needle.length) + "</mark>" + safe.slice(i + needle.length);
}
function renderKbFilters() {
  const cats = (S.meta && S.meta.categories) || {};
  const total = S.kb ? S.kb.entries.length : 0;
  let html = `<button class="filter-chip ${S.kbView.cat === "all" ? "active" : ""}" data-c="all">全部 <span class="n">${total}</span></button>`;
  Object.keys(cats).forEach(c => {
    html += `<button class="filter-chip ${S.kbView.cat === c ? "active" : ""}" data-c="${esc(c)}">${esc(c.replace(/^全国 · |^广东省 · |^中小企业 · /, ""))} <span class="n">${cats[c]}</span></button>`;
  });
  $("#kb-filters").innerHTML = html;
  $$("#kb-filters .filter-chip").forEach(b => b.addEventListener("click", () => {
    S.kbView.cat = b.dataset.c; renderKbFilters(); renderKbList();
  }));
}
function renderKbList() {
  const box = $("#kb-list");
  const q = S.kbView.q.trim().toLowerCase();
  let entries = S.kb.entries.filter(e => {
    if (S.kbView.cat !== "all" && e.category !== S.kbView.cat) return false;
    if (S.kbView.fav && !S.favorites.has(e.id)) return false;
    if (q && !kbMatches(e, q)) return false;
    return true;
  });
  if (S.kbView.sort === "title") entries = entries.slice().sort((a, b) => a.title.localeCompare(b.title, "zh"));
  if (S.kbView.sort === "status") entries = entries.slice().sort((a, b) => (a.status === "现行有效" ? -1 : 1) - (b.status === "现行有效" ? -1 : 1));
  S.kbView.items = entries;
  $("#kb-count").textContent = `显示 ${entries.length} / ${S.kb.entries.length} 条${S.kbView.fav ? " · 仅收藏" : ""}`;
  if (!entries.length) {
    box.innerHTML = emptyState("没有匹配的法规条目", "试试更换关键词，或清除分类筛选、收藏筛选", "清除全部筛选", "kb-clear-filters");
    const clr = $("#kb-clear-filters");
    if (clr) clr.addEventListener("click", () => {
      S.kbView.cat = "all"; S.kbView.q = ""; S.kbView.fav = false;
      const inp = $("#kb-search"); if (inp) inp.value = "";
      const fav = $("#kb-fav-toggle"); if (fav) fav.setAttribute("aria-pressed", "false");
      renderKbFilters(); renderKbList();
      toast("已清除全部筛选");
    });
    return;
  }
  let lastCat = "", html = "";
  entries.forEach(e => {
    if (e.category !== lastCat) { lastCat = e.category; html += `<div class="kb-cat-title">${esc(e.category)}</div>`; }
    const fav = S.favorites.has(e.id);
    html += `<div class="kb-item ${S.activeDetail === e.id ? "active" : ""}" data-id="${esc(e.id)}" role="option" tabindex="0" aria-selected="${S.activeDetail === e.id}">
      <span class="t"><b>${fav ? "★ " : ""}${highlight(e.title, q)}</b><small>${esc(e.no || "")} ${esc(e.category)}</small></span>
      <span class="st ${statusClass(e.status)}">${esc(e.status)}</span></div>`;
  });
  box.innerHTML = html;
  box.querySelectorAll(".kb-item").forEach(el => {
    el.addEventListener("click", () => openDetail(el.dataset.id));
    el.addEventListener("keydown", ev => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openDetail(el.dataset.id); }
      else if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        const items = $$(".kb-item"); const i = items.indexOf(el);
        const next = items[i + (ev.key === "ArrowDown" ? 1 : -1)];
        if (next) { next.focus(); next.click(); }
      }
    });
  });
}
function fieldOrder(fields) {
  const order = ["文号", "发文机关", "效力层级", "公布/施行", "时效性", "适用范围", "信源", "核验"];
  return Object.keys(fields).sort((a, b) => {
    const ia = order.indexOf(a), ib = order.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
}
function openDetail(id) {
  const e = S.kbIndex[id];
  if (!e) { toast("未找到该法规条目", "warn"); return; }
  S.activeDetail = id;
  switchTab("kb");
  // 从对话引用跳转时，若当前筛选排除了该条目则自动重置，保证一定能看到详情
  if ((S.kbView.cat !== "all" && e.category !== S.kbView.cat) || (S.kbView.fav && !S.favorites.has(id))) {
    S.kbView.cat = "all"; S.kbView.fav = false;
    $("#kb-fav-toggle").setAttribute("aria-pressed", "false");
    renderKbFilters();
  }
  renderKbList();
  const pane = $("#kb-detail");
  pane.classList.remove("empty");
  const fav = S.favorites.has(id);
  const idx = S.kbView.items.findIndex(x => x.id === id);
  const prev = idx > 0 ? S.kbView.items[idx - 1] : null;
  const next = idx >= 0 && idx < S.kbView.items.length - 1 ? S.kbView.items[idx + 1] : null;
  const related = S.kb.entries.filter(x => x.id !== id && x.category === e.category).slice(0, 6);

  let html = `<button class="detail-back" id="detail-back"><svg class="ico"><use href="#i-back"/></svg> 返回列表</button>
    <div class="detail-top"><h2>${esc(e.title)}</h2>
      <div class="detail-actions">
        <button id="detail-fav" class="${fav ? "on" : ""}" title="${fav ? "取消收藏" : "收藏"}"><svg class="ico"><use href="#i-star"/></svg></button>
        <button id="detail-copy" title="复制条目摘要"><svg class="ico"><use href="#i-copy"/></svg></button>
      </div></div>
    <div class="detail-sub"><span class="detail-crumb">${esc(e.category)}</span><span>›</span><span>${esc(e.no || e.id)}</span>
      <span class="st ${statusClass(e.status)}">${esc(e.status)}</span>
      <span class="tier ${e.tier === "A" ? "tier-a" : "tier-b"}" title="${e.tier === "A" ? "10 项元数据齐备且至少两个官方信源" : (e.tier === "B1" ? "元数据齐备但仅单一信源" : (e.entry_type === "regulation" ? "法规型条目存在元数据缺口，作为依据前须回查原文" : "汇编/表格型条目，仅供检索线索"))}">${e.tier === "A" ? "A 生产级 · 双源核验" : (e.tier === "B1" ? "B1 · 单源待复核" : "B2 · 汇编/参考层")}</span>
      ${e.entry_type ? `<span class="etype">${esc(ENTRY_TYPE_LABEL[e.entry_type] || e.entry_type)}</span>` : ""}
      <span>来源 ${esc(e.source_file || "")}</span></div>`;
  if (Object.keys(e.fields).length) {
    html += `<table class="field-table">`;
    fieldOrder(e.fields).forEach(k => {
      const v = String(e.fields[k] || "");
      const flag = /待核验|待复核|已到期|未通过|草案/.test(v) ? " flag" : "";
      html += `<tr><td>${esc(k)}</td><td class="${flag}">${esc(v).replace(/\n/g, "<br>")}</td></tr>`;
    });
    html += `</table>`;
  } else {
    html += `<div class="hint-block">本条目为表格型速查数据，无独立法规字段；可在「优惠速查」页按政策名称与有效期筛选查看。</div>`;
  }
  html += `<div class="md-body">${renderMD(e.body_md)}</div>`;
  if (related.length) html += `<div class="related-box"><b>同分类相关条目</b><div class="related-list">${related.map(r =>
    `<span class="ref-chip" data-ref="${esc(r.id)}">${esc(r.title)}</span>`).join("")}</div></div>`;
  html += `<div class="detail-nav">
    ${prev ? `<button data-go="${esc(prev.id)}"><svg class="ico"><use href="#i-back"/></svg><span>${esc(prev.title)}</span></button>` : `<button disabled><span>已是第一条</span></button>`}
    ${next ? `<button data-go="${esc(next.id)}"><span>${esc(next.title)}</span><svg class="ico" style="transform:rotate(180deg)"><use href="#i-back"/></svg></button>` : `<button disabled><span>已是最后一条</span></button>`}
  </div>`;
  pane.innerHTML = html;
  pane.scrollTop = 0;
  $("#detail-fav").addEventListener("click", () => toggleFav(id));
  $("#detail-copy").addEventListener("click", async () => {
    const text = `${e.title}\n文号：${e.fields["文号"] || e.no || ""}\n发文机关：${e.fields["发文机关"] || ""}\n时效性：${e.status}\n核心条款：${e.fields["核心条款"] || ""}\n合规要点：${e.fields["合规要点"] || ""}`;
    try { await navigator.clipboard.writeText(text); toast("条目摘要已复制"); }
    catch (_) { toast("复制失败，请手动选择文本", "warn"); }
  });
  $("#detail-back").addEventListener("click", () => pane.classList.add("empty"));
  pane.querySelectorAll("[data-go]").forEach(b => b.addEventListener("click", () => openDetail(b.dataset.go)));
  bindRefs(pane);
  if (window.innerWidth <= 720) pane.scrollIntoView({ behavior: "smooth", block: "start" });
}
function toggleFav(id) {
  if (S.favorites.has(id)) S.favorites.delete(id); else S.favorites.add(id);
  lsSet("favorites", Array.from(S.favorites));
  toast(S.favorites.has(id) ? "已加入收藏" : "已取消收藏");
  renderKbList(); openDetail(id);
}

/* ---------------- 优惠速查（结构化） ---------------- */
function classifyExpiry(expiryText, rowText) {
  const t = String(expiryText || "");
  const full = String(rowText || t);
  // 整行扫描：文号「待核验」「凭既有知识」等标注即使不在有效期列，也应保守标为待核验
  if (/已到期|执行期限至\s*2025|⚠/.test(full)) return "expired";
  if (/待核验|待复核|凭既有知识|未见新文件|以当地细则为准/.test(full)) return "unknown";
  if (/至\s*2026|2026-12-31|2026\s*年/.test(t)) return "soon";
  return "ok";
}
function parseIncentiveTables() {
  const out = [];
  S.kb.entries.filter(e => e.file === "06").forEach(e => {
    const lines = String(e.body_md || "").split("\n");
    let rows = [];
    const flush = () => {
      if (rows.length < 2) { rows = []; return; }
      const parse = (r) => r.split("|").slice(1, -1).map(c => c.trim());
      const headers = parse(rows[0]);
      const data = rows.slice(1).filter(r => !parse(r).every(c => /^:?-{2,}:?$/.test(c) || c === ""))
        .map(r => {
          const cells = parse(r);
          const expiryIdx = headers.findIndex(h => /有效期|期限|执行期/.test(h));
          const expiry = expiryIdx >= 0 ? cells[expiryIdx] : "";
          const rowText = cells.join(" ");
          return { cells, expiry, state: classifyExpiry(expiry, rowText), text: rowText };
        });
      if (data.length) out.push({ section: e.title, headers, rows: data });
      rows = [];
    };
    lines.forEach(l => {
      if (l.trim().startsWith("|")) rows.push(l.trim()); else flush();
    });
    flush();
  });
  return out;
}
function renderIncFilters() {
  const defs = [["all", "全部"], ["ok", "现行有效"], ["soon", "临期"], ["expired", "已到期"], ["unknown", "待核验"]];
  $("#inc-filters").innerHTML = defs.map(([v, l]) =>
    `<button class="filter-chip ${S.inc.status === v ? "active" : ""}" data-s="${v}">${l}</button>`).join("");
  $$("#inc-filters .filter-chip").forEach(b => b.addEventListener("click", () => {
    S.inc.status = b.dataset.s; renderIncFilters(); renderIncentives();
  }));
}
function visibleIncRows() {
  const q = S.inc.q.trim().toLowerCase();
  return S.inc.tables.map(t => ({
    section: t.section, headers: t.headers,
    rows: t.rows.filter(r => (S.inc.status === "all" || r.state === S.inc.status) && (!q || r.text.toLowerCase().includes(q))),
  })).filter(t => t.rows.length);
}
function renderIncentives() {
  const all = S.inc.tables.flatMap(t => t.rows);
  const cnt = (s) => all.filter(r => r.state === s).length;
  $("#inc-stats").innerHTML = `
    <div class="inc-stat"><b>${all.length}</b><span>政策条目</span></div>
    <div class="inc-stat"><b>${cnt("ok")}</b><span>现行 / 长期</span></div>
    <div class="inc-stat warn"><b>${cnt("soon") + cnt("unknown")}</b><span>临期 / 待核验</span></div>
    <div class="inc-stat bad"><b>${cnt("expired")}</b><span>已到期</span></div>`;
  const q = S.inc.q.trim();
  const groups = visibleIncRows();
  const box = $("#incentives-body");
  if (!groups.length) { box.innerHTML = emptyState("没有匹配的政策条目", "试试「小微」「加计」「免征」等关键词，或清空搜索框"); return; }
  box.innerHTML = groups.map(t => {
    const expiryIdx = t.headers.findIndex(h => /有效期|期限|执行期/.test(h));
    return `<div class="inc-section">
      <div class="inc-section-head"><h4>${esc(t.section)}</h4><span>${t.rows.length} 条</span></div>
      <div class="inc-table-wrap"><table class="inc-table"><thead><tr>${t.headers.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead>
      <tbody>${t.rows.map(r => `<tr class="${r.state === "expired" ? "row-expired" : ""}">${r.cells.map((c, i) => {
        const cls = i === expiryIdx ? `expiry ${r.state}` : "";
        return `<td class="${cls}">${q ? highlight(c, q) : esc(c)}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table></div>
      <div class="inc-note">⚠️ 标注「已到期」的政策不作为现行依据；「待核验」字段引用前须复核官方原文。</div>
    </div>`;
  }).join("");
}
function exportIncCSV() {
  const groups = visibleIncRows();
  if (!groups.length) { toast("当前没有可导出的条目", "warn"); return; }
  const lines = [["分类", "状态", ...(groups[0].headers || [])].join(",")];
  groups.forEach(t => t.rows.forEach(r => lines.push([t.section, r.state, ...r.cells]
    .map(v => `"${String(v || "").replace(/"/g, '""')}"`).join(","))));
  const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "财税优惠政策速查-" + new Date().toISOString().slice(0, 10) + ".csv";
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  toast("已导出 CSV（含中文 BOM，Excel 可直接打开）");
}

/* ---------------- 关于页 ---------------- */
function renderModelPrices() {
  const box = $("#about-models");
  if (!box) return;
  if (!S.cloud.models.length) {
    box.innerHTML = `<p class="muted small">云端模型目录未连接，当前使用本地精编答案库；连接后此处会列出全部免费与低价模型。</p>`;
    return;
  }
  const picks = S.cloud.models.filter(m => m._rate != null && m._rate <= 0.15).slice(0, 12);
  box.innerHTML = `<div class="model-price-grid">` + picks.map(m => `
      <button class="model-price-item ${m.id === S.cloud.current ? "active" : ""}" data-model="${esc(m.id)}" title="切换为 ${esc(m.name)}">
        <span class="mp-name">${esc(m.name)}</span>
        <span class="model-price ${m._rate === 0 ? "free" : "cheap"}">${esc(rateText(m._rate))}</span>
      </button>`).join("") + `</div>
    <p class="muted small">倍率为云端积分系数，数值越低越省；标注「免费」的为限时活动档，额度或活动期可能变化。点击即切换，选择会保存在本机。</p>`;
  box.querySelectorAll("[data-model]").forEach(btn => btn.addEventListener("click", () => {
    S.cloud.current = btn.dataset.model;
    lsSet("model", S.cloud.current);
    const sel = $("#model-select");
    if (sel) sel.value = S.cloud.current;
    const m = S.cloud.models.find(x => x.id === S.cloud.current);
    const r = m ? m._rate : null;
    const el = $("#model-price");
    if (el) {
      el.textContent = rateText(r);
      el.className = "model-price " + (r === 0 ? "free" : "cheap");
    }
    cloudStatus((m ? m.name : S.cloud.current) + " · 云端已连接 · " + rateText(r), "ok");
    renderModelPrices();
    toast("已切换模型：" + (m ? m.name : S.cloud.current) + "（" + rateText(r) + "）");
  }));
}
function renderAbout() {
  if (!S.meta) return;
  $("#about-entries").textContent = S.meta.entries;
  $("#about-verified").textContent = S.meta.verified_at;
  renderModelPrices();
  $("#about-facts").innerHTML = [
    ["知识库", S.meta.kb_version + " · " + S.meta.files + " 个主题文件"],
    ["法规条目", S.meta.entries + " 条"], ["精编问答", S.meta.rules + " 条"],
    ["核验日期", S.meta.verified_at], ["服务端口", S.meta.port],
  ].map(([k, v]) => `<span class="fact"><b>${esc(v)}</b>${esc(k)}</span>`).join("");
  $("#about-roles").innerHTML = (S.meta.roles || []).map(r =>
    `<div class="role-card"><b>${esc(r.emoji)} ${esc(r.name)}</b><span>${esc(r.desc)}</span></div>`).join("");
  $("#about-keymap").innerHTML = [
    ["Ctrl / ⌘ + K", "全局搜索"], ["1 – 4", "切换页签"], ["/", "聚焦搜索"],
    ["Enter", "发送问题"], ["Shift + Enter", "换行"], ["Esc", "关闭浮层"],
  ].map(([k, v]) => `<span><kbd>${esc(k)}</kbd> ${esc(v)}</span>`).join("");
}

/* ---------------- 命令面板 ---------------- */
let CMD_ITEMS = [], CMD_SEL = 0;
function openCmd() {
  $("#cmd-overlay").hidden = false;
  $("#cmd-input").value = "";
  $("#cmd-input").focus();
  renderCmd("");
}
function closeOverlays() {
  $("#cmd-overlay").hidden = true;
  $("#settings-overlay").hidden = true;
}
function renderCmd(q) {
  const query = q.trim().toLowerCase();
  const items = [];
  // 功能跳转
  Object.keys(TAB_META).forEach(t => {
    if (!query || TAB_META[t][0].includes(query) || t.includes(query) || "跳转".includes(query))
      items.push({ type: "tab", icon: "i-route", title: "前往「" + TAB_META[t][0] + "」", tag: "功能", val: t });
  });
  if (!query) items.push({ type: "new", icon: "i-plus", title: "新建对话", tag: "功能", val: "" });
  // 示例问题
  ((S.examples && S.examples.groups) || []).forEach(g => g.items.forEach(it => {
    if (!query || it.q.toLowerCase().includes(query)) items.push({ type: "ask", icon: "i-chat", title: it.q, tag: g.label, val: it.q });
  }));
  // 法规条目
  if (query) S.kb.entries.forEach(e => {
    if (kbMatches(e, query))
      items.push({ type: "kb", icon: "i-book", title: e.title, tag: e.category, val: e.id });
  });
  // 会话
  S.sessions.filter(s => s.messages.length).forEach(s => {
    if (!query || s.title.toLowerCase().includes(query)) items.push({ type: "session", icon: "i-chat", title: s.title, tag: "会话", val: s.id });
  });

  CMD_ITEMS = items.slice(0, 24); CMD_SEL = 0;
  const box = $("#cmd-results");
  if (!CMD_ITEMS.length) {
    box.innerHTML = `<div class="cmd-empty"><svg class="ico" style="width:26px;height:26px;stroke-width:1.4;opacity:.5"><use href="#i-search"/></svg><b>没有找到匹配项</b><span>试试法规名称（如「征管法」）、文号（如「512 号令」）或问题关键词</span></div>`;
    return;
  }
  let html = "", last = "";
  CMD_ITEMS.forEach((it, i) => {
    if (it.tag !== last && !query) { last = it.tag; html += `<div class="cmd-group-label">${esc(it.tag)}</div>`; }
    html += `<button class="cmd-item ${i === 0 ? "sel" : ""}" data-i="${i}" role="option">
      <svg class="ico"><use href="#${it.icon}"/></svg><span class="cmd-main">${esc(it.title)}</span>
      <span class="cmd-tag">${esc(it.tag)}</span></button>`;
  });
  box.innerHTML = html;
  box.querySelectorAll(".cmd-item").forEach(b => b.addEventListener("click", () => { cmdPick(Number(b.dataset.i)); }));
}
function cmdMove(d) {
  if (!CMD_ITEMS.length) return;
  CMD_SEL = (CMD_SEL + d + CMD_ITEMS.length) % CMD_ITEMS.length;
  $$(".cmd-item").forEach((b, i) => b.classList.toggle("sel", i === CMD_SEL));
  const sel = $$(".cmd-item")[CMD_SEL];
  if (sel) sel.scrollIntoView({ block: "nearest" });
}
function cmdPick(i) {
  const it = CMD_ITEMS[i == null ? CMD_SEL : i];
  if (!it) return;
  closeOverlays();
  if (it.type === "tab") switchTab(it.val);
  else if (it.type === "ask") { switchTab("chat"); setTimeout(() => ask(it.val), 60); }
  else if (it.type === "kb") openDetail(it.val);
  else if (it.type === "session") loadSession(it.val);
  else if (it.type === "new") { switchTab("chat"); newSession(); }
}

/* ---------------- 输入框 ---------------- */
function autoGrow() {
  const ta = $("#chat-input");
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
}
function updateCount() {
  const n = $("#chat-input").value.length;
  $("#char-count").textContent = n ? `${n} / 2000` : "";
  $("#char-count").style.color = n > 2000 ? "var(--risk-high)" : "";
}

/* ---------------- 事件绑定 ---------------- */
function bindEvents() {
  $$(".nav-item, .mobile-nav-item").forEach(b => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  $("#new-chat").addEventListener("click", () => { switchTab("chat"); newSession(); });
  $("#mobile-new-chat").addEventListener("click", () => { switchTab("chat"); newSession(); });
  $("#chat-clear").addEventListener("click", clearSession);
  $("#theme-quick").addEventListener("click", () => {
    // 快捷按钮始终产生可见变化：在浅/深之间直接切换；「跟随系统」在设置面板中选择
    setTheme(effectiveDark() ? "light" : "dark");
  });

  // 输入
  $("#chat-send").addEventListener("click", () => ask($("#chat-input").value));
  $("#chat-input").addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask($("#chat-input").value); }
  });
  $("#chat-input").addEventListener("input", () => { autoGrow(); updateCount(); });
  $("#chat-stop").addEventListener("click", () => { if (S.abort) S.abort.abort(); });
  $("#chat-scroll").addEventListener("scroll", () => {
    const sc = $("#chat-scroll");
    S.stick = sc.scrollHeight - sc.scrollTop - sc.clientHeight < 80;
    updateScrollBtn();
  });
  $("#scroll-bottom").addEventListener("click", () => { S.stick = true; scrollChat(true); });

  // 法规库
  const kbSearch = debounce(v => { S.kbView.q = v; renderKbList(); }, 160);
  $("#kb-search").addEventListener("input", e => {
    $("#kb-search-clear").hidden = !e.target.value;
    kbSearch(e.target.value);
  });
  $("#kb-search-clear").addEventListener("click", () => {
    $("#kb-search").value = ""; $("#kb-search-clear").hidden = true; S.kbView.q = ""; renderKbList(); $("#kb-search").focus();
  });
  $("#kb-sort").addEventListener("change", e => { S.kbView.sort = e.target.value; renderKbList(); });
  $("#kb-fav-toggle").addEventListener("click", e => {
    S.kbView.fav = !S.kbView.fav;
    e.currentTarget.setAttribute("aria-pressed", S.kbView.fav ? "true" : "false");
    renderKbList();
  });

  // 优惠速查
  const incSearch = debounce(v => { S.inc.q = v; renderIncentives(); }, 160);
  $("#inc-search").addEventListener("input", e => {
    $("#inc-search-clear").hidden = !e.target.value; incSearch(e.target.value);
  });
  $("#inc-search-clear").addEventListener("click", () => {
    $("#inc-search").value = ""; $("#inc-search-clear").hidden = true; S.inc.q = ""; renderIncentives();
  });
  $("#inc-export").addEventListener("click", exportIncCSV);

  // 浮层
  $("#cmd-trigger").addEventListener("click", openCmd);
  $("#cmd-close").addEventListener("click", closeOverlays);
  $("#cmd-overlay").addEventListener("click", e => { if (e.target.id === "cmd-overlay") closeOverlays(); });
  $("#settings-trigger").addEventListener("click", () => { $("#settings-overlay").hidden = false; });
  $("#settings-close").addEventListener("click", closeOverlays);
  $("#settings-overlay").addEventListener("click", e => { if (e.target.id === "settings-overlay") closeOverlays(); });
  $("#cmd-input").addEventListener("input", e => renderCmd(e.target.value));
  $("#cmd-input").addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); cmdMove(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); cmdMove(-1); }
    else if (e.key === "Enter") { e.preventDefault(); cmdPick(); }
    else if (e.key === "Escape") closeOverlays();
  });
  $$("#theme-seg button").forEach(b => b.addEventListener("click", () => setTheme(b.dataset.val)));
  $$("#font-seg button").forEach(b => b.addEventListener("click", () => {
    S.settings.fontsize = b.dataset.val; applySettings();
  }));
  $("#opt-stream").addEventListener("change", e => { S.settings.stream = e.target.checked; applySettings(); });
  $("#opt-autoscroll").addEventListener("change", e => { S.settings.autoscroll = e.target.checked; applySettings(); });

  // 全局快捷键
  document.addEventListener("keydown", e => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openCmd(); return; }
    if (e.key === "Escape") { closeOverlays(); return; }
    if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
    if (["1", "2", "3", "4", "5"].includes(e.key)) { e.preventDefault(); switchTab(["chat", "kb", "incentives", "about", "business"][Number(e.key) - 1]); }
    else if (e.key === "/") {
      e.preventDefault();
      const target = S.tab === "kb" ? $("#kb-search") : S.tab === "incentives" ? $("#inc-search")
        : S.tab === "business" ? $("#bc-search") : $("#chat-input");
      target.focus();
    }
  });

  // 网络状态
  window.addEventListener("offline", () => toast("网络已断开，云端模型可能不可用", "warn", 4000));
  window.addEventListener("online", () => toast("网络已恢复"));
  window.addEventListener("resize", () => { updateScrollBtn(); });
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => {
      if (S.settings.theme === "system") applySettings();
    });
  }
  $("#fatal-retry").addEventListener("click", () => location.reload());
}

/* ---------------- 致命错误 ---------------- */
function showFatal(err) {
  $("#fatal-msg").textContent = "无法加载知识库数据：" + (err && err.message ? err.message : String(err)) + "。请确认 server.py 已在端口 8777 启动。";
  $("#fatal").hidden = false;
}

/* ---------------- 启动 ---------------- */
async function init() {
  loadLocal();
  bindEvents();
  applySettings();
  try {
    const [meta, examples, kb] = await Promise.all([
      fetch("/api/meta").then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }),
      fetch("/api/examples").then(r => r.json()),
      fetch("/api/kb").then(r => r.json()),
    ]);
    S.meta = meta; S.examples = examples; S.kb = kb;
    S.kbIndex = {}; kb.entries.forEach(e => { S.kbIndex[e.id] = e; e._blob = kbBlob(e); });
    $("#kb-summary").textContent = `知识库 ${meta.kb_version} · ${meta.entries} 条法规 · ${meta.rules} 条精编问答`;
    $("#view-sub").textContent = TAB_META.chat[1];
    renderExamples(); renderKbFilters(); renderKbList();
    S.inc.tables = parseIncentiveTables(); renderIncFilters(); renderIncentives();
    renderAbout(); renderSessions(); renderChat();
    showKbDetailEmpty();
  } catch (err) {
    console.error("init failed:", err);
    showFatal(err); return;
  }
  initCloud();
}
function showKbDetailEmpty() {
  $("#kb-detail").classList.add("empty");
  $("#kb-detail").innerHTML = `<div class="detail-empty">
    <svg class="ico"><use href="#i-book"/></svg><b>选择一份法规查看完整详情</b>
    <span>左侧可按分类筛选、搜索名称或文号；点击条目后展示字段表、原文条款与同分类相关条目。</span></div>`;
}

init();
