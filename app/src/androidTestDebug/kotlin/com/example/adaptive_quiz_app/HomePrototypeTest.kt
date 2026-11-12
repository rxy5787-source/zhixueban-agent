package com.example.adaptive_quiz_app

import android.content.Intent
import android.widget.RadioButton
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.assertion.ViewAssertions.doesNotExist
import androidx.test.espresso.matcher.ViewMatchers.isAssignableFrom
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withContentDescription
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.adaptive_quiz_app.learning.LearningStore
import org.hamcrest.Matchers.allOf
import org.hamcrest.Matchers.startsWith
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** The accepted Compose home is the real MainActivity; all evidence is written to a sandbox. */
@RunWith(AndroidJUnit4::class)
class HomePrototypeTest {
    @get:Rule
    val compose = ComposeTestDriver()
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()

    @Test
    fun onlyLauncherAndAllNativeTodayTabsReturnToTheSameComposeHome() {
        val target = instrumentation.targetContext
        val launcher = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
            .setPackage(target.packageName)
        @Suppress("DEPRECATION")
        val launchers = target.packageManager.queryIntentActivities(launcher, 0)
        assertEquals("The installed app must expose exactly one home entry", 1, launchers.size)
        assertEquals(LoginActivity::class.java.name, launchers.single().activityInfo.name)
        MainBridgeSandbox().use { sandbox ->
            ActivityScenario.launch(MainActivity::class.java).use {
                val original = sandbox.awaitMainScreen("home")
                assertHome()
                listOf(
                    Triple("Libraries", "把知识，收进自己的书架。", 1),
                    Triple("Profile", "我的学习空间", 3),
                ).forEach { (destination, title, expectedTab) ->
                    compose.clickTag("home_nav_$destination")
                    onView(withText(title)).check(matches(isDisplayed()))
                    instrumentation.runOnMainSync {
                        assertEquals(expectedTab, sandbox.readField(original, "tab"))
                    }
                    onView(withContentDescription("今日")).perform(click())
                    assertHome()
                    assertSame(original, sandbox.awaitMainScreen("home"))
                    compose.clickTag("home_nav_$destination")
                    onView(withText(title)).check(matches(isDisplayed()))
                    pressBack()
                    assertHome()
                }
                assertEquals("Tabs must share one MainActivity and one home", 1, sandbox.initializations)
                assertEquals(0L, sandbox.store(original).count("SELECT COUNT(*) n FROM attempt"))
                assertEquals(0L, sandbox.store(original).count("SELECT COUNT(*) n FROM session"))
            }
        }
    }

    @Test
    fun reportLivesUnderProfileAndReturnsThereAfterRecreation() {
        MainBridgeSandbox().use { sandbox ->
            ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                val home = sandbox.awaitMainScreen("home")
                compose.assertNoText("报告")
                compose.clickTag("home_nav_Profile")
                onView(withContentDescription("报告")).check(doesNotExist())
                onView(withContentDescription("我的，当前页面")).check(matches(isDisplayed()))
                onView(withText("学习报告  ›")).perform(scrollTo(), click())
                onView(withText("学习报告")).check(matches(isDisplayed()))
                onView(withContentDescription("返回")).check(matches(isDisplayed()))
                onView(withContentDescription("今日")).check(doesNotExist())
                instrumentation.runOnMainSync { assertEquals(3, sandbox.readField(home, "tab")) }
                scenario.recreate()
                sandbox.awaitMainScreen("report")
                onView(withText("学习报告")).check(matches(isDisplayed()))
                pressBack()
                onView(withText("我的学习空间")).check(matches(isDisplayed()))
                onView(withContentDescription("我的，当前页面")).check(matches(isDisplayed()))
                onView(withContentDescription("报告")).check(doesNotExist())
                val restored = sandbox.awaitMainScreen("home")
                assertEquals(0L, sandbox.store(restored).count("SELECT COUNT(*) n FROM attempt"))
            }
        }
    }

    @Test
    fun realAnswerProgressAndSessionSurviveSaveExitRecreationAndRelaunch() {
        MainBridgeSandbox().use { sandbox ->
            val first = ActivityScenario.launch(MainActivity::class.java)
            var sessionId = 0L
            var target = 0L
            var savedAttempt = ""
            var savedSchema = ""
            try {
                val home = sandbox.awaitMainScreen("home")
                val store = sandbox.store(home)
                target = dailyTarget(store)
                savedSchema = schema(store)
                assertEquals(4, store.readableDatabase.version)
                compose.assertText("home_progress", "0 / $target")
                compose.clickTag("home_start")
                val learning = sandbox.awaitMainScreen("practice")
                sessionId = sandbox.readField(learning, "sessionId") as Long
                answerCurrentQuestion(store, sessionId)
                val plan = store.one("SELECT plan FROM session WHERE id=?", "$sessionId").getString("plan")
                savedAttempt = store.one("SELECT * FROM attempt WHERE session_id=?", "$sessionId").toString()
                assertEquals(1L, store.count("SELECT COUNT(*) n FROM attempt"))
                assertTrue(store.count("SELECT COUNT(*) n FROM state_change") > 0)

                first.recreate()
                val restored = sandbox.awaitMainScreen("practice")
                val restoredStore = sandbox.store(restored)
                assertEquals(sessionId, sandbox.readField(restored, "sessionId"))
                assertEquals(plan, restoredStore.one("SELECT plan FROM session WHERE id=?", "$sessionId").getString("plan"))
                assertEquals(1L, restoredStore.count("SELECT COUNT(*) n FROM attempt"))
                onView(withText("下一题／完成本轮")).check(matches(isDisplayed()))
                saveAndExit()
                assertHome()
                compose.assertText("home_progress", "1 / $target")
                compose.clickTag("home_start")
                val resumed = sandbox.awaitMainScreen("practice")
                assertEquals(sessionId, sandbox.readField(resumed, "sessionId"))
                onView(withText("下一题／完成本轮")).perform(click())
                assertEquals(1, restoredStore.one("SELECT position FROM session WHERE id=?", "$sessionId").getInt("position"))
                saveAndExit()
                compose.assertText("home_progress", "1 / $target")
            } finally {
                first.close()
            }
            ActivityScenario.launch(MainActivity::class.java).use {
                val home = sandbox.awaitMainScreen("home")
                val store = sandbox.store(home)
                assertHome()
                compose.assertText("home_progress", "1 / $target")
                assertEquals(savedAttempt, store.one("SELECT * FROM attempt WHERE session_id=?", "$sessionId").toString())
                assertEquals(savedSchema, schema(store))
                assertEquals(4, store.readableDatabase.version)
                compose.clickTag("home_start")
                val practice = sandbox.awaitMainScreen("practice")
                assertEquals(sessionId, sandbox.readField(practice, "sessionId"))
                assertEquals(1, store.one("SELECT position FROM session WHERE id=?", "$sessionId").getInt("position"))
                assertEquals(1L, store.count("SELECT COUNT(*) n FROM attempt"))
                assertEquals(1L, store.count("SELECT COUNT(*) n FROM session"))
            }
            assertTrue("The same persisted data must survive two new hosts", sandbox.initializations >= 3)
        }
    }

    @Test
    fun completedLearningCreatesRealTasksAndTheirCompletionUpdatesHome() {
        MainBridgeSandbox().use { sandbox ->
            ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                val home = sandbox.awaitMainScreen("home")
                val store = sandbox.store(home)
                val savedSchema = schema(store)
                val item = store.one("SELECT * FROM item WHERE kind='question' ORDER BY id LIMIT 1")
                val library = item.getLong("library_id")
                scenario.onActivity { activity ->
                    store.writableDatabase.execSQL("UPDATE library SET archived=1 WHERE id<>?", arrayOf(library))
                    store.writableDatabase.execSQL("UPDATE item SET archived=1 WHERE library_id=? AND id<>?",
                        arrayOf(library, item.getLong("id")))
                    invokeHome(activity)
                }
                compose.assertText("home_progress", "0 / 1")
                compose.clickTag("home_start")
                val practice = sandbox.awaitMainScreen("practice")
                val session = sandbox.readField(practice, "sessionId") as Long
                answerCurrentQuestion(store, session)
                onView(withText("下一题／完成本轮")).perform(click())
                onView(withText("本轮练习报告")).check(matches(isDisplayed()))
                assertEquals(1, store.one("SELECT finished FROM session WHERE id=?", "$session").getInt("finished"))
                assertEquals(4L, store.count("SELECT COUNT(*) n FROM task WHERE source_session=?", "$session"))
                val attempt = store.one("SELECT * FROM attempt WHERE session_id=?", "$session").toString()
                pressBack()
                assertHome()
                compose.assertText("home_progress", "1 / 1")
                compose.assertContainsText("4 项巩固任务")
                compose.openStudyAction("home_tasks")
                onView(withText("巩固与复测")).check(matches(isDisplayed()))
                onView(withText(startsWith("概念回顾与辨析 ·"))).perform(scrollTo(), click())
                onView(withText("已回顾学习内容 · 完成本阶段")).perform(scrollTo(), click())
                assertEquals(1, store.one("SELECT completed FROM task WHERE source_session=? AND stage='concept'", "$session").getInt("completed"))
                assertEquals(3L, store.count("SELECT COUNT(*) n FROM task WHERE source_session=? AND completed=0", "$session"))
                assertEquals(attempt, store.one("SELECT * FROM attempt WHERE session_id=?", "$session").toString())
                pressBack()
                assertHome()
                compose.assertContainsText("3 项巩固任务")
                assertEquals(savedSchema, schema(store))
                assertEquals(4, store.readableDatabase.version)
            }
        }
    }

    @Test
    fun allStudyDetailsKeepTheirOriginalBusinessDestinations() {
        MainBridgeSandbox().use { sandbox ->
            ActivityScenario.launch(MainActivity::class.java).use {
                val home = sandbox.awaitMainScreen("home")
                listOf(
                    "home_today_plans" to "今日计划",
                    "home_tasks" to "巩固与复测",
                    "home_due" to "到期复习",
                    "home_progress_details" to "学习报告",
                    "home_resume" to "继续练习",
                ).forEach { (tag, title) ->
                    compose.openStudyAction(tag)
                    onView(withText(title)).check(matches(isDisplayed()))
                    pressBack()
                    assertHome()
                }
                assertEquals(0L, sandbox.store(home).count("SELECT COUNT(*) n FROM attempt"))
                assertEquals(0L, sandbox.store(home).count("SELECT COUNT(*) n FROM session"))
            }
        }
    }

    private fun assertHome() {
        compose.assertDisplayed("home_greeting")
        compose.assertTodaySelected()
        onView(withText("把一点点，变成进步。")).check(doesNotExist())
        onView(withText("今日学习任务")).check(doesNotExist())
    }

    private fun answerCurrentQuestion(store: LearningStore, sessionId: Long) {
        val session = store.one("SELECT * FROM session WHERE id=?", "$sessionId")
        assertNotNull(session)
        assertEquals("question", session.getString("mode"))
        val itemId = org.json.JSONArray(session.getString("plan")).getLong(session.getInt("position"))
        val item = store.one("SELECT * FROM item WHERE id=?", "$itemId")
        onView(allOf(isAssignableFrom(RadioButton::class.java),
            withText(startsWith(item.getString("answer") + "   ")))).perform(scrollTo(), click())
        onView(withText("确定")).perform(scrollTo(), click())
        onView(withText("提交答案")).perform(click())
        assertEquals(1L, store.count("SELECT COUNT(*) n FROM attempt WHERE session_id=? AND position=?",
            "$sessionId", "${session.getInt("position")}"))
        assertEquals(1, store.one("SELECT correct FROM attempt WHERE session_id=? AND position=?",
            "$sessionId", "${session.getInt("position")}").getInt("correct"))
    }

    private fun saveAndExit() {
        pressBack()
        onView(withText("保存并退出")).perform(click())
    }

    private fun invokeHome(activity: MainActivity) {
        MainActivity::class.java.getDeclaredMethod("home", Int::class.javaPrimitiveType)
            .apply { isAccessible = true }.invoke(activity, 0)
    }

    private fun schema(store: LearningStore): String = store.rows(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name",
    ).toString()

    private fun dailyTarget(store: LearningStore): Long = store.one(
        "SELECT COALESCE(SUM(MIN(10,(SELECT COUNT(*) FROM item i WHERE i.library_id=l.id AND i.archived=0))),0) n FROM library l WHERE l.archived=0",
    ).getLong("n")
}
