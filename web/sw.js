const CACHE="matchlab-shell-v7";
const SHELL=["/","/web/app.css?v=7","/web/app.js?v=7","/web/icon.svg","/web/onboarding.css?v=7"];
self.addEventListener("install",e=>{self.skipWaiting();e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)))});
self.addEventListener("activate",e=>e.waitUntil(Promise.all([self.clients.claim(),caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))])));
self.addEventListener("fetch",e=>{
  const u=new URL(e.request.url);
  if(u.pathname.startsWith("/api/")) return;
  if(e.request.method!=="GET") return;
  e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));
});