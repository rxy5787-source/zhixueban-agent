package com.example.adaptive_quiz_app.ui.theme

import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

@Immutable
data class ZhixueSpacing(
    val xxs: Dp = 4.dp,
    val xs: Dp = 8.dp,
    val sm: Dp = 12.dp,
    val md: Dp = 16.dp,
    val lg: Dp = 20.dp,
    val xl: Dp = 24.dp,
    val xxl: Dp = 32.dp,
    val section: Dp = 40.dp,
    val touchTarget: Dp = 48.dp,
    val buttonMinHeight: Dp = 48.dp,
)

internal val LocalZhixueSpacing = staticCompositionLocalOf { ZhixueSpacing() }
