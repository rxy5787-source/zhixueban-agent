package com.example.adaptive_quiz_app.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.PlatformTextStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.example.adaptive_quiz_app.ui.TypeScale
import com.example.adaptive_quiz_app.ui.TypeScale.Role

/** Shared resource roles are authored in sp; LocalDensity applies system scaling exactly once. */
@Composable
fun zhixueTypography(): Typography {
    val resources = LocalContext.current.resources
    return remember(resources) {
        fun style(role: Role) = TextStyle(
            fontFamily = FontFamily.SansSerif,
            fontWeight = if (role.medium) FontWeight.Medium else FontWeight.Normal,
            fontSize = TypeScale.authoredSp(resources, role.sizeResource).sp,
            lineHeight = TypeScale.authoredSp(resources, role.lineResource).sp,
            letterSpacing = 0.sp,
            platformStyle = PlatformTextStyle(includeFontPadding = false),
        )
        Typography(
            displayLarge = style(Role.DISPLAY_LARGE),
            displayMedium = style(Role.DISPLAY_MEDIUM),
            displaySmall = style(Role.DISPLAY_SMALL),
            headlineLarge = style(Role.HEADLINE_LARGE),
            headlineMedium = style(Role.HERO),
            headlineSmall = style(Role.PAGE),
            titleLarge = style(Role.PAGE),
            titleMedium = style(Role.SECTION),
            titleSmall = style(Role.BUTTON),
            bodyLarge = style(Role.READING),
            bodyMedium = style(Role.BODY),
            bodySmall = style(Role.SECONDARY),
            labelLarge = style(Role.BUTTON),
            labelMedium = style(Role.SECONDARY),
            labelSmall = style(Role.CAPTION),
        )
    }
}
