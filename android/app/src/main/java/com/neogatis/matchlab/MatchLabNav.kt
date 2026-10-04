package com.neogatis.matchlab

import android.content.Intent
import android.graphics.Typeface
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import androidx.appcompat.app.AppCompatActivity

object MatchLabNav {
    fun add(
        activity: AppCompatActivity,
        container: LinearLayout,
        current: String,
    ) {
        val nav = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            background = MatchLabStyle.rounded(
                MatchLabStyle.SURFACE,
                MatchLabStyle.dp(activity, 24),
                MatchLabStyle.BORDER,
                1,
            )
            setPadding(
                MatchLabStyle.dp(activity, 6),
                MatchLabStyle.dp(activity, 6),
                MatchLabStyle.dp(activity, 6),
                MatchLabStyle.dp(activity, 6),
            )
        }

        fun item(label: String, key: String, target: Class<out AppCompatActivity>) {
            val button = Button(activity).apply {
                text = label
                isAllCaps = false
                textSize = 12f
                typeface = Typeface.create(
                    "sans",
                    if (current == key) Typeface.BOLD else Typeface.NORMAL,
                )
                setTextColor(
                    MatchLabStyle.color(
                        if (current == key) MatchLabStyle.CORAL_DARK
                        else MatchLabStyle.MUTED
                    )
                )
                background = if (current == key) {
                    MatchLabStyle.rounded(MatchLabStyle.SURFACE_SOFT, 18)
                } else {
                    MatchLabStyle.rounded(MatchLabStyle.SURFACE, 18)
                }
                layoutParams = LinearLayout.LayoutParams(
                    0,
                    MatchLabStyle.dp(activity, 52),
                    1f,
                )
                setOnClickListener {
                    if (current == key) return@setOnClickListener
                    activity.startActivity(
                        Intent(activity, target).apply {
                            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                        }
                    )
                }
            }
            nav.addView(button)
        }

        item("⌂\nГлавная", "home", HomeActivity::class.java)
        item("♡\nСовпадения", "matches", MatchesActivity::class.java)
        item("◌\nЧаты", "chats", ChatsActivity::class.java)
        item("♙\nПрофиль", "profile", OnboardingActivity::class.java)

        container.addView(nav)
        MatchLabStyle.withMargins(nav, top = 22, bottom = 8)
    }
}
