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

  function renderAuth(mode="login") {
    clearPoller();
    const register = mode === "register";
    root.innerHTML = '<main class="auth-screen">' +
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
        '<p class="auth-legal muted" style="font-size:11px;text-align:center;margin:13px 18px 0">18+. Профиль не публикуется до завершения анкеты и проверки фотографий.</p>' +
      '</div>' +
    '</main>';
    document.getElementById("auth-login-tab").onclick = () => renderAuth("login");
    document.getElementById("auth-register-tab").onclick = () => renderAuth("register");
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
    '</div>';
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
        await post("/api/v1/auth/phone/register/verify",{phone,password,code});
        await afterAuth();
      } catch(e) { status("Не удалось зарегистрироваться: " + e.message, true); }
    };
    document.getElementById("reg-email-finish").onclick = async () => {
      const email = document.getElementById("reg-email").value.trim();
      const password = document.getElementById("reg-email-password").value;
      if (!email) return status("Введите email.", true);
      if (password.length < 10) return status("Пароль — минимум 10 символов.", true);
      status("Создаём аккаунт…");
      try {
        await post("/api/v1/auth/register",{email,password});
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
    const labels = {
      values:"Ценности",
      relationship:"Отношения",
      communication:"Общение",
      lifestyle:"Образ жизни",
      personality:"Характер",
      intimacy:"Близость",
      conflict:"Конфликты",
    };
    return entries.map(([key,value]) =>
      '<span class="tag">' + esc(labels[key] || key) + ' · ' + esc(value) + '%</span>'
    ).join("") || '<span class="tag">Совместимые критерии</span>';
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
        '<div class="candidate-title"><div><h2>' + esc(name + age) + '</h2><div class="muted">' + esc(c.city || "") + '</div></div></div>' +
        '<div class="tags">' + compatibilityReason(c) + '</div>' +
        (c.bio ? '<p>' + esc(c.bio) + '</p>' : '') +
        '<div class="actions">' +
          '<button class="secondary" data-candidate-detail="' + c.user_id + '">Подробнее</button>' +
          '<button class="primary" data-candidate-like="' + c.user_id + '">Хочу познакомиться</button>' +
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
  }

  function renderCandidate() {
    clearPoller();
    const c = state.currentCandidate;
    if (!c) return setRoute("home");
    const score = c.mutual_fit_score ?? c.compatibility_score ?? 0;
    const scores = c.category_scores || {};
    root.innerHTML = '<main class="page">' +
      '<header class="topbar"><button class="icon-btn" id="back-home">←</button><div class="brand" style="font-size:25px">Совместимость</div><div></div></header>' +
      candidateCard(c) +
      '<div class="section-head"><h2>Почему вы подходите</h2></div>' +
      '<section class="card"><div class="score-grid">' +
        Object.entries(scores).slice(0,4).map(([key,value]) =>
          '<div class="score"><b>' + esc(value) + '%</b><span class="muted">' + esc(key) + '</span></div>'
        ).join("") +
        (!Object.keys(scores).length ? '<div class="score"><b>' + esc(score) + '%</b><span class="muted">Общий показатель</span></div>' : '') +
      '</div></section>' +
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

  async function renderChats() {
    clearPoller(); loading("chats");
    try { state.conversations=(await api("/api/v1/chat/conversations")).conversations||[]; }
    catch { state.conversations=[]; }
    root.innerHTML='<main class="page">'+topbar("Сообщения")+
      '<div class="section-head"><div><div class="eyebrow">Общение</div><h2>Ваши чаты</h2></div></div>'+
      (state.conversations.length
        ? '<div class="grid">'+state.conversations.map(c=>{
          const p=c.profile||{};
          const last=c.last_message;
          return '<button class="card match-card" style="text-align:left;width:100%;border:1px solid var(--border)" data-open-chat="'+c.conversation_id+'">'+
            photo(p)+'<div class="match-main"><h3>'+esc(c.other_display_name||p.display_name||"Профиль")+'</h3>'+
            '<div class="muted line-clamp">'+esc(last?.body||"Начните общение")+'</div></div>'+
            (c.unread_count?'<span class="badge">'+esc(c.unread_count)+'</span>':'')+
          '</button>';
        }).join("")+'</div>'
        : '<section class="card empty"><div class="emoji">◌</div><h3>Пока нет диалогов</h3><p class="muted">После взаимного интереса здесь появится ваш чат.</p><button class="primary" data-route="matches">Совпадения</button></section>')+
    '</main>'+nav("chats");
    bindCommon();
    document.querySelectorAll("[data-open-chat]").forEach(btn=>btn.onclick=()=>{
      const id=Number(btn.dataset.openChat);
      state.currentConversation=state.conversations.find(x=>Number(x.conversation_id)===id);
      setRoute("chat");
    });
  }

  async function renderChat() {
    clearPoller();
    const conv=state.currentConversation;
    if(!conv) return setRoute("chats");
    const p=conv.profile||{};
    root.innerHTML='<main class="page chat-shell" style="padding-bottom:150px">'+
      '<header class="chat-head"><button class="icon-btn" id="chat-back">←</button>'+
        photo(p,"avatar small")+
        '<div class="chat-title"><b>'+esc(p.display_name||conv.other_display_name||"MatchLab")+'</b>'+
        '<span>'+esc(conv.mutual_fit_score??conv.compatibility_score??"")+(conv.mutual_fit_score!=null||conv.compatibility_score!=null?"% совместимость":"")+'</span></div>'+
        '<button class="icon-btn">⋯</button></header>'+
      '<div id="messages" class="messages"><div class="loader"></div></div>'+
    '</main>'+
    '<div class="composer"><textarea id="message-input" rows="1" placeholder="Напишите сообщение…"></textarea><button class="send" id="send-message">➤</button></div>'+
    nav("chats");
    bindCommon();
    document.getElementById("chat-back").onclick=()=>setRoute("chats");
    document.getElementById("send-message").onclick=sendCurrentMessage;
    await loadMessages();
    state.poller=setInterval(loadMessages,5000);
  }

  async function loadMessages() {
    const conv=state.currentConversation;
    if(!conv) return;
    try{
      const data=await api("/api/v1/chat/messages?conversation_id="+conv.conversation_id+"&limit=100");
      const items=data.messages||[];
      const box=document.getElementById("messages");
      if(!box) return;
      box.innerHTML=items.length ? items.map(m=>
        '<div class="bubble '+(m.is_mine?"mine":"theirs")+'">'+esc(m.body)+
        '<span class="bubble-time">'+esc((m.created_at||"").slice(11,16))+'</span></div>'
      ).join("") : '<div class="empty"><div class="emoji">♡</div><h3>Начните разговор</h3><p class="muted">Напишите первое сообщение — без шаблонов, просто по-человечески.</p></div>';
      if(items.length){
        const last=items[items.length-1];
        await post("/api/v1/chat/read",{conversation_id:conv.conversation_id,through_message_id:last.id}).catch(()=>{});
      }
      box.scrollTop=box.scrollHeight;
    }catch(e){}
  }

  async function sendCurrentMessage(){
    const input=document.getElementById("message-input");
    const text=input.value.trim();
    if(!text||!state.currentConversation) return;
    input.value="";
    try{
      await post("/api/v1/chat/messages",{
        conversation_id:state.currentConversation.conversation_id,
        body:text,
        client_message_id:(crypto.randomUUID?crypto.randomUUID():Date.now()+"-"+Math.random())
      });
      await loadMessages();
    }catch(e){alert("Не удалось отправить: "+e.message)}
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
  const selectHtml = (id, value, options) =>
    '<select class="input" id="'+id+'">'+options.map(([v,l]) =>
      '<option value="'+esc(v)+'" '+(String(value||"")===String(v)?"selected":"")+'>'+esc(l)+'</option>'
    ).join("")+'</select>';

  function firstIncompleteStep() {
    const c=state.onboarding?.completion||{};
    return (ONBOARDING_STEPS.find(([key])=>!c[key])||["photos"])[0];
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

    if(step==="questionnaire") return renderQuestionnaireStep();

    let body="";
    if(step==="basic"){
      body='<div class="onboarding-card"><div class="eyebrow">Начнём с главного</div><h1>Расскажите немного о себе</h1><p class="muted">Это поможет не показывать вам случайных людей.</p>'+
        '<div class="form-stack">'+
        '<label class="field-label">Имя<input class="input" id="ob-name" value="'+esc(p.display_name||"")+'" placeholder="Как к вам обращаться"></label>'+
        '<label class="field-label">Дата рождения<input class="input" id="ob-dob" type="date" value="'+esc(p.dob||"")+'"></label>'+
        '<div class="form-grid">'+
          '<label class="field-label">Ваш пол'+selectHtml("ob-gender",p.gender,[["M","Мужчина"],["F","Женщина"],["OTHER","Другое"]])+'</label>'+
          '<label class="field-label">Кого ищете'+selectHtml("ob-seek",p.seek_gender,[["F","Женщину"],["M","Мужчину"],["ANY","Не важно"],["OTHER","Другое"]])+'</label>'+
        '</div>'+
        '<button class="primary full" id="ob-save-basic">Продолжить →</button></div></div>';
    } else if(step==="relationship"){
      body='<div class="onboarding-card"><div class="eyebrow">Статус</div><h1>Вы сейчас в отношениях?</h1><p class="muted">MatchLab показывает анкеты только тем, кто действительно открыт к знакомству.</p>'+
        '<div class="choice-grid" id="relationship-choice">'+
          '<button class="choice-card" data-rel="no"><b>Нет</b><span>Я свободен(на)</span></button>'+
          '<button class="choice-card" data-rel="yes"><b>Да</b><span>Сейчас я в отношениях</span></button>'+
        '</div>'+
        '<div id="openness-block" class="form-stack" hidden><div class="field-label">Насколько вы открыты к знакомствам?</div>'+
          selectHtml("ob-openness","ACTIVE",[["ACTIVE","Активно хочу знакомиться"],["OPEN","Открыт(а), если встречу подходящего человека"],["UNSURE","Пока не уверен(а)"],["NO","Не хочу знакомств"]])+
          '<button class="primary full" id="ob-save-relationship">Продолжить →</button></div></div>';
    } else if(step==="readiness"){
      body='<div class="onboarding-card"><div class="eyebrow">Готовность</div><h1>Как вам комфортнее начинать знакомство?</h1><p class="muted">Это не влияет на «оценку» — только помогает подобрать людей с похожим темпом.</p>'+
        '<div class="form-stack">'+
        '<label class="field-label">Готовность общаться в чате'+selectHtml("ob-chat",p.readiness_chat,[["YES","Да, готов(а)"],["RATHER_YES","Скорее да"],["LOOK_ONLY","Пока хочу присмотреться"]])+'</label>'+
        '<label class="field-label">Готовность встретиться офлайн'+selectHtml("ob-offline",p.readiness_offline,[["YES","Да"],["MAYBE","Возможно, после общения"],["NO","Пока нет"]])+'</label>'+
        '<button class="primary full" id="ob-save-readiness">Продолжить →</button></div></div>';
    } else if(step==="details"){
      body='<div class="onboarding-card wide"><div class="eyebrow">О вас</div><h1>Что важно знать для совместимости?</h1><p class="muted">Только то, что реально помогает подобрать человека.</p>'+
        '<div class="form-grid">'+
          '<label class="field-label">Рост, см<input class="input" id="ob-height" type="number" min="100" max="250" value="'+esc(p.height||"")+'"></label>'+
          '<label class="field-label">Цель знакомства'+selectHtml("ob-goal",p.dating_goal,[["SERIOUS","Серьёзные отношения"],["FAMILY","Семья"],["SEE","Посмотрим, как сложится"],["CHAT","Общение"],["UNKNOWN","Пока не знаю"]])+'</label>'+
          '<label class="field-label">Дети'+selectHtml("ob-children",p.children_status,[["NO_CHILDREN","Нет детей"],["HAS_CHILDREN","Есть дети"]])+'</label>'+
          '<label class="field-label">Планы на детей'+selectHtml("ob-children-plans",p.children_plans,[["WANTS","Хочу"],["MAYBE","Возможно"],["DOES_NOT_WANT","Не хочу"]])+'</label>'+
          '<label class="field-label">Курение'+selectHtml("ob-smoking",p.smoking,[["NO","Не курю"],["RARE","Иногда"],["YES","Курю"]])+'</label>'+
          '<label class="field-label">Алкоголь'+selectHtml("ob-alcohol",p.alcohol,[["NO","Не употребляю"],["RARE","Редко"],["MODERATE","Умеренно"],["YES","Регулярно"]])+'</label>'+
          '<label class="field-label">Образ жизни'+selectHtml("ob-lifestyle",p.lifestyle,[["CALM","Спокойный"],["BALANCED","Сбалансированный"],["ACTIVE","Активный"],["VERY_ACTIVE","Очень активный"]])+'</label>'+
          '<label class="field-label">Религия — необязательно<input class="input" id="ob-religion" value="'+esc(p.religion||"")+'" placeholder="Например, ислам"></label>'+
        '</div>'+
        '<label class="field-label">Коротко о себе<textarea class="input textarea" id="ob-bio" maxlength="2000" placeholder="Чем вы живёте, что любите, какой человек вам близок">'+esc(p.bio||"")+'</textarea></label>'+
        '<button class="primary full" id="ob-save-details">Перейти к анкете →</button></div>';
    } else if(step==="partner_preferences"){
      const seek=p.seek_gender||"ANY";
      body='<div class="onboarding-card wide"><div class="eyebrow">Ваш человек</div><h1>Кого вы хотите встретить?</h1><p class="muted">Не делаем бесконечный фильтр. Только критерии, которые действительно важны.</p>'+
        '<div class="form-grid">'+
          '<label class="field-label">Возраст от<input class="input" id="pref-age-min" type="number" min="18" max="100" value="23"></label>'+
          '<label class="field-label">Возраст до<input class="input" id="pref-age-max" type="number" min="18" max="100" value="38"></label>'+
          '<label class="field-label">Расстояние, км<input class="input" id="pref-distance" type="number" min="1" max="1000" value="100"></label>'+
          '<label class="field-label">Рост от<input class="input" id="pref-height-min" type="number" min="100" max="250" value="150"></label>'+
          '<label class="field-label">Рост до<input class="input" id="pref-height-max" type="number" min="100" max="250" value="200"></label>'+
          '<label class="field-label">Цель знакомства'+selectHtml("pref-goal","SERIOUS",[["SERIOUS","Серьёзные отношения"],["FAMILY","Семья"],["SEE","Посмотрим"],["ANY","Любая"]])+'</label>'+
        '</div>'+
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
    pick("onboarding-exit").onclick=()=>setRoute("home");

    if(step==="basic"){
      pick("ob-save-basic").onclick=async()=>{
        try{
          onboardingStatus("Сохраняем…");
          await post("/api/v1/profile/basic",{display_name:pick("ob-name").value.trim(),dob:pick("ob-dob").value,gender:pick("ob-gender").value,seek_gender:pick("ob-seek").value,market_code:"KZ-ALA",preferred_locale:"ru-KZ"});
          await loadMe(); renderOnboarding();
        }catch(e){onboardingStatus("Проверьте данные: "+e.message,true)}
      };
    } else if(step==="relationship"){
      let inRelationship=false;
      document.querySelectorAll("[data-rel]").forEach(btn=>btn.onclick=()=>{
        inRelationship=btn.dataset.rel==="yes";
        document.querySelectorAll("[data-rel]").forEach(x=>x.classList.toggle("selected",x===btn));
        pick("openness-block").hidden=false;
        if(inRelationship) pick("ob-openness").value="NO";
      });
      pick("ob-save-relationship").onclick=async()=>{
        try{
          await post("/api/v1/profile/relationship",{in_relationship:inRelationship,openness:pick("ob-openness").value});
          await loadMe(); renderOnboarding();
        }catch(e){onboardingStatus(e.message,true)}
      };
    } else if(step==="readiness"){
      pick("ob-save-readiness").onclick=async()=>{
        try{
          await post("/api/v1/profile/readiness",{chat:pick("ob-chat").value,offline:pick("ob-offline").value});
          await loadMe(); renderOnboarding();
        }catch(e){onboardingStatus(e.message,true)}
      };
    } else if(step==="details"){
      pick("ob-save-details").onclick=async()=>{
        try{
          await post("/api/v1/profile/details",{height:Number(pick("ob-height").value),dating_goal:pick("ob-goal").value,children_status:pick("ob-children").value,children_plans:pick("ob-children-plans").value,smoking:pick("ob-smoking").value,alcohol:pick("ob-alcohol").value,lifestyle:pick("ob-lifestyle").value,bio:pick("ob-bio").value.trim(),religion:pick("ob-religion").value.trim(),nationality:""});
          await loadMe(); renderOnboarding();
        }catch(e){onboardingStatus("Не удалось сохранить: "+e.message,true)}
      };
    } else if(step==="partner_preferences"){
      pick("ob-save-preferences").onclick=async()=>{
        const seek=(state.onboarding?.profile?.seek_gender||"ANY");
        const gender=seek==="ANY"?["M","F","OTHER"]:[seek];
        const goal=pick("pref-goal").value;
        const prefs={
          age:{importance:"HARD",value:{min:Number(pick("pref-age-min").value),max:Number(pick("pref-age-max").value)}},
          gender:{importance:"HARD",value:gender},
          market:{importance:"HARD",value:["KZ-ALA"]},
          distance_km:{importance:"IMPORTANT",value:{max:Number(pick("pref-distance").value)}},
          dating_goal:{importance:"IMPORTANT",value:goal==="ANY"?["SERIOUS","FAMILY","SEE","CHAT","UNKNOWN"]:[goal]},
          children_status:{importance:"IGNORE"},
          children_plans:{importance:"IGNORE"},
          smoking:{importance:"IGNORE"},
          alcohol:{importance:"IGNORE"},
          lifestyle:{importance:"IGNORE"},
          height:{importance:"PREFERENCE",value:{min:Number(pick("pref-height-min").value),max:Number(pick("pref-height-max").value)}}
        };
        try{
          onboardingStatus("Сохраняем критерии…");
          await post("/api/v1/preferences",{preferences:prefs});
          await loadMe(); renderOnboarding();
        }catch(e){onboardingStatus("Не удалось сохранить: "+e.message,true)}
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

  async function renderProfile() {
    clearPoller(); loading("profile"); await loadMe();
    const p=state.profile?.profile;
    const c=state.profile?.completion||{};
    const steps=[
      ["Базовый профиль",c.basic],["Статус отношений",c.relationship],["Готовность",c.readiness],
      ["О себе",c.details],["Анкета",c.questionnaire],["Критерии партнёра",c.partner_preferences],["Фото",c.photos]
    ];
    root.innerHTML='<main class="page">'+topbar("Профиль")+
      '<section class="card"><div class="eyebrow">Ваш профиль</div><h2 style="font-family:Georgia,serif;font-size:30px">'+esc(p?.display_name||"MatchLab")+'</h2>'+
      '<p class="muted">'+esc(p?.city||"Алматы")+'</p>'+
      '<div class="tags">'+steps.map(([name,done])=>'<span class="tag">'+(done?"✓ ":"○ ")+esc(name)+'</span>').join("")+'</div>'+
      '<button class="secondary full" id="logout-btn" style="margin-top:14px">Выйти из аккаунта</button></section>'+
      '<div class="section-head"><h2>Статус анкеты</h2></div>'+
      '<section class="card"><p>'+esc(state.onboarding?.waitlist?.message||"Продолжайте заполнять профиль, чтобы участвовать в подборе.")+'</p>'+
      '<button class="primary full" id="continue-onboarding">Продолжить анкету →</button></section>'+
    '</main>'+nav("profile");
    bindCommon();
    const continueBtn=document.getElementById("continue-onboarding");
    if(continueBtn) continueBtn.onclick=()=>setRoute("onboarding");
    document.getElementById("logout-btn").onclick=async()=>{
      try{await post("/api/v1/auth/logout",{});}catch{}
      state.authenticated=false; state.profile=null; state.onboarding=null; location.hash=""; renderAuth("login");
    };
  }

  async function renderRoute(force=false) {
    clearPoller();
    if(!state.authenticated){
      try{
        await api("/api/v1/auth/methods");
        state.authenticated=true;
      }catch(e){
        if(e.status===401){renderAuth("login");return;}
      }
    }
    const route=(location.hash||"#home").slice(1).split("?")[0];
    if(route==="onboarding") return renderOnboarding(force);
    if(route==="home") return renderHome();
    if(route==="candidate") return renderCandidate();
    if(route==="matches") return renderMatches();
    if(route==="chats") return renderChats();
    if(route==="chat") return renderChat();
    if(route==="profile") return renderProfile();
    return setRoute("home");
  }

  window.addEventListener("hashchange",()=>renderRoute());
  window.addEventListener("load",async()=>{
    if("serviceWorker" in navigator) navigator.serviceWorker.register("/web/sw.js").catch(()=>{});
    await renderRoute();
  });
})();