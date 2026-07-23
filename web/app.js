/* MI/Transport LAB — dashboard app (no dependencies) */
"use strict";

/* ================= theme ================= */
const root = document.documentElement;
// localStorage can throw in sandboxed iframes — treat it as best-effort
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
};
function applyTheme(t) {
  root.setAttribute("data-theme", t);
  store.set("milab-theme", t);
}
applyTheme(
  new URLSearchParams(location.search).get("theme") ||
  store.get("milab-theme") ||
  (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
);
document.getElementById("theme-toggle").addEventListener("click", () => {
  applyTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark");
  drawScatter();
});

/* ================= routing ================= */
const VIEWS = ["overview", "explorer", "models"];
function route() {
  const view = VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "overview";
  for (const v of VIEWS) {
    document.getElementById("view-" + v).hidden = v !== view;
  }
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.view === view));
  if (view === "explorer") requestAnimationFrame(drawScatter);
  window.scrollTo({ top: 0 });
}
addEventListener("hashchange", route);

/* ================= data model ================= */
// dataset.json column order
const C = {
  ID: 0, FORMULA: 1, GAP: 2, DIRECT: 3, S_P: 4, S_N: 5,
  LSIG_P: 6, LSIG_N: 7, DENSITY: 8, VPA: 9, NSITES: 10,
  SG: 11, XTAL: 12, EHULL: 13,
};

// fixed crystal-system order = fixed categorical slot assignment (never re-mapped)
const XTAL_ORDER = ["Cubic", "Hexagonal", "Trigonal", "Tetragonal", "Orthorhombic", "Monoclinic", "Triclinic"];
const XTAL_JP = {
  Cubic: "立方晶", Hexagonal: "六方晶", Trigonal: "三方晶", Tetragonal: "正方晶",
  Orthorhombic: "斜方晶", Monoclinic: "単斜晶", Triclinic: "三斜晶",
};
const XTAL_VAR = {
  Cubic: "--xtal-cubic", Hexagonal: "--xtal-hex", Trigonal: "--xtal-trig",
  Tetragonal: "--xtal-tetra", Orthorhombic: "--xtal-ortho",
  Monoclinic: "--xtal-mono", Triclinic: "--xtal-tri",
};
function xtalColor(sys) {
  return getComputedStyle(root).getPropertyValue(XTAL_VAR[sys]).trim();
}

const X_AXES = {
  band_gap: { col: C.GAP, label: "登録バンドギャップ E_g", axis: "E_g (eV)", short: "E_g", unit: "eV" },
  density: { col: C.DENSITY, label: "密度", axis: "密度 (g/cm³)", short: "密度", unit: "g/cm³" },
  vpa: { col: C.VPA, label: "原子あたり体積", axis: "V/atom (Å³)", short: "V/atom", unit: "Å³" },
  nsites: { col: C.NSITES, label: "サイト数", axis: "サイト数", short: "サイト数", unit: "" },
};
const Y_AXES = {
  s_p: { col: C.S_P, label: "ゼーベック係数 S(p型)", axis: "S p型 (µV/K)", short: "S_p", unit: "µV/K", stage: 2 },
  s_n: { col: C.S_N, label: "ゼーベック係数 S(n型)", axis: "S n型 (µV/K)", short: "S_n", unit: "µV/K", stage: 2 },
  lsig_p: { col: C.LSIG_P, label: "電気伝導率 log₁₀σ(p型)", axis: "log₁₀σ p型 (S/m)", short: "log₁₀σ_p", unit: "", stage: 3 },
  lsig_n: { col: C.LSIG_N, label: "電気伝導率 log₁₀σ(n型)", axis: "log₁₀σ n型 (S/m)", short: "log₁₀σ_n", unit: "", stage: 3 },
};

const TARGETS = {
  seebeck_p_uV_K: { jp: "ゼーベック係数 S", type: "p型", stage: 2, unit: "µV/K", parity: "assets/parity_seebeck_p_uV_K.png" },
  seebeck_n_uV_K: { jp: "ゼーベック係数 S", type: "n型", stage: 2, unit: "µV/K", parity: "assets/parity_seebeck_n_uV_K.png" },
  sigma_p_S_m: { jp: "電気伝導率 log₁₀σ", type: "p型", stage: 3, unit: "dex", parity: "assets/parity_sigma_p_S_m.png" },
  sigma_n_S_m: { jp: "電気伝導率 log₁₀σ", type: "n型", stage: 3, unit: "dex", parity: "assets/parity_sigma_n_S_m.png" },
};

/* ================= helpers ================= */
const fmtInt = n => n.toLocaleString("ja-JP");
function fmtNum(v, d) { return v == null ? "—" : Number(v).toFixed(d); }

// "Bi2Te3" -> DOM fragment with <sub> digits (built safely, no innerHTML of data)
function formulaFrag(f) {
  const frag = document.createDocumentFragment();
  for (const part of String(f).split(/(\d+\.?\d*)/)) {
    if (!part) continue;
    if (/^\d/.test(part)) {
      const sub = document.createElement("sub");
      sub.textContent = part;
      frag.appendChild(sub);
    } else {
      frag.appendChild(document.createTextNode(part));
    }
  }
  return frag;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function niceTicks(min, max, n = 6) {
  const span = max - min || 1;
  const step0 = span / n;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= n) || 10 * mag;
  const ticks = [];
  for (let t = Math.ceil(min / step) * step; t <= max + 1e-9; t += step) {
    ticks.push(Math.abs(t) < step * 1e-6 ? 0 : t);
  }
  return ticks;
}

/* ================= state ================= */
let DATA = null, RESULTS = null;
const state = {
  x: "band_gap",
  y: "s_p",
  systems: new Set(XTAL_ORDER),
  search: "",
  pinned: null,          // row reference
  tableOpen: false,
  sort: { col: C.S_P, dir: -1 },
  target: "seebeck_p_uV_K",
};

function filteredRows() {
  const q = state.search.trim().toLowerCase();
  return DATA.rows.filter(r =>
    state.systems.has(r[C.XTAL]) &&
    (!q || r[C.FORMULA].toLowerCase().includes(q) || r[C.ID].toLowerCase().includes(q))
  );
}

/* ================= overview ================= */
function renderOverview() {
  const kpis = [
    { label: "MATERIALS", value: fmtInt(DATA.rows.length), sub: "安定相・非金属半導体" },
    { label: "FEATURES", value: "145", sub: "Magpie 132 + 構造 + E_g" },
    { label: "TARGETS", value: "4", sub: "S / σ × p型・n型" },
    { label: "BEST R²", value: "0.757", sub: "log₁₀σ n型(テスト)" },
    { label: "E_g SHAP RANK", value: "1", sub: "S(p型・n型とも)", accent: true },
  ];
  const wrap = document.getElementById("hero-kpis");
  for (const k of kpis) {
    const tile = el("div", "kpi");
    tile.appendChild(el("div", "kpi-label", k.label));
    const v = el("div", "kpi-value", k.value);
    if (k.accent) v.style.color = "var(--accent)";
    tile.appendChild(v);
    tile.appendChild(el("div", "kpi-sub", k.sub));
    wrap.appendChild(tile);
  }

  const funnel = [
    { label: "MPContribs 非金属エントリ", value: 30467 },
    { label: "現行MPデータベースと結合", value: 22623 },
    { label: "安定相フィルター E_hull ≤ 0.05", value: 15682 },
    { label: "登録バンドギャップ > 0(最終)", value: 15479, final: true },
  ];
  const fwrap = document.getElementById("funnel");
  for (const f of funnel) {
    const row = el("div", "funnel-row" + (f.final ? " final" : ""));
    row.appendChild(el("div", "funnel-label", f.label));
    const track = el("div", "funnel-track");
    const bar = el("div", "funnel-bar");
    bar.style.width = "0%";
    requestAnimationFrame(() =>
      requestAnimationFrame(() => { bar.style.width = (f.value / funnel[0].value * 100) + "%"; }));
    track.appendChild(bar);
    row.appendChild(track);
    row.appendChild(el("div", "funnel-value", fmtInt(f.value)));
    fwrap.appendChild(row);
  }
  fwrap.appendChild(el("p", "funnel-note",
    "古典的熱電材料ファミリー(Bi₂Te₃, SnSe, Mg₂Si, ハーフホイスラー ZrNiSn, スクッテルダイト CoSb₃)はすべて最終データセットに残存。"));
}

/* ================= explorer: controls ================= */
function initControls() {
  const selX = document.getElementById("sel-x");
  const selY = document.getElementById("sel-y");
  for (const [k, a] of Object.entries(Y_AXES)) {
    selY.appendChild(new Option(`${a.label}${a.unit ? ` [${a.unit}]` : ""}`, k));
  }
  for (const [k, a] of Object.entries(X_AXES)) {
    selX.appendChild(new Option(`${a.label}${a.unit ? ` [${a.unit}]` : ""}`, k));
  }
  selY.value = state.y; selX.value = state.x;
  selY.addEventListener("change", () => { state.y = selY.value; refreshExplorer(); });
  selX.addEventListener("change", () => { state.x = selX.value; refreshExplorer(); });

  let debounce;
  document.getElementById("inp-search").addEventListener("input", e => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { state.search = e.target.value; refreshExplorer(); }, 120);
  });

  const btnTable = document.getElementById("btn-table");
  btnTable.addEventListener("click", () => {
    state.tableOpen = !state.tableOpen;
    btnTable.setAttribute("aria-pressed", String(state.tableOpen));
    document.getElementById("table-card").hidden = !state.tableOpen;
    if (state.tableOpen) renderTable();
  });

  // crystal-system legend chips (identity + filter)
  const counts = {};
  for (const r of DATA.rows) counts[r[C.XTAL]] = (counts[r[C.XTAL]] || 0) + 1;
  const legend = document.getElementById("xtal-legend");
  for (const sys of XTAL_ORDER) {
    const chip = el("button", "legend-chip");
    chip.type = "button";
    chip.setAttribute("aria-pressed", "true");
    chip.dataset.sys = sys;
    const dot = el("span", "dot");
    dot.style.background = `var(${XTAL_VAR[sys]})`;
    chip.appendChild(dot);
    chip.appendChild(el("span", null, XTAL_JP[sys]));
    chip.appendChild(el("span", "cnt", fmtInt(counts[sys] || 0)));
    chip.addEventListener("click", () => {
      if (state.systems.size === XTAL_ORDER.length) {
        // from "all on": isolate the clicked system
        state.systems = new Set([sys]);
      } else if (state.systems.has(sys)) {
        state.systems.delete(sys);
        if (state.systems.size === 0) state.systems = new Set(XTAL_ORDER);
      } else {
        state.systems.add(sys);
      }
      syncLegend(); refreshExplorer();
    });
    legend.appendChild(chip);
  }
  const reset = el("button", "legend-chip reset", "すべて表示");
  reset.type = "button";
  reset.addEventListener("click", () => {
    state.systems = new Set(XTAL_ORDER);
    syncLegend(); refreshExplorer();
  });
  legend.appendChild(reset);
}
function syncLegend() {
  document.querySelectorAll(".legend-chip[data-sys]").forEach(chip =>
    chip.setAttribute("aria-pressed", String(state.systems.has(chip.dataset.sys))));
}
function refreshExplorer() {
  drawScatter();
  if (state.tableOpen) renderTable();
}

/* ================= explorer: scatter (canvas) ================= */
const canvas = document.getElementById("scatter");
const ctx = canvas.getContext("2d");
const tip = document.getElementById("scatter-tip");
let plot = null; // { rows, sx, sy, pad, w, h } — screen mapping of last draw

function drawScatter() {
  if (!DATA || document.getElementById("view-explorer").hidden) return;
  const wrap = document.getElementById("scatter-wrap");
  const w = wrap.clientWidth, h = wrap.clientHeight;
  if (!w) return;
  const dpr = devicePixelRatio || 1;
  canvas.width = w * dpr; canvas.height = h * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const css = getComputedStyle(root);
  const colGrid = css.getPropertyValue("--grid").trim();
  const colBase = css.getPropertyValue("--baseline").trim();
  const colMuted = css.getPropertyValue("--muted").trim();
  const colSurface = css.getPropertyValue("--surface").trim();

  ctx.clearRect(0, 0, w, h);

  const X = X_AXES[state.x], Y = Y_AXES[state.y];
  const rows = filteredRows();
  document.getElementById("scatter-title").textContent = `${Y.axis} vs ${X.axis}`;
  document.getElementById("scatter-count").textContent =
    `${fmtInt(rows.length)} / ${fmtInt(DATA.rows.length)} 件を表示 · 300 K · n = 10¹⁸ cm⁻³`;

  const pad = { t: 14, r: 18, b: 44, l: 62 };
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;

  let xmin = Infinity, xmax = -Infinity, ymin = Infinity, ymax = -Infinity;
  for (const r of rows) {
    const xv = r[X.col], yv = r[Y.col];
    if (xv < xmin) xmin = xv; if (xv > xmax) xmax = xv;
    if (yv < ymin) ymin = yv; if (yv > ymax) ymax = yv;
  }
  if (!rows.length) { xmin = 0; xmax = 1; ymin = 0; ymax = 1; }
  const xr = (xmax - xmin) || 1, yr = (ymax - ymin) || 1;
  xmin -= xr * 0.03; xmax += xr * 0.03; ymin -= yr * 0.05; ymax += yr * 0.05;

  const sx = v => pad.l + (v - xmin) / (xmax - xmin) * iw;
  const sy = v => pad.t + (1 - (v - ymin) / (ymax - ymin)) * ih;

  // gridlines + ticks (hairline, recessive)
  ctx.font = "11px ui-monospace, Menlo, monospace";
  ctx.fillStyle = colMuted;
  ctx.strokeStyle = colGrid;
  ctx.lineWidth = 1;
  for (const t of niceTicks(ymin, ymax, 6)) {
    const y = Math.round(sy(t)) + 0.5;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
    ctx.textAlign = "right"; ctx.textBaseline = "middle";
    ctx.fillText(formatTick(t), pad.l - 8, y);
  }
  for (const t of niceTicks(xmin, xmax, 7)) {
    const x = Math.round(sx(t)) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, h - pad.b); ctx.stroke();
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    ctx.fillText(formatTick(t), x, h - pad.b + 8);
  }
  // axes baselines
  ctx.strokeStyle = colBase;
  ctx.beginPath();
  ctx.moveTo(pad.l + 0.5, pad.t); ctx.lineTo(pad.l + 0.5, h - pad.b + 0.5);
  ctx.lineTo(w - pad.r, h - pad.b + 0.5); ctx.stroke();

  // axis titles
  ctx.fillStyle = colMuted;
  ctx.font = "11.5px system-ui, sans-serif";
  ctx.textAlign = "center"; ctx.textBaseline = "bottom";
  ctx.fillText(X.axis, pad.l + iw / 2, h - 4);
  ctx.save();
  ctx.translate(12, pad.t + ih / 2); ctx.rotate(-Math.PI / 2);
  ctx.textBaseline = "top";
  ctx.fillText(Y.axis, 0, 0);
  ctx.restore();

  // points, colored by crystal system (fixed slot order)
  const colors = {};
  for (const s of XTAL_ORDER) colors[s] = xtalColor(s);
  ctx.globalAlpha = rows.length > 4000 ? 0.45 : 0.7;
  for (const r of rows) {
    ctx.fillStyle = colors[r[C.XTAL]];
    ctx.beginPath();
    ctx.arc(sx(r[X.col]), sy(r[Y.col]), 2.6, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  // pinned point: surface ring + accent ring so it survives overlap
  if (state.pinned && rows.includes(state.pinned)) {
    const px = sx(state.pinned[X.col]), py = sy(state.pinned[Y.col]);
    ctx.beginPath(); ctx.arc(px, py, 5, 0, Math.PI * 2);
    ctx.fillStyle = colors[state.pinned[C.XTAL]]; ctx.fill();
    ctx.lineWidth = 2; ctx.strokeStyle = colSurface; ctx.stroke();
    ctx.beginPath(); ctx.arc(px, py, 8.5, 0, Math.PI * 2);
    ctx.strokeStyle = css.getPropertyValue("--accent").trim(); ctx.stroke();
  }

  plot = { rows, sx, sy, X, Y, w, h };
}

function formatTick(t) {
  if (Math.abs(t) >= 1000) return t.toLocaleString("ja-JP");
  return +t.toFixed(4) + "";
}

/* nearest-point hover (24px hit radius) */
function nearestRow(mx, my) {
  if (!plot) return null;
  let best = null, bestD = 24 * 24;
  const { rows, sx, sy, X, Y } = plot;
  for (const r of rows) {
    const dx = sx(r[X.col]) - mx, dy = sy(r[Y.col]) - my;
    const d = dx * dx + dy * dy;
    if (d < bestD) { bestD = d; best = r; }
  }
  return best;
}

canvas.addEventListener("pointermove", e => {
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  const r = nearestRow(mx, my);
  if (!r) { tip.hidden = true; return; }
  renderTooltip(r);
  tip.hidden = false;
  const wrap = document.getElementById("scatter-wrap");
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  let tx = mx + 16, ty = my - th / 2;
  if (tx + tw > wrap.clientWidth - 4) tx = mx - tw - 16;
  ty = Math.max(4, Math.min(ty, wrap.clientHeight - th - 4));
  tip.style.left = tx + "px"; tip.style.top = ty + "px";
  canvas.style.cursor = "pointer";
});
canvas.addEventListener("pointerleave", () => { tip.hidden = true; canvas.style.cursor = "crosshair"; });
canvas.addEventListener("click", e => {
  const rect = canvas.getBoundingClientRect();
  const r = nearestRow(e.clientX - rect.left, e.clientY - rect.top);
  state.pinned = r || null;
  renderDetail();
  drawScatter();
});

function renderTooltip(r) {
  tip.replaceChildren();
  const f = el("div", "tt-formula"); f.appendChild(formulaFrag(r[C.FORMULA]));
  tip.appendChild(f);
  tip.appendChild(el("div", "tt-id", r[C.ID]));
  const { X, Y } = plot;
  for (const [axis, val] of [[Y, r[Y.col]], [X, r[X.col]]]) {
    const row = el("div", "tt-row");
    row.appendChild(el("span", "v", `${fmtNum(val, 3)}${axis.unit ? " " + axis.unit : ""}`));
    row.appendChild(el("span", "k", axis.short));
    tip.appendChild(row);
  }
  const xt = el("div", "tt-xtal");
  const dot = el("span", "dot");
  dot.style.background = `var(${XTAL_VAR[r[C.XTAL]]})`;
  xt.appendChild(dot);
  xt.appendChild(document.createTextNode(`${XTAL_JP[r[C.XTAL]]} · SG ${r[C.SG]}`));
  tip.appendChild(xt);
}

/* ================= explorer: detail panel ================= */
function renderDetail() {
  const panel = document.getElementById("detail-panel");
  panel.replaceChildren();
  const r = state.pinned;
  if (!r) {
    panel.appendChild(el("p", "detail-empty", "点をクリックすると、材料の詳細がここに表示されます。"));
    return;
  }
  const close = el("button", "detail-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "選択を解除");
  close.addEventListener("click", () => { state.pinned = null; renderDetail(); drawScatter(); });
  panel.appendChild(close);

  const f = el("div", "detail-formula"); f.appendChild(formulaFrag(r[C.FORMULA]));
  panel.appendChild(f);
  panel.appendChild(el("div", "detail-id", r[C.ID]));

  const rows = [
    ["E_g (MP登録)", `${fmtNum(r[C.GAP], 3)} eV${r[C.DIRECT] ? " · 直接" : " · 間接"}`],
    ["S p型", `${fmtNum(r[C.S_P], 1)} µV/K`],
    ["S n型", `${fmtNum(r[C.S_N], 1)} µV/K`],
    ["log₁₀σ p型", fmtNum(r[C.LSIG_P], 2)],
    ["log₁₀σ n型", fmtNum(r[C.LSIG_N], 2)],
    ["密度", `${fmtNum(r[C.DENSITY], 2)} g/cm³`],
    ["V/atom", `${fmtNum(r[C.VPA], 1)} Å³`],
    ["結晶系", `${XTAL_JP[r[C.XTAL]]} (SG ${r[C.SG]})`],
    ["E_hull", `${fmtNum(r[C.EHULL], 1)} meV/atom`],
  ];
  const table = el("table", "detail-table");
  for (const [k, v] of rows) {
    const tr = el("tr");
    tr.appendChild(el("td", null, k));
    tr.appendChild(el("td", null, v));
    table.appendChild(tr);
  }
  panel.appendChild(table);

  const link = el("a", "detail-link", "Materials Project で見る ↗");
  link.href = "https://materialsproject.org/materials/" + encodeURIComponent(r[C.ID]);
  link.target = "_blank"; link.rel = "noopener";
  panel.appendChild(link);
}

/* ================= explorer: table view ================= */
const TABLE_COLS = [
  { col: C.ID, label: "ID" },
  { col: C.FORMULA, label: "組成" },
  { col: C.GAP, label: "E_g (eV)", d: 3 },
  { col: C.S_P, label: "S_p (µV/K)", d: 1 },
  { col: C.S_N, label: "S_n (µV/K)", d: 1 },
  { col: C.LSIG_P, label: "log₁₀σ_p", d: 2 },
  { col: C.LSIG_N, label: "log₁₀σ_n", d: 2 },
  { col: C.DENSITY, label: "ρ (g/cm³)", d: 2 },
  { col: C.XTAL, label: "結晶系" },
];
const TABLE_CAP = 300;

function renderTable() {
  const rows = filteredRows().slice();
  const { col, dir } = state.sort;
  rows.sort((a, b) => (a[col] > b[col] ? 1 : a[col] < b[col] ? -1 : 0) * dir);

  document.getElementById("table-count").textContent =
    rows.length > TABLE_CAP
      ? `${fmtInt(rows.length)} 件中、先頭 ${TABLE_CAP} 件を表示(検索・フィルターで絞り込めます)`
      : `${fmtInt(rows.length)} 件を表示`;

  const table = document.getElementById("data-table");
  table.replaceChildren();
  const thead = el("thead"); const hr = el("tr");
  for (const tc of TABLE_COLS) {
    const th = el("th", null, tc.label);
    if (tc.col === col) th.appendChild(el("span", "arrow", dir === 1 ? "▲" : "▼"));
    th.addEventListener("click", () => {
      state.sort = { col: tc.col, dir: tc.col === col ? -dir : -1 };
      renderTable();
    });
    hr.appendChild(th);
  }
  thead.appendChild(hr); table.appendChild(thead);

  const tbody = el("tbody");
  for (const r of rows.slice(0, TABLE_CAP)) {
    const tr = el("tr");
    for (const tc of TABLE_COLS) {
      const td = el("td");
      if (tc.col === C.FORMULA) td.appendChild(formulaFrag(r[tc.col]));
      else if (tc.col === C.XTAL) td.textContent = XTAL_JP[r[tc.col]];
      else if (tc.d != null) td.textContent = fmtNum(r[tc.col], tc.d);
      else td.textContent = r[tc.col];
      tr.appendChild(td);
    }
    tr.addEventListener("click", () => { state.pinned = r; renderDetail(); drawScatter(); });
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
}

/* ================= models view ================= */
function initModels() {
  const tabs = document.getElementById("target-tabs");
  for (const [key, t] of Object.entries(TARGETS)) {
    const b = el("button", "target-tab");
    b.type = "button";
    b.dataset.target = key;
    b.appendChild(el("span", "stage-tag", "STAGE " + t.stage));
    b.appendChild(document.createTextNode(`${t.jp}(${t.type})`));
    b.addEventListener("click", () => { state.target = key; renderModels(); });
    tabs.appendChild(b);
  }
  renderModels();
}

function renderModels() {
  document.querySelectorAll(".target-tab").forEach(b =>
    b.classList.toggle("active", b.dataset.target === state.target));

  const m = RESULTS.metrics[state.target];
  const t = TARGETS[state.target];
  const unit = t.unit === "dex" ? " dex" : " " + t.unit;

  const kpis = [
    { label: "TEST R²", value: m.test_r2.toFixed(3), sub: `n_test = ${fmtInt(m.n_test)}` },
    { label: "MAE", value: m.test_mae.toFixed(m.log10_transformed ? 3 : 1), sub: unit.trim() },
    { label: "RMSE", value: m.test_rmse.toFixed(m.log10_transformed ? 3 : 1), sub: unit.trim() },
    { label: "5-FOLD CV R²", value: m.cv_r2_mean.toFixed(3), sub: `± ${m.cv_r2_std.toFixed(3)}` },
    { label: "E_g SHAP RANK", value: `${m.band_gap_shap_rank}`, sub: "/ 145 特徴量", accent: m.band_gap_shap_rank === 1 },
  ];
  const kwrap = document.getElementById("model-kpis");
  kwrap.replaceChildren();
  for (const k of kpis) {
    const tile = el("div", "kpi");
    tile.appendChild(el("div", "kpi-label", k.label));
    const v = el("div", "kpi-value", k.value);
    if (k.accent) v.style.color = "var(--accent)";
    tile.appendChild(v);
    tile.appendChild(el("div", "kpi-sub", k.sub));
    kwrap.appendChild(tile);
  }

  // SHAP top-15: emphasis form — band gap in accent, everything else de-emphasized
  const shap = RESULTS.shap[state.target];
  const chart = document.getElementById("shap-chart");
  chart.replaceChildren();
  const max = shap.top[0].value;
  shap.top.forEach((s, i) => {
    const isGap = s.feature === "band_gap_mp_eV";
    const row = el("div", "shap-row" + (isGap ? " is-gap" : ""));
    const name = el("div", "shap-name", prettyFeature(s.feature));
    name.title = s.feature;
    row.appendChild(name);
    const track = el("div", "shap-track");
    // reserve 56px at the right so end labels never clip against the card edge
    const frac = s.value / max;
    const width = `calc((100% - 56px) * ${frac.toFixed(4)})`;
    const bar = el("div", "shap-bar");
    bar.style.width = "0%";
    requestAnimationFrame(() => requestAnimationFrame(() => { bar.style.width = width; }));
    track.appendChild(bar);
    // selective labels: the top bar and the band-gap bar
    if (i === 0 || isGap) {
      const val = el("span", "shap-val", s.value.toFixed(m.log10_transformed ? 3 : 1));
      val.style.setProperty("--w", width);
      track.appendChild(val);
    }
    track.title = `${s.feature} — mean |SHAP| = ${s.value}`;
    row.appendChild(track);
    chart.appendChild(row);
  });

  // single-file (artifact) builds inject the images as data URIs via MILAB_PARITY
  document.getElementById("parity-img").src =
    (window.MILAB_PARITY && window.MILAB_PARITY[state.target]) || t.parity;
  document.getElementById("parity-sub").textContent =
    `${t.jp}(${t.type})· MAE ${m.test_mae.toFixed(m.log10_transformed ? 3 : 1)}${unit} · R² ${m.test_r2.toFixed(3)}`;
}

function prettyFeature(f) {
  const map = {
    band_gap_mp_eV: "登録バンドギャップ E_g",
    is_gap_direct_int: "直接/間接ギャップ",
    density_g_cm3: "密度",
    volume_per_atom_A3: "原子あたり体積",
    nsites: "サイト数",
    spacegroup_number: "空間群番号",
  };
  if (map[f]) return map[f];
  return f.replace(/^MagpieData /, "").replace(/^crystal_/, "");
}

/* ================= boot ================= */
(function boot() {
  DATA = window.MILAB_DATA;
  RESULTS = window.MILAB_RESULTS;
  if (!DATA || !RESULTS) {
    document.querySelector("main").prepend(
      el("p", "section-desc", "データの読み込みに失敗しました。`python web/build_data.py` で web/data/ を生成してください。"));
    return;
  }
  renderOverview();
  initControls();
  initModels();
  renderDetail();
  route();
  new ResizeObserver(() => drawScatter()).observe(document.getElementById("scatter-wrap"));
})();
