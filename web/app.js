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

  function renderLanding() {
    clearPoller();
    document.body.classList.add("landing-active");
    const heroPhoto="https://images.unsplash.com/photo-1776266099714-2177bb456209?auto=format&fit=crop&fm=jpg&q=88&w=1800";
    const demoProfiles=[
      {name:"Анна",age:26,role:"Дизайнер",city:"Алматы",score:92,photo:"https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=900&q=82",note:"Любит спокойные вечера, путешествия и развиваться в профессии."},
      {name:"Дмитрий",age:28,role:"Предприниматель",city:"Алматы",score:89,photo:"https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=900&q=82",note:"Ценит близкие отношения, спорт и честный разговор."},
      {name:"Екатерина",age:25,role:"Психолог",city:"Алматы",score:87,photo:"https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=900&q=82",note:"Интересуется людьми, искусством и осознанным образом жизни."},
      {name:"Алексей",age:30,role:"Маркетолог",city:"Алматы",score:84,photo:"https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=900&q=82",note:"Любит горы, новые идеи и отношения без игр."}
    ];
    root.innerHTML =
      '<main class="landing">' +
        '<header class="landing-header">' +
          '<div class="landing-header-inner">' +
            '<button class="landing-brand" data-scroll="top" aria-label="MatchLab"><span class="landing-logo-mark">♡</span><span>Match<span>Lab</span></span></button>' +
            '<nav class="landing-nav" id="landing-nav">' +
              '<button data-scroll="about">О нас</button>' +
              '<button data-scroll="how">Как это работает</button>' +
              '<button data-scroll="stories">Истории</button>' +
              '<button data-scroll="safety">Безопасность</button>' +
              '<button data-scroll="blog">Блог</button>' +
            '</nav>' +
            '<div class="landing-header-actions"><span class="landing-lang">🌐 RU</span><button class="tertiary" data-auth="login">Войти</button><button class="primary landing-create" data-auth="register">Создать аккаунт</button><button class="landing-burger" id="landing-burger" aria-label="Меню">☰</button></div>' +
          '</div>' +
        '</header>' +

        '<section class="landing-hero landing-anchor" id="top">' +
          '<div class="landing-container hero-grid">' +
            '<div class="hero-content" id="about">' +
              '<div class="landing-kicker">БОЛЬШЕ, ЧЕМ ЗНАКОМСТВА</div>' +
              '<h1>Знакомства без<br><em>бесконечных свайпов</em></h1>' +
              '<p class="hero-lead">MatchLab анализирует ваши ценности, характер и взгляды на отношения, чтобы находить людей, с которыми действительно может возникнуть совместимость.</p>' +
              '<div class="hero-actions"><button class="primary landing-primary" data-auth="register">Пройти анкету →</button><button class="secondary landing-secondary" data-scroll="how">▶&nbsp;&nbsp;Как это работает</button></div>' +
              '<div class="landing-proof">' +
                '<div class="proof-avatars">' +
                  demoProfiles.slice(0,3).map(p=>'<img src="'+esc(p.photo)+'" alt="" loading="lazy">').join("") +
                '</div>' +
                '<div><b>Первые участники формируют MatchLab</b><span>Без выдуманных цифр: сервис собирает качественную базу для запуска.</span></div>' +
              '</div>' +
            '</div>' +
            '<div class="hero-visual">' +
              '<div class="hero-glow hero-glow-one"></div><div class="hero-glow hero-glow-two"></div>' +
              '<img class="hero-couple" src="'+heroPhoto+'" alt="Пара, которая проводит время вместе">' +
              '<div class="hero-signup-card">' +
                '<div class="signup-progress"><i class="active"></i><i></i><i></i><i></i><i></i></div>' +
                '<div class="eyebrow">Начните с себя</div><h2>Кого мы будем искать для вас?</h2>' +
                '<p>Пройдите короткий первый этап — дальше MatchLab постепенно узнает вас лучше.</p>' +
                '<label class="landing-field-title">Кто вы?</label>' +
                '<div class="gender-choices"><button data-landing-gender="F">♀ <span>Я женщина</span></button><button data-landing-gender="M">♂ <span>Я мужчина</span></button></div>' +
                '<div class="age-head"><label for="landing-age">Ваш возраст</label><strong id="landing-age-value">25</strong></div>' +
                '<input id="landing-age" class="landing-range" type="range" min="18" max="70" value="25">' +
                '<button class="primary full" id="landing-continue">Продолжить →</button>' +
                '<div class="signup-privacy">🔒 Ваши данные защищены</div>' +
              '</div>' +
            '</div>' +
          '</div>' +
        '</section>' +

        '<section class="landing-section landing-anchor" id="how">' +
          '<div class="landing-container">' +
            '<div class="landing-section-head centered"><div class="landing-kicker">КАК ЭТО РАБОТАЕТ</div><h2>Технологии, которые сближают людей</h2><p>От глубокой анкеты до нескольких осмысленных знакомств — без каталога из сотен случайных профилей.</p></div>' +
            '<div class="feature-grid">' +
              '<article class="feature-card"><div class="feature-icon">▤</div><h3>Глубокая анкета</h3><p>Вы отвечаете на вопросы о ценностях, образе жизни, характере и взглядах на отношения.</p><span>10–15 минут для первого этапа</span></article>' +
              '<article class="feature-card"><div class="feature-icon">✦</div><h3>MatchLab анализирует совместимость</h3><p>Ответы складываются в психологически и жизненно осмысленный профиль совместимости.</p><span>Не только интересы</span></article>' +
              '<article class="feature-card"><div class="feature-icon">♡</div><h3>Осмысленные знакомства</h3><p>Вместо сотен случайных профилей — ограниченное количество действительно подходящих людей.</p><span>Без бесконечных свайпов</span></article>' +
              '<article class="feature-card"><div class="feature-icon">◌</div><h3>Настоящее общение</h3><p>Когда интерес взаимный, MatchLab помогает перейти к содержательному диалогу.</p><span>Взаимный интерес</span></article>' +
            '</div>' +
          '</div>' +
        '</section>' +

        '<section class="landing-section candidate-demo-section">' +
          '<div class="landing-container">' +
            '<div class="landing-section-head"><div><div class="landing-kicker">НЕ СЛУЧАЙНЫЕ ПРОФИЛИ</div><h2>Люди, которые могут вам подойти</h2><p>Мы уже сделали большую часть поиска за вас. Ниже — демонстрационный пример того, как выглядит подбор.</p></div></div>' +
            '<div class="demo-candidate-grid">' +
              demoProfiles.map(p=>'<article class="demo-candidate-card"><div class="demo-photo-wrap"><img src="'+esc(p.photo)+'" alt="'+esc(p.name)+'" loading="lazy"><span class="demo-label">Демонстрационный профиль</span></div><div class="demo-candidate-copy"><div class="demo-name-row"><div><h3>'+esc(p.name)+', '+p.age+'</h3><span>'+esc(p.role)+' · '+esc(p.city)+'</span></div><div class="demo-score"><b>💜 '+p.score+'%</b><small>по анкете</small></div></div><p>'+esc(p.note)+'</p></div></article>').join("") +
            '</div>' +
          '</div>' +
        '</section>' +

        '<section class="landing-section compatibility-showcase">' +
          '<div class="landing-container">' +
            '<div class="landing-section-head centered"><div class="landing-kicker">ОБЪЯСНЯЕМ, А НЕ ПРОСТО СЧИТАЕМ</div><h2>Почему вам действительно может быть хорошо вместе</h2><p>Процент — только начало. Главное — понять, где именно вы совпадаете и что стоит спокойно обсудить.</p></div>' +
            '<div class="compat-chat-grid">' +
              '<article class="landing-compat-card">' +
                '<div class="landing-compat-top"><div><div class="compat-status">💜 Высокая совместимость</div><div class="compat-people"><img src="'+esc(demoProfiles[0].photo)+'" alt=""><div class="compat-ring"><strong id="landing-compat-percent">0%</strong><span>по анкете</span></div><img src="'+esc(demoProfiles[1].photo)+'" alt=""></div></div></div>' +
                '<h3>Почему вы можете подойти друг другу</h3>' +
                '<div class="landing-reasons">' +
                  '<div><span>💜</span><p><b>Ценности — очень близкие</b>Оба цените стабильность, личную свободу и развитие.</p></div>' +
                  '<div><span>🏠</span><p><b>Семья — совпадает</b>Похожее отношение к семье и будущему.</p></div>' +
                  '<div><span>💬</span><p><b>Общение — высокая совместимость</b>Вы оба предпочитаете обсуждать проблемы напрямую.</p></div>' +
                  '<div><span>🌙</span><p><b>Образ жизни — есть различия</b>Один из вас чаще выбирает активную социальную жизнь.</p></div>' +
                '</div>' +
                '<div class="landing-attention"><div class="eyebrow">На что стоит обратить внимание</div><p>У вас может отличаться потребность в социальной активности. Это не обязательно проблема — просто тема, которую полезно обсудить.</p></div>' +
                '<div class="landing-candidate-actions"><button class="tertiary" data-auth="register">Подробнее</button><button class="primary" data-auth="register">💜 Хочу познакомиться</button><button class="secondary" data-auth="register">Пока не подходит</button></div>' +
              '</article>' +
              '<article class="landing-chat-card">' +
                '<div class="chat-preview-head"><div><div class="landing-kicker">ОБЩЕНИЕ</div><h3>Общение, которое начинается с общего</h3></div><span>92%</span></div>' +
                '<div class="chat-preview-person"><img src="'+esc(demoProfiles[0].photo)+'" alt=""><div><b>Анна, 26</b><span>Высокая совместимость</span></div></div>' +
                '<div class="chat-preview-messages"><div class="preview-bubble mine">Привет! Увидел, что мы оба мечтаем съездить в Японию. Какое место ты бы посетила первым? 🙂</div><div class="preview-bubble">Наверное Киото. Особенно весной 🌸 А ты?</div></div>' +
                '<div class="chat-assist-preview">✨ MatchLab может предложить тему для начала разговора</div>' +
                '<div class="preview-composer"><span>Напишите сообщение...</span><button>➤</button></div>' +
              '</article>' +
            '</div>' +
          '</div>' +
        '</section>' +

        '<section class="landing-section stories-section landing-anchor" id="stories">' +
          '<div class="landing-container">' +
            '<div class="landing-section-head centered"><div class="landing-kicker">ИСТОРИИ MATCHLAB</div><h2>Истории, которые начнутся с совпадения</h2><p>Мы не публикуем выдуманные отзывы. Здесь появятся реальные истории пар после запуска и только с их согласия.</p></div>' +
            '<div class="stories-honest-card"><div class="stories-orbit"><span>♡</span><span>✦</span><span>♡</span></div><h3>Первые знакомства уже впереди</h3><p>MatchLab создаётся для того, чтобы находить не «идеальных» людей, а тех, с кем совпадают действительно важные вещи.</p><button class="secondary" data-auth="register">Стать одним из первых участников</button></div>' +
          '</div>' +
        '</section>' +

        '<section class="landing-section safety-section landing-anchor" id="safety">' +
          '<div class="landing-container safety-grid">' +
            '<div><div class="landing-kicker">БЕЗОПАСНОСТЬ И ДОВЕРИЕ</div><h2>Серьёзные знакомства требуют спокойного пространства</h2><p>Профиль появляется в подборе только после заполнения ключевых данных и прохождения необходимых проверок. Жалобы, блокировки и управление видимостью встроены в продукт.</p><div class="safety-points"><div><b>18+</b><span>сервис только для совершеннолетних</span></div><div><b>Контроль</b><span>можно поставить знакомства на паузу</span></div><div><b>Безопасность</b><span>жалоба и блокировка доступны из профиля и чата</span></div></div></div>' +
            '<div class="safety-visual"><div class="shield-mark">♡</div><h3>Ваш профиль — под вашим контролем</h3><p>Вы сами управляете фотографиями, критериями, статусом знакомств, уведомлениями и удалением аккаунта.</p><a href="/privacy" target="_blank" rel="noopener">Политика конфиденциальности →</a></div>' +
          '</div>' +
        '</section>' +

        '<section class="landing-section blog-section landing-anchor" id="blog">' +
          '<div class="landing-container"><div class="landing-section-head"><div><div class="landing-kicker">БЛОГ</div><h2>О знакомствах без игр</h2></div></div><div class="blog-grid">' +
            '<article><span>Совместимость</span><h3>Почему общие интересы — ещё не всё</h3><p>Как ценности, границы и стиль общения влияют на отношения.</p></article>' +
            '<article><span>Первое знакомство</span><h3>Что обсуждать, когда хочется узнать человека глубже</h3><p>Темы, которые помогают перейти от small talk к настоящему диалогу.</p></article>' +
            '<article><span>Безопасность</span><h3>Как знакомиться онлайн спокойнее</h3><p>Простые правила личных границ и первой встречи.</p></article>' +
          '</div></div>' +
        '</section>' +

        '<section class="landing-final-cta">' +
          '<div class="landing-container"><div class="final-cta-card"><div class="landing-kicker">ГОТОВЫ ПОЗНАКОМИТЬСЯ ИНАЧЕ?</div><h2>Пройдите анкету — остальное MatchLab возьмёт на себя.</h2><p>Вместо бесконечного выбора — несколько людей, с которыми действительно стоит познакомиться.</p><button class="primary landing-primary" data-auth="register">Начать анкету →</button></div></div>' +
        '</section>' +

        '<footer class="landing-footer"><div class="landing-container footer-grid"><div><button class="landing-brand" data-scroll="top"><span class="landing-logo-mark">♡</span><span>Match<span>Lab</span></span></button><p>Знакомства по совместимости. 18+.</p></div><div><b>Продукт</b><button data-scroll="how">Как это работает</button><button data-scroll="safety">Безопасность</button><button data-scroll="blog">Блог</button></div><div><b>Документы</b><a href="/privacy" target="_blank" rel="noopener">Конфиденциальность</a><a href="/terms" target="_blank" rel="noopener">Условия</a></div><div><b>Аккаунт</b><button data-auth="login">Войти</button><button data-auth="register">Создать аккаунт</button></div></div></footer>' +
      '</main>';
    bindLanding();
  }

  function bindLanding() {
    document.querySelectorAll("[data-auth]").forEach(btn=>btn.onclick=()=>setRoute(btn.dataset.auth));
    document.querySelectorAll("[data-scroll]").forEach(btn=>btn.onclick=()=>{
      const target=document.getElementById(btn.dataset.scroll);
      if(target) target.scrollIntoView({behavior:"smooth",block:"start"});
      document.getElementById("landing-nav")?.classList.remove("open");
    });
    const burger=document.getElementById("landing-burger");
    if(burger) burger.onclick=()=>document.getElementById("landing-nav")?.classList.toggle("open");

    let gender="";
    document.querySelectorAll("[data-landing-gender]").forEach(btn=>btn.onclick=()=>{
      gender=btn.dataset.landingGender;
      document.querySelectorAll("[data-landing-gender]").forEach(x=>x.classList.toggle("selected",x===btn));
    });
    const age=document.getElementById("landing-age");
    const ageValue=document.getElementById("landing-age-value");
    if(age&&ageValue) age.oninput=()=>ageValue.textContent=age.value;
    const continueBtn=document.getElementById("landing-continue");
    if(continueBtn) continueBtn.onclick=()=>{
      try{
        sessionStorage.setItem("ml_landing_gender",gender);
        sessionStorage.setItem("ml_landing_age",age?.value||"25");
      }catch{}
      setRoute("register");
    };

    const score=document.getElementById("landing-compat-percent");
    if(score){
      const target=94;
      let current=0;
      const tick=()=>{
        current=Math.min(target,current+2);
        score.textContent=current+"%";
        if(current<target) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }
  }

  function renderAuth(mode="login") {
    clearPoller();
    document.body.classList.remove("landing-active");
    const register = mode === "register";
    root.innerHTML = '<main class="auth-screen auth-screen-v12">' +
      '<button class="auth-home-back" id="auth-home-back">← На главную</button>' +
      '<div class="auth-v12-shell">' +
        '<section class="auth-v12-visual">' +
          '<img src="https://images.unsplash.com/photo-1776266099714-2177bb456209?auto=format&fit=crop&fm=jpg&q=86&w=1600" alt="Пара">' +
          '<div class="auth-v12-copy"><div class="landing-kicker">MATCHLAB</div><h1>Не выбирайте из всех.<br>Найдите подходящего.</h1><p>Глубокая анкета, небольшой подбор и понятное объяснение совместимости.</p></div>' +
        '</section>' +
        '<section class="auth-panel auth-panel-v12">' +
          '<div class="auth-v12-brand"><span class="landing-logo-mark">♡</span><div class="brand">Match<span>Lab</span></div></div>' +
          '<div class="tabs auth-switch">' +
            '<button class="tab ' + (!register?"active":"") + '" id="auth-login-tab">Вход</button>' +
            '<button class="tab ' + (register?"active":"") + '" id="auth-register-tab">Регистрация</button>' +
          '</div>' +
          '<section class="auth-card">' +
            '<div class="eyebrow">' + (register?"Новый профиль":"С возвращением") + '</div>' +
            '<h2>' + (register?"Создайте аккаунт":"Войдите в MatchLab") + '</h2>' +
            '<p class="muted">' + (register?"После регистрации начнём анкету совместимости.":"По SMS-коду или телефону/email и паролю.") + '</p>' +
            (register ? registerForm() : loginForm()) +
            '<div id="form-status" class="status" hidden></div>' +
          '</section>' +
          '<p class="auth-legal muted">18+. Продолжая, вы принимаете <a href="/terms" target="_blank" rel="noopener">Условия</a> и <a href="/privacy" target="_blank" rel="noopener">Политику конфиденциальности</a>.</p>' +
        '</section>' +
      '</div>' +
    '</main>';
    document.getElementById("auth-home-back").onclick=()=>{location.hash="";renderRoute()};
    document.getElementById("auth-login-tab").onclick = () => setRoute("login");
    document.getElementById("auth-register-tab").onclick = () => setRoute("register");
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
        await post("/api/v1/auth/phone/register/verify",{phone,password,code});
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
    document.body.classList.remove("landing-active");
    const body=active==="home"
      ? '<section class="card loading-state"><div class="loading-spark">✦</div><h3>Ищем подходящих людей</h3><p class="muted">MatchLab сравнивает ценности, образ жизни и ожидания от отношений.</p><div class="loader"></div></section>'
      : '<div class="loader"></div>';
    root.innerHTML = '<main class="page">' + topbar() + body + '</main>' + nav(active);
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
        '<div class="compat-pill"><span>Совместимость по анкете</span><b>' + esc(score) + '%</b></div>' +
      '</div>' +
      '<div class="candidate-body">' +
        '<div class="candidate-title"><div><h2>' + esc(name + age) + '</h2><div class="muted">' + esc(c.city || "") + '</div></div></div>' +
        '<div class="tags">' + compatibilityReason(c) + '</div>' +
        (c.bio ? '<p>' + esc(c.bio) + '</p>' : '') +
        '<button class="candidate-detail-link" data-candidate-detail="' + c.user_id + '">Подробнее</button>' +
        '<div class="actions candidate-actions">' +
          '<button class="secondary candidate-reject" data-candidate-skip="' + c.user_id + '">Пока не подходит</button>' +
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
          btn.textContent="Пока не подходит";
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
    modal.innerHTML = '<div class="modal"><div class="hearts">💜</div>' +
      '<div class="eyebrow">Взаимный интерес</div><h2>Интерес взаимный</h2>' +
      '<p class="muted">Теперь вы можете начать общение' + (c.display_name ? " с " + esc(c.display_name) : "") + '.</p>' +
      '<button class="primary full" id="mutual-chat">Написать сообщение →</button>' +
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
        '<button class="icon-btn" id="chat-safety">⋯</button></header>'+
      '<div class="conversation-assist">✨ MatchLab может предложить тему для начала разговора — но сообщение всегда пишете вы.</div>'+
      '<div id="messages" class="messages"><div class="loader"></div></div>'+
    '</main>'+
    '<div class="composer"><textarea id="message-input" rows="1" placeholder="Напишите сообщение…"></textarea><button class="send" id="send-message">➤</button></div>'+
    nav("chats");
    bindCommon();
    document.getElementById("chat-back").onclick=()=>setRoute("chats");
    const safetyBtn=document.getElementById("chat-safety");
    if(safetyBtn)safetyBtn.onclick=()=>{
      const userId=Number(p.user_id||conv.other_user_id||0);
      if(userId)showSafetyModal(userId,p.display_name||conv.other_display_name||"этого пользователя");
    };
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


  async function renderWaitlistCompletion(){
    clearPoller();
    if(!state.onboarding) await loadMe();
    const p=state.onboarding?.profile||state.profile?.profile||{};
    let waitlist=state.onboarding?.waitlist||{};
    try{waitlist=await api("/api/v1/waitlist/status");}catch{}
    const ready=!!waitlist.ready;
    const stateLabel=waitlist.state==="WAITLIST"?"Вы в листе ожидания":waitlist.state==="MATCHING_ACTIVE"?"Подбор уже открыт":"Профиль готов";
    root.innerHTML='<main class="onboarding-page waitlist-page">'+
      '<header class="onboarding-head"><div class="brand">Match<span>Lab</span></div><button class="ghost" id="waitlist-profile">Профиль</button></header>'+
      '<section class="onboarding-shell"><div class="onboarding-card waitlist-card">'+
        '<div class="waitlist-mark">'+(ready?"✓":"♡")+'</div>'+
        '<div class="eyebrow">Анкета завершена</div>'+
        '<h1>'+esc(stateLabel)+(p.display_name?" — "+esc(p.display_name):"")+'</h1>'+
        '<p class="muted">'+esc(waitlist.message||"Ваш профиль сохранён. Мы сообщим, когда подбор станет доступен.")+'</p>'+
        '<div class="waitlist-summary">'+
          '<div><b>100%</b><span>анкета заполнена</span></div>'+
          '<div><b>'+esc(p.market_code==="KZ-ALA"?"Алматы":p.market_code||"Алматы")+'</b><span>город запуска</span></div>'+
          '<div><b>'+esc(ready?"Готов":"Проверяем")+'</b><span>статус профиля</span></div>'+
        '</div>'+
        '<button class="primary full" id="waitlist-home">Перейти в приложение →</button>'+
        '<button class="secondary full" id="waitlist-edit">Изменить профиль</button>'+
      '</div></section></main>';
    document.getElementById("waitlist-home").onclick=()=>setRoute("home");
    document.getElementById("waitlist-edit").onclick=()=>setRoute("profile");
    document.getElementById("waitlist-profile").onclick=()=>setRoute("profile");
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
      '<section class="profile-menu">'+
        profileMenuRow("👤","Редактировать профиль","Имя, о себе, образ жизни","profile-edit")+
        profileMenuRow("🎯","Кого я ищу","Возраст, цели, привычки и другие критерии","preferences")+
        profileMenuRow("🧠","Моя совместимость","Что анкета говорит о ваших приоритетах","compatibility",c.questionnaire?"Готово":"")+
        profileMenuRow("📷","Мои фотографии","Добавить, удалить, выбрать главное фото","photos",(photoData.progress?.approved||0)+"/2")+
        profileMenuRow("❤️","Статус знакомств","Активно, пауза или уже в отношениях","dating-status")+
        profileMenuRow("🔔","Уведомления","Push и разрешения этого устройства","notifications")+
        profileMenuRow("🛡","Безопасность и заблокированные","Жалобы, блокировки и список исключений","safety")+
        profileMenuRow("⚙️","Настройки аккаунта","Вход, данные, документы и удаление","settings")+
      '</section>'+
    '</main>'+nav("profile");
    bindCommon();
  }

  async function renderProfileEdit(){
    clearPoller(); loading("profile"); await loadMe();
    const p=state.profile?.profile||{};
    root.innerHTML='<main class="page">'+profileBackHeader("Редактировать профиль")+
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
        btn.disabled=false;inlineStatus("profile-edit-status","Не удалось сохранить: "+e.message,true);
      }
    };
  }

  async function renderPreferences(){
    clearPoller(); loading("profile"); await loadMe();
    let data={values:{}};
    try{data=await api("/api/v1/preferences");}catch{}
    const values=data.values||{};
    const val=(key,fallback)=>values[key]?.value??fallback;
    const age=val("age",{min:23,max:38});
    const height=val("height",{min:150,max:200});
    const distance=val("distance_km",{max:100});
    const first=(key,fallback)=>{
      const v=val(key,[fallback]);
      return Array.isArray(v)&&v.length?v[0]:fallback;
    };
    const genderValues=val("gender",[]);
    const gender=Array.isArray(genderValues)&&genderValues.length===1?genderValues[0]:"ANY";
    const goalValues=val("dating_goal",[]);
    const goal=Array.isArray(goalValues)&&goalValues.length===1?goalValues[0]:"ANY";

    root.innerHTML='<main class="page">'+profileBackHeader("Кого я ищу")+
      '<section class="card settings-card"><div class="eyebrow">Критерии партнёра</div><h2>Показывать только действительно подходящих людей</h2>'+
      '<p class="muted">Жёсткие критерии отсекают неподходящих кандидатов, остальные влияют на ранжирование совместимости.</p>'+
      '<div class="form-grid">'+
        '<label class="field-label">Возраст от<input class="input" id="pref-edit-age-min" type="number" min="18" max="100" value="'+esc(age.min??23)+'"></label>'+
        '<label class="field-label">Возраст до<input class="input" id="pref-edit-age-max" type="number" min="18" max="100" value="'+esc(age.max??38)+'"></label>'+
        '<label class="field-label">Кого ищу'+selectHtml("pref-edit-gender",gender,[["F","Женщину"],["M","Мужчину"],["OTHER","Другое"],["ANY","Не важно"]])+'</label>'+
        '<label class="field-label">Максимальное расстояние, км<input class="input" id="pref-edit-distance" type="number" min="1" max="1000" value="'+esc(distance.max??100)+'"></label>'+
        '<label class="field-label">Рост от<input class="input" id="pref-edit-height-min" type="number" min="100" max="250" value="'+esc(height.min??150)+'"></label>'+
        '<label class="field-label">Рост до<input class="input" id="pref-edit-height-max" type="number" min="100" max="250" value="'+esc(height.max??200)+'"></label>'+
        '<label class="field-label">Цель знакомства'+selectHtml("pref-edit-goal",goal,[["SERIOUS","Серьёзные отношения"],["FAMILY","Семья"],["SEE","Посмотрим"],["CHAT","Общение"],["ANY","Не важно"]])+'</label>'+
        '<label class="field-label">Дети'+selectHtml("pref-edit-children",first("children_status","ANY"),[["ANY","Не важно"],["NO_CHILDREN","Без детей"],["HAS_CHILDREN","Есть дети"]])+'</label>'+
        '<label class="field-label">Планы на детей'+selectHtml("pref-edit-plans",first("children_plans","ANY"),[["ANY","Не важно"],["WANTS","Хочет"],["MAYBE","Возможно"],["DOES_NOT_WANT","Не хочет"]])+'</label>'+
        '<label class="field-label">Курение'+selectHtml("pref-edit-smoking",first("smoking","ANY"),[["ANY","Не важно"],["NO","Не курит"],["RARE","Иногда"],["YES","Курит"]])+'</label>'+
        '<label class="field-label">Алкоголь'+selectHtml("pref-edit-alcohol",first("alcohol","ANY"),[["ANY","Не важно"],["NO","Не употребляет"],["RARE","Редко"],["MODERATE","Умеренно"],["YES","Регулярно"]])+'</label>'+
        '<label class="field-label">Образ жизни'+selectHtml("pref-edit-lifestyle",first("lifestyle","ANY"),[["ANY","Не важно"],["CALM","Спокойный"],["BALANCED","Сбалансированный"],["ACTIVE","Активный"],["VERY_ACTIVE","Очень активный"]])+'</label>'+
      '</div>'+
      '<button class="primary full" id="save-preferences-edit">Сохранить критерии</button>'+
      '<div id="preferences-status" class="status" hidden></div></section>'+
    '</main>'+nav("profile");
    bindCommon();
    document.getElementById("profile-back").onclick=()=>setRoute("profile");
    document.getElementById("save-preferences-edit").onclick=async()=>{
      const g=document.getElementById("pref-edit-gender").value;
      const goalValue=document.getElementById("pref-edit-goal").value;
      const prefs={
        age:{importance:"HARD",value:{min:Number(document.getElementById("pref-edit-age-min").value),max:Number(document.getElementById("pref-edit-age-max").value)}},
        gender:{importance:"HARD",value:g==="ANY"?["M","F","OTHER"]:[g]},
        market:{importance:"HARD",value:["KZ-ALA"]},
        distance_km:{importance:"IMPORTANT",value:{max:Number(document.getElementById("pref-edit-distance").value)}},
        dating_goal:{importance:"IMPORTANT",value:goalValue==="ANY"?["SERIOUS","FAMILY","SEE","CHAT","UNKNOWN"]:[goalValue]},
        children_status:{importance:"IMPORTANT",value:[document.getElementById("pref-edit-children").value]},
        children_plans:{importance:"IMPORTANT",value:[document.getElementById("pref-edit-plans").value]},
        smoking:{importance:"PREFERENCE",value:[document.getElementById("pref-edit-smoking").value]},
        alcohol:{importance:"PREFERENCE",value:[document.getElementById("pref-edit-alcohol").value]},
        lifestyle:{importance:"PREFERENCE",value:[document.getElementById("pref-edit-lifestyle").value]},
        height:{importance:"PREFERENCE",value:{min:Number(document.getElementById("pref-edit-height-min").value),max:Number(document.getElementById("pref-edit-height-max").value)}}
      };
      const btn=document.getElementById("save-preferences-edit");
      btn.disabled=true;inlineStatus("preferences-status","Сохраняем…");
      try{
        await post("/api/v1/preferences",{preferences:prefs});
        await loadMe();
        btn.disabled=false;inlineStatus("preferences-status","Критерии сохранены ✓");
      }catch(e){btn.disabled=false;inlineStatus("preferences-status","Не удалось сохранить: "+e.message,true)}
    };
  }

  async function renderCompatibility(){
    clearPoller(); loading("profile");
    let data=null;
    try{data=await api("/api/v1/compatibility/me");}catch{}
    root.innerHTML='<main class="page">'+profileBackHeader("Моя совместимость")+
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
      root.innerHTML='<main class="page">'+profileBackHeader("Мои фотографии")+'<section class="card empty"><h3>Фото пока недоступны</h3><p class="muted">'+esc(e.message)+'</p></section></main>'+nav("profile");
      bindCommon();document.getElementById("profile-back").onclick=()=>setRoute("profile");return;
    }
    const items=(data.photos||[]).slice().sort((a,b)=>(a.sort_order||0)-(b.sort_order||0));
    const statusLabel={APPROVED:"Одобрено",PENDING:"На модерации",REJECTED:"Отклонено"};
    root.innerHTML='<main class="page">'+profileBackHeader("Мои фотографии")+
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
    root.innerHTML='<main class="page">'+profileBackHeader("Статус знакомств")+
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
    root.innerHTML='<main class="page">'+profileBackHeader("Уведомления")+
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
    root.innerHTML='<main class="page">'+profileBackHeader("Безопасность")+
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
    root.innerHTML='<main class="page">'+profileBackHeader("Настройки аккаунта")+
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
    if(!state.authenticated && route==="login") return renderAuth("login");
    if(!state.authenticated && route==="register") return renderAuth("register");
    if(!state.authenticated){
      try{
        await api("/api/v1/auth/methods");
        state.authenticated=true;
      }catch(e){
        if(e.status===401){renderLanding();return;}
      }
    }
    document.body.classList.remove("landing-active");
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
    if("serviceWorker" in navigator) navigator.serviceWorker.register("/web/sw.js").catch(()=>{});
    await renderRoute();
  });
})();