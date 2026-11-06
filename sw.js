// Network first so a new version shows up immediately when online;
// cached copy when offline or when the venue wifi takes longer than 3s.
const C = "devfestka-2026";
// Speaker photos are precached on install so every avatar works offline, even ones not scrolled to yet.
const PRECACHE = ["./", "./speakers/af.webp","./speakers/christianl.webp","./speakers/ck.webp","./speakers/ds.webp","./speakers/fs.webp","./speakers/gm.webp","./speakers/jp.webp","./speakers/jr.webp","./speakers/krc.webp","./speakers/kv.webp","./speakers/lc.webp","./speakers/lr.webp","./speakers/mb.webp","./speakers/mis.webp","./speakers/mreuter.webp","./speakers/mr.webp","./speakers/ms.webp","./speakers/np.webp","./speakers/rh.webp","./speakers/sl.webp","./speakers/ts.webp"];
self.addEventListener("install", e => { self.skipWaiting(); e.waitUntil(caches.open(C).then(c => c.addAll(PRECACHE))); });
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  e.respondWith(caches.open(C).then(async c => {
    const net = fetch(e.request, { cache: "no-cache" }).then(r => {
      if (r.ok || r.type === "opaque") c.put(e.request, r.clone());
      return r;
    });
    const slow = new Promise(res => setTimeout(res, 3000));
    const hit = await c.match(e.request, { ignoreSearch: true });
    if (!hit) return net;
    return Promise.race([net.catch(() => hit), slow.then(() => hit)]);
  }));
});
