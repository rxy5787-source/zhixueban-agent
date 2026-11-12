package com.example.adaptive_quiz_app.ui.prototype

import android.os.Bundle
import android.content.Intent
import android.content.res.Configuration
import android.view.ContextThemeWrapper
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.ViewCompositionStrategy
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.example.adaptive_quiz_app.R
import com.example.adaptive_quiz_app.MainActivity
import com.example.adaptive_quiz_app.ui.theme.ZhixuePalette
import com.example.adaptive_quiz_app.ui.theme.ZhixueTheme

/** Debug home. Display state stays mocked; actions enter the existing Java screens. */
class HomePrototypeActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        delegate.localNightMode = AppCompatDelegate.MODE_NIGHT_NO
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        // Only the debug UI receives this configuration; the system and learning Activity keep theirs.
        val scale = intent.getFloatExtra("home_font_scale", 0f)
        val uiContext = if (scale in setOf(1f, 1.3f, 1.6f)) {
            // Keep the Activity as base context so dialogs retain its WindowManager/token.
            ContextThemeWrapper(this, 0).apply {
                applyOverrideConfiguration(Configuration().apply { fontScale = scale })
            }
        } else this
        val view = ComposeView(uiContext).apply {
            id = R.id.home_prototype_root
            setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnDetachedFromWindowOrReleasedFromPool)
            setContent {
                ZhixueTheme {
                    HomePrototype { action ->
                        startActivity(Intent(this@HomePrototypeActivity, MainActivity::class.java)
                            .putExtra(MainActivity.EXTRA_HOME_ACTION, action))
                    }
                }
            }
        }
        setContentView(view)
        WindowInsetsControllerCompat(window, view).apply {
            isAppearanceLightStatusBars = true
            isAppearanceLightNavigationBars = true
        }
        @Suppress("DEPRECATION") // Needed for the existing API 24+ devices; newer Android draws edge to edge.
        window.statusBarColor = ZhixuePalette.Paper.toArgb()
        @Suppress("DEPRECATION")
        window.navigationBarColor = ZhixuePalette.White.toArgb()
    }
}
