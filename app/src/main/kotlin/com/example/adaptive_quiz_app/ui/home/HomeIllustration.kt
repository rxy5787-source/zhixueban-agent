package com.example.adaptive_quiz_app.ui.home

import androidx.compose.foundation.Canvas
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale

/** Original small still life, drawn locally: an open book, tea and a leafy sprig. */
@Composable
internal fun HomeIllustration(modifier: Modifier = Modifier) {
    val colors = MaterialTheme.colorScheme
    Canvas(modifier) {
        scale(size.width / 160f, size.height / 108f, pivot = Offset.Zero) {
            val ink = colors.onSurface.copy(alpha = .72f)
            val fine = Stroke(width = 1.4f, cap = StrokeCap.Round)
            drawCircle(colors.surfaceContainerHighest, 38f, Offset(111f, 53f))
            drawLine(colors.outlineVariant, Offset(7f, 96f), Offset(153f, 96f), 1.2f, StrokeCap.Round)
            val book = Path().apply {
                moveTo(10f, 66f); cubicTo(24f, 57f, 40f, 56f, 54f, 64f)
                cubicTo(68f, 55f, 82f, 56f, 94f, 61f)
                lineTo(92f, 91f); cubicTo(78f, 86f, 66f, 86f, 53f, 94f)
                cubicTo(38f, 88f, 23f, 89f, 12f, 94f); close()
            }
            drawPath(book, colors.surface)
            drawPath(book, ink, style = fine)
            drawLine(ink, Offset(54f, 65f), Offset(53f, 93f), 1.2f)
            for (dy in listOf(0f, 6f)) {
                drawPath(Path().apply {
                    moveTo(21f, 72f + dy); quadraticTo(34f, 67f + dy, 44f, 72f + dy)
                    moveTo(64f, 71f + dy); quadraticTo(74f, 66f + dy, 84f, 69f + dy)
                }, colors.outline, style = Stroke(1f))
            }
            drawRoundRect(colors.surface, Offset(108f, 65f), Size(25f, 24f), CornerRadius(5f))
            drawRoundRect(ink, Offset(108f, 65f), Size(25f, 24f), CornerRadius(5f), style = fine)
            drawPath(Path().apply {
                moveTo(134f, 69f); cubicTo(149f, 64f, 149f, 85f, 134f, 81f)
            }, ink, style = fine)
            drawLine(ink, Offset(103f, 93f), Offset(141f, 93f), 1.2f, StrokeCap.Round)
            drawPath(Path().apply {
                moveTo(113f, 57f); cubicTo(107f, 51f, 119f, 47f, 115f, 40f)
                moveTo(124f, 57f); cubicTo(119f, 52f, 130f, 48f, 126f, 43f)
            }, colors.outline, style = fine)
            drawPath(Path().apply {
                moveTo(108f, 38f); cubicTo(103f, 27f, 111f, 17f, 121f, 9f)
            }, colors.primary, style = fine)
            drawPath(Path().apply {
                moveTo(108f, 28f); cubicTo(91f, 28f, 92f, 13f, 98f, 15f)
                cubicTo(107f, 15f, 111f, 22f, 108f, 28f); close()
                moveTo(114f, 18f); cubicTo(114f, 5f, 132f, 4f, 135f, 8f)
                cubicTo(131f, 18f, 120f, 22f, 114f, 18f); close()
            }, colors.primary.copy(alpha = .75f))
        }
    }
}
