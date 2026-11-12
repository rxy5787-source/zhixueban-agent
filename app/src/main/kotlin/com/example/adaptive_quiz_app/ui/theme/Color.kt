package com.example.adaptive_quiz_app.ui.theme

import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.graphics.Color

/** Warm paper, white surfaces and one restrained green accent. No dynamic colors. */
object ZhixuePalette {
    val Paper = Color(0xFFF5F4EF)
    val White = Color(0xFFFFFFFF)
    val Ink = Color(0xFF262B28)
    val Muted = Color(0xFF686F68)
    val Green = Color(0xFF4D746A)
    val GreenSoft = Color(0xFFE7EEE8)
    val QuietSurface = Color(0xFFEDEDE6)
    val Line = Color(0xFFE3E5DE)
    val Outline = Color(0xFF939A92)
    val Error = Color(0xFF8C5149)
    val ErrorSoft = Color(0xFFF5E8E4)
}

val ZhixueLightColors = lightColorScheme(
    primary = ZhixuePalette.Green,
    onPrimary = ZhixuePalette.White,
    primaryContainer = ZhixuePalette.GreenSoft,
    onPrimaryContainer = ZhixuePalette.Ink,
    inversePrimary = ZhixuePalette.GreenSoft,
    secondary = ZhixuePalette.Muted,
    onSecondary = ZhixuePalette.White,
    secondaryContainer = ZhixuePalette.QuietSurface,
    onSecondaryContainer = ZhixuePalette.Ink,
    tertiary = ZhixuePalette.Green,
    onTertiary = ZhixuePalette.White,
    tertiaryContainer = ZhixuePalette.GreenSoft,
    onTertiaryContainer = ZhixuePalette.Ink,
    background = ZhixuePalette.Paper,
    onBackground = ZhixuePalette.Ink,
    surface = ZhixuePalette.White,
    onSurface = ZhixuePalette.Ink,
    surfaceVariant = ZhixuePalette.QuietSurface,
    onSurfaceVariant = ZhixuePalette.Muted,
    surfaceTint = ZhixuePalette.Green,
    inverseSurface = ZhixuePalette.Ink,
    inverseOnSurface = ZhixuePalette.Paper,
    surfaceBright = ZhixuePalette.White,
    surfaceDim = ZhixuePalette.QuietSurface,
    surfaceContainerLowest = ZhixuePalette.White,
    surfaceContainerLow = ZhixuePalette.Paper,
    surfaceContainer = ZhixuePalette.Paper,
    surfaceContainerHigh = ZhixuePalette.QuietSurface,
    surfaceContainerHighest = ZhixuePalette.QuietSurface,
    outline = ZhixuePalette.Outline,
    outlineVariant = ZhixuePalette.Line,
    error = ZhixuePalette.Error,
    onError = ZhixuePalette.White,
    errorContainer = ZhixuePalette.ErrorSoft,
    onErrorContainer = ZhixuePalette.Error,
    scrim = ZhixuePalette.Ink,
)
