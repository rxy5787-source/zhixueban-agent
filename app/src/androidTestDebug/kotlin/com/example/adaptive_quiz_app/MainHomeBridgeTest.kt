package com.example.adaptive_quiz_app

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import android.os.SystemClock
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleCallback
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import com.example.adaptive_quiz_app.learning.LearningStore
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.ExecutorService
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.Rule
import org.junit.runner.RunWith

/** Whole-lifecycle database isolation also protects the real user during recreation. */
class MainBridgeSandbox(private val onboarded: Boolean = true) : AutoCloseable {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val target = instrumentation.targetContext
    private val prefix = "home_bridge_test_"
    private val activities = CopyOnWriteArrayList<MainActivity>()
    var initializations: Int = 0
        private set

    private val lifecycle = ActivityLifecycleCallback { activity: Activity, stage: Stage ->
        if (activity is MainActivity && stage == Stage.PRE_ON_CREATE) {
            // This runs before MainActivity starts its worker. No initialization, seed or
            // restored session can access a production database or production preference.
            val original = activity.baseContext
            val isolated = object : ContextWrapper(original) {
                override fun openOrCreateDatabase(name: String, mode: Int,
                    factory: SQLiteDatabase.CursorFactory?): SQLiteDatabase =
                    original.openOrCreateDatabase(prefix + name, mode, factory)

                override fun openOrCreateDatabase(name: String, mode: Int,
                    factory: SQLiteDatabase.CursorFactory?, handler: DatabaseErrorHandler?): SQLiteDatabase =
                    original.openOrCreateDatabase(prefix + name, mode, factory, handler)

                override fun getDatabasePath(name: String): File = original.getDatabasePath(prefix + name)

                override fun getSharedPreferences(name: String, mode: Int) =
                    original.getSharedPreferences(prefix + name, mode)
            }
            ContextWrapper::class.java.getDeclaredField("mBase").apply { isAccessible = true }
                .set(activity, isolated)
            check(activity.baseContext === isolated) { "Database sandbox must be installed before onCreate" }
            activities += activity
            initializations++
        }
    }

    init {
        com.example.adaptive_quiz_app.auth.AuthTestBridge.setEnabled(true)
        target.deleteDatabase(prefix + "zhixue_learning.db")
        assertTrue(target.getSharedPreferences(prefix + "MainActivity", Context.MODE_PRIVATE).edit()
            .clear().putBoolean("onboarded", onboarded).putInt("daily", 10).commit())
        instrumentation.runOnMainSync {
            ActivityLifecycleMonitorRegistry.getInstance().addLifecycleCallback(lifecycle)
        }
    }

    fun awaitMainScreen(screen: String, timeoutMillis: Long = 12_000): MainActivity {
        var found: MainActivity? = null
        val deadline = SystemClock.elapsedRealtime() + timeoutMillis
        while (found == null && SystemClock.elapsedRealtime() < deadline) {
            instrumentation.runOnMainSync {
                found = activities.lastOrNull { !it.isDestroyed && !it.isFinishing && readField(it, "screen") == screen }
            }
            if (found == null) SystemClock.sleep(30)
        }
        return checkNotNull(found) { "MainActivity did not reach $screen in isolated database" }
    }

    fun readField(activity: MainActivity, name: String): Any? {
        var type: Class<*>? = MainActivity::class.java
        while (type != null) {
            try { return type.getDeclaredField(name).apply { isAccessible = true }.get(activity) }
            catch (_: NoSuchFieldException) { type = type.superclass }
        }
        error("Missing Activity field $name")
    }

    fun store(activity: MainActivity) = readField(activity, "db") as LearningStore

    override fun close() {
        com.example.adaptive_quiz_app.auth.AuthTestBridge.setEnabled(false)
        instrumentation.runOnMainSync {
            activities.filter { !it.isDestroyed }.forEach { it.finish() }
            ActivityLifecycleMonitorRegistry.getInstance().removeLifecycleCallback(lifecycle)
        }
        instrumentation.waitForIdleSync()
        // Finish and worker shutdown precede deleting the sandbox files, including WAL/SHM.
        val deadline = SystemClock.elapsedRealtime() + 12_000
        while (activities.any { !it.isDestroyed } && SystemClock.elapsedRealtime() < deadline) {
            instrumentation.waitForIdleSync()
            SystemClock.sleep(30)
        }
        assertTrue("All isolated Activities must be destroyed", activities.all { it.isDestroyed })
        activities.forEach { activity ->
            val worker = readField(activity, "worker") as ExecutorService
            assertTrue("Main worker must finish closing its store", worker.awaitTermination(8, TimeUnit.SECONDS))
        }
        target.databaseList().filter { it.startsWith(prefix) }.forEach { target.deleteDatabase(it) }
        File(target.applicationInfo.dataDir, "shared_prefs").listFiles().orEmpty()
            .filter { it.name.startsWith(prefix) && it.name.endsWith(".xml") }.forEach { file ->
            assertTrue(target.deleteSharedPreferences(file.name.removeSuffix(".xml")))
        }
    }
}

@RunWith(AndroidJUnit4::class)
class MainHomeBridgeTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    @get:Rule val compose = ComposeTestDriver()

    @Test
    fun learningRouteUsesExistingSessionFlowAndRecreationDoesNotRepeatIt() {
        MainBridgeSandbox().use { sandbox ->
            val intent = Intent(instrumentation.targetContext, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            ActivityScenario.launch<MainActivity>(intent).use { scenario ->
                val ready = sandbox.awaitMainScreen("home")
                assertEquals(0L, sandbox.store(ready).count("SELECT COUNT(*) n FROM session"))
                scenario.onActivity { activity ->
                    activity.intent = Intent(activity, MainActivity::class.java)
                        .putExtra(MainActivity.EXTRA_HOME_ACTION, "learn")
                    val open = MainActivity::class.java.getDeclaredMethod("openRequestedHomeAction")
                        .apply { isAccessible = true }
                    assertTrue(open.invoke(activity) as Boolean)
                    assertFalse(activity.intent.hasExtra(MainActivity.EXTRA_HOME_ACTION))
                    assertEquals("practice", sandbox.readField(activity, "screen"))
                    assertFalse("The consumed action cannot launch twice", open.invoke(activity) as Boolean)
                }
                val original = sandbox.awaitMainScreen("practice")
                val session = sandbox.readField(original, "sessionId") as Long
                assertTrue("Original Java learning flow creates its session", session > 0)
                assertEquals(1L, sandbox.store(original).count("SELECT COUNT(*) n FROM session"))
                assertEquals(0L, sandbox.store(original).count("SELECT COUNT(*) n FROM attempt"))

                scenario.recreate()
                val restored = sandbox.awaitMainScreen("practice")
                assertTrue("Recreation creates another isolated Activity", sandbox.initializations >= 2)
                assertEquals("The same learning session is resumed", session,
                    sandbox.readField(restored, "sessionId"))
                assertFalse(restored.intent.hasExtra(MainActivity.EXTRA_HOME_ACTION))
                assertEquals("Rotation must not create another session", 1L,
                    sandbox.store(restored).count("SELECT COUNT(*) n FROM session"))
            }
        }
    }

    @Test
    fun freshLaunchShowsComposeAndLearningAloneRequestsOnboarding() {
        MainBridgeSandbox(onboarded = false).use { sandbox ->
            val intent = Intent(instrumentation.targetContext, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            ActivityScenario.launch<MainActivity>(intent).use { scenario ->
                val home = sandbox.awaitMainScreen("home")
                compose.assertDisplayed("home_greeting")
                compose.assertTodaySelected()
                assertFalse(home.getPreferences(Context.MODE_PRIVATE).getBoolean("onboarded", false))
                assertEquals(0L, sandbox.store(home).count("SELECT COUNT(*) n FROM session"))
                compose.clickTag("home_start")
                sandbox.awaitMainScreen("welcome")
                onView(withText("跳过引导  ›")).perform(scrollTo(), click())
                val completed = sandbox.awaitMainScreen("home")
                compose.assertDisplayed("home_greeting")
                scenario.onActivity { activity ->
                    assertEquals(0, sandbox.readField(activity, "tab"))
                    assertTrue(activity.getPreferences(Context.MODE_PRIVATE).getBoolean("onboarded", false))
                }
                assertEquals(0L, sandbox.store(completed).count("SELECT COUNT(*) n FROM session"))
                compose.clickTag("home_start")
                val practice = sandbox.awaitMainScreen("practice")
                assertEquals(1L, sandbox.store(practice).count("SELECT COUNT(*) n FROM session"))
                assertEquals(0L, sandbox.store(practice).count("SELECT COUNT(*) n FROM attempt"))
            }
        }
    }
}
