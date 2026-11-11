/* business.js — 业务事项结构化指引视图（v13.1）
   独立模块：只依赖 /api/business-cases，不改动 app.js 的主状态。
   列表模式（q 为空）列出全部 30 条；搜索模式按相关度返回；详情渲染 11 字段。 */
(function () {
  "use strict";
  var $ = (s) => document.querySelector(s);
  var $$ = (s) => Array.from(document.querySelectorAll(s));
  var esc = (v) => String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  var linkify = (v) => esc(v).replace(/https?:\/\/[^\s<）)】]+/g,
    (u) => '<a href="' + u + '" target="_blank" rel="noopener noreferrer">' + u + "</a>");

  /* 依据名称 → 法规库检索；URL 保持外链 */
  function lawLinkify(v) {
    var s = esc(v || "");
    s = s.replace(/https?:\/\/[^\s<）)】"]+/g, (u) =>
      '<a href="' + u + '" target="_blank" rel="noopener noreferrer">' + u + "</a>");
    s = s.replace(/《([^》]+)》/g, (m, name) =>
      '<a href="#" class="bc-law-link" data-law="' + name +
      '" title="在法规库中检索该依据">《' + name + "》</a>");
    return s;
  }

  function csvCell(v) {
    var s = String(v == null ? "" : v).replace(/\r?\n/g, " ");
    return '"' + s.replace(/"/g, '""') + '"';
  }

  function flashBtn(msg) {
    var b = $("#bc-export");
    if (!b) return;
    var old = b.textContent;
    b.textContent = msg;
    b.disabled = true;
    setTimeout(() => { b.textContent = old; b.disabled = false; }, 1400);
  }

  function exportCsv() {
    var items = visible();
    if (!items.length) { flashBtn("无可导出条目"); return; }
    var head = ["编号", "条目ID", "标题", "分类", "层级", "生效状态"].concat(FIELDS);
    var lines = [head.map(csvCell).join(",")];
    items.forEach((x) => {
      var f = x.fields || {};
      var row = [x.no || "", x.id || "", x.title || "", shortCat(x.category),
                 x.tier || "", x.status || ""].concat(FIELDS.map((k) => f[k] || ""));
      lines.push(row.map(csvCell).join(","));
    });
    var d = new Date();
    var stamp = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") +
                "-" + String(d.getDate()).padStart(2, "0");
    var blob = new Blob(["\uFEFF" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "business-cases-" + stamp + ".csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    flashBtn("已导出 " + items.length + " 条");
  }

  /* ③ 依据名称 → 精确法源条目；解析不到时明提示并回退关键词检索 */
  var LAW_INDEX = null;

  function normLaw(s) {
    return String(s || "")
      .replace(/[《》〈〉\s]/g, "")
      .replace(/^中华人民共和国/, "")
      .replace(/（[^）]*）|\([^)]*\)/g, "")
      .replace(/[—－·・,，。;；:：\-]/g, "")
      .toLowerCase();
  }

  async function lawIndex() {
    if (LAW_INDEX) return LAW_INDEX;
    try {
      var d = await fetch("/api/kb", { cache: "force-cache" }).then((r) => r.json());
      LAW_INDEX = Array.isArray(d.entries) ? d.entries : [];
    } catch (e) { LAW_INDEX = []; }
    return LAW_INDEX;
  }

  async function resolveLawId(name) {
    var raw = String(name || "").trim();
    var key = normLaw(raw);
    if (!key) return null;
    var es = await lawIndex();
    if (!es.length) return null;
    /* 准则类条目以「CAS N」命名（如 38-38.3），先按第N号命中 */
    if (/企业会计准则/.test(raw)) {
      var m = raw.match(/第\s*(\d+)\s*号/);
      if (m) {
        var re = new RegExp("CAS\\s*0*" + m[1] + "(?!\\d)", "i");
        var c = es.find((x) => re.test(String(x.title || "") + " " + String(x.heading || "")));
        if (c) return c.id;
      }
    }
    var best = null, bestScore = 0;
    es.forEach((e) => {
      var t = normLaw(e.title || "");
      var h = normLaw(e.heading || "");
      var dn = normLaw(e.doc_no || "");
      var sc = 0;
      if (t && t === key) sc = 100;
      else if (dn && dn === key) sc = 95;
      else if (t && key && (t.indexOf(key) === 0 || key.indexOf(t) === 0)
               && Math.abs(t.length - key.length) <= 8) sc = 80;
      else if (h && key.length >= 4 && h.indexOf(key) >= 0) sc = 65;
      if (sc > bestScore) { bestScore = sc; best = e; }
    });
    return bestScore >= 65 ? best.id : null;
  }

  async function jumpToKb(law) {
    var id = null;
    try { id = await resolveLawId(law); } catch (e) { id = null; }
    if (id && window.openDetail) {
      window.openDetail(id);
      return;
    }
    /* 回退：未定位到精确条目时按关键词检索，并明确告知用户 */
    var kw = String(law || "").trim();
    if (!kw) return;
    var m = kw.match(/^(.+?第\d+号)/);
    if (m) kw = m[1];
    try {
      if (window.switchTab) window.switchTab("kb");
      else { var nav = document.querySelector('.nav-item[data-tab="kb"]'); if (nav) nav.click(); }
    } catch (e) { /* noop */ }
    var inp = $("#kb-search");
    if (inp) {
      inp.value = kw;
      inp.dispatchEvent(new Event("input", { bubbles: true }));
      var clr = $("#kb-search-clear");
      if (clr) clr.hidden = false;
      inp.focus();
    }
    try {
      if (window.toast) window.toast("未找到精确法源条目，已按关键词检索「" + kw + "」", "warn");
    } catch (e) { /* noop */ }
  }

  var CATS = [["全部", ""], ["收入", "51"], ["资产", "52"], ["费用", "53"],
              ["税费", "54"], ["往来", "55"], ["期末结转", "56"]];
  var FIELDS = ["适用范围", "确认与计量要求", "会计分录与处理流程", "税务处理规定",
                "税会差异提示", "参照依据与关键条款", "依据层级", "生效状态",
                "适用边界", "信源", "核验"];

  var ST = { items: [], total: 0, q: "", cat: "", selected: null };

  function shortCat(c) {
    var m = String(c || "").match(/业务事项 · ([^（]+)/);
    return m ? m[1].replace("类", "") : (c || "业务事项");
  }

  async function load(q) {
    try {
      var r = await fetch("/api/business-cases?q=" + encodeURIComponent(q || ""), { cache: "no-store" });
      var d = await r.json();
      ST.items = Array.isArray(d.results) ? d.results : [];
      ST.total = d.total || ST.items.length;
      ST.q = q || "";
      if (ST.selected && !ST.items.some((x) => x.id === ST.selected)) ST.selected = null;
      render();
    } catch (e) {
      var list = $("#bc-list");
      if (list) list.innerHTML = '<div class="detail-empty"><b>业务事项加载失败</b><span>请确认本地服务已启动</span></div>';
    }
  }

  function visible() {
    if (!ST.cat) return ST.items;
    return ST.items.filter((x) => String(x.id || "").indexOf(ST.cat + "-") === 0);
  }

  function renderStats() {
    var el = $("#bc-stats");
    if (!el) return;
    el.innerHTML = '<div class="bc-stat"><b>' + ST.total + "</b><span>结构化条目</span></div>" +
      '<div class="bc-stat"><b>' + visible().length + "</b><span>当前显示</span></div>" +
      '<div class="bc-stat"><b>11</b><span>字段/条</span></div>';
  }

  function renderChips() {
    var el = $("#bc-filters");
    if (!el) return;
    el.innerHTML = CATS.map((c) => '<button class="filter-chip' +
      (ST.cat === c[1] ? " active" : "") + '" data-cat="' + c[1] + '">' + esc(c[0]) + "</button>").join("");
  }

  function renderList() {
    var el = $("#bc-list");
    if (!el) return;
    var items = visible();
    if (!items.length) {
      el.innerHTML = '<div class="detail-empty"><b>没有匹配的业务事项</b><span>换个关键词或点「全部」</span></div>';
      return;
    }
    el.innerHTML = items.map((x) =>
      '<button class="bc-item' + (ST.selected === x.id ? " active" : "") + '" data-id="' + esc(x.id) + '" role="option">' +
      '<span class="bc-no">' + esc(x.no || x.id) + "</span>" +
      '<span class="bc-title">' + esc(x.title) + "</span>" +
      '<span class="bc-cat">' + esc(shortCat(x.category)) + "</span>" +
      '<span class="bc-tier">' + esc(x.tier || "") + "</span></button>").join("");
  }

  function renderDetail() {
    var el = $("#bc-detail");
    if (!el) return;
    var item = ST.items.find((x) => x.id === ST.selected);
    if (!item) {
      el.innerHTML = '<div class="detail-empty"><b>选择左侧业务事项查看完整指引</b><span>含 11 项结构化字段与官方依据边界</span></div>';
      return;
    }
    var f = item.fields || {};
    var rows = FIELDS.map((k) => '<tr><th>' + esc(k) + "</th><td>" +
      (k === "参照依据与关键条款" ? lawLinkify(f[k] || "") :
       k === "信源" ? linkify(f[k] || item.basis || "") :
       linkify(f[k] || "")) + "</td></tr>").join("");
    el.innerHTML =
      '<div class="bc-detail-head">' +
      '<div class="bc-badges"><span class="bc-badge">' + esc(item.tier || "—") + ' 层</span>' +
      '<span class="bc-badge">' + esc(item.status || "—") + "</span>" +
      '<span class="bc-badge">' + esc(shortCat(item.category)) + "</span></div>" +
      "<h2>" + esc(item.no || "") + " " + esc(item.title) + "</h2>" +
      '<p class="bc-id">条目 ' + esc(item.id) + " · 业务事项结构化指引 · 非法规原文</p></div>" +
      '<table class="field-table bc-fields"><tbody>' + rows + "</tbody></table>" +
      '<div class="bc-foot">本层按业务事项组织，用于理解确认计量、分录流程与税会差异。' +
      '<b>点击带下划线的《法规名称》可跳转法规库检索</b>，右上角「导出 CSV」可导出当前筛选结果。' +
      '作申报或对外依据前，请按 <code>SOURCES-CHANNELS.md</code> 八步 SOP 回查官方原文。</div>';
  }

  function render() { renderStats(); renderChips(); renderList(); renderDetail(); }

  function debounce(fn, ms) {
    var t; return function (v) { clearTimeout(t); t = setTimeout(() => fn(v), ms); };
  }

  function init() {
    if (!$("#bc-list")) return;
    var doSearch = debounce((v) => load(v.trim()), 180);
    var input = $("#bc-search");
    if (input) input.addEventListener("input", (e) => {
      var clear = $("#bc-search-clear");
      if (clear) clear.hidden = !e.target.value;
      doSearch(e.target.value);
    });
    var clearBtn = $("#bc-search-clear");
    if (clearBtn) clearBtn.addEventListener("click", () => {
      if (input) { input.value = ""; input.focus(); }
      clearBtn.hidden = true;
      load("");
    });
    var chips = $("#bc-filters");
    if (chips) chips.addEventListener("click", (e) => {
      var b = e.target.closest("[data-cat]");
      if (!b) return;
      ST.cat = b.dataset.cat || "";
      render();
    });
    var list = $("#bc-list");
    if (list) list.addEventListener("click", (e) => {
      var b = e.target.closest(".bc-item");
      if (!b) return;
      ST.selected = b.dataset.id;
      renderList(); renderDetail();
    });
    var exp = $("#bc-export");
    if (exp) exp.addEventListener("click", exportCsv);
    var detail = $("#bc-detail");
    if (detail) detail.addEventListener("click", (e) => {
      var t = e.target;
      var a = t && t.closest ? t.closest(".bc-law-link") : null;
      if (!a) return;
      e.preventDefault();
      jumpToKb(a.getAttribute("data-law"));
    });
    load("");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
