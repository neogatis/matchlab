(() => {
  const root = document.getElementById("app");
  const HERO_IMAGE = "https://images.unsplash.com/photo-1776266099714-2177bb456209?auto=format&fit=crop&fm=jpg&q=86&w=2400";
  const state = {
    authenticated: false,
    profile: null,
    onboarding: null,
    candidates: [],
    matches: [],
    conversations: [],
    currentCandidate: null,
    currentConversation: null,
    poller: null,
    voiceRecorder: null,
    voiceTimer: null,
    mediaSending: false,
  };

  function safeStorage(storage,key,value){
    try{
      if(arguments.length===2)return storage.getItem(key);
      storage.setItem(key,value);
    }catch{}
    return null;
  }

  function captureFirstTouchAttribution(){
    let saved={};
    try{saved=JSON.parse(safeStorage(localStorage,"ml_first_touch_attribution")||"{}")||{}}catch{}
    const params=new URLSearchParams(location.search);
    const referral=params.get("ref")||params.get("referral")||params.get("referral_code")||"";
    const incoming={
      utm_source:params.get("utm_source")||"",
      utm_medium:params.get("utm_medium")||"",
      utm_campaign:params.get("utm_campaign")||"",
      utm_content:params.get("utm_content")||"",
      utm_term:params.get("utm_term")||"",
      referral_input:referral,
    };
    let changed=false;
    Object.entries(incoming).forEach(([key,value])=>{
      if(value&&!saved[key]){saved[key]=value;changed=true}
    });
    if(changed||!safeStorage(localStorage,"ml_first_touch_attribution")){
      safeStorage(localStorage,"ml_first_touch_attribution",JSON.stringify(saved));
    }
    return saved;
  }

  function attribution(){
    try{return JSON.parse(safeStorage(localStorage,"ml_first_touch_attribution")||"{}")||{}}catch{return {}}
  }

  function visitorId(){
    let id=safeStorage(localStorage,"ml_visitor_id");
    if(!id){
      id=(crypto.randomUUID?crypto.randomUUID():"v-"+Date.now()+"-"+Math.random().toString(36).slice(2));
      safeStorage(localStorage,"ml_visitor_id",id);
    }
    return id;
  }

  async function trackAnonymous(eventType,metadata={}){
    try{
      await post("/api/v1/analytics/event",{
        event_type:eventType,
        visitor_id:visitorId(),
        metadata:{...attribution(),...metadata},
      });
    }catch{}
  }

  function trackRegistrationStarted(){
    if(safeStorage(sessionStorage,"ml_registration_started"))return;
    safeStorage(sessionStorage,"ml_registration_started","1");
    trackAnonymous("REGISTRATION_STARTED");
  }

  function trackCandidateViewed(candidateId){
    const key="ml_candidate_viewed_"+candidateId;
    if(safeStorage(sessionStorage,key))return;
    safeStorage(sessionStorage,key,"1");
    post("/api/v1/analytics/product",{
      event_type:"CANDIDATE_VIEWED",
      metadata:{candidate_user_id:Number(candidateId)}
    }).catch(()=>{});
  }

  const esc = (value="") => String(value)
    .replaceAll("&","&amp;").replaceAll("<","&lt;")
    .replaceAll(">","&gt;").replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");

  const cookie = name => document.cookie.split(";")
    .map(v => v.trim())
    .find(v => v.startsWith(name + "="))
    ?.slice(name.length + 1) || "";

  const FRIENDLY_ERRORS = {
    invalid_credentials:"Неверный логин или пароль.",
    invalid_or_expired_challenge:"Код устарел или введён неверно. Запросите новый.",
    rate_limited:"Слишком много попыток. Попробуйте немного позже.",
    phone_already_registered:"Этот номер уже зарегистрирован.",
    email_already_registered:"Этот email уже зарегистрирован.",
    blocked:"Действие недоступно.",
    sender_inactive:"Отправка сообщений сейчас недоступна.",
    recipient_inactive:"Этому пользователю сейчас нельзя отправить сообщение.",
    message_is_empty:"Введите сообщение.",
    message_too_long:"Сообщение слишком длинное.",
    chat_media_too_large:"Файл слишком большой.",
    unsupported_chat_media_type:"Этот формат файла пока не поддерживается.",
    invalid_chat_media_content:"Не удалось проверить файл. Выберите другой.",
    chat_media_upload_not_prepared:"Не удалось подготовить вложение. Попробуйте ещё раз.",
    chat_media_upload_expired:"Время загрузки истекло. Выберите файл ещё раз.",
    chat_media_caption_too_long:"Подпись к вложению должна быть короче 1000 символов.",
    deletion_already_requested:"Запрос на удаление аккаунта уже принят.",
    underage:"MatchLab доступен только пользователям 18+.",
    profile_not_found:"Профиль пока не готов.",
    market_unavailable:"Выберите доступный город.",
  };

  function friendlyError(error, fallback="Что-то пошло не так. Попробуйте ещё раз.") {
    const code=String(error?.code||"").trim().toLowerCase();
    if(FRIENDLY_ERRORS[code])return FRIENDLY_ERRORS[code];
    const statusCode=Number(error?.status||0);
    if(statusCode===401)return "Сессия завершилась. Войдите в аккаунт ещё раз.";
    if(statusCode===429)return "Слишком много попыток. Попробуйте немного позже.";
    if(statusCode>=500)return "Сервис временно недоступен. Попробуйте ещё раз чуть позже.";
    const message=String(error?.message||"").trim();
    const looksTechnical=/(http\s*\d|csrf|backend|api\b|sql|postgres|s3|fcm|token|stack|trace|exception|invalid_|not_|_required|_failed|_error)/i.test(message);
    if(message && /^[А-Яа-яЁё]/.test(message) && !looksTechnical)return message;
    return fallback;
  }

  async function refreshCsrf(){
    try{
      await fetch("/api/v1/auth/csrf",{
        method:"GET",
        credentials:"include",
        headers:{"Accept":"application/json"},
      });
    }catch{}
  }

  async function api(path, options={}) {
    const csrfRetried=!!options._csrfRetried;
    const cleanOptions={...options};
    delete cleanOptions._csrfRetried;
    const method=String(cleanOptions.method||"GET").toUpperCase();
    const unsafe=!["GET","HEAD","OPTIONS"].includes(method);
    if(unsafe&&!cookie("ml_csrf"))await refreshCsrf();
    const headers={"Accept":"application/json",...(cleanOptions.headers||{})};
    if(unsafe){
      headers["Content-Type"]="application/json";
      headers["X-CSRF-Token"]=decodeURIComponent(cookie("ml_csrf"));
      headers["Origin"]=location.origin;
    }
    const response=await fetch(path,{
      credentials:"include",
      ...cleanOptions,
      method,
      headers,
    });
    const text=await response.text();
    let data={};
    try{data=text?JSON.parse(text):{}}catch{}
    if(!response.ok){
      if(response.status===403&&unsafe&&!csrfRetried){
        await refreshCsrf();
        return api(path,{...cleanOptions,_csrfRetried:true});
      }
      const error=new Error(data.message||data.error||"request_failed");
      error.status=response.status;
      error.code=data.error;
      throw error;
    }
    return data;
  }

  const post = (path, body={}) => api(path, {
    method:"POST",
    body:JSON.stringify(body),
  });

  function setRoute(route) {
    if (location.hash !== "#" + route) location.hash = route;
    else renderRoute();
  }

  function clearPoller() {
    if (state.poller) clearInterval(state.poller);
    state.poller = null;
    if (state.voiceTimer) clearInterval(state.voiceTimer);
    state.voiceTimer = null;
    if (state.voiceRecorder) {
      const session=state.voiceRecorder;
      session.cancelled=true;
      try {
        if(session.recorder&&session.recorder.state!=="inactive") session.recorder.stop();
      } catch {}
      try { session.stream?.getTracks()?.forEach(track=>track.stop()); } catch {}
      state.voiceRecorder=null;
    }
  }

  function navIcon(key){
    const icons={
      home:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 10.8 12 3.8l8.5 7v8.4a1.8 1.8 0 0 1-1.8 1.8H5.3a1.8 1.8 0 0 1-1.8-1.8Z"/><path d="M9.2 21v-6.7h5.6V21"/></svg>',
      matches:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.8 4.9a5.2 5.2 0 0 0-7.4 0L12 6.3l-1.4-1.4a5.2 5.2 0 0 0-7.4 7.4L12 21l8.8-8.7a5.2 5.2 0 0 0 0-7.4Z"/></svg>',
      chats:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 11.3a8.2 8.2 0 0 1-8.6 8.2 9 9 0 0 1-3.6-.8L3.5 21l1.4-4.1A8.1 8.1 0 1 1 20.5 11.3Z"/></svg>',
      profile:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4.6 21c.7-4.2 3.4-6.5 7.4-6.5s6.7 2.3 7.4 6.5"/></svg>',
    };
    return icons[key]||"";
  }

  function nav(active) {
    const items = [
      ["home","Главная"],
      ["matches","Совпадения"],
      ["chats","Чаты"],
      ["profile","Профиль"],
    ];
    return '<nav class="bottom-nav">' + items.map(([key,label]) =>
      '<button class="nav-btn ' + (active===key?"active":"") + '" data-route="' + key + '">' +
      '<i>' + navIcon(key) + '</i><span>' + label + '</span></button>'
    ).join("") + '</nav>';
  }

  function topbar(title="MatchLab") {
    return '<header class="topbar">' +
      '<div><div class="eyebrow">MatchLab</div><div class="brand" style="font-size:28px">' +
      esc(title === "MatchLab" ? "Match" : title) +
      (title === "MatchLab" ? '<span>Lab</span>' : '') +
      '</div></div>' +
      '<div class="top-actions"><button class="icon-btn" id="refresh-btn">↻</button></div>' +
    '</header>';
  }

  function bindCommon() {
    document.querySelectorAll("[data-route]").forEach(btn => {
      btn.onclick = () => setRoute(btn.dataset.route);
    });
    const refresh = document.getElementById("refresh-btn");
    if (refresh) refresh.onclick = () => renderRoute(true);
  }

  function status(message, error=false) {
    const el = document.getElementById("form-status");
    if (!el) return;
    el.className = "status" + (error ? " error" : "");
    el.textContent = message;
    el.hidden = false;
  }

  function showCandidateFeedback(message) {
    document.querySelector(".candidate-feedback")?.remove();
    const el = document.createElement("div");
    el.className = "candidate-feedback";
    el.textContent = message;
    document.body.appendChild(el);
    requestAnimationFrame(() => el.classList.add("show"));
    setTimeout(() => {
      el.classList.remove("show");
      setTimeout(() => el.remove(), 240);
    }, 2600);
  }

  function renderAuth(mode="login") {
    clearPoller();
    const register = mode === "register";
    root.innerHTML = '<main class="auth-screen auth-v19">' +
      '<div class="auth-v19-decor auth-v19-decor-a"></div><div class="auth-v19-decor auth-v19-decor-b"></div>' +
      '<div class="auth-wrap auth-v19-wrap">' +
        '<header class="auth-v19-header">' +
          '<div class="auth-logo auth-v19-logo"><div class="brand">Match<span>Lab</span></div></div>' +
          '<div class="auth-tagline auth-v19-tagline">' +
            '<h1>Не выбирай из всех.<br><span>Найди подходящего.</span></h1>' +
            '<p>Общие ценности, реальные люди и серьёзные намерения.</p>' +
          '</div>' +
        '</header>' +
        '<div class="auth-panel auth-v19-panel">' +
          '<div class="tabs auth-switch">' +
            '<button class="tab ' + (!register?"active":"") + '" id="auth-login-tab">Вход</button>' +
            '<button class="tab ' + (register?"active":"") + '" id="auth-register-tab">Регистрация</button>' +
          '</div>' +
          '<section class="auth-card auth-v19-card">' +
            '<div class="eyebrow">' + (register?"НОВЫЙ ПРОФИЛЬ":"С ВОЗВРАЩЕНИЕМ") + '</div>' +
            '<h2>' + (register?"Создайте аккаунт":"Войдите в MatchLab") + '</h2>' +
            '<p class="muted">' +
              (register
                ?"Регистрация займёт пару минут. Затем начнём анкету совместимости."
                :"По SMS-коду или телефону/email и паролю.") +
            '</p>' +
            (register ? registerForm() : loginForm()) +
            '<div id="form-status" class="status" hidden></div>' +
          '</section>' +
        '</div>' +
        '<p class="auth-legal muted">18+. Продолжая, вы принимаете <a href="/terms" target="_blank" rel="noopener">Условия</a> и <a href="/privacy" target="_blank" rel="noopener">Политику конфиденциальности</a>.</p>' +
      '</div>' +
    '</main>';
    document.getElementById("auth-login-tab").onclick = () => renderAuth("login");
    document.getElementById("auth-register-tab").onclick = () => {trackRegistrationStarted();renderAuth("register")};
    if(register)trackRegistrationStarted();
    register ? bindRegister() : bindLogin();
  }

  function loginForm() {
    return '<div class="tabs auth-method-tabs" id="login-method-tabs">' +
      '<button class="tab active" data-login-method="password">Пароль</button>' +
      '<button class="tab" data-login-method="sms">SMS-код</button>' +
    '</div>' +
    '<div id="login-password" class="form-stack auth-form-stack">' +
      '<label class="auth-input-wrap"><input class="input" id="login-identifier" placeholder="Телефон или email" autocomplete="username"></label>' +
      '<label class="auth-input-wrap"><input class="input" id="login-password-value" type="password" placeholder="Пароль" autocomplete="current-password"></label>' +
      '<button class="primary full" id="password-login-btn">Войти →</button>' +
      '<button class="ghost full auth-link-btn" id="forgot-password-btn" type="button">Забыли пароль?</button>' +
    '</div>' +
    '<div id="login-sms" class="form-stack auth-form-stack" hidden>' +
      '<label class="auth-input-wrap"><input class="input" id="sms-phone" placeholder="+7 747 123 45 67" inputmode="tel"></label>' +
      '<button class="primary full" id="sms-request-btn">Получить SMS-код →</button>' +
      '<input class="input" id="sms-code" placeholder="6-значный код" inputmode="numeric" hidden>' +
      '<input class="input" id="sms-new-password" type="password" placeholder="Задать пароль — необязательно" hidden>' +
      '<button class="primary full" id="sms-verify-btn" hidden>Войти →</button>' +
    '</div>';
  }

  function bindLogin() {
    document.querySelectorAll("[data-login-method]").forEach(btn => {
      btn.onclick = () => {
        const method = btn.dataset.loginMethod;
        document.querySelectorAll("[data-login-method]").forEach(x => x.classList.toggle("active", x===btn));
        document.getElementById("login-password").hidden = method !== "password";
        document.getElementById("login-sms").hidden = method !== "sms";
      };
    });
    document.getElementById("forgot-password-btn").onclick = () => setRoute("reset-password");
    document.getElementById("password-login-btn").onclick = async () => {
      const identifier = document.getElementById("login-identifier").value.trim();
      const password = document.getElementById("login-password-value").value;
      if (!identifier || !password) return status("Введите телефон/email и пароль.", true);
      status("Входим…");
      try {
        await post("/api/v1/auth/login",{identifier,password});
        await afterAuth();
      } catch(e) { status("Не удалось войти. Проверьте данные.", true); }
    };
    document.getElementById("sms-request-btn").onclick = async () => {
      const phone = document.getElementById("sms-phone").value.trim();
      if (!phone) return status("Введите номер телефона.", true);
      status("Отправляем SMS…");
      try {
        await post("/api/v1/auth/phone/request",{phone});
        document.getElementById("sms-code").hidden = false;
        document.getElementById("sms-new-password").hidden = false;
        document.getElementById("sms-verify-btn").hidden = false;
        status("Код отправлен. Введите 6 цифр.");
      } catch(e) { status("Не удалось отправить код: " + friendlyError(e), true); }
    };
    document.getElementById("sms-verify-btn").onclick = async () => {
      const phone = document.getElementById("sms-phone").value.trim();
      const code = document.getElementById("sms-code").value.trim();
      const password = document.getElementById("sms-new-password").value;
      if (!code) return status("Введите код из SMS.", true);
      if (password && password.length < 10) return status("Пароль — минимум 10 символов.", true);
      status("Проверяем код…");
      try {
        await post("/api/v1/auth/phone/verify",{phone,code,...(password?{password}:{})});
        await afterAuth();
      } catch(e) { status("Код неверный или истёк.", true); }
    };
  }


  function renderPasswordReset() {
    clearPoller();
    const raw=(location.hash||"#reset-password").slice(1);
    const query=new URLSearchParams(raw.includes("?")?raw.split("?").slice(1).join("?"):"");
    const linkedEmail=query.get("email")||"";
    const linkedToken=query.get("challenge")||"";
    const hasLink=!!(linkedEmail&&linkedToken);

    root.innerHTML='<main class="auth-screen"><div class="auth-wrap">'+
      '<div class="auth-logo"><div class="brand-mark">♡</div><div class="brand">Match<span>Lab</span></div></div>'+
      '<div class="auth-tagline"><div class="eyebrow">Безопасность аккаунта</div><h1>Верните доступ<br><span>к MatchLab.</span></h1><p>Сбросьте пароль по номеру телефона или email.</p></div>'+
      '<div class="auth-panel"><section class="auth-card">'+
        '<div class="eyebrow">Восстановление доступа</div><h2 style="font-family:Georgia,serif;font-size:30px;line-height:1.04;margin:7px 0 8px">'+
          (hasLink?'Задайте новый пароль':'Как восстановить пароль?')+
        '</h2>'+
        (hasLink
          ? '<div class="form-stack"><input class="input" value="'+esc(linkedEmail)+'" disabled>'+
            '<input class="input" id="reset-linked-password" type="password" autocomplete="new-password" placeholder="Новый пароль — минимум 10 символов">'+
            '<button class="primary full" id="reset-linked-confirm">Сохранить новый пароль →</button></div>'
          : '<div class="tabs" id="reset-method-tabs"><button class="tab active" data-reset-method="phone">По номеру</button><button class="tab" data-reset-method="email">По email</button></div>'+
            '<div id="reset-phone" class="form-stack">'+
              '<input class="input" id="reset-phone-value" placeholder="+7 747 123 45 67" inputmode="tel">'+
              '<button class="primary full" id="reset-phone-request">Получить SMS-код →</button>'+
              '<input class="input" id="reset-phone-code" placeholder="6-значный код" inputmode="numeric" hidden>'+
              '<input class="input" id="reset-phone-password" type="password" placeholder="Новый пароль — минимум 10 символов" hidden>'+
              '<button class="primary full" id="reset-phone-confirm" hidden>Сменить пароль →</button>'+
            '</div>'+
            '<div id="reset-email" class="form-stack" hidden>'+
              '<input class="input" id="reset-email-value" type="email" autocomplete="email" placeholder="Ваш email">'+
              '<button class="primary full" id="reset-email-request">Отправить ссылку →</button>'+
              '<p class="muted small">Если email зарегистрирован, вы получите ссылку для смены пароля.</p>'+
            '</div>')+
        '<div id="form-status" class="status" hidden style="margin-top:14px"></div>'+
        '<button class="ghost full" id="reset-back-login" type="button">← Вернуться ко входу</button>'+
      '</section></div>'+
      '<p class="auth-legal muted" style="font-size:11px;text-align:center;margin:13px 18px 0"><a href="/privacy" target="_blank" rel="noopener">Конфиденциальность</a> · <a href="/terms" target="_blank" rel="noopener">Условия</a></p>'+
    '</div></main>';

    document.getElementById("reset-back-login").onclick=()=>{location.hash="";renderAuth("login")};

    if(hasLink){
      document.getElementById("reset-linked-confirm").onclick=async()=>{
        const password=document.getElementById("reset-linked-password").value;
        if(password.length<10)return status("Пароль — минимум 10 символов.",true);
        status("Сохраняем новый пароль…");
        try{
          await post("/api/v1/auth/password/reset/confirm",{email:linkedEmail,token:linkedToken,password});
          await afterAuth();
        }catch(e){status("Ссылка недействительна или истекла. Запросите новую.",true)}
      };
      return;
    }

    document.querySelectorAll("[data-reset-method]").forEach(btn=>btn.onclick=()=>{
      const method=btn.dataset.resetMethod;
      document.querySelectorAll("[data-reset-method]").forEach(x=>x.classList.toggle("active",x===btn));
      document.getElementById("reset-phone").hidden=method!=="phone";
      document.getElementById("reset-email").hidden=method!=="email";
    });

    document.getElementById("reset-phone-request").onclick=async()=>{
      const phone=document.getElementById("reset-phone-value").value.trim();
      if(!phone)return status("Введите номер телефона.",true);
      status("Отправляем SMS…");
      try{
        await post("/api/v1/auth/phone/request",{phone});
        document.getElementById("reset-phone-code").hidden=false;
        document.getElementById("reset-phone-password").hidden=false;
        document.getElementById("reset-phone-confirm").hidden=false;
        status("Код отправлен. Введите код и новый пароль.");
      }catch(e){status("Не удалось отправить код: "+friendlyError(e),true)}
    };

    document.getElementById("reset-phone-confirm").onclick=async()=>{
      const phone=document.getElementById("reset-phone-value").value.trim();
      const code=document.getElementById("reset-phone-code").value.trim();
      const password=document.getElementById("reset-phone-password").value;
      if(!code)return status("Введите SMS-код.",true);
      if(password.length<10)return status("Пароль — минимум 10 символов.",true);
      status("Меняем пароль…");
      try{
        await post("/api/v1/auth/phone/verify",{phone,code,password});
        await afterAuth();
      }catch(e){status("Код неверный или истёк.",true)}
    };

    document.getElementById("reset-email-request").onclick=async()=>{
      const email=document.getElementById("reset-email-value").value.trim();
      if(!email)return status("Введите email.",true);
      status("Отправляем инструкцию…");
      try{
        const result=await post("/api/v1/auth/password/reset/request",{email});
        if(result.delivery==="email_not_configured"){
          status("Сброс по email временно не подключён. Используйте номер телефона.",true);
        }else{
          status("Если такой email зарегистрирован, ссылка уже отправлена.");
        }
      }catch(e){status("Не удалось отправить инструкцию: "+friendlyError(e),true)}
    };
  }

  function registerForm() {
    return '<div class="tabs">' +
      '<button class="tab active" data-register-method="phone">По номеру</button>' +
      '<button class="tab" data-register-method="email">По email</button>' +
    '</div>' +
    '<div id="register-phone" class="form-stack">' +
      '<input class="input" id="reg-phone" placeholder="+7 747 123 45 67" inputmode="tel">' +
      '<input class="input" id="reg-phone-password" type="password" placeholder="Придумайте пароль">' +
      '<button class="primary full" id="reg-phone-request">Получить SMS-код →</button>' +
      '<input class="input" id="reg-phone-code" placeholder="6-значный код" inputmode="numeric" hidden>' +
      '<button class="primary full" id="reg-phone-finish" hidden>Создать аккаунт →</button>' +
    '</div>' +
    '<div id="register-email" class="form-stack" hidden>' +
      '<input class="input" id="reg-email" type="email" placeholder="Email" autocomplete="email">' +
      '<input class="input" id="reg-email-password" type="password" placeholder="Придумайте пароль">' +
      '<button class="primary full" id="reg-email-finish">Зарегистрироваться →</button>' +
    '</div>' +
    '<label class="legal-check"><input type="checkbox" id="reg-legal"><span>Мне есть 18 лет, я принимаю <a href="/terms" target="_blank" rel="noopener">Условия</a> и <a href="/privacy" target="_blank" rel="noopener">Политику конфиденциальности</a>.</span></label>';
  }

  function bindRegister() {
    document.querySelectorAll("[data-register-method]").forEach(btn => {
      btn.onclick = () => {
        const method = btn.dataset.registerMethod;
        document.querySelectorAll("[data-register-method]").forEach(x => x.classList.toggle("active", x===btn));
        document.getElementById("register-phone").hidden = method !== "phone";
        document.getElementById("register-email").hidden = method !== "email";
      };
    });
    document.getElementById("reg-phone-request").onclick = async () => {
      if(!document.getElementById("reg-legal").checked)return status("Подтвердите 18+ и принятие Условий и Политики конфиденциальности.",true);
      const phone = document.getElementById("reg-phone").value.trim();
      const password = document.getElementById("reg-phone-password").value;
      if (!phone) return status("Введите номер телефона.", true);
      if (password.length < 10) return status("Пароль — минимум 10 символов.", true);
      status("Отправляем SMS…");
      try {
        await post("/api/v1/auth/phone/register/request",{phone});
        document.getElementById("reg-phone-code").hidden = false;
        document.getElementById("reg-phone-finish").hidden = false;
        status("Код отправлен.");
      } catch(e) {
        status(e.code === "phone_already_registered"
          ? "Этот номер уже зарегистрирован. Перейдите во «Вход»."
          : "Не удалось отправить код: " + friendlyError(e), true);
      }
    };
    document.getElementById("reg-phone-finish").onclick = async () => {
      const phone = document.getElementById("reg-phone").value.trim();
      const password = document.getElementById("reg-phone-password").value;
      const code = document.getElementById("reg-phone-code").value.trim();
      status("Создаём профиль…");
      try {
        await post("/api/v1/auth/phone/register/verify",{
          phone,password,code,
          referral_code:attribution().referral_input||null,
          attribution:attribution()
        });
        await afterAuth();
      } catch(e) { status("Не удалось зарегистрироваться: " + friendlyError(e), true); }
    };
    document.getElementById("reg-email-finish").onclick = async () => {
      if(!document.getElementById("reg-legal").checked)return status("Подтвердите 18+ и принятие Условий и Политики конфиденциальности.",true);
      const email = document.getElementById("reg-email").value.trim();
      const password = document.getElementById("reg-email-password").value;
      if (!email) return status("Введите email.", true);
      if (password.length < 10) return status("Пароль — минимум 10 символов.", true);
      status("Создаём аккаунт…");
      try {
        await post("/api/v1/auth/register",{
          email,password,
          referral_code:attribution().referral_input||null,
          attribution:attribution()
        });
        await afterAuth();
      } catch(e) { status("Не удалось зарегистрироваться: " + friendlyError(e), true); }
    };
  }

  async function afterAuth() {
    state.authenticated = true;
    await loadMe();
    const done = !!state.onboarding?.completion?.profile;
    setRoute(done ? "home" : "onboarding");
  }

  async function loadMe() {
    try {
      const [profile,onboarding] = await Promise.all([
        api("/api/v1/profile/me"),
        api("/api/v1/onboarding"),
      ]);
      state.profile = profile;
      state.onboarding = onboarding;
    } catch {}
  }

  function loading(active="home") {
    root.innerHTML = '<main class="page">' + topbar() + '<div class="loader"></div></main>' + nav(active);
    bindCommon();
  }

  function photo(profile, cls="avatar") {
    const url = profile?.photos?.[0];
    return url
      ? '<img class="' + cls + '" src="' + esc(url) + '" alt="' + esc(profile.display_name || "Фото") + '">'
      : '<div class="' + cls + '" style="display:grid;place-items:center;font-size:24px;color:var(--coral)">♡</div>';
  }

  function compatibilityReason(candidate) {
    const scores = candidate.category_scores || {};
    const entries = Object.entries(scores).sort((a,b)=>Number(b[1])-Number(a[1])).slice(0,3);
    return entries.map(([key,value]) =>
      '<span class="tag">' + esc(compatibilityMeta(key).label) + ' · ' + esc(value) + '%</span>'
    ).join("") || '<span class="tag">Совместимые критерии</span>';
  }

  const COMPATIBILITY_META = {
    values:{
      label:"Ценности",icon:"💜",
      high:"очень близкие",mid:"много общего",soft:"есть точки совпадения",
      highCopy:"Ваши ответы о жизненных приоритетах и важных принципах во многом совпадают.",
      midCopy:"У вас много общего в жизненных приоритетах, а различия могут помочь лучше узнать взгляды друг друга.",
      softCopy:"Есть общие ориентиры, которые стоит раскрыть подробнее в разговоре.",
      attention:"Полезно обсудить, какие жизненные принципы для каждого особенно важны в отношениях."
    },
    relationship:{
      label:"Отношения",icon:"🤝",
      high:"ожидания совпадают",mid:"похожий взгляд",soft:"есть точки совпадения",
      highCopy:"Ваши ожидания от отношений, близости и личных границ хорошо сочетаются.",
      midCopy:"В представлении об отношениях у вас много общего, при этом некоторые ожидания лучше проговорить.",
      softCopy:"Есть совместимые ожидания, которые стоит уточнить при знакомстве.",
      attention:"Можно заранее поговорить о темпе сближения, личном пространстве и ожиданиях от отношений."
    },
    family:{
      label:"Семья",icon:"🏠",
      high:"очень близко",mid:"похожий взгляд",soft:"есть общее",
      highCopy:"Ваши ответы о семье, долгосрочных планах и близких отношениях хорошо совпадают.",
      midCopy:"Во взглядах на семью есть много общего, а детали полезно обсудить лично.",
      softCopy:"Есть общая основа во взглядах на семью и будущее.",
      attention:"Полезно спокойно обсудить планы на семью, детей и формат совместной жизни."
    },
    children:{
      label:"Семья и дети",icon:"🏠",
      high:"взгляды совпадают",mid:"много общего",soft:"есть общая основа",
      highCopy:"Ваши ответы о семье и детях хорошо совпадают.",
      midCopy:"В вопросах семьи и детей у вас много общего, а детали можно уточнить при общении.",
      softCopy:"Есть общая основа во взглядах на семью и будущее.",
      attention:"Полезно заранее проговорить ожидания по семье и детям — без спешки и давления."
    },
    communication:{
      label:"Общение",icon:"💬",
      high:"высокая совместимость",mid:"хорошо сочетается",soft:"есть потенциал",
      highCopy:"Ваши стили общения хорошо сочетаются: есть потенциал спокойно обсуждать важные темы.",
      midCopy:"В общении у вас много совместимых привычек, а различия могут дополнять друг друга.",
      softCopy:"Есть точки соприкосновения в общении, которые лучше проверить в живом диалоге.",
      attention:"Стоит узнать, как каждому удобнее обсуждать сложные темы и когда нужно личное пространство."
    },
    lifestyle:{
      label:"Образ жизни",icon:"🌙",
      high:"ритм близкий",mid:"в целом совпадает",soft:"есть различия",
      highCopy:"Ваш повседневный ритм, привычки и отношение к свободному времени во многом совместимы.",
      midCopy:"В образе жизни у вас много общего, хотя отдельные привычки могут отличаться.",
      softCopy:"Ваш ритм жизни отличается в некоторых деталях — это хороший повод узнать привычки друг друга.",
      attention:"Можно обсудить привычный ритм недели, социальную активность, отдых и личное время."
    },
    personality:{
      label:"Характер",icon:"✨",
      high:"хорошо дополняется",mid:"много общего",soft:"интересное сочетание",
      highCopy:"По анкете ваши личные особенности хорошо сочетаются и могут дополнять друг друга.",
      midCopy:"В характере есть много совместимых черт и несколько интересных различий.",
      softCopy:"Темпераменты отличаются, но это может дать хороший баланс при взаимном уважении.",
      attention:"Полезно обратить внимание на темп принятия решений, эмоциональность и потребность в личном времени."
    },
    intimacy:{
      label:"Близость",icon:"🫶",
      high:"ожидания близкие",mid:"хорошо сочетается",soft:"нужно узнать друг друга",
      highCopy:"Ваши ожидания от эмоциональной близости и проявления заботы хорошо сочетаются.",
      midCopy:"В представлении о близости у вас много общего, а личные нюансы лучше узнавать постепенно.",
      softCopy:"Есть совместимая основа, которую важно раскрывать в комфортном для обоих темпе.",
      attention:"Можно мягко обсудить, как каждый проявляет заботу, привязанность и нуждается в поддержке."
    },
    conflict:{
      label:"Разногласия",icon:"🧩",
      high:"подходы совместимы",mid:"можете договориться",soft:"важно понять стиль",
      highCopy:"Ваши способы реагировать на разногласия хорошо сочетаются.",
      midCopy:"У вас есть совместимые способы решать спорные ситуации и возвращаться к диалогу.",
      softCopy:"Подходы к разногласиям различаются, но их можно хорошо согласовать через открытый разговор.",
      attention:"Стоит узнать, как каждому комфортнее брать паузу, обсуждать эмоции и возвращаться к решению."
    }
  };

  function compatibilityMeta(key) {
    if (COMPATIBILITY_META[key]) return COMPATIBILITY_META[key];
    return {
      label:"Дополнительный фактор",icon:"♡",
      high:"очень близко",mid:"много общего",soft:"есть точки совпадения",
      highCopy:"По этому параметру ваши ответы очень близки.",
      midCopy:"По этому параметру у вас много общего.",
      softCopy:"По этому параметру есть точки соприкосновения, которые стоит узнать глубже.",
      attention:"Этот параметр полезно обсудить подробнее при знакомстве."
    };
  }

  function compatibilityLevel(value, meta) {
    const score = Number(value) || 0;
    if (score >= 85) return {label:meta.high,copy:meta.highCopy,tone:"strong"};
    if (score >= 70) return {label:meta.mid,copy:meta.midCopy,tone:"good"};
    return {label:meta.soft,copy:meta.softCopy,tone:"soft"};
  }

  function overallCompatibility(score) {
    const value = Number(score) || 0;
    if (value >= 85) return "высокая совместимость";
    if (value >= 75) return "хорошая совместимость";
    if (value >= 65) return "перспективная совместимость";
    return "есть точки соприкосновения";
  }

  function compatibilityReasonCard(key,value) {
    const meta=compatibilityMeta(key);
    const level=compatibilityLevel(value,meta);
    return '<article class="compatibility-reason '+level.tone+'">'+
      '<div class="compatibility-reason-icon">'+esc(meta.icon)+'</div>'+
      '<div class="compatibility-reason-copy">'+
        '<div class="compatibility-reason-head"><b>'+esc(meta.label)+'</b><span>'+esc(level.label)+'</span></div>'+
        '<p>'+esc(level.copy)+'</p>'+
        '<div class="compatibility-mini-track" aria-hidden="true"><i style="width:'+Math.max(0,Math.min(100,Number(value)||0))+'%"></i></div>'+
      '</div>'+
    '</article>';
  }

  function compatibilityAttention(entries) {
    const candidates=entries
      .filter(([,value])=>Number(value)<85)
      .sort((a,b)=>Number(a[1])-Number(b[1]))
      .slice(0,2);
    if(!candidates.length){
      return '<div class="compatibility-attention-item"><span>💡</span><div><b>Проверьте живую химию</b><p>По анкете совпадение сильное. Следующий важный шаг — понять, насколько вам легко и интересно общаться вживую.</p></div></div>';
    }
    return candidates.map(([key])=>{
      const meta=compatibilityMeta(key);
      return '<div class="compatibility-attention-item"><span>'+esc(meta.icon)+'</span><div><b>'+esc(meta.label)+'</b><p>'+esc(meta.attention)+'</p></div></div>';
    }).join("");
  }

  function candidateCard(c) {
    const image = c.photos?.[0];
    const name = c.display_name || "Профиль";
    const age = c.age ? ", " + c.age : "";
    const score = c.mutual_fit_score ?? c.compatibility_score ?? 0;
    return '<article class="card candidate-card">' +
      '<div class="candidate-photo">' +
        (image ? '<img src="' + esc(image) + '" alt="' + esc(name) + '">' :
          '<div style="height:100%;display:grid;place-items:center;font-size:76px;color:var(--coral)">♡</div>') +
        '<div class="compat-pill">' + esc(score) + '% совместимость</div>' +
      '</div>' +
      '<div class="candidate-body">' +
        '<div class="candidate-title"><div><h2>' + esc(name + age) + '</h2><div class="muted">' + esc(c.city || "") + '</div><div class="candidate-badges">' + (c.identity_verified?'<span class="verified-profile-badge">✓ Личность подтверждена</span>':'') + (c.is_test_profile?'<span class="test-profile-badge">Тестовый профиль</span>':'') + '</div></div></div>' +
        '<div class="tags">' + compatibilityReason(c) + '</div>' +
        (c.bio ? '<p>' + esc(c.bio) + '</p>' : '') +
        '<div class="actions candidate-actions">' +
          '<button class="primary" data-candidate-like="' + c.user_id + '">Хочу познакомиться</button>' +
          '<button class="secondary candidate-reject" data-candidate-skip="' + c.user_id + '">Пока не подходит</button>' +
        '</div>' +
        '<div class="candidate-utility-row">' +
          '<button class="candidate-detail-link" data-candidate-detail="' + c.user_id + '">Подробнее</button>' +
          '<button class="safety-link" data-candidate-safety="' + c.user_id + '">Безопасность</button>' +
        '</div>' +
      '</div>' +
    '</article>';
  }

  async function renderHome() {
    clearPoller();
    loading("home");
    await loadMe();
    let response = {candidates:[],enabled:false};
    try { response = await api("/api/v1/discovery/candidates?limit=5"); } catch {}
    state.candidates = response.candidates || [];
    const profile = state.profile?.profile;
    const first = state.candidates[0];
    const waitlist = state.onboarding?.waitlist;
    root.innerHTML = '<main class="page">' +
      topbar() +
      '<section class="hero">' +
        '<img src="https://images.unsplash.com/photo-1776266099714-2177bb456209?auto=format&fit=crop&fm=jpg&q=86&w=2400" alt="Счастливая пара">' +
        '<div class="hero-copy"><div class="eyebrow" style="color:#ffd9dd">Больше, чем совпадения</div>' +
        '<h1>Не выбирай из всех.<br>Найди подходящего.</h1>' +
        '<p>Совместимость, общие ценности и серьёзные намерения.</p></div>' +
      '</section>' +
      '<div class="section-head"><div><div class="eyebrow">Для вас</div><h2>' +
        (profile?.display_name ? "Здравствуйте, " + esc(profile.display_name) : "Ваши подборки") +
      '</h2></div></div>' +
      (first
        ? candidateCard(first)
        : '<section class="card empty"><div class="emoji">♡</div><h3>' +
          (response.enabled ? "Ищем подходящих людей" : "Подбор скоро откроется") +
          '</h3><p class="muted">' +
          esc(waitlist?.message || "Мы готовим качественную базу пользователей в Алматы.") +
          '</p>' +
          '<button class="primary" data-route="profile">Проверить профиль</button></section>') +
      (state.candidates.length > 1
        ? '<div class="section-head"><h2>Ещё варианты</h2></div><div class="grid">' +
          state.candidates.slice(1).map(candidateCard).join("") + '</div>' : '') +
    '</main>' + nav("home");
    bindCommon();
    bindCandidates();
  }

  function bindCandidates() {
    document.querySelectorAll("[data-candidate-detail]").forEach(btn => {
      btn.onclick = () => {
        const id = Number(btn.dataset.candidateDetail);
        state.currentCandidate = state.candidates.find(x => Number(x.user_id) === id);
        trackCandidateViewed(id);
        setRoute("candidate");
      };
    });
    document.querySelectorAll("[data-candidate-like]").forEach(btn => {
      btn.onclick = async () => {
        const id = Number(btn.dataset.candidateLike);
        btn.disabled = true; btn.textContent = "Отправляем…";
        try {
          const result = await post("/api/v1/discovery/decision",{
            candidate_user_id:id, action:"INTERESTED"
          });
          if (result.mutual_match) showMutual(result.match_id, id);
          else {
            btn.textContent = "Интерес отправлен ✓";
            btn.className = "secondary";
          }
        } catch(e) {
          btn.disabled = false;
          btn.textContent = "Хочу познакомиться";
          alert("Сейчас действие недоступно: " + friendlyError(e));
        }
      };
    });
    document.querySelectorAll("[data-candidate-skip]").forEach(btn=>{
      btn.onclick=async()=>{
        const id=Number(btn.dataset.candidateSkip);
        btn.disabled=true;
        btn.textContent="Учитываем…";
        try{
          await post("/api/v1/discovery/decision",{candidate_user_id:id,action:"SKIPPED"});
          showCandidateFeedback("Поняли. Учтём ваш выбор при следующих подборках.");
          state.candidates=state.candidates.filter(x=>Number(x.user_id)!==id);
          if(state.currentCandidate&&Number(state.currentCandidate.user_id)===id)state.currentCandidate=null;
          if((location.hash||"").startsWith("#candidate"))setRoute("home");
          else renderHome();
        }catch(e){
          btn.disabled=false;
          btn.textContent="Пока не подходит";
          alert("Не удалось учесть выбор: "+friendlyError(e));
        }
      };
    });
    document.querySelectorAll("[data-candidate-safety]").forEach(btn=>{
      btn.onclick=()=>{
        const id=Number(btn.dataset.candidateSafety);
        const candidate=state.candidates.find(x=>Number(x.user_id)===id)||state.currentCandidate||{};
        showSafetyModal(id,candidate.display_name||"этого пользователя");
      };
    });
  }

  function renderCandidate() {
    clearPoller();
    const c = state.currentCandidate;
    if (!c) return setRoute("home");
    const score = c.mutual_fit_score ?? c.compatibility_score ?? 0;
    const scores = c.category_scores || {};
    const entries = Object.entries(scores).sort((a,b)=>Number(b[1])-Number(a[1]));
    const strongest = entries.slice(0,4);
    const strongestLabels = strongest.slice(0,2).map(([key])=>compatibilityMeta(key).label);
    const summary = strongestLabels.length
      ? "Особенно близки: " + strongestLabels.join(" и ").toLowerCase() + "."
      : "Совместимость рассчитана по вашим ответам, критериям и профилю.";
    root.innerHTML = '<main class="page compatibility-page">' +
      '<header class="topbar"><button class="icon-btn" id="back-home">←</button><div class="brand" style="font-size:25px">Совместимость</div><div></div></header>' +
      candidateCard(c) +
      '<section class="card compatibility-overview-card">' +
        '<div class="eyebrow">Ваше совпадение</div>' +
        '<div class="compatibility-overview-score"><strong>' + esc(score) + '%</strong><div><h1>' + esc(overallCompatibility(score)) + '</h1><p>' + esc(summary) + '</p></div></div>' +
        '<div class="compatibility-overall-track" aria-hidden="true"><i style="width:'+Math.max(0,Math.min(100,Number(score)||0))+'%"></i></div>' +
        '<p class="compatibility-trust-note">Процент — не оценка человека и не гарантия отношений. Это степень совпадения ваших ответов и критериев MatchLab.</p>' +
      '</section>' +
      '<div class="section-head compatibility-section-head"><div><div class="eyebrow">Совпадения</div><h2>Почему вы можете подойти друг другу</h2></div></div>' +
      '<section class="compatibility-reasons">' +
        (strongest.length
          ? strongest.map(([key,value])=>compatibilityReasonCard(key,value)).join("")
          : '<article class="card"><p class="muted">Мы видим общее совпадение по анкете. Детализация по категориям появится после следующего пересчёта профиля.</p></article>') +
      '</section>' +
      '<section class="card compatibility-attention-card">' +
        '<div class="compatibility-attention-title"><span>🌿</span><div><div class="eyebrow">Для хорошего старта</div><h2>На что стоит обратить внимание</h2></div></div>' +
        '<p class="compatibility-attention-intro">Не как на недостатки, а как на темы, которые помогут быстрее понять друг друга.</p>' +
        '<div class="compatibility-attention-list">' + compatibilityAttention(entries) + '</div>' +
      '</section>' +
      '<div class="section-head"><h2>О человеке</h2></div>' +
      '<section class="card"><p>' + esc(c.bio || "Профиль заполнен и прошёл основные критерии MatchLab.") + '</p>' +
      '<div class="tags">' +
        (c.dating_goal ? '<span class="tag">' + esc(c.dating_goal) + '</span>' : '') +
        (c.lifestyle ? '<span class="tag">' + esc(c.lifestyle) + '</span>' : '') +
        (c.height ? '<span class="tag">' + esc(c.height) + ' см</span>' : '') +
      '</div></section>' +
    '</main>' + nav("home");
    bindCommon(); bindCandidates();
    document.getElementById("back-home").onclick = () => setRoute("home");
  }


  function showSafetyModal(userId,name="пользователя"){
    if(!userId)return;
    document.querySelector(".modal-backdrop.safety-modal")?.remove();
    const modal=document.createElement("div");
    modal.className="modal-backdrop safety-modal";
    modal.innerHTML='<div class="modal">'+
      '<div class="eyebrow">Безопасность</div>'+
      '<h2>Действия с '+esc(name)+'</h2>'+
      '<p class="muted">Жалоба отправляется на модерацию. Блокировка сразу убирает человека из подбора и запрещает сообщения.</p>'+
      '<label class="field-label">Причина жалобы<select class="input" id="safety-reason">'+
        '<option value="SPAM">Спам</option><option value="HARASSMENT">Оскорбления / преследование</option>'+
        '<option value="SCAM">Мошенничество</option><option value="FAKE_PROFILE">Фейковый профиль</option>'+
        '<option value="SEXUAL_CONTENT">Нежелательный сексуальный контент</option><option value="VIOLENCE">Угрозы / насилие</option>'+
        '<option value="UNDERAGE">Возможный несовершеннолетний</option><option value="PRIVACY">Нарушение приватности</option>'+
        '<option value="OTHER">Другое</option></select></label>'+
      '<button class="secondary full" id="safety-report">Отправить жалобу</button>'+
      '<button class="danger-btn full" id="safety-block">Заблокировать пользователя</button>'+
      '<button class="ghost full" id="safety-close">Отмена</button>'+
      '<div id="safety-status" class="status" hidden></div>'+
    '</div>';
    document.body.appendChild(modal);
    const msg=(text,error=false)=>{
      const el=document.getElementById("safety-status");
      if(!el)return;
      el.hidden=false;el.className="status"+(error?" error":"");el.textContent=text;
    };
    document.getElementById("safety-close").onclick=()=>modal.remove();
    modal.onclick=e=>{if(e.target===modal)modal.remove()};
    document.getElementById("safety-report").onclick=async()=>{
      const btn=document.getElementById("safety-report");
      btn.disabled=true;
      try{
        await post("/api/v1/safety/report",{user_id:userId,reason:document.getElementById("safety-reason").value});
        msg("Жалоба отправлена модераторам.");
        btn.textContent="Жалоба отправлена ✓";
      }catch(e){btn.disabled=false;msg("Не удалось отправить жалобу: "+friendlyError(e),true)}
    };
    document.getElementById("safety-block").onclick=async()=>{
      if(!confirm("Заблокировать "+name+"? Человек исчезнет из подбора и не сможет писать вам."))return;
      const btn=document.getElementById("safety-block");
      btn.disabled=true;
      try{
        await post("/api/v1/safety/block",{user_id:userId});
        state.candidates=state.candidates.filter(x=>Number(x.user_id)!==Number(userId));
        modal.remove();
        alert("Пользователь заблокирован.");
        if((location.hash||"").startsWith("#chat"))setRoute("chats");
        else setRoute("home");
      }catch(e){btn.disabled=false;msg("Не удалось заблокировать: "+friendlyError(e),true)}
    };
  }

  function showMutual(matchId, candidateId) {
    const c = state.candidates.find(x => Number(x.user_id) === Number(candidateId)) || {};
    const modal = document.createElement("div");
    modal.className = "modal-backdrop";
    modal.innerHTML = '<div class="modal"><div class="hearts">♡ ♥ ♡</div>' +
      '<div class="eyebrow">Взаимный интерес</div><h2>Вы выбрали друг друга!</h2>' +
      '<p class="muted">Теперь можно начать общение' + (c.display_name ? " с " + esc(c.display_name) : "") + '.</p>' +
      '<button class="primary full" id="mutual-chat">Начать общение →</button>' +
      '<button class="ghost full" id="mutual-later">Позже</button></div>';
    document.body.appendChild(modal);
    document.getElementById("mutual-later").onclick = () => { modal.remove(); renderHome(); };
    document.getElementById("mutual-chat").onclick = async () => {
      try {
        const conv = await post("/api/v1/matches/conversation",{match_id:matchId});
        state.currentConversation = {
          conversation_id:conv.conversation_id, match_id:matchId, profile:c,
          compatibility_score:c.compatibility_score, mutual_fit_score:c.mutual_fit_score
        };
        modal.remove(); setRoute("chat");
      } catch(e) { alert(friendlyError(e)); }
    };
  }

  async function renderMatches() {
    clearPoller(); loading("matches");
    try { state.matches = (await api("/api/v1/matches")).matches || []; }
    catch { state.matches=[]; }
    root.innerHTML = '<main class="page">' + topbar("Совпадения") +
      '<div class="section-head"><div><div class="eyebrow">Взаимно</div><h2>Ваши совпадения</h2></div></div>' +
      (state.matches.length
        ? '<div class="grid">' + state.matches.map(m => {
          const p=m.profile||{};
          return '<section class="card match-card">' + photo(p) +
            '<div class="match-main"><h3>' + esc((p.display_name||"Профиль") + (p.age?", "+p.age:"")) + '</h3>' +
            '<div class="muted">' + esc(m.mutual_fit_score ?? m.compatibility_score) + '% совместимость</div></div>' +
            '<button class="primary" data-open-match="' + m.match_id + '">Написать</button></section>';
        }).join("") + '</div>'
        : '<section class="card empty"><div class="emoji">♡</div><h3>Пока нет взаимных интересов</h3><p class="muted">Когда вы выберете друг друга, совпадение появится здесь.</p><button class="primary" data-route="home">Смотреть подборки</button></section>') +
    '</main>' + nav("matches");
    bindCommon();
    document.querySelectorAll("[data-open-match]").forEach(btn => btn.onclick = async () => {
      const matchId=Number(btn.dataset.openMatch);
      const match=state.matches.find(x=>Number(x.match_id)===matchId);
      try{
        const conv=await post("/api/v1/matches/conversation",{match_id:matchId});
        state.currentConversation={conversation_id:conv.conversation_id,match_id:matchId,profile:match?.profile||{},compatibility_score:match?.compatibility_score,mutual_fit_score:match?.mutual_fit_score};
        setRoute("chat");
      }catch(e){alert(friendlyError(e))}
    });
  }

  async function renderChats() {
    clearPoller(); loading("chats");
    try { state.conversations=(await api("/api/v1/chat/conversations")).conversations||[]; }
    catch { state.conversations=[]; }
    root.innerHTML='<main class="page chats-page">'+
      '<header class="chats-hero"><div><div class="eyebrow">MATCHLAB</div><h1>Сообщения</h1><p>Общайся, узнавай друг друга и находи близких по духу людей.</p></div><button class="icon-btn chats-refresh" id="refresh-btn" aria-label="Обновить">↻</button></header>'+
      '<div class="chats-section-title">Ваши чаты</div>'+
      (state.conversations.length
        ? '<div class="chat-list">'+state.conversations.map(conv=>{
          const p=conv.profile||{};
          const last=conv.last_message;
          const time=last?.created_at ? String(last.created_at).slice(11,16) : "";
          return '<button class="chat-list-item" data-open-chat="'+conv.conversation_id+'">'+
            '<div class="chat-list-avatar-wrap">'+photo(p,"chat-list-avatar")+'<span class="chat-online-dot"></span></div>'+
            '<div class="chat-list-copy"><b>'+esc(conv.other_display_name||p.display_name||"Профиль")+'</b><span>'+esc(last?.body||"Начните общение")+'</span></div>'+
            '<div class="chat-list-meta">'+(time?'<time>'+esc(time)+'</time>':'')+(conv.unread_count?'<span class="badge">'+esc(conv.unread_count)+'</span>':'')+'</div>'+
            '<span class="chat-list-arrow">›</span>'+
          '</button>';
        }).join("")+'</div>'
        : '<section class="card empty"><div class="emoji">♡</div><h3>Пока нет диалогов</h3><p class="muted">После взаимного интереса здесь появится ваш чат.</p><button class="primary" data-route="matches">Совпадения</button></section>')+
    '</main>'+nav("chats");
    bindCommon();
    document.querySelectorAll("[data-open-chat]").forEach(btn=>btn.onclick=()=>{
      const id=Number(btn.dataset.openChat);
      state.currentConversation=state.conversations.find(x=>Number(x.conversation_id)===id);
      setRoute("chat");
    });
  }

  function formatBytes(value){
    const bytes=Number(value||0);
    if(!bytes)return "";
    if(bytes<1024)return bytes+" Б";
    if(bytes<1024*1024)return (bytes/1024).toFixed(bytes<10*1024?1:0)+" КБ";
    return (bytes/(1024*1024)).toFixed(bytes<10*1024*1024?1:0)+" МБ";
  }

  function formatDuration(value){
    const total=Math.max(0,Math.round(Number(value||0)));
    const min=Math.floor(total/60);
    const sec=String(total%60).padStart(2,"0");
    return min+":"+sec;
  }

  function chatMediaHtml(media){
    if(!media||!media.url)return "";
    const url=esc(media.url);
    const kind=String(media.kind||"");
    if(kind==="image"){
      return '<a class="chat-media chat-media-image" href="'+url+'" target="_blank" rel="noopener">'+
        '<img src="'+url+'" loading="lazy" alt="Фото в чате"></a>';
    }
    if(kind==="video"){
      return '<div class="chat-media chat-media-video"><video controls playsinline preload="metadata" src="'+url+'"></video>'+
        '<small>'+esc(formatBytes(media.size))+'</small></div>';
    }
    if(kind==="voice"){
      return '<div class="chat-media chat-media-voice">'+
        '<span class="voice-message-icon" aria-hidden="true">🎙</span>'+
        '<audio controls preload="metadata" src="'+url+'"></audio>'+
        '<span class="voice-message-duration">'+esc(formatDuration(media.duration_seconds))+'</span>'+
      '</div>';
    }
    return "";
  }

  function bubbleHtml(m,extraClass=""){
    const time=(m.created_at||"").slice(11,16);
    const media=chatMediaHtml(m.media);
    const text=String(m.body||"").trim();
    return '<div class="bubble '+(m.is_mine?"mine":"theirs")+(m.media?" has-media":"")+(extraClass?" "+extraClass:"")+'" '+(m.client_message_id?'data-client-message="'+esc(m.client_message_id)+'"':'')+'>'+
      media+
      (text?'<div class="bubble-body">'+esc(text)+'</div>':'')+
      '<span class="bubble-time">'+esc(time)+(extraClass.includes("pending")?" · отправляем…":"")+'</span>'+
    '</div>';
  }

  function chatStatus(message="",error=false,recording=false){
    const el=document.getElementById("chat-upload-status");
    if(!el)return;
    el.hidden=!message;
    el.className="chat-upload-status"+(error?" error":"")+(recording?" recording":"");
    el.textContent=message;
  }

  function setComposerBusy(busy){
    state.mediaSending=!!busy;
    const attach=document.getElementById("chat-media-input");
    const mic=document.getElementById("voice-record");
    const send=document.getElementById("send-message");
    if(attach)attach.disabled=!!busy;
    if(mic)mic.disabled=!!busy;
    if(send)send.disabled=!!busy;
  }

  async function renderChat() {
    clearPoller();
    const conv=state.currentConversation;
    if(!conv) return setRoute("chats");
    const p=conv.profile||{};
    root.innerHTML='<main class="page chat-shell">'+
      '<header class="chat-head"><button class="icon-btn" id="chat-back">←</button>'+
        photo(p,"avatar small")+
        '<div class="chat-title"><b>'+esc(p.display_name||conv.other_display_name||"MatchLab")+'</b>'+
        '<span>'+esc(conv.mutual_fit_score??conv.compatibility_score??"")+(conv.mutual_fit_score!=null||conv.compatibility_score!=null?"% совместимость":"")+'</span></div>'+
        '<button class="icon-btn" id="chat-safety">⋯</button></header>'+
      '<div class="chat-context">💜 Взаимный интерес · можно общаться в своём темпе</div>'+
      '<div id="messages" class="messages"><div class="loader"></div></div>'+
    '</main>'+
    '<div class="composer">'+
      '<div id="chat-upload-status" class="chat-upload-status" hidden></div>'+
      '<div class="composer-row">'+
        '<label class="composer-action attach-action" title="Отправить фото или видео" aria-label="Отправить фото или видео">'+
          '<input id="chat-media-input" type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime">'+
          '<span aria-hidden="true">＋</span>'+
        '</label>'+
        '<textarea id="message-input" rows="1" maxlength="4000" placeholder="Напишите сообщение…"></textarea>'+
        '<button class="composer-action mic-action" id="voice-record" type="button" aria-label="Записать голосовое">🎙</button>'+
        '<button class="voice-cancel" id="voice-cancel" type="button" hidden>Отмена</button>'+
        '<button class="send" id="send-message" aria-label="Отправить">➤</button>'+
      '</div>'+
    '</div>'+
    nav("chats");
    bindCommon();
    document.getElementById("chat-back").onclick=()=>setRoute("chats");
    const safetyBtn=document.getElementById("chat-safety");
    if(safetyBtn)safetyBtn.onclick=()=>{
      const userId=Number(p.user_id||conv.other_user_id||0);
      if(userId)showSafetyModal(userId,p.display_name||conv.other_display_name||"этого пользователя");
    };
    const input=document.getElementById("message-input");
    document.getElementById("send-message").onclick=sendCurrentMessage;
    input.addEventListener("keydown",e=>{
      if(e.key==="Enter"&&!e.shiftKey){
        e.preventDefault();
        sendCurrentMessage();
      }
    });
    input.addEventListener("input",()=>{
      input.style.height="auto";
      input.style.height=Math.min(120,input.scrollHeight)+"px";
    });
    const mediaInput=document.getElementById("chat-media-input");
    if(mediaInput)mediaInput.onchange=async e=>{
      const file=e.target.files?.[0];
      e.target.value="";
      if(!file)return;
      const mime=String(file.type||"").split(";",1)[0].toLowerCase();
      const kind=mime.startsWith("image/")?"image":mime.startsWith("video/")?"video":"";
      if(!kind)return chatStatus("Поддерживаются JPG, PNG, WEBP, MP4, WEBM и MOV.",true);
      await sendChatMedia(file,kind);
    };
    const voice=document.getElementById("voice-record");
    if(voice)voice.onclick=toggleVoiceRecording;
    const cancel=document.getElementById("voice-cancel");
    if(cancel)cancel.onclick=()=>stopVoiceRecording(true);
    await loadMessages();
    state.poller=setInterval(()=>loadMessages(false),2500);
  }

  async function loadMessages(forceScroll=true) {
    const conv=state.currentConversation;
    if(!conv) return;
    try{
      const data=await api("/api/v1/chat/messages?conversation_id="+conv.conversation_id+"&limit=100");
      const items=data.messages||[];
      const box=document.getElementById("messages");
      if(!box) return;
      const nearBottom=box.scrollHeight-box.scrollTop-box.clientHeight<90;
      const pending=[...box.querySelectorAll(".bubble.pending")].map(el=>el.outerHTML);
      box.innerHTML=(items.length ? items.map(m=>bubbleHtml(m)).join("") : '')+
        pending.join("")+
        (!items.length&&!pending.length?'<div class="empty chat-empty"><div class="emoji">♡</div><h3>Начните разговор</h3><p class="muted">Можно начать с того, что вам действительно понравилось в анкете человека.</p></div>':'');
      if(items.length){
        const last=items[items.length-1];
        post("/api/v1/chat/read",{conversation_id:conv.conversation_id,through_message_id:last.id}).catch(()=>{});
      }
      if(forceScroll||nearBottom)box.scrollTop=box.scrollHeight;
    }catch(e){}
  }

  function preferredVoiceMime(){
    if(typeof MediaRecorder==="undefined")return "";
    const choices=[
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/ogg;codecs=opus",
      "audio/ogg"
    ];
    if(typeof MediaRecorder.isTypeSupported!=="function")return "";
    return choices.find(type=>MediaRecorder.isTypeSupported(type))||"";
  }

  function updateVoiceUi(){
    const session=state.voiceRecorder;
    const mic=document.getElementById("voice-record");
    const cancel=document.getElementById("voice-cancel");
    const input=document.getElementById("message-input");
    const attach=document.getElementById("chat-media-input");
    const send=document.getElementById("send-message");
    const composer=document.querySelector(".composer");
    if(!session){
      if(mic){mic.textContent="🎙";mic.setAttribute("aria-label","Записать голосовое")}
      if(cancel)cancel.hidden=true;
      if(input)input.disabled=false;
      if(attach)attach.disabled=state.mediaSending;
      if(send)send.disabled=state.mediaSending;
      composer?.classList.remove("recording");
      return;
    }
    const elapsed=(Date.now()-session.startedAt)/1000;
    if(mic){mic.textContent="■";mic.setAttribute("aria-label","Остановить и отправить голосовое")}
    if(cancel)cancel.hidden=false;
    if(input)input.disabled=true;
    if(attach)attach.disabled=true;
    if(send)send.disabled=true;
    composer?.classList.add("recording");
    chatStatus("● Запись "+formatDuration(elapsed)+" · нажмите ■, чтобы отправить",false,true);
  }

  async function toggleVoiceRecording(){
    if(state.mediaSending)return;
    if(state.voiceRecorder){
      stopVoiceRecording(false);
      return;
    }
    if(!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==="undefined"){
      chatStatus("Запись голосовых не поддерживается этим браузером.",true);
      return;
    }
    try{
      const stream=await navigator.mediaDevices.getUserMedia({
        audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}
      });
      const preferred=preferredVoiceMime();
      const recorder=preferred?new MediaRecorder(stream,{mimeType:preferred}):new MediaRecorder(stream);
      const session={
        recorder,
        stream,
        chunks:[],
        startedAt:Date.now(),
        cancelled:false
      };
      state.voiceRecorder=session;
      recorder.ondataavailable=e=>{if(e.data&&e.data.size)session.chunks.push(e.data)};
      recorder.onerror=()=>{
        session.cancelled=true;
        chatStatus("Не удалось записать голосовое.",true);
      };
      recorder.onstop=async()=>{
        try{session.stream.getTracks().forEach(track=>track.stop())}catch{}
        if(state.voiceTimer)clearInterval(state.voiceTimer);
        state.voiceTimer=null;
        if(state.voiceRecorder===session)state.voiceRecorder=null;
        updateVoiceUi();
        if(session.cancelled)return chatStatus("");
        const duration=Math.max(.1,(Date.now()-session.startedAt)/1000);
        if(!session.chunks.length)return chatStatus("Голосовое получилось пустым. Попробуйте ещё раз.",true);
        let mime=String(recorder.mimeType||session.chunks[0]?.type||"audio/webm").split(";",1)[0].toLowerCase();
        if(!["audio/webm","audio/ogg","audio/mp4","audio/mpeg"].includes(mime)){
          mime="audio/webm";
        }
        const blob=new Blob(session.chunks,{type:mime});
        const ext=mime==="audio/mp4"?".m4a":mime==="audio/ogg"?".ogg":mime==="audio/mpeg"?".mp3":".webm";
        const file=new File([blob],"voice-"+Date.now()+ext,{type:mime});
        await sendChatMedia(file,"voice",duration);
      };
      recorder.start(250);
      updateVoiceUi();
      state.voiceTimer=setInterval(()=>{
        if(!state.voiceRecorder||state.voiceRecorder!==session)return;
        const elapsed=(Date.now()-session.startedAt)/1000;
        if(elapsed>=300){
          stopVoiceRecording(false);
          return;
        }
        updateVoiceUi();
      },500);
    }catch(err){
      chatStatus(err?.name==="NotAllowedError"
        ?"Разрешите доступ к микрофону, чтобы отправлять голосовые."
        :"Не удалось включить микрофон.",true);
    }
  }

  function stopVoiceRecording(cancelled=false){
    const session=state.voiceRecorder;
    if(!session)return;
    session.cancelled=!!cancelled;
    if(state.voiceTimer)clearInterval(state.voiceTimer);
    state.voiceTimer=null;
    try{
      if(session.recorder.state!=="inactive")session.recorder.stop();
    }catch{
      try{session.stream.getTracks().forEach(track=>track.stop())}catch{}
      state.voiceRecorder=null;
      updateVoiceUi();
      if(cancelled)chatStatus("");
    }
  }

  async function sendChatMedia(file,kind,durationSeconds=null){
    const conv=state.currentConversation;
    if(!conv||!file||state.mediaSending)return;
    const mime=String(file.type||"").split(";",1)[0].toLowerCase();
    const imageLimit=12*1024*1024;
    const voiceLimit=25*1024*1024;
    const videoLimit=60*1024*1024;
    const limit=kind==="image"?imageLimit:kind==="voice"?voiceLimit:videoLimit;
    if(!mime||file.size<=0)return chatStatus("Не удалось прочитать файл.",true);
    if(file.size>limit){
      const label=kind==="image"?"12 МБ":kind==="voice"?"25 МБ":"60 МБ";
      return chatStatus("Файл слишком большой. Максимум "+label+".",true);
    }
    const input=document.getElementById("message-input");
    const caption=String(input?.value||"").trim();
    if(caption.length>1000)return chatStatus("Подпись к фото или видео — максимум 1000 символов.",true);
    if(input){input.value="";input.style.height="auto"}
    setComposerBusy(true);
    chatStatus(kind==="voice"?"Отправляем голосовое…":kind==="video"?"Загружаем видео…":"Загружаем фото…");
    const clientId=(crypto.randomUUID?crypto.randomUUID():Date.now()+"-"+Math.random());
    try{
      const prep=await post("/api/v1/chat/media/prepare",{
        conversation_id:conv.conversation_id,
        mime,
        kind,
        size:file.size,
        name:file.name||""
      });
      const headers=prep.upload?.headers||{"Content-Type":prep.mime||mime};
      const uploaded=await fetch(prep.upload.url,{method:"PUT",headers,body:file});
      if(!uploaded.ok)throw new Error("upload_failed");
      await post("/api/v1/chat/messages",{
        conversation_id:conv.conversation_id,
        body:caption,
        client_message_id:clientId,
        media:{
          object_key:prep.object_key,
          kind:prep.kind||kind,
          mime:prep.mime||mime,
          name:prep.name||file.name||"",
          size:file.size,
          duration_seconds:durationSeconds
        }
      });
      chatStatus("");
      await loadMessages(true);
    }catch(err){
      if(input&&caption&&!input.value)input.value=caption;
      chatStatus("Не удалось отправить вложение. Попробуйте ещё раз.",true);
    }finally{
      setComposerBusy(false);
      updateVoiceUi();
    }
  }

  async function sendCurrentMessage(){
    const input=document.getElementById("message-input");
    const send=document.getElementById("send-message");
    const text=input?.value.trim();
    if(!text||!state.currentConversation||!input||!send) return;
    const clientId=(crypto.randomUUID?crypto.randomUUID():Date.now()+"-"+Math.random());
    const box=document.getElementById("messages");
    input.value="";
    input.style.height="auto";
    const empty=box?.querySelector(".chat-empty");
    if(empty)empty.remove();
    if(box){
      box.insertAdjacentHTML("beforeend",bubbleHtml({
        body:text,is_mine:true,created_at:new Date().toISOString(),client_message_id:clientId
      },"pending"));
      box.scrollTop=box.scrollHeight;
    }
    send.disabled=true;
    try{
      const response=await post("/api/v1/chat/messages",{
        conversation_id:state.currentConversation.conversation_id,
        body:text,
        client_message_id:clientId
      });
      const optimistic=box?.querySelector('[data-client-message="'+CSS.escape(clientId)+'"]');
      if(optimistic){
        optimistic.classList.remove("pending");
        const t=optimistic.querySelector(".bubble-time");
        if(t)t.textContent=((responsfriendlyError(e)?.created_at||"").slice(11,16)||"сейчас");
        optimistic.removeAttribute("data-client-message");
      }
    }catch(e){
      const optimistic=box?.querySelector('[data-client-message="'+CSS.escape(clientId)+'"]');
      if(optimistic){
        optimistic.classList.remove("pending");
        optimistic.classList.add("failed");
        const t=optimistic.querySelector(".bubble-time");
        if(t)t.textContent="Не отправлено";
      }
      input.value=text;
      input.focus();
    }finally{
      send.disabled=false;
    }
  }


  const ONBOARDING_STEPS = [
    ["basic","О вас"],
    ["relationship","Статус"],
    ["readiness","Готовность"],
    ["details","Образ жизни"],
    ["questionnaire","Анкета"],
    ["partner_preferences","Кого ищете"],
    ["photos","Фото"],
  ];

  const pick = (id) => document.getElementById(id);
  const selectHtml = (id, value, options, config={}) => {
    const current=String(value??"");
    const required=config.required!==false;
    const placeholder=config.placeholder||"Выберите вариант";
    return '<select class="input" id="'+id+'" '+(required?'required':'')+'>'+
      '<option value="" '+(!current?'selected':'')+' disabled>'+esc(placeholder)+'</option>'+
      options.map(([v,l]) =>
        '<option value="'+esc(v)+'" '+(current===String(v)?"selected":"")+'>'+esc(l)+'</option>'
      ).join("")+
    '</select>';
  };

  const importanceHtml = (id, value="") => selectHtml(id,value,[
    ["HARD","Обязательно"],
    ["IMPORTANT","Важно"],
    ["PREFERENCE","Желательно"],
    ["IGNORE","Не важно"],
  ],{placeholder:"Насколько это важно?"});

  const MARKET_OPTIONS = [
    ["KZ-ALA","Алматы"],
    ["KZ-AST","Астана"],
    ["KZ-SHY","Шымкент"],
    ["KZ-KAR","Караганда"],
    ["KZ-OTHER","Другой город"],
  ];

  function requireFields(ids,message="Заполните все обязательные поля"){
    const missing=ids.some(id=>{
      const el=pick(id);
      return !el||String(el.value||"").trim()==="";
    });
    if(missing){onboardingStatus(message,true);return false}
    return true;
  }

  function preferenceCard({key,title,valueHtml,importance="",hint=""}){
    return '<div class="preference-card" data-pref-card="'+key+'">'+
      '<div class="preference-card-head"><div><b>'+esc(title)+'</b>'+(hint?'<span>'+esc(hint)+'</span>':'')+'</div></div>'+
      '<div class="preference-value">'+valueHtml+'</div>'+
      '<label class="field-label preference-importance">Насколько это важно?'+importanceHtml("importance-"+key,importance)+'</label>'+
    '</div>';
  }

  function importanceConfig(key,value){
    const importance=pick("importance-"+key)?.value||"";
    if(!importance)throw new Error("Укажите важность критерия «"+key+"»");
    if(importance==="IGNORE")return {importance:"IGNORE"};
    return {importance,value};
  }

  function firstIncompleteStep() {
    const c=state.onboarding?.completion||{};
    const item=ONBOARDING_STEPS.find(([key])=>!c[key]);
    return item ? item[0] : null;
  }

  function verificationBanner(){
    const v=state.onboarding?.verification||state.profile?.verification||{};
    if(v.contact_verified)return "";
    if(!v.email)return '<div class="verification-banner"><div><b>Подтвердите контакт</b><span>Для активного подбора нужен подтверждённый email или телефон.</span></div></div>';
    return '<div class="verification-banner"><div><b>Подтвердите email</b><span>Анкету можно продолжать. Подбор включится после подтверждения email или телефона.</span></div>'+
      '<button class="secondary" id="verify-email-resend">'+(v.email_delivery_available?"Отправить письмо":"Email пока не настроен")+'</button></div>';
  }

  function bindVerificationBanner(){
    const btn=pick("verify-email-resend");
    if(!btn)return;
    const v=state.onboarding?.verification||state.profile?.verification||{};
    if(!v.email_delivery_available){btn.disabled=true;return}
    btn.onclick=async()=>{
      btn.disabled=true;btn.textContent="Отправляем…";
      try{
        await post("/api/v1/auth/email/verification/request");
        btn.textContent="Письмо отправлено ✓";
      }catch(e){
        btn.disabled=false;btn.textContent="Отправить ещё раз";
        onboardingStatus("Не удалось отправить письмо: "+friendlyError(e),true);
      }
    };
  }

  function onboardingChrome(step, body) {
    const idx=Math.max(0,ONBOARDING_STEPS.findIndex(([key])=>key===step));
    const pct=Math.round((idx/ONBOARDING_STEPS.length)*100);
    return '<main class="onboarding-page">'+
      '<header class="onboarding-head"><div class="brand">Match<span>Lab</span></div>'+
      '<button class="ghost" id="onboarding-exit">Позже</button></header>'+
      '<section class="onboarding-shell">'+
        verificationBanner()+
        '<div class="onboarding-progress"><div class="progress-copy"><span>Шаг '+(idx+1)+' из '+ONBOARDING_STEPS.length+'</span><b>'+esc(ONBOARDING_STEPS[idx]?.[1]||"Анкета")+'</b></div>'+
        '<div class="progress-track"><i style="width:'+pct+'%"></i></div></div>'+
        body+
        '<div id="onboarding-status" class="status" hidden></div>'+
      '</section>'+
    '</main>';
  }

  function onboardingStatus(message,error=false){
    const el=pick("onboarding-status");
    if(!el)return;
    el.className="status"+(error?" error":"");
    el.textContent=message;
    el.hidden=false;
  }

  async function renderOnboarding(force=false) {
    clearPoller();
    if(force||!state.onboarding) await loadMe();
    const step=firstIncompleteStep();
    const p=state.onboarding?.profile||state.profile?.profile||{};

    if(!step) return renderWaitlistCompletion();
    if(step==="questionnaire") return renderQuestionnaireStep();

    let preferenceData={values:{}};
    if(step==="partner_preferences"){
      try{preferenceData=await api("/api/v1/preferences")}catch{}
    }
    const prefValues=preferenceData.values||{};
    const pref=(key)=>prefValues[key]||{};
    const prefValue=(key,fallback="")=>pref(key).value??fallback;
    const prefImportance=(key)=>pref(key).importance||"";
    const prefFirst=(key)=>{
      const value=prefValue(key,[]);
      return Array.isArray(value)&&value.length?value[0]:"";
    };

    let body="";
    if(step==="basic"){
      const currentMarket=p.market_code||"";
      body='<div class="onboarding-card"><div class="eyebrow">Начнём с главного</div><h1>Расскажите немного о себе</h1><p class="muted">Никаких ответов по умолчанию — сохраняем только то, что выбрали вы.</p>'+
        '<div class="form-stack">'+
        '<label class="field-label">Имя<input class="input" id="ob-name" value="'+esc(p.display_name||"")+'" placeholder="Как к вам обращаться"></label>'+
        '<label class="field-label">Дата рождения<input class="input" id="ob-dob" type="date" value="'+esc(p.dob||"")+'"></label>'+
        '<div class="form-grid">'+
          '<label class="field-label">Ваш пол'+selectHtml("ob-gender",p.gender,[["M","Мужчина"],["F","Женщина"],["OTHER","Другое"]])+'</label>'+
          '<label class="field-label">Кого ищете'+selectHtml("ob-seek",p.seek_gender,[["F","Женщину"],["M","Мужчину"],["ANY","Не важно"],["OTHER","Другое"]])+'</label>'+
        '</div>'+
        '<label class="field-label">В каком городе вы сейчас живёте?'+selectHtml("ob-market",currentMarket,MARKET_OPTIONS,{placeholder:"Выберите город"})+'</label>'+
        '<label class="field-label" id="ob-other-city-wrap" '+(currentMarket==="KZ-OTHER"?"":"hidden")+'>Ваш город<input class="input" id="ob-other-city" maxlength="120" value="'+esc(currentMarket==="KZ-OTHER"?(p.city||""):"")+'" placeholder="Например, Павлодар"></label>'+
        '<button class="primary full" id="ob-save-basic">Продолжить →</button></div></div>';
    } else if(step==="relationship"){
      body='<div class="onboarding-card"><div class="eyebrow">Статус</div><h1>Вы сейчас в отношениях?</h1><p class="muted">Выберите ответ сами — статус не назначается автоматически.</p>'+
        '<div class="choice-grid" id="relationship-choice">'+
          '<button class="choice-card" data-rel="no"><b>Нет</b><span>Я свободен(на)</span></button>'+
          '<button class="choice-card" data-rel="yes"><b>Да</b><span>Сейчас я в отношениях</span></button>'+
        '</div>'+
        '<div id="openness-block" class="form-stack" hidden><div class="field-label">Насколько вы открыты к знакомствам?</div>'+
          selectHtml("ob-openness","",[["ACTIVE","Активно хочу знакомиться"],["OPEN","Открыт(а), если встречу подходящего человека"],["UNSURE","Пока не уверен(а)"],["NO","Не хочу знакомств"]])+
          '<button class="primary full" id="ob-save-relationship">Продолжить →</button></div></div>';
    } else if(step==="readiness"){
      body='<div class="onboarding-card"><div class="eyebrow">Готовность</div><h1>Как вам комфортнее начинать знакомство?</h1><p class="muted">Оба ответа нужно выбрать явно.</p>'+
        '<div class="form-stack">'+
        '<label class="field-label">Готовность общаться в чате'+selectHtml("ob-chat",p.readiness_chat,[["YES","Да, готов(а)"],["RATHER_YES","Скорее да"],["LOOK_ONLY","Пока хочу присмотреться"]])+'</label>'+
        '<label class="field-label">Готовность встретиться офлайн'+selectHtml("ob-offline",p.readiness_offline,[["YES","Да"],["MAYBE","Возможно, после общения"],["NO","Пока нет"]])+'</label>'+
        '<button class="primary full" id="ob-save-readiness">Продолжить →</button></div></div>';
    } else if(step==="details"){
      body='<div class="onboarding-card wide"><div class="eyebrow">О вас</div><h1>Что важно знать для совместимости?</h1><p class="muted">Обязательные пункты не имеют скрытого первого ответа.</p>'+
        '<div class="form-grid">'+
          '<label class="field-label">Рост, см<input class="input" id="ob-height" type="number" min="100" max="250" value="'+esc(p.height||"")+'"></label>'+
          '<label class="field-label">Цель знакомства'+selectHtml("ob-goal",p.dating_goal,[["SERIOUS","Серьёзные отношения"],["FAMILY","Семья"],["SEE","Посмотрим, как сложится"],["CHAT","Общение"],["UNKNOWN","Пока не знаю"]])+'</label>'+
          '<label class="field-label">Дети'+selectHtml("ob-children",p.children_status,[["NO_CHILDREN","Нет детей"],["HAS_CHILDREN","Есть дети"]])+'</label>'+
          '<label class="field-label">Планы на детей'+selectHtml("ob-children-plans",p.children_plans,[["WANTS","Хочу"],["MAYBE","Возможно"],["DOES_NOT_WANT","Не хочу"]])+'</label>'+
          '<label class="field-label">Курение'+selectHtml("ob-smoking",p.smoking,[["NO","Не курю"],["RARE","Иногда"],["YES","Курю"]])+'</label>'+
          '<label class="field-label">Алкоголь'+selectHtml("ob-alcohol",p.alcohol,[["NO","Не употребляю"],["RARE","Редко"],["MODERATE","Умеренно"],["YES","Регулярно"]])+'</label>'+
          '<label class="field-label">Образ жизни'+selectHtml("ob-lifestyle",p.lifestyle,[["CALM","Спокойный"],["BALANCED","Сбалансированный"],["ACTIVE","Активный"],["VERY_ACTIVE","Очень активный"]])+'</label>'+
          '<label class="field-label">Религия — необязательно<input class="input" id="ob-religion" value="'+esc(p.religion||"")+'" placeholder="Можно не указывать"></label>'+
        '</div>'+
        '<label class="field-label">Коротко о себе<textarea class="input textarea" id="ob-bio" maxlength="2000" placeholder="Чем вы живёте, что любите, какой человек вам близок">'+esc(p.bio||"")+'</textarea></label>'+
        '<button class="primary full" id="ob-save-details">Перейти к анкете →</button></div>';
    } else if(step==="partner_preferences"){
      const age=prefValue("age",{});
      const height=prefValue("height",{});
      const distance=prefValue("distance_km",{});
      const marketValue=prefFirst("market");
      body='<div class="onboarding-card wide preferences-onboarding"><div class="eyebrow">Ваш человек</div><h1>Кого вы хотите встретить?</h1>'+
        '<p class="muted">Для каждого критерия сначала выберите значение, а затем насколько оно важно. «Не важно» полностью исключает критерий из расчёта.</p>'+
        '<div class="preference-grid">'+
          preferenceCard({key:"age",title:"Возраст партнёра",importance:prefImportance("age"),valueHtml:
            '<div class="range-pair"><input class="input" id="pref-age-min" type="number" min="18" max="100" value="'+esc(age.min??"")+'" placeholder="От"><input class="input" id="pref-age-max" type="number" min="18" max="100" value="'+esc(age.max??"")+'" placeholder="До"></div>'})+
          preferenceCard({key:"gender",title:"Кого вы ищете",importance:prefImportance("gender"),valueHtml:
            selectHtml("pref-gender",prefFirst("gender")||p.seek_gender,[["F","Женщину"],["M","Мужчину"],["OTHER","Другой пол"]],{placeholder:"Выберите"})})+
          preferenceCard({key:"market",title:"Город партнёра",importance:prefImportance("market"),valueHtml:
            selectHtml("pref-market",marketValue,MARKET_OPTIONS.slice(0,4),{placeholder:"Выберите город"})})+
          preferenceCard({key:"distance_km",title:"Максимальное расстояние",hint:"Используется как примерное ограничение между городами",importance:prefImportance("distance_km"),valueHtml:
            '<input class="input" id="pref-distance" type="number" min="1" max="1000" value="'+esc(distance.max??"")+'" placeholder="Например, 100 км">'})+
          preferenceCard({key:"dating_goal",title:"Цель знакомства",importance:prefImportance("dating_goal"),valueHtml:
            selectHtml("pref-goal",prefFirst("dating_goal"),[["SERIOUS","Серьёзные отношения"],["FAMILY","Семья"],["SEE","Посмотрим"],["CHAT","Общение"],["UNKNOWN","Пока не знаю"]])})+
          preferenceCard({key:"children_status",title:"Наличие детей",importance:prefImportance("children_status"),valueHtml:
            selectHtml("pref-children",prefFirst("children_status"),[["NO_CHILDREN","Без детей"],["HAS_CHILDREN","Есть дети"]])})+
          preferenceCard({key:"children_plans",title:"Планы на детей",importance:prefImportance("children_plans"),valueHtml:
            selectHtml("pref-plans",prefFirst("children_plans"),[["WANTS","Хочет"],["MAYBE","Возможно"],["DOES_NOT_WANT","Не хочет"]])})+
          preferenceCard({key:"smoking",title:"Курение",importance:prefImportance("smoking"),valueHtml:
            selectHtml("pref-smoking",prefFirst("smoking"),[["NO","Не курит"],["RARE","Иногда"],["YES","Курит"]])})+
          preferenceCard({key:"alcohol",title:"Алкоголь",importance:prefImportance("alcohol"),valueHtml:
            selectHtml("pref-alcohol",prefFirst("alcohol"),[["NO","Не употребляет"],["RARE","Редко"],["MODERATE","Умеренно"],["YES","Регулярно"]])})+
          preferenceCard({key:"lifestyle",title:"Образ жизни",importance:prefImportance("lifestyle"),valueHtml:
            selectHtml("pref-lifestyle",prefFirst("lifestyle"),[["CALM","Спокойный"],["BALANCED","Сбалансированный"],["ACTIVE","Активный"],["VERY_ACTIVE","Очень активный"]])})+
          preferenceCard({key:"height",title:"Рост партнёра",importance:prefImportance("height"),valueHtml:
            '<div class="range-pair"><input class="input" id="pref-height-min" type="number" min="100" max="250" value="'+esc(height.min??"")+'" placeholder="От"><input class="input" id="pref-height-max" type="number" min="100" max="250" value="'+esc(height.max??"")+'" placeholder="До"></div>'})+
        '</div>'+
        '<button class="primary full" id="ob-save-preferences">Сохранить критерии →</button></div>';
    } else {
      const photos=state.onboarding?.photos||{};
      const photoMinimum=Number(photos.minimum||1);
      body='<div class="onboarding-card"><div class="eyebrow">Последний шаг</div><h1>Добавьте фотографию</h1><p class="muted">Для готовности профиля достаточно 1 одобренного фото. Потом можно добавить ещё — рекомендуем 3–5.</p>'+
        '<div class="photo-progress-big"><b>'+esc(photos.approved||0)+'/'+esc(photoMinimum)+'</b><span>минимум одобрено</span></div>'+
        '<label class="photo-upload"><input type="file" id="ob-photo" accept="image/jpeg,image/png,image/webp"><span>＋ Добавить фото</span></label>'+
        '<p class="muted small">После загрузки фото отправляется на модерацию. Пока оно проверяется, можно пользоваться приложением.</p>'+
        '<button class="secondary full" id="ob-finish-later">Перейти в приложение</button></div>';
    }

    root.innerHTML=onboardingChrome(step,body);
    bindVerificationBanner();
    pick("onboarding-exit").onclick=()=>setRoute("home");

    if(step==="basic"){
      const market=pick("ob-market");
      const otherWrap=pick("ob-other-city-wrap");
      market.onchange=()=>{otherWrap.hidden=market.value!=="KZ-OTHER"};
      pick("ob-save-basic").onclick=async()=>{
        if(!requireFields(["ob-name","ob-dob","ob-gender","ob-seek","ob-market"]))return;
        if(market.value==="KZ-OTHER"&&!String(pick("ob-other-city").value||"").trim()){
          return onboardingStatus("Укажите ваш город",true);
        }
        try{
          onboardingStatus("Сохраняем…");
          await post("/api/v1/profile/basic",{
            display_name:pick("ob-name").value.trim(),
            dob:pick("ob-dob").value,
            gender:pick("ob-gender").value,
            seek_gender:pick("ob-seek").value,
            market_code:market.value,
            city:market.value==="KZ-OTHER"?pick("ob-other-city").value.trim():"",
            preferred_locale:"ru-KZ"
          });
          await loadMe(); renderOnboarding();
        }catch(e){onboardingStatus("Проверьте данные: "+friendlyError(e),true)}
      };
    } else if(step==="relationship"){
      let relationshipAnswer=null;
      document.querySelectorAll("[data-rel]").forEach(btn=>btn.onclick=()=>{
        relationshipAnswer=btn.dataset.rel;
        document.querySelectorAll("[data-rel]").forEach(x=>x.classList.toggle("selected",x===btn));
        pick("openness-block").hidden=false;
        pick("ob-openness").value="";
      });
      pick("ob-save-relationship").onclick=async()=>{
        if(relationshipAnswer===null)return onboardingStatus("Выберите, состоите ли вы сейчас в отношениях",true);
        if(!requireFields(["ob-openness"]))return;
        try{
          await post("/api/v1/profile/relationship",{in_relationship:relationshipAnswer==="yes",openness:pick("ob-openness").value});
          await loadMe(); renderOnboarding();
        }catch(e){onboardingStatus(friendlyError(e),true)}
      };
    } else if(step==="readiness"){
      pick("ob-save-readiness").onclick=async()=>{
        if(!requireFields(["ob-chat","ob-offline"]))return;
        try{
          await post("/api/v1/profile/readiness",{chat:pick("ob-chat").value,offline:pick("ob-offline").value});
          await loadMe(); renderOnboarding();
        }catch(e){onboardingStatus(friendlyError(e),true)}
      };
    } else if(step==="details"){
      pick("ob-save-details").onclick=async()=>{
        if(!requireFields(["ob-height","ob-goal","ob-children","ob-children-plans","ob-smoking","ob-alcohol","ob-lifestyle"]))return;
        try{
          await post("/api/v1/profile/details",{height:Number(pick("ob-height").value),dating_goal:pick("ob-goal").value,children_status:pick("ob-children").value,children_plans:pick("ob-children-plans").value,smoking:pick("ob-smoking").value,alcohol:pick("ob-alcohol").value,lifestyle:pick("ob-lifestyle").value,bio:pick("ob-bio").value.trim(),religion:pick("ob-religion").value.trim(),nationality:""});
          await loadMe(); renderOnboarding();
        }catch(e){onboardingStatus("Не удалось сохранить: "+friendlyError(e),true)}
      };
    } else if(step==="partner_preferences"){
      const valueOrIgnore=(key,id,wrap=v=>v)=>{
        const importance=pick("importance-"+key).value;
        if(!importance)throw new Error("Выберите важность: "+key);
        if(importance==="IGNORE")return {importance:"IGNORE"};
        const raw=pick(id)?.value;
        if(raw==null||String(raw).trim()==="")throw new Error("Выберите значение: "+key);
        return {importance,value:wrap(raw)};
      };
      pick("ob-save-preferences").onclick=async()=>{
        try{
          const ageImportance=pick("importance-age").value;
          if(!ageImportance)throw new Error("Выберите важность возраста");
          let ageConfig={importance:"IGNORE"};
          if(ageImportance!=="IGNORE"){
            const min=Number(pick("pref-age-min").value),max=Number(pick("pref-age-max").value);
            if(!min||!max||min<18||max<min||max>100)throw new Error("Проверьте возрастной диапазон");
            ageConfig={importance:ageImportance,value:{min,max}};
          }
          const heightImportance=pick("importance-height").value;
          if(!heightImportance)throw new Error("Выберите важность роста");
          let heightConfig={importance:"IGNORE"};
          if(heightImportance!=="IGNORE"){
            const min=Number(pick("pref-height-min").value),max=Number(pick("pref-height-max").value);
            if(!min||!max||min<100||max<min||max>250)throw new Error("Проверьте диапазон роста");
            heightConfig={importance:heightImportance,value:{min,max}};
          }
          const distanceImportance=pick("importance-distance_km").value;
          if(!distanceImportance)throw new Error("Выберите важность расстояния");
          let distanceConfig={importance:"IGNORE"};
          if(distanceImportance!=="IGNORE"){
            const max=Number(pick("pref-distance").value);
            if(!max||max<1||max>1000)throw new Error("Проверьте максимальное расстояние");
            distanceConfig={importance:distanceImportance,value:{max}};
          }
          const prefs={
            age:ageConfig,
            gender:valueOrIgnore("gender","pref-gender",v=>[v]),
            market:valueOrIgnore("market","pref-market",v=>[v]),
            distance_km:distanceConfig,
            dating_goal:valueOrIgnore("dating_goal","pref-goal",v=>[v]),
            children_status:valueOrIgnore("children_status","pref-children",v=>[v]),
            children_plans:valueOrIgnore("children_plans","pref-plans",v=>[v]),
            smoking:valueOrIgnore("smoking","pref-smoking",v=>[v]),
            alcohol:valueOrIgnore("alcohol","pref-alcohol",v=>[v]),
            lifestyle:valueOrIgnore("lifestyle","pref-lifestyle",v=>[v]),
            height:heightConfig
          };
          onboardingStatus("Сохраняем критерии…");
          await post("/api/v1/preferences",{preferences:prefs});
          await loadMe(); renderOnboarding();
        }catch(e){onboardingStatus(friendlyError(e)||"Проверьте критерии",true)}
      };
    } else {
      pick("ob-finish-later").onclick=()=>setRoute("home");
      pick("ob-photo").onchange=async(e)=>{
        const file=e.target.files?.[0]; if(!file)return;
        if(file.size>12*1024*1024)return onboardingStatus("Фото слишком большое. Максимум 12 МБ.",true);
        try{
          onboardingStatus("Загружаем фото…");
          const prep=await post("/api/v1/photos/prepare",{mime:file.type});
          const headers=prep.upload?.headers||{"Content-Type":file.type};
          const up=await fetch(prep.upload.url,{method:"PUT",headers,body:file});
          if(!up.ok) throw new Error("upload_failed");
          await post("/api/v1/photos/finalize",{ticket:prep.ticket});
          await loadMe(); renderOnboarding();
        }catch(err){onboardingStatus("Не удалось загрузить фото: "+err.message,true)}
      };
    }
  }


  async function renderWaitlistCompletion(){
    clearPoller();
    if(!state.onboarding) await loadMe();
    const p=state.onboarding?.profile||state.profile?.profile||{};
    let waitlist=state.onboarding?.waitlist||{};
    try{waitlist=await api("/api/v1/waitlist/status");}catch{}
    const ready=!!waitlist.ready;
    const stateLabel=
      waitlist.state==="WAITLIST"?"Вы в листе ожидания":
      waitlist.state==="MATCHING_ACTIVE"?"Подбор уже открыт":
      waitlist.state==="CONTACT_VERIFICATION_REQUIRED"?"Нужно подтвердить контакт":
      "Профиль готов";
    root.innerHTML='<main class="onboarding-page waitlist-page">'+
      '<header class="onboarding-head"><div class="brand">Match<span>Lab</span></div><button class="ghost" id="waitlist-profile">Профиль</button></header>'+
      '<section class="onboarding-shell">'+verificationBanner()+'<div class="onboarding-card waitlist-card">'+
        '<div class="waitlist-mark">'+(ready?"✓":"♡")+'</div>'+
        '<div class="eyebrow">Анкета завершена</div>'+
        '<h1>'+esc(stateLabel)+(p.display_name?" — "+esc(p.display_name):"")+'</h1>'+
        '<p class="muted">'+esc(waitlist.message||"Ваш профиль сохранён. Мы сообщим, когда подбор станет доступен.")+'</p>'+
        '<div class="waitlist-summary">'+
          '<div><b>100%</b><span>анкета заполнена</span></div>'+
          '<div><b>'+esc(p.city||"Город не указан")+'</b><span>ваш город</span></div>'+
          '<div><b>'+esc(ready?"Готов":"Проверяем")+'</b><span>статус профиля</span></div>'+
        '</div>'+
        '<button class="primary full" id="waitlist-home">Перейти в приложение →</button>'+
        '<button class="secondary full" id="waitlist-edit">Изменить профиль</button>'+
      '</div></section></main>';
    bindVerificationBanner();
    document.getElementById("waitlist-home").onclick=()=>setRoute("home");
    document.getElementById("waitlist-edit").onclick=()=>setRoute("profile");
    document.getElementById("waitlist-profile").onclick=()=>setRoute("profile");
  }

  async function renderQuestionnaireStep(){
    let q;
    try{q=await api("/api/v1/questionnaire/adaptive");}
    catch(e){return root.innerHTML=onboardingChrome("questionnaire",'<div class="onboarding-card"><h1>Анкета пока недоступна</h1><p class="muted">'+esc(friendlyError(e))+'</p></div>')}

    if(q.complete){
      await loadMe();
      return renderOnboarding();
    }
    const progress=q.progress||{};
    const question=q.question||{};
    if(q.phase==="ADAPTIVE"){
      setTimeout(()=>post("/api/v1/questionnaire/adaptive/prefetch",{}).catch(()=>{}),120);
    }
    root.innerHTML=onboardingChrome("questionnaire",
      '<div class="onboarding-card questionnaire-card">'+
      '<div class="question-meta"><span>'+esc(question.axis_label||"Совместимость")+'</span><b>'+esc(progress.percent||0)+'%</b></div>'+
      '<div class="progress-track big"><i style="width:'+Number(progress.percent||0)+'%"></i></div>'+
      '<h1>'+esc(question.text||"")+'</h1>'+
      '<p class="muted">Выберите вариант, который лучше всего описывает вас. Здесь нет правильных ответов.</p>'+
      '<div class="answer-scale">'+(question.options||[]).map(o=>
        '<button type="button" class="answer-option" data-answer="'+esc(o.value)+'"><b>'+esc(o.value)+'</b><span>'+esc(o.label)+'</span></button>'
      ).join("")+'</div>'+
      '<button type="button" class="primary full questionnaire-continue" id="questionnaire-continue" disabled>Сначала выберите ответ</button>'+
      '<button type="button" class="ghost full" id="questionnaire-later">Продолжить позже</button>'+
      '</div>');
    bindVerificationBanner();
    pick("onboarding-exit").onclick=()=>setRoute("home");
    pick("questionnaire-later").onclick=()=>setRoute("home");
    let selectedAnswer = null;
    const answerButtons = [...document.querySelectorAll("[data-answer]")];
    const continueAnswer = pick("questionnaire-continue");
    answerButtons.forEach(btn=>{
      btn.type="button";
      btn.onclick=()=>{
        selectedAnswer=Number(btn.dataset.answer);
        answerButtons.forEach(x=>x.classList.toggle("selected",x===btn));
        continueAnswer.disabled=false;
        continueAnswer.textContent="Продолжить →";
      };
    });
    continueAnswer.onclick=async()=>{
      if(selectedAnswer===null)return;
      answerButtons.forEach(x=>x.disabled=true);
      continueAnswer.disabled=true;
      continueAnswer.textContent="Сохраняем…";
      try{
        await post("/api/v1/questionnaire/adaptive/answer",{question_token:question.token,value:selectedAnswer});
        await renderQuestionnaireStep();
      }catch(e){
        answerButtons.forEach(x=>x.disabled=false);
        continueAnswer.disabled=false;
        continueAnswer.textContent="Продолжить →";
        onboardingStatus("Не удалось сохранить ответ: "+friendlyError(e),true);
      }
    };
  }

  function ageFromDob(dob){
    if(!dob)return null;
    const birth=new Date(dob+"T00:00:00");
    if(Number.isNaN(birth.getTime()))return null;
    const now=new Date();
    let age=now.getFullYear()-birth.getFullYear();
    const beforeBirthday=(now.getMonth()<birth.getMonth())||(now.getMonth()===birth.getMonth()&&now.getDate()<birth.getDate());
    if(beforeBirthday)age--;
    return age;
  }

  function completionPercent(c={}){
    const keys=["basic","relationship","readiness","details","questionnaire","partner_preferences","photos"];
    return Math.round(keys.filter(key=>!!c[key]).length*100/keys.length);
  }

  function profileBackHeader(title,back="profile"){
    return '<header class="topbar profile-subhead"><button class="icon-btn" id="profile-back">←</button><div><div class="eyebrow">Профиль</div><div class="brand" style="font-size:25px">'+esc(title)+'</div></div><div></div></header>';
  }

  function inlineStatus(id,message,error=false){
    const el=document.getElementById(id);
    if(!el)return;
    el.hidden=false;
    el.className="status"+(error?" error":"");
    el.textContent=message;
  }

  function profileMenuRow(icon,title,subtitle,route,badge=""){
    return '<button class="profile-menu-row" data-route="'+route+'">'+
      '<span class="profile-menu-icon">'+icon+'</span>'+
      '<span class="profile-menu-copy"><b>'+esc(title)+'</b><small>'+esc(subtitle)+'</small></span>'+
      (badge?'<span class="profile-menu-badge">'+esc(badge)+'</span>':'')+
      '<span class="profile-menu-arrow">›</span>'+
    '</button>';
  }

  async function renderProfile() {
    clearPoller(); loading("profile"); await loadMe();
    const p=state.profile?.profile||{};
    const c=state.profile?.completion||{};
    const pct=completionPercent(c);
    let photoData={photos:[]},identity={status:"NOT_STARTED",verified:false};
    try{
      [photoData,identity]=await Promise.all([
        api("/api/v1/photos"),
        api("/api/v1/identity/verification")
      ]);
    }catch{}
    const photos=photoData.photos||[];
    const mainPhoto=photos.find(x=>x.is_main)||photos[0];
    const age=ageFromDob(p.dob);
    const waitlist=state.onboarding?.waitlist||{};
    const statusLabels={
      ACTIVE_SEARCH:"Активно знакомлюсь",
      OPEN_TO_MATCH:"Открыт(а) к знакомствам",
      PAUSED:"На паузе",
      IN_RELATIONSHIP:"Уже в отношениях",
      NOT_ACTIVE:"Знакомства выключены",
    };
    const photoHtml=mainPhoto?.url
      ? '<img class="profile-avatar-large" src="'+esc(mainPhoto.url)+'" alt="Фото профиля">'
      : '<div class="profile-avatar-large profile-avatar-empty">♡</div>';

    root.innerHTML='<main class="page profile-page profile-v19">'+
      '<section class="profile-v19-hero">'+
        '<div class="profile-v19-person">'+
          '<div class="profile-v19-avatar-wrap">'+photoHtml+'<button class="profile-avatar-edit" data-route="photos" aria-label="Изменить фото">✎</button></div>'+
          '<div class="profile-v19-person-copy"><h1>'+esc(p.display_name||"MatchLab")+(age?", "+age:"")+'</h1><p class="profile-location">⌖ '+esc(p.city||"Город не указан")+'</p><div class="profile-state-row"><span class="profile-state"><i></i>'+esc(statusLabels[p.relationship_status]||"Настройте статус знакомств")+'</span>'+(identity.verified?'<span class="identity-badge">✓ Личность подтверждена</span>':'')+'</div></div>'+
        '</div>'+
        '<div class="profile-v19-completion">'+
          '<div class="profile-v19-completion-head"><div><b>Профиль заполнен на '+pct+'%</b><span>'+esc(waitlist.message||"Завершите профиль, чтобы подбор был точнее.")+'</span></div><strong>'+pct+'%</strong></div>'+
          '<div class="progress-track big"><i style="width:'+pct+'%"></i></div>'+
          (pct<100?'<button class="primary full" data-route="onboarding">Продолжить анкету →</button>':'<button class="secondary full" data-route="onboarding">Статус листа ожидания</button>')+
        '</div>'+
      '</section>'+
      '<section class="profile-menu-section profile-v19-section"><div class="profile-menu-heading"><span>Профиль и подбор</span><small>Настройте себя и того, кого хотите встретить</small></div><div class="profile-menu profile-v19-menu">'+
        profileMenuRow("👤","Редактировать профиль","Имя, о себе, образ жизни","profile-edit")+
        profileMenuRow("🎯","Кого я ищу","Возраст, цели и важные критерии","preferences")+
        profileMenuRow("🧠","Моя совместимость","Ваши приоритеты по анкете","compatibility",c.questionnaire?"Готово":"")+
        profileMenuRow("📷","Мои фотографии","Главное фото, порядок и подтверждение личности","photos",(photoData.progress?.approved||0)+"/"+(photoData.progress?.minimum||1))+
      '</div></section>'+
      '<section class="profile-menu-section profile-v19-section"><div class="profile-menu-heading"><span>Аккаунт и безопасность</span></div><div class="profile-menu profile-v19-menu">'+
        profileMenuRow("❤️","Статус знакомств","Активность и пауза","dating-status")+
        profileMenuRow("🔔","Уведомления","Сообщения и совпадения","notifications")+
        profileMenuRow("🛡","Безопасность","Блокировки и жалобы","safety")+
        profileMenuRow("⚙️","Настройки аккаунта","Вход, данные и удаление","settings")+
      '</div></section>'+
    '</main>'+nav("profile");
    bindCommon();
  }

  async function renderProfileEdit(){
    clearPoller(); loading("profile"); await loadMe();
    const p=state.profile?.profile||{};
    root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Редактировать профиль")+
      '<section class="card settings-card"><div class="section-head compact"><div><div class="eyebrow">Основное</div><h2>О вас</h2></div></div>'+
      '<div class="form-grid">'+
        '<label class="field-label">Имя<input class="input" id="edit-name" maxlength="80" value="'+esc(p.display_name||"")+'"></label>'+
        '<label class="field-label">Дата рождения<input class="input" id="edit-dob" type="date" value="'+esc(p.dob||"")+'"></label>'+
        '<label class="field-label">Ваш пол'+selectHtml("edit-gender",p.gender,[["M","Мужчина"],["F","Женщина"],["OTHER","Другое"]])+'</label>'+
        '<label class="field-label">Кого ищете'+selectHtml("edit-seek",p.seek_gender,[["F","Женщину"],["M","Мужчину"],["ANY","Не важно"],["OTHER","Другое"]])+'</label>'+
        '<label class="field-label">Рост, см<input class="input" id="edit-height" type="number" min="100" max="250" value="'+esc(p.height||"")+'"></label>'+
        '<label class="field-label">Цель знакомства'+selectHtml("edit-goal",p.dating_goal,[["SERIOUS","Серьёзные отношения"],["FAMILY","Семья"],["SEE","Посмотрим, как сложится"],["CHAT","Общение"],["UNKNOWN","Пока не знаю"]])+'</label>'+
        '<label class="field-label">Дети'+selectHtml("edit-children",p.children_status,[["NO_CHILDREN","Нет детей"],["HAS_CHILDREN","Есть дети"]])+'</label>'+
        '<label class="field-label">Планы на детей'+selectHtml("edit-children-plans",p.children_plans,[["WANTS","Хочу"],["MAYBE","Возможно"],["DOES_NOT_WANT","Не хочу"]])+'</label>'+
        '<label class="field-label">Курение'+selectHtml("edit-smoking",p.smoking,[["NO","Не курю"],["RARE","Иногда"],["YES","Курю"]])+'</label>'+
        '<label class="field-label">Алкоголь'+selectHtml("edit-alcohol",p.alcohol,[["NO","Не употребляю"],["RARE","Редко"],["MODERATE","Умеренно"],["YES","Регулярно"]])+'</label>'+
        '<label class="field-label">Образ жизни'+selectHtml("edit-lifestyle",p.lifestyle,[["CALM","Спокойный"],["BALANCED","Сбалансированный"],["ACTIVE","Активный"],["VERY_ACTIVE","Очень активный"]])+'</label>'+
        '<label class="field-label">Религия — необязательно<input class="input" id="edit-religion" maxlength="120" value="'+esc(p.religion||"")+'"></label>'+
      '</div>'+
      '<label class="field-label" style="margin-top:14px">О себе<textarea class="input textarea" id="edit-bio" maxlength="2000">'+esc(p.bio||"")+'</textarea></label>'+
      '<button class="primary full" id="save-profile-edit">Сохранить изменения</button>'+
      '<div id="profile-edit-status" class="status" hidden></div></section>'+
    '</main>'+nav("profile");
    bindCommon();
    document.getElementById("profile-back").onclick=()=>setRoute("profile");
    document.getElementById("save-profile-edit").onclick=async()=>{
      const height=Number(document.getElementById("edit-height").value);
      if(!document.getElementById("edit-name").value.trim())return inlineStatus("profile-edit-status","Укажите имя.",true);
      if(!document.getElementById("edit-dob").value)return inlineStatus("profile-edit-status","Укажите дату рождения.",true);
      if(!height)return inlineStatus("profile-edit-status","Укажите рост.",true);
      const btn=document.getElementById("save-profile-edit");
      btn.disabled=true; inlineStatus("profile-edit-status","Сохраняем…");
      try{
        await post("/api/v1/profile/basic",{
          display_name:document.getElementById("edit-name").value.trim(),
          dob:document.getElementById("edit-dob").value,
          gender:document.getElementById("edit-gender").value,
          seek_gender:document.getElementById("edit-seek").value,
          market_code:p.market_code||"KZ-ALA",
          preferred_locale:p.preferred_locale||"ru-KZ"
        });
        await post("/api/v1/profile/details",{
          height,
          dating_goal:document.getElementById("edit-goal").value,
          children_status:document.getElementById("edit-children").value,
          children_plans:document.getElementById("edit-children-plans").value,
          smoking:document.getElementById("edit-smoking").value,
          alcohol:document.getElementById("edit-alcohol").value,
          lifestyle:document.getElementById("edit-lifestyle").value,
          bio:document.getElementById("edit-bio").value.trim(),
          religion:document.getElementById("edit-religion").value.trim(),
          nationality:p.nationality||""
        });
        await loadMe();
        inlineStatus("profile-edit-status","Изменения сохранены ✓");
        btn.disabled=false;
      }catch(e){
        btn.disabled=false;inlineStatus("profile-edit-status","Не удалось сохранить: "+friendlyError(e),true);
      }
    };
  }

  async function renderPreferences(){
    clearPoller(); loading("profile"); await loadMe();
    let data={values:{}};
    try{data=await api("/api/v1/preferences");}catch{}
    const values=data.values||{};
    const pref=(key)=>values[key]||{};
    const val=(key,fallback="")=>pref(key).value??fallback;
    const imp=(key)=>pref(key).importance||"";
    const first=(key)=>{
      const v=val(key,[]);
      return Array.isArray(v)&&v.length?v[0]:"";
    };
    const age=val("age",{}),height=val("height",{}),distance=val("distance_km",{});

    root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Кого я ищу")+
      '<section class="card settings-card preferences-editor"><div class="eyebrow">Критерии партнёра</div><h2>Что для вас действительно важно?</h2>'+
      '<p class="muted">Вы сами определяете силу каждого критерия. «Не важно» не фильтрует людей и вообще не участвует в проценте.</p>'+
      '<div class="preference-grid">'+
        preferenceCard({key:"age",title:"Возраст партнёра",importance:imp("age"),valueHtml:'<div class="range-pair"><input class="input" id="pref-edit-age-min" type="number" min="18" max="100" value="'+esc(age.min??"")+'" placeholder="От"><input class="input" id="pref-edit-age-max" type="number" min="18" max="100" value="'+esc(age.max??"")+'" placeholder="До"></div>'})+
        preferenceCard({key:"gender",title:"Кого ищу",importance:imp("gender"),valueHtml:selectHtml("pref-edit-gender",first("gender"),[["F","Женщину"],["M","Мужчину"],["OTHER","Другой пол"]])})+
        preferenceCard({key:"market",title:"Город партнёра",importance:imp("market"),valueHtml:selectHtml("pref-edit-market",first("market"),MARKET_OPTIONS.slice(0,4),{placeholder:"Выберите город"})})+
        preferenceCard({key:"distance_km",title:"Максимальное расстояние",hint:"Ориентир между городами, не геолокация человека",importance:imp("distance_km"),valueHtml:'<input class="input" id="pref-edit-distance" type="number" min="1" max="1000" value="'+esc(distance.max??"")+'" placeholder="км">'})+
        preferenceCard({key:"dating_goal",title:"Цель знакомства",importance:imp("dating_goal"),valueHtml:selectHtml("pref-edit-goal",first("dating_goal"),[["SERIOUS","Серьёзные отношения"],["FAMILY","Семья"],["SEE","Посмотрим"],["CHAT","Общение"],["UNKNOWN","Пока не знаю"]])})+
        preferenceCard({key:"children_status",title:"Дети",importance:imp("children_status"),valueHtml:selectHtml("pref-edit-children",first("children_status"),[["NO_CHILDREN","Без детей"],["HAS_CHILDREN","Есть дети"]])})+
        preferenceCard({key:"children_plans",title:"Планы на детей",importance:imp("children_plans"),valueHtml:selectHtml("pref-edit-plans",first("children_plans"),[["WANTS","Хочет"],["MAYBE","Возможно"],["DOES_NOT_WANT","Не хочет"]])})+
        preferenceCard({key:"smoking",title:"Курение",importance:imp("smoking"),valueHtml:selectHtml("pref-edit-smoking",first("smoking"),[["NO","Не курит"],["RARE","Иногда"],["YES","Курит"]])})+
        preferenceCard({key:"alcohol",title:"Алкоголь",importance:imp("alcohol"),valueHtml:selectHtml("pref-edit-alcohol",first("alcohol"),[["NO","Не употребляет"],["RARE","Редко"],["MODERATE","Умеренно"],["YES","Регулярно"]])})+
        preferenceCard({key:"lifestyle",title:"Образ жизни",importance:imp("lifestyle"),valueHtml:selectHtml("pref-edit-lifestyle",first("lifestyle"),[["CALM","Спокойный"],["BALANCED","Сбалансированный"],["ACTIVE","Активный"],["VERY_ACTIVE","Очень активный"]])})+
        preferenceCard({key:"height",title:"Рост партнёра",importance:imp("height"),valueHtml:'<div class="range-pair"><input class="input" id="pref-edit-height-min" type="number" min="100" max="250" value="'+esc(height.min??"")+'" placeholder="От"><input class="input" id="pref-edit-height-max" type="number" min="100" max="250" value="'+esc(height.max??"")+'" placeholder="До"></div>'})+
      '</div>'+
      '<button class="primary full" id="save-preferences-edit">Сохранить критерии</button>'+
      '<div id="preferences-status" class="status" hidden></div></section>'+
    '</main>'+nav("profile");
    bindCommon();
    document.getElementById("profile-back").onclick=()=>setRoute("profile");
    document.getElementById("save-preferences-edit").onclick=async()=>{
      const button=document.getElementById("save-preferences-edit");
      try{
        const simple=(key,id)=>{
          const importance=pick("importance-"+key).value;
          if(!importance)throw new Error("Выберите важность для каждого критерия");
          if(importance==="IGNORE")return {importance:"IGNORE"};
          const v=pick(id).value;
          if(!v)throw new Error("Заполните значение для критерия");
          return {importance,value:[v]};
        };
        const range=(key,minId,maxId,minAllowed,maxAllowed)=>{
          const importance=pick("importance-"+key).value;
          if(!importance)throw new Error("Выберите важность для каждого критерия");
          if(importance==="IGNORE")return {importance:"IGNORE"};
          const min=Number(pick(minId).value),max=Number(pick(maxId).value);
          if(!min||!max||min<minAllowed||max>maxAllowed||max<min)throw new Error("Проверьте диапазон "+key);
          return {importance,value:{min,max}};
        };
        const maxPref=(key,id)=>{
          const importance=pick("importance-"+key).value;
          if(!importance)throw new Error("Выберите важность для каждого критерия");
          if(importance==="IGNORE")return {importance:"IGNORE"};
          const max=Number(pick(id).value);
          if(!max||max<1||max>1000)throw new Error("Проверьте расстояние");
          return {importance,value:{max}};
        };
        const prefs={
          age:range("age","pref-edit-age-min","pref-edit-age-max",18,100),
          gender:simple("gender","pref-edit-gender"),
          market:simple("market","pref-edit-market"),
          distance_km:maxPref("distance_km","pref-edit-distance"),
          dating_goal:simple("dating_goal","pref-edit-goal"),
          children_status:simple("children_status","pref-edit-children"),
          children_plans:simple("children_plans","pref-edit-plans"),
          smoking:simple("smoking","pref-edit-smoking"),
          alcohol:simple("alcohol","pref-edit-alcohol"),
          lifestyle:simple("lifestyle","pref-edit-lifestyle"),
          height:range("height","pref-edit-height-min","pref-edit-height-max",100,250)
        };
        button.disabled=true;inlineStatus("preferences-status","Сохраняем…");
        await post("/api/v1/preferences",{preferences:prefs});
        await loadMe();
        inlineStatus("preferences-status","Критерии сохранены ✓");
      }catch(e){inlineStatus("preferences-status",friendlyError(e)||"Не удалось сохранить критерии",true)}
      finally{button.disabled=false}
    };
  }


  async function renderCompatibility(){
    clearPoller(); loading("profile");
    let data=null;
    try{data=await api("/api/v1/compatibility/me");}catch{}
    root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Моя совместимость")+
      (data
        ? '<section class="card compatibility-self"><div class="eyebrow">Ваш профиль совместимости</div><h2>Не «оценка личности», а карта приоритетов</h2>'+
          '<p class="muted">'+esc(data.note||"")+'</p>'+
          '<div class="compatibility-bars">'+Object.entries(data.summary||{}).map(([label,value])=>
            '<div class="compatibility-row"><div><b>'+esc(label)+'</b><span>'+esc(value)+'%</span></div><div class="compatibility-track"><i style="width:'+Math.max(0,Math.min(100,Number(value)||0))+'%"></i></div></div>'
          ).join("")+'</div>'+
          '<div class="insight-box"><b>Как это используется</b><p>MatchLab сравнивает не один общий процент, а несколько областей: ценности, отношение к семье, близость, социальность и другие сигналы анкеты. Итоговый подбор учитывает также ваши критерии партнёра.</p></div>'+
          '<button class="secondary full" data-route="preferences">Изменить критерии партнёра</button></section>'
        : '<section class="card empty"><div class="emoji">🧠</div><h3>Сначала завершите анкету</h3><p class="muted">После заполнения мы покажем ваш профиль совместимости.</p><button class="primary" data-route="onboarding">Продолжить анкету</button></section>')+
    '</main>'+nav("profile");
    bindCommon();
    document.getElementById("profile-back").onclick=()=>setRoute("profile");
  }

  async function renderPhotos(){
    clearPoller(); loading("profile");
    let data={photos:[],progress:{}},identity={status:"NOT_STARTED",verified:false};
    try{
      [data,identity]=await Promise.all([
        api("/api/v1/photos"),
        api("/api/v1/identity/verification")
      ]);
    }catch(e){
      root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Мои фотографии")+'<section class="card empty"><h3>Фото пока недоступны</h3><p class="muted">'+esc(friendlyError(e))+'</p></section></main>'+nav("profile");
      bindCommon();document.getElementById("profile-back").onclick=()=>setRoute("profile");return;
    }
    const items=(data.photos||[]).slice().sort((a,b)=>(a.sort_order||0)-(b.sort_order||0));
    const statusLabel={APPROVED:"Одобрено",PENDING:"На модерации",REJECTED:"Отклонено"};
    const identityLabel={
      NOT_STARTED:"Не начато",
      PENDING:"На проверке",
      VERIFIED:"Личность подтверждена",
      REJECTED:"Нужно повторить"
    };
    const canSubmitIdentity=identity.status==="NOT_STARTED"||identity.status==="REJECTED";
    const minimum=Number(data.progress?.minimum||1);
    const maximum=Number(data.progress?.maximum||5);
    root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Мои фотографии")+
      '<section class="card settings-card identity-verification-card">'+
        '<div class="identity-verification-head"><div><div class="eyebrow">Доверие и безопасность</div><h2>Подтверждение личности</h2></div><span class="identity-status '+String(identity.status||"").toLowerCase()+'">'+esc(identityLabel[identity.status]||identity.status)+'</span></div>'+
        '<p class="muted">'+esc(identity.instructions||"Сделайте свежее селфи для проверки.")+'</p>'+
        (identity.status==="VERIFIED"
          ? '<div class="identity-verified-box"><b>✓ Личность подтверждена</b><span>Селфи прошло ручную проверку и не показывается другим пользователям.</span></div>'
          : identity.status==="PENDING"
          ? '<div class="identity-pending-box"><b>Проверяем селфи</b><span>После решения вы получите уведомление.</span></div>'
          : '<label class="photo-upload identity-upload"><input type="file" id="identity-selfie-upload" accept="image/jpeg,image/png,image/webp" capture="user"><span>Сделать селфи для проверки</span><small>Селфи не попадёт в вашу галерею</small></label>'+
            (identity.status==="REJECTED"&&identity.moderation_reason?'<p class="photo-reason">Причина: '+esc(identity.moderation_reason)+'</p>':'')
        )+
        '<div id="identity-status-message" class="status" hidden></div>'+
      '</section>'+
      '<section class="card settings-card"><div class="section-head compact"><div><div class="eyebrow">Фотографии профиля</div><h2>'+(data.progress?.approved||0)+'/'+minimum+' минимум</h2></div></div>'+
      '<p class="muted">Для готовности профиля достаточно 1 одобренного фото. Можно добавить до '+maximum+'. Рекомендуем 3–5 фотографий.</p>'+
      '<div class="photo-manager-grid">'+
        items.map((item,index)=>'<article class="photo-manager-item">'+
          (item.url?'<img src="'+esc(item.url)+'" alt="Фото '+(index+1)+'">':'<div class="photo-manager-placeholder">Фото</div>')+
          '<div class="photo-manager-meta"><span class="photo-status '+String(item.moderation_status||"").toLowerCase()+'">'+esc(statusLabel[item.moderation_status]||item.moderation_status||"")+'</span>'+
          (item.is_main?'<b>Главное</b>':'')+'</div>'+
          (item.moderation_reason?'<small class="photo-reason">'+esc(item.moderation_reason)+'</small>':'')+
          '<div class="photo-manager-actions">'+
            (item.moderation_status==="APPROVED"&&!item.is_main?'<button class="secondary" data-photo-main="'+item.id+'">Главное</button>':'')+
            (index>0?'<button class="ghost" data-photo-move="'+item.id+'" data-dir="-1">←</button>':'')+
            (index<items.length-1?'<button class="ghost" data-photo-move="'+item.id+'" data-dir="1">→</button>':'')+
            '<button class="ghost danger-text" data-photo-delete="'+item.id+'">Удалить</button>'+
          '</div></article>').join("")+
        (items.length<maximum
          ? '<label class="photo-upload photo-manager-upload"><input type="file" id="profile-photo-upload" accept="image/jpeg,image/png,image/webp"><span>＋ Добавить фото</span><small>JPG, PNG или WEBP · до 12 МБ</small></label>'
          : '<div class="photo-manager-placeholder limit-reached">Добавлено максимум '+maximum+' фото</div>')+
      '</div><div id="photos-status" class="status" hidden></div></section>'+
    '</main>'+nav("profile");
    bindCommon();
    document.getElementById("profile-back").onclick=()=>setRoute("profile");
    document.querySelectorAll("[data-photo-main]").forEach(btn=>btn.onclick=async()=>{
      try{await post("/api/v1/photos/main",{photo_id:Number(btn.dataset.photoMain)});await renderPhotos()}catch(e){inlineStatus("photos-status","Не удалось выбрать главное фото: "+friendlyError(e),true)}
    });
    document.querySelectorAll("[data-photo-delete]").forEach(btn=>btn.onclick=async()=>{
      if(!confirm("Удалить эту фотографию?"))return;
      try{await post("/api/v1/photos/delete",{photo_id:Number(btn.dataset.photoDelete)});await renderPhotos()}catch(e){inlineStatus("photos-status","Не удалось удалить фото: "+friendlyError(e),true)}
    });
    document.querySelectorAll("[data-photo-move]").forEach(btn=>btn.onclick=async()=>{
      const id=Number(btn.dataset.photoMove),dir=Number(btn.dataset.dir);
      const ids=items.map(x=>Number(x.id));
      const index=ids.indexOf(id),next=index+dir;
      if(index<0||next<0||next>=ids.length)return;
      [ids[index],ids[next]]=[ids[next],ids[index]];
      try{await post("/api/v1/photos/reorder",{photo_ids:ids});await renderPhotos()}catch(e){inlineStatus("photos-status","Не удалось изменить порядок: "+friendlyError(e),true)}
    });
    const upload=document.getElementById("profile-photo-upload");
    if(upload)upload.onchange=async e=>{
      const file=e.target.files?.[0];if(!file)return;
      if(file.size>12*1024*1024)return inlineStatus("photos-status","Фото слишком большое. Максимум 12 МБ.",true);
      inlineStatus("photos-status","Загружаем фото…");
      try{
        const prep=await post("/api/v1/photos/prepare",{mime:file.type});
        const headers=prep.upload?.headers||{"Content-Type":file.type};
        const up=await fetch(prep.upload.url,{method:"PUT",headers,body:file});
        if(!up.ok)throw new Error("upload_failed");
        await post("/api/v1/photos/finalize",{ticket:prep.ticket});
        await renderPhotos();
      }catch(err){inlineStatus("photos-status","Не удалось загрузить фото: "+err.message,true)}
    };
    const selfie=document.getElementById("identity-selfie-upload");
    if(selfie&&canSubmitIdentity)selfie.onchange=async e=>{
      const file=e.target.files?.[0];if(!file)return;
      if(file.size>12*1024*1024)return inlineStatus("identity-status-message","Селфи слишком большое. Максимум 12 МБ.",true);
      inlineStatus("identity-status-message","Загружаем селфи…");
      try{
        const prep=await post("/api/v1/identity/verification/prepare",{mime:file.type});
        const headers=prep.upload?.headers||{"Content-Type":file.type};
        const up=await fetch(prep.upload.url,{method:"PUT",headers,body:file});
        if(!up.ok)throw new Error("upload_failed");
        await post("/api/v1/identity/verification/finalize",{ticket:prep.ticket});
        await renderPhotos();
      }catch(err){inlineStatus("identity-status-message","Не удалось отправить селфи: "+err.message,true)}
    };
  }


  async function renderDatingStatus(){
    clearPoller(); loading("profile"); await loadMe();
    const p=state.profile?.profile||{};
    const relMap={ACTIVE_SEARCH:"ACTIVE",OPEN_TO_MATCH:"OPEN",PAUSED:"UNSURE",NOT_ACTIVE:"NO",IN_RELATIONSHIP:"IN_RELATIONSHIP"};
    const current=relMap[p.relationship_status]||"ACTIVE";
    root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Статус знакомств")+
      '<section class="card settings-card"><div class="eyebrow">Видимость в подборе</div><h2>Управляйте статусом без удаления профиля</h2>'+
      '<p class="muted">Пауза или статус «в отношениях» сразу исключают профиль из активного подбора.</p>'+
      '<div class="form-stack">'+
        '<label class="field-label">Сейчас я'+selectHtml("dating-openness",current,[["ACTIVE","Активно хочу знакомиться"],["OPEN","Открыт(а), если встречу подходящего человека"],["UNSURE","Поставить знакомства на паузу"],["NO","Не хочу знакомств"],["IN_RELATIONSHIP","Уже в отношениях"]])+'</label>'+
        '<label class="field-label">Готовность общаться в чате'+selectHtml("dating-chat",p.readiness_chat,[["YES","Да, готов(а)"],["RATHER_YES","Скорее да"],["LOOK_ONLY","Пока хочу присмотреться"]])+'</label>'+
        '<label class="field-label">Готовность встретиться офлайн'+selectHtml("dating-offline",p.readiness_offline,[["YES","Да"],["MAYBE","Возможно, после общения"],["NO","Пока нет"]])+'</label>'+
        '<button class="primary full" id="save-dating-status">Сохранить статус</button>'+
        '<div id="dating-status-message" class="status" hidden></div>'+
      '</div></section>'+
    '</main>'+nav("profile");
    bindCommon();document.getElementById("profile-back").onclick=()=>setRoute("profile");
    document.getElementById("save-dating-status").onclick=async()=>{
      const selected=document.getElementById("dating-openness").value;
      const inRelationship=selected==="IN_RELATIONSHIP";
      const openness=inRelationship?"NO":selected;
      const btn=document.getElementById("save-dating-status");btn.disabled=true;
      inlineStatus("dating-status-message","Сохраняем…");
      try{
        await post("/api/v1/profile/relationship",{in_relationship:inRelationship,openness});
        await post("/api/v1/profile/readiness",{chat:document.getElementById("dating-chat").value,offline:document.getElementById("dating-offline").value});
        await loadMe();btn.disabled=false;inlineStatus("dating-status-message","Статус обновлён ✓");
      }catch(e){btn.disabled=false;inlineStatus("dating-status-message","Не удалось сохранить: "+friendlyError(e),true)}
    };
  }

  async function renderNotifications(){
    clearPoller(); loading("profile");
    const permission=("Notification" in window)?Notification.permission:"unsupported";
    const stateLabel={
      granted:"Уведомления включены",
      denied:"Уведомления отключены",
      default:"Уведомления пока выключены",
      unsupported:"Уведомления недоступны",
    }[permission]||"Уведомления";
    const stateText={
      granted:"Вы сможете вовремя узнавать о новых совпадениях, сообщениях и важных обновлениях.",
      denied:"Разрешить уведомления можно в настройках браузера или устройства.",
      default:"Включите уведомления, чтобы не пропускать новые совпадения и сообщения.",
      unsupported:"На этом устройстве уведомления сейчас недоступны. Сам MatchLab продолжит работать как обычно.",
    }[permission]||"";
    root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Уведомления")+
      '<section class="card settings-card notifications-friendly">'+
        '<div class="eyebrow">Уведомления</div>'+
        '<h2>Не пропускайте важные совпадения</h2>'+
        '<p class="muted">Получайте уведомления о новых совпадениях, сообщениях и важной активности в MatchLab.</p>'+
        '<div class="setting-line notification-state"><div><b>'+esc(stateLabel)+'</b><span class="muted">'+esc(stateText)+'</span></div>'+
          (permission==="granted"?'<span class="tag">Включены</span>':permission==="default"?'<button class="primary" id="request-browser-notifications">Включить</button>':'')+
        '</div>'+
        '<div id="notifications-status" class="status" hidden></div>'+
      '</section></main>'+nav("profile");
    bindCommon();document.getElementById("profile-back").onclick=()=>setRoute("profile");
    const btn=document.getElementById("request-browser-notifications");
    if(btn)btn.onclick=async()=>{
      try{await Notification.requestPermission();await renderNotifications()}catch{
        inlineStatus("notifications-status","Не удалось изменить настройку уведомлений.",true);
      }
    };
  }

  async function renderSafety(){
    clearPoller(); loading("profile");
    let data={blocked:[]};
    try{data=await api("/api/v1/safety/blocked");}catch{}
    const blocked=data.blocked||[];
    root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Безопасность")+
      '<section class="card settings-card"><div class="eyebrow">Безопасность</div><h2>Заблокированные пользователи</h2>'+
      '<p class="muted">Заблокированный человек не появляется в подборе и не может отправлять вам сообщения.</p>'+
      (blocked.length?'<div class="blocked-list">'+blocked.map(item=>
        '<div class="blocked-row"><div class="profile-avatar-small">⊘</div><div><b>'+esc(item.display_name||"Пользователь")+(item.age?", "+item.age:"")+'</b><small>'+esc(item.city||"")+'</small></div><button class="secondary" data-unblock-user="'+item.user_id+'">Разблокировать</button></div>'
      ).join("")+'</div>':'<div class="empty compact-empty"><div class="emoji">🛡</div><h3>Список пуст</h3><p class="muted">Здесь появятся люди, которых вы заблокируете из карточки или чата.</p></div>')+
      '<div id="safety-page-status" class="status" hidden></div>'+
      '<div class="insight-box"><b>Как пожаловаться</b><p>Откройте карточку кандидата или меню ⋯ в чате и выберите причину жалобы. Она попадёт в очередь модерации.</p></div>'+
      '</section></main>'+nav("profile");
    bindCommon();document.getElementById("profile-back").onclick=()=>setRoute("profile");
    document.querySelectorAll("[data-unblock-user]").forEach(btn=>btn.onclick=async()=>{
      try{await post("/api/v1/safety/unblock",{user_id:Number(btn.dataset.unblockUser)});await renderSafety()}catch(e){inlineStatus("safety-page-status","Не удалось разблокировать: "+friendlyError(e),true)}
    });
  }

  async function renderSettings(){
    clearPoller(); loading("profile");
    let methods={methods:[]};
    try{methods=await api("/api/v1/auth/methods");}catch{}
    const methodLabels={email:"Email",phone:"Телефон",google:"Google",apple:"Apple"};
    root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Настройки аккаунта")+
      '<section class="card settings-card"><div class="eyebrow">Вход и безопасность</div><h2>Аккаунт</h2>'+
      '<div class="setting-line"><div><b>Способы входа</b><span class="muted">'+esc((methods.methods||[]).map(x=>methodLabels[x]||x).join(", ")||"Не определено")+'</span></div><button class="secondary" data-route="reset-password">Сменить пароль</button></div>'+
      (methods.phone?'<div class="setting-line"><div><b>Телефон</b><span class="muted">'+esc(methods.phone)+'</span></div><span class="tag">'+(methods.phone_verified?"Подтверждён":"Не подтверждён")+'</span></div>':'')+
      '</section>'+
      '<section class="card settings-card"><div class="eyebrow">Данные и документы</div>'+
      '<a class="settings-link" href="/privacy" target="_blank" rel="noopener"><b>Политика конфиденциальности</b><span>Открыть ↗</span></a>'+
      '<a class="settings-link" href="/terms" target="_blank" rel="noopener"><b>Условия использования</b><span>Открыть ↗</span></a>'+
      '<button class="settings-link button-link" id="export-data"><b>Скачать копию моих данных</b><span>Скачать ↓</span></button>'+
      '</section>'+
      '<section class="card settings-card danger-zone"><div class="eyebrow">Управление аккаунтом</div><h2>Удаление аккаунта</h2>'+
      '<p class="muted">Для защиты от случайного удаления введите <b>УДАЛИТЬ</b>. После подтверждения аккаунт станет недоступен и начнётся удаление данных.</p>'+
      '<input class="input" id="delete-confirmation" placeholder="Введите УДАЛИТЬ" autocomplete="off">'+
      '<button class="danger-btn full" id="delete-account" disabled>Удалить аккаунт</button>'+
      '<div id="settings-status" class="status" hidden></div>'+
      '</section>'+
      '<button class="secondary full logout-wide" id="settings-logout">Выйти из аккаунта</button>'+
    '</main>'+nav("profile");
    bindCommon();document.getElementById("profile-back").onclick=()=>setRoute("profile");
    document.getElementById("export-data").onclick=async()=>{
      const btn=document.getElementById("export-data");btn.disabled=true;
      try{
        const data=await api("/api/v1/privacy/export");
        const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});
        const url=URL.createObjectURL(blob);
        const a=document.createElement("a");a.href=url;a.download="matchlab-my-data.json";a.click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
      }catch(e){inlineStatus("settings-status","Не удалось подготовить данные: "+friendlyError(e),true)}
      btn.disabled=false;
    };
    const deletionInput=document.getElementById("delete-confirmation");
    const deletionBtn=document.getElementById("delete-account");
    deletionInput.oninput=()=>{deletionBtn.disabled=deletionInput.value.trim().toUpperCase()!=="УДАЛИТЬ"};
    deletionBtn.onclick=async()=>{
      if(deletionInput.value.trim().toUpperCase()!=="УДАЛИТЬ")return;
      if(!confirm("Удалить аккаунт MatchLab? Это действие запускает процедуру удаления данных."))return;
      deletionBtn.disabled=true;
      try{
        await post("/api/v1/privacy/delete",{confirmation:"DELETE"});
        state.authenticated=false;state.profile=null;state.onboarding=null;
        location.hash="";
        renderAuth("login");
        status("Запрос на удаление аккаунта принят.");
      }catch(e){deletionBtn.disabled=false;inlineStatus("settings-status","Не удалось удалить аккаунт: "+friendlyError(e),true)}
    };
    document.getElementById("settings-logout").onclick=async()=>{
      try{await post("/api/v1/auth/logout",{});}catch{}
      state.authenticated=false;state.profile=null;state.onboarding=null;location.hash="";renderAuth("login");
    };
  }

  function hashQuery(){
    const raw=location.hash||"";
    const q=raw.includes("?")?raw.slice(raw.indexOf("?")+1):"";
    return new URLSearchParams(q);
  }

  async function renderEmailVerification(){
    clearPoller();
    const params=hashQuery();
    const email=params.get("email")||"";
    const challenge=params.get("challenge")||"";
    root.innerHTML='<main class="auth-screen verify-email-screen"><div class="verify-email-card">'+
      '<div class="brand">Match<span>Lab</span></div>'+
      '<div class="eyebrow">Подтверждение email</div>'+
      '<h1 id="verify-email-title">Проверяем ссылку…</h1>'+
      '<p class="muted" id="verify-email-copy">Это займёт несколько секунд.</p>'+
      '<button class="primary full" id="verify-email-continue" hidden>Продолжить →</button>'+
    '</div></main>';
    const title=pick("verify-email-title"),copy=pick("verify-email-copy"),btn=pick("verify-email-continue");
    if(!email||!challenge){
      title.textContent="Ссылка неполная";
      copy.textContent="Запросите новое письмо подтверждения в MatchLab.";
      btn.hidden=false;btn.textContent="Открыть MatchLab";btn.onclick=()=>setRoute("home");
      return;
    }
    try{
      await post("/api/v1/auth/email/verify",{email,challenge});
      title.textContent="Email подтверждён ✓";
      copy.textContent="Теперь подтверждение не будет мешать активному подбору.";
      btn.hidden=false;btn.onclick=async()=>{await loadMe();setRoute("home")};
    }catch(e){
      title.textContent="Ссылка истекла или уже использована";
      copy.textContent="Откройте MatchLab и запросите новое письмо подтверждения.";
      btn.hidden=false;btn.textContent="Открыть MatchLab";btn.onclick=()=>setRoute("home");
    }
  }

  async function renderRoute(force=false) {
    clearPoller();
    const route=(location.hash||"#home").slice(1).split("?")[0];
    if(route==="reset-password") return renderPasswordReset();
    if(route==="verify-email") return renderEmailVerification();
    if(!state.authenticated){
      try{
        await api("/api/v1/auth/methods");
        state.authenticated=true;
      }catch(e){
        if(e.status===401){renderAuth("login");return;}
      }
    }
    if(route==="onboarding") return renderOnboarding(force);
    if(route==="home") return renderHome();
    if(route==="candidate") return renderCandidate();
    if(route==="matches") return renderMatches();
    if(route==="chats") return renderChats();
    if(route==="chat") return renderChat();
    if(route==="profile") return renderProfile();
    if(route==="profile-edit") return renderProfileEdit();
    if(route==="preferences") return renderPreferences();
    if(route==="compatibility") return renderCompatibility();
    if(route==="photos") return renderPhotos();
    if(route==="dating-status") return renderDatingStatus();
    if(route==="notifications") return renderNotifications();
    if(route==="safety") return renderSafety();
    if(route==="settings") return renderSettings();
    return setRoute("home");
  }

  window.addEventListener("hashchange",()=>renderRoute());
  window.addEventListener("load",async()=>{
    captureFirstTouchAttribution();
    if(!safeStorage(sessionStorage,"ml_landing_view")){
      safeStorage(sessionStorage,"ml_landing_view","1");
      trackAnonymous("LANDING_VIEW");
    }
    if("serviceWorker" in navigator) navigator.serviceWorker.register("/web/sw.js").catch(()=>{});
    await renderRoute();
  });
})();