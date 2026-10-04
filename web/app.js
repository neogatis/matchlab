(() => {
  const root = document.getElementById("app");
  const HERO_IMAGE = "https://images.unsplash.com/photo-1776266099714-2177bb456209?auto=format&fit=crop&fm=jpg&q=86&w=2400";
  const ATTRIBUTION_KEY = "ml_attribution_v1";
  const VISITOR_KEY = "ml_visitor_id";

  function visitorId() {
    let value = localStorage.getItem(VISITOR_KEY);
    if (!value) {
      value = (crypto.randomUUID ? crypto.randomUUID() : Date.now()+"-"+Math.random().toString(36).slice(2));
      localStorage.setItem(VISITOR_KEY,value);
    }
    return value;
  }

  function captureAttribution() {
    let existing={};
    try{existing=JSON.parse(localStorage.getItem(ATTRIBUTION_KEY)||"{}")||{}}catch{}
    const query=new URLSearchParams(location.search);
    const hashQuery=(location.hash.includes("?")?new URLSearchParams(location.hash.split("?")[1]):new URLSearchParams());
    const read=(...keys)=>{
      for(const key of keys){
        const value=(query.get(key)||hashQuery.get(key)||"").trim();
        if(value)return value.slice(0,255);
      }
      return "";
    };
    const incoming={
      utm_source:read("utm_source"),
      utm_medium:read("utm_medium"),
      utm_campaign:read("utm_campaign"),
      utm_content:read("utm_content"),
      utm_term:read("utm_term"),
      referral_code:read("ref","referral","referral_code"),
      platform:"web"
    };
    const merged={...existing};
    Object.entries(incoming).forEach(([key,value])=>{
      if(value && !merged[key]) merged[key]=value;
    });
    try{localStorage.setItem(ATTRIBUTION_KEY,JSON.stringify(merged))}catch{}
    return merged;
  }

  function attributionPayload(){
    return captureAttribution();
  }

  function trackAnonymous(eventType){
    const key="ml_anon_"+eventType;
    if(sessionStorage.getItem(key))return;
    sessionStorage.setItem(key,"1");
    fetch("/api/v1/analytics/anonymous",{
      method:"POST",
      credentials:"include",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        event_type:eventType,
        visitor_id:visitorId(),
        platform:"web",
        attribution:attributionPayload()
      })
    }).catch(()=>sessionStorage.removeItem(key));
  }

  function trackClient(eventType,metadata={}){
    return post("/api/v1/analytics/event",{event_type:eventType,metadata:{platform:"web",...metadata}}).catch(()=>{});
  }

  const state = {
    authenticated: false,
    profile: null,
    onboarding: null,
    account: null,
    candidates: [],
    matches: [],
    conversations: [],
    currentCandidate: null,
    currentConversation: null,
    poller: null,
  };

  const esc = (value="") => String(value)
    .replaceAll("&","&amp;").replaceAll("<","&lt;")
    .replaceAll(">","&gt;").replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");

  const cookie = name => document.cookie.split(";")
    .map(v => v.trim())
    .find(v => v.startsWith(name + "="))
    ?.slice(name.length + 1) || "";

  async function api(path, options={}) {
    const method = options.method || "GET";
    const headers = {"Accept":"application/json", ...(options.headers || {})};
    if (!["GET","HEAD","OPTIONS"].includes(method)) {
      headers["Content-Type"] = "application/json";
      headers["X-CSRF-Token"] = decodeURIComponent(cookie("ml_csrf"));
      headers["Origin"] = location.origin;
    }
    const response = await fetch(path, {
      credentials:"include",
      ...options,
      method,
      headers,
    });
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch {}
    if (!response.ok) {
      const error = new Error(data.message || data.error || "HTTP " + response.status);
      error.status = response.status;
      error.code = data.error;
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
  }

  function nav(active) {
    const items = [
      ["home","⌂","Главная"],
      ["matches","♡","Совпадения"],
      ["chats","◌","Чаты"],
      ["profile","♙","Профиль"],
    ];
    return '<nav class="bottom-nav">' + items.map(([key, icon, label]) =>
      '<button class="nav-btn ' + (active===key?"active":"") + '" data-route="' + key + '">' +
      '<i>' + icon + '</i><span>' + label + '</span></button>'
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
    root.innerHTML = '<main class="auth-screen">' +
      '<img class="auth-hero-photo" src="/web/hero.jpg?v=14" alt="" aria-hidden="true">' +
      '<div class="auth-wrap">' +
        '<div class="auth-logo"><div class="brand-mark">♡</div><div class="brand">Match<span>Lab</span></div></div>' +
        '<div class="auth-tagline">' +
          '<div class="eyebrow">Знакомства по совместимости</div>' +
          '<h1>Не выбирай из всех.<br><span style="color:#ff5d6c">Найди подходящего.</span></h1>' +
          '<p>Общие ценности, реальные люди и серьёзные намерения.</p>' +
        '</div>' +
        '<div class="auth-panel">' +
          '<div class="tabs auth-switch">' +
            '<button class="tab ' + (!register?"active":"") + '" id="auth-login-tab">Вход</button>' +
            '<button class="tab ' + (register?"active":"") + '" id="auth-register-tab">Регистрация</button>' +
          '</div>' +
          '<section class="auth-card">' +
            '<div class="eyebrow">' + (register?"Новый профиль":"С возвращением") + '</div>' +
            '<h2 style="font-family:Georgia,serif;font-size:30px;line-height:1.04;margin:7px 0 8px">' +
              (register?"Создайте аккаунт":"Войдите в MatchLab") +
            '</h2>' +
            '<p class="muted" style="margin:0 0 18px">' +
              (register
                ?"Регистрация займёт пару минут. Затем начнём анкету совместимости."
                :"По SMS-коду или телефону/email и паролю.") +
            '</p>' +
            (register ? registerForm() : loginForm()) +
            '<div id="form-status" class="status" hidden style="margin-top:14px"></div>' +
          '</section>' +
        '</div>' +
        '<p class="auth-legal muted" style="font-size:11px;text-align:center;margin:13px 18px 0">18+. Продолжая, вы принимаете <a href="/terms" target="_blank" rel="noopener">Условия</a> и <a href="/privacy" target="_blank" rel="noopener">Политику конфиденциальности</a>. Профиль не публикуется до завершения анкеты и проверки фотографий.</p>' +
      '</div>' +
    '</main>';
    document.getElementById("auth-login-tab").onclick = () => renderAuth("login");
    document.getElementById("auth-register-tab").onclick = () => renderAuth("register");
    if(register) trackAnonymous("REGISTRATION_STARTED");
    register ? bindRegister() : bindLogin();
  }

  function loginForm() {
    return '<div class="tabs" id="login-method-tabs">' +
      '<button class="tab active" data-login-method="password">Пароль</button>' +
      '<button class="tab" data-login-method="sms">SMS-код</button>' +
    '</div>' +
    '<div id="login-password" class="form-stack">' +
      '<input class="input" id="login-identifier" placeholder="Телефон или email" autocomplete="username">' +
      '<input class="input" id="login-password-value" type="password" placeholder="Пароль" autocomplete="current-password">' +
      '<button class="primary full" id="password-login-btn">Войти →</button>' +
      '<button class="ghost full auth-link-btn" id="forgot-password-btn" type="button">Забыли пароль?</button>' +
    '</div>' +
    '<div id="login-sms" class="form-stack" hidden>' +
      '<input class="input" id="sms-phone" placeholder="+7 747 123 45 67" inputmode="tel">' +
      '<button class="primary full" id="sms-request-btn">Получить код →</button>' +
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
      } catch(e) { status("Не удалось отправить код: " + e.message, true); }
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
      }catch(e){status("Не удалось отправить код: "+e.message,true)}
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
      }catch(e){status("Не удалось отправить инструкцию: "+e.message,true)}
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
          : "Не удалось отправить код: " + e.message, true);
      }
    };
    document.getElementById("reg-phone-finish").onclick = async () => {
      const phone = document.getElementById("reg-phone").value.trim();
      const password = document.getElementById("reg-phone-password").value;
      const code = document.getElementById("reg-phone-code").value.trim();
      status("Создаём профиль…");
      try {
        const a=attributionPayload();
        await post("/api/v1/auth/phone/register/verify",{phone,password,code,referral_code:a.referral_code||"",attribution:a});
        await afterAuth();
      } catch(e) { status("Не удалось зарегистрироваться: " + e.message, true); }
    };
    document.getElementById("reg-email-finish").onclick = async () => {
      if(!document.getElementById("reg-legal").checked)return status("Подтвердите 18+ и принятие Условий и Политики конфиденциальности.",true);
      const email = document.getElementById("reg-email").value.trim();
      const password = document.getElementById("reg-email-password").value;
      if (!email) return status("Введите email.", true);
      if (password.length < 10) return status("Пароль — минимум 10 символов.", true);
      status("Создаём аккаунт…");
      try {
        const a=attributionPayload();
        await post("/api/v1/auth/register",{email,password,referral_code:a.referral_code||"",attribution:a});
        await afterAuth();
      } catch(e) { status("Не удалось зарегистрироваться: " + e.message, true); }
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
      state.account = onboarding?.account || profile?.account || null;
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
        '<div class="candidate-title"><div><h2>' + esc(name + age) + '</h2><div class="muted">' + esc(c.city || "") + '</div>' + (c.is_test_profile?'<span class="test-profile-badge">Тестовый профиль</span>':'') + '</div></div>' +
        '<div class="tags">' + compatibilityReason(c) + '</div>' +
        (c.bio ? '<p>' + esc(c.bio) + '</p>' : '') +
        '<button class="candidate-detail-link" data-candidate-detail="' + c.user_id + '">Подробнее о человеке →</button>' +
        '<div class="actions candidate-actions">' +
          '<button class="secondary candidate-reject" data-candidate-skip="' + c.user_id + '">Не мой человек</button>' +
          '<button class="primary" data-candidate-like="' + c.user_id + '">Хочу познакомиться</button>' +
        '</div>' +
        '<button class="safety-link" data-candidate-safety="' + c.user_id + '">Пожаловаться или заблокировать</button>' +
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
          alert("Сейчас действие недоступно: " + e.message);
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
          btn.textContent="Не мой человек";
          alert("Не удалось учесть выбор: "+e.message);
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
      }catch(e){btn.disabled=false;msg("Не удалось отправить жалобу: "+e.message,true)}
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
      }catch(e){btn.disabled=false;msg("Не удалось заблокировать: "+e.message,true)}
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
      } catch(e) { alert(e.message); }
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
      }catch(e){alert(e.message)}
    });
  }

  function chatTime(value){
    if(!value)return "";
    const d=new Date(value);
    if(Number.isNaN(d.getTime()))return "";
    const now=new Date();
    const same=now.toDateString()===d.toDateString();
    return same
      ? d.toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"})
      : d.toLocaleDateString("ru-RU",{day:"2-digit",month:"2-digit"});
  }

  async function renderChats() {
    clearPoller();loading("chats");
    try{state.conversations=(await api("/api/v1/chat/conversations")).conversations||[]}catch{state.conversations=[]}
    root.innerHTML='<main class="page chats-page">'+topbar("Сообщения")+
      '<div class="section-head chat-section-head"><div><div class="eyebrow">Взаимный интерес</div><h2>Диалоги</h2><p class="muted">Здесь только люди, с которыми интерес совпал.</p></div></div>'+
      (state.conversations.length
        ? '<section class="chat-list">'+state.conversations.map(conv=>{
            const p=conv.profile||{},last=conv.last_message;
            const score=conv.mutual_fit_score??conv.compatibility_score;
            return '<button class="chat-list-item" data-open-chat="'+conv.conversation_id+'">'+
              '<div class="chat-list-avatar">'+photo(p,"chat-avatar")+(conv.unread_count?'<i class="chat-unread-dot"></i>':'')+'</div>'+
              '<div class="chat-list-copy"><div class="chat-list-name"><b>'+esc(conv.other_display_name||p.display_name||"Профиль")+'</b>'+
                (score!=null?'<span>💜 '+esc(score)+'%</span>':'')+'</div>'+
                '<div class="chat-list-preview '+(conv.unread_count?"unread":"")+'">'+esc(last?.body||"Можно начать разговор")+'</div></div>'+
              '<div class="chat-list-meta"><time>'+esc(chatTime(last?.created_at))+'</time>'+(conv.unread_count?'<b>'+esc(conv.unread_count)+'</b>':'')+'</div>'+
            '</button>';
          }).join("")+'</section>'
        : '<section class="card empty"><div class="emoji">◌</div><h3>Пока нет диалогов</h3><p class="muted">После взаимного интереса здесь появится чат.</p><button class="primary" data-route="matches">Совпадения</button></section>')+
    '</main>'+nav("chats");
    bindCommon();
    document.querySelectorAll("[data-open-chat]").forEach(btn=>btn.onclick=()=>{
      const id=Number(btn.dataset.openChat);
      state.currentConversation=state.conversations.find(x=>Number(x.conversation_id)===id);
      state.currentMessages=[];
      state.messageFingerprint="";
      setRoute("chat");
    });
  }

  function messageHtml(m){
    const pending=m.pending?" pending":"";
    const failed=m.failed?" failed":"";
    const status=m.pending?"Отправляется…":m.failed?"Не отправлено":chatTime(m.created_at);
    return '<div class="message-row '+(m.is_mine?"mine":"theirs")+'" '+(m.client_local_id?'data-local-message="'+esc(m.client_local_id)+'"':'')+'>'+
      '<div class="bubble'+pending+failed+'"><div class="bubble-body">'+esc(m.body)+'</div>'+
      '<div class="bubble-meta">'+(m.is_mine&&!m.failed?'<span class="message-check">'+(m.pending?"○":"✓")+'</span>':'')+
      '<span>'+esc(status)+'</span></div></div></div>';
  }

  function renderMessageList(items,{forceBottom=false}={}){
    const box=pick("messages");if(!box)return;
    const nearBottom=box.scrollHeight-box.scrollTop-box.clientHeight<90;
    box.innerHTML=items.length
      ? items.map(messageHtml).join("")
      : '<div class="chat-empty-state"><div>♡</div><h3>Начните разговор</h3><p>Можно оттолкнуться от общего интереса или просто написать по-человечески.</p></div>';
    if(forceBottom||nearBottom) requestAnimationFrame(()=>{box.scrollTop=box.scrollHeight});
  }

  async function renderChat() {
    clearPoller();
    const conv=state.currentConversation;
    if(!conv)return setRoute("chats");
    const p=conv.profile||{};
    const score=conv.mutual_fit_score??conv.compatibility_score;
    state.currentMessages=state.currentMessages||[];
    state.sendingCount=0;
    root.innerHTML='<main class="chat-page">'+
      '<header class="chat-head-modern"><button class="icon-btn" id="chat-back">←</button>'+
        '<div class="chat-head-person">'+photo(p,"chat-head-avatar")+
          '<div><b>'+esc(p.display_name||conv.other_display_name||"MatchLab")+'</b>'+
          '<span>'+(score!=null?'💜 '+esc(score)+'% совместимость по анкете':'Взаимный интерес')+'</span></div></div>'+
        '<button class="icon-btn" id="chat-safety">⋯</button></header>'+
      '<div class="conversation-assist"><span>✨</span><div><b>Есть с чего начать</b><small>Спросите о том, что действительно зацепило вас в профиле. MatchLab не пишет сообщения вместо вас.</small></div></div>'+
      '<section id="messages" class="messages-modern"><div class="loader"></div></section>'+
      '<div class="chat-composer-wrap"><div class="chat-composer">'+
        '<textarea id="message-input" rows="1" maxlength="4000" placeholder="Сообщение…"></textarea>'+
        '<button class="chat-send" id="send-message" aria-label="Отправить">➤</button>'+
      '</div><div class="composer-hint">Enter — отправить · Shift+Enter — новая строка</div></div>'+
    '</main>'+nav("chats");
    bindCommon();
    pick("chat-back").onclick=()=>setRoute("chats");
    const safetyBtn=pick("chat-safety");
    if(safetyBtn)safetyBtn.onclick=()=>{
      const userId=Number(p.user_id||conv.other_user_id||0);
      if(userId)showSafetyModal(userId,p.display_name||conv.other_display_name||"этого пользователя");
    };
    const input=pick("message-input");
    const resize=()=>{input.style.height="auto";input.style.height=Math.min(input.scrollHeight,132)+"px"};
    input.addEventListener("input",resize);
    input.addEventListener("keydown",e=>{
      if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendCurrentMessage()}
    });
    pick("send-message").onclick=sendCurrentMessage;
    await loadMessages(true);
    state.poller=setInterval(()=>loadMessages(false),3000);
  }

  async function loadMessages(force=false) {
    const conv=state.currentConversation;
    if(!conv||(!force&&state.sendingCount>0))return;
    try{
      const data=await api("/api/v1/chat/messages?conversation_id="+conv.conversation_id+"&limit=100");
      const items=data.messages||[];
      const fingerprint=items.map(m=>m.id+":"+(m.read_at||"")).join("|");
      if(force||fingerprint!==state.messageFingerprint){
        state.currentMessages=items;
        state.messageFingerprint=fingerprint;
        renderMessageList(items,{forceBottom:force});
      }
      if(items.length){
        const last=items[items.length-1];
        if(!last.is_mine&&!last.read_at){
          post("/api/v1/chat/read",{conversation_id:conv.conversation_id,through_message_id:last.id}).catch(()=>{});
        }
      }
    }catch(e){}
  }

  async function sendCurrentMessage(){
    const input=pick("message-input");
    const text=input?.value.trim();
    const conv=state.currentConversation;
    if(!text||!conv)return;
    const clientId=crypto.randomUUID?crypto.randomUUID():Date.now()+"-"+Math.random();
    input.value="";input.style.height="auto";
    const optimistic={
      body:text,is_mine:true,pending:true,failed:false,
      client_local_id:clientId,created_at:new Date().toISOString()
    };
    state.currentMessages=[...(state.currentMessages||[]),optimistic];
    renderMessageList(state.currentMessages,{forceBottom:true});
    state.sendingCount=(state.sendingCount||0)+1;
    try{
      const result=await post("/api/v1/chat/messages",{
        conversation_id:conv.conversation_id,
        body:text,
        client_message_id:clientId
      });
      const saved=result.message||{};
      state.currentMessages=(state.currentMessages||[]).map(m=>
        m.client_local_id===clientId?{...saved,is_mine:true}:m
      );
      renderMessageList(state.currentMessages,{forceBottom:true});
      loadMessages(true);
    }catch(e){
      state.currentMessages=(state.currentMessages||[]).map(m=>
        m.client_local_id===clientId?{...m,pending:false,failed:true}:m
      );
      renderMessageList(state.currentMessages,{forceBottom:true});
    }finally{
      state.sendingCount=Math.max(0,(state.sendingCount||1)-1);
      input?.focus();
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
  const selectHtml = (id, value, options, placeholder="Выберите вариант") => {
    const selected=String(value??"");
    return '<select class="input" id="'+id+'" required>'+
      '<option value="" disabled '+(!selected?"selected":"")+'>'+esc(placeholder)+'</option>'+
      options.map(([v,l]) =>
        '<option value="'+esc(v)+'" '+(selected===String(v)?"selected":"")+'>'+esc(l)+'</option>'
      ).join("")+'</select>';
  };

  const IMPORTANCE_OPTIONS=[
    ["HARD","Обязательно"],
    ["IMPORTANT","Важно"],
    ["PREFERENCE","Желательно"],
    ["IGNORE","Не важно"],
  ];

  function importanceSelect(id,value){
    return selectHtml(id,value,IMPORTANCE_OPTIONS,"Насколько это важно?");
  }

  function requireFields(ids,message="Заполните все обязательные поля."){
    const missing=ids.some(id=>{
      const el=pick(id);
      return !el || String(el.value||"").trim()==="";
    });
    if(missing){onboardingStatus(message,true);return false}
    return true;
  }

  function verificationBanner(){
    const a=state.account||state.onboarding?.account||{};
    if(a.contact_verified || !a.email) return "";
    return '<div class="verification-banner"><div><b>✉ Подтвердите email</b><span>Анкету можно заполнять сейчас. Подтверждение понадобится перед активным подбором.</span></div><button type="button" class="secondary" id="resend-verification">Отправить письмо</button></div>';
  }

  function bindVerificationBanner(){
    const btn=pick("resend-verification");
    if(!btn)return;
    btn.onclick=async()=>{
      btn.disabled=true;btn.textContent="Отправляем…";
      try{
        const result=await post("/api/v1/auth/email/verification/request",{});
        btn.textContent=result.email_verified?"Email подтверждён ✓":(result.delivery==="email"?"Письмо отправлено ✓":"Отправка пока не настроена");
      }catch(e){btn.disabled=false;btn.textContent="Повторить отправку"}
    };
  }

  function firstIncompleteStep() {
    const c=state.onboarding?.completion||{};
    const item=ONBOARDING_STEPS.find(([key])=>!c[key]);
    return item ? item[0] : null;
  }

  function onboardingChrome(step, body) {
    const idx=Math.max(0,ONBOARDING_STEPS.findIndex(([key])=>key===step));
    const pct=Math.round((idx/ONBOARDING_STEPS.length)*100);
    return '<main class="onboarding-page">'+
      '<header class="onboarding-head"><div class="brand">Match<span>Lab</span></div>'+
      '<button class="ghost" id="onboarding-exit">Позже</button></header>'+
      '<section class="onboarding-shell">'+
        '<div class="onboarding-progress"><div class="progress-copy"><span>Шаг '+(idx+1)+' из '+ONBOARDING_STEPS.length+'</span><b>'+esc(ONBOARDING_STEPS[idx]?.[1]||"Анкета")+'</b></div>'+
        '<div class="progress-track"><i style="width:'+pct+'%"></i></div></div>'+
        verificationBanner()+body+
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

  const MARKET_OPTIONS=[
    ["KZ-ALA","Алматы"],
    ["KZ-AST","Астана"],
    ["KZ-CIT","Шымкент"],
    ["KZ-KGF","Караганда"],
    ["KZ-OTHER","Другой город"],
  ];
  const PARTNER_MARKET_OPTIONS=MARKET_OPTIONS.filter(([code])=>code!=="KZ-OTHER");

  function prefStored(values,key){
    return values?.[key]||{};
  }
  function prefFirst(values,key){
    const value=prefStored(values,key).value;
    return Array.isArray(value)&&value.length?value[0]:"";
  }
  function prefRangeValue(values,key,part){
    const value=prefStored(values,key).value;
    return value&&typeof value==="object"&&value[part]!=null?value[part]:"";
  }
  function preferenceEditorHtml(prefix,values,profile={}){
    const imp=(key)=>prefStored(values,key).importance||"";
    const gender=prefFirst(values,"gender")||( ["M","F","OTHER"].includes(profile.seek_gender)?profile.seek_gender:"");
    const card=(key,title,control,note="") =>
      '<article class="preference-editor-card" data-pref-card="'+key+'">'+
        '<div class="preference-editor-title"><b>'+esc(title)+'</b>'+(note?'<span>'+esc(note)+'</span>':'')+'</div>'+
        '<div class="preference-editor-controls"><label>Насколько это важно?'+importanceSelect(prefix+"-"+key+"-importance",imp(key))+'</label>'+control+'</div>'+
      '</article>';
    return '<div class="preference-editor">'+
      card("age","Возраст партнёра",
        '<div class="preference-value-grid"><label>От<input class="input" id="'+prefix+'-age-min" type="number" min="18" max="100" value="'+esc(prefRangeValue(values,"age","min"))+'" placeholder="18+"></label><label>До<input class="input" id="'+prefix+'-age-max" type="number" min="18" max="100" value="'+esc(prefRangeValue(values,"age","max"))+'" placeholder="Например, 35"></label></div>',
        "Диапазон не задаётся автоматически")+
      card("gender","Пол партнёра",
        '<label>Кого рассматриваете?'+selectHtml(prefix+"-gender",gender,[["F","Женщину"],["M","Мужчину"],["OTHER","Другой вариант"]],"Выберите вариант")+'</label>')+
      card("market","Город партнёра",
        '<label>Город'+selectHtml(prefix+"-market",prefFirst(values,"market"),PARTNER_MARKET_OPTIONS,"Выберите город")+'</label>',
        "Можно оставить неважным")+
      card("distance_km","Расстояние",
        '<label>Максимум, км<input class="input" id="'+prefix+'-distance_km-max" type="number" min="1" max="1000" value="'+esc(prefRangeValue(values,"distance_km","max"))+'" placeholder="Например, 50"></label>',
        "Ориентировочно между городами, без GPS-точности")+
      card("dating_goal","Цель знакомства",
        '<label>Цель'+selectHtml(prefix+"-dating_goal",prefFirst(values,"dating_goal"),[["SERIOUS","Серьёзные отношения"],["FAMILY","Семья"],["SEE","Посмотрим, как сложится"],["CHAT","Общение"],["UNKNOWN","Пока не определился(ась)"]])+'</label>')+
      card("children_status","Наличие детей",
        '<label>У партнёра'+selectHtml(prefix+"-children_status",prefFirst(values,"children_status"),[["NO_CHILDREN","Нет детей"],["HAS_CHILDREN","Есть дети"]])+'</label>')+
      card("children_plans","Планы на детей",
        '<label>Планы'+selectHtml(prefix+"-children_plans",prefFirst(values,"children_plans"),[["WANTS","Хочет детей"],["MAYBE","Возможно"],["DOES_NOT_WANT","Не хочет детей"]])+'</label>')+
      card("smoking","Курение",
        '<label>Курение'+selectHtml(prefix+"-smoking",prefFirst(values,"smoking"),[["NO","Не курит"],["RARE","Иногда"],["YES","Курит"]])+'</label>')+
      card("alcohol","Алкоголь",
        '<label>Алкоголь'+selectHtml(prefix+"-alcohol",prefFirst(values,"alcohol"),[["NO","Не употребляет"],["RARE","Редко"],["MODERATE","Умеренно"],["YES","Регулярно"]])+'</label>')+
      card("lifestyle","Образ жизни",
        '<label>Ритм'+selectHtml(prefix+"-lifestyle",prefFirst(values,"lifestyle"),[["CALM","Спокойный"],["BALANCED","Сбалансированный"],["ACTIVE","Активный"],["VERY_ACTIVE","Очень активный"]])+'</label>')+
      card("height","Рост",
        '<div class="preference-value-grid"><label>От, см<input class="input" id="'+prefix+'-height-min" type="number" min="100" max="250" value="'+esc(prefRangeValue(values,"height","min"))+'" placeholder="Например, 160"></label><label>До, см<input class="input" id="'+prefix+'-height-max" type="number" min="100" max="250" value="'+esc(prefRangeValue(values,"height","max"))+'" placeholder="Например, 190"></label></div>')+
      card("religion","Религия",
        '<label>Значение<input class="input" id="'+prefix+'-religion-text" maxlength="120" value="'+esc(prefFirst(values,"religion"))+'" placeholder="Например, ислам"></label>')+
      card("nationality","Национальность",
        '<label>Значение<input class="input" id="'+prefix+'-nationality-text" maxlength="120" value="'+esc(prefFirst(values,"nationality"))+'" placeholder="Самоопределение"></label>')+
    '</div>';
  }

  function bindPreferenceImportance(prefix){
    document.querySelectorAll('[id^="'+prefix+'-"][id$="-importance"]').forEach(select=>{
      const key=select.id.slice((prefix+"-").length,-"-importance".length);
      const card=document.querySelector('[data-pref-card="'+key+'"]');
      const refresh=()=>{
        const ignored=select.value==="IGNORE";
        card?.querySelectorAll("input,select").forEach(el=>{
          if(el===select)return;
          el.disabled=ignored;
          if(ignored) el.setCustomValidity("");
        });
        card?.classList.toggle("ignored",ignored);
      };
      select.onchange=refresh;refresh();
    });
  }

  function collectPreferences(prefix){
    const keys=["age","gender","market","distance_km","dating_goal","children_status","children_plans","smoking","alcohol","lifestyle","height","religion","nationality"];
    const out={};
    for(const key of keys){
      const importance=pick(prefix+"-"+key+"-importance")?.value||"";
      if(!importance) throw new Error("Укажите важность для каждого критерия.");
      if(importance==="IGNORE"){out[key]={importance:"IGNORE"};continue}

      let value=null;
      if(key==="age"){
        const min=Number(pick(prefix+"-age-min").value),max=Number(pick(prefix+"-age-max").value);
        if(!Number.isInteger(min)||!Number.isInteger(max)||min<18||max>100||max<min)
          throw new Error("Проверьте возраст партнёра: от 18 до 100, «до» не меньше «от».");
        value={min,max};
      }else if(key==="height"){
        const min=Number(pick(prefix+"-height-min").value),max=Number(pick(prefix+"-height-max").value);
        if(!Number.isInteger(min)||!Number.isInteger(max)||min<100||max>250||max<min)
          throw new Error("Проверьте диапазон роста.");
        value={min,max};
      }else if(key==="distance_km"){
        const max=Number(pick(prefix+"-distance_km-max").value);
        if(!Number.isFinite(max)||max<1||max>1000) throw new Error("Укажите расстояние от 1 до 1000 км.");
        value={max};
      }else if(key==="religion"||key==="nationality"){
        const textValue=pick(prefix+"-"+key+"-text").value.trim();
        if(!textValue) throw new Error("Заполните «"+(key==="religion"?"Религия":"Национальность")+"» или выберите «Не важно».");
        value=[textValue];
      }else{
        const el=pick(prefix+"-"+key);
        const selected=el?.value||"";
        if(!selected) throw new Error("Выберите значение критерия или укажите «Не важно».");
        value=[selected];
      }
      out[key]={importance,value};
    }
    return out;
  }

  async function renderOnboarding(force=false) {
    clearPoller();
    if(force||!state.onboarding) await loadMe();
    trackClient("ONBOARDING_STARTED");
    const step=firstIncompleteStep();
    const p=state.onboarding?.profile||state.profile?.profile||{};

    if(!step) return renderWaitlistCompletion();
    if(step==="questionnaire") return renderQuestionnaireStep();

    let body="";
    if(step==="basic"){
      const cityOther=p.market_code==="KZ-OTHER";
      body='<div class="onboarding-card"><div class="eyebrow">Начнём с главного</div><h1>Расскажите немного о себе</h1><p class="muted">Ничего не выбираем за вас — каждое обязательное поле нужно заполнить самостоятельно.</p>'+
        '<div class="form-stack">'+
        '<label class="field-label">Имя<input class="input" id="ob-name" value="'+esc(p.display_name||"")+'" placeholder="Как к вам обращаться"></label>'+
        '<label class="field-label">Дата рождения<input class="input" id="ob-dob" type="date" value="'+esc(p.dob||"")+'"></label>'+
        '<div class="form-grid">'+
          '<label class="field-label">Ваш пол'+selectHtml("ob-gender",p.gender,[["M","Мужчина"],["F","Женщина"],["OTHER","Другое"]])+'</label>'+
          '<label class="field-label">Кого вы рассматриваете'+selectHtml("ob-seek",p.seek_gender,[["F","Женщин"],["M","Мужчин"],["OTHER","Другой вариант"],["ANY","Пол не важен"]])+'</label>'+
          '<label class="field-label">В каком городе вы сейчас живёте?'+selectHtml("ob-market",p.market_code,MARKET_OPTIONS,"Выберите город")+'</label>'+
          '<label class="field-label" id="ob-city-other-wrap" '+(cityOther?"":"hidden")+'>Ваш город<input class="input" id="ob-city-other" maxlength="120" value="'+esc(cityOther?(p.city||""):"")+'" placeholder="Введите город"></label>'+
        '</div>'+
        '<button class="primary full" id="ob-save-basic">Продолжить →</button></div></div>';
    } else if(step==="relationship"){
      body='<div class="onboarding-card"><div class="eyebrow">Статус</div><h1>Вы сейчас в отношениях?</h1><p class="muted">Выберите ответ сами — MatchLab не подставляет его автоматически.</p>'+
        '<div class="choice-grid" id="relationship-choice">'+
          '<button class="choice-card" data-rel="no"><b>Нет</b><span>Я свободен(на)</span></button>'+
          '<button class="choice-card" data-rel="yes"><b>Да</b><span>Сейчас я в отношениях</span></button>'+
        '</div>'+
        '<div id="openness-block" class="form-stack" hidden><div class="field-label">Насколько вы открыты к знакомствам?</div>'+
          selectHtml("ob-openness","",[["ACTIVE","Активно хочу знакомиться"],["OPEN","Открыт(а), если встречу подходящего человека"],["UNSURE","Пока не уверен(а)"],["NO","Не хочу знакомств"]])+
          '<button class="primary full" id="ob-save-relationship" disabled>Продолжить →</button></div></div>';
    } else if(step==="readiness"){
      body='<div class="onboarding-card"><div class="eyebrow">Готовность</div><h1>Как вам комфортнее начинать знакомство?</h1><p class="muted">Оба ответа обязательны и начинаются без выбранного варианта.</p>'+
        '<div class="form-stack">'+
        '<label class="field-label">Готовность общаться в чате'+selectHtml("ob-chat",p.readiness_chat,[["YES","Да, готов(а)"],["RATHER_YES","Скорее да"],["LOOK_ONLY","Пока хочу присмотреться"]])+'</label>'+
        '<label class="field-label">Готовность встретиться офлайн'+selectHtml("ob-offline",p.readiness_offline,[["YES","Да"],["MAYBE","Возможно, после общения"],["NO","Пока нет"]])+'</label>'+
        '<button class="primary full" id="ob-save-readiness">Продолжить →</button></div></div>';
    } else if(step==="details"){
      body='<div class="onboarding-card wide"><div class="eyebrow">О вас</div><h1>Что важно знать для совместимости?</h1><p class="muted">Обязательные варианты не заполнены заранее.</p>'+
        '<div class="form-grid">'+
          '<label class="field-label">Рост, см<input class="input" id="ob-height" type="number" min="100" max="250" value="'+esc(p.height||"")+'" placeholder="Например, 175"></label>'+
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
      const values=state.onboarding?.preferences||{};
      body='<div class="onboarding-card wide preference-onboarding"><div class="eyebrow">Ваш человек</div><h1>Кого вы хотите встретить?</h1><p class="muted">Для каждого критерия сначала решите, насколько он важен. «Не важно» полностью исключает критерий из фильтра и процента предпочтений.</p>'+
        preferenceEditorHtml("ob-pref",values,p)+
        '<button class="primary full" id="ob-save-preferences">Сохранить критерии →</button></div>';
    } else {
      const photos=state.onboarding?.photos||{};
      body='<div class="onboarding-card"><div class="eyebrow">Последний шаг</div><h1>Добавьте фотографии</h1><p class="muted">Нужно минимум 2 одобренных фото. Первое станет главным.</p>'+
        '<div class="photo-progress-big"><b>'+esc(photos.approved||0)+'/2</b><span>одобрено</span></div>'+
        '<label class="photo-upload"><input type="file" id="ob-photo" accept="image/jpeg,image/png,image/webp"><span>＋ Добавить фото</span></label>'+
        '<p class="muted small">После загрузки фото отправляется на модерацию. Пока оно проверяется, можно пользоваться приложением.</p>'+
        '<button class="secondary full" id="ob-finish-later">Перейти в приложение</button></div>';
    }

    root.innerHTML=onboardingChrome(step,body);
    bindVerificationBanner();
    pick("onboarding-exit").onclick=()=>setRoute("home");

    if(step==="basic"){
      const market=pick("ob-market"),otherWrap=pick("ob-city-other-wrap");
      market.onchange=()=>{otherWrap.hidden=market.value!=="KZ-OTHER"};
      pick("ob-save-basic").onclick=async()=>{
        if(!requireFields(["ob-name","ob-dob","ob-gender","ob-seek","ob-market"]))return;
        if(market.value==="KZ-OTHER"&&!pick("ob-city-other").value.trim())return onboardingStatus("Введите ваш город.",true);
        try{
          onboardingStatus("Сохраняем…");
          await post("/api/v1/profile/basic",{
            display_name:pick("ob-name").value.trim(),
            dob:pick("ob-dob").value,
            gender:pick("ob-gender").value,
            seek_gender:pick("ob-seek").value,
            market_code:market.value,
            city_text:market.value==="KZ-OTHER"?pick("ob-city-other").value.trim():"",
            preferred_locale:"ru-KZ"
          });
          await loadMe();renderOnboarding();
        }catch(e){onboardingStatus("Проверьте данные: "+e.message,true)}
      };
    } else if(step==="relationship"){
      let selectedRelationship=null;
      document.querySelectorAll("[data-rel]").forEach(btn=>btn.onclick=()=>{
        selectedRelationship=btn.dataset.rel==="yes";
        document.querySelectorAll("[data-rel]").forEach(x=>x.classList.toggle("selected",x===btn));
        pick("openness-block").hidden=false;
        if(selectedRelationship){
          pick("ob-openness").value="";
          pick("ob-openness").disabled=true;
        }else{
          pick("ob-openness").disabled=false;
        }
        pick("ob-save-relationship").disabled=false;
      });
      pick("ob-save-relationship").onclick=async()=>{
        if(selectedRelationship===null)return onboardingStatus("Выберите, находитесь ли вы сейчас в отношениях.",true);
        if(!selectedRelationship&&!pick("ob-openness").value)return onboardingStatus("Укажите, насколько вы открыты к знакомствам.",true);
        try{
          await post("/api/v1/profile/relationship",{in_relationship:selectedRelationship,openness:selectedRelationship?"NO":pick("ob-openness").value});
          await loadMe();renderOnboarding();
        }catch(e){onboardingStatus(e.message,true)}
      };
    } else if(step==="readiness"){
      pick("ob-save-readiness").onclick=async()=>{
        if(!requireFields(["ob-chat","ob-offline"]))return;
        try{
          await post("/api/v1/profile/readiness",{chat:pick("ob-chat").value,offline:pick("ob-offline").value});
          await loadMe();renderOnboarding();
        }catch(e){onboardingStatus(e.message,true)}
      };
    } else if(step==="details"){
      pick("ob-save-details").onclick=async()=>{
        if(!requireFields(["ob-height","ob-goal","ob-children","ob-children-plans","ob-smoking","ob-alcohol","ob-lifestyle"]))return;
        const height=Number(pick("ob-height").value);
        if(!Number.isInteger(height)||height<100||height>250)return onboardingStatus("Укажите корректный рост от 100 до 250 см.",true);
        try{
          await post("/api/v1/profile/details",{
            height,dating_goal:pick("ob-goal").value,children_status:pick("ob-children").value,
            children_plans:pick("ob-children-plans").value,smoking:pick("ob-smoking").value,
            alcohol:pick("ob-alcohol").value,lifestyle:pick("ob-lifestyle").value,
            bio:pick("ob-bio").value.trim(),religion:pick("ob-religion").value.trim(),nationality:""
          });
          await loadMe();renderOnboarding();
        }catch(e){onboardingStatus("Не удалось сохранить: "+e.message,true)}
      };
    } else if(step==="partner_preferences"){
      bindPreferenceImportance("ob-pref");
      pick("ob-save-preferences").onclick=async()=>{
        try{
          const prefs=collectPreferences("ob-pref");
          onboardingStatus("Сохраняем критерии…");
          await post("/api/v1/preferences",{preferences:prefs});
          await loadMe();renderOnboarding();
        }catch(e){onboardingStatus(e.message||"Не удалось сохранить критерии.",true)}
      };
    } else {
      pick("ob-finish-later").onclick=()=>setRoute("home");
      pick("ob-photo").onchange=async(e)=>{
        const file=e.target.files?.[0];if(!file)return;
        if(file.size>12*1024*1024)return onboardingStatus("Фото слишком большое. Максимум 12 МБ.",true);
        try{
          onboardingStatus("Загружаем фото…");
          const prep=await post("/api/v1/photos/prepare",{mime:file.type});
          const headers=prep.upload?.headers||{"Content-Type":file.type};
          const up=await fetch(prep.upload.url,{method:"PUT",headers,body:file});
          if(!up.ok)throw new Error("upload_failed");
          await post("/api/v1/photos/finalize",{ticket:prep.ticket});
          await loadMe();renderOnboarding();
        }catch(err){onboardingStatus("Не удалось загрузить фото: "+err.message,true)}
      };
    }
  }


  async function renderEmailVerification(){
    clearPoller();
    const raw=location.hash.includes("?")?location.hash.split("?")[1]:"";
    const params=new URLSearchParams(raw);
    const email=params.get("email")||"";
    const token=params.get("challenge")||params.get("token")||"";
    root.innerHTML='<main class="onboarding-page verification-page"><section class="onboarding-shell"><div class="onboarding-card waitlist-card">'+
      '<div class="waitlist-mark">✉</div><div class="eyebrow">Подтверждение email</div>'+
      '<h1 id="verify-email-title">Проверяем ссылку…</h1>'+
      '<p class="muted" id="verify-email-copy">Это займёт несколько секунд.</p>'+
      '<button class="primary full" id="verify-email-continue" hidden>Продолжить →</button>'+
    '</div></section></main>';
    const title=pick("verify-email-title"),copy=pick("verify-email-copy"),btn=pick("verify-email-continue");
    if(!email||!token){
      title.textContent="Ссылка неполная";
      copy.textContent="Запросите новое письмо подтверждения в профиле.";
      btn.hidden=false;btn.textContent="Перейти к профилю";btn.onclick=()=>setRoute("profile");return;
    }
    try{
      await post("/api/v1/auth/email/verify",{email,token});
      title.textContent="Email подтверждён ✓";
      copy.textContent="Теперь этот способ связи подтверждён, и профиль может участвовать в подборе после выполнения остальных условий.";
      btn.hidden=false;btn.onclick=async()=>{await loadMe();setRoute("home")};
    }catch(e){
      title.textContent="Ссылка недействительна или истекла";
      copy.textContent="Запросите новое письмо подтверждения. Старые и уже использованные ссылки не работают.";
      btn.hidden=false;btn.textContent="Перейти к профилю";btn.onclick=()=>setRoute("profile");
    }
  }

  async function renderWaitlistCompletion(){
    clearPoller();
    if(!state.onboarding) await loadMe();
    const p=state.onboarding?.profile||state.profile?.profile||{};
    let waitlist=state.onboarding?.waitlist||{};
    try{waitlist=await api("/api/v1/waitlist/status")}catch{}
    const ready=!!waitlist.ready;
    const labels={
      WAITLIST:"Вы в листе ожидания",
      CITY_WAITLIST:"Ваш город в листе ожидания",
      MATCHING_ACTIVE:"Подбор уже открыт",
      CONTACT_VERIFICATION_REQUIRED:"Осталось подтвердить контакт",
      READY:"Профиль готов",
    };
    const stateLabel=labels[waitlist.state]||"Профиль сохранён";
    const city=waitlist.market_name||p.city||"Не указан";
    root.innerHTML='<main class="onboarding-page waitlist-page">'+
      '<header class="onboarding-head"><div class="brand">Match<span>Lab</span></div><button class="ghost" id="waitlist-profile">Профиль</button></header>'+
      '<section class="onboarding-shell">'+verificationBanner()+'<div class="onboarding-card waitlist-card">'+
        '<div class="waitlist-mark">'+(ready?"✓":"♡")+'</div>'+
        '<div class="eyebrow">Анкета завершена</div>'+
        '<h1>'+esc(stateLabel)+(p.display_name?" — "+esc(p.display_name):"")+'</h1>'+
        '<p class="muted">'+esc(waitlist.message||"Ваш профиль сохранён. Мы сообщим, когда подбор станет доступен.")+'</p>'+
        '<div class="waitlist-summary">'+
          '<div><b>100%</b><span>анкета заполнена</span></div>'+
          '<div><b>'+esc(city)+'</b><span>ваш город</span></div>'+
          '<div><b>'+esc(waitlist.contact_verified?"Контакт подтверждён":"Нужно подтверждение")+'</b><span>готовность к подбору</span></div>'+
        '</div>'+
        '<button class="primary full" id="waitlist-home">Перейти в приложение →</button>'+
        '<button class="secondary full" id="waitlist-edit">Изменить профиль</button>'+
      '</div></section></main>';
    bindVerificationBanner();
    pick("waitlist-home").onclick=()=>setRoute("home");
    pick("waitlist-edit").onclick=()=>setRoute("profile");
    pick("waitlist-profile").onclick=()=>setRoute("profile");
  }

  async function renderQuestionnaireStep(){
    let q;
    try{q=await api("/api/v1/questionnaire/adaptive");}
    catch(e){return root.innerHTML=onboardingChrome("questionnaire",'<div class="onboarding-card"><h1>Анкета пока недоступна</h1><p class="muted">'+esc(e.message)+'</p></div>')}

    if(q.complete){
      await loadMe();
      return renderOnboarding();
    }
    const progress=q.progress||{};
    const question=q.question||{};
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
        onboardingStatus("Не удалось сохранить ответ: "+e.message,true);
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
    let photoData={photos:[]};
    try{photoData=await api("/api/v1/photos");}catch{}
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

    root.innerHTML='<main class="page profile-page">'+topbar("Профиль")+
      '<section class="card profile-overview">'+
        '<div class="profile-overview-main">'+photoHtml+
          '<div><div class="eyebrow">Ваш профиль</div><h1>'+esc(p.display_name||"MatchLab")+(age?", "+age:"")+'</h1>'+
          '<p class="muted">'+esc(p.city||"Алматы")+'</p>'+
          '<span class="profile-state">'+esc(statusLabels[p.relationship_status]||"Настройте статус знакомств")+'</span></div>'+
        '</div>'+
        '<div class="profile-completion"><div class="profile-completion-copy"><b>Профиль заполнен на '+pct+'%</b><span>'+esc(waitlist.message||"Заполненный профиль помогает подобрать более совместимых людей.")+'</span></div>'+
        '<div class="progress-track big"><i style="width:'+pct+'%"></i></div></div>'+
        (pct<100?'<button class="primary full" data-route="onboarding">Продолжить анкету →</button>':
          '<button class="secondary full" data-route="onboarding">Статус листа ожидания</button>')+
      '</section>'+
      '<section class="profile-menu-section"><div class="profile-menu-heading"><span>Профиль и подбор</span><small>Настройте себя и то, кого хотите встретить</small></div><div class="profile-menu">'+
        profileMenuRow("👤","Редактировать профиль","Имя, о себе, образ жизни","profile-edit")+
        profileMenuRow("🎯","Кого я ищу","Возраст, цели и важные критерии","preferences")+
        profileMenuRow("🧠","Моя совместимость","Ваши приоритеты по анкете","compatibility",c.questionnaire?"Готово":"")+
        profileMenuRow("📷","Мои фотографии","Главное фото и порядок","photos",(photoData.progress?.approved||0)+"/2")+
      '</div></section>'+
      '<section class="profile-menu-section"><div class="profile-menu-heading"><span>Аккаунт и безопасность</span><small>Статус, уведомления и управление аккаунтом</small></div><div class="profile-menu">'+
        profileMenuRow("❤️","Статус знакомств","Активность и пауза","dating-status")+
        profileMenuRow("🔔","Уведомления","Push и разрешения","notifications")+
        profileMenuRow("🛡","Безопасность","Блокировки и жалобы","safety")+
        profileMenuRow("⚙️","Настройки аккаунта","Вход, данные и удаление","settings")+
      '</div></section>'+
    '</main>'+nav("profile");
    bindCommon();
  }

  async function renderProfileEdit(){
    clearPoller();loading("profile");await loadMe();
    const p=state.profile?.profile||{};
    const otherCity=p.market_code==="KZ-OTHER";
    root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Редактировать профиль")+
      '<section class="card settings-card"><div class="section-head compact"><div><div class="eyebrow">Основное</div><h2>О вас</h2></div></div>'+
      '<div class="form-grid">'+
        '<label class="field-label">Имя<input class="input" id="edit-name" maxlength="80" value="'+esc(p.display_name||"")+'"></label>'+
        '<label class="field-label">Дата рождения<input class="input" id="edit-dob" type="date" value="'+esc(p.dob||"")+'"></label>'+
        '<label class="field-label">Ваш пол'+selectHtml("edit-gender",p.gender,[["M","Мужчина"],["F","Женщина"],["OTHER","Другое"]])+'</label>'+
        '<label class="field-label">Кого рассматриваете'+selectHtml("edit-seek",p.seek_gender,[["F","Женщин"],["M","Мужчин"],["OTHER","Другой вариант"],["ANY","Пол не важен"]])+'</label>'+
        '<label class="field-label">Город'+selectHtml("edit-market",p.market_code,MARKET_OPTIONS,"Выберите город")+'</label>'+
        '<label class="field-label" id="edit-city-other-wrap" '+(otherCity?"":"hidden")+'>Ваш город<input class="input" id="edit-city-other" maxlength="120" value="'+esc(otherCity?(p.city||""):"")+'"></label>'+
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
    const market=pick("edit-market"),otherWrap=pick("edit-city-other-wrap");
    market.onchange=()=>{otherWrap.hidden=market.value!=="KZ-OTHER"};
    pick("save-profile-edit").onclick=async()=>{
      const required=["edit-name","edit-dob","edit-gender","edit-seek","edit-market","edit-height","edit-goal","edit-children","edit-children-plans","edit-smoking","edit-alcohol","edit-lifestyle"];
      if(required.some(id=>!String(pick(id)?.value||"").trim()))return inlineStatus("profile-edit-status","Заполните все обязательные поля.",true);
      if(market.value==="KZ-OTHER"&&!pick("edit-city-other").value.trim())return inlineStatus("profile-edit-status","Введите ваш город.",true);
      const height=Number(pick("edit-height").value);
      if(!Number.isInteger(height)||height<100||height>250)return inlineStatus("profile-edit-status","Укажите корректный рост.",true);
      const btn=pick("save-profile-edit");btn.disabled=true;inlineStatus("profile-edit-status","Сохраняем…");
      try{
        await post("/api/v1/profile/basic",{
          display_name:pick("edit-name").value.trim(),dob:pick("edit-dob").value,
          gender:pick("edit-gender").value,seek_gender:pick("edit-seek").value,
          market_code:market.value,city_text:market.value==="KZ-OTHER"?pick("edit-city-other").value.trim():"",
          preferred_locale:p.preferred_locale||"ru-KZ"
        });
        await post("/api/v1/profile/details",{
          height,dating_goal:pick("edit-goal").value,children_status:pick("edit-children").value,
          children_plans:pick("edit-children-plans").value,smoking:pick("edit-smoking").value,
          alcohol:pick("edit-alcohol").value,lifestyle:pick("edit-lifestyle").value,
          bio:pick("edit-bio").value.trim(),religion:pick("edit-religion").value.trim(),
          nationality:p.nationality||""
        });
        await loadMe();inlineStatus("profile-edit-status","Изменения сохранены ✓");btn.disabled=false;
      }catch(e){btn.disabled=false;inlineStatus("profile-edit-status","Не удалось сохранить: "+e.message,true)}
    };
  }

  async function renderPreferences(){
    clearPoller();loading("profile");await loadMe();
    let data={values:{}};
    try{data=await api("/api/v1/preferences")}catch{}
    const values=data.values||{};
    const p=state.profile?.profile||{};
    root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Кого я ищу")+
      '<section class="card settings-card preference-settings"><div class="eyebrow">Критерии партнёра</div><h2>Что для вас действительно важно?</h2>'+
      '<p class="muted">У каждого критерия своя важность. «Не важно» полностью исключает его из фильтра и расчёта предпочтений.</p>'+
      preferenceEditorHtml("pref-edit",values,p)+
      '<button class="primary full" id="save-preferences-edit">Сохранить критерии</button>'+
      '<div id="preferences-status" class="status" hidden></div></section>'+
    '</main>'+nav("profile");
    bindCommon();bindPreferenceImportance("pref-edit");
    pick("profile-back").onclick=()=>setRoute("profile");
    pick("save-preferences-edit").onclick=async()=>{
      const btn=pick("save-preferences-edit");
      try{
        const prefs=collectPreferences("pref-edit");
        btn.disabled=true;inlineStatus("preferences-status","Сохраняем…");
        await post("/api/v1/preferences",{preferences:prefs});
        await loadMe();
        btn.disabled=false;inlineStatus("preferences-status","Критерии сохранены ✓");
      }catch(e){btn.disabled=false;inlineStatus("preferences-status",e.message||"Не удалось сохранить.",true)}
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
    let data={photos:[],progress:{}};
    try{data=await api("/api/v1/photos");}catch(e){
      root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Мои фотографии")+'<section class="card empty"><h3>Фото пока недоступны</h3><p class="muted">'+esc(e.message)+'</p></section></main>'+nav("profile");
      bindCommon();document.getElementById("profile-back").onclick=()=>setRoute("profile");return;
    }
    const items=(data.photos||[]).slice().sort((a,b)=>(a.sort_order||0)-(b.sort_order||0));
    const statusLabel={APPROVED:"Одобрено",PENDING:"На модерации",REJECTED:"Отклонено"};
    root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Мои фотографии")+
      '<section class="card settings-card"><div class="section-head compact"><div><div class="eyebrow">Фотографии</div><h2>'+(data.progress?.approved||0)+'/2 одобрено</h2></div></div>'+
      '<p class="muted">Первое главное фото показывается в подборе. Можно добавить до лимита, удалить или поменять порядок.</p>'+
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
        '<label class="photo-upload photo-manager-upload"><input type="file" id="profile-photo-upload" accept="image/jpeg,image/png,image/webp"><span>＋ Добавить фото</span><small>JPG, PNG или WEBP · до 12 МБ</small></label>'+
      '</div><div id="photos-status" class="status" hidden></div></section>'+
    '</main>'+nav("profile");
    bindCommon();
    document.getElementById("profile-back").onclick=()=>setRoute("profile");
    document.querySelectorAll("[data-photo-main]").forEach(btn=>btn.onclick=async()=>{
      try{await post("/api/v1/photos/main",{photo_id:Number(btn.dataset.photoMain)});await renderPhotos()}catch(e){inlineStatus("photos-status","Не удалось выбрать главное фото: "+e.message,true)}
    });
    document.querySelectorAll("[data-photo-delete]").forEach(btn=>btn.onclick=async()=>{
      if(!confirm("Удалить эту фотографию?"))return;
      try{await post("/api/v1/photos/delete",{photo_id:Number(btn.dataset.photoDelete)});await renderPhotos()}catch(e){inlineStatus("photos-status","Не удалось удалить фото: "+e.message,true)}
    });
    document.querySelectorAll("[data-photo-move]").forEach(btn=>btn.onclick=async()=>{
      const id=Number(btn.dataset.photoMove),dir=Number(btn.dataset.dir);
      const ids=items.map(x=>Number(x.id));
      const index=ids.indexOf(id),next=index+dir;
      if(index<0||next<0||next>=ids.length)return;
      [ids[index],ids[next]]=[ids[next],ids[index]];
      try{await post("/api/v1/photos/reorder",{photo_ids:ids});await renderPhotos()}catch(e){inlineStatus("photos-status","Не удалось изменить порядок: "+e.message,true)}
    });
    document.getElementById("profile-photo-upload").onchange=async e=>{
      const f=e.target.files?.[0];if(!f)return;
      if(f.size>12*1024*1024)return inlineStatus("photos-status","Фото слишком большое. Максимум 12 МБ.",true);
      inlineStatus("photos-status","Загружаем фото…");
      try{
        const prep=await post("/api/v1/photos/prepare",{mime:f.type});
        const headers=prep.upload?.headers||{"Content-Type":f.type};
        const up=await fetch(prep.upload.url,{method:"PUT",headers,body:f});
        if(!up.ok)throw new Error("upload_failed");
        await post("/api/v1/photos/finalize",{ticket:prep.ticket});
        await renderPhotos();
      }catch(err){inlineStatus("photos-status","Не удалось загрузить фото: "+err.message,true)}
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
      }catch(e){btn.disabled=false;inlineStatus("dating-status-message","Не удалось сохранить: "+e.message,true)}
    };
  }

  async function renderNotifications(){
    clearPoller(); loading("profile");
    let devices={devices:[]};
    try{devices=await api("/api/v1/push/devices");}catch{}
    const permission=("Notification" in window)?Notification.permission:"unsupported";
    const permissionLabels={granted:"Разрешены",denied:"Запрещены",default:"Не выбрано",unsupported:"Не поддерживаются"};
    root.innerHTML='<main class="page profile-subpage">'+profileBackHeader("Уведомления")+
      '<section class="card settings-card"><div class="eyebrow">Уведомления</div><h2>Не пропускайте важные совпадения</h2>'+
      '<div class="setting-line"><div><b>Разрешение браузера</b><span class="muted">'+esc(permissionLabels[permission]||permission)+'</span></div>'+
      (permission==="default"?'<button class="secondary" id="request-browser-notifications">Разрешить</button>':'')+'</div>'+
      '<div class="setting-line"><div><b>Push-устройства</b><span class="muted">Подключено: '+esc((devices.devices||[]).filter(x=>x.enabled).length)+'</span></div><span class="tag">FCM</span></div>'+
      '<div class="insight-box"><b>Что уже работает</b><p>Backend умеет регистрировать push-устройства и доставлять системные уведомления. Для web-push нужна отдельная подписка браузера — её подключим после основного P0 UX.</p></div>'+
      '</section></main>'+nav("profile");
    bindCommon();document.getElementById("profile-back").onclick=()=>setRoute("profile");
    const btn=document.getElementById("request-browser-notifications");
    if(btn)btn.onclick=async()=>{
      try{await Notification.requestPermission();await renderNotifications()}catch{}
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
      try{await post("/api/v1/safety/unblock",{user_id:Number(btn.dataset.unblockUser)});await renderSafety()}catch(e){inlineStatus("safety-page-status","Не удалось разблокировать: "+e.message,true)}
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
      '<button class="settings-link button-link" id="export-data"><b>Скачать мои данные</b><span>JSON ↓</span></button>'+
      '</section>'+
      '<section class="card settings-card danger-zone"><div class="eyebrow">Опасная зона</div><h2>Удаление аккаунта</h2>'+
      '<p class="muted">Для защиты от случайного удаления введите <b>DELETE</b>. После запроса аккаунт станет недоступен, а удаление пройдёт по политике хранения данных.</p>'+
      '<input class="input" id="delete-confirmation" placeholder="Введите DELETE" autocomplete="off">'+
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
      }catch(e){inlineStatus("settings-status","Не удалось подготовить данные: "+e.message,true)}
      btn.disabled=false;
    };
    const deletionInput=document.getElementById("delete-confirmation");
    const deletionBtn=document.getElementById("delete-account");
    deletionInput.oninput=()=>{deletionBtn.disabled=deletionInput.value.trim()!=="DELETE"};
    deletionBtn.onclick=async()=>{
      if(deletionInput.value.trim()!=="DELETE")return;
      if(!confirm("Удалить аккаунт MatchLab? Это действие запускает процедуру удаления данных."))return;
      deletionBtn.disabled=true;
      try{
        await post("/api/v1/privacy/delete",{confirmation:"DELETE"});
        state.authenticated=false;state.profile=null;state.onboarding=null;
        location.hash="";
        renderAuth("login");
        status("Запрос на удаление аккаунта принят.");
      }catch(e){deletionBtn.disabled=false;inlineStatus("settings-status","Не удалось удалить аккаунт: "+e.message,true)}
    };
    document.getElementById("settings-logout").onclick=async()=>{
      try{await post("/api/v1/auth/logout",{});}catch{}
      state.authenticated=false;state.profile=null;state.onboarding=null;location.hash="";renderAuth("login");
    };
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
    captureAttribution();
    trackAnonymous("LANDING_VIEW");
    if("serviceWorker" in navigator) navigator.serviceWorker.register("/web/sw.js").catch(()=>{});
    await renderRoute();
  });
})();