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
    !it.dir && { label: "Copy share link", icon: "link", run: () => quickShare(it) },
    "-",
    { label: "Available offline", icon: "offline", checked: !!it.pinned, run: () => setPinned(it, !it.pinned) },
    "-",
    { label: "Rename…", icon: "rename", run: () => rename(it) },
    { label: "Move to…", icon: "move", run: () => moveTo(it) },
    !it.dir && { label: "Duplicate", icon: "copy", run: () => duplicate(it) },
    !it.dir && { label: "Earlier versions", icon: "history", run: () => openItem(it, "versions") },
    { label: "Details", icon: "info", run: () => openItem(it) },
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
  const views = { files: renderFiles, search: renderSearch, deleted: renderDeleted, snapshots: renderSnapshots,
                  snapshot: renderSnapshot, health: renderHealth };
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
  const rows = data.items.map((it) => itemRow(it));
  const body = rows.length ? h("div", { class: "list" }, listHead(), rows)
    : h("div", { class: "empty" }, h("b", {}, "Nothing here yet"), "Drop files anywhere on this page, or use Upload.");
  page(bar, body, h("div", { class: "spacer" }));
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
    !it.dir && h("button", { class: "btn ghost", onclick: () => share(it, extra) }, "Share link"),
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

async function share(it, into) {
  const r = await attempt(() => api("/api/share", { path: it.path, hours: 24 * 7 }));
  if (!r) return;
  const url = (r.lan && r.lan[0]) || location.origin + r.path;
  const input = h("input", { value: url, readonly: true, onclick: (e) => e.target.select() });
  const copy = h("button", { class: "btn small", onclick: async () => {
    try { await navigator.clipboard.writeText(url); toast("Link copied"); } catch { input.select(); }
  } }, "Copy");
  const local = !r.lan || !r.lan.length;
  into.replaceChildren(h("div", { class: "share-url" }, input, copy),
    h("div", { class: "hint" }, `Works for 7 days. ${local
      ? "It only opens on this computer. To share with phones and computers at home, turn on “Web dashboard on your network” in the DiscordDrive menu (Settings)."
      : "Anyone on your home network with this link can download this one file."}`));
}

async function quickShare(it) {
  const r = await attempt(() => api("/api/share", { path: it.path, hours: 24 * 7 }));
  if (!r) return;
  const url = (r.lan && r.lan[0]) || location.origin + r.path;
  try {
    await navigator.clipboard.writeText(url);
    toast("Share link copied. It works for 7 days.");
  } catch {
    await ask({ title: "Share link", value: url, ok: "Done", text: "Copy this link. It works for 7 days." });
  }
}

async function moveTo(it) {
  const dest = await ask({ title: `Move “${it.name}”`, value: parent(it.path), ok: "Move",
                           text: "Folder to move it into, for example /Photos/2024." });
  if (!dest) return;
  const folder = "/" + dest.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  if (folder === parent(it.path)) return;
  if (await attempt(() => api("/api/move", { from: it.path, to: join(folder, it.name) }), `Moved to ${folder}`)) {
    closeSheet(); render();
  }
}

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
    const item = h("div", { class: "item" }, h("div", { class: "n" }, h("span", {}, file.name), pct), h("div", { class: "meter" }, bar));
    tray.append(item);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload" + q({ path: join(dir, file.name) }));
    xhr.setRequestHeader("X-DD", "1");
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const p = Math.round((e.loaded / e.total) * 100);
      bar.style.width = p + "%";
      pct.textContent = p < 100 ? p + "%" : "Saving";
    };
    xhr.onload = () => {
      const ok = xhr.status >= 200 && xhr.status < 300;
      pct.textContent = ok ? "Done" : "Failed";
      if (!ok) { try { toast(JSON.parse(xhr.responseText).error); } catch { toast("Upload failed"); } }
      setTimeout(() => item.remove(), ok ? 1500 : 6000);
      resolve(ok);
    };
    xhr.onerror = () => { pct.textContent = "Failed"; setTimeout(() => item.remove(), 6000); resolve(false); };
    xhr.send(file);
  });
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
  $("#drop-to").textContent = currentDir === "/" ? "Drive" : base(currentDir);
  drop.classList.add("on");
});
document.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; drop.classList.remove("on"); } });
document.addEventListener("dragover", (e) => { if (route.name === "files") e.preventDefault(); });
document.addEventListener("drop", async (e) => {
  if (route.name !== "files") return;
  e.preventDefault();
  dragDepth = 0;
  drop.classList.remove("on");
  const out = [];
  const items = [...(e.dataTransfer.items || [])].map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (items.length) for (const entry of items) await readEntries(entry, "", out);
  else for (const file of e.dataTransfer.files) out.push({ file, rel: file.name });
  uploadAll(out, currentDir);
});

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
    h("p", { class: "muted", style: "margin-top:40px;font-size:12px" }, `DiscordDrive ${status.version} · Made by XO.ST`));
}

// ------------------------------------------------------------------ account
$("#account").addEventListener("click", (e) => {
  const r = e.currentTarget.getBoundingClientRect();
  openMenu([
    { label: status && status.user ? `Signed in as ${status.user}` : "Signed in", icon: "user", disabled: true },
    "-",
    { label: "Sign out", icon: "signout", run: async () => { await api("/api/logout", {}).catch(() => null); location.reload(); } },
  ], r.right - 220, r.bottom + 6, "Account");
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });

// ------------------------------------------------------------------ start
render();
refreshStatus();
setInterval(refreshStatus, 3000);
