// Service worker: lets browsers install MacroRail as an app (they require one, on HTTPS or
// localhost). It adds no caching: the app is only useful while the Pi is reachable, and a
// cached copy of the UI could fall out of step with the server it talks to.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {
  // Let every request go to the network as usual.
});
