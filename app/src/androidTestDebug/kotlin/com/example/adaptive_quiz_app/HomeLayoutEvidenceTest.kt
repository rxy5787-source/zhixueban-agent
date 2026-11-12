package com.example.adaptive_quiz_app

import android.content.Intent
import android.content.ContextWrapper
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import android.graphics.Bitmap
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.graphics.layer.GraphicsLayer
import androidx.compose.ui.graphics.layer.drawLayer
import androidx.compose.ui.graphics.rememberGraphicsLayer
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.ViewCompositionStrategy
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.text.TextLayoutResult
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.adaptive_quiz_app.ui.home.HomeNavigation
import com.example.adaptive_quiz_app.ui.home.HomePageContents
import com.example.adaptive_quiz_app.ui.home.HomeScreen
import com.example.adaptive_quiz_app.ui.home.HomeStateMapper
import com.example.adaptive_quiz_app.ui.home.HomeUiState
import com.example.adaptive_quiz_app.learning.HomeSummaryReader
import com.example.adaptive_quiz_app.learning.LearningStore
import com.example.adaptive_quiz_app.ui.prototype.HomePrototypeActivity
import com.example.adaptive_quiz_app.ui.theme.ZhixueTheme
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Real-device checks. Font overrides are scoped to the debug Activity, never system settings. */
@RunWith(AndroidJUnit4::class)
class HomeLayoutEvidenceTest {
    @get:Rule
    val compose = createEmptyComposeRule()

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val evidenceDir get() = File(instrumentation.targetContext.cacheDir, "home-evidence").apply { mkdirs() }

    @Test
    fun normalFontHasNoClippedTextAndExportsCompleteHome() = verifyProfile(1f, "normal")

    @Test
    fun largeFontHasNoClippedTextAndExportsCompleteHome() = verifyProfile(1.3f, "large")

    @Test
    fun extraLargeFontHasNoClippedTextAndExportsCompleteHome() = verifyProfile(1.6f, "extra-large")

    private fun verifyProfile(fontScale: Float, profile: String) {
        val state = realHomeState(profile)
        val intent = Intent(instrumentation.targetContext, HomePrototypeActivity::class.java)
            .putExtra("home_font_scale", fontScale)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ActivityScenario.launch<HomePrototypeActivity>(intent).use { scenario ->
            compose.waitForIdle()
            scenario.onActivity { activity ->
                val host = activity.findViewById<ComposeView>(R.id.home_prototype_root)
                assertEquals("Activity-only font scale", fontScale, host.resources.configuration.fontScale, .001f)
                val metrics = host.resources.displayMetrics
                File(evidenceDir, "$profile-device.txt").writeText(
                    "fontScale=$fontScale\ndensity=${metrics.density}\nviewportWidthPx=${host.width}\n" +
                        "viewportWidthDp=${host.width / metrics.density}\n" +
                        "screen-*.png are unedited UiAutomation screenshots.\n" +
                        "full-native.png is one native Compose graphics layer of all content plus navigation; " +
                        "it is not a stitched screenshot and contains no system status-bar text.\n" +
                        "Display state comes from HomeSummaryReader and real LearningStore submissions in " +
                        "a separate test_home_layout database; the user's database is never opened.\n",
                )
                activity.setContentView(ComposeView(host.context).apply {
                    id = R.id.home_prototype_root
                    setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnDetachedFromWindowOrReleasedFromPool)
                    setContent {
                        ZhixueTheme {
                            HomeScreen(state, onStartLearning = {}, onFocusClick = {},
                                onDestinationClick = {}, onStudyAction = {})
                        }
                    }
                })
            }
            compose.waitForIdle()

            assertEquals("Measured Compose text uses the requested font scale", fontScale,
                compose.onNodeWithTag("home_greeting").fetchSemanticsNode().layoutInfo.density.fontScale, .001f)
            // Capture before assertions so a measurement failure still leaves visual evidence.
            saveScreen("$profile-screen-top.png")
            assertAllTextFits(diagnosticName = "$profile-text-layout.txt")
            val modules = listOf("home_greeting", "home_today_plan", "home_focus", "home_footprints")
                .map(::unclippedBounds)
            modules.zipWithNext().forEachIndexed { index, (upper, lower) ->
                assertTrue("Modules $index and ${index + 1} overlap at $fontScale", upper.bottom <= lower.top + 1f)
            }
            val navigationTop = unclippedBounds("home_navigation").top

            compose.onNodeWithTag("home_footprints").performScrollTo().assertIsDisplayed()
            compose.onNodeWithTag("home_content").performSemanticsAction(SemanticsActions.ScrollBy) { scrollBy ->
                scrollBy(0f, 10_000f)
            }
            compose.waitForIdle()
            assertTrue("Footprints must scroll clear of the fixed navigation",
                unclippedBounds("home_footprints").bottom <= unclippedBounds("home_navigation").top + 1f)
            assertEquals("Navigation must stay fixed while scrolling", navigationTop,
                unclippedBounds("home_navigation").top, 1f)
            saveScreen("$profile-screen-bottom.png")

            // Typography checks must never start real learning or mutate the user's data.
            listOf("home_start", "home_focus").forEach { action ->
                compose.onNodeWithTag(action).performScrollTo().assertIsDisplayed()
                assertMinimumTouchTarget(action)
            }
            compose.onNodeWithTag("home_nav_Report").assertDoesNotExist()
            listOf("Today", "Libraries", "Profile").forEach { destination ->
                compose.onNodeWithTag("home_nav_$destination").assertIsDisplayed()
                assertMinimumTouchTarget("home_nav_$destination")
            }
            compose.onNodeWithTag("home_nav_Today").assertIsDisplayed().performClick()
            compose.onNodeWithTag("home_nav_Today").assertIsSelected()
            compose.onNodeWithTag("home_today_plan").performScrollTo().performClick()
            compose.onNodeWithTag("home_study_details").assertIsDisplayed()
            // Use the sheet's accessibility action before scrolling its content. The default
            // half-height stop is intentional UI behavior, especially with enlarged text.
            val expandable = SemanticsMatcher.keyIsDefined(SemanticsActions.Expand)
            if (compose.onAllNodes(expandable).fetchSemanticsNodes().isNotEmpty()) {
                compose.onNode(expandable).performSemanticsAction(SemanticsActions.Expand) { expand -> expand() }
                compose.waitForIdle()
            }
            saveScreen("$profile-details.png")
            listOf("home_today_plans", "home_tasks", "home_due", "home_progress_details", "home_resume")
                .forEach { action ->
                    compose.onNodeWithTag(action).performScrollTo().assertIsDisplayed()
                    assertMinimumTouchTarget(action)
                    val node = compose.onNodeWithTag(action).fetchSemanticsNode()
                    assertEquals("$action must be fully visible after scrolling",
                        node.size.height.toFloat(), node.boundsInRoot.height, 1f)
                }
            saveScreen("$profile-details-bottom.png")
            assertAllTextFits(minimumTextNodes = 12, diagnosticName = "$profile-details-text-layout.txt")
            exportEntirePage(scenario, "$profile-full-native.png", fontScale, state)
        }
    }

    /** Exercise the production store and mapper, confined to a disposable database per profile. */
    private fun realHomeState(profile: String): HomeUiState {
        val target = instrumentation.targetContext
        val prefix = "test_home_layout_${profile}_"
        val database = "${prefix}zhixue_learning.db"
        target.deleteDatabase(database)
        val isolated = object : ContextWrapper(target) {
            override fun openOrCreateDatabase(
                name: String,
                mode: Int,
                factory: SQLiteDatabase.CursorFactory?,
                errorHandler: DatabaseErrorHandler?,
            ): SQLiteDatabase = super.openOrCreateDatabase(prefix + name, mode, factory, errorHandler)

            override fun getDatabasePath(name: String): File = super.getDatabasePath(prefix + name)
        }
        val store = LearningStore(isolated)
        try {
            store.seed()
            val library = store.one("SELECT id FROM library WHERE kind='question' ORDER BY id LIMIT 1")
                .getLong("id")
            val finished = store.start(library, "question", 3, "adaptive", 0)
            // Completing the existing flow produces real state changes and its four task stages.
            repeat(3) {
                val session = store.one("SELECT * FROM session WHERE id=?", finished.toString())
                val position = session.getInt("position")
                val item = store.one("SELECT * FROM item WHERE id=?",
                    JSONArray(session.getString("plan")).getLong(position).toString())
                store.submit(finished, position, item.getLong("id"), item.getString("prompt"),
                    item.getString("answer"), item.getString("answer"), true, 1, "question", 1200)
                store.advance(finished)
            }
            assertEquals(1, store.one("SELECT finished FROM session WHERE id=?", finished.toString()).getInt("finished"))
            val active = store.start(library, "question", 3, "adaptive", 0)
            val session = store.one("SELECT * FROM session WHERE id=?", active.toString())
            val item = store.one("SELECT * FROM item WHERE id=?",
                JSONArray(session.getString("plan")).getLong(0).toString())
            store.submit(active, 0, item.getLong("id"), item.getString("prompt"),
                item.getString("answer"), item.getString("answer"), true, 1, "question", 1500)
            store.advance(active)
            val now = System.currentTimeMillis()
            val due = store.count("SELECT COUNT(*) n FROM state WHERE seen>0 AND due_at<=?", now.toString()).toInt()
            // This fixture has only newly generated stage chains: concept is their sole eligible stage.
            val runnable = store.count("SELECT COUNT(*) n FROM task WHERE completed=0 AND stage='concept' AND due_at<=?",
                now.toString()).toInt()
            val snapshot = HomeSummaryReader.read(store, 6, now, due, runnable)
            assertEquals(4, snapshot.getInt("doneToday"))
            assertEquals(4, snapshot.getInt("tasks"))
            assertEquals(1, snapshot.getInt("resumeCount"))
            assertTrue("The home must use observed weak-point evidence", !snapshot.isNull("weak"))
            return HomeStateMapper.fromSnapshot(snapshot)
        } finally {
            store.close()
            target.deleteDatabase(database)
        }
    }

    private fun assertAllTextFits(minimumTextNodes: Int = 20, diagnosticName: String? = null) {
        val nodes = compose.onAllNodes(
            SemanticsMatcher.keyIsDefined(SemanticsActions.GetTextLayoutResult), useUnmergedTree = true,
        ).fetchSemanticsNodes()
        val diagnostics = StringBuilder("textNodes=${nodes.size}; minimumTextNodes=$minimumTextNodes\n")
        val failures = mutableListOf<String>()
        if (nodes.size < minimumTextNodes) failures += "Expected text nodes must be composed"
        compose.runOnIdle {
            nodes.forEachIndexed { index, node ->
                val text = node.config.getOrElse(SemanticsProperties.Text) { emptyList() }.joinToString()
                diagnostics.append("\n[$index] text=$text; nodeSize=${node.size}; positionInRoot=${node.positionInRoot}\n")
                if (text.contains("示例") || text.contains("预览")) failures += "Developer copy must not appear: $text"
                val layouts = mutableListOf<TextLayoutResult>()
                val measured = node.config[SemanticsActions.GetTextLayoutResult].action!!.invoke(layouts)
                if (!measured || layouts.isEmpty()) failures += "Text must expose its measured layout: $text"
                layouts.forEach { layout ->
                    val measurement = "size=${layout.size}; multiParagraph.width=${layout.multiParagraph.width}; " +
                        "multiParagraph.height=${layout.multiParagraph.height}; " +
                        "didOverflowWidth=${layout.didOverflowWidth}; didOverflowHeight=${layout.didOverflowHeight}; " +
                        "hasVisualOverflow=${layout.hasVisualOverflow}; lineCount=${layout.lineCount}; " +
                        "constraints=${layout.layoutInput.constraints}"
                    diagnostics.append(measurement).append('\n')
                    val lines = StringBuilder()
                    for (line in 0 until layout.lineCount) {
                        val lineInfo = "line[$line]: top=${layout.getLineTop(line)}; bottom=${layout.getLineBottom(line)}; " +
                            "left=${layout.getLineLeft(line)}; right=${layout.getLineRight(line)}; " +
                            "end=${layout.getLineEnd(line, visibleEnd = false)}; " +
                            "ellipsized=${layout.isLineEllipsized(line)}\n"
                        diagnostics.append(lineInfo)
                        lines.append(lineInfo)
                        if (layout.isLineEllipsized(line)) failures += "Text is ellipsized: $text; $measurement; $lineInfo"
                        // Compose 1.9 String Text semantics rebuilds a paragraph with the parent's
                        // previous maxWidth but retains the actual intrinsic layoutSize. Its
                        // hasVisualOverflow can therefore be true for fully visible text. Check
                        // the actual line bounds and retained text instead of paragraph width.
                        // One physical pixel permits the float-to-integer layout rounding only.
                        if (layout.getLineLeft(line) < -1f || layout.getLineRight(line) > layout.size.width + 1f ||
                            layout.getLineTop(line) < -1f || layout.getLineBottom(line) > layout.size.height + 1f) {
                            failures += "Text line exceeds its measured bounds: $text; $measurement; $lineInfo"
                        }
                    }
                    val finalEnd = if (layout.lineCount > 0) layout.getLineEnd(layout.lineCount - 1, visibleEnd = false) else 0
                    if (finalEnd != layout.layoutInput.text.length) {
                        failures += "Text is truncated: $text; finalEnd=$finalEnd; " +
                            "textLength=${layout.layoutInput.text.length}; $measurement; $lines"
                    }
                }
            }
        }
        diagnostics.append("\nfailures=${failures.size}\n").append(failures.joinToString("\n"))
        diagnosticName?.let { File(evidenceDir, it).writeText(diagnostics.toString()) }
        assertTrue(failures.firstOrNull().orEmpty(), failures.isEmpty())
    }

    private fun unclippedBounds(tag: String): Rect {
        val node = compose.onNodeWithTag(tag).fetchSemanticsNode()
        return Rect(node.positionInRoot.x, node.positionInRoot.y,
            node.positionInRoot.x + node.size.width, node.positionInRoot.y + node.size.height)
    }

    private fun assertMinimumTouchTarget(tag: String) {
        val node = compose.onNodeWithTag(tag).fetchSemanticsNode()
        val minPx = 48f * node.layoutInfo.density.density
        assertTrue("$tag width must remain at least 48dp", node.size.width + 1f >= minPx)
        assertTrue("$tag height must remain at least 48dp", node.size.height + 1f >= minPx)
    }

    private fun saveScreen(name: String) {
        compose.waitForIdle()
        val bitmap = instrumentation.uiAutomation.takeScreenshot()
        assertNotNull("Device screenshot is available", bitmap)
        savePng(bitmap!!, name)
        bitmap.recycle()
    }

    /**
     * Records the actual reusable composables in one unbounded-height native layer. The normal
     * screen remains a scrolling page with fixed tabs; only this test harness lays out the tabs
     * after all content to produce a complete, inspectable long image without stitching frames.
     */
    private fun exportEntirePage(
        scenario: ActivityScenario<HomePrototypeActivity>,
        name: String,
        fontScale: Float,
        state: HomeUiState,
    ) {
        val recorded = AtomicBoolean(false)
        val layerRef = AtomicReference<GraphicsLayer>()
        scenario.onActivity { activity ->
            val original = activity.findViewById<ComposeView>(R.id.home_prototype_root)
            activity.setContentView(ComposeView(original.context).apply {
                setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnViewTreeLifecycleDestroyed)
                setContent {
                    ZhixueTheme {
                        // Match Scaffold's default content color in this isolated rendering host.
                        CompositionLocalProvider(LocalContentColor provides MaterialTheme.colorScheme.onBackground) {
                            val layer = rememberGraphicsLayer()
                            val actualFontScale = LocalDensity.current.fontScale
                            SideEffect {
                                assertEquals("Long rendering preserves LocalDensity font scale", fontScale, actualFontScale, .001f)
                                layerRef.set(layer)
                            }
                            Column(Modifier.fillMaxWidth()
                                .wrapContentHeight(align = Alignment.Top, unbounded = true)
                                .drawWithContent {
                                    layer.record { this@drawWithContent.drawContent() }
                                    drawLayer(layer)
                                    recorded.set(true)
                                }
                                .background(MaterialTheme.colorScheme.background)) {
                                HomePageContents(state, onStartLearning = {}, onFocusClick = {})
                                HomeNavigation(onDestinationClick = {})
                            }
                        }
                    }
                }
            })
        }
        compose.waitUntil(timeoutMillis = 10_000) { recorded.get() && layerRef.get() != null }
        compose.waitForIdle()
        val image = runBlocking(Dispatchers.Main) { layerRef.get().toImageBitmap() }
        assertTrue("Full-page layer has a useful width", image.width > 0)
        assertTrue("Full-page layer contains all sections", image.height > image.width)
        savePng(image.asAndroidBitmap(), name)
    }

    private fun savePng(bitmap: Bitmap, name: String) {
        File(evidenceDir, name).outputStream().use { output ->
            assertTrue("PNG encoding succeeds", bitmap.compress(Bitmap.CompressFormat.PNG, 100, output))
        }
    }
}
