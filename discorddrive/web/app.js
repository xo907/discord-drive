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
  const more = h("button", { class: "icon-btn more", "aria-label": `More for ${it.name}`, title: "Details",
                             onclick: (e) => { e.preventDefault(); e.stopPropagation(); openItem(it); } }, icon("more"));
  const attrs = it.dir ? { class: "row", href: "#/files" + enc(it.path) }
                       : { class: "row click", tabindex: "0", role: "button",
                           onclick: () => openItem(it), onkeydown: (e) => { if (e.key === "Enter") openItem(it); } };
  return h(it.dir ? "a" : "div", attrs, name,
           h("span", { class: "size" }, it.dir ? "" : size(it.size)),
           h("span", { class: "date" }, when(it.mtime)), more);
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
  page(bar, body);
}

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

function openItem(it) {
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
                             if (await attempt(() => api("/api/pin", { path: it.path, on }),
                                               on ? "Downloading it to keep it available offline" : "No longer kept offline")) {
                               sw.setAttribute("aria-checked", String(on)); it.pinned = on;
                             }
                           } });
  const toggle = h("div", { class: "toggle" },
    h("div", {}, h("div", { class: "t" }, "Available offline"),
      h("div", { class: "s" }, it.dir ? "Everything in it, including new files, stays downloaded on the computer running the drive"
                                      : "Stays downloaded on the computer running the drive, so it opens instantly")),
    sw);
  const extra = h("div");
  body.replaceChildren(preview(it), meta, actions, toggle, extra);
  if (!it.dir) loadVersions(it, extra);
  $("#sheet").classList.add("open");
  $("#sheet").setAttribute("aria-hidden", "false");
  $("#scrim").classList.add("open");
}

async function loadVersions(it, into) {
  const data = await api("/api/versions" + q({ path: it.path })).catch(() => null);
  if (!data || !data.versions.length) return;
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

$("#pick").addEventListener("change", (e) => {
  const files = [...e.target.files].map((file) => ({ file, rel: file.name }));
  e.target.value = "";
  uploadAll(files, currentDir);
});

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
async function renderDeleted() {
  const data = await attempt(() => api("/api/deleted"));
  const items = data ? data.items : [];
  page(h("h1", {}, "Deleted"),
       h("p", { class: "lede" }, "Deleted files are kept for a while (see Settings) and can be brought back on every device."),
       items.length ? h("div", { class: "list rows-simple" }, items.map((it) => h("div", { class: "row" },
         h("span", { class: "name" }, icon(kind(it.path)), h("span", { style: "min-width:0" },
           h("span", { class: "label" }, base(it.path)), h("div", { class: "where" }, parent(it.path)))),
         h("span", { class: "size" }, size(it.size)),
         h("span", { class: "date" }, when(it.at)),
         h("button", { class: "btn ghost small", onclick: async (e) => {
           e.target.disabled = true;
           if (await attempt(() => api("/api/undelete", { path: it.path }), `${base(it.path)} restored`)) setTimeout(renderDeleted, 2500);
           else e.target.disabled = false;
         } }, "Restore"))))
       : h("div", { class: "empty" }, h("b", {}, "Nothing deleted"), "Files you delete show up here."));
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
  const restore = h("button", { class: "btn", onclick: async () => {
    const ok = await ask({ title: `Restore ${path === "/" ? "the whole drive" : "“" + base(path) + "”"}?`, ok: "Restore",
                           text: "It is copied into a new folder named after the snapshot, so nothing you have now is changed." });
    if (!ok) return;
    const r = await attempt(() => api("/api/snapshots/restore", { id, path }));
    if (r) { toast(`${plural(r.files, "file")} restored into ${r.folder}`); setTimeout(() => go("#/files" + enc(r.folder)), 2500); }
  } }, path === "/" ? "Restore everything" : "Restore this folder");
  page(h("div", { class: "bar" },
         crumbs(path, title, (p) => `#/snapshot/${id}` + enc(p)),
         h("div", { class: "actions" }, h("a", { class: "btn ghost", href: "#/snapshots" }, "All snapshots"), restore)),
       list.items.length ? h("div", { class: "list" }, listHead(), list.items.map((it) => h(it.dir ? "a" : "div",
         it.dir ? { class: "row", href: `#/snapshot/${id}` + enc(it.path) } : { class: "row" },
         h("span", { class: "name" }, icon(it.dir ? "folder" : (kind(it.name) === "pdf" ? "text" : kind(it.name)), it.dir ? "folder" : ""),
           h("span", { class: "label" }, it.name)),
         h("span", { class: "size" }, it.dir ? "" : size(it.size)),
         h("span", { class: "date" }, when(it.mtime)), h("span"))))
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

// ------------------------------------------------------------------ start
render();
refreshStatus();
setInterval(refreshStatus, 3000);
