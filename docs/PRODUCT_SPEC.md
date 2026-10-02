Ты выступаешь как полноценная senior product & engineering team.

Твои роли одновременно:
— Senior Product Manager
— Senior UX/UI Designer
— Senior Mobile Developer
— Senior Frontend Developer
— Senior Backend Developer
— Database Architect
— Security Engineer
— QA Engineer
— DevOps Engineer
— Product Analyst

Твоя задача — разработать production-ready приложение знакомств нового типа.

ВАЖНО:
Это НЕ Tinder, НЕ Badoo и НЕ приложение со свайпами.

Это сервис персонального подбора партнёра по совместимости.

Главная идея:

Пользователь не листает сотни анкет.

Он:

1. Регистрируется.
2. Заполняет подробную анкету.
3. Указывает критерии партнёра.
4. Загружает фотографии.
5. Система анализирует его профиль.
6. Система ищет подходящих людей.
7. Пользователь получает только несколько действительно релевантных кандидатов.
8. Система объясняет, почему люди подходят друг другу.
9. Если интерес взаимный — открывается возможность общения.

Главное позиционирование продукта:

«Не выбирай из всех. Найди подходящего.»

Продукт должен восприниматься не как dating app, а как персональный matchmaker.

━━━━━━━━━━━━━━━━━━
ГЛАВНЫЕ ПРИНЦИПЫ
━━━━━━━━━━━━━━━━━━

1. НИКАКИХ СВАЙПОВ.
2. НИКАКОЙ бесконечной ленты людей.
3. Не показывать пользователей просто ради наполнения экрана.
4. Если подходящего человека нет — честно сообщить:
   «Мы пока не нашли человека, который проходит ваши основные критерии.»
5. Matching должен быть взаимным.

Если пользователь A подходит пользователю B, но B не подходит обязательным критериям A — match не создаётся.

6. Основой продукта является качество подбора, а не количество анкет.
7. Все пользователи сервиса должны быть 18+.
8. Профили со статусами:
   — ACTIVE_SEARCH
   — OPEN_TO_MATCH
   — PAUSED
   — IN_RELATIONSHIP
   — NOT_ACTIVE

PAUSED и IN_RELATIONSHIP полностью исключаются из новых подборов.

9. Безопасность пользователей имеет высокий приоритет.
10. Приложение должно быть максимально простым визуально, премиальным и понятным.

━━━━━━━━━━━━━━━━━━
ПЕРВЫЙ РЫНОК
━━━━━━━━━━━━━━━━━━

Первый город:
Алматы, Казахстан.

Но архитектура должна сразу поддерживать:
— другие города;
— другие страны;
— несколько языков;
— разные валюты;
— региональные настройки.

Не хардкодить Алматы в архитектуре.

━━━━━━━━━━━━━━━━━━
ЦЕЛЕВАЯ АУДИТОРИЯ
━━━━━━━━━━━━━━━━━━

Совершеннолетние мужчины и женщины, которые:
— сейчас свободны;
— открыты к знакомствам;
— ищут отношения;
— хотят более качественный подбор;
— не хотят тратить время на бесконечные свайпы.

━━━━━━━━━━━━━━━━━━
USER FLOW
━━━━━━━━━━━━━━━━━━

Основной путь пользователя:

Splash
↓
Onboarding
↓
Registration
↓
Age verification
↓
Relationship status
↓
Dating intention
↓
Basic profile
↓
Full questionnaire
↓
Partner preferences
↓
Photos
↓
Profile analysis
↓
Compatibility profile
↓
Waiting / Matching
↓
Candidate
↓
Compatibility breakdown
↓
Express interest
↓
Mutual interest
↓
Conversation

Пользователь всегда должен понимать:
— где он находится;
— зачем задаётся вопрос;
— сколько осталось;
— что произойдёт дальше.

━━━━━━━━━━━━━━━━━━
РЕГИСТРАЦИЯ
━━━━━━━━━━━━━━━━━━

Поддержать:

— номер телефона;
— email;
— Apple Sign In;
— Google Sign In.

После регистрации:
верификация контакта.

Дата рождения обязательна.

Если возраст < 18:
регистрацию остановить.

━━━━━━━━━━━━━━━━━━
ONBOARDING FILTER
━━━━━━━━━━━━━━━━━━

Спросить:

«Вы сейчас состоите в отношениях?»

Варианты:
— Нет
— Да

«Вы открыты к знакомствам?»

— Да, активно ищу
— Да, если встречу подходящего человека
— Пока не уверен(а)
— Нет

Если пользователь находится в отношениях или не открыт к знакомствам:
не включать его в matching.

━━━━━━━━━━━━━━━━━━
АНКЕТА
━━━━━━━━━━━━━━━━━━

Анкета должна быть достаточно глубокой для реального подбора.

Ориентировочно 60–100 вопросов.

Но НЕ показывать пользователю 100 вопросов одним полотном.

Разделить на логические блоки.

Категории:

1. Базовая информация
2. Образ жизни
3. Характер
4. Ценности
5. Отношения
6. Семья
7. Дети
8. Работа
9. Амбиции
10. Деньги
11. Социальность
12. Личное пространство
13. Конфликты
14. Эмоциональная близость
15. Интересы
16. Привычки
17. Жизненные планы
18. Отношение к путешествиям
19. Режим жизни
20. Коммуникация

Для вопросов использовать:
— single choice;
— multiple choice;
— scale;
— priority;
— optional text.

Не использовать длинные текстовые ответы без необходимости.

Каждый вопрос должен иметь:
question_id
category
question_text
answer_type
weight
match_logic

━━━━━━━━━━━━━━━━━━
КРИТЕРИИ ПАРТНЁРА
━━━━━━━━━━━━━━━━━━

Пользователь указывает:

— возраст;
— пол;
— город;
— расстояние;
— отношения;
— дети;
— планы на детей;
— курение;
— алкоголь;
— образ жизни;
— рост;
— религия при желании;
— другие критерии.

Для каждого предпочтения:

HARD
IMPORTANT
PREFERENCE
IGNORE

HARD:
если критерий не выполняется — кандидат не показывается.

IMPORTANT:
значительно влияет на compatibility score.

PREFERENCE:
умеренно влияет.

IGNORE:
не учитывать.

━━━━━━━━━━━━━━━━━━
MATCHING ENGINE
━━━━━━━━━━━━━━━━━━

Matching НЕ должен зависеть только от AI.

Основной подбор должен быть детерминированным и объяснимым.

Pipeline:

STEP 1:
Eligibility filter.

STEP 2:
Hard filters.

STEP 3:
Mutual hard filters.

STEP 4:
Compatibility calculation.

STEP 5:
Mutual preference calculation.

STEP 6:
Behavior / activity score.

STEP 7:
Final mutual fit score.

Разделить compatibility на категории:

values_score
relationship_score
family_score
lifestyle_score
communication_score
personality_score
future_score
interests_score

Итоговый score:
0–100.

Но не создавать ложную научную точность.

Интерфейс может показывать:
«Высокая совместимость»
или число + объяснение.

AI можно использовать для генерации понятного объяснения:

«У вас совпадают взгляды на семью, образ жизни и личное пространство. Основная зона различий — отношение к социальной активности.»

AI НЕ должен единолично решать, подходят ли люди друг другу.

━━━━━━━━━━━━━━━━━━
MATCH RESULT
━━━━━━━━━━━━━━━━━━

Карточка кандидата:

Фото
Имя
Возраст
Город

Compatibility:
например 87%

Блоки:

Ценности
Семья
Образ жизни
Коммуникация
Будущее

Показать:

«Почему вы подходите»

«На что обратить внимание»

Не использовать негативные ярлыки.

━━━━━━━━━━━━━━━━━━
INTEREST SYSTEM
━━━━━━━━━━━━━━━━━━

Не использовать swipe.

Кнопки:

«Интересен человек»

«Пока пропустить»

Если оба пользователя нажали интерес:
создать MUTUAL_MATCH.

Только после взаимного интереса:
разрешить чат.

━━━━━━━━━━━━━━━━━━
ЧАТ
━━━━━━━━━━━━━━━━━━

Функции:

— текст;
— фото позже;
— push notifications;
— unread;
— block;
— report.

Не добавлять сложные функции в MVP.

━━━━━━━━━━━━━━━━━━
ФОТО
━━━━━━━━━━━━━━━━━━

Минимум 2 фото.

Рекомендуется 3–5.

Поддержать:

— upload;
— reorder;
— main photo;
— delete;
— moderation.

В будущем:
selfie verification.

━━━━━━━━━━━━━━━━━━
SAFETY
━━━━━━━━━━━━━━━━━━

Обязательно:

— block user;
— report user;
— report photo;
— report message;
— moderation queue;
— admin ban;
— soft ban;
— account deletion;
— data deletion.

Добавить причины жалоб.

Логировать moderation actions.

━━━━━━━━━━━━━━━━━━
ADMIN PANEL
━━━━━━━━━━━━━━━━━━

Создать полноценную web admin panel.

Разделы:

Dashboard
Users
Profiles
Photos
Reports
Matches
Chats metadata
Questionnaire
Matching settings
Marketing
Analytics
Audience balance

Главный блок:
AUDIENCE BALANCE.

Показывать:

active users
women
men
age distribution
cities
completed profiles
incomplete profiles
active search
paused
in relationship

Также:

SUPPLY vs DEMAND.

Пример:

Женщины 24–28:
180

Ищут мужчин 27–35:
145

Подходящих активных мужчин:
51

DEMAND GAP:
94

Система должна автоматически показывать:
«Кого сейчас не хватает в базе».

Это используется для рекламы.

━━━━━━━━━━━━━━━━━━
PRE-LAUNCH MODE
━━━━━━━━━━━━━━━━━━

Добавить:

PRE_LAUNCH_MODE = true / false

Если true:

можно:
— зарегистрироваться;
— пройти анкету;
— загрузить фото;
— получить собственный compatibility profile;
— попасть в waitlist.

Но администрация может отключить полноценную выдачу кандидатов.

Это нужно для предварительного набора аудитории до официального запуска.

━━━━━━━━━━━━━━━━━━
MARKETING TRACKING
━━━━━━━━━━━━━━━━━━

Хранить:

utm_source
utm_medium
utm_campaign
utm_content
utm_term
referral_code

Отслеживать:

registration
questionnaire_started
questionnaire_completed
photo_uploaded
profile_completed
first_match
interest_sent
mutual_match
chat_started
subscription_started

Не просто считать установки.

━━━━━━━━━━━━━━━━━━
REFERRAL SYSTEM
━━━━━━━━━━━━━━━━━━

Каждому пользователю:
unique referral code.

После анкеты:

«Пригласить друга пройти тест совместимости»

Отслеживать:

invite
registration
completed_profile

━━━━━━━━━━━━━━━━━━
МОНЕТИЗАЦИЯ
━━━━━━━━━━━━━━━━━━

Архитектура должна поддерживать:

FREE
PREMIUM
PREMIUM_PLUS

Но первоначальный MVP не должен агрессивно закрывать функции оплатой.

Возможные Premium функции:

— дополнительные активные подборы;
— глубокий compatibility breakdown;
— расширенные предпочтения;
— priority matching;
— AI relationship analysis.

Также:
one-time purchase:
deep compatibility report.

Subscription architecture должна быть готова для App Store и Google Play.

━━━━━━━━━━━━━━━━━━
АНАЛИТИКА
━━━━━━━━━━━━━━━━━━

Главные продуктовые показатели:

registration_conversion
questionnaire_start_rate
questionnaire_completion_rate
profile_completion_rate
match_rate
mutual_interest_rate
chat_start_rate
D1
D7
D30
subscription_conversion
report_rate

Самый важный показатель:

USERS_WITH_RELEVANT_MATCH

Не оптимизировать продукт под количество просмотров профилей.

━━━━━━━━━━━━━━━━━━
DATABASE
━━━━━━━━━━━━━━━━━━

Спроектировать нормальную production database.

Пример сущностей:

users
profiles
photos
questionnaire_questions
questionnaire_answers
partner_preferences
user_status
matches
match_scores
interests
conversations
messages
blocks
reports
subscriptions
payments
notifications
referrals
marketing_attribution
audit_logs

Не хранить всё одним JSON.

Допустимо использовать JSON только там, где это действительно оправдано.

Добавить indexes.

Продумать scale.

━━━━━━━━━━━━━━━━━━
SECURITY
━━━━━━━━━━━━━━━━━━

Обязательно:

password hashing
JWT/session security
rate limiting
validation
authorization
role-based permissions
secure uploads
encrypted secrets
audit logging
API protection

Не хранить secrets в source code.

Не логировать пароли, токены и чувствительные пользовательские данные.

━━━━━━━━━━━━━━━━━━
PRIVACY
━━━━━━━━━━━━━━━━━━

Архитектура должна поддерживать:

consent logging
privacy settings
data export
account deletion
data deletion
retention policy

Система должна позволять удалить данные пользователя корректно.

━━━━━━━━━━━━━━━━━━
UI / UX
━━━━━━━━━━━━━━━━━━

Стиль:

premium
clean
minimal
warm
modern

НЕ:
яркий игровой Tinder-style интерфейс.

Не использовать:
— casino-style engagement;
— endless scrolling;
— дешёвые градиенты;
— визуальный шум.

Главный фокус:
доверие.

Использовать много воздуха.

Большие фотографии.

Хорошая типографика.

Минимум действий на экране.

Mobile-first.

━━━━━━━━━━━━━━━━━━
ТЕХНИЧЕСКАЯ АРХИТЕКТУРА
━━━━━━━━━━━━━━━━━━

Перед тем как писать код:

1. Проанализируй существующий проект.
2. Покажи текущую архитектуру.
3. Найди технический долг.
4. Определи, что можно оставить.
5. Определи, что необходимо переделать.
6. Не переписывай рабочие части без причины.

После этого предложи production architecture.

Не создавай несколько разных backend без необходимости.

Не дублируй бизнес-логику.

Создай единый источник истины для matching.

━━━━━━━━━━━━━━━━━━
ПРАВИЛА РАЗРАБОТКИ
━━━━━━━━━━━━━━━━━━

КРИТИЧЕСКИ ВАЖНО:

НЕ пытайся разработать всё приложение одним огромным изменением.

Работай итерациями.

Для каждого этапа:

1. Проанализируй задачу.
2. Проверь существующий код.
3. Составь implementation plan.
4. Реализуй.
5. Проверь ошибки.
6. Запусти tests.
7. Исправь tests.
8. Проверь UI.
9. Проверь edge cases.
10. Только потом переходи дальше.

Никогда не оставляй:

TODO
fake data
placeholder
mock logic

в production flow без явного указания.

━━━━━━━━━━━━━━━━━━
TESTING
━━━━━━━━━━━━━━━━━━

Создай:

unit tests
integration tests
API tests
matching tests
auth tests
permission tests

Особенно тщательно тестировать matching.

Создать synthetic users.

Проверить:

A подходит B
B подходит A

A подходит B
B НЕ подходит A

hard filter conflict

paused profile

relationship profile

blocked user

age restriction

distance restriction

empty database

large candidate pool

━━━━━━━━━━━━━━━━━━
ERROR HANDLING
━━━━━━━━━━━━━━━━━━

Ни один экран не должен просто падать.

Обработать:

no internet
server error
timeout
invalid form
upload failure
empty matches
expired session
deleted user
blocked user
notification failure

Показывать нормальные human-readable ошибки.

━━━━━━━━━━━━━━━━━━
QUALITY STANDARD
━━━━━━━━━━━━━━━━━━

Код должен быть:

production-ready
clean
maintainable
typed where possible
documented where necessary
scalable
secure

Не делать «демо ради демо».

Это настоящий коммерческий продукт.

━━━━━━━━━━━━━━━━━━
ВАЖНОЕ ПРАВИЛО ДЛЯ ТЕБЯ
━━━━━━━━━━━━━━━━━━

Не соглашайся автоматически со всеми моими идеями.

Если моё решение:
— ухудшает UX;
— создаёт security risk;
— противоречит архитектуре;
— может вызвать проблемы App Store;
— плохо масштабируется;
— усложняет продукт без пользы;

скажи об этом и предложи более сильное решение.

Но не меняй концепцию продукта без необходимости.

━━━━━━━━━━━━━━━━━━
КОНТРОЛЬ КОНТЕКСТА
━━━━━━━━━━━━━━━━━━

Перед каждым существенным изменением перечитай этот документ.

Все новые функции должны соответствовать базовой концепции:

«Система сама ищет небольшое количество взаимно подходящих людей вместо бесконечной ленты анкет.»

Если новая функция противоречит этому принципу — сначала объясни проблему.

━━━━━━━━━━━━━━━━━━
ПОРЯДОК РАЗРАБОТКИ
━━━━━━━━━━━━━━━━━━

Работай в следующем порядке:

PHASE 1
Architecture audit

PHASE 2
Database architecture

PHASE 3
Authentication

PHASE 4
User/profile model

PHASE 5
Questionnaire

PHASE 6
Partner preferences

PHASE 7
Matching engine

PHASE 8
Compatibility results

PHASE 9
Photos

PHASE 10
Interest + mutual matching

PHASE 11
Chat

PHASE 12
Safety / block / reports

PHASE 13
Admin panel

PHASE 14
Audience balance

PHASE 15
Pre-launch / waitlist

PHASE 16
Analytics

PHASE 17
Referral system

PHASE 18
Monetization infrastructure

PHASE 19
Push notifications

PHASE 20
Full QA

PHASE 21
Security audit

PHASE 22
Performance audit

PHASE 23
App Store / Play Store readiness

Не перескакивай через фундаментальные этапы.

━━━━━━━━━━━━━━━━━━
ПЕРВОЕ ЗАДАНИЕ
━━━━━━━━━━━━━━━━━━

СЕЙЧАС НЕ НАЧИНАЙ МАССОВО ПИСАТЬ КОД.

Сначала:

1. Изучи весь текущий проект.
2. Опиши, что уже реализовано.
3. Покажи архитектуру.
4. Покажи слабые места.
5. Составь список того, что отсутствует.
6. Сравни текущий проект с требованиями этого документа.
7. Создай roadmap реализации.
8. Разбей roadmap на маленькие конкретные задачи.
9. Укажи зависимости между задачами.
10. Только после этого начинай PHASE 1.

После завершения каждого PHASE:
выдай:

DONE
WHAT WAS BUILT
WHAT WAS TESTED
KNOWN ISSUES
NEXT PHASE