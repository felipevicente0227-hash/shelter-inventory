// sw.js - lets the browser version open without internet after the first visit.
//
// It keeps a copy of the page, the two Python files and the pinned Pyodide
// files in the browser's cache. It only ever stores files; your inventory
// itself is in the browser's IndexedDB and is never sent anywhere.
//
// Bump CACHE on every release (tests.py checks it matches APP_VERSION), and
// keep PYODIDE in step with PYODIDE_URL in index.html.
const CACHE = "shelter-inventory-v0.7.0";
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const FILES = ["./", "inventory_core.py", "browser_api.py", "favicon.ico"];
const PYODIDE_FILES = ["pyodide.js", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]
  .map((f) => PYODIDE + f);

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll([...FILES, ...PYODIDE_FILES])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k.startsWith("shelter-inventory-") && k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (req.url.startsWith(PYODIDE)) {
    // Pinned version: these files never change, so the cache always wins.
    event.respondWith(caches.match(req, {ignoreVary: true}).then((hit) => hit || fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
      return res;
    })));
  } else if (url.origin === self.location.origin) {
    // Our own files: the newest copy when online, the saved copy when not.
    event.respondWith(fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
      return res;
    }).catch(() => caches.match(req, {ignoreSearch: true})
      .then((hit) => hit || (req.mode === "navigate" ? caches.match("./") : undefined))
      .then((hit) => hit || Response.error())));
  }
});
