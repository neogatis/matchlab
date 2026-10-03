package com.neogatis.matchlab

import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

class OnboardingActivity : AppCompatActivity() {
    data class Choice(val label: String, val value: String) {
        override fun toString(): String = label
    }

    private lateinit var api: MatchLabApi
    private lateinit var scroll: ScrollView
    private lateinit var root: LinearLayout
    private lateinit var status: TextView
    private var currentStep: Int = 1
    private val totalSteps: Int = 7

    private val photoPicker = registerForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri ->
        if (uri == null) return@registerForActivityResult
        lifecycleScope.launch {
            setStatus("Загружаем фото…")
            runCatching {
                val mime = contentResolver.getType(uri) ?: "image/jpeg"
                if (mime !in setOf("image/jpeg", "image/png", "image/webp")) {
                    error("Поддерживаются JPEG, PNG и WebP")
                }
                val bytes = withContext(Dispatchers.IO) {
                    contentResolver.openInputStream(uri)?.use { stream -> stream.readBytes() }
                        ?: error("Не удалось открыть изображение")
                }
                val prepared = api.preparePhoto(mime)
                val upload = prepared.getJSONObject("upload")
                api.uploadPreparedPhoto(
                    upload.getString("url"),
                    mime,
                    bytes,
                )
                api.finalizePhoto(prepared.getString("ticket"))
            }.onSuccess {
                setStatus("Фото загружено и отправлено на модерацию.")
                loadState()
            }.onFailure { error ->
                setStatus("Ошибка фото: " + error.message)
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        api = MatchLabApi(this)

        scroll = ScrollView(this).apply {
            isFillViewport = true
            setBackgroundColor(MatchLabStyle.color(MatchLabStyle.BG))
        }
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(
                MatchLabStyle.dp(this@OnboardingActivity, 24),
                MatchLabStyle.dp(this@OnboardingActivity, 26),
                MatchLabStyle.dp(this@OnboardingActivity, 24),
                MatchLabStyle.dp(this@OnboardingActivity, 56),
            )
        }
        scroll.addView(root)
        setContentView(scroll)

        if (!api.hasSession()) {
            finish()
            return
        }
        loadState()
    }

    private fun loadState() {
        lifecycleScope.launch {
            renderLoading("Загружаем профиль…")
            runCatching { api.getOnboarding() }
                .onSuccess { state ->
                    renderNextStep(state)
                }
                .onFailure { error ->
                    renderError("Не удалось загрузить профиль: " + error.message)
                }
        }
    }

    private fun renderNextStep(state: JSONObject) {
        val completion = state.getJSONObject("completion")
        when {
            !completion.optBoolean("basic") -> {
                currentStep = 1
                renderBasic(state)
            }
            !completion.optBoolean("relationship") -> {
                currentStep = 2
                renderRelationship()
            }
            !completion.optBoolean("readiness") -> {
                currentStep = 3
                renderReadiness()
            }
            !completion.optBoolean("details") -> {
                currentStep = 4
                renderDetails(state)
            }
            !completion.optBoolean("questionnaire") -> {
                currentStep = 5
                renderQuestionnaire()
            }
            !completion.optBoolean("partner_preferences") -> {
                currentStep = 6
                renderPreferences(state)
            }
            !completion.optBoolean("photos") -> {
                currentStep = 7
                renderPhotos(state)
            }
            else -> {
                currentStep = 7
                renderWaitlist(state)
            }
        }
    }

    private fun reset(title: String, subtitle: String) {
        root.removeAllViews()

        val brand = TextView(this).apply {
            text = MatchLabStyle.brandText()
            textSize = 22f
            typeface = Typeface.create("sans", Typeface.BOLD)
        }
        root.addView(brand)

        val progressHeader = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(
                0,
                MatchLabStyle.dp(this@OnboardingActivity, 18),
                0,
                MatchLabStyle.dp(this@OnboardingActivity, 6),
            )
        }
        progressHeader.addView(TextView(this).apply {
            text = "Шаг " + currentStep.toString() + " из " + totalSteps.toString()
            MatchLabStyle.subtitle(this)
            textSize = 13f
        })
        root.addView(progressHeader)

        val progress = ProgressBar(
            this,
            null,
            android.R.attr.progressBarStyleHorizontal,
        ).apply {
            max = totalSteps
            this.progress = currentStep
            minimumHeight = MatchLabStyle.dp(this@OnboardingActivity, 5)
        }
        MatchLabStyle.progress(progress)
        root.addView(progress)

        addTitle(title)
        addText(subtitle, 16f)

        status = TextView(this).apply {
            MatchLabStyle.status(this)
            visibility = View.GONE
        }
        root.addView(status)
        MatchLabStyle.withMargins(status, top = 8)
        scroll.scrollTo(0, 0)
    }

    private fun renderLoading(message: String) {
        root.removeAllViews()
        root.addView(TextView(this).apply {
            text = MatchLabStyle.brandText()
            textSize = 30f
            typeface = Typeface.create("sans", Typeface.BOLD)
        })
        addTitle("Подбираем следующий шаг")
        addText(message, 16f)
        status = TextView(this).apply {
            MatchLabStyle.status(this)
            visibility = View.GONE
        }
        root.addView(status)
    }

    private fun renderError(message: String) {
        reset("MatchLab", "Не удалось продолжить онбординг.")
        setStatus(message)
        addButton("Повторить") { loadState() }
    }

    private fun renderBasic(state: JSONObject) {
        reset(
            "О вас",
            "Начнём с базовой информации. MatchLab доступен только пользователям 18+."
        )

        val existing = state.optJSONObject("profile")
        val name = field(
            "Имя",
            existing?.optString("display_name").orEmpty()
        )
        val dob = field(
            "Дата рождения, ГГГГ-ММ-ДД",
            existing?.optString("dob").orEmpty()
        )

        addLabel("Ваш пол")
        val gender = choiceSpinner(
            listOf(
                Choice("Мужчина", "M"),
                Choice("Женщина", "F"),
                Choice("Другое", "OTHER"),
            ),
            existing?.optString("gender")
        )

        addLabel("С кем хотите знакомиться")
        val seek = choiceSpinner(
            listOf(
                Choice("Женщины", "F"),
                Choice("Мужчины", "M"),
                Choice("Не ограничивать", "ANY"),
                Choice("Другое", "OTHER"),
            ),
            existing?.optString("seek_gender")
        )

        addText("Город запуска: Алматы", 14f)

        addButton("Продолжить") {
            lifecycleScope.launch {
                setStatus("Сохраняем…")
                runCatching {
                    api.saveBasicProfile(
                        displayName = name.text.toString().trim(),
                        dob = dob.text.toString().trim(),
                        gender = selected(gender),
                        seekGender = selected(seek),
                    )
                }.onSuccess {
                    loadState()
                }.onFailure { error ->
                    setStatus("Проверьте данные: " + error.message)
                }
            }
        }
    }

    private fun renderRelationship() {
        reset(
            "Статус знакомства",
            "Для качественной базы нам важно понимать, свободны ли вы сейчас и открыты ли к знакомству."
        )

        addLabel("Сейчас вы в отношениях?")
        val relationship = choiceSpinner(
            listOf(
                Choice("Нет", "NO"),
                Choice("Да", "YES"),
            )
        )

        addLabel("Насколько вы открыты к знакомству?")
        val openness = choiceSpinner(
            listOf(
                Choice("Активно ищу", "ACTIVE"),
                Choice("Открыт(а), если встретится подходящий человек", "OPEN"),
                Choice("Пока не уверен(а)", "UNSURE"),
                Choice("Сейчас не хочу знакомиться", "NO"),
            )
        )

        addButton("Сохранить") {
            lifecycleScope.launch {
                setStatus("Сохраняем статус…")
                runCatching {
                    api.saveRelationship(
                        inRelationship = selected(relationship) == "YES",
                        openness = selected(openness),
                    )
                }.onSuccess {
                    loadState()
                }.onFailure { error ->
                    setStatus("Ошибка: " + error.message)
                }
            }
        }
    }

    private fun renderReadiness() {
        reset(
            "Готовность к знакомству",
            "Это помогает не показывать друг другу людей с совершенно разным темпом общения."
        )

        addLabel("Готовы переписываться с подходящим человеком?")
        val chat = choiceSpinner(
            listOf(
                Choice("Да", "YES"),
                Choice("Скорее да", "RATHER_YES"),
                Choice("Пока только смотрю", "LOOK_ONLY"),
            )
        )

        addLabel("Готовы встретиться офлайн, если общение пойдёт хорошо?")
        val offline = choiceSpinner(
            listOf(
                Choice("Да", "YES"),
                Choice("Возможно", "MAYBE"),
                Choice("Нет", "NO"),
            )
        )

        addButton("Продолжить") {
            lifecycleScope.launch {
                setStatus("Сохраняем…")
                runCatching {
                    api.saveReadiness(
                        chat = selected(chat),
                        offline = selected(offline),
                    )
                }.onSuccess {
                    loadState()
                }.onFailure { error ->
                    setStatus("Ошибка: " + error.message)
                }
            }
        }
    }

    private fun renderDetails(state: JSONObject) {
        reset(
            "Профиль для подбора",
            "Эти данные используются как ваши характеристики и для взаимных критериев."
        )
        val existing = state.optJSONObject("profile")
        val existingHeight = existing?.optInt("height", 0) ?: 0

        val height = field(
            "Рост, см",
            if (existingHeight > 0) existingHeight.toString() else "",
            InputType.TYPE_CLASS_NUMBER,
        )

        addLabel("Цель знакомства")
        val goal = choiceSpinner(
            listOf(
                Choice("Серьёзные отношения", "SERIOUS"),
                Choice("Семья", "FAMILY"),
                Choice("Посмотреть, как сложится", "SEE"),
                Choice("Общение", "CHAT"),
                Choice("Пока не определился(ась)", "UNKNOWN"),
            ),
            existing?.optString("dating_goal")
        )

        addLabel("Дети сейчас")
        val children = choiceSpinner(
            listOf(
                Choice("Нет детей", "NO_CHILDREN"),
                Choice("Есть дети", "HAS_CHILDREN"),
            ),
            existing?.optString("children_status")
        )

        addLabel("Планы на детей")
        val childrenPlans = choiceSpinner(
            listOf(
                Choice("Хочу", "WANTS"),
                Choice("Возможно", "MAYBE"),
                Choice("Не хочу", "DOES_NOT_WANT"),
            ),
            existing?.optString("children_plans")
        )

        addLabel("Курение")
        val smoking = choiceSpinner(
            listOf(
                Choice("Не курю", "NO"),
                Choice("Редко", "RARE"),
                Choice("Курю", "YES"),
            ),
            existing?.optString("smoking")
        )

        addLabel("Алкоголь")
        val alcohol = choiceSpinner(
            listOf(
                Choice("Не употребляю", "NO"),
                Choice("Редко", "RARE"),
                Choice("Умеренно", "MODERATE"),
                Choice("Регулярно", "YES"),
            ),
            existing?.optString("alcohol")
        )

        addLabel("Образ жизни")
        val lifestyle = choiceSpinner(
            listOf(
                Choice("Спокойный", "CALM"),
                Choice("Сбалансированный", "BALANCED"),
                Choice("Активный", "ACTIVE"),
                Choice("Очень активный", "VERY_ACTIVE"),
            ),
            existing?.optString("lifestyle")
        )

        val bio = field(
            "Коротко о себе (необязательно)",
            existing?.optString("bio").orEmpty()
        )

        addButton("Сохранить") {
            lifecycleScope.launch {
                val heightValue = height.text.toString().trim().toIntOrNull()
                if (heightValue == null) {
                    setStatus("Укажите рост числом.")
                    return@launch
                }
                setStatus("Сохраняем…")
                runCatching {
                    api.saveProfileDetails(
                        height = heightValue,
                        datingGoal = selected(goal),
                        childrenStatus = selected(children),
                        childrenPlans = selected(childrenPlans),
                        smoking = selected(smoking),
                        alcohol = selected(alcohol),
                        lifestyle = selected(lifestyle),
                        bio = bio.text.toString().trim(),
                    )
                }.onSuccess {
                    loadState()
                }.onFailure { error ->
                    setStatus("Ошибка: " + error.message)
                }
            }
        }
    }

    private fun renderQuestionnaire() {
        lifecycleScope.launch {
            renderLoading("Загружаем вопросы…")
            runCatching { api.getQuestionnaire() }
                .onSuccess { payload ->
                    val progress = payload.getJSONObject("progress")
                    val answers = payload.optJSONObject("answers") ?: JSONObject()
                    val sections = payload.getJSONArray("sections")

                    var nextQuestion: JSONObject? = null
                    var sectionName = ""
                    loop@ for (i in 0 until sections.length()) {
                        val section = sections.getJSONObject(i)
                        val questions = section.getJSONArray("questions")
                        for (j in 0 until questions.length()) {
                            val question = questions.getJSONObject(j)
                            val key = question.getLong("id").toString()
                            if (!answers.has(key)) {
                                nextQuestion = question
                                sectionName = section.getString("category")
                                break@loop
                            }
                        }
                    }

                    val question = nextQuestion
                    if (question == null) {
                        loadState()
                        return@onSuccess
                    }

                    reset(
                        "Анкета совместимости",
                        sectionName + " · " +
                            (progress.optInt("required_answered") + 1).toString() +
                            " из " + progress.optInt("required_total").toString()
                    )
                    addText(question.getString("text"), 20f)

                    val group = RadioGroup(this@OnboardingActivity).apply {
                        orientation = RadioGroup.VERTICAL
                    }
                    val options = question.getJSONArray("options")
                    for (i in 0 until options.length()) {
                        val option = options.getJSONObject(i)
                        val button = RadioButton(this@OnboardingActivity).apply {
                            id = View.generateViewId()
                            text = option.getString("label")
                            tag = option.getInt("value")
                            textSize = 16f
                            MatchLabStyle.radioOption(this)
                        }
                        group.addView(button)
                        MatchLabStyle.withMargins(button, top = 8)
                    }
                    root.addView(group)

                    addButton("Ответить и дальше") {
                        val checkedId = group.checkedRadioButtonId
                        if (checkedId == -1) {
                            setStatus("Выберите вариант ответа.")
                            return@addButton
                        }
                        val checked = group.findViewById<RadioButton>(checkedId)
                        lifecycleScope.launch {
                            setStatus("Сохраняем ответ…")
                            runCatching {
                                api.saveQuestionnaireAnswer(
                                    question.getLong("id"),
                                    checked.tag as Int,
                                )
                            }.onSuccess {
                                renderQuestionnaire()
                            }.onFailure { error ->
                                setStatus("Ошибка: " + error.message)
                            }
                        }
                    }

                    addButton("Вернуться позже") { finish() }
                }
                .onFailure { error ->
                    renderError("Не удалось загрузить анкету: " + error.message)
                }
        }
    }

    private fun renderPreferences(state: JSONObject) {
        reset(
            "Кого вы ищете",
            "Укажите реальные критерии. Позже их можно будет изменить."
        )

        val profile = state.optJSONObject("profile")
        val seekGender = profile?.optString("seek_gender", "F") ?: "F"

        val ageMin = field("Возраст от", "22", InputType.TYPE_CLASS_NUMBER)
        val ageMax = field("Возраст до", "40", InputType.TYPE_CLASS_NUMBER)
        val ageImportance = importanceSpinner("HARD")

        addLabel("Пол")
        val gender = choiceSpinner(
            listOf(
                Choice("Женщина", "F"),
                Choice("Мужчина", "M"),
                Choice("Другое", "OTHER"),
            ),
            if (seekGender == "ANY") null else seekGender
        )
        val genderImportance = importanceSpinner("HARD")

        val distance = field("Максимальное расстояние, км", "50", InputType.TYPE_CLASS_NUMBER)
        val distanceImportance = importanceSpinner("PREFERENCE")

        addLabel("Цель знакомства партнёра")
        val goal = choiceSpinner(
            listOf(
                Choice("Серьёзные отношения", "SERIOUS"),
                Choice("Семья", "FAMILY"),
                Choice("Посмотреть, как сложится", "SEE"),
                Choice("Общение", "CHAT"),
                Choice("Не определился(ась)", "UNKNOWN"),
            )
        )
        val goalImportance = importanceSpinner("IMPORTANT")

        addLabel("Наличие детей")
        val children = choiceSpinner(
            listOf(
                Choice("Не важно", "ANY"),
                Choice("Нет детей", "NO_CHILDREN"),
                Choice("Есть дети", "HAS_CHILDREN"),
            )
        )
        val childrenImportance = importanceSpinner("PREFERENCE")

        addLabel("Планы на детей")
        val childrenPlans = choiceSpinner(
            listOf(
                Choice("Не важно", "ANY"),
                Choice("Хочет", "WANTS"),
                Choice("Возможно", "MAYBE"),
                Choice("Не хочет", "DOES_NOT_WANT"),
            )
        )
        val childrenPlansImportance = importanceSpinner("IMPORTANT")

        addLabel("Курение")
        val smoking = choiceSpinner(
            listOf(
                Choice("Не важно", "ANY"),
                Choice("Не курит", "NO"),
                Choice("Редко", "RARE"),
                Choice("Курит", "YES"),
            )
        )
        val smokingImportance = importanceSpinner("PREFERENCE")

        addLabel("Алкоголь")
        val alcohol = choiceSpinner(
            listOf(
                Choice("Не важно", "ANY"),
                Choice("Не употребляет", "NO"),
                Choice("Редко", "RARE"),
                Choice("Умеренно", "MODERATE"),
                Choice("Регулярно", "YES"),
            )
        )
        val alcoholImportance = importanceSpinner("PREFERENCE")

        addLabel("Образ жизни")
        val lifestyle = choiceSpinner(
            listOf(
                Choice("Не важно", "ANY"),
                Choice("Спокойный", "CALM"),
                Choice("Сбалансированный", "BALANCED"),
                Choice("Активный", "ACTIVE"),
                Choice("Очень активный", "VERY_ACTIVE"),
            )
        )
        val lifestyleImportance = importanceSpinner("PREFERENCE")

        val heightMin = field("Рост от, см", "150", InputType.TYPE_CLASS_NUMBER)
        val heightMax = field("Рост до, см", "210", InputType.TYPE_CLASS_NUMBER)
        val heightImportance = importanceSpinner("IGNORE")

        addButton("Сохранить критерии") {
            lifecycleScope.launch {
                setStatus("Сохраняем критерии…")
                runCatching {
                    fun number(input: EditText, label: String): Int {
                        return input.text.toString().trim().toIntOrNull()
                            ?: throw IllegalArgumentException("Заполните: " + label)
                    }

                    val preferences = JSONObject()

                    fun putRange(
                        key: String,
                        importance: Spinner,
                        min: Int,
                        max: Int,
                    ) {
                        val imp = selected(importance)
                        val cfg = JSONObject().put("importance", imp)
                        if (imp != "IGNORE") {
                            cfg.put(
                                "value",
                                JSONObject().put("min", min).put("max", max)
                            )
                        }
                        preferences.put(key, cfg)
                    }

                    fun putMax(
                        key: String,
                        importance: Spinner,
                        max: Int,
                    ) {
                        val imp = selected(importance)
                        val cfg = JSONObject().put("importance", imp)
                        if (imp != "IGNORE") {
                            cfg.put("value", JSONObject().put("max", max))
                        }
                        preferences.put(key, cfg)
                    }

                    fun putMulti(
                        key: String,
                        importance: Spinner,
                        value: String,
                    ) {
                        val imp = selected(importance)
                        val cfg = JSONObject().put("importance", imp)
                        if (imp != "IGNORE") {
                            cfg.put("value", JSONArray().put(value))
                        }
                        preferences.put(key, cfg)
                    }

                    putRange(
                        "age",
                        ageImportance,
                        number(ageMin, "возраст от"),
                        number(ageMax, "возраст до"),
                    )
                    putMulti("gender", genderImportance, selected(gender))
                    preferences.put(
                        "market",
                        JSONObject()
                            .put("importance", "HARD")
                            .put("value", JSONArray().put("KZ-ALA"))
                    )
                    putMax(
                        "distance_km",
                        distanceImportance,
                        number(distance, "расстояние"),
                    )
                    putMulti("dating_goal", goalImportance, selected(goal))
                    putMulti("children_status", childrenImportance, selected(children))
                    putMulti("children_plans", childrenPlansImportance, selected(childrenPlans))
                    putMulti("smoking", smokingImportance, selected(smoking))
                    putMulti("alcohol", alcoholImportance, selected(alcohol))
                    putMulti("lifestyle", lifestyleImportance, selected(lifestyle))
                    putRange(
                        "height",
                        heightImportance,
                        number(heightMin, "рост от"),
                        number(heightMax, "рост до"),
                    )

                    api.savePreferences(preferences)
                }.onSuccess {
                    loadState()
                }.onFailure { error ->
                    setStatus("Проверьте критерии: " + error.message)
                }
            }
        }
    }

    private fun renderPhotos(state: JSONObject) {
        val photos = state.optJSONObject("photos") ?: JSONObject()
        val approved = photos.optInt("approved")
        val pending = photos.optInt("pending")
        val rejected = photos.optInt("rejected")

        reset(
            "Фото профиля",
            "Нужно минимум 2 одобренных фото. Рекомендуем 3–5."
        )
        addText(
            "Одобрено: " + approved.toString() +
                " · На модерации: " + pending.toString() +
                " · Отклонено: " + rejected.toString(),
            16f
        )
        addText(
            "Фото хранятся в приватном хранилище и становятся видимыми только после модерации.",
            14f
        )

        addButton("Добавить фото") {
            photoPicker.launch("image/*")
        }
        addButton("Обновить статус") {
            loadState()
        }
        addButton("Вернуться позже") {
            finish()
        }
    }

    private fun renderWaitlist(state: JSONObject) {
        val waitlist = state.optJSONObject("waitlist") ?: JSONObject()
        reset(
            "Профиль готов",
            waitlist.optString(
                "message",
                "Профиль заполнен и готов к следующему этапу."
            )
        )
        addText("Статус: " + waitlist.optString("state"), 16f)

        addButton("Мой профиль совместимости") {
            lifecycleScope.launch {
                setStatus("Считаем профиль…")
                runCatching { api.getCompatibilityProfile() }
                    .onSuccess { result ->
                        val summary = result.optJSONObject("summary") ?: JSONObject()
                        val lines = mutableListOf<String>()
                        val keys = summary.keys()
                        while (keys.hasNext()) {
                            val key = keys.next()
                            lines += key + ": " + summary.optInt(key).toString() + "%"
                        }
                        val note = result.optString("note")
                        setStatus(
                            if (lines.isEmpty()) note
                            else lines.joinToString("\n") + "\n\n" + note
                        )
                    }
                    .onFailure { error ->
                        setStatus("Пока недоступно: " + error.message)
                    }
            }
        }

        addButton("Обновить статус") { loadState() }
    }

    private fun addTitle(text: String) {
        root.addView(TextView(this).apply {
            this.text = text
            MatchLabStyle.title(this)
            setPadding(
                0,
                MatchLabStyle.dp(this@OnboardingActivity, 22),
                0,
                MatchLabStyle.dp(this@OnboardingActivity, 8),
            )
        })
    }

    private fun addText(text: String, size: Float) {
        root.addView(TextView(this).apply {
            this.text = text
            MatchLabStyle.subtitle(this)
            textSize = size
            setPadding(
                0,
                MatchLabStyle.dp(this@OnboardingActivity, 4),
                0,
                MatchLabStyle.dp(this@OnboardingActivity, 14),
            )
        })
    }

    private fun addLabel(text: String) {
        root.addView(TextView(this).apply {
            this.text = text
            MatchLabStyle.label(this)
            setPadding(
                0,
                MatchLabStyle.dp(this@OnboardingActivity, 18),
                0,
                MatchLabStyle.dp(this@OnboardingActivity, 7),
            )
        })
    }

    private fun field(
        hint: String,
        value: String = "",
        inputTypeValue: Int = InputType.TYPE_CLASS_TEXT,
    ): EditText {
        val edit = EditText(this).apply {
            this.hint = hint
            setText(value)
            inputType = inputTypeValue
            MatchLabStyle.input(this)
        }
        root.addView(edit)
        MatchLabStyle.withMargins(edit, top = 6)
        return edit
    }

    private fun choiceSpinner(
        values: List<Choice>,
        selectedValue: String? = null,
    ): Spinner {
        val spinner = Spinner(this)
        val adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_item,
            values,
        ).also { adapterValue ->
            adapterValue.setDropDownViewResource(
                android.R.layout.simple_spinner_dropdown_item
            )
        }
        spinner.adapter = adapter
        val index = values.indexOfFirst { item -> item.value == selectedValue }
        if (index >= 0) spinner.setSelection(index)
        MatchLabStyle.spinner(spinner)
        root.addView(spinner)
        return spinner
    }

    private fun importanceSpinner(default: String): Spinner {
        addLabel("Насколько это важно?")
        return choiceSpinner(
            listOf(
                Choice("Обязательно", "HARD"),
                Choice("Важно", "IMPORTANT"),
                Choice("Предпочтительно", "PREFERENCE"),
                Choice("Не учитывать", "IGNORE"),
            ),
            default,
        )
    }

    private fun selected(spinner: Spinner): String =
        (spinner.selectedItem as Choice).value

    private fun addButton(text: String, action: () -> Unit) {
        val button = Button(this).apply {
            this.text = text
            MatchLabStyle.primaryButton(this)
            setOnClickListener { action() }
        }
        root.addView(button)
        MatchLabStyle.withMargins(button, top = 14)
    }

    private fun setStatus(text: String) {
        status.text = text
        status.visibility = View.VISIBLE
    }
}
