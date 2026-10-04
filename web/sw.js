const CACHE="matchlab-shell-v1";
const SHELL=["/","/web/app.css?v=4","/web/app.js?v=4","/web/icon.svg"];
self.addEventListener("install",e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL))));
self.addEventListener("activate",e=>e.waitUntil(self.clients.claim()));
self.addEventListener("fetch",e=>{
  const u=new URL(e.request.url);
  if(u.pathname.startsWith("/api/")) return;
  if(e.request.method!=="GET") return;
  e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));
});