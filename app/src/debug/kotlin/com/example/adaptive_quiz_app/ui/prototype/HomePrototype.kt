package com.example.adaptive_quiz_app.ui.prototype

import androidx.compose.runtime.Composable
import androidx.compose.ui.tooling.preview.Preview
import com.example.adaptive_quiz_app.ui.home.HomeDestination
import com.example.adaptive_quiz_app.ui.home.HomeScreen
import com.example.adaptive_quiz_app.ui.home.HomeUiState
import com.example.adaptive_quiz_app.ui.home.LearningDay
import com.example.adaptive_quiz_app.ui.theme.ZhixueTheme

// All mock learning content stays in the debug source set, outside the reusable home screen.
internal val PreviewHomeState = HomeUiState(
    dateLabel = "10 月 17 日 · 星期六",
    greeting = "今天，学一点就好。",
    encouragement = "留一小段时间，给自己。",
    planTitle = "复习，再学一点。",
    planSummary = "SQL 5 题 · 英语 6 词",
    durationLabel = "约 12 分钟",
    focusTitle = "SQL · 聚合与分组",
    focusNote = "WHERE 与 HAVING 的区别",
    footprintSummary = "这周，有 3 天留给了学习。",
    week = listOf(
        LearningDay("一", true), LearningDay("二", false), LearningDay("三", true),
        LearningDay("四", false), LearningDay("五", true), LearningDay("六", false, true),
        LearningDay("日", false),
    ),
)

@Composable
internal fun HomePrototype(onAction: (String) -> Unit) {
    HomeScreen(
        state = PreviewHomeState,
        onStartLearning = { onAction("learn") },
        onFocusClick = { onAction("report") },
        onDestinationClick = { destination ->
            when (destination) {
                HomeDestination.Today -> Unit
                HomeDestination.Libraries -> onAction("libraries")
                HomeDestination.Profile -> onAction("profile")
            }
        },
    )
}

@Preview(name = "首页 · 标准字号", widthDp = 390, heightDp = 900, showBackground = true)
@Preview(name = "首页 · 大字号", widthDp = 320, heightDp = 704, fontScale = 1.3f, showBackground = true)
@Composable
private fun HomePrototypePreview() {
    ZhixueTheme { HomePrototype(onAction = {}) }
}
