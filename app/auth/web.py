from __future__ import annotations


def phone_login_html() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Вход по телефону — MatchLab</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;max-width:520px;margin:48px auto;padding:0 20px;line-height:1.5}
h1{font-size:28px;margin-bottom:8px}.muted{opacity:.7;margin-bottom:24px}
input,button{font:inherit;padding:12px;margin:6px 0;width:100%;box-sizing:border-box;border-radius:10px}
input{border:1px solid #bbb}button{border:0;cursor:pointer;font-weight:700}
.row{margin-top:18px}.status{margin-top:16px;white-space:pre-wrap}
#verifyBox{display:none}
</style>
</head>
<body>
<h1>MatchLab</h1>
<div class="muted">Вход по номеру телефона</div>

<div class="row">
<input id="phone" type="tel" autocomplete="tel" placeholder="+7 747 123 45 67">
<button id="send">Получить код</button>
</div>

<div id="verifyBox" class="row">
<input id="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="6-значный код">
<button id="verify">Войти</button>
</div>

<div id="status" class="status"></div>

<script>
const status=document.getElementById("status");
const verifyBox=document.getElementById("verifyBox");

async function post(path, body){
  const r=await fetch(path,{
    method:"POST",
    credentials:"same-origin",
    headers:{
      "Content-Type":"application/json",
      "Origin":location.origin
    },
    body:JSON.stringify(body)
  });
  let data={};
  try{ data=await r.json(); }catch(e){}
  if(!r.ok) throw new Error(data.error||data.message||("HTTP "+r.status));
  return data;
}

document.getElementById("send").addEventListener("click",async()=>{
  const phone=document.getElementById("phone").value.trim();
  status.textContent="Отправляем SMS...";
  try{
    await post("/api/v1/auth/phone/request",{phone});
    status.textContent="Код отправлен. Введите 6 цифр из SMS.";
    verifyBox.style.display="block";
    document.getElementById("code").focus();
  }catch(e){
    status.textContent="Ошибка отправки: "+e.message;
  }
});

document.getElementById("verify").addEventListener("click",async()=>{
  const phone=document.getElementById("phone").value.trim();
  const code=document.getElementById("code").value.trim();
  status.textContent="Проверяем код...";
  try{
    const data=await post("/api/v1/auth/phone/verify",{phone,code});
    status.textContent="Готово. Вход выполнен. User ID: "+data.user_id;
  }catch(e){
    status.textContent="Ошибка проверки: "+e.message;
  }
});
</script>
</body>
</html>"""
