from __future__ import annotations


def prelaunch_dashboard_html() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MatchLab — pre-launch dashboard</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f5f5f7;color:#111}
main{max-width:1100px;margin:32px auto;padding:0 20px}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:24px}
h1{margin:0 0 6px;font-size:30px}
a{color:#111}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-bottom:26px}
.card{background:#fff;padding:18px;border-radius:16px;box-shadow:0 2px 12px rgba(0,0,0,.05)}
.value{font-size:34px;font-weight:750;margin-top:6px}
.section{background:#fff;border-radius:16px;padding:20px;margin:16px 0}
.funnel-row{display:grid;grid-template-columns:220px 1fr 70px;gap:12px;align-items:center;margin:10px 0}
.track{background:#eee;height:12px;border-radius:999px;overflow:hidden}
.fill{background:#111;height:100%;border-radius:999px}
.small{color:#666;font-size:14px}
table{width:100%;border-collapse:collapse}
td,th{text-align:left;padding:9px;border-bottom:1px solid #eee}
button{font:inherit;border:0;border-radius:10px;padding:10px 14px;background:#111;color:#fff;cursor:pointer}
</style>
</head>
<body>
<main>
<header>
<div>
<h1>MatchLab · pre-launch</h1>
<div class="small">Качество и готовность базы до открытия matching</div>
</div>
<div>
<a href="/moderation/photos">Модерация фото</a>
&nbsp;&nbsp;
<button onclick="load()">Обновить</button>
</div>
</header>
<div id="status" class="small">Загрузка…</div>
<div id="cards" class="cards"></div>
<div class="section">
<h2>Воронка готовности</h2>
<div id="funnel"></div>
</div>
<div class="section">
<h2>Состав базы</h2>
<div id="composition"></div>
</div>
</main>
<script>
async function api(path){
  const response=await fetch(path,{credentials:"same-origin"});
  let data={};
  try{data=await response.json();}catch(e){}
  if(!response.ok) throw new Error(data.error||data.message||("HTTP "+response.status));
  return data;
}
function card(label,value){
  return '<div class="card"><div class="small">'+label+'</div><div class="value">'+value+'</div></div>';
}
function table(title,obj){
  const rows=Object.entries(obj||{}).map(([k,v])=>'<tr><td>'+k+'</td><td>'+v+'</td></tr>').join("");
  return '<h3>'+title+'</h3><table><tbody>'+rows+'</tbody></table>';
}
async function load(){
  const status=document.getElementById("status");
  status.textContent="Обновляем…";
  try{
    const data=await api("/api/v1/admin/prelaunch/metrics");
    document.getElementById("cards").innerHTML=
      card("Активные пользователи",data.users.active)+
      card("Новые за 24 часа",data.users.new_24h)+
      card("Новые за 7 дней",data.users.new_7d)+
      card("Фото на модерации",data.pending_photos);

    const base=Math.max(1,data.users.active||0);
    document.getElementById("funnel").innerHTML=(data.funnel||[]).map(row=>{
      const pct=Math.round(100*row.count/base);
      return '<div class="funnel-row">'+
        '<div>'+row.label+'</div>'+
        '<div class="track"><div class="fill" style="width:'+Math.min(100,pct)+'%"></div></div>'+
        '<div>'+row.count+' <span class="small">('+pct+'%)</span></div>'+
        '</div>';
    }).join("");

    const markets=(data.markets||[]).map(x=>[x.code+" · "+x.name,x.profiles]);
    document.getElementById("composition").innerHTML=
      table("Пол",data.gender)+
      table("Статус отношений",data.relationship)+
      '<h3>Рынки</h3><table><tbody>'+
      markets.map(x=>'<tr><td>'+x[0]+'</td><td>'+x[1]+'</td></tr>').join("")+
      '</tbody></table>';

    status.textContent="Обновлено: "+new Date(data.generated_at).toLocaleString();
  }catch(e){
    status.textContent="Ошибка: "+e.message;
  }
}
load();
</script>
</body>
</html>"""
