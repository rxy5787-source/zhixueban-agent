package com.example.adaptive_quiz_app.ui.home

import androidx.compose.runtime.Immutable

/** Presentation data only. This package does not open databases or run learning algorithms. */
@Immutable
data class HomeUiState(
    val dateLabel: String,
    val greeting: String,
    val encouragement: String,
    val planTitle: String,
    val planSummary: String,
    val durationLabel: String,
    val focusTitle: String,
    val focusNote: String,
    val footprintSummary: String,
    val week: List<LearningDay>,
    val progressLabel: String? = null,
    val studyDetails: HomeStudyDetails? = null,
    val isLoading: Boolean = false,
)

/** Read-only counts prepared by the existing Java learning flow. */
@Immutable
data class HomeStudyDetails(
    val target: Long,
    val completed: Long,
    val doneToday: Long,
    val tasks: Long,
    val runnableTasks: Long,
    val due: Long,
    val resumeCount: Long,
    val activeSessionName: String = "",
)

@Immutable
data class LearningDay(val label: String, val studied: Boolean, val isToday: Boolean = false)

enum class HomeDestination { Today, Libraries, Profile }
