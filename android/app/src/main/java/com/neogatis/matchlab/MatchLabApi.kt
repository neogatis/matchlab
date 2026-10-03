package com.neogatis.matchlab

import android.content.Context
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class PersistentCookieJar(context: Context) : CookieJar {
    private val prefs = context.getSharedPreferences("matchlab_cookies", Context.MODE_PRIVATE)
    private val allowedNames = setOf("ml_session", "ml_csrf")

    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        val edit = prefs.edit()
        for (cookie in cookies) {
            if (cookie.name !in allowedNames) continue
            if (cookie.value == "deleted" || cookie.expiresAt <= System.currentTimeMillis()) {
                edit.remove(cookie.name)
            } else {
                edit.putString(cookie.name, cookie.value)
            }
        }
        edit.apply()
    }

    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        return allowedNames.mapNotNull { name ->
            val value = prefs.getString(name, null) ?: return@mapNotNull null
            Cookie.Builder()
                .name(name)
                .value(value)
                .domain(url.host)
                .path("/")
                .secure()
                .build()
        }
    }

    fun csrfToken(): String? = prefs.getString("ml_csrf", null)
    fun hasSession(): Boolean = !prefs.getString("ml_session", null).isNullOrBlank()

    fun clear() {
        prefs.edit().clear().apply()
    }
}

class MatchLabApi(context: Context) {
    private val baseUrl = BuildConfig.API_BASE_URL.trimEnd('/')
    private val cookieJar = PersistentCookieJar(context.applicationContext)

    private val client = OkHttpClient.Builder()
        .cookieJar(cookieJar)
        .addInterceptor { chain ->
            val original = chain.request()
            val builder = original.newBuilder()
            val unsafe = original.method !in setOf("GET", "HEAD", "OPTIONS")
            if (unsafe) {
                builder.header("Origin", baseUrl)
                cookieJar.csrfToken()?.let {
                    builder.header("X-CSRF-Token", it)
                }
            }
            chain.proceed(builder.build())
        }
        .build()

    fun hasSession(): Boolean = cookieJar.hasSession()

    suspend fun requestPhoneCode(phone: String) {
        post(
            "/api/v1/auth/phone/request",
            JSONObject().put("phone", phone),
        )
    }

    suspend fun verifyPhoneCode(phone: String, code: String): Long {
        val result = post(
            "/api/v1/auth/phone/verify",
            JSONObject()
                .put("phone", phone)
                .put("code", code),
        )
        return result.getLong("user_id")
    }

    suspend fun requestOidcNonce(provider: String): String {
        val result = post(
            "/api/v1/auth/oidc/nonce",
            JSONObject().put("provider", provider),
        )
        return result.getString("nonce")
    }

    suspend fun oauth(provider: String, idToken: String, nonce: String): Long {
        val result = post(
            "/api/v1/auth/oauth",
            JSONObject()
                .put("provider", provider)
                .put("id_token", idToken)
                .put("nonce", nonce),
        )
        return result.getLong("user_id")
    }

    suspend fun registerPushToken(token: String, locale: String = "ru-KZ"): Long {
        val result = post(
            "/api/v1/push/devices",
            JSONObject()
                .put("token", token)
                .put("locale", locale),
        )
        return result.getLong("id")
    }

    suspend fun listAuthMethods(): JSONObject = get("/api/v1/auth/methods")

    private suspend fun get(path: String): JSONObject = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url(baseUrl + path)
            .get()
            .build()
        client.newCall(request).execute().use { response ->
            val raw = response.body?.string().orEmpty()
            val json = if (raw.isBlank()) JSONObject() else JSONObject(raw)
            if (!response.isSuccessful) {
                throw IllegalStateException(
                    json.optString("error", "HTTP \${response.code}")
                )
            }
            json
        }
    }

    private suspend fun post(path: String, payload: JSONObject): JSONObject =
        withContext(Dispatchers.IO) {
            val body = payload.toString()
                .toRequestBody("application/json; charset=utf-8".toMediaType())
            val request = Request.Builder()
                .url(baseUrl + path)
                .post(body)
                .build()

            client.newCall(request).execute().use { response ->
                val raw = response.body?.string().orEmpty()
                val json = if (raw.isBlank()) JSONObject() else JSONObject(raw)
                if (!response.isSuccessful) {
                    throw IllegalStateException(
                        json.optString("error", "HTTP \${response.code}")
                    )
                }
                json
            }
        }
}
