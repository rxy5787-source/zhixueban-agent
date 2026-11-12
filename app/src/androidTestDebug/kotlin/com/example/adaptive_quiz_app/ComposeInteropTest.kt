package com.example.adaptive_quiz_app

import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.lifecycle.Lifecycle
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.example.adaptive_quiz_app.ui.demo.ComposeDemoActivity
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ComposeInteropTest {
    @get:Rule
    val compose = createAndroidComposeRule<ComposeDemoActivity>()

    @Test
    fun javaXmlHostAndComposeStateSurviveActivityRecreation() {
        onView(withId(R.id.compose_demo_native_header)).check(matches(isDisplayed()))
        compose.onNodeWithTag("compose_counter").assertTextEquals("已点击 0 次")
        compose.onNodeWithTag("compose_reset").assertIsNotEnabled()
        compose.onNodeWithTag("compose_increment").performClick()
        compose.onNodeWithTag("compose_counter").assertTextEquals("已点击 1 次")

        compose.activityRule.scenario.recreate()

        onView(withId(R.id.compose_demo_native_header)).check(matches(isDisplayed()))
        compose.onNodeWithTag("compose_counter").assertTextEquals("已点击 1 次")
        compose.onNodeWithTag("compose_reset").assertIsEnabled().performClick()
        compose.onNodeWithTag("compose_counter").assertTextEquals("已点击 0 次")
    }

    @Test
    fun composeCloseButtonCallsJavaHost() {
        compose.onNodeWithTag("compose_close").performClick()
        // finish() completes after the window transition, not merely main-looper idle.
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.activityRule.scenario.state == Lifecycle.State.DESTROYED
        }
        assertEquals(Lifecycle.State.DESTROYED, compose.activityRule.scenario.state)
    }
}
