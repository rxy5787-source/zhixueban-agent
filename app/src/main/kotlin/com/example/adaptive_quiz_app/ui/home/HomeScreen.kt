package com.example.adaptive_quiz_app.ui.home

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineBreak
import androidx.compose.ui.unit.dp
import com.example.adaptive_quiz_app.R
import com.example.adaptive_quiz_app.ui.components.ZhixueCard
import com.example.adaptive_quiz_app.ui.components.ZhixuePrimaryButton
import com.example.adaptive_quiz_app.ui.theme.ZhixueTheme

/** Stateless home UI. All actions are supplied by its host, never performed while rendering. */
@Composable
fun HomeScreen(
    state: HomeUiState,
    onStartLearning: () -> Unit,
    onFocusClick: () -> Unit,
    onDestinationClick: (HomeDestination) -> Unit,
    onStudyAction: (String) -> Unit = {},
) {
    var showStudyDetails by rememberSaveable { mutableStateOf(false) }
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        contentWindowInsets = WindowInsets.safeDrawing,
        bottomBar = { HomeNavigation { if (!state.isLoading) onDestinationClick(it) } },
    ) { insets ->
        Column(Modifier.fillMaxSize().padding(insets)
            .verticalScroll(rememberScrollState()).testTag("home_content")) {
            HomePageContents(state, onStartLearning, onFocusClick,
                onStudyDetails = { showStudyDetails = true })
        }
    }
    if (showStudyDetails && state.studyDetails != null && !state.isLoading) {
        StudyDetailsSheet(state.studyDetails,
            onDismiss = { showStudyDetails = false },
            onAction = { action ->
                showStudyDetails = false
                onStudyAction(action)
            })
    }
}

@Composable
internal fun HomePageContents(
    state: HomeUiState,
    onStartLearning: () -> Unit,
    onFocusClick: () -> Unit,
    modifier: Modifier = Modifier,
    onStudyDetails: () -> Unit = {},
) {
    val spacing = ZhixueTheme.spacing
    BoxWithConstraints(modifier.fillMaxWidth()) {
        val gutter = if (maxWidth < 360.dp) spacing.lg else spacing.xl
        Column(Modifier.fillMaxWidth().padding(horizontal = gutter)
            .padding(top = spacing.sm, bottom = spacing.xxl)) {
            HomeGreeting(state)
            Spacer(Modifier.height(spacing.xxl))
            TodayPlan(state, onStartLearning, onStudyDetails)
            Spacer(Modifier.height(spacing.section))
            Text(stringResource(R.string.home_focus_title), style = MaterialTheme.typography.titleSmall)
            Spacer(Modifier.height(spacing.sm))
            Row(Modifier.fillMaxWidth().testTag("home_focus")
                .clip(MaterialTheme.shapes.small)
                .clickable(enabled = !state.isLoading, role = Role.Button, onClick = onFocusClick)
                .heightIn(min = spacing.touchTarget).padding(vertical = spacing.xs),
                verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(spacing.xxs)) {
                    Text(state.focusTitle, style = MaterialTheme.typography.bodyMedium)
                    Text(state.focusNote, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall)
                }
                Chevron(Modifier.padding(start = spacing.xs).size(20.dp))
            }
            Spacer(Modifier.height(spacing.section))
            LearningFootprints(state)
        }
    }
}

@Composable
private fun HomeGreeting(state: HomeUiState) {
    val spacing = ZhixueTheme.spacing
    Text(stringResource(R.string.home_brand), style = MaterialTheme.typography.titleSmall)
    Row(Modifier.fillMaxWidth().padding(top = spacing.sm, bottom = spacing.md),
        verticalAlignment = Alignment.Bottom) {
        Text(state.dateLabel, style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f).padding(bottom = spacing.xs))
        HomeIllustration(Modifier.size(112.dp, 76.dp))
    }
    Text(state.greeting, modifier = Modifier.testTag("home_greeting"),
        style = MaterialTheme.typography.headlineMedium.copy(lineBreak = LineBreak.Heading))
    Spacer(Modifier.height(spacing.xs))
    Text(state.encouragement, color = MaterialTheme.colorScheme.onSurfaceVariant,
        style = MaterialTheme.typography.bodyMedium)
}

@Composable
private fun TodayPlan(state: HomeUiState, onStart: () -> Unit, onStudyDetails: () -> Unit) {
    val spacing = ZhixueTheme.spacing
    ZhixueCard(Modifier.fillMaxWidth().testTag("home_today_plan"),
        onClick = onStudyDetails.takeIf { state.studyDetails != null && !state.isLoading },
        contentPadding = PaddingValues(spacing.lg)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.home_today_plan), style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (state.studyDetails != null) {
                    Chevron(Modifier.padding(start = spacing.xxs).size(12.dp))
                }
            }
            Text(state.progressLabel ?: state.durationLabel, style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.testTag("home_progress").then(if (state.studyDetails != null) {
                    Modifier.semantics {
                        contentDescription = "今日已完成 ${state.studyDetails.completed} / ${state.studyDetails.target} 条"
                    }
                } else Modifier))
        }
        Spacer(Modifier.height(spacing.sm))
        Text(state.planTitle, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(spacing.xs))
        Text(state.planSummary, style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(spacing.md))
        ZhixuePrimaryButton(onStart, Modifier.testTag("home_start"), enabled = !state.isLoading) {
            Text(stringResource(R.string.home_start_learning))
            Chevron(Modifier.padding(start = spacing.xs).size(16.dp), MaterialTheme.colorScheme.onPrimary)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun StudyDetailsSheet(
    details: HomeStudyDetails,
    onDismiss: () -> Unit,
    onAction: (String) -> Unit,
) {
    val spacing = ZhixueTheme.spacing
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.onBackground,
        tonalElevation = 0.dp,
        shape = MaterialTheme.shapes.extraLarge,
    ) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())
            .testTag("home_study_details")
            .padding(horizontal = spacing.xl)
            .padding(bottom = spacing.xl)) {
            Text("今天的学习安排", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(spacing.xs))
            Text("今日已完成 ${details.completed} / ${details.target} 条 · 已作答 ${details.doneToday} 条",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(spacing.lg))
            StudyDetailAction("今日计划", "按知识库查看今天的计划", "home_today_plans") { onAction("plans") }
            StudyDetailAction("巩固任务", "${details.tasks} 项未完成 · ${details.runnableTasks} 项现在可练", "home_tasks") { onAction("tasks") }
            StudyDetailAction("到期复习", "${details.due} 项到期 · 按原有间隔安排", "home_due") { onAction("review") }
            StudyDetailAction("学习进度", "查看真实作答、学习覆盖与记录", "home_progress_details") { onAction("progress") }
            val resumeNote = buildString {
                append("${details.resumeCount} 轮未完成")
                if (details.activeSessionName.isNotBlank()) append(" · ${details.activeSessionName}")
            }
            StudyDetailAction("未完成练习", resumeNote, "home_resume") { onAction("resume") }
        }
    }
}

@Composable
private fun StudyDetailAction(title: String, note: String, tag: String, onClick: () -> Unit) {
    val spacing = ZhixueTheme.spacing
    Row(Modifier.fillMaxWidth().testTag(tag).clip(MaterialTheme.shapes.small)
        .clickable(role = Role.Button, onClick = onClick)
        .heightIn(min = spacing.touchTarget)
        .padding(vertical = spacing.sm),
        verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(spacing.xxs)) {
            Text(title, style = MaterialTheme.typography.bodyMedium)
            Text(note, style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Chevron(Modifier.padding(start = spacing.xs).size(20.dp))
    }
}

@Composable
private fun LearningFootprints(state: HomeUiState) {
    val spacing = ZhixueTheme.spacing
    val colors = MaterialTheme.colorScheme
    Column(Modifier.fillMaxWidth().testTag("home_footprints")) {
        Text(stringResource(R.string.home_footprint_title), style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(spacing.xs))
        Text(state.footprintSummary, style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
        Spacer(Modifier.height(spacing.lg))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            state.week.forEach { day ->
                val description = stringResource(R.string.home_day_accessibility, day.label,
                    stringResource(if (day.studied) R.string.home_day_studied else R.string.home_day_rest),
                    if (day.isToday) stringResource(R.string.home_day_current) else "")
                Column(horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.semantics(mergeDescendants = true) { contentDescription = description }) {
                    Text(day.label, style = MaterialTheme.typography.labelSmall,
                        fontWeight = if (day.isToday) FontWeight.Medium else FontWeight.Normal,
                        color = colors.onSurfaceVariant)
                    Spacer(Modifier.height(spacing.sm))
                    Box(Modifier.size(10.dp)
                        .background(if (day.studied) colors.primary else colors.outlineVariant, CircleShape)
                        .then(if (day.isToday) Modifier.border(1.dp, colors.primary, CircleShape) else Modifier))
                }
            }
        }
    }
}

@Composable
internal fun HomeNavigation(onDestinationClick: (HomeDestination) -> Unit) {
    val colors = MaterialTheme.colorScheme
    val spacing = ZhixueTheme.spacing
    Surface(color = colors.surface, tonalElevation = 0.dp, shadowElevation = 0.dp) {
        Row(Modifier.fillMaxWidth().testTag("home_navigation").windowInsetsPadding(WindowInsets.navigationBars)
            .padding(horizontal = spacing.xs).selectableGroup()) {
            HomeDestination.entries.forEach { destination ->
                val selected = destination == HomeDestination.Today
                val title = stringResource(when (destination) {
                    HomeDestination.Today -> R.string.home_today
                    HomeDestination.Libraries -> R.string.home_libraries
                    HomeDestination.Profile -> R.string.home_profile
                })
                val color = if (selected) colors.primary else colors.onSurfaceVariant
                Column(Modifier.weight(1f).testTag("home_nav_${destination.name}")
                    .selectable(selected = selected, role = Role.Tab,
                        onClick = { onDestinationClick(destination) })
                    .heightIn(min = 64.dp).padding(horizontal = spacing.xxs, vertical = spacing.xs),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center) {
                    DestinationIcon(destination, color)
                    Spacer(Modifier.height(spacing.xxs))
                    Text(title, style = MaterialTheme.typography.labelSmall, color = color)
                }
            }
        }
    }
}

@Composable
private fun Chevron(modifier: Modifier, color: Color = MaterialTheme.colorScheme.onSurfaceVariant) {
    Canvas(modifier) {
        drawPath(Path().apply {
            moveTo(size.width * .35f, size.height * .23f)
            lineTo(size.width * .64f, size.height * .5f)
            lineTo(size.width * .35f, size.height * .77f)
        }, color, style = Stroke(1.5.dp.toPx(), cap = StrokeCap.Round))
    }
}

@Composable
private fun DestinationIcon(destination: HomeDestination, color: Color) {
    Canvas(Modifier.size(22.dp)) {
        scale(size.width / 24f, size.height / 24f, pivot = Offset.Zero) {
            val path = Path()
            when (destination) {
                HomeDestination.Today -> {
                    path.moveTo(3f, 11f); path.lineTo(12f, 3f); path.lineTo(21f, 11f)
                    path.moveTo(5f, 10f); path.lineTo(5f, 21f); path.lineTo(10f, 21f)
                    path.lineTo(10f, 15f); path.lineTo(14f, 15f); path.lineTo(14f, 21f)
                    path.lineTo(19f, 21f); path.lineTo(19f, 10f)
                }
                HomeDestination.Libraries -> {
                    path.moveTo(3f, 5f); path.cubicTo(6f, 3f, 9f, 3f, 12f, 5f)
                    path.cubicTo(15f, 3f, 18f, 3f, 21f, 5f); path.lineTo(21f, 20f)
                    path.cubicTo(18f, 18f, 15f, 18f, 12f, 20f)
                    path.cubicTo(9f, 18f, 6f, 18f, 3f, 20f); path.close()
                    path.moveTo(12f, 5f); path.lineTo(12f, 20f)
                }
                HomeDestination.Profile -> {
                    drawCircle(color, 3.5f, Offset(12f, 7f), style = Stroke(1.6f))
                    path.moveTo(4f, 21f); path.cubicTo(4f, 12f, 20f, 12f, 20f, 21f)
                }
            }
            drawPath(path, color, style = Stroke(1.6f, cap = StrokeCap.Round))
        }
    }
}
