package com.neogatis.matchlab

import android.Manifest
import android.content.Intent
import android.graphics.Typeface
import android.os.Build
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
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.lifecycle.lifecycleScope
import com.google.android.gms.common.ConnectionResult
import com.google.android.gms.common.GoogleApiAvailability
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {
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
                MatchLabStyle.dp(this@MainActivity, 24),
                MatchLabStyle.dp(this@MainActivity, 36),
                MatchLabStyle.dp(this@MainActivity, 24),
                MatchLabStyle.dp(this@MainActivity, 40),
            )
        }
        scroll.addView(root)

        val brandRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        brandRow.addView(TextView(this).apply {
            text = "♡"
            textSize = 42f
            setTextColor(MatchLabStyle.color(MatchLabStyle.CORAL))
            typeface = Typeface.create("sans", Typeface.BOLD)
            gravity = Gravity.CENTER
            setPadding(0, 0, MatchLabStyle.dp(this@MainActivity, 8), 0)
        })
        brandRow.addView(TextView(this).apply {
            text = MatchLabStyle.brandText()
            textSize = 34f
            typeface = Typeface.create("sans", Typeface.BOLD)
        })
        root.addView(brandRow)

        root.addView(TextView(this).apply {
            text = "Не выбирай из всех.\nНайди подходящего."
            MatchLabStyle.title(this)
            textSize = 31f
            setPadding(0, MatchLabStyle.dp(this@MainActivity, 28), 0, 0)
        })

        root.addView(TextView(this).apply {
            text = "Совместимость. Общие ценности. Серьёзные намерения."
            MatchLabStyle.subtitle(this)
            textSize = 16f
            setPadding(
                0,
                MatchLabStyle.dp(this@MainActivity, 10),
                0,
                MatchLabStyle.dp(this@MainActivity, 22),
            )
        })

        val valueCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(
                MatchLabStyle.dp(this@MainActivity, 18),
                MatchLabStyle.dp(this@MainActivity, 18),
                MatchLabStyle.dp(this@MainActivity, 18),
                MatchLabStyle.dp(this@MainActivity, 18),
            )
        }
        MatchLabStyle.card(valueCard)
        addTrustItem(valueCard, "♡", "Глубокая совместимость", "Ценности, характер и жизненные планы")
        addTrustItem(valueCard, "◎", "Настоящие люди", "Качественные анкеты и модерация")
        addTrustItem(valueCard, "♥", "Серьёзные намерения", "Не свайпы, а релевантный подбор")
        root.addView(valueCard)
        MatchLabStyle.withMargins(valueCard, top = 4, bottom = 20)

        val accountTabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        val accountLoginTab = Button(this).apply {
            text = "Вход"
            layoutParams = LinearLayout.LayoutParams(
                0,
                MatchLabStyle.dp(this@MainActivity, 52),
                1f,
            ).apply {
                marginEnd = MatchLabStyle.dp(this@MainActivity, 6)
            }
            MatchLabStyle.primaryButton(this)
        }
        val accountRegisterTab = Button(this).apply {
            text = "Регистрация"
            layoutParams = LinearLayout.LayoutParams(
                0,
                MatchLabStyle.dp(this@MainActivity, 52),
                1f,
            ).apply {
                marginStart = MatchLabStyle.dp(this@MainActivity, 6)
            }
            MatchLabStyle.secondaryButton(this)
        }
        accountTabs.addView(accountLoginTab)
        accountTabs.addView(accountRegisterTab)
        root.addView(accountTabs)
        MatchLabStyle.withMargins(accountTabs, top = 0, bottom = 14)

        accountRegisterTab.setOnClickListener {
            startActivity(Intent(this, RegistrationActivity::class.java))
        }

        val authCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(
                MatchLabStyle.dp(this@MainActivity, 18),
                MatchLabStyle.dp(this@MainActivity, 20),
                MatchLabStyle.dp(this@MainActivity, 18),
                MatchLabStyle.dp(this@MainActivity, 20),
            )
        }
        MatchLabStyle.card(authCard)

        authCard.addView(TextView(this).apply {
            text = "Войти в MatchLab"
            setTextColor(MatchLabStyle.color(MatchLabStyle.NAVY))
            textSize = 21f
            typeface = Typeface.create("serif", Typeface.BOLD)
        })
        authCard.addView(TextView(this).apply {
            text = "По SMS-коду или паролю — как удобнее."
            MatchLabStyle.subtitle(this)
            setPadding(
                0,
                MatchLabStyle.dp(this@MainActivity, 5),
                0,
                MatchLabStyle.dp(this@MainActivity, 14),
            )
        })

        val tabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        val smsTab = Button(this).apply {
            text = "SMS-код"
            layoutParams = LinearLayout.LayoutParams(
                0,
                MatchLabStyle.dp(this@MainActivity, 52),
                1f,
            ).apply {
                marginEnd = MatchLabStyle.dp(this@MainActivity, 6)
            }
        }
        val passwordTab = Button(this).apply {
            text = "Пароль"
            layoutParams = LinearLayout.LayoutParams(
                0,
                MatchLabStyle.dp(this@MainActivity, 52),
                1f,
            ).apply {
                marginStart = MatchLabStyle.dp(this@MainActivity, 6)
            }
        }
        tabs.addView(smsTab)
        tabs.addView(passwordTab)
        authCard.addView(tabs)

        val smsContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        val phoneInput = EditText(this).apply {
            hint = "+7 747 123 45 67"
            inputType = InputType.TYPE_CLASS_PHONE
            MatchLabStyle.input(this)
        }
        smsContainer.addView(phoneInput)
        MatchLabStyle.withMargins(phoneInput, top = 14)

        val sendCodeButton = Button(this).apply {
            text = "Получить код  →"
            MatchLabStyle.primaryButton(this)
        }
        smsContainer.addView(sendCodeButton)
        MatchLabStyle.withMargins(sendCodeButton, top = 12)

        val codeInput = EditText(this).apply {
            hint = "6-значный код"
            inputType = InputType.TYPE_CLASS_NUMBER
            visibility = View.GONE
            MatchLabStyle.input(this)
        }
        smsContainer.addView(codeInput)
        MatchLabStyle.withMargins(codeInput, top = 14)

        val createPasswordInput = EditText(this).apply {
            hint = "Придумайте пароль — необязательно"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            visibility = View.GONE
            MatchLabStyle.input(this)
        }
        smsContainer.addView(createPasswordInput)
        MatchLabStyle.withMargins(createPasswordInput, top = 10)

        val passwordHint = TextView(this).apply {
            text = "Если зададите пароль от 10 символов, в следующий раз сможете войти без SMS."
            MatchLabStyle.subtitle(this)
            textSize = 12f
            visibility = View.GONE
            setPadding(4, 6, 4, 0)
        }
        smsContainer.addView(passwordHint)

        val verifyButton = Button(this).apply {
            text = "Войти  →"
            visibility = View.GONE
            MatchLabStyle.primaryButton(this)
        }
        smsContainer.addView(verifyButton)
        MatchLabStyle.withMargins(verifyButton, top = 12)

        authCard.addView(smsContainer)

        val passwordContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
        }
        val identifierInput = EditText(this).apply {
            hint = "Телефон или email"
            inputType = InputType.TYPE_CLASS_TEXT
            MatchLabStyle.input(this)
        }
        passwordContainer.addView(identifierInput)
        MatchLabStyle.withMargins(identifierInput, top = 14)

        val passwordInput = EditText(this).apply {
            hint = "Пароль"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            MatchLabStyle.input(this)
        }
        passwordContainer.addView(passwordInput)
        MatchLabStyle.withMargins(passwordInput, top = 10)

        val passwordLoginButton = Button(this).apply {
            text = "Войти по паролю  →"
            MatchLabStyle.primaryButton(this)
        }
        passwordContainer.addView(passwordLoginButton)
        MatchLabStyle.withMargins(passwordLoginButton, top = 12)

        passwordContainer.addView(TextView(this).apply {
            text = "Нет пароля? Переключитесь на SMS-код и задайте его после подтверждения номера."
            MatchLabStyle.subtitle(this)
            textSize = 12f
            setPadding(4, 8, 4, 0)
        })
        authCard.addView(passwordContainer)

        fun showSmsMode() {
            smsContainer.visibility = View.VISIBLE
            passwordContainer.visibility = View.GONE
            MatchLabStyle.primaryButton(smsTab)
            MatchLabStyle.secondaryButton(passwordTab)
        }

        fun showPasswordMode() {
            smsContainer.visibility = View.GONE
            passwordContainer.visibility = View.VISIBLE
            MatchLabStyle.secondaryButton(smsTab)
            MatchLabStyle.primaryButton(passwordTab)
        }

        smsTab.setOnClickListener { showSmsMode() }
        passwordTab.setOnClickListener { showPasswordMode() }
        showSmsMode()

        authCard.addView(TextView(this).apply {
            text = "или"
            MatchLabStyle.subtitle(this)
            gravity = Gravity.CENTER
            setPadding(
                0,
                MatchLabStyle.dp(this@MainActivity, 18),
                0,
                MatchLabStyle.dp(this@MainActivity, 10),
            )
        })

        val googleButton = Button(this).apply {
            text = "Продолжить с Google"
            MatchLabStyle.secondaryButton(this)
        }
        authCard.addView(googleButton)

        status = TextView(this).apply {
            MatchLabStyle.status(this)
            visibility = View.GONE
        }
        authCard.addView(status)
        MatchLabStyle.withMargins(status, top = 14)

        root.addView(authCard)

        root.addView(TextView(this).apply {
            text = "Больше, чем знакомства.\nЛюди, которые действительно подходят."
            MatchLabStyle.subtitle(this)
            gravity = Gravity.CENTER
            setPadding(
                0,
                MatchLabStyle.dp(this@MainActivity, 22),
                0,
                0,
            )
        })

        setContentView(scroll)

        sendCodeButton.setOnClickListener {
            val phone = phoneInput.text.toString().trim()
            if (phone.isBlank()) {
                showStatus("Введите номер телефона.")
                return@setOnClickListener
            }
            lifecycleScope.launch {
                setBusy("Отправляем SMS…")
                runCatching {
                    api.requestPhoneCode(phone)
                }.onSuccess {
                    showStatus("Код отправлен. Введите 6 цифр из SMS.")
                    codeInput.visibility = View.VISIBLE
                    createPasswordInput.visibility = View.VISIBLE
                    passwordHint.visibility = View.VISIBLE
                    verifyButton.visibility = View.VISIBLE
                    codeInput.requestFocus()
                }.onFailure {
                    showStatus("Ошибка отправки: " + it.message)
                }
            }
        }

        verifyButton.setOnClickListener {
            val phone = phoneInput.text.toString().trim()
            val code = codeInput.text.toString().trim()
            val newPassword = createPasswordInput.text.toString()
            if (newPassword.isNotBlank() && newPassword.length < 10) {
                showStatus("Пароль должен содержать минимум 10 символов.")
                return@setOnClickListener
            }
            lifecycleScope.launch {
                setBusy("Проверяем код…")
                runCatching {
                    api.verifyPhoneCode(
                        phone = phone,
                        code = code,
                        newPassword = newPassword.takeIf { it.isNotBlank() },
                    )
                }.onSuccess { userId ->
                    onAuthenticated(userId, "телефон")
                }.onFailure {
                    showStatus("Ошибка входа: " + it.message)
                }
            }
        }

        passwordLoginButton.setOnClickListener {
            val identifier = identifierInput.text.toString().trim()
            val password = passwordInput.text.toString()
            if (identifier.isBlank() || password.isBlank()) {
                showStatus("Введите телефон или email и пароль.")
                return@setOnClickListener
            }
            lifecycleScope.launch {
                setBusy("Входим…")
                runCatching {
                    api.loginWithPassword(identifier, password)
                }.onSuccess { userId ->
                    onAuthenticated(userId, "пароль")
                }.onFailure {
                    showStatus("Неверный телефон/email или пароль.")
                }
            }
        }

        googleButton.setOnClickListener {
            val playServices = GoogleApiAvailability.getInstance()
                .isGooglePlayServicesAvailable(this)
            if (playServices != ConnectionResult.SUCCESS) {
                showStatus(
                    "Google Play Services недоступны в этом Android-окружении. " +
                        "Вход по телефону работает."
                )
                return@setOnClickListener
            }

            lifecycleScope.launch {
                setBusy("Открываем Google…")
                runCatching {
                    val nonce = api.requestOidcNonce("GOOGLE")
                    val idToken = googleIdToken(nonce)
                    api.oauth("GOOGLE", idToken, nonce)
                }.onSuccess { userId ->
                    onAuthenticated(userId, "Google")
                }.onFailure {
                    showStatus("Ошибка Google Sign-In: " + it.message)
                }
            }
        }

        if (api.hasSession()) {
            lifecycleScope.launch {
                runCatching { api.listAuthMethods() }
                    .onSuccess {
                        showStatus("Сессия восстановлена.")
                        registerPush()
                        openOnboarding()
                    }
                    .onFailure {
                        showStatus("Нужно войти снова.")
                    }
            }
        }
    }

    private fun addTrustItem(
        container: LinearLayout,
        icon: String,
        title: String,
        subtitle: String,
    ) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(
                0,
                MatchLabStyle.dp(this@MainActivity, 8),
                0,
                MatchLabStyle.dp(this@MainActivity, 8),
            )
        }
        row.addView(TextView(this).apply {
            text = icon
            textSize = 24f
            gravity = Gravity.CENTER
            setTextColor(MatchLabStyle.color(MatchLabStyle.CORAL))
            background = MatchLabStyle.rounded(MatchLabStyle.SURFACE_SOFT, 20)
            val size = MatchLabStyle.dp(this@MainActivity, 44)
            layoutParams = LinearLayout.LayoutParams(size, size)
        })
        val copy = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(MatchLabStyle.dp(this@MainActivity, 12), 0, 0, 0)
        }
        copy.addView(TextView(this).apply {
            text = title
            setTextColor(MatchLabStyle.color(MatchLabStyle.NAVY))
            textSize = 15f
            typeface = Typeface.create("sans", Typeface.BOLD)
        })
        copy.addView(TextView(this).apply {
            text = subtitle
            MatchLabStyle.subtitle(this)
            textSize = 13f
        })
        row.addView(copy)
        container.addView(row)
    }

    private suspend fun googleIdToken(nonce: String): String {
        val credentialManager = CredentialManager.create(this)
        val googleIdOption = GetGoogleIdOption.Builder()
            .setFilterByAuthorizedAccounts(false)
            .setServerClientId(BuildConfig.GOOGLE_SERVER_CLIENT_ID)
            .setAutoSelectEnabled(false)
            .setNonce(nonce)
            .build()

        val request = GetCredentialRequest.Builder()
            .addCredentialOption(googleIdOption)
            .build()

        val result = credentialManager.getCredential(
            context = this,
            request = request,
        )
        val credential = result.credential

        if (
            credential is CustomCredential &&
            credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL
        ) {
            return GoogleIdTokenCredential
                .createFrom(credential.data)
                .idToken
        }
        error("Google credential type is not supported")
    }

    private fun onAuthenticated(userId: Long, method: String) {
        showStatus("Вход выполнен через " + method + ".")
        requestNotificationPermission()
        registerPush()
        openOnboarding()
    }

    private fun openOnboarding() {
        startActivity(Intent(this, OnboardingActivity::class.java))
    }

    private fun registerPush() {
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { token ->
                lifecycleScope.launch {
                    runCatching {
                        api.registerPushToken(token)
                    }
                }
            }
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33) {
            requestPermissions(
                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                1001,
            )
        }
    }

    private fun setBusy(message: String) {
        showStatus(message)
    }

    private fun showStatus(message: String) {
        status.text = message
        status.visibility = View.VISIBLE
    }
}
