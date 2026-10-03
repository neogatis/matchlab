from __future__ import annotations


def photo_moderation_html() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MatchLab — модерация фото</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f5f5f7;color:#111}
main{max-width:1100px;margin:32px auto;padding:0 20px}
header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:24px}
h1{margin:0;font-size:28px}
button{font:inherit;border:0;border-radius:10px;padding:10px 14px;cursor:pointer;font-weight:650}
.refresh{background:#111;color:white}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:18px}
.card{background:white;border-radius:16px;padding:14px;box-shadow:0 2px 12px rgba(0,0,0,.06)}
.card img{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:12px;background:#eee}
.meta{font-size:13px;color:#666;margin:10px 0}
.actions{display:flex;gap:8px}
.approve{background:#111;color:white;flex:1}
.reject{background:#eee;color:#111;flex:1}
.empty{padding:48px 0;color:#666}
.status{margin:10px 0 18px;color:#555;min-height:22px}
</style>
</head>
<body>
<main>
<header>
<div>
<h1>MatchLab · модерация фото</h1>
<div>Pending-фото пользователей</div>
</div>
<button class="refresh" onclick="loadPending()">Обновить</button>
</header>
<div id="status" class="status"></div>
<div id="grid" class="grid"></div>
</main>
<script>
function cookie(name){
  return document.cookie.split(";").map(x=>x.trim()).find(x=>x.startsWith(name+"="))?.slice(name.length+1)||"";
}
async function api(path, options={}){
  const headers={...(options.headers||{})};
  if(options.method && options.method!=="GET"){
    headers["Content-Type"]="application/json";
    headers["X-CSRF-Token"]=decodeURIComponent(cookie("ml_csrf"));
  }
  const response=await fetch(path,{credentials:"same-origin",...options,headers});
  let data={};
  try{data=await response.json();}catch(e){}
  if(!response.ok) throw new Error(data.error||data.message||("HTTP "+response.status));
  return data;
}
function esc(value){
  const div=document.createElement("div");
  div.textContent=String(value??"");
  return div.innerHTML;
}
async function loadPending(){
  const grid=document.getElementById("grid");
  const status=document.getElementById("status");
  status.textContent="Загрузка…";
  grid.innerHTML="";
  try{
    const data=await api("/api/v1/admin/photos/pending");
    const photos=data.photos||[];
    status.textContent="На модерации: "+photos.length;
    if(!photos.length){
      grid.innerHTML='<div class="empty">Новых фото нет.</div>';
      return;
    }
    for(const photo of photos){
      const card=document.createElement("div");
      card.className="card";
      card.innerHTML=
        '<img src="'+esc(photo.url)+'" alt="Фото на модерации">'+
        '<div class="meta">Photo #'+esc(photo.id)+' · User #'+esc(photo.user_id)+
        '<br>'+esc(photo.mime)+' · '+Math.round((photo.byte_size||0)/1024)+' KB</div>'+
        '<div class="actions">'+
        '<button class="approve">Одобрить</button>'+
        '<button class="reject">Отклонить</button>'+
        '</div>';
      card.querySelector(".approve").onclick=()=>moderate(photo.id,"APPROVED","");
      card.querySelector(".reject").onclick=()=>{
        const reason=prompt("Причина отклонения:","Не подходит для профиля");
        if(reason!==null) moderate(photo.id,"REJECTED",reason);
      };
      grid.appendChild(card);
    }
  }catch(e){
    status.textContent="Ошибка: "+e.message;
  }
}
async function moderate(photoId, moderationStatus, reason){
  const status=document.getElementById("status");
  status.textContent="Сохраняем решение…";
  try{
    await api("/api/v1/admin/photos/moderate",{
      method:"POST",
      body:JSON.stringify({
        photo_id:photoId,
        status:moderationStatus,
        reason:reason
      })
    });
    await loadPending();
  }catch(e){
    status.textContent="Ошибка: "+e.message;
  }
}
loadPending();
</script>
</body>
</html>"""
