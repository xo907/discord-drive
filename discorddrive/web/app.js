"use strict";

/* DiscordDrive web dashboard. No framework: a small element helper, hash routes, fetch. */

const $ = (sel) => document.querySelector(sel);
const main = $("#main");
let status = null;
let route = { name: "", args: [] };

// ------------------------------------------------------------------ helpers
function h(tag, attrs, ...children) {
  const el = tag === "svg" ? document.createElementNS("http://www.w3.org/2000/svg", "svg") : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.setAttribute("class", v);
    else if (k === "style") el.style.cssText = v;      // CSSOM, which the page's CSP allows
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;        // only ever used with constant SVG markup
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const ICONS = {
  folder: '<path d="M2.5 5.5a1.5 1.5 0 0 1 1.5-1.5h3.6l1.6 1.8H16a1.5 1.5 0 0 1 1.5 1.5v7.7A1.5 1.5 0 0 1 16 16.5H4a1.5 1.5 0 0 1-1.5-1.5z"/>',
  file: '<path d="M5 2.5h6.5L15 6v11.5H5z"/><path d="M11.5 2.5V6H15"/>',
  image: '<rect x="3" y="3.5" width="14" height="13" rx="1.5"/><circle cx="7.5" cy="8" r="1.4"/><path d="m3.5 14.5 4-4 3 3 2-2 4 3.5"/>',
  video: '<rect x="2.5" y="4.5" width="11" height="11" rx="1.5"/><path d="m13.5 8.5 4-2.2v7.4l-4-2.2"/>',
  audio: '<path d="M8 14.5V4.5l8-1.5v10"/><circle cx="6" cy="14.5" r="2"/><circle cx="14" cy="13" r="2"/>',
  text: '<path d="M5 2.5h6.5L15 6v11.5H5z"/><path d="M7.5 9.5h5M7.5 12h5M7.5 14.5h3"/>',
  archive: '<path d="M5 2.5h10v15H5z"/><path d="M10 2.5v2M10 6.5v2M10 10.5v2"/>',
  more: '<circle cx="5" cy="10" r=".9"/><circle cx="10" cy="10" r=".9"/><circle cx="15" cy="10" r=".9"/>',
  open: '<path d="M2.5 10s2.8-5 7.5-5 7.5 5 7.5 5-2.8 5-7.5 5-7.5-5-7.5-5z"/><circle cx="10" cy="10" r="2.2"/>',
  enter: '<path d="M8 4.5h6.5a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H8"/><path d="M3.5 10H12M9 7l3 3-3 3"/>',
  download: '<path d="M10 3.5v9M6.5 9 10 12.5 13.5 9M4 16.5h12"/>',
  upload: '<path d="M10 13V4M6.5 7.5 10 4l3.5 3.5M4 16.5h12"/>',
  link: '<path d="M8.5 11.5a3 3 0 0 0 4.2 0l2.4-2.4a3 3 0 0 0-4.2-4.2l-.9.9"/><path d="M11.5 8.5a3 3 0 0 0-4.2 0l-2.4 2.4a3 3 0 0 0 4.2 4.2l.9-.9"/>',
  offline: '<path d="M6 15.5h8.5a3.5 3.5 0 0 0 .4-7 5 5 0 0 0-9.7 1.3A2.9 2.9 0 0 0 6 15.5z"/><path d="m8 11.5 1.6 1.6 3-3"/>',
  rename: '<path d="M4 16h3.2l8.4-8.4a2.2 2.2 0 0 0-3.2-3.2L4 12.8z"/><path d="m11.4 5.4 3.2 3.2"/>',
  move: '<path d="M2.5 5.5a1.5 1.5 0 0 1 1.5-1.5h3.6l1.6 1.8H16a1.5 1.5 0 0 1 1.5 1.5v7.7A1.5 1.5 0 0 1 16 16.5H4a1.5 1.5 0 0 1-1.5-1.5z"/><path d="M7.5 11h5M10.5 9l2 2-2 2"/>',
  copy: '<rect x="6.5" y="6.5" width="9.5" height="9.5" rx="1.5"/><path d="M13.5 6.5V5a1.5 1.5 0 0 0-1.5-1.5H5A1.5 1.5 0 0 0 3.5 5v7A1.5 1.5 0 0 0 5 13.5h1.5"/>',
  history: '<path d="M3.5 10a6.5 6.5 0 1 0 1.9-4.6"/><path d="M3.5 4v3.5H7M10 6.5V10l2.5 1.5"/>',
  info: '<circle cx="10" cy="10" r="7"/><path d="M10 9v4.5M10 6.6v.1"/>',
  trash: '<path d="M4 6h12M8 6V4.5h4V6M5.5 6l.7 9.6a1 1 0 0 0 1 .9h5.6a1 1 0 0 0 1-.9L14.5 6"/>',
  restore: '<path d="M3.5 10a6.5 6.5 0 1 0 1.9-4.6"/><path d="M3.5 4v3.5H7"/>',
  newfolder: '<path d="M2.5 5.5a1.5 1.5 0 0 1 1.5-1.5h3.6l1.6 1.8H16a1.5 1.5 0 0 1 1.5 1.5v7.7A1.5 1.5 0 0 1 16 16.5H4a1.5 1.5 0 0 1-1.5-1.5z"/><path d="M10 8.5v5M7.5 11h5"/>',
  refresh: '<path d="M16 10a6 6 0 1 1-1.8-4.3"/><path d="M16.5 3.5v3.5H13"/>',
  check: '<path d="m4.5 10.5 3.5 3.5 7.5-8"/>',
  user: '<circle cx="10" cy="7" r="3.2"/><path d="M3.8 16.5a6.2 6.2 0 0 1 12.4 0"/>',
  signout: '<path d="M12 4.5H15a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-3"/><path d="M12.5 10H4M7 7l-3 3 3 3"/>',
  close: '<path d="m5 5 10 10M15 5 5 15"/>',
  settings: '<circle cx="10" cy="10" r="2.5"/><path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M4.7 15.3l1.4-1.4M13.9 6.1l1.4-1.4"/>',
  note: '<path d="M5 2.5h10a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-13a1 1 0 0 1 1-1z"/><path d="M7 7h6M7 10h6M7 13h3.5"/>',
  lock: '<rect x="4.5" y="9" width="11" height="8" rx="1.5"/><path d="M7 9V6.5a3 3 0 0 1 6 0V9"/>',
  plus: '<path d="M10 4.5v11M4.5 10h11"/>',
  back: '<path d="M12 4.5 6.5 10l5.5 5.5"/>',
  save: '<path d="M4.5 3.5h9l2 2v11h-11z"/><path d="M7 3.5v4h6v-4M7 16.5v-5h6v5"/>',
};
const icon = (name, cls = "") => h("svg", { viewBox: "0 0 20 20", class: `ico ${cls}`, "aria-hidden": "true", html: ICONS[name] });

const EXT = {
  image: "jpg jpeg png gif webp avif bmp svg heic",
  video: "mp4 m4v webm mov mkv avi",
  audio: "mp3 m4a aac flac wav ogg opus",
  text: "txt md log csv json xml yml yaml ini conf cfg py js ts css html sh bat ps1 c h cpp rs go java toml srt",
  archive: "zip rar 7z tar gz bz2 xz zst iso",
  pdf: "pdf",
};
function kind(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  for (const [k, list] of Object.entries(EXT)) if (list.split(" ").includes(ext)) return k;
  return "file";
}

function size(n) {
  n = Number(n || 0);
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < units.length - 1);
  return `${n >= 100 ? n.toFixed(0) : n.toFixed(1)} ${units[i]}`;
}
const fmtDay = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
const fmtYear = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" });
const fmtTime = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });
const fmtFull = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
function when(t) {
  if (!t) return "";
  const d = new Date(t * 1000), now = new Date();
  if (d.toDateString() === now.toDateString()) return fmtTime.format(d);
  return d.getFullYear() === now.getFullYear() ? fmtDay.format(d) : fmtYear.format(d);
}
function ago(t) {
  const s = Math.max(0, Date.now() / 1000 - t);
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400 * 1.5) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}
function speed(bps) { return bps > 0 ? size(bps) + "/s" : ""; }
function eta(sec) {
  if (sec == null || !isFinite(sec)) return "";
  sec = Math.max(1, Math.round(sec));
  if (sec < 60) return `${sec} s left`;
  if (sec < 3600) return `${Math.round(sec / 60)} min left`;
  return `${Math.floor(sec / 3600)} h ${Math.round((sec % 3600) / 60)} min left`;
}
const plural = (n, one, many) => `${Number(n).toLocaleString()} ${n === 1 ? one : many || one + "s"}`;

function join(dir, name) { return (dir === "/" ? "" : dir) + "/" + name; }
function parent(path) { const i = path.lastIndexOf("/"); return i <= 0 ? "/" : path.slice(0, i); }
function base(path) { return path.slice(path.lastIndexOf("/") + 1); }
function enc(path) { return path.split("/").map(encodeURIComponent).join("/"); }

// ------------------------------------------------------------------ api
async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-DD": "1" }, body: JSON.stringify(body),
  };
  const r = await fetch(path, { credentials: "same-origin", ...opts });
  if (r.status === 401) { location.reload(); throw new Error("Signed out"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
  return data;
}
const q = (params) => "?" + new URLSearchParams(params).toString();
const fileUrl = (path, dl) => "/api/file" + q(dl ? { path, dl: 1 } : { path });

let toastTimer;
function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("on"), 3200);
}
async function attempt(fn, ok) {
  try { const r = await fn(); if (ok) toast(ok); return r; }
  catch (e) { toast(e.message); return null; }
}

// ------------------------------------------------------------------ dialog
function ask({ title, text = "", value = null, ok = "OK", danger = false }) {
  const dlg = $("#dialog");
  $("#dialog-title").textContent = title;
  $("#dialog-text").textContent = text;
  const input = $("#dialog-input");
  input.hidden = value === null;
  input.value = value || "";
  const okBtn = $("#dialog-ok");
  okBtn.textContent = ok;
  okBtn.className = danger ? "btn danger" : "btn";
  input.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); dlg.close("ok"); } };
  return new Promise((resolve) => {
    dlg.onclose = () => resolve(dlg.returnValue === "ok" ? (value === null ? true : input.value.trim()) : null);
    dlg.returnValue = "";
    dlg.showModal();
    if (value !== null) {
      input.focus();
      const dot = input.value.lastIndexOf(".");
      input.setSelectionRange(0, dot > 0 ? dot : input.value.length);
    }
  });
}

// ------------------------------------------------------------------ context menu
// Right-click (desktop) or long press (touch) opens it: a small menu at the pointer on desktop,
// a sheet from the bottom of the screen on phones. Items: {label, icon, run, danger, checked, disabled}
// or "-" for a divider.
let ctxEl = null;
let ctxFor = null;           // the row whose menu is open (highlighted meanwhile)
let lastTouch = 0;
const sheetMode = () => matchMedia("(hover: none), (max-width: 760px)").matches;

function closeMenu() {
  if (ctxFor) { ctxFor.classList.remove("menu-on"); ctxFor = null; }
  if (!ctxEl) return;
  ctxEl.remove();
  $("#ctx-scrim")?.remove();
  ctxEl = null;
}

function openMenu(items, x, y, title, sub, anchor) {
  closeMenu();
  if (anchor && anchor.classList.contains("row")) { ctxFor = anchor; anchor.classList.add("menu-on"); }
  const asSheet = sheetMode();
  const buttons = [];
  const list = items.filter(Boolean).filter((it, i, all) => it !== "-" || (i > 0 && all[i - 1] !== "-" && i < all.length - 1));
  const el = h("div", { class: "ctx" + (asSheet ? " as-sheet" : ""), role: "menu", "aria-label": title || "Actions" },
    asSheet && title ? h("div", { class: "ctx-title" }, h("div", { class: "t" }, title), sub && h("div", { class: "s" }, sub)) : null,
    list.map((it) => {
      if (it === "-") return h("div", { class: "sep", role: "separator" });
      const b = h("button", { role: it.checked != null ? "menuitemcheckbox" : "menuitem", class: it.danger ? "danger" : "",
                              disabled: it.disabled, "aria-checked": it.checked != null ? String(!!it.checked) : null,
                              onclick: () => { closeMenu(); if (it.run) it.run(); } },
        icon(it.icon || "more"), h("span", { class: "l" }, it.label),
        it.checked != null ? h("span", { class: "on" + (it.checked ? " yes" : "") }, it.checked ? icon("check") : null) : null);
      buttons.push(b);
      return b;
    }));
  const scrim = h("div", { id: "ctx-scrim", class: "ctx-scrim" + (asSheet ? " dim" : ""), onclick: closeMenu,
                           oncontextmenu: (e) => { e.preventDefault(); closeMenu(); } });
  document.body.append(scrim, el);
  ctxEl = el;
  if (!asSheet) {
    const r = el.getBoundingClientRect();
    el.style.left = Math.max(8, Math.min(x, innerWidth - r.width - 8)) + "px";
    el.style.top = Math.max(8, y + r.height > innerHeight - 8 ? y - r.height : y) + "px";
  }
  const usable = buttons.filter((b) => !b.disabled);
  if (!asSheet && usable.length) usable[0].focus({ preventScroll: true });
  el.addEventListener("keydown", (e) => {
    const i = usable.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); usable[(i + 1) % usable.length].focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); usable[(i - 1 + usable.length) % usable.length].focus(); }
    else if (e.key === "Escape" || e.key === "Tab") { e.preventDefault(); closeMenu(); }
  });
}
window.addEventListener("resize", closeMenu);
main.addEventListener("scroll", closeMenu, { passive: true });

/** Right-click and long press on `el` open the menu that `items()` returns. */
function bindMenu(el, items, title, sub, skip) {
  el.addEventListener("contextmenu", (e) => {
    if (skip && skip(e)) return;
    e.preventDefault();
    e.stopPropagation();
    if (Date.now() - lastTouch < 1200) return;          // the long-press timer already opened it
    openMenu(items(), e.clientX, e.clientY, title, sub, el);
  });
  let timer = null, sx = 0, sy = 0;
  el.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" || (skip && skip(e))) return;
    sx = e.clientX; sy = e.clientY;
    clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      lastTouch = Date.now();
      el.dataset.longPress = "1";
      if (navigator.vibrate) navigator.vibrate(8);
      openMenu(items(), sx, sy, title, sub, el);
    }, 480);
  });
  const cancel = () => { clearTimeout(timer); timer = null; };
  el.addEventListener("pointermove", (e) => { if (timer && Math.hypot(e.clientX - sx, e.clientY - sy) > 10) cancel(); });
  el.addEventListener("pointerup", cancel);
  el.addEventListener("pointercancel", cancel);
  el.addEventListener("click", (e) => {
    if (el.dataset.longPress) { e.preventDefault(); e.stopImmediatePropagation(); delete el.dataset.longPress; }
  }, true);
}

function menuButton(items, title, sub) {
  return h("button", { class: "icon-btn more", "aria-label": `Actions for ${title}`, "aria-haspopup": "menu", title: "Actions",
                       onclick: (e) => {
                         e.preventDefault(); e.stopPropagation();
                         const r = e.currentTarget.getBoundingClientRect();
                         openMenu(items(), r.right - 220, r.bottom + 4, title, sub, e.currentTarget.closest(".row"));
                       } }, icon("more"));
}

function itemMenu(it) {
  return [
    it.dir ? { label: "Open", icon: "enter", run: () => go("#/files" + enc(it.path)) }
           : { label: "Preview", icon: "open", run: () => openItem(it) },
    it.dir ? { label: "Download as ZIP", icon: "download", run: () => download("/api/zip" + q({ path: it.path }), it.name + ".zip") }
           : { label: "Download", icon: "download", run: () => download(fileUrl(it.path, true), it.name) },
    { label: "Share…", icon: "link", run: () => shareDialog(it) },
    "-",
    { label: "Available offline", icon: "offline", checked: !!it.pinned, run: () => setPinned(it, !it.pinned) },
    "-",
    { label: "Rename…", icon: "rename", run: () => rename(it) },
    { label: "Move to…", icon: "move", run: () => moveTo(it) },
    !it.dir && { label: "Duplicate", icon: "copy", run: () => duplicate(it) },
    !it.dir && { label: "Earlier versions", icon: "history", run: () => openItem(it, "versions") },
    { label: "Details", icon: "info", run: () => openItem(it) },
    route.name === "files" && { label: sel.has(it.path) ? "Deselect" : "Select", icon: "check", run: () => toggleSel(it.path) },
    "-",
    { label: "Delete", icon: "trash", danger: true, run: () => remove(it) },
  ];
}

function backgroundMenu() {
  return [
    { label: "New folder…", icon: "newfolder", run: newFolder },
    { label: "Upload files…", icon: "upload", run: () => $("#pick").click() },
    { label: "Upload a folder…", icon: "upload", run: () => $("#pick-dir").click() },
    currentDir !== "/" && { label: "Download this folder as ZIP", icon: "download",
                            run: () => download("/api/zip" + q({ path: currentDir }), base(currentDir) + ".zip") },
    "-",
    { label: "Refresh", icon: "refresh", run: render },
  ];
}

function download(url, name) {
  const a = h("a", { href: url, download: name, style: "display:none" });
  document.body.append(a);
  a.click();
  a.remove();
}

// ------------------------------------------------------------------ status
async function refreshStatus() {
  try { status = await api("/api/status"); }
  catch { status = null; }
  const dot = $("#sync-dot"), text = $("#sync-text");
  if (!status) { dot.className = "dot warn"; text.textContent = "Not reachable"; return; }
  const st = status.stats;
  const busy = status.uploads.length + status.queued + st.unsynced;
  if (busy) { dot.className = "dot busy"; text.textContent = `Uploading ${st.unsynced || busy}`; }
  else if (st.outbox) { dot.className = "dot busy"; text.textContent = "Syncing"; }
  else { dot.className = "dot ok"; text.textContent = "Up to date"; }
  $("#usage").textContent = `${plural(st.files, "file")} · ${size(st.bytes)}`;
  showDiscordUploads(status.uploads);
  if (note && route.name === "notes") noteUploadState();
  const acct = $("#account");
  if (acct && status.user) { acct.textContent = status.user.slice(0, 1).toUpperCase(); acct.title = `Signed in as ${status.user}`; }
  if (route.name === "health" && !$("#sheet").classList.contains("open")) {
    keepScroll = true;
    try { renderHealth(true); } finally { keepScroll = false; }
  }
}

// ------------------------------------------------------------------ routing
function go(hash) { if (location.hash !== hash) location.hash = hash; else render(); }
function parseRoute() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [name, ...rest] = raw.split("/");
  const qs = raw.includes("?") ? new URLSearchParams(raw.slice(raw.indexOf("?") + 1)) : new URLSearchParams();
  const args = rest.join("/").split("?")[0];
  return { name: (name || "files").split("?")[0], path: "/" + decodeURIComponent(args).replace(/^\/+|\/+$/g, ""), qs, rest };
}
function render() {
  route = parseRoute();
  for (const a of document.querySelectorAll("#nav a")) {
    const n = a.dataset.nav;
    a.classList.toggle("on", n === route.name || (n === "snapshots" && route.name === "snapshot"));
  }
  closeSheet();
  leaveNotes();
  if (route.name !== "files" || route.path !== currentDir) sel.clear();
  const views = { files: renderFiles, search: renderSearch, deleted: renderDeleted, snapshots: renderSnapshots,
                  snapshot: renderSnapshot, health: renderHealth, notes: renderNotes, shared: renderShared,
                  settings: renderSettings, log: renderLog };
  (views[route.name] || renderFiles)();
}
window.addEventListener("hashchange", render);

let keepScroll = false;
function page(...children) {
  main.replaceChildren(h("div", { class: "page" }, ...children));
  if (!keepScroll) main.scrollTop = 0;
}

function crumbs(path, root, hrefFor) {
  const parts = path.split("/").filter(Boolean);
  const out = [h(parts.length ? "a" : "span", parts.length ? { href: hrefFor("/") } : {}, root)];
  let cur = "";
  parts.forEach((p, i) => {
    cur += "/" + p;
    out.push(h("span", { class: "sep" }, "/"));
    out.push(i === parts.length - 1 ? h("span", {}, p) : h("a", { href: hrefFor(cur) }, p));
  });
  return h("nav", { class: "crumbs", "aria-label": "Folder" }, out);
}

// ------------------------------------------------------------------ files
let currentDir = "/";

function itemRow(it, opts = {}) {
  const k = it.dir ? "folder" : kind(it.name);
  const tags = [];
  if (it.state && it.state !== "synced") tags.push(h("span", { class: "tag busy" }, it.state === "error" ? "Retrying" : "Uploading"));
  if (it.pinned) tags.push(h("span", { class: "tag" }, "Offline"));
  const label = h("span", { class: "label" }, it.name);
  const name = h("span", { class: "name" }, icon(k === "pdf" ? "text" : k, it.dir ? "folder" : ""),
                 opts.where ? h("span", { style: "min-width:0" }, label, h("div", { class: "where" }, parent(it.path))) : label,
                 ...tags);
  const sub = it.dir ? parent(it.path) : `${size(it.size)} · ${when(it.mtime)}`;
  const more = menuButton(() => itemMenu(it), it.name, sub);
  const attrs = it.dir ? { class: "row", href: "#/files" + enc(it.path) }
                       : { class: "row click", tabindex: "0", role: "button",
                           onclick: () => openItem(it), onkeydown: (e) => { if (e.key === "Enter") openItem(it); } };
  const row = h(it.dir ? "a" : "div", attrs, name,
                h("span", { class: "size" }, it.dir ? "" : size(it.size)),
                h("span", { class: "date" }, when(it.mtime)), more);
  bindMenu(row, () => itemMenu(it), it.name, sub);
  if (route.name === "files") {
    makeDraggable(row, it);
    const box = h("button", { class: "cb row-cb", role: "checkbox", "aria-checked": String(sel.has(it.path)),
                              "aria-label": `Select ${it.name}`, tabindex: "-1",
                              onclick: (e) => { e.preventDefault(); e.stopPropagation(); toggleSel(it.path); } }, icon("check"));
    row.querySelector(".name").prepend(box);
  }
  if (it.dir) dropTarget(row, it.path);
  return row;
}

function listHead() {
  return h("div", { class: "row head" }, h("span", {}, "Name"), h("span", { class: "size" }, "Size"),
           h("span", { class: "date" }, "Modified"), h("span"));
}

async function renderFiles() {
  const path = route.path;
  currentDir = path;
  const data = await attempt(() => api("/api/list" + q({ path })));
  if (!data) {
    page(h("div", { class: "empty" }, h("b", {}, "This folder isn't there any more"), h("a", { href: "#/files/" }, "Back to the drive")));
    return;
  }
  const bar = h("div", { class: "bar" },
    crumbs(path, "Drive", (p) => "#/files" + enc(p)),
    h("div", { class: "actions" },
      h("button", { class: "btn ghost", onclick: newFolder }, "New folder"),
      h("button", { class: "btn", onclick: () => $("#pick").click() }, "Upload")));
  listed = data.items;
  const rows = data.items.map((it) => itemRow(it));
  const body = rows.length ? h("div", { class: "list" }, listHead(), rows)
    : h("div", { class: "empty" }, h("b", {}, "Nothing here yet"), "Drop files anywhere on this page, or use Upload.");
  page(bar, selBar, body, h("div", { class: "spacer" }));
  for (const a of bar.querySelectorAll(".crumbs a")) {
    dropTarget(a, "/" + decodeURIComponent(a.getAttribute("href").replace(/^#\/files\/?/, "")).replace(/\/+$/, ""));
  }
  syncSel();
}

// ------------------------------------------------------------------ selection, drag and drop
// Ctrl/Cmd-click selects, Shift-click selects a range; drag a row (or the selection) onto a folder,
// a part of the path at the top, or "Files" to move it, onto "Deleted" to delete it. Files dragged
// in from the computer upload into the folder they are dropped on.
let listed = [];
const sel = new Set();
let anchorPath = null;
let dragging = null;
const selBar = h("div", { class: "selbar files-sel" });

function toggleSel(path) { sel.has(path) ? sel.delete(path) : sel.add(path); anchorPath = path; syncSel(); }

function syncSel() {
  for (const r of main.querySelectorAll(".row[data-path]")) {
    r.classList.toggle("sel", sel.has(r.dataset.path));
    const box = r.querySelector(".row-cb");
    if (box) box.setAttribute("aria-checked", String(sel.has(r.dataset.path)));
  }
  main.classList.toggle("selecting", sel.size > 0);
  const n = sel.size;
  selBar.hidden = !n;
  if (!n) return;
  selBar.replaceChildren(h("span", { class: "count" }, `${plural(n, "item")} selected`),
    h("div", { class: "actions" },
      h("button", { class: "btn ghost small", onclick: () => { sel.clear(); syncSel(); } }, "Clear"),
      h("button", { class: "btn ghost small", onclick: () => moveMany([...sel]) }, "Move to…"),
      h("button", { class: "btn danger small", onclick: () => deleteMany([...sel]) }, "Delete")));
}

function clickSelect(e, it) {
  if (route.name !== "files") return false;
  if (e.shiftKey && anchorPath) {
    const paths = listed.map((x) => x.path);
    const [a, b] = [paths.indexOf(anchorPath), paths.indexOf(it.path)].sort((x, y) => x - y);
    if (a >= 0) paths.slice(a, b + 1).forEach((p) => sel.add(p));
    syncSel();
    return true;
  }
  if (e.ctrlKey || e.metaKey) { toggleSel(it.path); return true; }
  if (sel.size) { sel.clear(); syncSel(); }
  return false;
}

function makeDraggable(row, it) {
  row.dataset.path = it.path;
  row.addEventListener("click", (e) => {
    if (e.target.closest(".row-cb")) return;          // the checkbox toggles on its own
    if (clickSelect(e, it)) { e.preventDefault(); e.stopImmediatePropagation(); }
  }, true);
  if (sheetMode()) return;
  row.draggable = true;
  row.addEventListener("dragstart", (e) => {
    dragging = sel.has(it.path) ? [...sel] : [it.path];
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", dragging.join("\n"));
    const chip = h("div", { class: "drag-chip" }, dragging.length === 1 ? it.name : plural(dragging.length, "item"));
    document.body.append(chip);
    e.dataTransfer.setDragImage(chip, 12, 14);
    setTimeout(() => chip.remove(), 0);
    for (const r of main.querySelectorAll(".row[data-path]")) if (dragging.includes(r.dataset.path)) r.classList.add("dragging");
  });
  row.addEventListener("dragend", () => {
    dragging = null;
    for (const r of document.querySelectorAll(".dragging, .drop-into")) r.classList.remove("dragging", "drop-into");
  });
}

const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
function canMove(paths, dest) {
  return paths.some((p) => p !== dest && !dest.startsWith(p + "/") && parent(p) !== dest);
}

/** Dropping on `el`: move what is dragged into folder `dest` (or delete it), or upload files from the computer. */
function dropTarget(el, dest, action = "move") {
  el.addEventListener("dragover", (e) => {
    if (dragging ? (action === "move" && !canMove(dragging, dest)) : (!hasFiles(e) || action !== "move")) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = dragging ? "move" : "copy";
    el.classList.add("drop-into");
    if (!dragging) $("#drop-to").textContent = dest === "/" ? "Drive" : base(dest);
  });
  el.addEventListener("dragleave", (e) => { if (!el.contains(e.relatedTarget)) el.classList.remove("drop-into"); });
  el.addEventListener("drop", async (e) => {
    el.classList.remove("drop-into");
    if (dragging) {
      e.preventDefault();
      e.stopPropagation();
      const paths = dragging;
      dragging = null;
      if (action === "delete") deleteMany(paths);
      else moveMany(paths, dest);
    } else if (hasFiles(e) && action === "move") {
      e.preventDefault();
      e.stopPropagation();
      dragDepth = 0;
      drop.classList.remove("on");
      uploadAll(await droppedFiles(e), dest);
    }
  });
}

async function moveMany(paths, dest) {
  if (dest === undefined) {
    dest = await pickFolder(paths.length === 1 ? `Move “${base(paths[0])}”` : `Move ${plural(paths.length, "item")}`,
                            parent(paths[0]), paths);
    if (dest == null) return;
  }
  let moved = 0;
  for (const p of paths) {
    if (p === dest || dest.startsWith(p + "/") || parent(p) === dest) continue;
    if (await attempt(() => api("/api/move", { from: p, to: join(dest, base(p)) }))) moved++;
  }
  if (moved) toast(`Moved ${moved === 1 ? base(paths[0]) : plural(moved, "item")} to ${dest === "/" ? "Drive" : base(dest)}`);
  sel.clear();
  closeSheet();
  render();
}

async function deleteMany(paths) {
  const one = paths.length === 1;
  const ok = await ask({ title: one ? `Delete “${base(paths[0])}”?` : `Delete ${plural(paths.length, "item")}?`, ok: "Delete",
                         danger: true, text: "Deleted on every device. You can recover files from Deleted for a while." });
  if (!ok) return;
  let n = 0;
  for (const p of paths) if (await attempt(() => api("/api/delete", { path: p }))) n++;
  if (n) toast(one ? "Deleted" : `${plural(n, "item")} deleted`);
  sel.clear();
  render();
}

document.addEventListener("keydown", (e) => {
  if (route.name !== "files" || e.target.closest("input, textarea, dialog")) return;
  if (e.key === "Escape" && sel.size) { sel.clear(); syncSel(); }
  else if ((e.key === "Delete" || e.key === "Backspace") && sel.size) { e.preventDefault(); deleteMany([...sel]); }
  else if (e.key.toLowerCase() === "a" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); listed.forEach((it) => sel.add(it.path)); syncSel(); }
});

// Box selection: press on empty space and drag; rows the box touches are selected
// (Ctrl/Cmd/Shift keeps what was already selected).
(function boxSelect() {
  let start = null, box = null, before = null, scrollTimer = null, last = null;
  main.addEventListener("pointerdown", (e) => {
    if (route.name !== "files" || e.button !== 0 || e.pointerType !== "mouse") return;
    if (e.target.closest(".row:not(.head), button, a, input, textarea, .selbar, .bar")) return;
    start = { x: e.clientX, y: e.clientY + main.scrollTop };
    before = e.ctrlKey || e.metaKey || e.shiftKey ? new Set(sel) : new Set();
    e.preventDefault();
  });
  function update(e) {
    last = e;
    const y = e.clientY + main.scrollTop;
    const r = { left: Math.min(start.x, e.clientX), right: Math.max(start.x, e.clientX),
                top: Math.min(start.y, y) - main.scrollTop, bottom: Math.max(start.y, y) - main.scrollTop };
    if (!box) {
      if (Math.hypot(e.clientX - start.x, y - start.y) < 6) return;
      box = h("div", { class: "marquee" });
      document.body.append(box);
    }
    Object.assign(box.style, { left: r.left + "px", top: r.top + "px", width: r.right - r.left + "px", height: r.bottom - r.top + "px" });
    sel.clear();
    before.forEach((p) => sel.add(p));
    for (const row of main.querySelectorAll(".row[data-path]")) {
      const b = row.getBoundingClientRect();
      if (b.bottom > r.top && b.top < r.bottom && b.right > r.left && b.left < r.right) sel.add(row.dataset.path);
    }
    syncSel();
  }
  window.addEventListener("pointermove", (e) => {
    if (!start) return;
    update(e);
    clearInterval(scrollTimer);
    const m = main.getBoundingClientRect();
    const dir = e.clientY < m.top + 30 ? -1 : e.clientY > m.bottom - 30 ? 1 : 0;
    if (dir && box) scrollTimer = setInterval(() => { main.scrollTop += dir * 18; if (last) update(last); }, 30);
  });
  window.addEventListener("pointerup", () => {
    clearInterval(scrollTimer);
    if (box) { box.remove(); box = null; if (sel.size) anchorPath = [...sel].pop(); }
    else if (start && !before.size && sel.size) { sel.clear(); syncSel(); }   // a plain click on empty space
    start = null;
  });
})();

// ------------------------------------------------------------------ modal + folder picker
function modal(title, ...content) {
  const dlg = h("dialog", { class: "modal" });
  const close = () => dlg.close();
  dlg.addEventListener("close", () => dlg.remove());
  dlg.addEventListener("click", (e) => { if (e.target === dlg) close(); });
  dlg.append(h("div", { class: "modal-head" }, h("h3", {}, title),
                 h("button", { class: "icon-btn", "aria-label": "Close", onclick: close }, icon("close"))),
             h("div", { class: "modal-body" }, ...content));
  document.body.append(dlg);
  dlg.showModal();
  return { dlg, close };
}

function pickFolder(title, start, moving = []) {
  return new Promise((resolve) => {
    let cur = start || "/";
    let chosen = null;
    const list = h("div", { class: "picker-list" });
    const where = h("div", { class: "picker-where" });
    const here = h("button", { class: "btn", onclick: () => { chosen = cur; m.close(); } }, "Move here");
    const m = modal(title, where, list,
      h("div", { class: "modal-actions" },
        h("button", { class: "btn ghost", onclick: async () => {
          const name = await ask({ title: "New folder", value: "", ok: "Create" });
          if (name && await attempt(() => api("/api/mkdir", { path: join(cur, name) }))) load(join(cur, name));
        } }, "New folder"),
        here));
    m.dlg.addEventListener("close", () => resolve(chosen));
    async function load(path) {
      cur = path;
      const data = await api("/api/list" + q({ path })).catch(() => null);
      const parts = path.split("/").filter(Boolean);
      where.replaceChildren(...["Drive", ...parts].flatMap((name, i) => {
        const target = "/" + parts.slice(0, i).join("/");
        const el = i === parts.length ? h("span", {}, name) : h("button", { class: "link", onclick: () => load(target) }, name);
        return i ? [h("span", { class: "sep" }, "/"), el] : [el];
      }));
      const dirs = (data ? data.items : []).filter((it) => it.dir);
      list.replaceChildren(...(dirs.length ? dirs.map((d) => {
        const blocked = moving.some((p) => d.path === p || d.path.startsWith(p + "/"));
        return h("button", { class: "picker-row", disabled: blocked, onclick: () => load(d.path) },
                 icon("folder", "folder"), h("span", {}, d.name), icon("enter"));
      }) : [h("div", { class: "muted picker-empty" }, "No folders in here")]));
      here.disabled = moving.length > 0 && !canMove(moving, path);
    }
    load(cur);
  });
}
bindMenu(main, backgroundMenu, "This folder", null,
         (e) => route.name !== "files" || !!e.target.closest(".row, button, a, input"));

async function newFolder() {
  const name = await ask({ title: "New folder", value: "", ok: "Create" });
  if (!name) return;
  if (await attempt(() => api("/api/mkdir", { path: join(currentDir, name) }))) render();
}

async function renderSearch() {
  const text = route.qs.get("q") || "";
  $("#q").value = text;
  const data = await attempt(() => api("/api/search" + q({ q: text })));
  const items = data ? data.items : [];
  page(h("div", { class: "bar" }, h("div", { class: "crumbs" }, h("span", {}, `Results for “${text}”`))),
       items.length ? h("div", { class: "list" }, listHead(), items.map((it) => itemRow(it, { where: true })))
                    : h("div", { class: "empty" }, h("b", {}, "No matches"), "Try part of the name."));
}

let searchTimer;
$("#q").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  const v = e.target.value.trim();
  searchTimer = setTimeout(() => {
    if (v.length >= 2) go("#/search?" + new URLSearchParams({ q: v }));
    else if (!v && route.name === "search") go("#/files/");
  }, 220);
});

// ------------------------------------------------------------------ item sheet
function closeSheet() {
  $("#sheet").classList.remove("open");
  $("#sheet").setAttribute("aria-hidden", "true");
  $("#scrim").classList.remove("open");
  for (const m of $("#sheet-body").querySelectorAll("video, audio")) m.pause();
}
$("#sheet-close").onclick = closeSheet;
$("#scrim").onclick = closeSheet;
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#dialog").open) closeSheet(); });

function preview(it) {
  const url = fileUrl(it.path);
  const k = kind(it.name);
  if (it.dir) return h("div", { class: "preview" }, icon("folder", "big folder"));
  if (k === "image") return h("div", { class: "preview" }, h("img", { src: url, alt: it.name }));
  if (k === "video") return h("div", { class: "preview" }, h("video", { src: url, controls: true, preload: "metadata", playsinline: true }));
  if (k === "audio") return h("div", { class: "preview" }, h("audio", { src: url, controls: true, preload: "metadata" }));
  if (k === "pdf" && it.size < 64 * 2 ** 20) return h("div", { class: "preview" }, h("iframe", { src: url, title: it.name }));
  if (k === "text" && it.size < 2 * 2 ** 20) {
    const pre = h("pre", {}, "Loading…");
    fetch(url, { credentials: "same-origin", headers: { Range: "bytes=0-262143" } })
      .then((r) => r.text()).then((t) => { pre.textContent = t; }).catch(() => { pre.textContent = "Could not load a preview."; });
    return h("div", { class: "preview text" }, pre);
  }
  return h("div", { class: "preview" }, h("div", { class: "note" }, icon(k === "file" ? "file" : k, "big"), h("div", {}, "No preview for this kind of file")));
}

async function setPinned(it, on) {
  if (await attempt(() => api("/api/pin", { path: it.path, on }),
                    on ? "Downloading it to keep it available offline" : "No longer kept offline")) {
    it.pinned = on;
    if (route.name === "files" || route.name === "search") render();
    return true;
  }
  return false;
}

function openItem(it, focus) {
  $("#sheet-title").textContent = it.name;
  const body = $("#sheet-body");
  const meta = h("dl", { class: "meta" },
    h("dt", {}, "Location"), h("dd", {}, parent(it.path)),
    !it.dir && [h("dt", {}, "Size"), h("dd", {}, `${size(it.size)} (${Number(it.size).toLocaleString()} bytes)`)],
    h("dt", {}, "Modified"), h("dd", {}, it.mtime ? fmtFull.format(new Date(it.mtime * 1000)) : "—"),
    !it.dir && [h("dt", {}, "Stored"), h("dd", {}, it.state === "synced" ? "In Discord" : "Waiting to upload")]);
  const actions = h("div", { class: "sheet-actions" },
    !it.dir && h("a", { class: "btn", href: fileUrl(it.path, true), download: it.name }, "Download"),
    h("button", { class: "btn ghost", onclick: () => shareDialog(it) }, "Share…"),
    h("button", { class: "btn ghost", onclick: () => rename(it) }, "Rename"),
    h("button", { class: "btn danger", onclick: () => remove(it) }, "Delete"));
  const sw = h("button", { class: "switch", role: "switch", "aria-checked": String(!!it.pinned), "aria-label": "Available offline",
                           onclick: async () => {
                             const on = sw.getAttribute("aria-checked") !== "true";
                             const isOpen = $("#sheet").classList.contains("open");
                             if (await setPinned(it, on)) {
                               sw.setAttribute("aria-checked", String(on));
                               if (isOpen && !$("#sheet").classList.contains("open")) openItem(it);
                             }
                           } });
  const toggle = h("div", { class: "toggle" },
    h("div", {}, h("div", { class: "t" }, "Available offline"),
      h("div", { class: "s" }, it.dir ? "Everything in it, including new files, stays downloaded on the computer running the drive"
                                      : "Stays downloaded on the computer running the drive, so it opens instantly")),
    sw);
  const extra = h("div");
  body.replaceChildren(preview(it), meta, actions, toggle, extra);
  if (!it.dir) loadVersions(it, extra, focus === "versions");
  $("#sheet").classList.add("open");
  $("#sheet").setAttribute("aria-hidden", "false");
  $("#scrim").classList.add("open");
}

async function loadVersions(it, into, focus) {
  const data = await api("/api/versions" + q({ path: it.path })).catch(() => null);
  if (!data || !data.versions.length) {
    if (focus) into.append(h("div", { class: "versions" }, h("h3", {}, "Earlier versions"), h("p", { class: "muted" }, "None kept for this file.")));
    return;
  }
  const reasons = { replaced: "Replaced", deleted: "Deleted", conflict: "Edited on two devices" };
  const box = h("div", { class: "versions" }, h("h3", {}, "Earlier versions"),
    data.versions.map((v) => h("div", { class: "v" },
      h("span", { class: "when" }, fmtFull.format(new Date(v.at * 1000)), " ", h("span", { class: "why" }, reasons[v.reason] || v.reason)),
      h("span", { class: "num muted" }, size(v.size)),
      h("button", { class: "btn ghost small", onclick: async () => {
        const ok = await ask({ title: "Bring back this version?", ok: "Restore",
                               text: "The current content is kept as an earlier version, so you can switch back." });
        if (ok && await attempt(() => api("/api/versions/restore", { path: it.path, n: v.n }), "Restored. It updates on every device in a few seconds.")) {
          closeSheet(); setTimeout(render, 2500);
        }
      } }, "Restore"))));
  into.append(box);
  if (focus) box.scrollIntoView({ block: "start", behavior: "smooth" });
}

const EXPIRY = [["1 hour", 1], ["1 day", 24], ["7 days", 168], ["30 days", 720], ["Never", 0]];
const isLocal = () => ["127.0.0.1", "localhost", "::1", "[::1]"].includes(location.hostname);
/** The address to give out: the one you are browsing from, unless that is this computer itself. */
function shareUrl(r) {
  if (!isLocal()) return location.origin + r.path;
  return r.url || (r.lan && r.lan[0]) || location.origin + r.path;
}

function switchEl(on, change, label) {
  const b = h("button", { type: "button", class: "switch", role: "switch", "aria-checked": String(!!on), "aria-label": label,
                          onclick: () => { const v = b.getAttribute("aria-checked") !== "true"; b.setAttribute("aria-checked", String(v)); change(v); } });
  return b;
}

function field(label, control, hint) {
  return h("div", { class: "field" }, h("div", { class: "fl" }, label), control, hint && h("div", { class: "hint" }, hint));
}

function linkBox(url, note) {
  const input = h("input", { value: url, readonly: true, onclick: (e) => e.target.select() });
  return h("div", { class: "share-done" },
    h("div", { class: "share-url" }, input,
      h("button", { class: "btn small", type: "button", onclick: async () => {
        try { await navigator.clipboard.writeText(url); toast("Link copied"); } catch { input.select(); document.execCommand("copy"); toast("Link copied"); }
      } }, "Copy")),
    note && h("div", { class: "hint" }, note));
}

function shareDialog(it, existing) {
  let hours = existing ? null : 168;
  let download = existing ? existing.download : true;
  let clearPw = false;
  const seg = h("div", { class: "seg", role: "radiogroup" }, EXPIRY.map(([label, v]) =>
    h("button", { type: "button", role: "radio", "aria-checked": String(v === hours),
                  onclick: (e) => { hours = v; for (const b of seg.children) b.setAttribute("aria-checked", String(b === e.currentTarget)); } }, label)));
  const pw = h("input", { type: "password", autocomplete: "new-password",
                          placeholder: existing && existing.password ? "Unchanged" : "None" });
  const result = h("div");
  const form = h("div", { class: "share-form" },
    field("Link works for", seg, existing ? `Now: ${existing.expires ? "until " + fmtFull.format(new Date(existing.expires * 1000)) : "no expiry"}` : null),
    field("Password", pw, existing && existing.password
      ? h("button", { type: "button", class: "link", onclick: (e) => { clearPw = true; pw.value = ""; pw.placeholder = "None"; e.target.remove(); } }, "Remove the password")
      : "Optional. People need it to open the link."),
    h("div", { class: "toggle" },
      h("div", {}, h("div", { class: "t" }, "Allow downloading"),
        h("div", { class: "s" }, "Off: people can view it on the page but get no download button")),
      switchEl(download, (v) => { download = v; }, "Allow downloading")));
  const go = h("button", { class: "btn", type: "button", onclick: async () => {
    go.disabled = true;
    let r;
    if (existing) {
      const body = { id: existing.id, download };
      if (hours !== null) body.hours = hours;
      if (pw.value || clearPw) body.password = pw.value;
      r = await attempt(() => api("/api/shares/update", body), "Link updated");
      if (r) { m.close(); if (route.name === "shared") renderShared(); }
    } else {
      r = await attempt(() => api("/api/share", { path: it.path, hours, password: pw.value, download }));
      if (r) {
        const url = shareUrl(r);
        form.remove();
        go.remove();
        const reach = isLocal() && !r.url && !(r.lan && r.lan.length)
          ? "It only opens on this computer. Set a domain name or turn on “On your network” in Settings to share it."
          : `Anyone with the link${r.password ? " and the password" : ""} can ${download ? "view and download" : "view"} ${it.dir ? "this folder" : "this file"}.`;
        result.replaceChildren(linkBox(url, reach));
        try { await navigator.clipboard.writeText(url); toast("Link copied"); } catch { /* the box is there to copy from */ }
        if (route.name === "shared") renderShared();
      }
    }
    go.disabled = false;
  } }, existing ? "Save" : "Create link");
  const m = modal(existing ? `Link to “${base(existing.item || "deleted item")}”` : `Share “${it.name}”`,
                  form, result, h("div", { class: "modal-actions" }, go));
}

function moveTo(it) { return moveMany([it.path]); }

async function duplicate(it) {
  const dot = it.name.lastIndexOf(".");
  const [stem, ext] = dot > 0 ? [it.name.slice(0, dot), it.name.slice(dot)] : [it.name, ""];
  const name = await ask({ title: "Duplicate", value: `${stem} copy${ext}`, ok: "Duplicate",
                           text: "The copy reuses the pieces already in Discord, so nothing is uploaded again." });
  if (!name) return;
  if (await attempt(() => api("/api/copy", { from: it.path, to: join(parent(it.path), name) }), "Duplicated")) render();
}

async function rename(it) {
  const name = await ask({ title: "Rename", value: it.name, ok: "Rename" });
  if (!name || name === it.name) return;
  if (await attempt(() => api("/api/move", { from: it.path, to: join(parent(it.path), name) }))) { closeSheet(); render(); }
}

async function remove(it) {
  const ok = await ask({ title: `Delete “${it.name}”?`, ok: "Delete", danger: true,
                         text: it.dir ? "The folder and everything in it are deleted on every device. Files can be recovered from Deleted for a while."
                                      : "It is deleted on every device. You can recover it from Deleted for a while." });
  if (ok && await attempt(() => api("/api/delete", { path: it.path }), "Deleted")) { closeSheet(); render(); }
}

// ------------------------------------------------------------------ uploads
const tray = $("#tray");
function uploadFile(file, dir) {
  return new Promise((resolve) => {
    const bar = h("i", { style: "width:0%" });
    const pct = h("span", {}, "0%");
    const sub = h("div", { class: "sub" }, "Sending to the drive…");
    const item = h("div", { class: "item" }, h("div", { class: "n" }, h("span", {}, file.name), pct), h("div", { class: "meter" }, bar), sub);
    tray.prepend(item);
    const started = Date.now();
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload" + q({ path: join(dir, file.name) }));
    xhr.setRequestHeader("X-DD", "1");
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const p = Math.round((e.loaded / e.total) * 100);
      const bps = e.loaded / Math.max(0.3, (Date.now() - started) / 1000);
      bar.style.width = p + "%";
      pct.textContent = p < 100 ? p + "%" : "Saving";
      sub.textContent = p < 100 ? `${size(e.loaded)} of ${size(e.total)} · ${speed(bps)} · ${eta((e.total - e.loaded) / bps)}`
                                : "Saving on the drive…";
    };
    xhr.onload = () => {
      const ok = xhr.status >= 200 && xhr.status < 300;
      pct.textContent = ok ? "Done" : "Failed";
      sub.textContent = ok ? "On the drive · uploading to Discord next" : "Not uploaded";
      if (!ok) { try { toast(JSON.parse(xhr.responseText).error); } catch { toast("Upload failed"); } }
      setTimeout(() => item.remove(), ok ? 1500 : 6000);
      resolve(ok);
    };
    xhr.onerror = () => { pct.textContent = "Failed"; setTimeout(() => item.remove(), 6000); resolve(false); };
    xhr.send(file);
  });
}

/** Uploads from the drive to Discord, live (one tray card per file). */
const discordCards = new Map();
function showDiscordUploads(list) {
  const seen = new Set();
  for (const u of list || []) {
    seen.add(u.path);
    let c = discordCards.get(u.path);
    if (!c) {
      c = { bar: h("i", { style: "width:0%" }), pct: h("span", {}), sub: h("div", { class: "sub" }) };
      c.el = h("div", { class: "item discord" }, h("div", { class: "n" }, h("span", { title: u.path }, base(u.path)), c.pct),
               h("div", { class: "meter" }, c.bar), c.sub);
      discordCards.set(u.path, c);
      tray.append(c.el);
    }
    c.bar.style.width = u.pct + "%";
    c.pct.textContent = Math.floor(u.pct) + "%";
    c.sub.textContent = u.stage === "spare pieces" ? "Adding spare pieces…"
      : `To Discord · ${size(u.bytes)} of ${size(u.size)}${u.speed ? " · " + speed(u.speed) : ""}${u.eta ? " · " + eta(u.eta) : ""}`;
  }
  for (const [path, c] of discordCards) {
    if (seen.has(path)) continue;
    discordCards.delete(path);
    c.bar.style.width = "100%";
    c.pct.textContent = "Done";
    c.sub.textContent = "Stored in Discord";
    setTimeout(() => c.el.remove(), 1500);
  }
}

async function uploadAll(entries, dir) {
  let n = 0;
  for (const { file, rel } of entries) {
    const folders = rel.split("/").slice(0, -1);
    let cur = dir;
    for (const f of folders) {
      cur = join(cur, f);
      await api("/api/mkdir", { path: cur }).catch(() => null);   // already exists: fine
    }
    if (await uploadFile(file, cur)) n++;
  }
  if (n) toast(`${plural(n, "file")} added. ${n === 1 ? "It uploads" : "They upload"} to Discord in the background.`);
  if (route.name === "files") render();
}

for (const id of ["#pick", "#pick-dir"]) {
  $(id).addEventListener("change", (e) => {
    const files = [...e.target.files].map((file) => ({ file, rel: file.webkitRelativePath || file.name }));
    e.target.value = "";
    uploadAll(files, currentDir);
  });
}

async function readEntries(entry, prefix, out) {
  if (entry.isFile) {
    await new Promise((res) => entry.file((file) => { out.push({ file, rel: prefix + file.name }); res(); }, res));
  } else if (entry.isDirectory) {
    const reader = entry.createReader();
    for (;;) {
      const batch = await new Promise((res) => reader.readEntries(res, () => res([])));
      if (!batch.length) break;
      for (const e of batch) await readEntries(e, prefix + entry.name + "/", out);
    }
  }
}

let dragDepth = 0;
const drop = $("#drop");
document.addEventListener("dragenter", (e) => {
  if (route.name !== "files" || ![...(e.dataTransfer?.types || [])].includes("Files")) return;
  dragDepth++;
  if (!e.target.closest || !e.target.closest(".drop-into")) $("#drop-to").textContent = currentDir === "/" ? "Drive" : base(currentDir);
  drop.classList.add("on");
});
document.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; drop.classList.remove("on"); } });
document.addEventListener("dragover", (e) => { if (route.name === "files") e.preventDefault(); });
document.addEventListener("drop", async (e) => {
  if (route.name !== "files") return;
  e.preventDefault();
  dragDepth = 0;
  drop.classList.remove("on");
  if (!hasFiles(e)) return;
  uploadAll(await droppedFiles(e), currentDir);
});

async function droppedFiles(e) {
  const out = [];
  const items = [...(e.dataTransfer.items || [])].map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (items.length) for (const entry of items) await readEntries(entry, "", out);
  else for (const file of e.dataTransfer.files) out.push({ file, rel: file.name });
  return out;
}

// ------------------------------------------------------------------ deleted
const picked = new Set();

async function renderDeleted() {
  const data = await attempt(() => api("/api/deleted"));
  const items = data ? data.items : [];
  for (const uid of [...picked]) if (!items.some((it) => it.uid === uid)) picked.delete(uid);
  const head = h("div", { class: "bar" }, h("h1", { style: "margin:0" }, "Deleted"));
  const lede = h("p", { class: "lede" }, "Deleted files are kept for a while (see Settings) and can be brought back on every device. ",
                 "Delete them for good to free the space now.");
  if (!items.length) {
    page(head, lede, h("div", { class: "empty" }, h("b", {}, "Nothing deleted"), "Files you delete show up here."));
    return;
  }
  const boxes = [];
  const selbar = h("div", { class: "selbar" });
  const all = checkbox(false, (on) => { items.forEach((it) => on ? picked.add(it.uid) : picked.delete(it.uid)); sync(); }, "Select all");
  function sync() {
    boxes.forEach(([it, box, row]) => { setBox(box, picked.has(it.uid)); row.classList.toggle("sel", picked.has(it.uid)); });
    setBox(all, picked.size === items.length ? true : picked.size ? "mixed" : false);
    const chosen = items.filter((it) => picked.has(it.uid));
    selbar.replaceChildren(
      h("span", { class: "count" }, chosen.length ? `${plural(chosen.length, "file")} selected · ${size(chosen.reduce((a, it) => a + it.size, 0))}`
                                                  : `${plural(items.length, "file")} · ${size(items.reduce((a, it) => a + it.size, 0))}`),
      h("div", { class: "actions" },
        chosen.length ? h("button", { class: "btn ghost small", onclick: () => { picked.clear(); sync(); } }, "Clear") : null,
        h("button", { class: "btn ghost small", disabled: !chosen.length, onclick: () => restoreMany(chosen) }, "Restore"),
        h("button", { class: "btn danger small", disabled: !chosen.length, onclick: () => purgeMany(chosen) }, "Delete forever")));
  }
  const rows = items.map((it) => {
    const box = checkbox(false, (on) => { on ? picked.add(it.uid) : picked.delete(it.uid); sync(); }, `Select ${base(it.path)}`);
    const menu = () => deletedMenu(it, sync);
    const row = h("div", { class: "row click pick", tabindex: "0",
                           onclick: (e) => { if (e.target.closest("button")) return; picked.has(it.uid) ? picked.delete(it.uid) : picked.add(it.uid); sync(); },
                           onkeydown: (e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); row.click(); } } },
      h("span", { class: "name" }, box, icon(kind(it.path) === "pdf" ? "text" : kind(it.path)), h("span", { style: "min-width:0" },
        h("span", { class: "label" }, base(it.path)), h("div", { class: "where" }, parent(it.path)))),
      h("span", { class: "size" }, size(it.size)),
      h("span", { class: "date" }, when(it.at)),
      menuButton(menu, base(it.path), `Deleted ${when(it.at)}`));
    bindMenu(row, menu, base(it.path), `Deleted ${when(it.at)}`);
    boxes.push([it, box, row]);
    return row;
  });
  page(head, lede, selbar,
       h("div", { class: "list" },
         h("div", { class: "row head" }, h("span", { class: "name" }, all, h("span", {}, "Name")), h("span", { class: "size" }, "Size"),
           h("span", { class: "date" }, "Deleted"), h("span")),
         rows));
  sync();
}

function checkbox(on, change, label) {
  const b = h("button", { class: "cb", role: "checkbox", "aria-label": label, "aria-checked": String(on),
                          onclick: (e) => { e.stopPropagation(); change(b.getAttribute("aria-checked") !== "true"); } },
              icon("check"));
  return b;
}
function setBox(b, state) { b.setAttribute("aria-checked", String(state)); }

function deletedMenu(it, sync) {
  return [
    { label: "Restore", icon: "restore", run: () => restoreMany([it]) },
    { label: picked.has(it.uid) ? "Deselect" : "Select", icon: "check",
      run: () => { picked.has(it.uid) ? picked.delete(it.uid) : picked.add(it.uid); sync(); } },
    "-",
    { label: "Delete forever", icon: "trash", danger: true, run: () => purgeMany([it]) },
  ];
}

async function restoreMany(list) {
  const r = await attempt(() => api("/api/undelete", { uids: list.map((it) => it.uid) }));
  if (!r) return;
  list.forEach((it) => picked.delete(it.uid));
  toast(list.length === 1 ? `${base(list[0].path)} restored` : `${plural(r.count, "file")} restored`);
  setTimeout(() => { if (route.name === "deleted") renderDeleted(); }, 2500);
}

async function purgeMany(list) {
  const one = list.length === 1;
  const ok = await ask({ title: one ? `Delete “${base(list[0].path)}” forever?` : `Delete ${plural(list.length, "file")} forever?`,
                         ok: "Delete forever", danger: true,
                         text: `${one ? "It is" : "They are"} removed from Discord on every device and can't be recovered. ` +
                               "Snapshots taken before still contain them until those snapshots expire." });
  if (!ok) return;
  const r = await attempt(() => api("/api/purge", { uids: list.map((it) => it.uid) }));
  if (!r) return;
  list.forEach((it) => picked.delete(it.uid));
  toast(one ? "Deleted forever" : `${plural(r.count, "file")} deleted forever`);
  renderDeleted();
}

// ------------------------------------------------------------------ snapshots
async function renderSnapshots() {
  const data = await attempt(() => api("/api/snapshots"));
  const items = data ? data.items : [];
  const s = status && status.snapshots;
  const every = s && s.interval ? `A snapshot is taken every ${s.interval} hours and kept ${s.keep} days. ` : "";
  page(h("div", { class: "bar" }, h("h1", { style: "margin:0" }, "Snapshots"),
         h("div", { class: "actions" }, h("button", { class: "btn", onclick: async (e) => {
           e.target.disabled = true;
           if (await attempt(() => api("/api/snapshots/create", { label: "Manual" }), "Snapshot taken")) renderSnapshots();
           e.target.disabled = false;
         } }, "Take snapshot now"))),
       h("p", { class: "lede" }, `${every}Each one is the whole drive exactly as it was, so you can bring back a folder as it was on a given day.`),
       items.length ? h("div", { class: "list rows-simple" }, items.map((sn) => h("a", { class: "row", href: `#/snapshot/${sn.id}/` },
         h("span", { class: "name" }, icon("folder", "folder"), h("span", { class: "label" }, fmtFull.format(new Date(sn.at * 1000))),
           sn.label && h("span", { class: "tag" }, sn.label)),
         h("span", { class: "size" }, size(sn.bytes)),
         h("span", { class: "date" }, plural(sn.files, "file")),
         h("span", { class: "date" }, sn.keep_until ? `until ${when(sn.keep_until)}` : "kept"))))
       : h("div", { class: "empty" }, h("b", {}, "No snapshots yet"), "Take one now, or wait for the first automatic one."));
}

async function renderSnapshot() {
  const [id, ...rest] = route.rest;
  const path = "/" + rest.map(decodeURIComponent).join("/").replace(/^\/+|\/+$/g, "");
  const [list, snaps] = await Promise.all([api("/api/snapshot" + q({ id, path })).catch(() => null),
                                           api("/api/snapshots").catch(() => null)]);
  const sn = snaps && snaps.items.find((x) => x.id === id);
  if (!list || !sn) { page(h("div", { class: "empty" }, h("b", {}, "Snapshot not found"), h("a", { href: "#/snapshots" }, "All snapshots"))); return; }
  const title = fmtFull.format(new Date(sn.at * 1000));
  async function restoreFrom(what) {
    const ok = await ask({ title: `Restore ${what === "/" ? "the whole drive" : "“" + base(what) + "”"}?`, ok: "Restore",
                           text: "It is copied into a new folder named after the snapshot, so nothing you have now is changed." });
    if (!ok) return;
    const r = await attempt(() => api("/api/snapshots/restore", { id, path: what }));
    if (r) { toast(`${plural(r.files, "file")} restored into ${r.folder}`); setTimeout(() => go("#/files" + enc(r.folder)), 2500); }
  }
  const restore = h("button", { class: "btn", onclick: () => restoreFrom(path) }, path === "/" ? "Restore everything" : "Restore this folder");
  page(h("div", { class: "bar" },
         crumbs(path, title, (p) => `#/snapshot/${id}` + enc(p)),
         h("div", { class: "actions" }, h("a", { class: "btn ghost", href: "#/snapshots" }, "All snapshots"), restore)),
       list.items.length ? h("div", { class: "list" }, listHead(), list.items.map((it) => {
         const menu = () => [
           it.dir && { label: "Open", icon: "enter", run: () => go(`#/snapshot/${id}` + enc(it.path)) },
           { label: it.dir ? "Restore this folder" : "Restore this file", icon: "restore", run: () => restoreFrom(it.path) },
         ];
         const row = h(it.dir ? "a" : "div",
           it.dir ? { class: "row", href: `#/snapshot/${id}` + enc(it.path) } : { class: "row" },
           h("span", { class: "name" }, icon(it.dir ? "folder" : (kind(it.name) === "pdf" ? "text" : kind(it.name)), it.dir ? "folder" : ""),
             h("span", { class: "label" }, it.name)),
           h("span", { class: "size" }, it.dir ? "" : size(it.size)),
           h("span", { class: "date" }, when(it.mtime)), menuButton(menu, it.name, title));
         bindMenu(row, menu, it.name, title);
         return row;
       }))
       : h("div", { class: "empty" }, h("b", {}, "Empty folder")));
}

// ------------------------------------------------------------------ health
function stat(k, v, s, pct) {
  return h("div", { class: "stat" }, h("div", { class: "k" }, k), h("div", { class: "v" }, v),
           s && h("div", { class: "s" }, s), pct != null && h("div", { class: "meter" }, h("i", { style: `width:${pct}%` })));
}

function renderHealth(quiet) {
  if (!status) { if (!quiet) page(h("h1", {}, "Health"), h("p", { class: "lede" }, "Connecting to the drive…")); return; }
  const st = status.stats, hl = status.health, sc = hl.scrub || {}, sv = status.saved || {};
  const pct = st.chunks ? Math.floor((st.protected_chunks / st.chunks) * 1000) / 10 : 100;
  const lede = hl.parity
    ? `Every group of ${hl.group} pieces is stored with ${hl.pieces} spare pieces, so Discord can lose pieces without you losing files. Missing pieces are rebuilt and uploaded again automatically.`
    : "Spare pieces are turned off, so a piece Discord loses can't be rebuilt. Turn them on in Settings.";
  const checkPct = sc.total ? Math.min(100, Math.round(((sc.done || 0) / sc.total) * 100)) : null;
  const uploads = status.uploads.map((u) => h("div", { class: "kv-up" },
    h("div", { class: "row", style: "grid-template-columns:minmax(0,1fr) auto" },
      h("span", { class: "name" }, icon(kind(u.path)), h("span", { class: "label" }, u.path)),
      h("span", { class: "size" }, `${Math.floor((u.done / u.total) * 100)}% of ${size(u.size)}`))));
  const saved = (sv.compressed_saved || 0) + (sv.reused_bytes || 0);
  page(
    h("h1", {}, "Health"),
    h("p", { class: "lede" }, lede),
    h("div", { class: "stats" },
      stat("Protected", `${pct}%`, `${Number(st.protected_chunks).toLocaleString()} of ${Number(st.chunks).toLocaleString()} pieces`, pct),
      stat("Spare pieces", Number(st.spare_pieces).toLocaleString(), size(st.spare_bytes)),
      stat("Checked", sc.last_pass ? ago(sc.last_pass) : (sc.checked ? `${(sc.checked || 0).toLocaleString()}` : "Not yet"),
           sc.last_pass ? "last full check" : (hl.leader ? "pieces, first check running" : "another device checks"), checkPct),
      stat("Repaired", Number((sc.repaired || 0) + (hl.healer.repaired || 0)).toLocaleString(),
           (sc.lost || hl.healer.lost) ? `${sc.lost || hl.healer.lost} could not be rebuilt` : "nothing lost")),
    h("h2", {}, "Storage"),
    h("div", { class: "kv" },
      h("div", {}, "Files"), h("div", {}, `${plural(st.files, "file")} in ${plural(st.dirs, "folder")}`),
      h("div", {}, "Size"), h("div", {}, size(st.bytes)),
      h("div", {}, "Earlier versions"), h("div", {}, `${plural(st.versions, "version")} · ${size(st.version_bytes)}`),
      h("div", {}, "Snapshots"), h("div", {}, plural(st.snapshots, "snapshot")),
      h("div", {}, "Saved this session"), h("div", {}, saved ? `${size(saved)} not uploaded thanks to compression and identical pieces` : "—"),
      h("div", {}, "Uploading with"), h("div", {}, plural(status.bots, "bot")),
      h("div", {}, "Encryption"), h("div", {}, status.encrypted ? "On (AES-256-GCM): Discord sees only random data" : "Off")),
    uploads.length ? [h("h2", {}, "Uploading now"), h("div", { class: "list" }, uploads)] : null,
    h("h2", {}, "Devices"),
    h("div", { class: "list rows-simple" }, status.devices.map((d) => h("div", { class: "row", style: "grid-template-columns:minmax(0,1fr) auto" },
      h("span", { class: "name" }, h("span", { class: "label" }, d.name || d.id), h("span", { class: "tag" }, d.id), d.me && h("span", { class: "tag" }, "This device")),
      h("span", { class: "date" }, d.me ? "online" : `seen ${ago(d.seen)}`)))),
    status.lan.length ? [h("h2", {}, "On your network"), h("div", { class: "kv" },
      h("div", {}, "Open on your phone"), h("div", {}, h("code", {}, status.lan[0])))] : null,
    h("p", { class: "muted", style: "margin-top:40px;font-size:12px" }, `DiscordDrive ${status.version} · Made by XO.ST · `,
      h("button", { class: "link", onclick: whatsNew }, "What's new")));
}

// ------------------------------------------------------------------ shared links
async function renderShared() {
  const data = await attempt(() => api("/api/shares"));
  const items = data ? data.items : [];
  const menu = (l) => () => [
    { label: "Copy link", icon: "link", run: async () => {
      try { await navigator.clipboard.writeText(shareUrl(l)); toast("Link copied"); }
      catch { await ask({ title: "Share link", value: shareUrl(l), ok: "Done" }); } } },
    { label: "Open the link", icon: "open", run: () => window.open(l.path, "_blank", "noopener") },
    l.item && { label: "Show in Files", icon: "enter", run: () => go("#/files" + enc(l.dir ? l.item : parent(l.item))) },
    { label: "Link settings…", icon: "settings", run: () => shareDialog(null, l) },
    "-",
    { label: "Turn off the link", icon: "trash", danger: true, run: async () => {
      if (await ask({ title: "Turn off this link?", ok: "Turn off", danger: true,
                      text: "It stops working right away. The file itself stays where it is." })
          && await attempt(() => api("/api/shares/revoke", { id: l.id }), "Link turned off")) renderShared();
    } },
  ];
  page(h("h1", {}, "Shared"),
       h("p", { class: "lede" }, "Links you made. Anyone with a link can open what it points to until it expires or you turn it off."),
       items.length ? h("div", { class: "list" },
         h("div", { class: "row head" }, h("span", {}, "Item"), h("span", { class: "size" }, "Views"), h("span", { class: "date" }, "Works until"), h("span")),
         items.map((l) => {
           const name = l.item ? base(l.item) || "Drive" : "Deleted item";
           const row = h("div", { class: "row click", tabindex: "0", onclick: () => shareDialog(null, l) },
             h("span", { class: "name" }, icon(l.dir ? "folder" : kind(name) === "pdf" ? "text" : kind(name), l.dir ? "folder" : ""),
               h("span", { style: "min-width:0" }, h("span", { class: "label" }, name), h("div", { class: "where" }, l.item ? parent(l.item) : "")),
               l.password && h("span", { class: "tag", title: "Needs a password" }, icon("lock", "tag-ico"), "Password"),
               !l.download && h("span", { class: "tag" }, "View only")),
             h("span", { class: "size" }, String(l.views)),
             h("span", { class: "date" }, l.expires ? when(l.expires) : "No expiry"),
             menuButton(menu(l), name, l.expires ? `until ${fmtFull.format(new Date(l.expires * 1000))}` : "no expiry"));
           bindMenu(row, menu(l), name);
           return row;
         }))
       : h("div", { class: "empty" }, h("b", {}, "No links yet"), "Right-click a file or folder and choose Share."));
}

// ------------------------------------------------------------------ settings
const SETTING_ROWS = [
  ["Web dashboard", [
    ["web_hosts", "Domain names", "Names this dashboard answers to behind a reverse proxy (e.g. drive.example.com). Several: separate with commas.", "list"],
    ["web_public_url", "Address for share links", "Used when you share from this computer itself, e.g. https://drive.example.com. Empty: the first domain name.", "text"],
    ["web_lan", "On your network", "Phones and computers at home (and a reverse proxy on another machine) can open the dashboard.", "bool"],
  ]],
  ["Discord", [
    ["discord_pace", "Pace", "How fast to talk to Discord. Gentle stays far below Discord's limits so it never has to slow you down; fast uploads quicker but can hit them.", ["gentle", "balanced", "fast"]],
    ["uploads_per_minute", "Uploads per minute (per bot)", "0 = from the pace (gentle: 30, about 4.5 MB/s per bot).", "num"],
    ["deletes_per_minute", "Deletes per minute (per bot)", "Removing old pieces happens in the background. 0 = from the pace (gentle: 15).", "num"],
    ["requests_per_minute", "Other requests per minute", "Checks, syncing and refreshing links. 0 = from the pace (gentle: 90).", "num"],
  ]],
  ["Protection", [
    ["parity_enabled", "Self-healing", "Spare pieces let lost pieces be rebuilt.", "bool"],
    ["parity_pieces", "Spare pieces per 10", "How many pieces of a group can be lost (2 is about 20% extra space).", "num"],
    ["scrub_enabled", "Background check", "Regularly confirm every piece is still on Discord, and repair what isn't.", "bool"],
    ["protect_existing", "Protect older files", "Add spare pieces to files uploaded without them.", "bool"],
  ]],
  ["Storage", [
    ["compression", "Compression", "Shrink pieces that compress well before encrypting them. Lossless.", "bool"],
    ["dedup", "Store identical pieces once", "A copy of a file uploads nothing new.", "bool"],
    ["keep_versions", "Keep earlier versions", "Replaced and deleted files can be brought back.", "bool"],
    ["version_retention_days", "Keep versions for (days)", "0 keeps them forever.", "num"],
    ["snapshot_interval_hours", "Snapshot every (hours)", "0 turns automatic snapshots off.", "num"],
    ["snapshot_keep_days", "Keep snapshots for (days)", "", "num"],
  ]],
  ["This computer", [
    ["cache_mode", "Read cache", "Disk keeps opened files for faster reopening; memory stores nothing on disk.", ["disk", "memory"]],
    ["hidden_folders", "Hidden folders", "Folders this computer doesn't show, e.g. /Movies. Separate with commas.", "list"],
  ]],
];

async function renderSettings() {
  const data = await attempt(() => api("/api/settings"));
  if (!data) return;
  const v = data.values;
  async function save(key, value) {
    const r = await attempt(() => api("/api/settings", { [key]: value }));
    if (r) { v[key] = value; toast(r.restart.length ? "Saved. Restart the drive for this to take effect." : "Saved"); }
  }
  const control = (key, type) => {
    if (type === "bool") return switchEl(v[key], (on) => save(key, on), key);
    if (Array.isArray(type)) {
      const s = h("select", { onchange: (e) => save(key, e.target.value) }, type.map((o) => h("option", { value: o, selected: v[key] === o }, o)));
      return s;
    }
    const val = type === "list" ? (v[key] || []).join(", ") : String(v[key] ?? "");
    const input = h("input", { value: val, inputmode: type === "num" ? "decimal" : null, spellcheck: "false",
                               placeholder: type === "list" ? "None" : type === "text" ? "Not set" : "",
                               onkeydown: (e) => { if (e.key === "Enter") e.target.blur(); },
                               onchange: (e) => save(key, type === "list" ? e.target.value.split(",").map((x) => x.trim()).filter(Boolean) : e.target.value.trim()) });
    return input;
  };
  page(h("h1", {}, "Settings"),
       h("p", { class: "lede" }, "Changes are saved as you make them, for this computer's drive."),
       SETTING_ROWS.map(([title, rows]) => [h("h2", {}, title), h("div", { class: "settings" }, rows.map(([key, label, hint, type]) =>
         h("div", { class: "set-row" }, h("div", { class: "set-text" }, h("div", { class: "t" }, label), hint && h("div", { class: "s" }, hint),
           data.restart.includes(key) && h("div", { class: "s faint" }, "Takes effect after a restart")),
           h("div", { class: "set-ctl" + (type === "bool" ? "" : " wide") }, control(key, type)))))]).flat(),
       h("h2", {}, "Sign-in"),
       h("p", { class: "muted" }, `Signed in as ${status && status.user ? status.user : "you"}. Change the user name or password in the DiscordDrive menu (Settings → Web dashboard sign-in) or with `, h("code", {}, "web-password"), "."));
}

// ------------------------------------------------------------------ notes
// Notes are files in /Notes on the drive: encrypted, synced to every device, with earlier versions.
// Typing saves to this computer at once and uploads to Discord when you pause; Save uploads now.
const NOTES = "/Notes";
let note = null;          // the open note: {path, name, mtime, dirty, gen, saving, timer}
let notesTimer = null;
let notesList = [];

function leaveNotes() {
  if (note && note.dirty) saveNote("later");
  if (route.name !== "notes") { clearInterval(notesTimer); notesTimer = null; note = null; }
}
window.addEventListener("beforeunload", () => { if (note && note.dirty) saveNote("later", true); });

const noteTitle = (name) => name.replace(/\.(md|txt)$/i, "");
const cleanTitle = (t) => (t.replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim() || "Untitled").slice(0, 120);

async function renderNotes() {
  const name = route.rest.length ? decodeURIComponent(route.rest.join("/")) : "";
  const data = await attempt(() => api("/api/notes"));
  notesList = data ? data.items : [];
  const current = notesList.find((n) => n.name === name);
  const search = h("input", { type: "search", placeholder: "Search notes", class: "notes-search",
                              oninput: () => fillList(search.value.trim().toLowerCase()) });
  const list = h("div", { class: "note-list" });
  function fillList(filter = "") {
    const shown = notesList.filter((n) => !filter || (n.title + " " + n.snippet).toLowerCase().includes(filter));
    list.replaceChildren(...(shown.length ? shown.map((n) => h("a", { class: "note-item" + (n.name === name ? " on" : ""), href: "#/notes/" + encodeURIComponent(n.name) },
      h("div", { class: "nt" }, n.title), h("div", { class: "ns" }, h("span", {}, when(n.mtime)), " ", n.snippet.replace(n.title, "").trim() || "Empty note")))
      : [h("div", { class: "muted note-none" }, filter ? "No matches" : "No notes yet")]));
  }
  fillList();
  const side = h("div", { class: "notes-side" },
    h("div", { class: "notes-head" }, h("h1", {}, "Notes"), h("button", { class: "btn small", onclick: newNote }, icon("plus"), "New")),
    search, list);
  let editor;
  if (current) {
    editor = noteEditor(current);
  } else {
    editor = h("div", { class: "notes-empty" }, h("b", {}, notesList.length ? "Pick a note" : "Write your first note"),
      h("p", { class: "muted" }, "Notes save as you type and sync to all your devices."),
      h("button", { class: "btn", onclick: newNote }, "New note"));
  }
  page(h("div", { class: "notes" + (current ? " editing" : "") }, side, editor));
  clearInterval(notesTimer);
  notesTimer = setInterval(pollNotes, 4000);
}

function noteEditor(n) {
  if (!note || note.path !== n.path) note = { path: n.path, name: n.name, mtime: n.mtime, dirty: false, gen: 0, saving: false };
  const title = h("input", { class: "note-title", value: noteTitle(n.name), spellcheck: "false", "aria-label": "Title",
                             onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); body.focus(); } },
                             onchange: () => renameNote(title) });
  const body = h("textarea", { class: "note-body", placeholder: "Start writing…", "aria-label": "Note" });
  const state = h("span", { class: "note-state", id: "note-state" }, "Loading…");
  const saveBtn = h("button", { class: "btn small", title: "Back up to Discord now (Ctrl+S)", onclick: () => saveNote("now") }, icon("save"), "Save");
  const it = { path: n.path, name: n.name, dir: false, size: n.size, mtime: n.mtime, state: n.state };
  const more = menuButton(() => [
    { label: "Earlier versions", icon: "history", run: () => openItem(it, "versions") },
    { label: "Download", icon: "download", run: () => download(fileUrl(n.path, true), n.name) },
    { label: "Share…", icon: "link", run: () => shareDialog(it) },
    "-",
    { label: "Delete note", icon: "trash", danger: true, run: async () => {
      if (await ask({ title: `Delete “${noteTitle(n.name)}”?`, ok: "Delete", danger: true, text: "You can recover it from Deleted for a while." })
          && await attempt(() => api("/api/delete", { path: n.path }), "Note deleted")) { note = null; go("#/notes"); }
    } },
  ], noteTitle(n.name));
  body.addEventListener("input", () => {
    note.dirty = true;
    note.gen++;
    setState("Editing…");
    clearTimeout(note.timer);
    note.timer = setTimeout(() => saveNote("later"), 700);
  });
  body.addEventListener("keydown", (e) => {
    if (e.key.toLowerCase() === "s" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); saveNote("now"); }
  });
  loadNoteText(body, n.state);
  return h("div", { class: "note-editor" },
    h("div", { class: "note-bar" },
      h("a", { class: "icon-btn note-back", href: "#/notes", "aria-label": "All notes" }, icon("back")),
      state, h("div", { class: "actions" }, saveBtn, more)),
    title, h("div", { class: "note-conflict", id: "note-conflict", hidden: true }), body);
}

function setState(text) { const el = $("#note-state"); if (el) el.textContent = text; }
function noteUploadState() {
  const u = status && status.uploads.find((x) => x.path === note.path);
  const el = $("#note-state");
  if (!el) return;
  let bar = $("#note-progress");
  if (u && !note.dirty && !note.saving) {
    el.textContent = `Uploading to Discord ${Math.floor(u.pct)}%${u.eta ? " · " + eta(u.eta) : ""}`;
    if (!bar) { bar = h("div", { class: "meter note-meter", id: "note-progress" }, h("i")); el.after(bar); }
    bar.firstChild.style.width = u.pct + "%";
  } else if (bar) {
    bar.remove();
  }
}
function syncedText(state) { return state === "synced" ? "Backed up to Discord" : "Saved on this computer · uploading soon"; }

async function loadNoteText(body, state) {
  const r = await fetch(fileUrl(note.path), { credentials: "same-origin", cache: "no-store" }).catch(() => null);
  if (!r || !r.ok) { setState("Could not open this note"); return; }
  const text = await r.text();
  if (note.dirty) return;
  const pos = [body.selectionStart, body.selectionEnd];
  body.value = text;
  if (document.activeElement === body) body.setSelectionRange(...pos);
  setState(syncedText(state));
}

async function saveNote(mode, unloading) {
  if (!note) return;
  const ta = $(".note-body");
  if (!ta) return;
  clearTimeout(note.timer);
  if (note.saving && !unloading) { note.again = mode === "now" ? "now" : note.again || "later"; return; }
  const gen = note.gen;
  note.saving = true;
  setState("Saving…");
  try {
    const r = await fetch("/api/upload" + q({ path: note.path, save: mode }), {
      method: "POST", credentials: "same-origin", keepalive: !!unloading, headers: { "X-DD": "1" },
      body: new Blob([ta.value], { type: "text/plain;charset=utf-8" }) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || "Could not save");
    if (data.mtime) note.mtime = data.mtime;
    if (note.gen === gen) note.dirty = false;
    setState(mode === "now" ? "Backing up to Discord…" : "Saved on this computer · uploading soon");
    if (mode === "now") note.backup = true;
  } catch (e) {
    setState("Not saved: " + e.message);
  } finally {
    note.saving = false;
    if (note.again) { const m = note.again; note.again = null; saveNote(m); }
  }
}

async function renameNote(input) {
  const t = cleanTitle(input.value);
  input.value = t;
  const name = t + ".md";
  if (!note || name === note.name) return;
  if (notesList.some((n) => n.name.toLowerCase() === name.toLowerCase())) { toast("A note with that title already exists"); input.value = noteTitle(note.name); return; }
  if (note.dirty) await saveNote("later");
  if (await attempt(() => api("/api/move", { from: note.path, to: join(NOTES, name) }))) {
    note.path = join(NOTES, name);
    note.name = name;
    history.replaceState(null, "", "#/notes/" + encodeURIComponent(name));
    route = parseRoute();
    refreshNoteList();
  }
}

async function newNote() {
  await api("/api/mkdir", { path: NOTES }).catch(() => null);
  const names = new Set(notesList.map((n) => n.name.toLowerCase()));
  let name = "Untitled.md";
  for (let i = 2; names.has(name.toLowerCase()); i++) name = `Untitled ${i}.md`;
  const r = await fetch("/api/upload" + q({ path: join(NOTES, name), save: "later" }),
                        { method: "POST", credentials: "same-origin", headers: { "X-DD": "1" }, body: "" });
  if (!r.ok) { toast("Could not create the note"); return; }
  note = null;
  go("#/notes/" + encodeURIComponent(name));
  setTimeout(() => { const t = $(".note-title"); if (t) { t.focus(); t.select(); } }, 300);
}

async function refreshNoteList() {
  const data = await api("/api/notes").catch(() => null);
  if (!data) return null;
  notesList = data.items;
  const search = $(".notes-search");
  const list = $(".note-list");
  if (list) {
    const filter = search ? search.value.trim().toLowerCase() : "";
    const name = note ? note.name : "";
    const shown = notesList.filter((n) => !filter || (n.title + " " + n.snippet).toLowerCase().includes(filter));
    list.replaceChildren(...(shown.length ? shown.map((n) => h("a", { class: "note-item" + (n.name === name ? " on" : ""), href: "#/notes/" + encodeURIComponent(n.name) },
      h("div", { class: "nt" }, n.title), h("div", { class: "ns" }, h("span", {}, when(n.mtime)), " ", n.snippet.replace(n.title, "").trim() || "Empty note")))
      : [h("div", { class: "muted note-none" }, "No notes yet")]));
  }
  return notesList;
}

async function pollNotes() {
  if (route.name !== "notes") return;
  const items = await refreshNoteList();
  if (!items || !note) return;
  const cur = items.find((n) => n.path === note.path);
  if (!cur) return;
  if (!note.dirty && !note.saving) setState(syncedText(cur.state));
  if (cur.mtime > note.mtime + 0.5) {
    note.mtime = cur.mtime;
    const box = $("#note-conflict");
    if (!note.dirty) {
      const ta = $(".note-body");
      if (ta) { await loadNoteText(ta, cur.state); toast("Updated with changes from another device"); }
    } else if (box) {
      box.hidden = false;
      box.replaceChildren(h("span", {}, "This note was changed somewhere else while you were typing."),
        h("button", { class: "btn ghost small", onclick: () => { note.dirty = false; box.hidden = true; loadNoteText($(".note-body"), cur.state); } }, "Load theirs"),
        h("button", { class: "btn small", onclick: () => { box.hidden = true; saveNote("now"); } }, "Keep mine"));
    }
  }
}

// ------------------------------------------------------------------ log
let logTimer = null;
let logAfter = 0;
let logLines = [];
let logPaused = false;
let logLevel = "all";
const LEVELS = { all: () => true, info: (l) => l !== "DEBUG", warn: (l) => l === "WARNING" || l === "ERROR" || l === "CRITICAL",
                 error: (l) => l === "ERROR" || l === "CRITICAL" };

function progressRow(title, sub, pct, ico) {
  return h("div", { class: "act-row" },
    h("div", { class: "act-top" }, icon(ico || kind(title)), h("span", { class: "act-name", title }, base(title) || title),
      h("span", { class: "act-pct" }, pct == null ? "" : Math.floor(pct) + "%")),
    pct == null ? null : h("div", { class: "meter" }, h("i", { style: `width:${pct}%` })),
    h("div", { class: "act-sub" }, sub));
}

async function renderLog() {
  logAfter = 0;
  logLines = [];
  const now = h("div", { class: "activity" });
  const search = h("input", { type: "search", placeholder: "Search the log", class: "log-search", oninput: () => drawLog() });
  const chips = h("div", { class: "seg log-levels", role: "radiogroup" }, [["all", "All"], ["info", "Info"], ["warn", "Warnings"], ["error", "Errors"]]
    .map(([k, label]) => h("button", { type: "button", role: "radio", "aria-checked": String(k === logLevel),
                                       onclick: (e) => { logLevel = k; for (const b of chips.children) b.setAttribute("aria-checked", String(b === e.currentTarget)); drawLog(); } }, label)));
  const pause = h("button", { class: "btn ghost small", onclick: () => { logPaused = !logPaused; pause.textContent = logPaused ? "Resume" : "Pause"; } }, logPaused ? "Resume" : "Pause");
  const save = h("button", { class: "btn ghost small", onclick: () => {
    const text = logLines.map((l) => `${new Date(l.t * 1000).toISOString()} [${l.l}] ${l.n}: ${l.m}`).join("\n");
    download(URL.createObjectURL(new Blob([text], { type: "text/plain" })), "discorddrive-log.txt");
  } }, "Download");
  const box = h("div", { class: "log-box", role: "log", "aria-live": "off" });
  page(h("h1", {}, "Log"),
       h("p", { class: "lede" }, "Everything the drive is doing, live: uploads and downloads with their progress, then every log line."),
       h("h2", {}, "Now"), now,
       h("div", { class: "log-bar" }, h("h2", { style: "margin:0" }, "Log"), chips, search, h("div", { class: "actions" }, pause, save)),
       box);

  function drawLog() {
    const f = LEVELS[logLevel];
    const term = search.value.trim().toLowerCase();
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    const shown = logLines.filter((l) => f(l.l) && (!term || (l.m + " " + l.n).toLowerCase().includes(term))).slice(-1500);
    box.replaceChildren(...shown.map((l) => h("div", { class: "log-line lvl-" + l.l.toLowerCase() },
      h("span", { class: "lt" }, fmtTime.format(new Date(l.t * 1000))), h("span", { class: "ll" }, l.l === "WARNING" ? "WARN" : l.l),
      h("span", { class: "ln" }, l.n), h("span", { class: "lm" }, l.m))));
    if (atBottom || !box.dataset.scrolled) { box.scrollTop = box.scrollHeight; box.dataset.scrolled = "1"; }
  }

  async function tick() {
    if (route.name !== "log") { clearInterval(logTimer); logTimer = null; return; }
    const [a, lg] = await Promise.all([api("/api/activity").catch(() => null),
                                       logPaused ? null : api("/api/log" + q({ after: logAfter })).catch(() => null)]);
    if (a) {
      const parts = [];
      a.uploads.forEach((u) => parts.push(progressRow(u.path,
        u.stage === "spare pieces" ? "Adding spare pieces" :
          `Uploading to Discord · ${size(u.bytes)} of ${size(u.size)} · piece ${u.done} of ${u.total}${u.speed ? " · " + speed(u.speed) : ""}${u.eta ? " · " + eta(u.eta) : ""}`, u.pct)));
      a.offline.forEach((j) => parts.push(progressRow(j.path, `Downloading to keep offline · ${size(j.bytes)} of ${size(j.total)}${j.speed ? " · " + speed(j.speed) : ""}${j.eta ? " · " + eta(j.eta) : ""}`, j.pct, "download")));
      a.downloads.forEach((d) => parts.push(progressRow(d.path, `Downloading ${plural(d.pieces, "piece")} (${size(d.bytes)}) for reading`, null, "download")));
      a.queue.forEach((qd) => parts.push(progressRow(qd.path, `Waiting to upload · ${size(qd.size)}${qd.due > a.time ? " · starts in " + Math.ceil(qd.due - a.time) + " s" : ""}`, null)));
      const sum = [];
      if (a.upload_speed) sum.push(`Uploading ${speed(a.upload_speed)}${a.upload_eta ? ", all done in about " + eta(a.upload_eta).replace(" left", "") : ""}`);
      if (a.download_speed) sum.push(`Downloading ${speed(a.download_speed)}`);
      if (a.sync.outbox) sum.push(`${plural(a.sync.outbox, "change")} to send to other devices`);
      if (a.sync.trash) sum.push(`${plural(a.sync.trash, "old piece")} to delete from Discord`);
      if (a.sync.repairs) sum.push(`${plural(a.sync.repairs, "repair")} queued`);
      if (a.sync.failures) sum.push("Can't reach Discord right now; retrying");
      if (a.check && a.check.total) sum.push(`Background check: ${Number(a.check.done || 0).toLocaleString()} of ${Number(a.check.total).toLocaleString()} pieces`);
      now.replaceChildren(h("div", { class: "act-sum" }, sum.length ? sum.join(" · ") : "Nothing is uploading or downloading right now."), ...parts);
    }
    if (lg && lg.lines.length) {
      logLines = logLines.concat(lg.lines).slice(-5000);
      logAfter = lg.lines[lg.lines.length - 1].i;
      drawLog();
    } else if (!logLines.length) {
      drawLog();
    }
  }
  clearInterval(logTimer);
  await tick();
  logTimer = setInterval(tick, 1000);
}

// ------------------------------------------------------------------ what's new
async function whatsNew() {
  const data = await attempt(() => api("/api/changelog"));
  if (!data) return;
  const body = h("div", { class: "changelog" });
  let list = null;
  for (const line of (data.text || "No changelog found.").split("\n")) {
    const t = line.trim();
    if (!t || t.startsWith("# ")) { list = null; continue; }
    if (t.startsWith("## ")) { list = null; body.append(h("h4", {}, t.slice(3))); }
    else if (t.startsWith("- ")) { if (!list) { list = h("ul"); body.append(list); } list.append(h("li", {}, t.slice(2).replace(/\*\*/g, ""))); }
    else if (list && line.startsWith("  ")) list.lastChild && list.lastChild.append(" " + t);
    else { list = null; body.append(h("p", { class: "muted" }, t)); }
  }
  modal(`What's new · version ${data.version}`, body);
}

// ------------------------------------------------------------------ account
$("#account").addEventListener("click", (e) => {
  const r = e.currentTarget.getBoundingClientRect();
  openMenu([
    { label: status && status.user ? `Signed in as ${status.user}` : "Signed in", icon: "user", disabled: true },
    "-",
    { label: "Settings", icon: "settings", run: () => go("#/settings") },
    { label: "What's new", icon: "info", run: whatsNew },
    { label: "Sign out", icon: "signout", run: async () => { await api("/api/logout", {}).catch(() => null); location.reload(); } },
  ], r.right - 220, r.bottom + 6, "Account");
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });

// ------------------------------------------------------------------ start
dropTarget(document.querySelector('#nav a[data-nav="files"]'), "/");
dropTarget(document.querySelector('#nav a[data-nav="deleted"]'), "/", "delete");
render();
refreshStatus();
(function poll() {
  const busy = status && (status.uploads.length || status.downloads || status.queued);
  setTimeout(async () => { await refreshStatus(); poll(); }, busy ? 1000 : 3000);
})();
