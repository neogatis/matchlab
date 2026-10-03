package com.neogatis.matchlab

import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class RegistrationActivity : AppCompatActivity() {
    private lateinit var api: MatchLabApi
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        api = MatchLabApi(this)

        val scroll = ScrollView(this).apply {
            isFillViewport = true
            setBackgroundColor(MatchLabStyle.color(MatchLabStyle.BG))
        }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(
                MatchLabStyle.dp(this@RegistrationActivity, 24),
                MatchLabStyle.dp(this@RegistrationActivity, 36),
                MatchLabStyle.dp(this@RegistrationActivity, 24),
                MatchLabStyle.dp(this@RegistrationActivity, 40),
            )
        }
        scroll.addView(root)

        root.addView(TextView(this).apply {
            text = MatchLabStyle.brandText()
            textSize = 34f
            typeface = Typeface.create("sans", Typeface.BOLD)
        })

        root.addView(TextView(this).apply {
            text = "Создайте профиль"
            MatchLabStyle.title(this)
            setPadding(0, MatchLabStyle.dp(this@RegistrationActivity, 24), 0, 0)
        })
        root.addView(TextView(this).apply {
            text = "Регистрация займёт пару минут. Дальше — анкета совместимости и критерии партнёра."
            MatchLabStyle.subtitle(this)
            textSize = 16f
            setPadding(
                0,
                MatchLabStyle.dp(this@RegistrationActivity, 8),
                0,
                MatchLabStyle.dp(this@RegistrationActivity, 18),
            )
        })

        val topTabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        val loginTab = Button(this).apply {
            text = "Вход"
            layoutParams = LinearLayout.LayoutParams(
                0,
                MatchLabStyle.dp(this@RegistrationActivity, 52),
                1f,
            ).apply {
                marginEnd = MatchLabStyle.dp(this@RegistrationActivity, 6)
            }
            MatchLabStyle.secondaryButton(this)
        }
        val registerTab = Button(this).apply {
            text = "Регистрация"
            layoutParams = LinearLayout.LayoutParams(
                0,
                MatchLabStyle.dp(this@RegistrationActivity, 52),
                1f,
            ).apply {
                marginStart = MatchLabStyle.dp(this@RegistrationActivity, 6)
            }
            MatchLabStyle.primaryButton(this)
        }
        topTabs.addView(loginTab)
        topTabs.addView(registerTab)
        root.addView(topTabs)

        loginTab.setOnClickListener {
            finish()
        }

        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(
                MatchLabStyle.dp(this@RegistrationActivity, 18),
                MatchLabStyle.dp(this@RegistrationActivity, 20),
                MatchLabStyle.dp(this@RegistrationActivity, 18),
                MatchLabStyle.dp(this@RegistrationActivity, 20),
            )
        }
        MatchLabStyle.card(card)
        root.addView(card)
        MatchLabStyle.withMargins(card, top = 16)

        val methodTabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        val phoneTab = Button(this).apply {
            text = "По номеру"
            layoutParams = LinearLayout.LayoutParams(
                0,
                MatchLabStyle.dp(this@RegistrationActivity, 50),
                1f,
            ).apply {
                marginEnd = MatchLabStyle.dp(this@RegistrationActivity, 6)
            }
        }
        val emailTab = Button(this).apply {
            text = "По email"
            layoutParams = LinearLayout.LayoutParams(
                0,
                MatchLabStyle.dp(this@RegistrationActivity, 50),
                1f,
            ).apply {
                marginStart = MatchLabStyle.dp(this@RegistrationActivity, 6)
            }
        }
        methodTabs.addView(phoneTab)
        methodTabs.addView(emailTab)
        card.addView(methodTabs)

        val phoneContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        val phone = EditText(this).apply {
            hint = "+7 747 123 45 67"
            inputType = InputType.TYPE_CLASS_PHONE
            MatchLabStyle.input(this)
        }
        phoneContainer.addView(phone)
        MatchLabStyle.withMargins(phone, top = 14)

        val phonePassword = EditText(this).apply {
            hint = "Придумайте пароль"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            MatchLabStyle.input(this)
        }
        phoneContainer.addView(phonePassword)
        MatchLabStyle.withMargins(phonePassword, top = 10)

        val requestCode = Button(this).apply {
            text = "Получить SMS-код  →"
            MatchLabStyle.primaryButton(this)
        }
        phoneContainer.addView(requestCode)
        MatchLabStyle.withMargins(requestCode, top = 12)

        val code = EditText(this).apply {
            hint = "6-значный код"
            inputType = InputType.TYPE_CLASS_NUMBER
            visibility = View.GONE
            MatchLabStyle.input(this)
        }
        phoneContainer.addView(code)
        MatchLabStyle.withMargins(code, top = 12)

        val finishPhone = Button(this).apply {
            text = "Создать аккаунт  →"
            visibility = View.GONE
            MatchLabStyle.primaryButton(this)
        }
        phoneContainer.addView(finishPhone)
        MatchLabStyle.withMargins(finishPhone, top = 12)

        phoneContainer.addView(TextView(this).apply {
            text = "Номер будет подтверждён одноразовым кодом. Пароль — минимум 10 символов."
            MatchLabStyle.subtitle(this)
            textSize = 12f
            setPadding(4, 8, 4, 0)
        })
        card.addView(phoneContainer)

        val emailContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
        }
        val email = EditText(this).apply {
            hint = "Email"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
            MatchLabStyle.input(this)
        }
        emailContainer.addView(email)
        MatchLabStyle.withMargins(email, top = 14)

        val emailPassword = EditText(this).apply {
            hint = "Придумайте пароль"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            MatchLabStyle.input(this)
        }
        emailContainer.addView(emailPassword)
        MatchLabStyle.withMargins(emailPassword, top = 10)

        val finishEmail = Button(this).apply {
            text = "Зарегистрироваться  →"
            MatchLabStyle.primaryButton(this)
        }
        emailContainer.addView(finishEmail)
        MatchLabStyle.withMargins(finishEmail, top = 12)

        emailContainer.addView(TextView(this).apply {
            text = "После регистрации сразу перейдём к созданию профиля."
            MatchLabStyle.subtitle(this)
            textSize = 12f
            setPadding(4, 8, 4, 0)
        })
        card.addView(emailContainer)

        fun showPhone() {
            phoneContainer.visibility = View.VISIBLE
            emailContainer.visibility = View.GONE
            MatchLabStyle.primaryButton(phoneTab)
            MatchLabStyle.secondaryButton(emailTab)
        }

        fun showEmail() {
            phoneContainer.visibility = View.GONE
            emailContainer.visibility = View.VISIBLE
            MatchLabStyle.secondaryButton(phoneTab)
            MatchLabStyle.primaryButton(emailTab)
        }

        phoneTab.setOnClickListener { showPhone() }
        emailTab.setOnClickListener { showEmail() }
        showPhone()

        status = TextView(this).apply {
            MatchLabStyle.status(this)
            visibility = View.GONE
        }
        card.addView(status)
        MatchLabStyle.withMargins(status, top = 14)

        requestCode.setOnClickListener {
            val phoneValue = phone.text.toString().trim()
            val passwordValue = phonePassword.text.toString()
            if (phoneValue.isBlank()) {
                showStatus("Введите номер телефона.")
                return@setOnClickListener
            }
            if (passwordValue.length < 10) {
                showStatus("Пароль должен содержать минимум 10 символов.")
                return@setOnClickListener
            }
            lifecycleScope.launch {
                showStatus("Отправляем SMS…")
                runCatching {
                    api.requestPhoneRegistrationCode(phoneValue)
                }.onSuccess {
                    showStatus("Код отправлен. Введите 6 цифр из SMS.")
                    code.visibility = View.VISIBLE
                    finishPhone.visibility = View.VISIBLE
                    code.requestFocus()
                }.onFailure {
                    showStatus("Не удалось отправить код: " + it.message)
                }
            }
        }

        finishPhone.setOnClickListener {
            val phoneValue = phone.text.toString().trim()
            val codeValue = code.text.toString().trim()
            val passwordValue = phonePassword.text.toString()
            lifecycleScope.launch {
                showStatus("Создаём аккаунт…")
                runCatching {
                    api.verifyPhoneRegistrationCode(
                        phone = phoneValue,
                        code = codeValue,
                        password = passwordValue,
                    )
                }.onSuccess { userId ->
                    onRegistered(userId)
                }.onFailure {
                    showStatus("Ошибка регистрации: " + it.message)
                }
            }
        }

        finishEmail.setOnClickListener {
            val emailValue = email.text.toString().trim()
            val passwordValue = emailPassword.text.toString()
            if (emailValue.isBlank()) {
                showStatus("Введите email.")
                return@setOnClickListener
            }
            if (passwordValue.length < 10) {
                showStatus("Пароль должен содержать минимум 10 символов.")
                return@setOnClickListener
            }
            lifecycleScope.launch {
                showStatus("Создаём аккаунт…")
                runCatching {
                    api.registerEmail(emailValue, passwordValue)
                }.onSuccess { userId ->
                    onRegistered(userId)
                }.onFailure {
                    showStatus("Ошибка регистрации: " + it.message)
                }
            }
        }

        setContentView(scroll)
    }

    private fun onRegistered(userId: Long) {
        startActivity(Intent(this, OnboardingActivity::class.java))
        finish()
    }

    private fun showStatus(message: String) {
        status.text = message
        status.visibility = View.VISIBLE
    }
}
