package com.neogatis.matchlab

import android.Manifest
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.lifecycle.lifecycleScope
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {
    private lateinit var api: MatchLabApi
    private lateinit var status: TextView
    private lateinit var codeInput: EditText
    private lateinit var verifyButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        api = MatchLabApi(this)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 72, 48, 48)
        }

        root.addView(TextView(this).apply {
            text = "MatchLab"
            textSize = 32f
        })

        root.addView(TextView(this).apply {
            text = "Вход в ранний доступ"
            textSize = 18f
            setPadding(0, 8, 0, 32)
        })

        val phoneInput = EditText(this).apply {
            hint = "+7 747 123 45 67"
            inputType = InputType.TYPE_CLASS_PHONE
        }
        root.addView(phoneInput)

        val sendCodeButton = Button(this).apply {
            text = "Получить код"
        }
        root.addView(sendCodeButton)

        codeInput = EditText(this).apply {
            hint = "6-значный код"
            inputType = InputType.TYPE_CLASS_NUMBER
            visibility = View.GONE
        }
        root.addView(codeInput)

        verifyButton = Button(this).apply {
            text = "Войти"
            visibility = View.GONE
        }
        root.addView(verifyButton)

        root.addView(TextView(this).apply {
            text = "или"
            textSize = 15f
            gravity = android.view.Gravity.CENTER
            setPadding(0, 24, 0, 16)
        })

        val googleButton = Button(this).apply {
            text = "Продолжить с Google"
        }
        root.addView(googleButton)

        status = TextView(this).apply {
            textSize = 15f
            setPadding(0, 32, 0, 0)
        }
        root.addView(status)

        setContentView(root)

        sendCodeButton.setOnClickListener {
            val phone = phoneInput.text.toString().trim()
            if (phone.isBlank()) {
                status.text = "Введите номер телефона."
                return@setOnClickListener
            }
            lifecycleScope.launch {
                setBusy("Отправляем SMS…")
                runCatching {
                    api.requestPhoneCode(phone)
                }.onSuccess {
                    status.text = "Код отправлен. Введите 6 цифр из SMS."
                    codeInput.visibility = View.VISIBLE
                    verifyButton.visibility = View.VISIBLE
                    codeInput.requestFocus()
                }.onFailure {
                    status.text = "Ошибка отправки: ${it.message}"
                }
            }
        }

        verifyButton.setOnClickListener {
            val phone = phoneInput.text.toString().trim()
            val code = codeInput.text.toString().trim()
            lifecycleScope.launch {
                setBusy("Проверяем код…")
                runCatching {
                    api.verifyPhoneCode(phone, code)
                }.onSuccess { userId ->
                    onAuthenticated(userId, "телефон")
                }.onFailure {
                    status.text = "Ошибка входа: ${it.message}"
                }
            }
        }

        googleButton.setOnClickListener {
            lifecycleScope.launch {
                setBusy("Открываем Google…")
                runCatching {
                    val nonce = api.requestOidcNonce("GOOGLE")
                    val idToken = googleIdToken(nonce)
                    api.oauth("GOOGLE", idToken, nonce)
                }.onSuccess { userId ->
                    onAuthenticated(userId, "Google")
                }.onFailure {
                    status.text = "Google пока не завершён: ${it.message}"
                }
            }
        }

        if (api.hasSession()) {
            lifecycleScope.launch {
                runCatching { api.listAuthMethods() }
                    .onSuccess {
                        status.text = "Сессия восстановлена."
                        registerPush()
                    }
                    .onFailure {
                        status.text = "Нужно войти снова."
                    }
            }
        }
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
        status.text = "Вход выполнен через $method. User ID: $userId"
        requestNotificationPermission()
        registerPush()
    }

    private fun registerPush() {
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { token ->
                lifecycleScope.launch {
                    runCatching {
                        api.registerPushToken(token)
                    }.onSuccess { deviceId ->
                        status.text = status.text.toString() +
                            "\nPush подключён. Device ID: $deviceId"
                    }.onFailure {
                        status.text = status.text.toString() +
                            "\nНе удалось зарегистрировать push: ${it.message}"
                    }
                }
            }
            .addOnFailureListener {
                status.text = status.text.toString() +
                    "\nНе удалось получить FCM token: ${it.message}"
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
        status.text = message
    }
}
