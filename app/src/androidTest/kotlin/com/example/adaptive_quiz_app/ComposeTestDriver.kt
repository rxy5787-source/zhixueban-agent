package com.example.adaptive_quiz_app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import org.junit.rules.TestRule
import org.junit.runner.Description
import org.junit.runners.model.Statement

/** A test-only Java bridge: native business tests can operate the real Compose home. */
class ComposeTestDriver : TestRule {
    private val compose = createEmptyComposeRule()

    override fun apply(base: Statement, description: Description): Statement = compose.apply(base, description)

    fun clickTag(tag: String) {
        val node = compose.onNodeWithTag(tag, useUnmergedTree = true)
        if (!tag.startsWith("home_nav_")) node.performScrollTo()
        node.assertIsDisplayed().performClick()
        compose.waitForIdle()
    }

    fun assertDisplayed(tag: String) {
        val node = compose.onNodeWithTag(tag, useUnmergedTree = true)
        if (!tag.startsWith("home_nav_")) node.performScrollTo()
        node.assertIsDisplayed()
    }

    fun assertText(tag: String, text: String) {
        compose.onNodeWithTag(tag, useUnmergedTree = true).assertTextEquals(text)
    }

    fun assertTodaySelected() {
        compose.onNodeWithTag("home_nav_Today").assertIsSelected()
    }

    fun assertNoText(text: String) {
        compose.onNodeWithText(text, useUnmergedTree = true).assertDoesNotExist()
    }

    fun assertContainsText(text: String) {
        compose.onNodeWithText(text, substring = true, useUnmergedTree = true).assertExists()
    }

    fun openStudyAction(tag: String) {
        clickTag("home_today_plan")
        clickTag(tag)
    }
}
