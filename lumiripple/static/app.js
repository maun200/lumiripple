"use strict";
// ---- access --------------------------------------------------------------
let token = location.hash.slice(1);
if (token) { try { localStorage.setItem("token", token); } catch { /* private window */ } history.replaceState(null, "", "/"); }
else { try { token = localStorage.getItem("token") || ""; } catch { token = ""; } }
async function call(cmd, data = {}) {
  try {
    const r = await fetch("/api", { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + token }, body: JSON.stringify({ cmd, ...data }) });
    return await r.json();
  } catch { return { ok: false, error: "The LumiRipple service does not answer" }; }
}
let meta = null, state = null, live = null, recording = null;
const loaders = [];                                 // functions that show the current settings
const main = document.getElementById("main"), status = document.getElementById("status");
async function run(cmd, data) { const r = await call(cmd, data); if (!r.ok) toast(r.error); await refresh(); return r; }
const dig = (o, path) => path.reduce((a, k) => a[k], o);
const queue = {};
function set(path, value) {
  let o = state.settings; path.slice(0, -1).forEach(k => { o = o[k]; }); o[path.at(-1)] = clone(value);
  const key = path.join("."); clearTimeout(queue[key]);
  queue[key] = setTimeout(async () => { delete queue[key]; const r = await call("set", { settings: path.reduceRight((a, k) => ({ [k]: a }), value) }); if (!r.ok) { toast(r.error); refresh(true); } }, 40);
}

// ---- building blocks -----------------------------------------------------
function section(title, hint, wide = false) {
  const s = el("section", { class: wide ? "wide" : "" }, el("h2", {}, title), hint ? el("p", { class: "hint" }, hint) : null);
  main.append(s); return s;
}
function check(s, name, hint, ...path) {
  const c = el("input", { type: "checkbox", "aria-label": name, onchange: () => set(path, c.checked) });
  loaders.push(e => { c.checked = dig(e, path); }); s.append(row(name, hint, c));
}
const UNITS = { brightness: v => Math.round(v * 100) + " %", speed: v => v.toFixed(1) + " keys/s", width: v => v.toFixed(2) + " keys", fade: v => v.toFixed(2) + " s", release: v => v.toFixed(2) + " s", sensitivity: v => v.toFixed(2) + "×", min_ms: v => Math.round(v) + " ms" };
function slider(s, name, ...path) {
  const k = path.at(-1), [lo, hi] = meta.limits[k], out = el("output"), i = el("input", { type: "range", min: lo, max: hi, step: (hi - lo) / 200, "aria-label": name });
  const show = () => { out.value = UNITS[k](+i.value); };
  i.addEventListener("input", () => { show(); set(path, +(+i.value).toFixed(3)); });
  loaders.push(e => { if (document.activeElement !== i || Math.abs(+i.value - dig(e, path)) > (hi - lo) / 150) { i.value = dig(e, path); out.value = UNITS[k](dig(e, path)); } });
  s.append(row(name, null, out, i));
}
function color(s, name, kind, ...path) {
  const b = swatch(name, kind, meta, v => set(path, v)); loaders.push(e => b.show(dig(e, path))); s.append(row(name, null, b));
}
function colors(s, name, parts, ...path) {
  const bs = parts.map(p => swatch(`${name}: ${p}`, "solid", meta, () => set(path, bs.map(b => b.get()))));
  loaders.push(e => dig(e, path).forEach((c, i) => bs[i].show(c))); s.append(row(name, parts.join(" · "), ...bs));
}
const select = (options, value, change, label) => { const n = el("select", { "aria-label": label, onchange: () => change(n.value) }, ...options.map(([v, t]) => el("option", { value: v }, t))); n.value = value; return n; };

// ---- page ----------------------------------------------------------------
function build() {
  let s = section("Keyboard", null, true);
  live = new Board(meta.keys, state.present); s.append(live.canvas);

  s = section("Profile", "Lighting and macros belong to the profile");
  const prof = el("select", { "aria-label": "Active profile", onchange: () => run("profile_switch", { name: prof.value }) });
  s.append(row("Active profile", null, prof), row("", null,
    el("button", { onclick: async () => { const n = await askText("New profile", "The current profile is copied."); if (n !== null) run("profile_new", { name: n }); } }, "New"),
    el("button", { onclick: async () => { const n = await askText("Rename profile", "", state.active); if (n !== null) run("profile_rename", { name: state.active, title: n }); } }, "Rename"),
    el("button", { onclick: resetProfile }, "Reset"), el("button", { class: "danger", onclick: deleteProfile }, "Delete …")));
  const pk = select([["", "none"], ...meta.triggers.map(t => [t, t])], "", v => run("profile_key", { key: v || null }), "Profile key");
  s.append(row("Profile key", "Switches to the next profile. The key keeps its normal function, so pick one you do not need.", pk));
  slider(s, "Overall brightness", "brightness");
  loaders.push(() => { prof.replaceChildren(...state.profiles.map(p => el("option", { value: p }, p))); prof.value = state.active; pk.value = state.profile_key || ""; });

  s = section("Base color"); color(s, "Color", "area", "base", "color"); slider(s, "Brightness", "base", "brightness");

  s = section("Wave", "Runs outwards from every key you press"); check(s, "Wave on key press", null, "wave", "on"); color(s, "Color", "wave", "wave", "color");
  slider(s, "Brightness", "wave", "brightness"); slider(s, "Speed", "wave", "speed"); slider(s, "Width (tail)", "wave", "width"); slider(s, "Fade", "wave", "fade");

  s = section("Pressed key", "Lights up while held, then fades"); check(s, "Light up the pressed key", null, "pressed", "on"); color(s, "Color", "wave", "pressed", "color");
  slider(s, "Brightness", "pressed", "brightness"); slider(s, "Fade out", "pressed", "release"); check(s, "Also over displays", "Cover stats, sound and highlighted keys for a moment", "pressed", "over_displays");
  check(s, "Ignore short touches", "Lighting only. Presses shorter than the minimum do not count.", "press", "on"); slider(s, "Minimum press", "press", "min_ms");

  s = section("Highlighted keys", "Own color for keys, and for the wave that starts on them"); check(s, "Show highlights", null, "highlight", "on"); slider(s, "Brightness", "highlight", "brightness");
  highlightList(s);

  s = section("Other lights", "Logo, light bars and special keys. Without an own color they follow the base color."); slider(s, "Brightness", "extra", "brightness"); extraList(s);

  s = section("PC stats", "Each display uses neighbouring keys of one row. Temperatures run from 30 to 90 °C."); check(s, "Show PC stats", null, "stats", "on"); colors(s, "Colors", ["low", "medium", "high"], "stats", "colors");
  slider(s, "Brightness", "stats", "brightness"); statList(s);

  for (const [q, title, hint] of [["sound", "Sound", "What the computer plays, bass left, treble right"], ["mic", "Microphone", "Only the level is used. Nothing is stored, and the microphone is open only while this is on."]]) {
    s = section(title, hint); check(s, "Show", null, q, "on"); colors(s, "Colors", ["bottom", "top"], q, "colors"); slider(s, "Brightness", q, "brightness"); slider(s, "Sensitivity", q, "sensitivity");
    const chips = el("div", { class: "chips" }), boxes = {};
    for (const [a, t] of Object.entries(meta.areas)) { boxes[a] = el("input", { type: "checkbox", onchange: () => set([q, "areas"], Object.keys(boxes).filter(k => boxes[k].checked)) }); chips.append(el("label", {}, boxes[a], t)); }
    loaders.push(e => Object.entries(boxes).forEach(([a, b]) => { b.checked = e[q].areas.includes(a); })); s.append(chips);
  }
  macroSection();
}
async function resetProfile() {
  const r = await ask("Reset to defaults?", `Profile "${state.active}". Name and other profiles stay.`, [["all", "Lighting and delete macros", "danger"], ["light", "Lighting only", "main"]]);
  if (r) run("profile_reset", { everything: r === "all" });
}
async function deleteProfile() {
  const others = state.profiles.filter(p => p !== state.active);
  if (!others.length) return toast("There is no other profile. The active profile cannot be deleted.");
  const pick = select(others.map(p => [p, p]), others[0], () => {}, "Profile");
  if (await ask("Delete a profile?", "Its lighting and macros are lost.", [["ok", "Delete", "danger"]], pick)) run("profile_delete", { name: pick.value });
}

// Lists are rebuilt only when their content changed from outside.
function listOf(s, path, makeRow, add) {
  let items = null; const box = el("div"); s.append(box, add ? row("", null, add.button) : "");
  const api = { get items() { return items; }, send: () => set(path, items), rebuild: () => box.replaceChildren(...items.map((it, i) => makeRow(it, i, api))), remove: i => { items.splice(i, 1); api.rebuild(); api.send(); } };
  loaders.push(e => { const n = dig(e, path); if (!same(n, items)) { items = clone(n); api.rebuild(); } });
  return api;
}
function highlightList(s) {
  const button = el("button", { onclick: () => { api.items.push({ keys: [], color: [255, 160, 0], wave: null }); api.rebuild(); api.send(); choose(api.items.at(-1)); } }, "Highlight keys");
  const choose = it => { const marks = {}; api.items.forEach(o => { if (o !== it) o.keys.forEach(k => { marks[k] = first(o.color || o.wave || [128, 128, 128]); }); });
    pickKeys("Select keys", meta, state.present, it.keys, first(it.color || it.wave || [255, 160, 0]), marks, k => { if (api.items.includes(it)) { it.keys = k; api.send(); } }); };
  const api = listOf(s, ["highlight", "items"], (it, i, l) => {
    const part = (k, name, kind, start) => { const b = swatch(name, kind, meta, v => { it[k] = v; l.send(); }), c = el("input", { type: "checkbox", checked: !!it[k], "aria-label": name, onchange: () => { it[k] = c.checked ? b.get() : null; b.disabled = !c.checked; l.send(); } }); b.show(it[k] || start); b.disabled = !it[k]; return row(name, null, c, b); };
    const names = it.keys.slice(0, 8).join(", ") + (it.keys.length > 8 ? ` and ${it.keys.length - 8} more` : "");
    return el("div", { class: "sub" }, row(names || "No keys selected", null, el("button", { onclick: () => choose(it) }, "Keys"), el("button", { class: "danger small", onclick: () => l.remove(i) }, "Remove")), part("color", "Own key color", "area", [255, 160, 0]), part("wave", "Own wave color", "wave", [255, 0, 0]));
  }, { button });
}
function extraList(s) {
  const box = el("div"); let shown = null; s.append(box);
  loaders.push(e => {
    const now = [state.extras, e.extra.colors]; if (same(now, shown)) return; shown = clone(now);
    box.replaceChildren(...(state.extras.length ? state.extras.map(n => {
      const send = () => { shown = clone([state.extras, state.settings.extra.colors]); };
      const put = v => { const c = clone(state.settings.extra.colors); if (v) c[n] = v; else delete c[n]; set(["extra", "colors"], c); send(); };
      const b = swatch(n, "area", meta, put), c = el("input", { type: "checkbox", checked: n in e.extra.colors, "aria-label": n, onchange: () => { b.disabled = !c.checked; put(c.checked ? b.get() : null); } });
      b.show(e.extra.colors[n] || [255, 160, 0]); b.disabled = !c.checked; return row(n, null, c, b);
    }) : [el("p", { class: "hint" }, "This keyboard reports none.")]));
  });
}
function statList(s) {
  const usable = () => meta.rows.map(r => r.filter(k => state.present.includes(k))).filter(r => r.length);
  const span = it => { const r = usable().find(x => x.includes(it.start)); if (!r) return [[], 1]; const i = r.indexOf(it.start); return [r.slice(i, i + it.count), r.length - i]; };
  const button = el("button", { onclick: () => { const used = new Set(api.items.flatMap(i => span(i)[0])), m = Object.keys(meta.metrics).find(k => !api.items.some(i => i.metric === k)) || "cpu"; let start = "1";
    for (const r of usable()) { const c = r.filter(k => !["Escape", "`", "Print Screen", "Scroll Lock", "Pause/Break"].includes(k) && !k.startsWith("Media")), i = c.findIndex((_, n) => c.length - n >= 4 && c.slice(n, n + 4).every(k => !used.has(k))); if (i >= 0) { start = c[i]; break; } }
    api.items.push({ metric: m, start, count: 4 }); api.rebuild(); api.send(); } }, "Add display");
  const api = listOf(s, ["stats", "items"], (it, i, l) => {
    const [keys, max] = span(it), clash = l.items.some((o, j) => j !== i && span(o)[0].some(k => keys.includes(k)));
    const count = el("input", { type: "number", min: 1, max: Math.min(max, 24), value: it.count, "aria-label": "Number of keys", onchange: () => { it.count = clamp(Math.round(+count.value) || 1, 1, Math.min(max, 24)); l.rebuild(); l.send(); } });
    count.style.width = "70px";
    return el("div", { class: "sub" }, row(meta.metrics[it.metric], (!keys.length ? "key not on this keyboard" : keys.length === 1 ? keys[0] : `${keys[0]} to ${keys.at(-1)}`) + (clash ? " · overlaps another display" : ""),
      select(Object.entries(meta.metrics), it.metric, v => { it.metric = v; l.rebuild(); l.send(); }, "Value"), select(usable().flat().map(k => [k, k]), it.start, v => { it.start = v; it.count = Math.min(it.count, span(it)[1]); l.rebuild(); l.send(); }, "First key"), count,
      el("button", { class: "danger small", onclick: () => l.remove(i) }, "Remove")));
  }, { button });
}
function macroSection() {
  const s = section("Macros", "Do not record passwords. The trigger key keeps its normal function, so pick one you do not need, such as Pause or F13.", true), play = el("div"), list = el("div");
  s.append(row("", null, el("button", { class: "main", onclick: record }, "Record macro")), play, list);
  let shown = null;
  loaders.push(() => {
    const now = state.macros.map(m => [m.name, m.trigger]); if (same(now, shown)) return; shown = now;
    list.replaceChildren(...state.macros.map(m => {
      const out = el("output"), i = el("input", { type: "range", min: meta.macro_speed[0], max: meta.macro_speed[1], step: .25, value: m.speed, "aria-label": "Speed" }), c = el("input", { type: "checkbox", checked: m.instant });
      const show = () => { out.value = (+i.value).toFixed(2) + "×"; i.disabled = c.checked; }, send = () => { show(); call("macro_set", { name: m.name, speed: +i.value, instant: c.checked }); };
      i.addEventListener("input", send); c.addEventListener("change", send); show();
      return row(m.name, `on key ${m.trigger}`, out, i, el("label", {}, c, " instant"), el("button", { class: "danger small", onclick: async () => { if (await ask("Delete macro?", m.name, [["ok", "Delete", "danger"]])) run("macro_delete", { name: m.name }); } }, "Delete"));
    }));
  });
  const bar = el("progress", { max: 1 }), text = el("div", { class: "name" }), sp = el("input", { type: "range", min: meta.macro_speed[0], max: meta.macro_speed[1], step: .25, "aria-label": "Playback speed", oninput: () => call("play_speed", { speed: +sp.value }) });
  play.append(el("div", { class: "row" }, text, el("div", { class: "controls" }, sp, el("button", { onclick: () => call("play_instant") }, "Finish now"), el("button", { class: "danger", onclick: () => call("play_cancel") }, "Cancel"))), bar); play.hidden = true;
  loaders.push(() => { const p = state.playing; play.hidden = !p; if (!p) return; text.textContent = `▶ ${p.name} · ${p.elapsed.toFixed(1)} s of ${p.total.toFixed(1)} s · last: ${p.last ?? "–"} · next: ${p.next ?? "–"}`; bar.value = p.total ? p.elapsed / p.total : 1; if (document.activeElement !== sp) sp.value = p.speed; });
}
async function record() {
  if (!(await run("record_start")).ok) return;
  const d = dialog("Recording"); recording = d; let keep = false;
  const stop = k => { keep = k; d.close(); };
  d.append(el("p", {}, "Type the macro now, also in another window. Recording ends after 60 seconds. Escape on the keyboard blinks red. No passwords!"), el("div", { class: "bar" }, el("button", { onclick: () => stop(false), tabIndex: -1 }, "Discard"), el("button", { class: "main", onclick: () => stop(true), tabIndex: -1 }, "Stop")));
  d.addEventListener("cancel", e => e.preventDefault());
  d.addEventListener("keydown", e => { e.preventDefault(); e.stopPropagation(); }, true);    // typed keys must not press the buttons
  d.addEventListener("close", async () => {
    recording = null;
    if (!keep) return run("record_discard");
    const r = await run("record_stop"); if (!r.ok) return;
    const name = el("input", { type: "text", maxLength: 40, "aria-label": "Name" }), trig = select(meta.triggers.map(t => [t, t]), "Pause/Break", () => {}, "Trigger key");
    const ok = await ask("Save macro", `${r.count} key presses recorded`, [["ok", "Save", "main"]], el("div", {}, row("Name", null, name), row("Trigger key", null, trig)));
    if (!ok || !(await run("macro_save", { name: name.value, trigger: trig.value })).ok) run("record_discard");
  });
  d.showModal(); d.tabIndex = -1; d.focus();
}

// ---- refresh -------------------------------------------------------------
async function refresh(force = false) {
  const r = await call("get");
  main.inert = !r.ok; status.classList.toggle("bad", !r.ok);
  if (!r.ok) { status.textContent = r.error === "wrong access token" ? "Please open LumiRipple with: lumiripple open" : r.error; return false; }
  if (!force && Object.keys(queue).length) r.settings = state.settings;      // our own change is still on its way
  const fresh = !state; const before = state; state = r;
  const bad = [!r.status.openrgb && "no OpenRGB server found", r.status.openrgb && !r.boards.length && "no per-key keyboard found", !r.status.input && (r.status.error || "no key input"), r.status.audio].filter(Boolean);
  status.textContent = bad.length ? bad.join(" · ") : r.boards.join(", "); status.classList.toggle("bad", bad.length > 0);
  if (recording && !r.recording) recording.querySelector("button.main").click();   // time limit reached
  if (fresh) return true;
  if (!same(before.present, r.present)) { const n = new Board(meta.keys, r.present); live.canvas.replaceWith(n.canvas); live = n; }
  loaders.forEach(f => f(state.settings));
  return true;
}
async function frames() {
  if (!document.hidden && live) { const r = await call("frame"); if (r.ok) { live.colors = r.keys; live.draw(); } }
  setTimeout(frames, 80);
}
(async () => {
  const m = await call("meta");
  if (!m.ok) { status.classList.add("bad"); status.textContent = m.error === "wrong access token" ? "Please open LumiRipple with: lumiripple open" : m.error; setTimeout(() => location.reload(), 5000); return; }
  meta = m; await refresh(); build(); loaders.forEach(f => f(state.settings)); frames();
  setInterval(refresh, 1000);
})();
