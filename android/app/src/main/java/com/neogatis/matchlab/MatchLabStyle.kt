package com.neogatis.matchlab

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.StateListDrawable
import android.text.Spannable
import android.text.SpannableString
import android.text.style.ForegroundColorSpan
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.Spinner
import android.widget.TextView

object MatchLabStyle {
    const val BG = "#FFF9F6"
    const val SURFACE = "#FFFFFF"
    const val SURFACE_SOFT = "#FFF1EF"
    const val NAVY = "#151C35"
    const val CORAL = "#FF5D6C"
    const val CORAL_DARK = "#E94B65"
    const val MUTED = "#777985"
    const val BORDER = "#F1D9D5"
    const val SUCCESS = "#2FA97C"

    fun color(hex: String): Int = Color.parseColor(hex)

    fun dp(context: Context, value: Int): Int =
        (value * context.resources.displayMetrics.density).toInt()

    fun rounded(
        fill: String,
        radius: Int,
        stroke: String? = null,
        strokeWidth: Int = 1,
    ): GradientDrawable = GradientDrawable().apply {
        setColor(color(fill))
        cornerRadius = radius.toFloat()
        if (stroke != null) setStroke(strokeWidth, color(stroke))
    }

    fun primaryBackground(): GradientDrawable = GradientDrawable(
        GradientDrawable.Orientation.LEFT_RIGHT,
        intArrayOf(color(CORAL), color(CORAL_DARK))
    ).apply {
        cornerRadius = 28f
    }

    fun card(view: View) {
        view.background = rounded(SURFACE, 28, BORDER, 1)
        view.elevation = dp(view.context, 2).toFloat()
    }

    fun primaryButton(button: Button) {
        button.isAllCaps = false
        button.textSize = 16f
        button.setTextColor(Color.WHITE)
        button.typeface = Typeface.create("sans", Typeface.BOLD)
        button.background = primaryBackground()
        button.minHeight = dp(button.context, 56)
        button.setPadding(
            dp(button.context, 18),
            dp(button.context, 12),
            dp(button.context, 18),
            dp(button.context, 12),
        )
    }

    fun secondaryButton(button: Button) {
        button.isAllCaps = false
        button.textSize = 16f
        button.setTextColor(color(NAVY))
        button.typeface = Typeface.create("sans", Typeface.BOLD)
        button.background = rounded(SURFACE, 28, BORDER, 1)
        button.minHeight = dp(button.context, 54)
        button.setPadding(
            dp(button.context, 18),
            dp(button.context, 12),
            dp(button.context, 18),
            dp(button.context, 12),
        )
    }

    fun input(editText: EditText) {
        editText.textSize = 16f
        editText.setTextColor(color(NAVY))
        editText.setHintTextColor(color(MUTED))
        editText.background = rounded(SURFACE, 18, BORDER, 1)
        editText.setPadding(
            dp(editText.context, 16),
            dp(editText.context, 15),
            dp(editText.context, 16),
            dp(editText.context, 15),
        )
        editText.minHeight = dp(editText.context, 56)
    }

    fun spinner(spinner: Spinner) {
        spinner.background = rounded(SURFACE, 18, BORDER, 1)
        spinner.setPadding(
            dp(spinner.context, 14),
            dp(spinner.context, 10),
            dp(spinner.context, 14),
            dp(spinner.context, 10),
        )
        spinner.minimumHeight = dp(spinner.context, 54)
        spinner.elevation = dp(spinner.context, 1).toFloat()
    }

    fun title(textView: TextView) {
        textView.setTextColor(color(NAVY))
        textView.textSize = 29f
        textView.typeface = Typeface.create("serif", Typeface.BOLD)
    }

    fun subtitle(textView: TextView) {
        textView.setTextColor(color(MUTED))
        textView.textSize = 15f
    }

    fun label(textView: TextView) {
        textView.setTextColor(color(NAVY))
        textView.textSize = 14f
        textView.typeface = Typeface.create("sans", Typeface.BOLD)
    }

    fun status(textView: TextView) {
        textView.setTextColor(color(MUTED))
        textView.textSize = 14f
        textView.background = rounded(SURFACE_SOFT, 16)
        textView.setPadding(
            dp(textView.context, 14),
            dp(textView.context, 12),
            dp(textView.context, 14),
            dp(textView.context, 12),
        )
    }

    fun progress(progressBar: ProgressBar) {
        progressBar.progressTintList = ColorStateList.valueOf(color(CORAL))
        progressBar.progressBackgroundTintList = ColorStateList.valueOf(color(BORDER))
    }

    fun radioOption(radioButton: RadioButton) {
        val checked = rounded(SURFACE_SOFT, 18, CORAL, 2)
        val normal = rounded(SURFACE, 18, BORDER, 1)
        val states = StateListDrawable().apply {
            addState(intArrayOf(android.R.attr.state_checked), checked)
            addState(intArrayOf(), normal)
        }
        radioButton.background = states
        radioButton.buttonTintList = ColorStateList(
            arrayOf(
                intArrayOf(android.R.attr.state_checked),
                intArrayOf()
            ),
            intArrayOf(color(CORAL), color(BORDER))
        )
        radioButton.setTextColor(color(NAVY))
        radioButton.setPadding(
            dp(radioButton.context, 14),
            dp(radioButton.context, 12),
            dp(radioButton.context, 14),
            dp(radioButton.context, 12),
        )
        radioButton.minHeight = dp(radioButton.context, 54)
    }

    fun brandText(): SpannableString {
        val value = SpannableString("MatchLab")
        value.setSpan(
            ForegroundColorSpan(color(NAVY)),
            0,
            5,
            Spannable.SPAN_EXCLUSIVE_EXCLUSIVE,
        )
        value.setSpan(
            ForegroundColorSpan(color(CORAL_DARK)),
            5,
            8,
            Spannable.SPAN_EXCLUSIVE_EXCLUSIVE,
        )
        return value
    }

    fun withMargins(view: View, top: Int = 12, bottom: Int = 0) {
        val params = view.layoutParams
        if (params is ViewGroup.MarginLayoutParams) {
            params.topMargin = dp(view.context, top)
            params.bottomMargin = dp(view.context, bottom)
            view.layoutParams = params
        }
    }
}
