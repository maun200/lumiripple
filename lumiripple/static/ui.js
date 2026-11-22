"use strict";
// ---- small helpers -------------------------------------------------------
function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "class") n.className = v;
    else if (k in n) n[k] = v;
    else n.setAttribute(k, v);
  }
  n.append(...kids.filter(k => k !== null && k !== undefined));
  return n;
}
const clone = v => JSON.parse(JSON.stringify(v));
const clamp = (v, a, b) => Math.min(Math.max(v, a), b);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const css = c => `rgb(${c[0]},${c[1]},${c[2]})`;
const hex = c => "#" + c.map(x => x.toString(16).padStart(2, "0")).join("").toUpperCase();
const unhex = t => { const m = /^\s*#?([0-9a-f]{6})\s*$/i.exec(t); return m ? [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16)) : null; };
const isGradient = p => !Array.isArray(p);
const first = p => isGradient(p) ? p.stops[0] : p;
const background = p => isGradient(p) ? `linear-gradient(90deg, ${p.stops.map(css).join(", ")})`
  : p.some(x => x) ? css(p) : "linear-gradient(135deg, #000 46%, #bbb 47%, #bbb 53%, #000 54%)";
function toHsv([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const v = Math.max(r, g, b), d = v - Math.min(r, g, b);
  const h = !d ? 0 : v === r ? ((g - b) / d + 6) % 6 : v === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h / 6, v ? d / v : 0, v];
}
function toRgb([h, s, v]) {
  const f = n => { const k = (n + h * 6) % 6; return Math.round(255 * (v - v * s * Math.max(0, Math.min(k, 4 - k, 1)))); };
  return [f(5), f(3), f(1)];
}
function toast(text) {
  const t = document.getElementById("toast");
  t.textContent = text; t.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => { t.hidden = true; }, 4500);
}
function row(name, hint, ...controls) {
  return el("div", { class: "row" }, el("div", { class: "name" }, name, hint ? el("small", {}, hint) : null), el("div", { class: "controls" }, ...controls));
}
function dialog(title, big = false) {
  const d = el("dialog", { class: big ? "big" : "" }, el("h2", {}, title));
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  return d;
}
function ask(title, text, buttons, extra = null) {
  return new Promise(done => {
    const d = dialog(title);
    if (text) d.append(el("p", {}, text));
    if (extra) d.append(extra);
    d.addEventListener("close", () => done(null));
    d.append(el("div", { class: "bar" }, el("button", { onclick: () => d.close() }, "Cancel"),
      ...buttons.map(([k, label, cls]) => el("button", { class: cls || "", onclick: () => { done(k); d.close(); } }, label))));
    d.showModal();
  });
}
async function askText(title, text, value = "") {
  const input = el("input", { type: "text", value, maxLength: 40, "aria-label": title });
  const r = ask(title, text, [["ok", "OK", "main"]], input);
  input.addEventListener("keydown", e => { if (e.key === "Enter") input.closest("dialog").querySelector("button.main").click(); });
  input.focus(); input.select();
  return (await r) === "ok" ? input.value : null;
}

// ---- color editor --------------------------------------------------------
const PALETTE = ["#FF0000", "#FF5000", "#FFA000", "#FFE000", "#80FF00", "#00FF00", "#00FF80", "#00FFFF", "#0090FF", "#0000FF", "#6000FF", "#B000FF", "#FF00FF", "#FF0080", "#FFFFFF", "#000000"];
const PRESETS = { Rainbow: ["#FF0000", "#FFB000", "#00FF00", "#00FFFF", "#0000FF", "#FF00FF"], Fire: ["#FF0000", "#FF5000", "#FFE000"], Ocean: ["#00FFC0", "#0090FF", "#0000FF"], Sunset: ["#FFA000", "#FF0080", "#6000FF"], Forest: ["#80FF00", "#00FF00", "#00FF80"], Neon: ["#00FFFF", "#FF00FF"] };

// kind: "solid" (one color), "area" (gradient with direction and motion) or "wave" (gradient over time)
function editColor(title, value, kind, meta, changed) {
  const before = clone(value), size = 270, ring = 24, half = size / 2, side = (half - ring - 9) * Math.SQRT2, off = half - side / 2;
  let grad = isGradient(value), stops = grad ? clone(value.stops) : [clone(value), toRgb([(toHsv(value)[0] + .33) % 1, 1, 1])];
  let dir = grad ? value.direction : "horizontal", speed = grad ? value.speed : 0, sel = 0, hsv = toHsv(stops[0]), drag = null, timer = 0;
  const get = () => grad ? { stops: clone(stops), direction: dir, speed } : clone(stops[sel]);
  const send = () => { clearTimeout(timer); timer = setTimeout(() => changed(get()), 40); };
  const d = dialog(title), wheel = el("canvas", { class: "wheel", width: size, height: size, "aria-label": "Color wheel" }), g = wheel.getContext("2d");
  const code = el("input", { type: "text", maxLength: 8, size: 9, "aria-label": "Color code" });
  const now = el("button", { class: "swatch", disabled: true, title: "New" });
  const old = el("button", { class: "swatch", title: "Back to the previous color", onclick: () => { load(before); paint(); send(); } });
  old.style.background = background(before);
  const extra = el("div"), list = el("div", { class: "controls" });
  const toggle = el("input", { type: "checkbox", onchange: () => { grad = toggle.checked; pick(0); send(); } });
  const dirs = el("select", { onchange: () => { dir = dirs.value; send(); } }, ...Object.entries(meta.directions).map(([k, v]) => el("option", { value: k }, v)));
  const motion = el("input", { type: "range", min: 0, max: meta.max_gradient_speed, step: .01, oninput: () => { speed = +motion.value; moving(); send(); } });
  const motionOut = el("output"), moving = () => { motionOut.value = speed ? speed.toFixed(2) + "/s" : "still"; };
  function load(v) { grad = isGradient(v); stops = grad ? clone(v.stops) : [clone(v), stops[1] || [0, 120, 255]]; if (grad) { dir = v.direction; speed = v.speed; } sel = 0; hsv = toHsv(stops[0]); }
  function pick(i) { sel = i; const n = toHsv(stops[i]); hsv = n[1] && n[2] ? n : [hsv[0], n[1], n[2]]; paint(); }
  function setColor(c) { const n = toHsv(c); hsv = n[1] && n[2] ? n : [hsv[0], n[1], n[2]]; stops[sel] = c; paint(); send(); }
  function paint(writeCode = true) {
    g.clearRect(0, 0, size, size); g.lineWidth = ring;
    for (let i = 0; i < 360; i++) { g.beginPath(); g.strokeStyle = `hsl(${i} 100% 50%)`; g.arc(half, half, half - ring / 2, i * Math.PI / 180, (i + 1.6) * Math.PI / 180); g.stroke(); }
    for (const [x1, y1, a, b] of [[off + side, off, "#fff", css(toRgb([hsv[0], 1, 1]))], [off, off + side, "rgba(0,0,0,0)", "#000"]]) {
      const l = g.createLinearGradient(off, off, x1, y1); l.addColorStop(0, a); l.addColorStop(1, b); g.fillStyle = l; g.fillRect(off, off, side, side);
    }
    const t = hsv[0] * 2 * Math.PI, r = half - ring / 2;
    for (const [x, y, c] of [[half + r * Math.cos(t), half + r * Math.sin(t), toRgb([hsv[0], 1, 1])], [off + hsv[1] * side, off + (1 - hsv[2]) * side, stops[sel]]]) {
      g.beginPath(); g.arc(x, y, 8, 0, 7); g.fillStyle = css(c); g.fill(); g.lineWidth = 4; g.strokeStyle = "rgba(0,0,0,.6)"; g.stroke(); g.lineWidth = 2; g.strokeStyle = "#fff"; g.stroke();
    }
    if (writeCode) code.value = hex(stops[sel]);
    now.style.background = background(get()); toggle.checked = grad; extra.hidden = !grad; dirs.value = dir; motion.value = speed; moving();
    list.replaceChildren(...stops.map((c, i) => { const b = el("button", { class: "swatch small" + (i === sel ? " on" : ""), title: `Edit color ${i + 1}`, onclick: () => pick(i) }); b.style.background = background(c); b.style.width = "30px"; return b; }),
      el("button", { class: "small", title: "Remove this color", disabled: stops.length <= 2, onclick: () => { stops.splice(sel, 1); pick(Math.max(sel - 1, 0)); send(); } }, "−"),
      el("button", { class: "small", title: "Add a color", disabled: stops.length >= meta.max_stops, onclick: () => { stops.splice(sel + 1, 0, clone(stops[sel])); pick(sel + 1); send(); } }, "+"));
  }
  function move(e) {
    const b = wheel.getBoundingClientRect(), x = (e.clientX - b.left) * size / b.width, y = (e.clientY - b.top) * size / b.height;
    if (drag === "ring") { hsv[0] = (Math.atan2(y - half, x - half) / (2 * Math.PI) + 1) % 1; if (!hsv[1] || !hsv[2]) hsv[1] = hsv[2] = 1; }
    else if (drag === "square") { hsv[1] = clamp((x - off) / side, 0, 1); hsv[2] = 1 - clamp((y - off) / side, 0, 1); }
    else return;
    stops[sel] = toRgb(hsv); paint(); send();
  }
  wheel.addEventListener("pointerdown", e => {
    const b = wheel.getBoundingClientRect(), x = (e.clientX - b.left) * size / b.width, y = (e.clientY - b.top) * size / b.height, q = Math.hypot(x - half, y - half);
    drag = x >= off && x <= off + side && y >= off && y <= off + side ? "square" : q <= half && q >= half - ring ? "ring" : null;
    wheel.setPointerCapture(e.pointerId); move(e);
  });
  wheel.addEventListener("pointermove", move); wheel.addEventListener("pointerup", () => { drag = null; });
  code.addEventListener("input", () => { const c = unhex(code.value); if (c) { const n = toHsv(c); hsv = n[1] && n[2] ? n : [hsv[0], n[1], n[2]]; stops[sel] = c; paint(false); send(); } });
  const sw = c => { const b = el("button", { title: c === "#000000" ? "Black = off" : c, onclick: () => setColor(unhex(c)) }); b.style.background = background(unhex(c)); return b; };
  if (kind !== "solid") {
    d.append(row("Gradient", null, toggle), extra);
    extra.append(row("Colors", null, list), row("Presets", null, ...Object.entries(PRESETS).map(([n, c]) => { const b = el("button", { class: "swatch small", title: n, onclick: () => { stops = c.map(unhex); pick(0); send(); } }); b.style.background = background({ stops: c.map(unhex) }); b.style.width = "40px"; return b; })));
    if (kind === "area") extra.append(row("Direction", null, dirs), row("Motion", null, motionOut, motion));
  }
  d.append(wheel, el("div", { class: "bar" }, el("span", { class: "left" }, "Before "), old, now, code), el("div", { class: "grid" }, ...PALETTE.map(sw)),
    el("p", { class: "hint" }, "Black means off: the key does not light up there."), el("div", { class: "bar" }, el("button", { class: "main", onclick: () => d.close() }, "Done")));
  d.addEventListener("close", () => { if (timer) { clearTimeout(timer); if (!same(get(), before)) changed(get()); } });
  paint(); d.showModal();
}
function swatch(title, kind, meta, changed) {
  let value = [0, 0, 0];
  const b = el("button", { class: "swatch", title, "aria-label": title, onclick: () => editColor(title, value, kind, meta, v => { b.show(v); changed(v); }) });
  b.show = v => { value = clone(v); b.style.background = background(v); };
  b.get = () => clone(value);
  return b;
}

// ---- keyboard ------------------------------------------------------------
const SHORT = { "Print Screen": "PrtSc", "Scroll Lock": "ScrLk", "Pause/Break": "Pause", "Backspace": "⌫", "Insert": "Ins", "Page Up": "PgUp", "Page Down": "PgDn", "Delete": "Del", "Caps Lock": "Caps", "Left Shift": "Shift", "Right Shift": "Shift", "Left Control": "Ctrl", "Right Control": "Ctrl", "Left Windows": "Win", "Right Windows": "Win", "Left Alt": "Alt", "Right Alt": "AltGr", "Right Fn": "Fn", "Space": "", "Up Arrow": "↑", "Down Arrow": "↓", "Left Arrow": "←", "Right Arrow": "→", "Num Lock": "Num", "Media Stop": "■", "Media Previous": "⏮", "Media Play/Pause": "⏯", "Media Next": "⏭", "Media Mute": "🔇", "Escape": "Esc", "Enter": "⏎", "\\ (ANSI)": "\\", "\\ (ISO)": "<", };
const shortName = n => SHORT[n] ?? n.replace("Number Pad ", "").replace("Enter", "⏎");
class Board {
  constructor(keys, present, onPick) {
    this.keys = keys.filter(k => !present.length || present.includes(k[0])); this.colors = {}; this.selected = new Set(); this.accent = [255, 160, 0]; this.marks = {};
    this.canvas = el("canvas", { class: "board" + (onPick ? " pick" : ""), role: "img", "aria-label": "Keyboard" });
    this.top = Math.min(...this.keys.map(k => k[2])); this.w = Math.max(...this.keys.map(k => k[1] + k[3])); this.h = Math.max(...this.keys.map(k => k[2] + k[4])) - this.top;
    new ResizeObserver(() => this.draw()).observe(this.canvas);
    if (!onPick) return;
    let on = null;
    const hit = e => { const b = this.canvas.getBoundingClientRect(), s = this.w / b.width, x = (e.clientX - b.left) * s, y = (e.clientY - b.top) * s + this.top; return this.keys.findLast(k => x >= k[1] && x <= k[1] + k[3] && y >= k[2] && y <= k[2] + k[4])?.[0]; };
    this.canvas.addEventListener("pointerdown", e => { this.canvas.setPointerCapture(e.pointerId); const k = hit(e); if (k) { on = !this.selected.has(k); onPick(k, on); } });
    this.canvas.addEventListener("pointermove", e => { if (on === null) return; const k = hit(e); if (k && this.selected.has(k) !== on) onPick(k, on); });
    this.canvas.addEventListener("pointerup", () => { on = null; });
  }
  draw() {
    const c = this.canvas, width = c.clientWidth; if (!width) return;
    const r = devicePixelRatio || 1, s = width / this.w, g = c.getContext("2d"), st = getComputedStyle(document.documentElement);
    if (c.width !== Math.round(width * r)) { c.width = Math.round(width * r); c.height = Math.round(this.h * s * r); c.style.height = this.h * s + "px"; }
    g.setTransform(r, 0, 0, r, 0, 0); g.clearRect(0, 0, width, this.h * s); g.textAlign = "center"; g.textBaseline = "middle";
    for (const [n, x, y, w, h] of this.keys) {
      const live = this.colors[n], sel = this.selected.has(n), f = sel ? this.accent : live;
      g.beginPath(); g.roundRect(x * s + 1.5, (y - this.top) * s + 1.5, w * s - 3, h * s - 3, 5); g.fillStyle = f ? css(f) : st.getPropertyValue("--key"); g.fill();
      g.lineWidth = sel ? 3 : 1; g.strokeStyle = st.getPropertyValue(sel ? "--fg" : "--line"); g.stroke();
      g.fillStyle = f ? (f[0] * .3 + f[1] * .59 + f[2] * .11 > 140 ? "#000" : "#fff") : st.getPropertyValue("--fg");
      const t = shortName(n); g.font = `${Math.max(s * (t.length > 2 ? .24 : .34), 7)}px system-ui, sans-serif`; g.fillText(t, (x + w / 2) * s, (y - this.top + h / 2) * s, w * s - 6);
      if (this.marks[n] && !sel) { g.beginPath(); g.arc((x + w) * s - 8, (y - this.top) * s + 8, 4, 0, 7); g.fillStyle = css(this.marks[n]); g.fill(); }
    }
  }
}
function pickKeys(title, meta, present, start, accent, marks, changed) {
  const d = dialog(title, true), b = new Board(meta.keys, present, (k, on) => { on ? b.selected.add(k) : b.selected.delete(k); b.draw(); changed([...b.selected]); });
  b.selected = new Set(start); b.accent = accent; b.marks = marks;
  const set = keys => { const all = keys.every(k => b.selected.has(k)); keys.forEach(k => all ? b.selected.delete(k) : b.selected.add(k)); b.draw(); changed([...b.selected]); };
  d.append(el("p", { class: "hint" }, "Click keys or drag across them."), b.canvas, el("div", { class: "bar" }, ...Object.entries(meta.groups).map(([n, k]) => el("button", { onclick: () => set(k) }, n)),
    el("button", { onclick: () => { b.selected.clear(); b.draw(); changed([]); } }, "None"), el("button", { class: "main", onclick: () => d.close() }, "Done")));
  d.showModal(); b.draw();
}
