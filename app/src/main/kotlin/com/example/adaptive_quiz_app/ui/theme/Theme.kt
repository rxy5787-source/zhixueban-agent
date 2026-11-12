package com.example.adaptive_quiz_app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.ReadOnlyComposable

@Composable
fun ZhixueTheme(content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalZhixueSpacing provides ZhixueSpacing()) {
        MaterialTheme(
            colorScheme = ZhixueLightColors,
            typography = zhixueTypography(),
            shapes = ZhixueShapes,
            content = content,
        )
    }
}

object ZhixueTheme {
    val spacing: ZhixueSpacing
        @Composable @ReadOnlyComposable get() = LocalZhixueSpacing.current
}
