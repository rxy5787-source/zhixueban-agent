package com.example.adaptive_quiz_app.ui.home

import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

/** Maps a read-only snapshot to display text; querying and learning decisions stay in Java. */
object HomeStateMapper {
    @JvmStatic
    fun fromSnapshot(snapshot: JSONObject): HomeUiState {
        val now = snapshot.optLong("now", System.currentTimeMillis())
        val target = snapshot.nonNegative("target")
        val completed = snapshot.nonNegative("completed").coerceAtMost(target)
        val tasks = snapshot.nonNegative("tasks")
        val runnable = snapshot.nonNegative("runnableTasks")
        val due = snapshot.nonNegative("due")
        val resumeCount = snapshot.nonNegative("resumeCount")
        val active = snapshot.optJSONObject("activeSession")
        val weak = snapshot.optJSONObject("weak")?.takeIf { it.optInt("seen") > 0 }
        val activeName = active?.optString("name").orEmpty()
        val week = days(snapshot, now)
        val studiedDays = snapshot.optInt("studiedDays", week.count { it.studied }).coerceIn(0, 7)
        val planTitle = when {
            active != null -> "接着上次，慢慢学。"
            runnable > 0 -> "巩固，再学一点。"
            due > 0 -> "复习，再学一点。"
            target > 0 && completed >= target -> "今天，已经有收获。"
            target > 0 -> "今天，从一点开始。"
            else -> "先添一点学习内容。"
        }
        return HomeUiState(
            dateLabel = dateLabel(now),
            greeting = "今天，学一点就好。",
            encouragement = "留一小段时间，给自己。",
            planTitle = planTitle,
            planSummary = "$tasks 项巩固任务 · $due 项待复习",
            durationLabel = "",
            focusTitle = weak?.optString("name")?.takeIf { it.isNotBlank() } ?: "先了解你的学习情况",
            focusNote = if (weak != null) {
                val mastery = (weak.optDouble("mastery", 0.0).coerceIn(0.0, 1.0) * 100).roundToInt()
                "掌握估计 $mastery% · ${weak.optInt("seen")} 次证据"
            } else "练习后，再一起找到需要加强的内容。",
            footprintSummary = if (studiedDays == 0) "这周的足迹，从今天开始。"
                else "这周，有 $studiedDays 天留给了学习。",
            week = week,
            progressLabel = "$completed / $target",
            studyDetails = HomeStudyDetails(
                target = target,
                completed = completed,
                doneToday = snapshot.nonNegative("doneToday"),
                tasks = tasks,
                runnableTasks = runnable,
                due = due,
                resumeCount = resumeCount,
                activeSessionName = activeName,
            ),
        )
    }

    @JvmStatic
    fun loading(): HomeUiState = HomeUiState(
        dateLabel = dateLabel(System.currentTimeMillis()),
        greeting = "今天，学一点就好。",
        encouragement = "留一小段时间，给自己。",
        planTitle = "正在整理今日学习。",
        planSummary = "读取你的学习记录…",
        durationLabel = "—",
        focusTitle = "正在读取学习依据",
        focusNote = "稍候就好。",
        footprintSummary = "正在整理这周的足迹。",
        week = days(JSONObject(), System.currentTimeMillis()),
        isLoading = true,
    )

    private fun dateLabel(now: Long): String =
        SimpleDateFormat("M 月 d 日 · EEEE", Locale.CHINA).format(Date(now))

    private fun days(snapshot: JSONObject, now: Long): List<LearningDay> {
        val labels = listOf("一", "二", "三", "四", "五", "六", "日")
        val today = (Calendar.getInstance().apply { timeInMillis = now }
            .get(Calendar.DAY_OF_WEEK) + 5) % 7
        val days = snapshot.optJSONArray("days")
        return labels.mapIndexed { index, label ->
            val day = days?.optJSONObject(index)
            LearningDay(
                label = day?.optString("label")?.takeIf { it.isNotBlank() } ?: label,
                studied = day?.optBoolean("studied") ?: false,
                isToday = day?.optBoolean("isToday") ?: (index == today),
            )
        }
    }

    private fun JSONObject.nonNegative(key: String): Long = optLong(key).coerceAtLeast(0)
}
