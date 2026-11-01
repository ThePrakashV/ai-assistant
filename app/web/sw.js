// Service worker: app shell (page + css + js) ah cache pannum. Chat server ku thaan, adhu offline work aagaadhu.
const CACHE = "nova-shell-v2";
const SHELL = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/pcm-worklet.js",
  "/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

// Network-first: code maathina udane puthusa varum. Network illana mattum cache.
self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/ws") || url.pathname === "/health") return;
  // Privacy / audit API responses (export data kooda) ethaiyum cache pannaadha
  if (url.pathname.startsWith("/api/")) return;

  event.respondWith(
    fetch(request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
        return response;
      })
      .catch(() => caches.match(request))
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window" }).then((windows) => {
      if (windows.length) return windows[0].focus();
      return self.clients.openWindow("/");
    })
  );
});