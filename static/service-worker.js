self.addEventListener("install", event => {
  event.waitUntil(
    caches.open("kiatsu-cache-v1").then(cache => {
      return cache.addAll([
        "/",
        "/static/manifest.json",
        "/static/icon.png"
      ]);
    })
  );
});

self.addEventListener("fetch", event => {
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});