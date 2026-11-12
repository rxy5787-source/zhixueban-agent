package com.example.adaptive_quiz_app.ui.home

import androidx.appcompat.app.AppCompatActivity
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.ViewCompositionStrategy
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.example.adaptive_quiz_app.R
import com.example.adaptive_quiz_app.ui.theme.ZhixuePalette
import com.example.adaptive_quiz_app.ui.theme.ZhixueTheme
import org.json.JSONObject
import java.util.function.Consumer

/** Small View/Compose bridge. Every action goes back to the existing Java host. */
object ComposeHomeUi {
    private class HomeHost(initialState: HomeUiState, var onAction: Consumer<String>) {
        var state by mutableStateOf(initialState)
    }

    @JvmStatic
    fun show(activity: AppCompatActivity, snapshot: JSONObject, onAction: Consumer<String>) {
        render(activity, HomeStateMapper.fromSnapshot(snapshot), onAction)
    }

    @JvmStatic
    fun showLoading(activity: AppCompatActivity) {
        render(activity, HomeStateMapper.loading(), Consumer { })
    }

    private fun render(activity: AppCompatActivity, state: HomeUiState, onAction: Consumer<String>) {
        WindowCompat.setDecorFitsSystemWindows(activity.window, false)
        val existingView = activity.findViewById<ComposeView>(R.id.compose_home_root)
        val existingHost = existingView?.tag as? HomeHost
        val view = if (existingView != null && existingHost != null) {
            // Keep the composition (and its saved scroll/sheet state) while refreshing data.
            existingHost.onAction = onAction
            existingHost.state = state
            existingView
        } else {
            val host = HomeHost(state, onAction)
            ComposeView(activity).apply {
                id = R.id.compose_home_root
                tag = host
                setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnDetachedFromWindowOrReleasedFromPool)
                setContent {
                    ZhixueTheme {
                        HomeScreen(
                            state = host.state,
                            onStartLearning = { host.onAction.accept("learn") },
                            onFocusClick = { host.onAction.accept("focus") },
                            onDestinationClick = { destination ->
                                when (destination) {
                                    HomeDestination.Today -> Unit
                                    HomeDestination.Libraries -> host.onAction.accept("libraries")
                                    HomeDestination.Profile -> host.onAction.accept("profile")
                                }
                            },
                            onStudyAction = { host.onAction.accept(it) },
                        )
                    }
                }
            }.also { activity.setContentView(it) }
        }
        WindowInsetsControllerCompat(activity.window, view).apply {
            isAppearanceLightStatusBars = true
            isAppearanceLightNavigationBars = true
        }
        @Suppress("DEPRECATION") // Existing API 24 devices still use platform bar colors.
        activity.window.statusBarColor = ZhixuePalette.Paper.toArgb()
        @Suppress("DEPRECATION")
        activity.window.navigationBarColor = ZhixuePalette.White.toArgb()
    }
}
