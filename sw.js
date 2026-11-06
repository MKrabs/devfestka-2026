// Network first so a new version shows up immediately when online;
// cached copy when offline or when the venue wifi takes longer than 3s.
const C = "devfestka-2026";
self.addEventListener("install", () => self.skipWaiting());
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
