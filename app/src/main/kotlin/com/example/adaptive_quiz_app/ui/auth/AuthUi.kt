package com.example.adaptive_quiz_app.ui.auth

import androidx.appcompat.app.AppCompatActivity
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.ViewCompositionStrategy
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.example.adaptive_quiz_app.R
import com.example.adaptive_quiz_app.ui.components.ZhixueCard
import com.example.adaptive_quiz_app.ui.components.ZhixuePrimaryButton
import com.example.adaptive_quiz_app.ui.theme.ZhixueTheme
import com.example.adaptive_quiz_app.ui.theme.ZhixuePalette
import java.util.function.Consumer

data class AuthForm(val action: String, val register: Boolean, val username: String, val password: String, val confirmation: String)

object AuthUi {
    private class Host(val initialRegister: Boolean, val callback: Consumer<AuthForm>) {
        var message by mutableStateOf("")
        var busy by mutableStateOf(false)
        var retry by mutableStateOf(false)
    }
    @JvmStatic
    fun show(activity: AppCompatActivity, message: String, busy: Boolean, retry: Boolean, register: Boolean, callback: Consumer<AuthForm>) {
        WindowCompat.setDecorFitsSystemWindows(activity.window, false)
        activity.window.statusBarColor = ZhixuePalette.Paper.toArgb()
        activity.window.navigationBarColor = ZhixuePalette.Paper.toArgb()
        var view = activity.findViewById<ComposeView>(R.id.auth_root)
        var host = view?.tag as? Host
        if (view == null || host == null) {
            host = Host(register, callback)
            val state = host
            view = ComposeView(activity).apply {
                id = R.id.auth_root
                tag = state
                setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnDetachedFromWindowOrReleasedFromPool)
                setContent { ZhixueTheme { LoginForm(state) } }
            }
            activity.setContentView(view)
        }
        host.message = message
        host.busy = busy
        host.retry = retry
        WindowInsetsControllerCompat(activity.window, view).apply {
            isAppearanceLightStatusBars = true
            isAppearanceLightNavigationBars = true
        }
    }
    @Composable
    private fun LoginForm(host: Host) {
        var register by rememberSaveable { mutableStateOf(host.initialRegister) }
        var username by rememberSaveable { mutableStateOf("") }
        var password by remember { mutableStateOf("") }
        var confirmation by remember { mutableStateOf("") }
        var showPassword by remember { mutableStateOf(false) }
        var showConfirmation by remember { mutableStateOf(false) }
        var submitted by remember { mutableStateOf(false) }
        val focus = LocalFocusManager.current
        val usernameFocus = remember { FocusRequester() }
        val passwordFocus = remember { FocusRequester() }
        val confirmationFocus = remember { FocusRequester() }
        val validUsername = username.trim().matches(Regex("[A-Za-z0-9_]{4,32}"))
        val validPassword = password.length in 8..128
        val validConfirmation = !register || password == confirmation
        val submit: () -> Unit = {
            if (!host.busy) {
                submitted = true
                host.message = ""
                when {
                    !validUsername -> usernameFocus.requestFocus()
                    !validPassword -> passwordFocus.requestFocus()
                    !validConfirmation -> confirmationFocus.requestFocus()
                    else -> {
                        focus.clearFocus()
                        host.callback.accept(AuthForm("submit", register, username.trim(), password, confirmation))
                    }
                }
            }
        }
        Surface(color = MaterialTheme.colorScheme.background) {
            Box(Modifier.fillMaxSize().safeDrawingPadding().imePadding(), contentAlignment = Alignment.TopCenter) {
            Column(
                Modifier.widthIn(max = 480.dp).fillMaxWidth().verticalScroll(rememberScrollState())
                    .padding(horizontal = 20.dp, vertical = 20.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Image(painterResource(R.drawable.ic_zhixue), null, Modifier.size(32.dp))
                    Text("知学伴", style = MaterialTheme.typography.titleMedium)
                }
                Text(if (register) "开始你的学习积累" else "欢迎回来", style = MaterialTheme.typography.headlineMedium)
                Text(if (register) "创建账号，开启今天的学习。" else "登录后，继续今天的学习。", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                ZhixueCard(Modifier.fillMaxWidth(), contentPadding = PaddingValues(16.dp)) {
                    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                        Text(if (register) "创建账号" else "登录账号", style = MaterialTheme.typography.titleMedium)
                        OutlinedTextField(
                            value = username, onValueChange = { username = it; host.message = "" }, label = { Text("账号") },
                            isError = submitted && !validUsername,
                            supportingText = if (register || submitted && !validUsername) ({ Text("4–32 位字母、数字或下划线") }) else null,
                            singleLine = true, enabled = !host.busy,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii, autoCorrectEnabled = false, imeAction = ImeAction.Next),
                            keyboardActions = KeyboardActions(onNext = { passwordFocus.requestFocus() }),
                            modifier = Modifier.fillMaxWidth().focusRequester(usernameFocus).testTag("auth_username"),
                        )
                        OutlinedTextField(
                            value = password, onValueChange = { password = it; host.message = "" }, label = { Text("密码") },
                            isError = submitted && !validPassword,
                            supportingText = if (register || submitted && !validPassword) ({ Text("8–128 位，区分大小写") }) else null,
                            singleLine = true, enabled = !host.busy,
                            visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                            trailingIcon = { TextButton(onClick = { showPassword = !showPassword }, enabled = !host.busy, modifier = Modifier.testTag("auth_password_visibility")) { Text(if (showPassword) "隐藏" else "显示") } },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = if (register) ImeAction.Next else ImeAction.Done),
                            keyboardActions = KeyboardActions(onNext = { confirmationFocus.requestFocus() }, onDone = { submit() }),
                            modifier = Modifier.fillMaxWidth().focusRequester(passwordFocus).testTag("auth_password"),
                        )
                        if (register) OutlinedTextField(
                            value = confirmation, onValueChange = { confirmation = it; host.message = "" }, label = { Text("确认密码") },
                            isError = submitted && !validConfirmation,
                            supportingText = if (submitted && !validConfirmation) ({ Text("两次输入的密码不一致") }) else null,
                            singleLine = true, enabled = !host.busy,
                            visualTransformation = if (showConfirmation) VisualTransformation.None else PasswordVisualTransformation(),
                            trailingIcon = { TextButton(onClick = { showConfirmation = !showConfirmation }, enabled = !host.busy) { Text(if (showConfirmation) "隐藏" else "显示") } },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                            keyboardActions = KeyboardActions(onDone = { submit() }),
                            modifier = Modifier.fillMaxWidth().focusRequester(confirmationFocus).testTag("auth_confirmation"),
                        )
                        if (host.message.isNotEmpty()) Text(host.message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.testTag("auth_message"))
                        ZhixuePrimaryButton(
                            onClick = submit,
                            enabled = !host.busy, modifier = Modifier.fillMaxWidth().testTag("auth_submit"),
                        ) {
                            if (host.busy) {
                                CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                                Spacer(Modifier.width(8.dp))
                            }
                            Text(if (host.busy) "正在连接…" else if (register) "注册并登录" else "登录")
                        }
                        if (host.retry) TextButton(
                            onClick = { host.callback.accept(AuthForm("retry", register, "", "", "")) }, enabled = !host.busy,
                            modifier = Modifier.fillMaxWidth().testTag("auth_retry"),
                        ) { Text("重新连接已登录账号") }
                        TextButton(
                            onClick = { register = !register; password = ""; confirmation = ""; showPassword = false; showConfirmation = false; submitted = false; host.message = ""; focus.clearFocus() }, enabled = !host.busy,
                            modifier = Modifier.fillMaxWidth().testTag("auth_switch"),
                        ) { Text(if (register) "已有账号，去登录" else "还没有账号，去注册") }
                    }
                }
                Text("学习记录按账号保存在本机。", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            }
        }
    }
}
