// Small vanilla JS layer: token handling, SSE streaming, rendering, SVG chart.
"use strict";

const TOKEN_KEY = "iwc_token";
const CRITERIA = [
  ["task_response", "Task Response"],
  ["coherence_cohesion", "Coherence and Cohesion"],
  ["lexical_resource", "Lexical Resource"],
  ["grammatical_range_accuracy", "Grammatical Range and Accuracy"],
];
const $ = (sel, root = document) => root.querySelector(sel);

function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
function setToken(t) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch {}
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c != null) node.append(c);
  return node;
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...options, headers });
  if (res.status === 401 && !path.startsWith("/api/auth/login")) {
    setToken(null);
    location.href = "/login";
    throw new Error("Not logged in");
  }
  return res;
}

async function errorText(res) {
  try {
    const body = await res.json();
    if (Array.isArray(body.detail)) return body.detail.map((d) => d.msg.replace(/^Value error, /, "")).join(" ");
    return body.detail || res.statusText;
  } catch { return res.statusText; }
}

function countWords(text) {
  return (text.match(/[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*/g) || []).length;
}

function requireLogin() {
  if (!getToken()) { location.href = "/login"; return false; }
  return true;
}

async function initHeader() {
  const logout = $("#logout");
  logout.addEventListener("click", () => { setToken(null); location.href = "/login"; });
  if (!getToken()) return;
  const res = await api("/api/auth/me");
  if (res.ok) {
    $("#who").textContent = (await res.json()).email;
    logout.classList.remove("hidden");
  }
}

// ---------- Auth pages ----------

function initAuth() {
  const form = $("#auth-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = JSON.stringify(Object.fromEntries(new FormData(form)));
    const err = $("#auth-error");
    err.textContent = "";
    if (form.dataset.mode === "register") {
      const r = await api("/api/auth/register", { method: "POST", body });
      if (!r.ok) { err.textContent = await errorText(r); return; }
    }
    const r = await api("/api/auth/login", { method: "POST", body });
    if (!r.ok) { err.textContent = await errorText(r); return; }
    setToken((await r.json()).access_token);
    location.href = "/";
  });
}

// ---------- Result rendering (shared by grading page and detail page) ----------

function bandBadge(value) {
  return el("span", { class: "band", text: value == null ? "…" : Number(value).toFixed(value % 1 ? 1 : 0) });
}

function buildSkeleton(root) {
  root.replaceChildren();
  root.append(el("div", { class: "overall" }, el("span", { text: "Overall (estimate)" }), el("span", { class: "band big", id: "band-overall", text: "…" })));
  for (const [key, label] of CRITERIA) {
    root.append(
      el("article", { class: "criterion", id: `c-${key}` },
        el("header", {}, el("h3", { text: label }), el("span", { class: "band", id: `band-${key}`, text: "…" })),
        el("p", { class: "comment prewrap" }),
        el("ul", { class: "errors" }))
    );
  }
  root.append(el("section", { id: "rewrites" }));
}

function fillResult(root, data) {
  const bands = data.bands;
  $("#band-overall", root).textContent = Number(bands.overall).toFixed(1);
  for (const [key] of CRITERIA) {
    $(`#band-${key}`, root).textContent = bands[key];
    const box = $(`#c-${key}`, root);
    const fb = data.feedback[key] || { comment: "", errors: [] };
    $(".comment", box).textContent = fb.comment;
    const list = $(".errors", box);
    list.replaceChildren();
    for (const e of fb.errors) {
      list.append(el("li", {},
        el("q", { text: e.quote }),
        el("span", { text: ` — ${e.issue}` }),
        e.correction ? el("span", { class: "fix", text: ` → ${e.correction}` }) : null));
    }
  }
  const rw = $("#rewrites", root);
  rw.replaceChildren(el("h3", { text: "Stronger sentences / Câu viết lại hay hơn" }));
  for (const r of data.rewrites) {
    rw.append(el("div", { class: "rewrite" },
      el("p", { class: "before", text: r.original }),
      el("p", { class: "after", text: r.improved }),
      r.explanation ? el("p", { class: "muted", text: r.explanation }) : null));
  }
}

// ---------- Grading page ----------

async function refreshQuota() {
  const r = await api("/api/quota");
  if (!r.ok) return;
  const q = await r.json();
  $("#quota").textContent = `${q.remaining}/${q.limit} essays left today`;
  $("#grade-btn").disabled = q.remaining === 0;
}

function parseFrames(buffer, onEvent) {
  const frames = buffer.split("\n\n");
  const rest = frames.pop();
  for (const frame of frames) {
    let event = "message", data = "";
    for (const line of frame.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    onEvent(event, data ? JSON.parse(data) : null);
  }
  return rest;
}

function initGrade() {
  if (!requireLogin()) return;
  const form = $("#grade-form");
  const min = Number(form.dataset.min), max = Number(form.dataset.max);
  const essayBox = form.elements.essay;
  const counter = $("#word-count");
  const updateCount = () => {
    const n = countWords(essayBox.value);
    counter.textContent = `${n} words (${min}–${max})`;
    counter.classList.toggle("bad", n > 0 && (n < min || n > max));
  };
  essayBox.addEventListener("input", updateCount);
  refreshQuota();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("#grade-error");
    err.textContent = "";
    const btn = $("#grade-btn");
    btn.disabled = true;
    btn.textContent = "Grading…";
    const root = $("#result-body");
    buildSkeleton(root);
    root.classList.remove("hidden");
    $("#result-placeholder").classList.add("hidden");

    try {
      const res = await api("/api/essays", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form))) });
      if (!res.ok) { err.textContent = await errorText(res); root.classList.add("hidden"); return; }
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      const onEvent = (event, data) => {
        if (event === "feedback") {
          $(`#c-${data.criterion} .comment`, root).textContent += data.text;
        } else if (event === "retry") {
          buildSkeleton(root);
          root.prepend(el("p", { class: "muted", text: "The AI answer was malformed, retrying once…" }));
        } else if (event === "result") {
          fillResult(root, data);
          root.append(el("p", {}, el("a", { href: `/history/${data.id}`, text: "Open this result in your history →" })));
        } else if (event === "error") {
          err.textContent = data.message;
        }
      };
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer = parseFrames(buffer + value, onEvent);
      }
    } catch (ex) {
      err.textContent = "Connection lost. This attempt was not counted. Please try again.";
    } finally {
      btn.textContent = "Grade my essay";
      refreshQuota();
    }
  });
}

// ---------- History page ----------

function drawChart(container, points) {
  if (points.length === 0) { container.replaceChildren(el("p", { class: "muted", text: "Your chart appears after your first graded essay." })); return; }
  const W = 720, H = 260, L = 36, R = 12, T = 12, B = 30;
  const x = (i) => L + (points.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (points.length - 1));
  const y = (v) => T + ((9 - v) * (H - T - B)) / 9;
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Band scores over time");
  const add = (tag, attrs, text) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text != null) n.textContent = text;
    svg.append(n);
    return n;
  };
  for (let b = 0; b <= 9; b += 1) {
    add("line", { x1: L, x2: W - R, y1: y(b), y2: y(b), class: "grid-line" });
    add("text", { x: L - 8, y: y(b) + 4, class: "axis", "text-anchor": "end" }, b);
  }
  const series = [["overall", "Overall"], ...CRITERIA];
  // Draw criteria first so the thicker Overall line stays on top.
  [...series.entries()].reverse().forEach(([s, [key, label]]) => {
    const d = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(Number(p[key]))}`).join(" ");
    add("path", { d, class: `series s${s}` });
    points.forEach((p, i) => {
      const dot = add("circle", { cx: x(i), cy: y(Number(p[key])), r: s === 0 ? 4 : 2.5, class: `dot s${s}` });
      const t = document.createElementNS(NS, "title");
      t.textContent = `${label}: ${p[key]} · ${new Date(p.created_at).toLocaleDateString()}`;
      dot.append(t);
    });
  });
  points.forEach((p, i) => add("text", { x: x(i), y: H - 8, class: "axis", "text-anchor": "middle" }, `#${i + 1}`));
  const legend = el("div", { class: "legend" });
  series.forEach(([, label], s) => legend.append(el("span", { class: `key s${s}`, text: label })));
  container.replaceChildren(svg, legend);
}

async function initHistory() {
  if (!requireLogin()) return;
  const [listRes, progRes] = await Promise.all([api("/api/essays?limit=100"), api("/api/essays/progress")]);
  const essays = await listRes.json();
  drawChart($("#chart"), await progRes.json());
  const list = $("#essay-list");
  $("#history-empty").classList.toggle("hidden", essays.length > 0);
  for (const e of essays) {
    list.append(el("li", {},
      el("a", { href: `/history/${e.id}` },
        el("span", { class: "band", text: Number(e.overall_band).toFixed(1) }),
        el("span", { class: "q", text: e.question }),
        el("span", { class: "muted", text: `${new Date(e.created_at).toLocaleString()} · ${e.word_count} words` }))));
  }
}

async function initEssay() {
  if (!requireLogin()) return;
  const id = $("#essay-detail").dataset.id;
  const res = await api(`/api/essays/${id}`);
  if (!res.ok) { $("#essay-detail").replaceChildren(el("p", { class: "error", text: "Essay not found." })); return; }
  const data = await res.json();
  $("#essay-meta").textContent = `${new Date(data.created_at).toLocaleString()} · ${data.word_count} words · ${data.model}`;
  $("#essay-question").textContent = data.question;
  $("#essay-text").textContent = data.essay;
  const root = $("#result-body");
  buildSkeleton(root);
  fillResult(root, data);
}

// ---------- Boot ----------

document.addEventListener("DOMContentLoaded", () => {
  initHeader();
  if ($("#auth-form")) initAuth();
  else if ($("#grade-form")) initGrade();
  else if ($("#essay-list")) initHistory();
  else if ($("#essay-detail")) initEssay();
});
