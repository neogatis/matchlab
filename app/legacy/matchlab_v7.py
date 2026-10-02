import os, json, sqlite3, hashlib, hmac, secrets, base64, urllib.parse, urllib.request, datetime, math, re
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http import cookies

VERSION="7.0"
PORT=int(os.getenv("PORT") or os.getenv("MATCH_PORT") or "8080")
DATA_DIR=os.getenv("MATCH_DATA_DIR","/app/data")
os.makedirs(DATA_DIR, exist_ok=True)
DB=os.path.join(DATA_DIR,"matchlab_prelaunch_v7.db")
OPENAI_API_KEY=os.getenv("OPENAI_API_KEY","")
OPENAI_MODEL=os.getenv("OPENAI_MODEL","gpt-5-mini")
ADMIN_KEY=os.getenv("ADMIN_IMPORT_KEY") or os.getenv("MATCH_ADMIN_KEY") or "change-me"
BASE_URL=os.getenv("PUBLIC_URL","https://rin-production-4899.up.railway.app")
PRELAUNCH_DEFAULT=os.getenv("PRE_LAUNCH_MODE","true").lower() in ("1","true","yes","on")

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def age_from_dob(dob):
    try:
        d=datetime.date.fromisoformat(dob)
        t=datetime.date.today()
        return t.year-d.year-((t.month,t.day)<(d.month,d.day))
    except Exception:
        return -1

def db():
    c=sqlite3.connect(DB, timeout=20)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    c=db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL,
      referral_code TEXT UNIQUE NOT NULL,
      referred_by INTEGER,
      invites_sent INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS sessions(
      token TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS profiles(
      user_id INTEGER PRIMARY KEY,
      display_name TEXT DEFAULT '',
      dob TEXT DEFAULT '',
      gender TEXT DEFAULT '',
      seek_gender TEXT DEFAULT '',
      city TEXT DEFAULT '',
      relationship_status TEXT DEFAULT 'PAUSED',
      eligibility_status TEXT DEFAULT 'NOT_ACTIVE_FOR_MATCHING',
      dating_goal TEXT DEFAULT '',
      readiness_chat TEXT DEFAULT '',
      readiness_offline TEXT DEFAULT '',
      readiness_score INTEGER DEFAULT 0,
      bio TEXT DEFAULT '',
      height INTEGER,
      smoking TEXT DEFAULT '',
      alcohol TEXT DEFAULT '',
      lifestyle TEXT DEFAULT '',
      religion TEXT DEFAULT '',
      nationality TEXT DEFAULT '',
      children_attitude TEXT DEFAULT '',
      children_plans TEXT DEFAULT '',
      questionnaire_completed INTEGER DEFAULT 0,
      profile_completed INTEGER DEFAULT 0,
      status_confirmed_at TEXT,
      updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS criteria(
      user_id INTEGER PRIMARY KEY,
      data TEXT NOT NULL DEFAULT '{}',
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS answers(
      user_id INTEGER NOT NULL,
      qid INTEGER NOT NULL,
      value INTEGER NOT NULL,
      PRIMARY KEY(user_id,qid)
    );
    CREATE TABLE IF NOT EXISTS photos(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      mime TEXT NOT NULL,
      data TEXT NOT NULL,
      is_main INTEGER NOT NULL DEFAULT 0,
      moderation_status TEXT NOT NULL DEFAULT 'PENDING',
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS likes(
      from_user INTEGER NOT NULL,
      to_user INTEGER NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY(from_user,to_user)
    );
    CREATE TABLE IF NOT EXISTS matches(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user1 INTEGER NOT NULL,
      user2 INTEGER NOT NULL,
      compatibility_score INTEGER NOT NULL,
      mutual_fit_score INTEGER NOT NULL,
      created_at TEXT NOT NULL,
      UNIQUE(user1,user2)
    );
    CREATE TABLE IF NOT EXISTS messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      match_id INTEGER NOT NULL,
      sender INTEGER NOT NULL,
      body TEXT NOT NULL,
      created_at TEXT NOT NULL,
      read_at TEXT
    );
    CREATE TABLE IF NOT EXISTS date_proposals(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      match_id INTEGER NOT NULL,
      proposer INTEGER NOT NULL,
      format TEXT NOT NULL,
      when_text TEXT NOT NULL,
      district TEXT DEFAULT '',
      budget TEXT DEFAULT '',
      note TEXT DEFAULT '',
      status TEXT NOT NULL DEFAULT 'PENDING',
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS blocks(
      blocker INTEGER NOT NULL,
      blocked INTEGER NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY(blocker,blocked)
    );
    CREATE TABLE IF NOT EXISTS reports(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      reporter INTEGER NOT NULL,
      target_user INTEGER,
      photo_id INTEGER,
      reason TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS attribution(
      user_id INTEGER PRIMARY KEY,
      utm_source TEXT DEFAULT '',
      utm_medium TEXT DEFAULT '',
      utm_campaign TEXT DEFAULT '',
      utm_content TEXT DEFAULT '',
      utm_term TEXT DEFAULT '',
      referral_input TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS notifications(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      kind TEXT NOT NULL,
      text TEXT NOT NULL,
      created_at TEXT NOT NULL,
      read_at TEXT
    );
    CREATE TABLE IF NOT EXISTS settings(
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      event_type TEXT NOT NULL,
      meta TEXT DEFAULT '{}',
      created_at TEXT NOT NULL
    );
    """)
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('PRE_LAUNCH_MODE',?)", ("true" if PRELAUNCH_DEFAULT else "false",))
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('PRELAUNCH_MATCHING_ENABLED','false')")
    c.commit(); c.close()

init_db()

SECTIONS=[
("Обо мне",[
"Мне легко описать, какой образ жизни подходит мне лучше всего.",
"Я понимаю, какие качества в себе считаю сильными.",
"Мне комфортно открыто рассказывать о своих привычках.",
"Я обычно понимаю, чего хочу от ближайших лет жизни."
]),
("Характер",[
"Я скорее спокоен(на), чем импульсивен(на).",
"Мне легко адаптироваться к неожиданным изменениям.",
"Я предпочитаю доводить начатое до конца.",
"Я склонен(на) принимать решения обдуманно."
]),
("Ценности",[
"Для меня принципиально важна честность даже в неудобных разговорах.",
"Верность договорённостям для меня важнее сиюминутных эмоций.",
"Мне важно, чтобы партнёр уважал мои убеждения.",
"Я готов(а) пересматривать своё мнение, если слышу сильные аргументы."
]),
("Отношения",[
"Я хочу строить отношения как команду.",
"Мне важны регулярные проявления внимания и заботы.",
"Я предпочитаю заранее обсуждать ожидания от отношений.",
"Для меня важно сохранять романтику и после периода влюблённости."
]),
("Семья",[
"Я хочу, чтобы партнёр был включён в семейную жизнь.",
"Мне важно поддерживать хорошие отношения с близкими партнёра.",
"Семейные традиции для меня имеют значение.",
"Я готов(а) совместно принимать решения о быте и семье."
]),
("Дети",[
"Я хочу детей в будущем.",
"Мне важно заранее совпадать во взглядах на воспитание детей.",
"Я готов(а) менять часть привычного образа жизни ради семьи с детьми.",
"Я считаю тему детей одной из ключевых для долгосрочных отношений."
]),
("Работа и амбиции",[
"Профессиональный рост для меня важен.",
"Я поддержу партнёра, если его работа временно требует больше времени.",
"Мне важно иметь собственные цели помимо отношений.",
"Я хочу, чтобы у партнёра были личные планы и амбиции."
]),
("Деньги",[
"Мне комфортно открыто обсуждать деньги с партнёром.",
"Я предпочитаю планировать крупные расходы заранее.",
"Для меня важно иметь финансовую подушку.",
"Я считаю, что долги и кредиты стоит обсуждать до серьёзных совместных решений."
]),
("Образ жизни",[
"Мне нравится регулярно заниматься физической активностью.",
"Мне важен похожий режим сна и бодрствования у партнёра.",
"Я предпочитаю активный отдых пассивному.",
"Мне важно, чтобы бытовые привычки партнёров были совместимы."
]),
("Социальность",[
"Мне нравится часто встречаться с друзьями.",
"Мне комфортно знакомиться с новыми людьми.",
"Я люблю мероприятия и компании.",
"Мне важно, чтобы партнёр спокойно относился к моей отдельной социальной жизни."
]),
("Личное пространство",[
"Мне необходимо регулярно проводить время наедине с собой.",
"Я спокойно отношусь к тому, что у партнёра есть отдельные интересы.",
"Мне не нужен постоянный контакт в течение всего дня.",
"Я считаю нормальным иметь часть личного пространства даже в близких отношениях."
]),
("Конфликты",[
"В конфликте я стараюсь обсуждать проблему без оскорблений.",
"Мне важно не откладывать серьёзные разногласия надолго.",
"Я умею признавать свою ошибку и извиняться.",
"После ссоры мне проще восстановить контакт через спокойный разговор."
]),
("Эмоциональная близость",[
"Мне важно регулярно говорить о чувствах.",
"Я хочу чувствовать эмоциональную поддержку партнёра.",
"Мне комфортно показывать уязвимость близкому человеку.",
"Мне важно понимать эмоциональное состояние партнёра."
]),
("Интересы",[
"Мне нравится пробовать новые занятия вместе с партнёром.",
"Совместные хобби для меня важны.",
"Мне интересно узнавать увлечения партнёра, даже если они не мои.",
"Я хочу регулярно планировать совместный досуг."
]),
("Привычки",[
"Мне важен умеренный или отсутствующий уровень курения и алкоголя в паре.",
"Я ценю порядок и предсказуемость в бытовых привычках.",
"Мне важно обсуждать привычки, которые могут раздражать партнёра.",
"Я готов(а) менять некоторые привычки ради комфортной совместной жизни."
]),
("Жизненные планы",[
"Я хочу заранее обсуждать город и страну, где мы будем жить.",
"Мне важно совпадать в представлении о темпе развития отношений.",
"Я готов(а) планировать совместное будущее на несколько лет вперёд.",
"Я хочу, чтобы ключевые жизненные решения принимались совместно."
])
]
QUESTIONS=[]
qid=1
for sec, arr in SECTIONS:
    for q in arr:
        QUESTIONS.append({"id":qid,"section":sec,"text":q}); qid+=1
assert len(QUESTIONS)==64 and len({q["text"] for q in QUESTIONS})==64

LIKERT=["Совсем не про меня","Скорее не про меня","Нейтрально","Скорее про меня","Полностью про меня"]

def hash_password(pw, salt=None):
    salt=salt or secrets.token_bytes(16)
    d=hashlib.pbkdf2_hmac("sha256",pw.encode(),salt,180000)
    return base64.b64encode(salt+d).decode()

def check_password(pw, stored):
    try:
        raw=base64.b64decode(stored); salt,d=raw[:16],raw[16:]
        test=hashlib.pbkdf2_hmac("sha256",pw.encode(),salt,180000)
        return hmac.compare_digest(test,d)
    except Exception:return False

def setting(c,key,default=""):
    r=c.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
    return r["value"] if r else default

def log_event(c,uid,typ,meta=None):
    c.execute("INSERT INTO events(user_id,event_type,meta,created_at) VALUES(?,?,?,?)",(uid,typ,json.dumps(meta or {},ensure_ascii=False),now()))

def status_from_screen(rel,openv):
    if rel=="YES": return ("IN_RELATIONSHIP","NOT_ACTIVE_FOR_MATCHING")
    if openv=="ACTIVE": return ("ACTIVE_SEARCH","ACTIVE_FOR_MATCHING")
    if openv=="OPEN": return ("OPEN_TO_MATCH","ACTIVE_FOR_MATCHING")
    if openv=="UNSURE": return ("PAUSED","NOT_ACTIVE_FOR_MATCHING")
    return ("NOT_ACTIVE","NOT_ACTIVE_FOR_MATCHING")

def readiness(chat,offline):
    a={"YES":60,"RATHER_YES":42,"LOOK_ONLY":12}.get(chat,0)
    b={"YES":40,"MAYBE":24,"NO":0}.get(offline,0)
    return max(0,min(100,a+b))

def active_matchable_row(p):
    if not p:return False
    if age_from_dob(p["dob"])<18:return False
    if p["relationship_status"] in ("PAUSED","IN_RELATIONSHIP","NOT_ACTIVE"):return False
    if p["eligibility_status"]!="ACTIVE_FOR_MATCHING":return False
    if not p["profile_completed"]:return False
    return True

def get_profile(c,uid):
    return c.execute("SELECT * FROM profiles WHERE user_id=?",(uid,)).fetchone()

def get_criteria(c,uid):
    r=c.execute("SELECT data FROM criteria WHERE user_id=?",(uid,)).fetchone()
    try:return json.loads(r["data"]) if r else {}
    except:return {}

def photo_count(c,uid):
    return c.execute("SELECT COUNT(*) n FROM photos WHERE user_id=?",(uid,)).fetchone()["n"]

def answers_count(c,uid):
    return c.execute("SELECT COUNT(*) n FROM answers WHERE user_id=?",(uid,)).fetchone()["n"]

def recompute_completion(c,uid):
    p=get_profile(c,uid)
    q=answers_count(c,uid); ph=photo_count(c,uid)
    basic=bool(p and p["display_name"] and p["dob"] and p["gender"] and p["seek_gender"] and p["city"] and p["dating_goal"])
    crit=bool(get_criteria(c,uid))
    completed=int(basic and crit and q==64 and ph>=2)
    c.execute("UPDATE profiles SET questionnaire_completed=?,profile_completed=?,updated_at=? WHERE user_id=?",(int(q==64),completed,now(),uid))
    return completed

def public_profile(c,uid,viewer=None):
    p=get_profile(c,uid)
    if not p:return None
    main=c.execute("SELECT id,data,mime FROM photos WHERE user_id=? ORDER BY is_main DESC,id LIMIT 1",(uid,)).fetchone()
    return {
      "user_id":uid,"display_name":p["display_name"],"age":age_from_dob(p["dob"]),"gender":p["gender"],
      "city":p["city"],"bio":p["bio"],"dating_goal":p["dating_goal"],"readiness_score":p["readiness_score"],
      "photo":(("data:"+main["mime"]+";base64,"+main["data"]) if main else None)
    }

def normalize_goal(x):
    m={"SERIOUS":"serious","FAMILY":"family","SEE":"see","CHAT":"chat","UNKNOWN":"unknown"}
    return m.get(x,x or "")

def hard_pass(c,a,b):
    pa,pb=get_profile(c,a),get_profile(c,b)
    if not pa or not pb or not active_matchable_row(pa) or not active_matchable_row(pb): return False
    if pa["seek_gender"] not in ("ANY",pb["gender"]): return False
    if pb["seek_gender"] not in ("ANY",pa["gender"]): return False
    if c.execute("SELECT 1 FROM blocks WHERE (blocker=? AND blocked=?) OR (blocker=? AND blocked=?)",(a,b,b,a)).fetchone(): return False
    ca,cb=get_criteria(c,a),get_criteria(c,b)
    def one(criteria,target):
        tp=get_profile(c,target); ta=age_from_dob(tp["dob"])
        for key in ("age","city","goal","children_attitude","children_plans","smoking","alcohol","lifestyle","religion","nationality","height"):
            spec=criteria.get(key,{})
            if spec.get("importance")!="REQUIRED": continue
            if key=="age":
                mn=int(spec.get("min") or 18); mx=int(spec.get("max") or 99)
                if not (mn<=ta<=mx): return False
            elif key=="city":
                wanted=(spec.get("value") or "").strip().lower()
                allow_other=bool(spec.get("allow_other_city"))
                if wanted and tp["city"].strip().lower()!=wanted and not allow_other:return False
            elif key=="height":
                mn=int(spec.get("min") or 0); mx=int(spec.get("max") or 999)
                h=int(tp["height"] or 0)
                if h and not(mn<=h<=mx):return False
            else:
                val=(spec.get("value") or "").strip().lower()
                actual=str(tp[key] or "").strip().lower()
                if val and val!="any" and val!=actual:return False
        return True
    return one(ca,b) and one(cb,a)

def answer_map(c,uid):
    return {r["qid"]:r["value"] for r in c.execute("SELECT qid,value FROM answers WHERE user_id=?",(uid,))}

def compatibility(c,a,b):
    aa,bb=answer_map(c,a),answer_map(c,b)
    common=set(aa)&set(bb)
    if not common:return (0,0,{})
    sims=[100-25*abs(aa[i]-bb[i]) for i in common]
    base=sum(sims)/len(sims)
    pa,pb=get_profile(c,a),get_profile(c,b)
    goal_bonus=100 if pa["dating_goal"]==pb["dating_goal"] else (75 if {pa["dating_goal"],pb["dating_goal"]}<={"SERIOUS","FAMILY","SEE"} else 45)
    score=round(base*.85+goal_bonus*.15)
    readiness_factor=.78+.22*(min(pa["readiness_score"],pb["readiness_score"])/100)
    mutual=round(score*readiness_factor)
    by={}
    for sec,_ in SECTIONS:
        ids=[q["id"] for q in QUESTIONS if q["section"]==sec and q["id"] in common]
        if ids:by[sec]=round(sum(100-25*abs(aa[i]-bb[i]) for i in ids)/len(ids))
    return score,mutual,by


HTML=r"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MatchLab — знакомства по совместимости</title>
<style>
:root{--bg:#171514;--panel:#24201f;--panel2:#2e2927;--text:#f7f2ec;--muted:#b9afa8;--line:#463d39;--p:#a978f5;--c:#ff8c7a;--ok:#55d4a8;--warn:#ffcc74}
*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,Arial;background:radial-gradient(circle at 20% 0,#332624,#171514 35%);color:var(--text)}
button,input,select,textarea{font:inherit}.wrap{max-width:1120px;margin:auto;padding:24px}.top{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 0 26px}.brand{font-size:28px;font-weight:800}.brand b{background:linear-gradient(90deg,var(--p),var(--c));-webkit-background-clip:text;color:transparent}.nav{display:flex;gap:8px;flex-wrap:wrap}.nav button,.ghost{border:1px solid var(--line);background:#211e1d;color:var(--text);padding:10px 14px;border-radius:14px;cursor:pointer}.nav button.active{background:#3a3230}.hero,.card{background:linear-gradient(145deg,#2b2523,#1f1c1b);border:1px solid #433a36;border-radius:26px;padding:28px;box-shadow:0 20px 50px #0005}.hero{padding:52px;min-height:420px;display:grid;align-content:center}.hero h1{font-size:54px;line-height:1.02;margin:0 0 18px;max-width:800px}.hero p{font-size:20px;color:var(--muted);max-width:720px}.primary{border:0;background:linear-gradient(90deg,var(--p),var(--c));color:#161214;font-weight:800;padding:15px 22px;border-radius:16px;cursor:pointer}.muted{color:var(--muted)}.small{font-size:13px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.full{grid-column:1/-1}.field{display:grid;gap:8px;margin:12px 0}.field label{font-weight:700}.field input,.field select,.field textarea{width:100%;background:#151313;border:1px solid var(--line);color:var(--text);padding:13px 14px;border-radius:14px}.pill{display:inline-flex;padding:7px 11px;border-radius:999px;background:#3a2f46;color:#e6d5ff;font-size:13px}.progress{height:10px;background:#171414;border-radius:99px;overflow:hidden}.progress i{display:block;height:100%;background:linear-gradient(90deg,var(--p),var(--c))}.options{display:grid;gap:10px;margin:18px 0}.opt{padding:14px;border:1px solid var(--line);border-radius:14px;cursor:pointer;background:#191716}.opt.sel{border-color:var(--p);background:#2b2033}.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.between{justify-content:space-between}.section-title{font-size:30px;margin:0 0 8px}.notice{padding:14px;border-radius:14px;background:#2a2521;border:1px solid #51463f}.ok{color:var(--ok)}.warn{color:var(--warn)}.hidden{display:none!important}.photo-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}.photo{position:relative;aspect-ratio:1;border-radius:18px;overflow:hidden;background:#111}.photo img{width:100%;height:100%;object-fit:cover}.photo .tag{position:absolute;left:8px;bottom:8px;background:#000b;padding:5px 8px;border-radius:9px;font-size:12px}.criteria{display:grid;gap:16px}.crit{border:1px solid var(--line);padding:16px;border-radius:18px}.metric{background:#181616;border:1px solid var(--line);padding:16px;border-radius:16px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.big{font-size:32px;font-weight:800}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:10px;border-bottom:1px solid var(--line);text-align:left}.wait{text-align:center;padding:46px}.result-bars{display:grid;gap:12px}.barrow{display:grid;grid-template-columns:220px 1fr 60px;gap:12px;align-items:center}.bar{height:10px;background:#181515;border-radius:99px;overflow:hidden}.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--p),var(--c))}
@media(max-width:800px){.wrap{padding:14px}.hero{padding:28px}.hero h1{font-size:38px}.grid,.metrics{grid-template-columns:1fr}.barrow{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}}
</style></head><body><div class="wrap"><div class="top"><div class="brand">Match<b>Lab</b></div><div class="nav" id="nav"></div></div><main id="app"></main></div>
<script>
const S={me:null,step:0,questions:[],answers:{},criteria:{},utm:{}};
const $=s=>document.querySelector(s), app=()=>$("#app");
async function api(url,opt={}){opt.headers={...(opt.headers||{}),"Content-Type":"application/json"};let r=await fetch(url,opt);let j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||"Ошибка");return j}
function esc(s){return String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]))}
function nav(){let n=$("#nav"); if(!S.me){n.innerHTML="";return} n.innerHTML=`<button onclick="showProfile()">Профиль</button><button onclick="showWaitlist()">Подбор</button><button onclick="showMatches()">Мэтчи и чаты</button><button onclick="showSettings()">Настройки</button><button onclick="logout()">Выйти</button>`}
function hero(){app().innerHTML=`<section class="hero"><span class="pill">PRE-LAUNCH · Алматы</span><h1>Знакомства без бесконечных свайпов</h1><p>Расскажите о себе. Мы будем искать среди участников людей, которые действительно подходят вам.</p><div><button class="primary" onclick="showRegister()">Пройти анкету</button></div><p class="small muted">18+. Ваш профиль не публикуется в открытом каталоге.</p></section>`}
function showRegister(){app().innerHTML=`<section class="card"><h2 class="section-title">Регистрация и первичный отбор</h2><p class="muted">Сначала проверим, подходит ли ваш профиль для базы знакомств.</p><div class="grid">
<div class="field"><label>Email</label><input id="email" type="email"></div><div class="field"><label>Пароль</label><input id="pass" type="password"></div>
<div class="field"><label>Имя</label><input id="name"></div><div class="field"><label>Дата рождения</label><input id="dob" type="date"></div>
<div class="field"><label>Пол</label><select id="gender"><option value="">Выберите</option><option value="M">Мужчина</option><option value="F">Женщина</option><option value="OTHER">Другое</option></select></div>
<div class="field"><label>Кого хотите встретить?</label><select id="seek"><option value="">Выберите</option><option value="M">Мужчину</option><option value="F">Женщину</option><option value="ANY">Неважно</option></select></div>
<div class="field"><label>Город проживания</label><input id="city" value="Алматы"></div>
<div class="field"><label>Вы сейчас состоите в отношениях?</label><select id="rel"><option value="NO">Нет</option><option value="YES">Да</option></select></div>
<div class="field full"><label>Вы открыты к новым знакомствам?</label><select id="open"><option value="ACTIVE">Да, активно ищу</option><option value="OPEN">Да, если встречу подходящего человека</option><option value="UNSURE">Пока не уверен(а)</option><option value="NO">Нет</option></select></div>
</div><div class="row"><button class="primary" onclick="register()">Продолжить</button><button class="ghost" onclick="showLogin()">У меня уже есть аккаунт</button></div><div id="err" class="warn"></div></section>`}
function showLogin(){app().innerHTML=`<section class="card" style="max-width:560px;margin:auto"><h2>Вход</h2><div class="field"><label>Email</label><input id="email"></div><div class="field"><label>Пароль</label><input id="pass" type="password"></div><button class="primary" onclick="login()">Войти</button><div id="err" class="warn"></div></section>`}
async function register(){try{let q=new URLSearchParams(location.search);let body={email:$("#email").value,password:$("#pass").value,display_name:$("#name").value,dob:$("#dob").value,gender:$("#gender").value,seek_gender:$("#seek").value,city:$("#city").value,relationship:$("#rel").value,open_to:$("#open").value,utm_source:q.get("utm_source")||"",utm_medium:q.get("utm_medium")||"",utm_campaign:q.get("utm_campaign")||"",utm_content:q.get("utm_content")||"",utm_term:q.get("utm_term")||"",ref:q.get("ref")||""};let r=await api("/api/register",{method:"POST",body:JSON.stringify(body)});S.me=r.me;nav();showBasics()}catch(e){$("#err").textContent=e.message}}
async function login(){try{let r=await api("/api/login",{method:"POST",body:JSON.stringify({email:$("#email").value,password:$("#pass").value})});S.me=r.me;nav();routeAfterLogin()}catch(e){$("#err").textContent=e.message}}
async function logout(){await api("/api/logout",{method:"POST",body:"{}"});S.me=null;nav();hero()}
async function loadMe(){try{let r=await api("/api/me");S.me=r.me;nav();if(S.me)routeAfterLogin();else hero()}catch(e){hero()}}
function routeAfterLogin(){if(S.me.needs_status_check)return showStatusCheck();if(!S.me.profile||!S.me.profile.dating_goal)showBasics();else if(!S.me.criteria_complete)showCriteria();else if(S.me.answer_count<64)startQuestions();else if(S.me.photo_count<2)showPhotos();else showProfile()}
function showStatusCheck(){app().innerHTML=`<section class="card wait"><h2>Вы всё ещё открыты к знакомствам?</h2><p class="muted">Мы периодически уточняем статус, чтобы в подборе были только актуальные анкеты.</p><div class="row" style="justify-content:center"><button class="primary" onclick="quickStatus('ACTIVE_SEARCH')">Да</button><button class="ghost" onclick="quickStatus('PAUSED')">Поставить профиль на паузу</button><button class="ghost" onclick="quickStatus('IN_RELATIONSHIP')">Я сейчас в отношениях</button></div></section>`}
async function quickStatus(st){let r=await api("/api/status",{method:"POST",body:JSON.stringify({status:st})});S.me=r.me;routeAfterLogin()}
function showBasics(){let p=S.me.profile||{};app().innerHTML=`<section class="card"><h2 class="section-title">О вас</h2><p class="muted">Эти данные помогают считать совместимость и взаимные фильтры.</p><div class="grid">
<div class="field"><label>Что вы хотите найти?</label><select id="goal"><option value="SERIOUS">Серьёзные отношения</option><option value="FAMILY">Отношения с перспективой семьи</option><option value="SEE">Познакомиться и посмотреть, что получится</option><option value="CHAT">Общение</option><option value="UNKNOWN">Пока не знаю</option></select></div>
<div class="field"><label>Рост, см</label><input id="height" type="number" min="120" max="230"></div>
<div class="field"><label>Курение</label><select id="smoking"><option>Не курю</option><option>Иногда</option><option>Курю</option></select></div>
<div class="field"><label>Алкоголь</label><select id="alcohol"><option>Не употребляю</option><option>Редко</option><option>Умеренно</option></select></div>
<div class="field"><label>Образ жизни</label><select id="lifestyle"><option>Активный</option><option>Сбалансированный</option><option>Спокойный</option></select></div>
<div class="field"><label>Национальность</label><input id="nationality"></div>
<div class="field"><label>Религия</label><input id="religion"></div>
<div class="field"><label>Отношение к детям</label><select id="childatt"><option>Положительно</option><option>Нейтрально</option><option>Не хочу детей</option></select></div>
<div class="field"><label>Планы на детей</label><select id="childplan"><option>Хочу</option><option>Возможно</option><option>Не хочу</option><option>Уже есть и больше не планирую</option></select></div>
<div class="field full"><label>Пара предложений о себе</label><textarea id="bio" rows="4"></textarea></div></div>
<h3>Готовность к знакомству</h3><div class="grid"><div class="field"><label>Если мы найдём подходящего человека, вы готовы начать общение?</label><select id="rch"><option value="YES">Да</option><option value="RATHER_YES">Скорее да</option><option value="LOOK_ONLY">Пока только хочу посмотреть результаты</option></select></div><div class="field"><label>Если общение пойдёт хорошо, готовы встретиться офлайн?</label><select id="roff"><option value="YES">Да</option><option value="MAYBE">Возможно</option><option value="NO">Нет</option></select></div></div>
<button class="primary" onclick="saveBasics()">Дальше: критерии партнёра</button><div id="err" class="warn"></div></section>`}
async function saveBasics(){try{let b={dating_goal:$("#goal").value,height:+$("#height").value||null,smoking:$("#smoking").value,alcohol:$("#alcohol").value,lifestyle:$("#lifestyle").value,nationality:$("#nationality").value,religion:$("#religion").value,children_attitude:$("#childatt").value,children_plans:$("#childplan").value,bio:$("#bio").value,readiness_chat:$("#rch").value,readiness_offline:$("#roff").value};let r=await api("/api/profile",{method:"POST",body:JSON.stringify(b)});S.me=r.me;showCriteria()}catch(e){$("#err").textContent=e.message}}
function imp(id){return `<select id="${id}"><option value="REQUIRED">ОБЯЗАТЕЛЬНО</option><option value="IMPORTANT" selected>ВАЖНО</option><option value="UNIMPORTANT">НЕВАЖНО</option></select>`}
function showCriteria(){app().innerHTML=`<section class="card"><h2 class="section-title">Критерии партнёра</h2><p class="muted">Обязательные критерии станут hard filters. Другим пользователям ваши требования не показываются.</p><div class="criteria">
<div class="crit"><b>Возраст партнёра</b><div class="grid"><div class="field"><label>От</label><input id="amin" type="number" value="24"></div><div class="field"><label>До</label><input id="amax" type="number" value="35"></div><div class="field full"><label>Важность</label>${imp("ai")}</div></div></div>
<div class="crit"><b>Город</b><div class="grid"><div class="field"><input id="pcity" value="Алматы"></div><div class="field"><label><input id="othercity" type="checkbox"> Допустим другой город</label></div><div class="field full"><label>Важность</label>${imp("ci")}</div></div></div>
<div class="crit"><b>Цель отношений</b><div class="grid"><div class="field"><select id="pgoal"><option value="SERIOUS">Серьёзные отношения</option><option value="FAMILY">Отношения с перспективой семьи</option><option value="SEE">Посмотреть, что получится</option><option value="CHAT">Общение</option><option value="ANY">Неважно</option></select></div><div class="field">${imp("gi")}</div></div></div>
${critSelect("Отношение к детям","catt","Положительно|Нейтрально|Не хочу детей")}
${critSelect("Планы на детей","cplan","Хочу|Возможно|Не хочу|Уже есть и больше не планирую")}
${critSelect("Курение","smk","Не курю|Иногда|Курю|ANY")}
${critSelect("Алкоголь","alc","Не употребляю|Редко|Умеренно|ANY")}
${critSelect("Образ жизни","life","Активный|Сбалансированный|Спокойный|ANY")}
<div class="crit"><b>Религия</b><div class="grid"><div class="field"><input id="prel"></div><div class="field">${imp("reli")}</div></div></div>
<div class="crit"><b>Национальность</b><p class="small muted">Добровольный предпочтительный параметр.</p><div class="grid"><div class="field"><input id="pnat"></div><div class="field">${imp("nati")}</div></div></div>
<div class="crit"><b>Рост</b><div class="grid"><div class="field"><input id="hmin" type="number" placeholder="от"></div><div class="field"><input id="hmax" type="number" placeholder="до"></div><div class="field full">${imp("hi")}</div></div></div>
<div class="crit"><b>Другие важные критерии</b><textarea id="other" rows="3" placeholder="Что ещё для вас важно?"></textarea><div class="field"><label>Важность</label>${imp("otheri")}</div><p class="small muted">Свободный текст сохраняется приватно. Для автоматического hard filter используются структурированные критерии выше.</p></div>
</div><br><button class="primary" onclick="saveCriteria()">Дальше: полная анкета</button><div id="err" class="warn"></div></section>`}
function critSelect(label,id,vals){return `<div class="crit"><b>${label}</b><div class="grid"><div class="field"><select id="${id}">${vals.split("|").map(v=>`<option>${v}</option>`).join("")}</select></div><div class="field">${imp(id+"i")}</div></div></div>`}
async function saveCriteria(){try{let d={age:{min:+$("#amin").value,max:+$("#amax").value,importance:$("#ai").value},city:{value:$("#pcity").value,allow_other_city:$("#othercity").checked,importance:$("#ci").value},goal:{value:$("#pgoal").value,importance:$("#gi").value},children_attitude:{value:$("#catt").value,importance:$("#catti").value},children_plans:{value:$("#cplan").value,importance:$("#cplani").value},smoking:{value:$("#smk").value,importance:$("#smki").value},alcohol:{value:$("#alc").value,importance:$("#alci").value},lifestyle:{value:$("#life").value,importance:$("#lifei").value},religion:{value:$("#prel").value,importance:$("#reli").value},nationality:{value:$("#pnat").value,importance:$("#nati").value},height:{min:+$("#hmin").value||0,max:+$("#hmax").value||999,importance:$("#hi").value},other:{value:$("#other").value,importance:$("#otheri").value}};let r=await api("/api/criteria",{method:"POST",body:JSON.stringify(d)});S.me=r.me;startQuestions()}catch(e){$("#err").textContent=e.message}}
async function startQuestions(){let r=await api("/api/questions");S.questions=r.questions;S.answers=r.answers||{};S.step=Object.keys(S.answers).length;showQuestion()}
function showQuestion(){let i=Math.min(S.step,63),q=S.questions[i],pct=Math.round((Object.keys(S.answers).length/64)*100);app().innerHTML=`<section class="card"><div class="row between"><span class="pill">${esc(q.section)}</span><b>${pct}%</b></div><div class="progress"><i style="width:${pct}%"></i></div><p class="muted">Анкета заполнена на ${pct}% · Вопрос ${i+1} из 64</p><h2 class="section-title">${esc(q.text)}</h2><div class="options">${["Совсем не про меня","Скорее не про меня","Нейтрально","Скорее про меня","Полностью про меня"].map((x,k)=>`<div class="opt ${S.answers[q.id]==k+1?"sel":""}" onclick="answerQ(${q.id},${k+1})">${esc(x)}</div>`).join("")}</div><div class="row between"><button class="ghost" onclick="prevQ()">Назад</button><button class="primary" onclick="nextQ()">Далее</button></div></section>`}
async function answerQ(id,v){S.answers[id]=v;await api("/api/answer",{method:"POST",body:JSON.stringify({qid:id,value:v})});showQuestion()}
function prevQ(){S.step=Math.max(0,S.step-1);showQuestion()} function nextQ(){if(!S.answers[S.questions[S.step].id])return alert("Выберите ответ");if(S.step<63){S.step++;showQuestion()}else showPhotos()}
async function showPhotos(){let r=await api("/api/photos");app().innerHTML=`<section class="card"><h2 class="section-title">Фотографии</h2><p>Минимум 2 фотографии. Рекомендуется 3–5. Первое фото становится главным.</p><div class="photo-grid">${r.photos.map(x=>`<div class="photo"><img src="${x.src}"><span class="tag">${x.is_main?"Главное":"Фото"}</span><button class="ghost" style="position:absolute;right:6px;top:6px;padding:5px 8px" onclick="delPhoto(${x.id})">×</button><button class="ghost" style="position:absolute;right:6px;bottom:6px;padding:5px 8px" onclick="mainPhoto(${x.id})">★</button></div>`).join("")}</div><div class="field"><label>Добавить фото</label><input id="file" type="file" accept="image/*" onchange="uploadPhoto(this)"></div><p class="small muted">Фото попадает в очередь модерации. Можно удалить или сменить главное.</p><button class="primary" onclick="finishProfile()">Завершить профиль</button><div id="err" class="warn"></div></section>`}
async function uploadPhoto(inp){let file=inp.files[0];if(!file)return;let rd=new FileReader();rd.onload=async()=>{try{let s=rd.result.split(",")[1];await api("/api/photos",{method:"POST",body:JSON.stringify({mime:file.type,data:s})});showPhotos()}catch(e){alert(e.message)}};rd.readAsDataURL(file)}
async function delPhoto(id){await api("/api/photos/"+id,{method:"DELETE"});showPhotos()} async function mainPhoto(id){await api("/api/photos/"+id+"/main",{method:"POST",body:"{}"});showPhotos()}
async function finishProfile(){try{let r=await api("/api/finish",{method:"POST",body:"{}"});S.me=r.me;showProfile()}catch(e){$("#err").textContent=e.message}}
async function showProfile(){let r=await api("/api/summary");S.me=r.me;let s=r.summary;app().innerHTML=`<section class="card"><span class="pill">Профиль готов</span><h2 class="section-title">Ваш профиль совместимости готов</h2><div class="result-bars">${Object.entries(s).map(([k,v])=>`<div class="barrow"><span>${esc(k)}</span><div class="bar"><i style="width:${v}%"></i></div><b>${v}%</b></div>`).join("")}</div><div class="notice" style="margin-top:22px">Сейчас мы ищем среди участников людей, которые подходят именно вам.</div><div class="row" style="margin-top:18px"><button class="primary" onclick="showWaitlist()">Посмотреть статус подбора</button><button class="ghost" onclick="showReferral()">Пригласить друга</button></div></section>`}
async function showWaitlist(){let r=await api("/api/feed");if(r.prelaunch&&!r.matching_enabled){app().innerHTML=`<section class="card wait"><span class="pill">WAITLIST</span><h2>Мы пока не нашли человека, который проходит ваши основные критерии.</h2><p class="muted">Ваш профиль активен. Мы сообщим, когда появится подходящий участник.</p><p class="small muted">В предзапуске случайные анкеты не показываются ради заполнения экрана.</p><button class="ghost" onclick="showReferral()">Пригласить друга пройти тест</button></section>`;return}if(!r.items.length){app().innerHTML=`<section class="card wait"><h2>Подходящих профилей пока нет</h2><p class="muted">Мы не будем показывать случайные анкеты. Ваш профиль остаётся активным.</p></section>`;return}app().innerHTML=`<section class="card"><h2>Подходящие профили</h2>${r.items.map(x=>`<div class="crit">${x.photo?`<img src="${x.photo}" style="width:160px;height:160px;object-fit:cover;border-radius:18px">`:""}<h3>${esc(x.display_name)}, ${x.age} · ${esc(x.city)}</h3><div class="big">${x.mutual_fit_score}%</div><p class="muted">Взаимная совместимость</p><div class="row"><button class="primary" onclick="like(${x.user_id})">Нравится</button><button class="ghost" onclick="reportPhoto(${x.user_id})">Пожаловаться на фото</button></div></div>`).join("")}</section>`}
async function like(id){let r=await api("/api/like",{method:"POST",body:JSON.stringify({target:id})});alert(r.match?"У вас новый мэтч!":"Лайк сохранён");showWaitlist()}
async function reportPhoto(id){let reason=prompt("Причина жалобы:");if(!reason)return;await api("/api/report-photo",{method:"POST",body:JSON.stringify({target_user:id,reason})});alert("Жалоба отправлена на модерацию.")}
function showSettings(){let p=S.me.profile;app().innerHTML=`<section class="card"><h2>Статус знакомств</h2><p class="muted">Если поставить паузу или указать отношения, профиль сразу исключается из новых подборов.</p><div class="field"><select id="st"><option value="ACTIVE_SEARCH">ACTIVE_SEARCH</option><option value="OPEN_TO_MATCH">OPEN_TO_MATCH</option><option value="PAUSED">PAUSED</option><option value="IN_RELATIONSHIP">IN_RELATIONSHIP</option><option value="NOT_ACTIVE">NOT_ACTIVE</option></select></div><button class="primary" onclick="saveStatus()">Сохранить</button></section>`;$("#st").value=p.relationship_status}
async function saveStatus(){let r=await api("/api/status",{method:"POST",body:JSON.stringify({status:$("#st").value})});S.me=r.me;alert("Статус обновлён")}
async function showReferral(){let r=await api("/api/referral");app().innerHTML=`<section class="card"><h2>Пригласите друга пройти тест</h2><p class="muted">Персональная ссылка:</p><div class="field"><input id="reflink" value="${esc(r.url)}" readonly></div><button class="primary" onclick="copyRef()">Скопировать приглашение</button><p>Регистраций по вашей ссылке: <b>${r.registered}</b><br>Полностью заполненных профилей: <b>${r.completed}</b></p></section>`}
async function copyRef(){navigator.clipboard.writeText($("#reflink").value);await api("/api/referral/invite",{method:"POST",body:"{}"});alert("Ссылка скопирована")}

async function showMatches(){let r=await api("/api/matches");app().innerHTML=`<section class="card"><h2>Мэтчи и чаты</h2>${r.items.length?r.items.map(x=>`<div class="crit"><div class="row between"><div><h3>${esc(x.profile.display_name)}, ${x.profile.age}</h3><div class="muted">${x.mutual_fit_score}% взаимная совместимость</div></div><button class="primary" onclick="openChat(${x.id})">Открыть чат${x.unread?` · ${x.unread}`:""}</button></div></div>`).join(""):`<p class="muted">Мэтчей пока нет.</p>`}</section>`}
async function openChat(mid){let r=await api("/api/chat?match_id="+mid);app().innerHTML=`<section class="card"><div class="row between"><h2>Чат с ${esc(r.other.display_name)}</h2><button class="ghost" onclick="proposeDate(${mid})">Предложить свидание</button></div><div style="display:grid;gap:8px;margin:18px 0">${r.messages.map(m=>`<div class="notice" style="margin-left:${m.mine?"18%":"0"};margin-right:${m.mine?"0":"18%"}">${esc(m.body)}<div class="small muted">${esc(m.created_at.slice(0,16).replace("T"," "))}</div></div>`).join("")}</div><div class="row"><input id="msg" style="flex:1;background:#151313;border:1px solid var(--line);color:white;padding:13px;border-radius:14px" placeholder="Сообщение"><button class="primary" onclick="sendMsg(${mid})">Отправить</button></div>${r.proposals.map(p=>`<div class="crit"><b>Свидание: ${esc(p.format)}</b><p>${esc(p.when_text)} · ${esc(p.district)} · ${esc(p.budget)}</p><p class="muted">${esc(p.note)}</p><b>${esc(p.status)}</b>${p.can_answer&&p.status=="PENDING"?`<div class="row"><button class="primary" onclick="dateAnswer(${p.id},'ACCEPTED',${mid})">Принять</button><button class="ghost" onclick="dateAnswer(${p.id},'DECLINED',${mid})">Отклонить</button></div>`:""}</div>`).join("")}</section>`}
async function sendMsg(mid){let b=$("#msg").value.trim();if(!b)return;await api("/api/message",{method:"POST",body:JSON.stringify({match_id:mid,body:b})});openChat(mid)}
function proposeDate(mid){app().innerHTML=`<section class="card"><h2>Предложить свидание</h2><div class="field"><label>Формат</label><select id="df"><option>Кофе</option><option>Ресторан</option><option>Прогулка</option><option>Активность</option><option>Бар</option><option>Кино</option></select></div><div class="field"><label>Когда</label><input id="dw" placeholder="Например: суббота, 19:00"></div><div class="field"><label>Район</label><input id="dd" placeholder="Алматы"></div><div class="field"><label>Бюджет</label><input id="db" placeholder="Например: до 20 000 ₸"></div><div class="field"><label>Комментарий</label><textarea id="dn"></textarea></div><button class="primary" onclick="sendDate(${mid})">Отправить предложение</button></section>`}
async function sendDate(mid){await api("/api/date-proposal",{method:"POST",body:JSON.stringify({match_id:mid,format:$("#df").value,when_text:$("#dw").value,district:$("#dd").value,budget:$("#db").value,note:$("#dn").value})});openChat(mid)}
async function dateAnswer(id,st,mid){await api("/api/date-proposal/respond",{method:"POST",body:JSON.stringify({proposal_id:id,status:st})});openChat(mid)}

loadMe();
</script></body></html>"""


def json_body(h):
    n=int(h.headers.get("Content-Length","0") or 0)
    if n>5_000_000: raise ValueError("Слишком большой запрос")
    raw=h.rfile.read(n) if n else b"{}"
    return json.loads(raw.decode("utf-8") or "{}")

def make_me(c,uid):
    p=get_profile(c,uid)
    u=c.execute("SELECT id,email,referral_code,invites_sent FROM users WHERE id=?",(uid,)).fetchone()
    needs=False
    if p and p["status_confirmed_at"]:
        try:
            dt=datetime.datetime.fromisoformat(p["status_confirmed_at"])
            needs=(datetime.datetime.now(datetime.timezone.utc)-dt).days>=30
        except Exception: needs=False
    return {
      "id":uid,"email":u["email"],"profile":dict(p) if p else None,
      "criteria_complete":bool(get_criteria(c,uid)),"answer_count":answers_count(c,uid),
      "photo_count":photo_count(c,uid),"referral_code":u["referral_code"],"needs_status_check":needs
    }

def summary_for(c,uid):
    a=answer_map(c,uid)
    def avg(sec):
        ids=[q["id"] for q in QUESTIONS if q["section"]==sec and q["id"] in a]
        if not ids:return 0
        return round(sum((a[i]-1)*25 for i in ids)/len(ids))
    return {
      "Ценности":avg("Ценности"),
      "Ориентация на семью":round((avg("Семья")+avg("Дети"))/2),
      "Потребность в близости":avg("Эмоциональная близость"),
      "Социальность":avg("Социальность"),
      "Амбициозность":avg("Работа и амбиции")
    }

def age_band(age):
    if age<24:return "18–23"
    if age<29:return "24–28"
    if age<36:return "29–35"
    if age<46:return "36–45"
    return "46+"

ADMIN_HTML=r"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MatchLab Admin</title>
<style>body{font-family:system-ui;background:#161414;color:#f6f1eb;margin:0}main{max-width:1200px;margin:auto;padding:24px}.card{background:#252120;border:1px solid #463d39;border-radius:22px;padding:22px;margin:14px 0}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.m{background:#1b1817;border-radius:14px;padding:14px}.big{font-size:30px;font-weight:800}input,button{padding:12px;border-radius:12px;border:1px solid #554944;background:#181515;color:white}button{cursor:pointer;background:#8f69de}.table{width:100%;border-collapse:collapse}.table td,.table th{padding:9px;border-bottom:1px solid #403936;text-align:left}.warn{color:#ffcc74}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style></head>
<body><main><h1>MatchLab · Audience Balance</h1><div class="card"><input id="key" type="password" placeholder="Admin key"><button onclick="load()">Открыть</button></div><div id="out"></div></main>
<script>
const E=s=>String(s??"").replace(/[&<>"]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[m]));
async function load(){let k=document.querySelector("#key").value,r=await fetch("/api/admin/dashboard?key="+encodeURIComponent(k)),j=await r.json();if(!r.ok)return alert(j.error||"Ошибка");let m=j.metrics,g=j.gaps,s=j.sources;document.querySelector("#out").innerHTML=`<div class="grid">${Object.entries(m).map(([a,b])=>`<div class="m"><div>${E(a)}</div><div class="big">${E(b)}</div></div>`).join("")}</div><div class="card"><h2>Audience Balance</h2><table class="table"><tr><th>Группа</th><th>Спрос</th><th>Предложение</th><th>Дефицит</th></tr>${g.map(x=>`<tr><td>${E(x.group)}</td><td>${x.demand}</td><td>${x.supply}</td><td class="${x.gap>0?"warn":""}">${x.gap}</td></tr>`).join("")}</table></div><div class="card"><h2>Распределение аудитории</h2><p><b>Возраст:</b> ${Object.entries(j.age_distribution).map(([k,v])=>E(k)+": "+v).join(" · ")||"нет данных"}</p><p><b>Города:</b> ${Object.entries(j.cities).map(([k,v])=>E(k)+": "+v).join(" · ")||"нет данных"}</p><p><b>Фото на модерации:</b> ${j.pending_photos} <button onclick="moderation()">Открыть очередь</button></p></div><div class="card"><h2>Кого сейчас не хватает в базе?</h2>${j.insights.map(x=>`<p>${E(x)}</p>`).join("")}</div><div class="card"><h2>Источники регистрации</h2><table class="table"><tr><th>Источник</th><th>Регистрации</th><th>Заполненные активные анкеты</th></tr>${s.map(x=>`<tr><td>${E(x.source)}</td><td>${x.registrations}</td><td>${x.completed_active}</td></tr>`).join("")}</table></div><div class="card"><h2>Настройки</h2><p>PRE_LAUNCH_MODE: <b>${j.prelaunch}</b></p><button onclick="toggle('${j.prelaunch=="true"?"false":"true"}')">Переключить PRE_LAUNCH_MODE</button></div>`}
async function moderation(){let k=document.querySelector("#key").value,r=await fetch("/api/admin/photos?key="+encodeURIComponent(k)),j=await r.json();if(!r.ok)return alert(j.error);document.querySelector("#out").innerHTML=`<div class="card"><h2>Модерация фото</h2>${j.items.length?j.items.map(x=>`<div class="m"><p>${E(x.email)} · ${E(x.name)} · фото #${x.id}</p><img src="${x.src}" style="width:180px;height:180px;object-fit:cover;border-radius:14px"><div><button onclick="photoDecision(${x.id},'APPROVED')">Одобрить</button> <button onclick="photoDecision(${x.id},'REJECTED')">Отклонить</button></div></div>`).join(""):"Очередь пуста."}<br><button onclick="load()">Назад</button></div>`}
async function photoDecision(id,status){let k=document.querySelector("#key").value,r=await fetch("/api/admin/photo-moderation?key="+encodeURIComponent(k),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({photo_id:id,status})}),j=await r.json();if(!r.ok)return alert(j.error);moderation()}
async function toggle(v){let k=document.querySelector("#key").value,r=await fetch("/api/admin/settings?key="+encodeURIComponent(k),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({PRE_LAUNCH_MODE:v})});let j=await r.json();if(!r.ok)return alert(j.error);load()}
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    server_version="MatchLab/7"
    def log_message(self, fmt,*args): print(fmt%args, flush=True)
    def send_json(self,obj,status=200,cookie=None):
        b=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)))
        if cookie:self.send_header("Set-Cookie",cookie)
        self.end_headers();self.wfile.write(b)
    def send_html(self,s,status=200):
        b=s.encode();self.send_response(status);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def uid(self,c):
        ck=cookies.SimpleCookie(self.headers.get("Cookie",""))
        token=ck.get("ml_session")
        if not token:return None
        r=c.execute("SELECT user_id FROM sessions WHERE token=?",(token.value,)).fetchone()
        return r["user_id"] if r else None
    def require(self,c):
        u=self.uid(c)
        if not u: raise PermissionError("Нужно войти")
        return u
    def parsed(self):
        return urllib.parse.urlparse(self.path)
    def do_GET(self):
        p=self.parsed()
        if p.path=="/": return self.send_html(HTML)
        if p.path=="/admin": return self.send_html(ADMIN_HTML)
        if p.path=="/health":
            c=db(); pre=setting(c,"PRE_LAUNCH_MODE","true"); c.close()
            return self.send_json({"ok":True,"version":VERSION,"questions":64,"unique":64,"prelaunch":pre})
        c=db()
        try:
            if p.path=="/api/me":
                uid=self.uid(c); return self.send_json({"me":make_me(c,uid) if uid else None})
            if p.path=="/api/questions":
                uid=self.require(c); ans=answer_map(c,uid)
                return self.send_json({"questions":QUESTIONS,"answers":ans})
            if p.path=="/api/photos":
                uid=self.require(c)
                rows=c.execute("SELECT id,mime,data,is_main,moderation_status FROM photos WHERE user_id=? ORDER BY is_main DESC,id",(uid,)).fetchall()
                return self.send_json({"photos":[{"id":r["id"],"src":"data:"+r["mime"]+";base64,"+r["data"],"is_main":bool(r["is_main"]),"moderation_status":r["moderation_status"]} for r in rows]})
            if p.path=="/api/summary":
                uid=self.require(c); return self.send_json({"me":make_me(c,uid),"summary":summary_for(c,uid)})
            if p.path=="/api/referral":
                uid=self.require(c); u=c.execute("SELECT referral_code,invites_sent FROM users WHERE id=?",(uid,)).fetchone()
                reg=c.execute("SELECT COUNT(*) n FROM users WHERE referred_by=?",(uid,)).fetchone()["n"]
                comp=c.execute("SELECT COUNT(*) n FROM users u JOIN profiles p ON p.user_id=u.id WHERE u.referred_by=? AND p.profile_completed=1",(uid,)).fetchone()["n"]
                return self.send_json({"url":BASE_URL+"/?ref="+u["referral_code"],"sent":u["invites_sent"],"registered":reg,"completed":comp})
            if p.path=="/api/feed":
                uid=self.require(c); pre=setting(c,"PRE_LAUNCH_MODE","true")=="true"; pe=setting(c,"PRELAUNCH_MATCHING_ENABLED","false")=="true"
                if pre and not pe:return self.send_json({"prelaunch":True,"matching_enabled":False,"items":[]})
                me=get_profile(c,uid)
                if not active_matchable_row(me):return self.send_json({"prelaunch":pre,"matching_enabled":True,"items":[]})
                ids=[r["user_id"] for r in c.execute("SELECT user_id FROM profiles WHERE user_id<>? AND profile_completed=1",(uid,))]
                out=[]
                for x in ids:
                    if c.execute("SELECT 1 FROM likes WHERE from_user=? AND to_user=?",(uid,x)).fetchone():continue
                    if hard_pass(c,uid,x):
                        s,m,by=compatibility(c,uid,x); pp=public_profile(c,x,uid)
                        pp.update({"compatibility_score":s,"mutual_fit_score":m,"dimensions":by});out.append(pp)
                out.sort(key=lambda x:(x["mutual_fit_score"],x["readiness_score"]),reverse=True)
                return self.send_json({"prelaunch":pre,"matching_enabled":True,"items":out[:20]})
            if p.path=="/api/matches":
                uid=self.require(c)
                rows=c.execute("SELECT * FROM matches WHERE user1=? OR user2=? ORDER BY id DESC",(uid,uid)).fetchall()
                items=[]
                for r in rows:
                    other=r["user2"] if r["user1"]==uid else r["user1"]
                    unread=c.execute("SELECT COUNT(*) n FROM messages WHERE match_id=? AND sender<>? AND read_at IS NULL",(r["id"],uid)).fetchone()["n"]
                    items.append({"id":r["id"],"compatibility_score":r["compatibility_score"],"mutual_fit_score":r["mutual_fit_score"],"profile":public_profile(c,other,uid),"unread":unread})
                return self.send_json({"items":items})
            if p.path=="/api/chat":
                uid=self.require(c)
                qs=urllib.parse.parse_qs(p.query); mid=int((qs.get("match_id") or [0])[0])
                m=c.execute("SELECT * FROM matches WHERE id=? AND (user1=? OR user2=?)",(mid,uid,uid)).fetchone()
                if not m:return self.send_json({"error":"Чат не найден"},404)
                other=m["user2"] if m["user1"]==uid else m["user1"]
                c.execute("UPDATE messages SET read_at=? WHERE match_id=? AND sender<>? AND read_at IS NULL",(now(),mid,uid));c.commit()
                msgs=[{"id":x["id"],"body":x["body"],"created_at":x["created_at"],"mine":x["sender"]==uid} for x in c.execute("SELECT * FROM messages WHERE match_id=? ORDER BY id",(mid,))]
                props=[]
                for x in c.execute("SELECT * FROM date_proposals WHERE match_id=? ORDER BY id DESC",(mid,)):
                    d=dict(x);d["can_answer"]=x["proposer"]!=uid;props.append(d)
                return self.send_json({"other":public_profile(c,other,uid),"messages":msgs,"proposals":props})
            if p.path=="/api/admin/photos":
                qs=urllib.parse.parse_qs(p.query); key=(qs.get("key") or [""])[0]
                if not hmac.compare_digest(key,ADMIN_KEY):return self.send_json({"error":"Нет доступа"},403)
                items=[]
                for r in c.execute("""SELECT ph.id,ph.mime,ph.data,u.email,p.display_name FROM photos ph
                  JOIN users u ON u.id=ph.user_id JOIN profiles p ON p.user_id=ph.user_id
                  WHERE ph.moderation_status='PENDING' ORDER BY ph.id LIMIT 100"""):
                    items.append({"id":r["id"],"email":r["email"],"name":r["display_name"],"src":"data:"+r["mime"]+";base64,"+r["data"]})
                return self.send_json({"items":items})
            if p.path=="/api/admin/dashboard":
                qs=urllib.parse.parse_qs(p.query); key=(qs.get("key") or [""])[0]
                if not hmac.compare_digest(key,ADMIN_KEY):return self.send_json({"error":"Нет доступа"},403)
                profs=c.execute("SELECT * FROM profiles").fetchall()
                active=[x for x in profs if active_matchable_row(x)]
                completed=[x for x in profs if x["profile_completed"]]
                withmatch=c.execute("SELECT COUNT(DISTINCT user1)+COUNT(DISTINCT user2) n FROM matches").fetchone()["n"] or 0
                users=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
                likes=c.execute("SELECT COUNT(*) n FROM likes").fetchone()["n"]
                matches=c.execute("SELECT COUNT(*) n FROM matches").fetchone()["n"]
                conv=c.execute("SELECT COUNT(DISTINCT match_id) n FROM messages").fetchone()["n"]
                metrics={
                  "ACTIVE_MATCHABLE_USERS":len(active),"COMPLETED_PROFILES":len(completed),
                  "USERS_WITH_AT_LEAST_ONE_MATCH":withmatch,"MATCH_RATE":round((withmatch/max(1,len(completed)))*100,1),
                  "MUTUAL_INTEREST_RATE":round((matches/max(1,likes))*100,1),
                  "CONVERSATION_START_RATE":round((conv/max(1,matches))*100,1),
                  "TOTAL_REGISTRATIONS":users,
                  "MEN":sum(1 for x in profs if x["gender"]=="M"),
                  "WOMEN":sum(1 for x in profs if x["gender"]=="F"),
                  "COMPLETED":len(completed),"INCOMPLETE":max(0,len(profs)-len(completed)),
                  "ACTIVE_SEARCH":sum(1 for x in profs if x["relationship_status"]=="ACTIVE_SEARCH"),
                  "OPEN_TO_MATCH":sum(1 for x in profs if x["relationship_status"]=="OPEN_TO_MATCH"),
                  "PAUSED":sum(1 for x in profs if x["relationship_status"]=="PAUSED"),
                  "IN_RELATIONSHIP":sum(1 for x in profs if x["relationship_status"]=="IN_RELATIONSHIP")
                }
                # supply-demand gap by seeker gender + preferred age band from criteria
                gaps=[]
                for seeker_gender in ("F","M"):
                    seekers=[x for x in active if x["gender"]==seeker_gender]
                    target_gender="M" if seeker_gender=="F" else "F"
                    for band in ("18–23","24–28","29–35","36–45","46+"):
                        demand=0
                        for x in seekers:
                            cr=get_criteria(c,x["user_id"]).get("age",{})
                            mn=int(cr.get("min") or 18);mx=int(cr.get("max") or 99)
                            mid={"18–23":21,"24–28":26,"29–35":32,"36–45":40,"46+":50}[band]
                            if mn<=mid<=mx:demand+=1
                        supply=sum(1 for x in active if x["gender"]==target_gender and age_band(age_from_dob(x["dob"]))==band)
                        gaps.append({"group":("Женщины" if seeker_gender=="F" else "Мужчины")+" → "+("мужчины " if target_gender=="M" else "женщины ")+band,"demand":demand,"supply":supply,"gap":max(0,demand-supply)})
                gaps.sort(key=lambda x:x["gap"],reverse=True)
                insights=[]
                for g in gaps[:5]:
                    if g["gap"]>0:insights.append(("Высокий дефицит: " if g["gap"]>=5 else "Средний дефицит: ")+g["group"]+" · не хватает "+str(g["gap"]))
                if not insights:insights=["Сейчас выраженного дефицита по базовым возрастным сегментам не видно."]
                src=[]
                for r in c.execute("""SELECT CASE WHEN u.referred_by IS NOT NULL THEN 'referral' ELSE COALESCE(NULLIF(a.utm_source,''),'direct') END source, COUNT(*) registrations,
                  SUM(CASE WHEN p.profile_completed=1 AND p.eligibility_status='ACTIVE_FOR_MATCHING' AND p.relationship_status NOT IN ('PAUSED','IN_RELATIONSHIP','NOT_ACTIVE') THEN 1 ELSE 0 END) completed_active
                  FROM users u LEFT JOIN attribution a ON a.user_id=u.id LEFT JOIN profiles p ON p.user_id=u.id GROUP BY source ORDER BY registrations DESC"""):
                    src.append(dict(r))
                ages={}
                cities={}
                for x in profs:
                    a=age_from_dob(x["dob"])
                    if a>=18:ages[age_band(a)]=ages.get(age_band(a),0)+1
                    city=(x["city"] or "Не указан").strip() or "Не указан"
                    cities[city]=cities.get(city,0)+1
                pending=c.execute("SELECT COUNT(*) n FROM photos WHERE moderation_status='PENDING'").fetchone()["n"]
                return self.send_json({"metrics":metrics,"gaps":gaps,"insights":insights,"sources":src,"prelaunch":setting(c,"PRE_LAUNCH_MODE","true"),"age_distribution":ages,"cities":cities,"pending_photos":pending})
            return self.send_json({"error":"Не найдено"},404)
        except PermissionError as e:return self.send_json({"error":str(e)},401)
        except Exception as e:
            print("GET ERR",repr(e),flush=True);return self.send_json({"error":"Ошибка сервера"},500)
        finally:c.close()
    def do_DELETE(self):
        p=self.parsed();c=db()
        try:
            uid=self.require(c)
            m=re.match(r"^/api/photos/(\d+)$",p.path)
            if m:
                pid=int(m.group(1));c.execute("DELETE FROM photos WHERE id=? AND user_id=?",(pid,uid));c.commit()
                if not c.execute("SELECT 1 FROM photos WHERE user_id=? AND is_main=1",(uid,)).fetchone():
                    r=c.execute("SELECT id FROM photos WHERE user_id=? ORDER BY id LIMIT 1",(uid,)).fetchone()
                    if r:c.execute("UPDATE photos SET is_main=1 WHERE id=?",(r["id"],));c.commit()
                recompute_completion(c,uid);c.commit();return self.send_json({"ok":True})
            return self.send_json({"error":"Не найдено"},404)
        except PermissionError as e:return self.send_json({"error":str(e)},401)
        finally:c.close()
    def do_POST(self):
        p=self.parsed();c=db()
        try:
            data=json_body(self)
            if p.path=="/api/register":
                email=(data.get("email") or "").strip().lower();pw=data.get("password") or "";dob=data.get("dob") or ""
                if age_from_dob(dob)<18:return self.send_json({"error":"Регистрация доступна только пользователям 18+."},400)
                if len(pw)<6 or "@" not in email:return self.send_json({"error":"Проверьте email и пароль (минимум 6 символов)."},400)
                rel,elig=status_from_screen(data.get("relationship"),data.get("open_to"))
                city=(data.get("city") or "").strip()
                if city.lower() not in ("алматы","almaty"): elig="NOT_ACTIVE_FOR_MATCHING"
                refcode=secrets.token_urlsafe(6)
                referred_by=None
                ri=(data.get("ref") or "").strip()
                if ri:
                    rr=c.execute("SELECT id FROM users WHERE referral_code=?",(ri,)).fetchone()
                    if rr:referred_by=rr["id"]
                try:
                    cur=c.execute("INSERT INTO users(email,password_hash,created_at,referral_code,referred_by) VALUES(?,?,?,?,?)",(email,hash_password(pw),now(),refcode,referred_by))
                except sqlite3.IntegrityError:return self.send_json({"error":"Такой email уже зарегистрирован."},409)
                uid=cur.lastrowid
                c.execute("""INSERT INTO profiles(user_id,display_name,dob,gender,seek_gender,city,relationship_status,eligibility_status,status_confirmed_at,updated_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?)""",(uid,(data.get("display_name") or "").strip(),dob,data.get("gender") or "",data.get("seek_gender") or "",city,rel,elig,now(),now()))
                c.execute("""INSERT INTO attribution(user_id,utm_source,utm_medium,utm_campaign,utm_content,utm_term,referral_input) VALUES(?,?,?,?,?,?,?)""",
                          (uid,data.get("utm_source",""),data.get("utm_medium",""),data.get("utm_campaign",""),data.get("utm_content",""),data.get("utm_term",""),ri))
                tok=secrets.token_urlsafe(32);c.execute("INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)",(tok,uid,now()))
                log_event(c,uid,"registration",{"source":data.get("utm_source") or "direct"});c.commit()
                return self.send_json({"me":make_me(c,uid)},201,"ml_session="+tok+"; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000")
            if p.path=="/api/login":
                email=(data.get("email") or "").strip().lower();r=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
                if not r or not check_password(data.get("password") or "",r["password_hash"]):return self.send_json({"error":"Неверный email или пароль."},401)
                tok=secrets.token_urlsafe(32);c.execute("INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)",(tok,r["id"],now()));c.commit()
                return self.send_json({"me":make_me(c,r["id"])},200,"ml_session="+tok+"; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000")
            if p.path=="/api/logout":
                uid=self.uid(c)
                ck=cookies.SimpleCookie(self.headers.get("Cookie",""));t=ck.get("ml_session")
                if t:c.execute("DELETE FROM sessions WHERE token=?",(t.value,));c.commit()
                return self.send_json({"ok":True},200,"ml_session=; Path=/; Max-Age=0")
            if p.path=="/api/admin/settings":
                qs=urllib.parse.parse_qs(p.query); key=(qs.get("key") or [""])[0]
                if not hmac.compare_digest(key,ADMIN_KEY):return self.send_json({"error":"Нет доступа"},403)
                for k in ("PRE_LAUNCH_MODE","PRELAUNCH_MATCHING_ENABLED"):
                    if k in data:c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,str(data[k]).lower()))
                c.commit();return self.send_json({"ok":True})
            if p.path=="/api/admin/photo-moderation":
                qs=urllib.parse.parse_qs(p.query); key=(qs.get("key") or [""])[0]
                if not hmac.compare_digest(key,ADMIN_KEY):return self.send_json({"error":"Нет доступа"},403)
                st=data.get("status")
                if st not in ("APPROVED","REJECTED"):return self.send_json({"error":"Некорректный статус"},400)
                pid=int(data.get("photo_id",0))
                c.execute("UPDATE photos SET moderation_status=? WHERE id=?",(st,pid))
                if st=="REJECTED":
                    row=c.execute("SELECT user_id FROM photos WHERE id=?",(pid,)).fetchone()
                    if row:
                        c.execute("INSERT INTO notifications(user_id,kind,text,created_at) VALUES(?,?,?,?)",(row["user_id"],"PHOTO","Одно из ваших фото не прошло модерацию",now()))
                c.commit();return self.send_json({"ok":True})
            uid=self.require(c)
            if p.path=="/api/profile":
                score=readiness(data.get("readiness_chat"),data.get("readiness_offline"))
                c.execute("""UPDATE profiles SET dating_goal=?,readiness_chat=?,readiness_offline=?,readiness_score=?,bio=?,height=?,smoking=?,alcohol=?,lifestyle=?,religion=?,nationality=?,children_attitude=?,children_plans=?,updated_at=? WHERE user_id=?""",
                          (data.get("dating_goal",""),data.get("readiness_chat",""),data.get("readiness_offline",""),score,data.get("bio",""),data.get("height"),data.get("smoking",""),data.get("alcohol",""),data.get("lifestyle",""),data.get("religion",""),data.get("nationality",""),data.get("children_attitude",""),data.get("children_plans",""),now(),uid))
                recompute_completion(c,uid);c.commit();return self.send_json({"me":make_me(c,uid)})
            if p.path=="/api/criteria":
                c.execute("INSERT INTO criteria(user_id,data,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at",(uid,json.dumps(data,ensure_ascii=False),now()))
                recompute_completion(c,uid);c.commit();return self.send_json({"me":make_me(c,uid)})
            if p.path=="/api/answer":
                qid=int(data.get("qid",0));val=int(data.get("value",0))
                if not (1<=qid<=64 and 1<=val<=5):return self.send_json({"error":"Некорректный ответ"},400)
                c.execute("INSERT INTO answers(user_id,qid,value) VALUES(?,?,?) ON CONFLICT(user_id,qid) DO UPDATE SET value=excluded.value",(uid,qid,val))
                recompute_completion(c,uid);c.commit();return self.send_json({"ok":True})
            if p.path=="/api/photos":
                if photo_count(c,uid)>=6:return self.send_json({"error":"Максимум 6 фотографий."},400)
                mime=data.get("mime") or "image/jpeg";blob=data.get("data") or ""
                if len(blob)>4_500_000:return self.send_json({"error":"Фото слишком большое."},400)
                main=1 if photo_count(c,uid)==0 else 0
                c.execute("INSERT INTO photos(user_id,mime,data,is_main,moderation_status,created_at) VALUES(?,?,?,?,?,?)",(uid,mime,blob,main,"PENDING",now()))
                recompute_completion(c,uid);c.commit();return self.send_json({"ok":True})
            m=re.match(r"^/api/photos/(\d+)/main$",p.path)
            if m:
                pid=int(m.group(1));own=c.execute("SELECT 1 FROM photos WHERE id=? AND user_id=?",(pid,uid)).fetchone()
                if not own:return self.send_json({"error":"Фото не найдено"},404)
                c.execute("UPDATE photos SET is_main=0 WHERE user_id=?",(uid,));c.execute("UPDATE photos SET is_main=1 WHERE id=?",(pid,));c.commit();return self.send_json({"ok":True})
            if p.path=="/api/finish":
                done=recompute_completion(c,uid)
                if not done:return self.send_json({"error":"Для готового профиля нужны все 64 ответа, критерии и минимум 2 фотографии."},400)
                log_event(c,uid,"profile_completed");c.commit();return self.send_json({"me":make_me(c,uid)})
            if p.path=="/api/status":
                st=data.get("status","")
                if st not in ("ACTIVE_SEARCH","OPEN_TO_MATCH","PAUSED","IN_RELATIONSHIP","NOT_ACTIVE"):return self.send_json({"error":"Некорректный статус"},400)
                pp=get_profile(c,uid)
                in_launch=bool(pp and (pp["city"] or "").strip().lower() in ("алматы","almaty"))
                elig="ACTIVE_FOR_MATCHING" if st in ("ACTIVE_SEARCH","OPEN_TO_MATCH") and in_launch else "NOT_ACTIVE_FOR_MATCHING"
                c.execute("UPDATE profiles SET relationship_status=?,eligibility_status=?,status_confirmed_at=?,updated_at=? WHERE user_id=?",(st,elig,now(),now(),uid));c.commit()
                return self.send_json({"me":make_me(c,uid)})
            if p.path=="/api/like":
                target=int(data.get("target",0))
                if not hard_pass(c,uid,target):return self.send_json({"error":"Профили не проходят взаимные обязательные критерии."},400)
                c.execute("INSERT OR IGNORE INTO likes(from_user,to_user,created_at) VALUES(?,?,?)",(uid,target,now()))
                reciprocal=c.execute("SELECT 1 FROM likes WHERE from_user=? AND to_user=?",(target,uid)).fetchone()
                made=False
                if reciprocal:
                    a,b=sorted((uid,target));score,mutual,_=compatibility(c,a,b)
                    c.execute("INSERT OR IGNORE INTO matches(user1,user2,compatibility_score,mutual_fit_score,created_at) VALUES(?,?,?,?,?)",(a,b,score,mutual,now()))
                    c.execute("INSERT INTO notifications(user_id,kind,text,created_at) VALUES(?,?,?,?)",(uid,"MATCH","У вас новый мэтч!",now()))
                    c.execute("INSERT INTO notifications(user_id,kind,text,created_at) VALUES(?,?,?,?)",(target,"MATCH","У вас новый мэтч!",now()));made=True
                c.commit();return self.send_json({"ok":True,"match":made})
            if p.path=="/api/message":
                mid=int(data.get("match_id",0));body=(data.get("body") or "").strip()
                m=c.execute("SELECT * FROM matches WHERE id=? AND (user1=? OR user2=?)",(mid,uid,uid)).fetchone()
                if not m or not body:return self.send_json({"error":"Нельзя отправить сообщение"},400)
                c.execute("INSERT INTO messages(match_id,sender,body,created_at) VALUES(?,?,?,?)",(mid,uid,body[:2000],now()))
                other=m["user2"] if m["user1"]==uid else m["user1"]
                c.execute("INSERT INTO notifications(user_id,kind,text,created_at) VALUES(?,?,?,?)",(other,"MESSAGE","Новое сообщение в MatchLab",now()))
                c.commit();return self.send_json({"ok":True})
            if p.path=="/api/date-proposal":
                mid=int(data.get("match_id",0));m=c.execute("SELECT * FROM matches WHERE id=? AND (user1=? OR user2=?)",(mid,uid,uid)).fetchone()
                if not m:return self.send_json({"error":"Мэтч не найден"},404)
                c.execute("INSERT INTO date_proposals(match_id,proposer,format,when_text,district,budget,note,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                          (mid,uid,data.get("format","Кофе"),data.get("when_text",""),data.get("district",""),data.get("budget",""),data.get("note",""),"PENDING",now()))
                other=m["user2"] if m["user1"]==uid else m["user1"]
                c.execute("INSERT INTO notifications(user_id,kind,text,created_at) VALUES(?,?,?,?)",(other,"DATE","Вам предложили свидание",now()))
                c.commit();return self.send_json({"ok":True})
            if p.path=="/api/date-proposal/respond":
                pid=int(data.get("proposal_id",0));st=data.get("status")
                if st not in ("ACCEPTED","DECLINED"):return self.send_json({"error":"Некорректный статус"},400)
                pr=c.execute("""SELECT dp.*,m.user1,m.user2 FROM date_proposals dp JOIN matches m ON m.id=dp.match_id
                                WHERE dp.id=? AND (m.user1=? OR m.user2=?)""",(pid,uid,uid)).fetchone()
                if not pr or pr["proposer"]==uid:return self.send_json({"error":"Нельзя изменить это предложение"},403)
                c.execute("UPDATE date_proposals SET status=? WHERE id=?",(st,pid))
                c.execute("INSERT INTO notifications(user_id,kind,text,created_at) VALUES(?,?,?,?)",(pr["proposer"],"DATE_RESULT","Предложение свидания: "+("принято" if st=="ACCEPTED" else "отклонено"),now()))
                c.commit();return self.send_json({"ok":True})
            if p.path=="/api/referral/invite":
                c.execute("UPDATE users SET invites_sent=invites_sent+1 WHERE id=?",(uid,));c.commit();return self.send_json({"ok":True})
            if p.path=="/api/report-photo":
                c.execute("INSERT INTO reports(reporter,target_user,photo_id,reason,created_at) VALUES(?,?,?,?,?)",(uid,data.get("target_user"),data.get("photo_id"),data.get("reason","Жалоба на фото"),now()));c.commit();return self.send_json({"ok":True})
            return self.send_json({"error":"Не найдено"},404)
        except PermissionError as e:return self.send_json({"error":str(e)},401)
        except Exception as e:
            print("POST ERR",repr(e),flush=True);return self.send_json({"error":"Ошибка сервера"},500)
        finally:c.close()

if __name__=="__main__":
    print(f"MATCHLAB_READY version={VERSION} questions={len(QUESTIONS)} unique={len(set(q['text'] for q in QUESTIONS))} prelaunch={PRELAUNCH_DEFAULT}",flush=True)
    ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
