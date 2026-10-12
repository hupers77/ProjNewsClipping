/* ProjNewsClipping v1 — 화면 동작 (프레임워크 없음) */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

async function api(path, body, opts = {}) {
  // retry: 같은 요청을 다시 보내도 안전한 것(수집 시작·미리보기)만 한 번 더 시도한다
  const attempts = opts.retry ? 3 : 1;
  let res;
  for (let i = 0; i < attempts; i++) {
    try {
      res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-NewsClip": "1" },
        body: JSON.stringify(body || {}),
      });
      break;
    } catch (_) {
      if (i === attempts - 1) {
        showDisconnected();
        throw new Error("앱 서버와 연결할 수 없습니다. 앱을 다시 실행해 주세요.");
      }
      await new Promise((r) => setTimeout(r, 400 * (i + 1)));
    }
  }
  let data = {};
  try { data = await res.json(); } catch (_) { /* 본문 없음 */ }
  if (!res.ok || data.error) throw new Error(data.error || `요청 실패 (${res.status})`);
  return data;
}

function toast(msg) {
  let el = $("#toast");
  if (!el) { el = document.createElement("div"); el.id = "toast"; el.className = "toast"; document.body.append(el); }
  el.textContent = msg;
  el.classList.add("on");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("on"), 2600);
}

function fail(err) { toast("⚠ " + (err && err.message ? err.message : err)); }

/* 서버 신호(ping): 연결이 끊기면 사용자에게 알린다 */
let pingFails = 0;
let lastVisible = Date.now();
function showDisconnected() {
  if ($("#disconnected")) return;
  const bar = document.createElement("div");
  bar.id = "disconnected";
  bar.className = "notice err";
  bar.style.cssText = "position:fixed;left:0;right:0;top:0;z-index:60;text-align:center;border-radius:0";
  bar.textContent = "⚠ 앱 서버와 연결이 끊어졌습니다. 앱을 닫고 바탕화면 아이콘으로 다시 실행해 주세요.";
  document.body.prepend(bar);
}
async function ping() {
  try {
    await fetch("/api/ping", { method: "POST", headers: { "X-NewsClip": "1" } });
    pingFails = 0;
    const bar = $("#disconnected");
    if (bar) bar.remove();
  } catch (_) {
    if (++pingFails >= 3) showDisconnected();
  }
}
setInterval(ping, 5000);
ping();
// 뒤로 가기 등으로 오래된 화면(캐시)이 되살아나면 서버의 최신 상태로 다시 읽는다
window.addEventListener("pageshow", (ev) => { if (ev.persisted) location.reload(); });
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { lastVisible = Date.now(); return; }
  ping();
  // 절전·최소화에서 오래 있다 돌아오면 후보 리스트를 최신 상태로 다시 읽는다 (결정은 즉시 저장되므로 안전)
  if (document.body.dataset.page === "candidates" && Date.now() - lastVisible > 120000) location.reload();
});

/* 사이드바 접기 */
(function () {
  const btn = $("#side-toggle");
  if (!btn) return;
  try { if (localStorage.getItem("sideCollapsed") === "1") document.body.classList.add("side-collapsed"); } catch (_) {}
  btn.addEventListener("click", () => {
    const on = document.body.classList.toggle("side-collapsed");
    try { localStorage.setItem("sideCollapsed", on ? "1" : "0"); } catch (_) {}
  });
})();

/* ───────── 후보 리스트 ───────── */
function initCandidates() {
  const cards = $$(".card[data-id]");
  const makeBtn = $("#make-email");
  const collectBtn = $("#collect");
  const q = $("#f-query");

  function approvedCount() { return cards.filter((c) => c.dataset.state === "approved").length; }

  function refreshCounts() {
    const n = approvedCount();
    makeBtn.textContent = `✉️ 이메일 만들기 (${n})`;
    makeBtn.disabled = n === 0;
    makeBtn.classList.toggle("ok", n > 0);
    $("#count-approved").textContent = n;
  }

  function applyFilters() {
    const cats = new Set($$(".f-cat:checked").map((i) => i.value));
    const state = $("#f-state").value;
    const onlyCand = $("#f-cand").checked;
    const text = q.value.trim().toLowerCase();
    let shown = 0;
    for (const c of cards) {
      let ok = cats.has(c.dataset.cat);
      if (ok && state && c.dataset.state !== (state === "pending" ? "" : state)) ok = false;
      if (ok && onlyCand && c.dataset.cand !== "1" && c.dataset.state !== "rejected") ok = false;
      if (ok && text && !c.dataset.text.includes(text)) ok = false;
      c.hidden = !ok;
      if (ok) shown++;
    }
    $("#no-match").hidden = shown !== 0 || cards.length === 0;
    $("#count-shown").textContent = shown;
  }

  function paint(card, state) {
    card.dataset.state = state;
    card.classList.toggle("approved", state === "approved");
    card.classList.toggle("rejected", state === "rejected");
    const badge = $(".badge", card);
    badge.className = "badge" + (state ? " " + state : "");
    badge.textContent = state === "approved" ? "✅ 승인" : state === "rejected" ? "🚫 거절" : "";
    badge.hidden = !state;
    $(".btn-approve", card).hidden = state === "approved";
    $(".btn-reject", card).hidden = state !== "";
    $(".btn-undo", card).hidden = state === "";
    $(".btn-undo", card).textContent = state === "approved" ? "승인 취소" : "거절 취소";
  }

  async function decide(card, state) {
    const prev = card.dataset.state;
    paint(card, state); // 낙관적 갱신: 먼저 화면을 바꾸고 실패하면 되돌린다
    refreshCounts();
    applyFilters();
    try {
      await api("/api/decision", { id: Number(card.dataset.id), ids: JSON.parse(card.dataset.ids), decision: state });
    } catch (e) {
      paint(card, prev); refreshCounts(); applyFilters(); fail(e);
    }
  }

  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button");
    const card = ev.target.closest(".card[data-id]");
    if (!btn || !card) return;
    if (btn.classList.contains("btn-approve")) decide(card, "approved");
    else if (btn.classList.contains("btn-reject")) decide(card, "rejected");
    else if (btn.classList.contains("btn-undo")) decide(card, "");
  });

  $$(".f-cat, #f-state, #f-cand").forEach((el) => el.addEventListener("change", applyFilters));
  q.addEventListener("input", applyFilters);
  applyFilters();
  refreshCounts();

  /* 수집 */
  const prog = $("#progress");
  async function pollCollect() {
    try {
      const st = await (await fetch("/api/collect/status")).json();
      prog.textContent = "⏳ " + (st.message || "수집 중…");
      if (st.running) { setTimeout(pollCollect, 700); return; }
      prog.classList.remove("on");
      collectBtn.disabled = false;
      if (st.error) { fail(st.error); return; }
      sessionStorage.setItem("collectReport", JSON.stringify(st.report || {}));
      location.reload();
    } catch (e) { fail(e); collectBtn.disabled = false; }
  }
  collectBtn.addEventListener("click", async () => {
    collectBtn.disabled = true;
    prog.classList.add("on");
    prog.textContent = "⏳ 수집을 시작합니다…";
    try { await api("/api/collect", {}, { retry: true }); pollCollect(); } catch (e) { fail(e); collectBtn.disabled = false; prog.classList.remove("on"); }
  });
  if ($("#collect-running")) { collectBtn.disabled = true; prog.classList.add("on"); pollCollect(); }

  const stored = sessionStorage.getItem("collectReport");
  if (stored) {
    sessionStorage.removeItem("collectReport");
    const rep = JSON.parse(stored);
    const box = $("#report");
    const bad = (rep.sources || []).filter((s) => s.error);
    box.hidden = false;
    box.className = "notice" + (bad.length ? " warn" : "");
    box.innerHTML = "";
    const head = document.createElement("div");
    head.textContent = `새 기사 ${rep.new_total || 0}건 수집 (본문 추출 ${rep.content_fetched || 0}건)` +
      (rep.purged ? ` · 오래된 기사 ${rep.purged}건 삭제` : "");
    box.append(head);
    bad.forEach((s) => { const d = document.createElement("div"); d.textContent = `⚠ ${s.source}: ${s.error}`; box.append(d); });
  }

  /* 이메일 만들기 */
  const dlg = $("#make-dialog");
  makeBtn.addEventListener("click", () => {
    $("#make-count").textContent = approvedCount();
    dlg.showModal();
  });
  $("#make-cancel").addEventListener("click", () => dlg.close());
  $("#make-go").addEventListener("click", async () => {
    $("#make-go").disabled = true;
    try {
      await api("/api/make-email", { clear_undecided: $("#make-clear").checked });
      location.href = "/email";
    } catch (e) { fail(e); $("#make-go").disabled = false; dlg.close(); }
  });
}

/* ───────── 이메일 ───────── */
function initEmail() {
  const form = $("#email-form");
  if (!form) return; // 초안 없음
  let timer = null;
  let dirty = false;

  function readDraft() {
    const items = $$(".item", form).map((el) => ({
      article_id: Number(el.dataset.id),
      category: el.dataset.cat,
      include: $(".i-include", el).checked,
      title: $(".i-title", el).value,
      summary: $(".i-summary", el).value,
      links: $$(".links tbody tr", el).map((tr) => ({
        title: $(".l-title", tr).value, outlet: $(".l-outlet", tr).value, url: $(".l-url", tr).value,
      })).filter((l) => l.url.trim()),
    }));
    return {
      subject: $("#e-subject").value, sender: $("#e-sender").value, recipients: $("#e-to").value,
      intro: $("#e-intro").value, outro: $("#e-outro").value, items,
    };
  }

  async function refreshPreview() {
    try {
      const res = await api("/api/email/preview", { draft: readDraft() }, { retry: true });
      $("#preview").srcdoc = res.html;
    } catch (e) { fail(e); }
  }
  function schedulePreview() {
    dirty = true;
    $("#dirty").hidden = false;
    clearTimeout(timer);
    timer = setTimeout(refreshPreview, 350);
  }

  form.addEventListener("input", schedulePreview);
  form.addEventListener("change", (ev) => {
    const inc = ev.target.closest(".i-include");
    if (inc) inc.closest(".item").classList.toggle("off", !inc.checked);
    schedulePreview();
  });
  form.addEventListener("click", (ev) => {
    const add = ev.target.closest(".l-add");
    const del = ev.target.closest(".l-del");
    if (add) {
      const tbody = $("tbody", add.closest(".item"));
      const tr = $("#link-row-template").content.firstElementChild.cloneNode(true);
      tbody.append(tr);
    } else if (del) {
      del.closest("tr").remove();
      schedulePreview();
    }
  });

  async function save(quiet) {
    await api("/api/email/save", { draft: readDraft() });
    dirty = false;
    $("#dirty").hidden = true;
    if (!quiet) toast("저장했습니다.");
  }
  $("#b-save").addEventListener("click", () => save(false).catch(fail));

  $("#b-open").addEventListener("click", async () => {
    try {
      const res = await api("/api/email/open", { draft: readDraft() });
      toast("메일 프로그램으로 열었습니다: " + res.path);
      dirty = false; $("#dirty").hidden = true;
    } catch (e) { fail(e); }
  });
  $("#b-mailto").addEventListener("click", async () => {
    try {
      const res = await api("/api/email/mailto", { draft: readDraft() });
      window.location.href = res.url;
    } catch (e) { fail(e); }
  });

  async function download(kind) {
    try {
      const res = await api("/api/email/export", { draft: readDraft(), kind });
      const bytes = Uint8Array.from(atob(res.data), (c) => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: res.mime }));
      const a = document.createElement("a");
      a.href = url; a.download = res.filename; document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (e) { fail(e); }
  }
  $("#b-eml").addEventListener("click", () => download("eml"));
  $("#b-html").addEventListener("click", () => download("html"));

  $("#b-sent").addEventListener("click", async () => {
    if (!confirm("메일을 실제로 보내셨나요?\n\n발송 처리하면 초안이 비워지고 담긴 기사는 '발송됨'으로 기록됩니다.")) return;
    try {
      await save(true);
      const res = await api("/api/email/sent");
      toast(`발송 처리했습니다 (${res.count}건)`);
      setTimeout(() => location.reload(), 600);
    } catch (e) { fail(e); }
  });
  $("#b-revert").addEventListener("click", async () => {
    if (!confirm("초안을 폐기하고 담긴 기사를 후보 리스트(승인 상태)로 되돌릴까요?")) return;
    try {
      const res = await api("/api/email/revert");
      toast(`${res.count}건을 후보 리스트로 되돌렸습니다`);
      setTimeout(() => (location.href = "/"), 600);
    } catch (e) { fail(e); }
  });

  window.addEventListener("beforeunload", (ev) => { if (dirty) { ev.preventDefault(); ev.returnValue = ""; } });
  refreshPreview();
}

/* ───────── 환경 설정 ───────── */
function initSettings() {
  const root = $("#settings-form");
  if (!root) return;
  let dirty = false;
  const markDirty = () => { dirty = true; $("#dirty").hidden = false; };
  root.addEventListener("input", markDirty);
  root.addEventListener("change", markDirty);

  $$(".tabs button").forEach((b) => b.addEventListener("click", () => {
    $$(".tabs button").forEach((x) => x.classList.toggle("on", x === b));
    $$(".tabpane").forEach((p) => p.classList.toggle("on", p.id === b.dataset.tab));
  }));

  function addRow(tableId, templateId) {
    const tr = $("#" + templateId).content.firstElementChild.cloneNode(true);
    $("#" + tableId + " tbody").append(tr);
    markDirty();
  }
  $("#add-source").addEventListener("click", () => addRow("sources-table", "source-row-template"));
  $("#add-keyword").addEventListener("click", () => addRow("keywords-table", "keyword-row-template"));
  root.addEventListener("click", (ev) => {
    const del = ev.target.closest(".row-del");
    if (del) { del.closest("tr").remove(); markDirty(); }
  });

  const num = (id) => Number($("#" + id).value);
  const val = (id) => $("#" + id).value;

  function collect() {
    return {
      collect: {
        days: num("c-days"), fetch_content: $("#c-fetch").checked, content_max_chars: num("c-chars"),
        max_items_per_source: num("c-max"), retention_days: num("c-retention"),
      },
      sources: $$("#sources-table tbody tr").map((tr) => ({
        id: $(".s-id", tr).value.trim(), name: $(".s-name", tr).value.trim(), type: $(".s-type", tr).value,
        url: $(".s-url", tr).value.trim(), category: $(".s-cat", tr).value, lang: $(".s-lang", tr).value,
        enabled: $(".s-on", tr).checked, top_n: Number($(".s-topn", tr).value) || 30,
        min_points: Number($(".s-minp", tr).value) || 150,
      })).filter((s) => s.id),
      filters: {
        exclude_keywords: val("f-exclude").split("\n").map((s) => s.trim()).filter(Boolean),
        exclude_in_content: $("#f-in-content").checked,
        include_keywords: $$("#keywords-table tbody tr").map((tr) => ({
          word: $(".k-word", tr).value.trim(), bonus: Number($(".k-bonus", tr).value) || 0,
        })).filter((k) => k.word),
      },
      review: {
        max_candidates: num("r-max"), min_score: num("r-min"), per_source_max: num("r-per"),
        cluster_threshold: num("r-cluster"), weight_freshness: num("r-wf"), weight_keyword: num("r-wk"),
        weight_buzz: num("r-wb"),
      },
      email: {
        subject_template: val("m-subject"), sender: val("m-sender"), recipients: val("m-to"),
        intro: val("m-intro"), outro: val("m-outro"), summary_chars: num("m-sumchars"), max_links: num("m-links"),
      },
    };
  }

  $("#save").addEventListener("click", async () => {
    $("#save").disabled = true;
    try {
      const res = await api("/api/settings", collect());
      dirty = false;
      $("#dirty").hidden = true;
      toast(res.message || "저장했습니다.");
      if (res.retention_days) $("#c-retention").value = res.retention_days;
    } catch (e) { fail(e); } finally { $("#save").disabled = false; }
  });
  window.addEventListener("beforeunload", (ev) => { if (dirty) { ev.preventDefault(); ev.returnValue = ""; } });
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "candidates") initCandidates();
  else if (page === "email") initEmail();
  else if (page === "settings") initSettings();
});
