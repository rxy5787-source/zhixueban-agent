package com.example.adaptive_quiz_app.ui.demo

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.ViewCompositionStrategy
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.adaptive_quiz_app.R
import com.example.adaptive_quiz_app.ui.theme.ZhixueTheme

/** Java calls this bridge without needing a composable function parameter. */
object ComposeDemoUi {
    @JvmStatic
    fun bind(view: ComposeView, onClose: Runnable) {
        // The host is an Activity; dispose when the View is removed from its window.
        view.setViewCompositionStrategy(
            ViewCompositionStrategy.DisposeOnDetachedFromWindowOrReleasedFromPool,
        )
        view.setContent {
            ZhixueTheme {
                ComposeDemoScreen(onClose = onClose::run)
            }
        }
    }
}

@Composable
private fun ComposeDemoScreen(onClose: () -> Unit) {
    var clicks by rememberSaveable { mutableIntStateOf(0) }

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
    ) {
        Column(
            modifier = Modifier
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            Text(
                text = stringResource(R.string.compose_demo_title),
                style = MaterialTheme.typography.headlineMedium,
            )
            Text(
                text = stringResource(R.string.compose_demo_description),
                style = MaterialTheme.typography.bodyLarge,
            )
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    Text(
                        text = stringResource(R.string.compose_demo_counter_title),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        text = stringResource(R.string.compose_demo_counter, clicks),
                        modifier = Modifier.testTag("compose_counter"),
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Button(
                            onClick = { clicks++ },
                            modifier = Modifier.testTag("compose_increment"),
                        ) {
                            Text(stringResource(R.string.compose_demo_increment))
                        }
                        OutlinedButton(
                            onClick = { clicks = 0 },
                            enabled = clicks > 0,
                            modifier = Modifier.testTag("compose_reset"),
                        ) {
                            Text(stringResource(R.string.compose_demo_reset))
                        }
                    }
                }
            }
            OutlinedButton(
                onClick = onClose,
                modifier = Modifier.fillMaxWidth().testTag("compose_close"),
            ) {
                Text(stringResource(R.string.compose_demo_close))
            }
        }
    }
}

@Preview(showBackground = true, widthDp = 360)
@Composable
private fun ComposeDemoPreview() {
    ZhixueTheme {
        ComposeDemoScreen(onClose = {})
    }
}
