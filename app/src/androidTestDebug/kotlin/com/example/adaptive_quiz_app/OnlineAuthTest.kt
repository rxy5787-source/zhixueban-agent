package com.example.adaptive_quiz_app

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import android.os.SystemClock
import androidx.compose.ui.test.*
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.*
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleCallback
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import com.example.adaptive_quiz_app.auth.*
import com.example.adaptive_quiz_app.learning.LearningStore
import java.io.File
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.ExecutorService
import java.util.concurrent.TimeUnit
import org.hamcrest.Matchers.allOf
import org.hamcrest.Matchers.startsWith
import org.junit.Assert.*
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Real HTTP authentication; every app database, preference and imported file is isolated. */
@RunWith(AndroidJUnit4::class)
class OnlineAuthTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val api get() = AuthApi("http://127.0.0.1:8088")
    private fun username() = "phone_" + UUID.randomUUID().toString().replace("-", "").take(16)
    @Before fun configure() { AuthTestBridge.setEnabled(false); AuthTestBridge.setBaseUrl("http://127.0.0.1:8088"); AuthTestBridge.setOffline(false) }
    @After fun reset() { AuthTestBridge.setOffline(false); AuthTestBridge.setBaseUrl(null); AuthTestBridge.setEnabled(false) }

    private inner class Sandbox : AutoCloseable {
        val target = instrumentation.targetContext
        private val prefix = "online_test_${UUID.randomUUID().toString().replace("-", "").take(10)}_"
        val activities = CopyOnWriteArrayList<Activity>()
        private fun wrap(original: Context) = object : ContextWrapper(original) {
            override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?): SQLiteDatabase = original.openOrCreateDatabase(prefix + name, mode, factory)
            override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?, handler: DatabaseErrorHandler?): SQLiteDatabase = original.openOrCreateDatabase(prefix + name, mode, factory, handler)
            override fun getDatabasePath(name: String): File = original.getDatabasePath(prefix + name)
            override fun getSharedPreferences(name: String, mode: Int) = original.getSharedPreferences(prefix + name, mode)
            override fun getFilesDir(): File = File(original.filesDir, "auth_tests/$prefix").apply { mkdirs() }
        }
        val context: Context = wrap(target)
        private val callback = ActivityLifecycleCallback { activity, stage ->
            if ((activity is MainActivity || activity is LoginActivity) && stage == Stage.PRE_ON_CREATE) {
                // Model inference can outlast the phone's display timeout. This
                // flag belongs only to sandbox test windows and disappears on close.
                activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                ContextWrapper::class.java.getDeclaredField("mBase").apply { isAccessible = true }.set(activity, wrap(activity.baseContext))
                activities += activity
            }
        }
        init {
            instrumentation.runOnMainSync { ActivityLifecycleMonitorRegistry.getInstance().addLifecycleCallback(callback) }
        }
        inline fun <reified T : Activity> awaitActivity(): T {
            var found: T? = null
            val deadline = SystemClock.elapsedRealtime() + 15_000
            while (found == null && SystemClock.elapsedRealtime() < deadline) {
                instrumentation.runOnMainSync { found = activities.filterIsInstance<T>().lastOrNull { !it.isFinishing && !it.isDestroyed } }
                if (found == null) SystemClock.sleep(30)
            }
            return checkNotNull(found) { "Expected activity ${T::class.java.simpleName}" }
        }
        override fun close() {
            AuthTestBridge.setOffline(false)
            instrumentation.runOnMainSync {
                activities.filter { !it.isDestroyed }.forEach { it.finish() }
                ActivityLifecycleMonitorRegistry.getInstance().removeLifecycleCallback(callback)
            }
            instrumentation.waitForIdleSync()
            activities.filterIsInstance<MainActivity>().forEach {
                val executor = MainActivity::class.java.getDeclaredField("worker").apply { isAccessible = true }.get(it) as ExecutorService
                assertTrue(executor.awaitTermination(10, TimeUnit.SECONDS))
                val gate = MainActivity::class.java.getDeclaredField("authGate").apply { isAccessible = true }.get(it)
                if (gate != null) {
                    val authWorker = OnlineAuthGate::class.java.getDeclaredField("worker").apply { isAccessible = true }.get(gate) as ExecutorService
                    assertTrue(authWorker.awaitTermination(15, TimeUnit.SECONDS))
                }
            }
            target.databaseList().filter { it.startsWith(prefix) }.forEach { target.deleteDatabase(it) }
            File(target.applicationInfo.dataDir, "shared_prefs").listFiles().orEmpty().filter { it.name.startsWith(prefix) }.forEach { target.deleteSharedPreferences(it.name.removeSuffix(".xml")) }
            context.filesDir.deleteRecursively()
        }
    }
    private fun awaitTag(tag: String) {
        compose.waitUntil(15_000) { compose.onAllNodesWithTag(tag, useUnmergedTree = true).fetchSemanticsNodes(atLeastOneRootRequired = false).isNotEmpty() }
    }
    private fun fill(tag: String, value: String) { compose.onNodeWithTag(tag, useUnmergedTree = true).performScrollTo().performTextReplacement(value) }
    private fun tap(tag: String) { compose.onNodeWithTag(tag, useUnmergedTree = true).performScrollTo().performClick() }
    private fun store(activity: MainActivity): LearningStore = MainActivity::class.java.getDeclaredField("db").apply { isAccessible = true }.get(activity) as LearningStore
    private fun captureAi(name: String) {
        instrumentation.waitForIdleSync()
        android.os.SystemClock.sleep(350)
        val bitmap = instrumentation.uiAutomation.takeScreenshot()
        File(instrumentation.targetContext.getExternalFilesDir(null), name).outputStream().use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }

    /** A pending status response must never swallow a cancellation tap. No inference is mocked as successful. */
    @Test fun cancellationBypassesBlockedPollAndIgnoresItsLateResponse() {
        AuthTestBridge.setBaseUrl(BuildConfig.AUTH_BASE_URL)
        val auth=AuthApi(BuildConfig.AUTH_BASE_URL)
        val session=auth.authenticate(true,username(),"Cancel-regression_123")
        val server=java.net.ServerSocket(0,10,java.net.InetAddress.getByName("127.0.0.1"))
        val requests=java.util.concurrent.Executors.newCachedThreadPool()
        val pending=java.util.concurrent.CountDownLatch(1)
        val release=java.util.concurrent.CountDownLatch(1)
        val cancellation=java.util.concurrent.CountDownLatch(1)
        val polls=java.util.concurrent.atomic.AtomicInteger()
        val stopped=java.util.concurrent.atomic.AtomicBoolean()
        val running="""{"state":"running","stage":"解析资料","accepted":0,"cancelRequested":false}"""
        val cancelled="""{"state":"cancelled","stage":"已取消，已保存结果保留","accepted":0,"cancelRequested":true}"""
        requests.execute {
            while(!stopped.get()) {
                val socket=try { server.accept() } catch (_:java.io.IOException) { break }
                requests.execute {
                    socket.use {
                        try {
                            val reader=it.getInputStream().bufferedReader()
                            val first=reader.readLine().orEmpty()
                            var length=0
                            while(true){val line=reader.readLine()?:break;if(line.isEmpty())break;if(line.startsWith("Content-Length:",true))length=line.substringAfter(':').trim().toInt()}
                            repeat(length){reader.read()}
                            val body=when {
                                first.startsWith("POST ") && first.contains("/cancel ") -> { cancellation.countDown();cancelled }
                                first.contains("/result ") -> """{"accepted":0,"files":[{"name":"资料.pdf","parsing":[{"location":"PDF第1页","extraction":"ocr","parsingNote":null,"parsingError":null,"textPreview":"测试识别文字"}]}],"rejected":[],"content":{"libraries":[]}}"""
                                polls.incrementAndGet()==1 -> running
                                else -> { pending.countDown();release.await(15,TimeUnit.SECONDS);running }
                            }
                            val bytes=body.toByteArray(Charsets.UTF_8)
                            it.getOutputStream().apply { write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n\r\n".toByteArray());write(bytes);flush() }
                        } catch (_:java.io.IOException) { }
                    }
                }
            }
        }
        var controller:com.example.adaptive_quiz_app.ai.AiGenerationController?=null
        try {
            Sandbox().use { sandbox ->
                SessionStore(sandbox.context).save(session)
                ActivityScenario.launch(MainActivity::class.java).use {
                    awaitTag("home_start")
                    val activity=sandbox.awaitActivity<MainActivity>()
                    val data=store(activity)
                    val before=data.rows("SELECT * FROM attempt ORDER BY id").toString()
                    instrumentation.runOnMainSync {
                        controller=com.example.adaptive_quiz_app.ai.AiGenerationController(activity,data,session,null,{},com.example.adaptive_quiz_app.ai.AiApi("http://127.0.0.1:${server.localPort}"))
                        controller!!.show(android.os.Bundle().apply { putString("owner",session.userId);putString("job","pending-status") })
                    }
                    assertTrue("Second status request must be blocked",pending.await(10,TimeUnit.SECONDS))
                    val started=SystemClock.elapsedRealtime()
                    onView(withId(R.id.ai_cancel)).perform(scrollTo(),click())
                    assertTrue("Cancel must reach server without waiting for status",cancellation.await(2,TimeUnit.SECONDS))
                    assertTrue(SystemClock.elapsedRealtime()-started<2500)
                    var shown=false
                    val deadline=SystemClock.elapsedRealtime()+5000
                    while(!shown&&SystemClock.elapsedRealtime()<deadline){instrumentation.runOnMainSync { shown=activity.findViewById<android.widget.TextView>(R.id.ai_status).text.startsWith("已取消") };SystemClock.sleep(50)}
                    assertTrue("Cancelled state must be rendered",shown)
                    release.countDown();SystemClock.sleep(1000)
                    instrumentation.runOnMainSync { assertTrue(activity.findViewById<android.widget.TextView>(R.id.ai_status).text.startsWith("已取消"));assertEquals(android.view.View.GONE,activity.findViewById<android.view.View>(R.id.ai_cancel).visibility) }
                    assertEquals(before,data.rows("SELECT * FROM attempt ORDER BY id").toString())
                    onView(withId(R.id.ai_extracted_text)).perform(scrollTo(),click())
                    onView(withId(android.R.id.message)).check(matches(withText(org.hamcrest.Matchers.containsString("测试识别文字"))))
                    onView(withId(android.R.id.message)).check(matches(withText(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("null")))))
                    pressBack()
                    captureAi("ai-cancel-blocked-status.png")
                    instrumentation.runOnMainSync { controller!!.close() }
                }
            }
        } finally {
            controller?.close();release.countDown();stopped.set(true);server.close();requests.shutdownNow();requests.awaitTermination(5,TimeUnit.SECONDS);auth.logout(session.token)
        }
    }

    @Test fun realAiUploadImportAnswerAndTraceSurviveDuplicateImport() {
        AuthTestBridge.setBaseUrl(BuildConfig.AUTH_BASE_URL)
        val actualAuth=AuthApi(BuildConfig.AUTH_BASE_URL)
        val session=actualAuth.authenticate(true,username(),"Ai-live-verification_123")
        val scan=InstrumentationRegistry.getArguments().getString("scanPdf")
        val personalized=InstrumentationRegistry.getArguments().getString("personalized")=="true"
        val requested=if(scan==null)"出一道简单单选题，重点考查 WHERE 筛选数据行的用途。" else "出一道简单单选题，只考查资料里已写明的截位直除规则：选项差距大时截几位。不要补全默写表中的空白答案。"
        try {
            Sandbox().use { sandbox ->
                SessionStore(sandbox.context).save(session)
                ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                    awaitTag("home_start")
                    var first=sandbox.awaitActivity<MainActivity>()
                    var data=store(first)
                    val point=data.rows("SELECT name,summary,example FROM point ORDER BY id LIMIT 1").getJSONObject(0)
                    val material=point.getString("name")+"\n"+point.getString("summary")+"\n"+point.getString("example")
                    val customName="我的自定义资料题库"
                    var customId=0L
                    if(personalized){
                        assertNotNull("Personalized regression uses the real scanned PDF",scan)
                        customId=data.insert("library",LearningStore.obj("name",customName,"subject","资料学习","kind","question"))
                        val pid=data.insert("point",LearningStore.obj("library_id",customId,"name","截位直除","summary","选项差距大（截两位）；选项差距小（截三位）。","example","","mnemonic",""))
                        val prior=data.insert("item",LearningStore.obj("library_id",customId,"kind","question","prompt","旧题：选项差距较大时采用哪种截位规则？","options","[\"两位\",\"三位\",\"四位\",\"五位\"]","answer","A","explanation","选项差距大（截两位）","difficulty",1,"meaning","","example","","context_prompt",""))
                        data.insert("item_point",LearningStore.obj("item_id",prior,"point_id",pid))
                        val sid=data.startQuestion(customId,prior)
                        data.submit(sid,0,prior,"旧题：选项差距较大时采用哪种截位规则？","A","B",false,2,"question",1000);data.advance(sid)
                    }
                    val attemptsBefore=data.count("SELECT COUNT(*) n FROM attempt")
                    val tracesBefore=data.count("SELECT COUNT(*) n FROM state_change")
                    val file=if(scan==null)File(sandbox.context.filesDir,"真实SQL资料.txt").apply { writeText(material) } else File(scan).also { assertTrue("Scanned PDF fixture required",it.isFile&&it.length()>0) }
                    val uri=android.net.Uri.fromFile(file)
                    compose.onNodeWithTag("home_nav_Libraries").performClick()
                    onView(withText("上传资料出题")).check(matches(isDisplayed()))
                    captureAi("ai-visible-library-entry.png")
                    onView(withText("上传资料出题")).perform(click())
                    onView(withId(R.id.ai_upload)).check(matches(isDisplayed()))
                    onView(withId(R.id.ai_requirements)).check(matches(isDisplayed()))
                    onView(withId(R.id.ai_generate)).check(matches(isDisplayed()))
                    captureAi("ai-upload-first-screen.png")
                    onView(withId(R.id.ai_requirements)).perform(androidx.test.espresso.action.ViewActions.replaceText(requested),androidx.test.espresso.action.ViewActions.closeSoftKeyboard())
                    if(personalized){
                        onView(withId(R.id.ai_target)).perform(scrollTo(),click())
                        onView(withText(customName)).perform(click())
                        onView(withId(R.id.ai_adaptive)).perform(scrollTo(),click())
                        onView(withId(R.id.ai_adaptive)).check(matches(isChecked()))
                        onView(withId(R.id.ai_adaptive_summary)).check(matches(withText(org.hamcrest.Matchers.containsString("掌握估计"))))
                        captureAi("adaptive-generation-before-answer.png")
                    }
                    // Intercept only the system picker result; upload and every AI call use real services.
                    val filter=android.content.IntentFilter(android.content.Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(android.content.Intent.CATEGORY_OPENABLE); addDataType("*/*")
                    }
                    val picked=android.app.Instrumentation.ActivityResult(Activity.RESULT_OK,android.content.Intent().setData(uri))
                    val monitor=android.app.Instrumentation.ActivityMonitor(filter,picked,true)
                    instrumentation.addMonitor(monitor)
                    try { onView(withId(R.id.ai_upload)).perform(click());assertTrue("Upload must open the system document picker",monitor.hits>0) } finally { instrumentation.removeMonitor(monitor) }
                    val uploadedDeadline=android.os.SystemClock.elapsedRealtime()+40_000
                    fun generateEnabled():Boolean {
                        var ready=false
                        instrumentation.runOnMainSync { ready=first.findViewById<android.widget.Button>(R.id.ai_generate)?.isEnabled==true }
                        return ready
                    }
                    while(!generateEnabled()&&android.os.SystemClock.elapsedRealtime()<uploadedDeadline)android.os.SystemClock.sleep(100)
                    assertTrue("The upload button must return from the file picker and perform a real upload",generateEnabled())
                    captureAi("ai-upload-with-requirements.png")
                    scenario.recreate()
                    first=sandbox.awaitActivity<MainActivity>();data=store(first)
                    val restoredDeadline=android.os.SystemClock.elapsedRealtime()+15_000
                    while(!generateEnabled()&&android.os.SystemClock.elapsedRealtime()<restoredDeadline)android.os.SystemClock.sleep(100)
                    onView(withId(R.id.ai_requirements)).check(matches(withText(requested)))
                    if(personalized)onView(withId(R.id.ai_adaptive)).check(matches(isChecked()))
                    assertTrue("Uploaded file handles and requirements survive recreation",generateEnabled())
                    onView(withId(R.id.ai_generate)).perform(click())
                    val ai=com.example.adaptive_quiz_app.ai.AiApi()
                    val handles=com.example.adaptive_quiz_app.ai.AiJobStore(first,session.userId,ai.base)
                    val submittedDeadline=android.os.SystemClock.elapsedRealtime()+20_000
                    while(handles.load().isEmpty()&&android.os.SystemClock.elapsedRealtime()<submittedDeadline)android.os.SystemClock.sleep(100)
                    val job=handles.load();assertTrue("Generate button must submit a task",job.isNotEmpty())
                    val deadline=android.os.SystemClock.elapsedRealtime()+480_000
                    var status:org.json.JSONObject
                    do {
                        status=ai.request("GET","jobs/$job",session,null)
                        if(status.getString("state") !in listOf("queued","running"))break
                        android.os.SystemClock.sleep(1000)
                    } while(android.os.SystemClock.elapsedRealtime()<deadline)
                    assertTrue("Live generation must honor the real request: $status",status.getInt("accepted")>0)
                    val result=ai.request("GET","jobs/$job/result",session,null)
                    val recorded=result.getJSONObject("generationRequest")
                    if(personalized){
                        assertTrue(recorded.getString("requirements").contains(requested))
                        assertTrue(recorded.getString("requirements").contains("掌握估计"))
                        assertEquals(customName,result.getJSONObject("content").getJSONArray("libraries").getJSONObject(0).getString("name"))
                    } else assertEquals(requested,recorded.getString("requirements"))
                    assertEquals(1,recorded.getInt("questionCount"));assertEquals(1,recorded.getInt("difficulty"))
                    val generated=result.getJSONObject("content").getJSONArray("libraries").getJSONObject(0).getJSONArray("items").getJSONObject(0)
                    assertEquals(1,generated.getInt("difficulty"))
                    val focusText=generated.getString("prompt")+generated.getJSONArray("options").getString(generated.getString("answer")[0]-'A')
                    if(scan==null)assertTrue("Question must address the requested WHERE topic: $generated",focusText.contains("WHERE",ignoreCase=true))
                    else {
                        assertTrue("Question must address the real OCR rule: $generated",focusText.contains("位")&&focusText.contains("选项"))
                        assertEquals("ocr",generated.getJSONObject("ai").getString("extraction"))
                        assertTrue(generated.getString("explanation").contains("选项差距大"))
                        assertTrue(generated.getString("explanation").contains("两位"))
                    }
                    File(instrumentation.targetContext.getExternalFilesDir(null),"ai-upload-ui-real-result.json").writeText(result.toString(2))
                    val ready=android.os.SystemClock.elapsedRealtime()+15_000
                    var canImport=false
                    while(android.os.SystemClock.elapsedRealtime()<ready) {
                        instrumentation.runOnMainSync { canImport=first.findViewById<android.widget.Button>(R.id.ai_import)?.let { it.isEnabled&&it.visibility==android.view.View.VISIBLE }==true }
                        if(canImport)break
                        android.os.SystemClock.sleep(100)
                    }
                    assertTrue("Real result must be offered for import",canImport)
                    onView(withText("以下为待导入预览，尚未写入手机知识库。")).perform(scrollTo()).check(matches(isDisplayed()))
                    if(scan!=null){
                        onView(withId(R.id.ai_extracted_text)).perform(scrollTo(),click())
                        onView(withText("资料识别结果")).check(matches(isDisplayed()))
                        captureAi("ai-scan-recognized-text.png")
                        pressBack()
                    }
                    onView(withId(R.id.ai_import)).perform(scrollTo())
                    captureAi("ai-upload-ui-result.png")
                    val stateBeforeImport=data.rows("SELECT * FROM state").toString()
                    onView(withId(R.id.ai_import)).perform(click())
                    val importDeadline=android.os.SystemClock.elapsedRealtime()+10_000
                    while(data.count("SELECT COUNT(*) n FROM ai_source")==0L&&android.os.SystemClock.elapsedRealtime()<importDeadline)android.os.SystemClock.sleep(100)
                    assertEquals(1L,data.count("SELECT COUNT(*) n FROM ai_source"))
                    assertEquals(stateBeforeImport,data.rows("SELECT * FROM state").toString())
                    val item=data.one("SELECT i.* FROM item i JOIN ai_source ai ON ai.item_id=i.id LIMIT 1")
                    val lid=item.getLong("library_id")
                    if(personalized)assertEquals(customId,lid)
                    instrumentation.runOnMainSync {
                        first.getPreferences(0).edit().putBoolean("onboarded",true).commit()
                    }
                    onView(withText("进入题库练习")).perform(scrollTo(),click())
                    if(personalized){
                        captureAi("adaptive-custom-library-cards.png")
                        onView(withText(item.getString("prompt"))).perform(scrollTo(),click())
                        captureAi("adaptive-card-before-answer.png")
                    } else onView(withText("开始自适应练习")).perform(scrollTo(),click())
                    onView(allOf(isAssignableFrom(android.widget.RadioButton::class.java),withText(startsWith(item.getString("answer")+"   ")))).perform(scrollTo(),click())
                    onView(withText("确定")).perform(scrollTo(),click());onView(withText("提交答案")).perform(click())
                    assertEquals(attemptsBefore+1,data.count("SELECT COUNT(*) n FROM attempt"));assertEquals(tracesBefore+1,data.count("SELECT COUNT(*) n FROM state_change"))
                    captureAi("ai-upload-ui-answer.png")
                    onView(withText("下一题／完成本轮")).perform(click())
                    onView(withText("本轮练习报告")).check(matches(isDisplayed()));captureAi("ai-upload-ui-report.png")
                    val state=data.rows("SELECT * FROM state").toString();data.importAiResult(result,session.userId)
                    assertEquals(1L,data.count("SELECT COUNT(*) n FROM ai_source"))
                    assertEquals(if(personalized)2L else 1L,data.count("SELECT COUNT(*) n FROM item WHERE library_id=?","$lid"))
                    assertEquals(state,data.rows("SELECT * FROM state").toString())
                    val backup=data.backup();data.restore(backup)
                    assertEquals(1L,data.count("SELECT COUNT(*) n FROM ai_source"));assertEquals(state,data.rows("SELECT * FROM state").toString())
                    if(personalized){
                        instrumentation.runOnMainSync { MainActivity::class.java.getDeclaredMethod("library",Long::class.javaPrimitiveType).apply { isAccessible=true }.invoke(first,lid) }
                        onView(withText("按掌握情况生成新题")).perform(scrollTo(),click())
                        onView(withId(R.id.ai_adaptive)).check(matches(isChecked()))
                        val latest=data.generationPlan(lid)
                        onView(withId(R.id.ai_adaptive_summary)).perform(scrollTo()).check(matches(withText(org.hamcrest.Matchers.containsString(latest.getString("requirements")))))
                        captureAi("adaptive-generation-after-answer.png")
                    }
                    val trace=data.one("SELECT before_value,after_value,model_version FROM state_change ORDER BY id DESC LIMIT 1")
                    File(instrumentation.targetContext.getExternalFilesDir(null),"ai-upload-ui-verification.json").writeText(org.json.JSONObject().put("jobId",job).put("requirements",requested).put("entryAndUploadButtonVisible",true).put("uploadedFileAndRequestSurvivedRecreation",true).put("attempts",1).put("trace",trace).put("uniqueItems",1).put("sourceRecords",1).put("stateSurvivedDuplicateImportAndBackup",true).toString(2))
                }
            }
        } finally { actualAuth.logout(session.token) }
    }

    @Test fun uploadIsVisibleAndEmptyFileErrorStaysByTheUploadButton() {
        AuthTestBridge.setBaseUrl(BuildConfig.AUTH_BASE_URL)
        val auth=AuthApi(BuildConfig.AUTH_BASE_URL)
        val session=auth.authenticate(true,username(),"Ai-upload-error_123")
        try {
            Sandbox().use { sandbox ->
                SessionStore(sandbox.context).save(session)
                ActivityScenario.launch(MainActivity::class.java).use {
                    awaitTag("home_start");val activity=sandbox.awaitActivity<MainActivity>()
                    compose.onNodeWithTag("home_nav_Libraries").performClick()
                    onView(withText("上传资料出题")).check(matches(isDisplayed())).perform(click())
                    onView(withId(R.id.ai_upload)).check(matches(isDisplayed()))
                    val file=File(sandbox.context.filesDir,"空资料.txt").apply { writeText("") }
                    val filter=android.content.IntentFilter(android.content.Intent.ACTION_OPEN_DOCUMENT).apply { addCategory(android.content.Intent.CATEGORY_OPENABLE);addDataType("*/*") }
                    val picked=android.app.Instrumentation.ActivityResult(Activity.RESULT_OK,android.content.Intent().setData(android.net.Uri.fromFile(file)))
                    val monitor=android.app.Instrumentation.ActivityMonitor(filter,picked,true)
                    instrumentation.addMonitor(monitor)
                    try { onView(withId(R.id.ai_upload)).perform(click()) } finally { instrumentation.removeMonitor(monitor) }
                    val deadline=android.os.SystemClock.elapsedRealtime()+30_000
                    var shown=false
                    while(!shown&&android.os.SystemClock.elapsedRealtime()<deadline){instrumentation.runOnMainSync { shown=activity.findViewById<android.widget.TextView>(R.id.ai_upload_status)?.text.toString().contains("0 字节") };if(!shown)android.os.SystemClock.sleep(100)}
                    assertTrue("Empty file rejection must stay visible beside upload",shown)
                    onView(withId(R.id.ai_upload_status)).check(matches(isDisplayed()))
                    onView(withId(R.id.ai_generate)).check(matches(org.hamcrest.Matchers.not(androidx.test.espresso.matcher.ViewMatchers.isEnabled())))
                    captureAi("ai-upload-empty-file-error.png")
                }
            }
        } finally { auth.logout(session.token) }
    }

    @Test fun lanLoginAndRealUploadWithoutUsbPortForwarding() {
        val host=java.net.URL(BuildConfig.AI_BASE_URL).host
        assertFalse("LAN verification must use the computer address",host in listOf("127.0.0.1","localhost","10.0.2.2"))
        assertEquals(host,java.net.URL(BuildConfig.AUTH_BASE_URL).host)
        AuthTestBridge.setBaseUrl(BuildConfig.AUTH_BASE_URL)
        val auth=AuthApi(BuildConfig.AUTH_BASE_URL)
        val session=auth.authenticate(true,username(),"Lan-upload-verification_123")
        assertEquals(session.userId,auth.verify(session).userId)
        try {
            Sandbox().use { sandbox ->
                SessionStore(sandbox.context).save(session)
                ActivityScenario.launch(MainActivity::class.java).use {
                    awaitTag("home_start");val activity=sandbox.awaitActivity<MainActivity>()
                    val data=store(activity)
                    val before=data.rows("SELECT * FROM attempt ORDER BY id").toString()
                    compose.onNodeWithTag("home_nav_Libraries").performClick()
                    onView(withText("上传资料出题")).perform(click())
                    val file=File(sandbox.context.filesDir,"WiFi上传验证.txt").apply { writeText("WHERE 子句用于筛选数据行。ORDER BY 子句用于排序。") }
                    val filter=android.content.IntentFilter(android.content.Intent.ACTION_OPEN_DOCUMENT).apply { addCategory(android.content.Intent.CATEGORY_OPENABLE);addDataType("*/*") }
                    val picked=android.app.Instrumentation.ActivityResult(Activity.RESULT_OK,android.content.Intent().setData(android.net.Uri.fromFile(file)))
                    val monitor=android.app.Instrumentation.ActivityMonitor(filter,picked,true)
                    instrumentation.addMonitor(monitor)
                    try { onView(withId(R.id.ai_upload)).perform(click());assertTrue(monitor.hits>0) } finally { instrumentation.removeMonitor(monitor) }
                    val deadline=SystemClock.elapsedRealtime()+30_000
                    var ready=false
                    while(!ready&&SystemClock.elapsedRealtime()<deadline){instrumentation.runOnMainSync { ready=activity.findViewById<android.widget.Button>(R.id.ai_generate)?.isEnabled==true };if(!ready)SystemClock.sleep(100)}
                    assertTrue("Actual Wi-Fi upload must finish with no USB forwarding",ready)
                    onView(withId(R.id.ai_upload_status)).check(matches(withText(org.hamcrest.Matchers.containsString("已上传 1 份资料"))))
                    captureAi("ai-wifi-upload-success.png")
                    assertEquals(before,data.rows("SELECT * FROM attempt ORDER BY id").toString())
                    File(instrumentation.targetContext.getExternalFilesDir(null),"ai-wifi-verification.json").writeText(org.json.JSONObject().put("authEndpoint",BuildConfig.AUTH_BASE_URL).put("aiEndpoint",BuildConfig.AI_BASE_URL).put("realUpload",true).put("realAuth",true).put("attemptsUnchanged",true).toString(2))
                }
            }
        } finally { auth.logout(session.token) }
    }

    @Test fun tokenIsEncryptedAndCorruptionRequiresLogin() {
        Sandbox().use { sandbox ->
            val session = AuthSession("random-secret-token-not-plaintext", "store-user", "testname", System.currentTimeMillis() + 60_000)
            val sessions = SessionStore(sandbox.context)
            sessions.save(session)
            assertEquals(session.token, sessions.load()!!.token)
            assertEquals(session.userId, sessions.load()!!.userId)
            assertFalse(sandbox.context.getSharedPreferences("online_auth", 0).getString("token", "")!!.contains(session.token))
            // Identity and expiry are inside the authenticated ciphertext as well.
            sandbox.context.getSharedPreferences("online_auth", 0).edit().putString("userId", "other-user").putLong("expiresAt", Long.MAX_VALUE).commit()
            assertEquals(session.userId, sessions.load()!!.userId)
            assertEquals(session.expiresAt, sessions.load()!!.expiresAt)
            sandbox.context.getSharedPreferences("online_auth", 0).edit().putString("token", "invalid").commit()
            assertNull(sessions.load())
        }
    }
    @Test fun legacyClaimAndAccountSpacesPreserveAndSeparateRecords() {
        Sandbox().use { sandbox ->
            LearningStore(sandbox.context).use { original ->
                original.seed()
                original.insert("library", LearningStore.obj("name", "原学习记录", "subject", "测试", "kind", "question"))
                val before = original.rows("SELECT * FROM library ORDER BY id").toString()
                assertTrue(AccountScope.needsLegacyChoice(sandbox.context, "first-user"))
                AccountScope.choose(sandbox.context, "first-user", true)
                val first = AccountScope(sandbox.context, "first-user")
                val second = AccountScope(sandbox.context, "second-user")
                LearningStore(first.databaseContext()).use { assertEquals(before, it.rows("SELECT * FROM library ORDER BY id").toString()) }
                LearningStore(second.databaseContext()).use {
                    it.seed()
                    assertEquals(0L, it.count("SELECT COUNT(*) n FROM library WHERE name='原学习记录'"))
                }
                sandbox.context.getSharedPreferences(first.preferencesName(), 0).edit().putInt("daily", 17).commit()
                assertEquals(10, sandbox.context.getSharedPreferences(second.preferencesName(), 0).getInt("daily", 10))
                assertNotEquals(first.filesDirectory().canonicalPath, second.filesDirectory().canonicalPath)
                assertEquals(before, original.rows("SELECT * FROM library ORDER BY id").toString())
                assertFalse(AccountScope.needsLegacyChoice(sandbox.context, "second-user"))
                try { AccountScope.choose(sandbox.context, "second-user", true); fail("Legacy owner must not change") } catch (_: IllegalStateException) { }
            }
        }
    }
    @Test fun realServerRejectsWrongPasswordRevokedAndMismatchedSessions() {
        val username = username()
        val session = api.authenticate(true, username, "Network-test-password_123")
        assertEquals(username, api.verify(session).username)
        try { api.authenticate(false, username, "wrong-password"); fail("Wrong password accepted") } catch (failure: AuthApi.Failure) { assertEquals(401, failure.status) }
        try { api.verify(AuthSession(session.token, "other-user", username, session.expiresAt)); fail("Mismatched identity accepted") } catch (failure: AuthApi.Failure) { assertEquals(401, failure.status) }
        api.logout(session.token)
        try { api.verify(session); fail("Revoked token accepted") } catch (failure: AuthApi.Failure) { assertEquals(401, failure.status) }
    }
    @Test fun anonymousMainCannotReadLearningData() {
        Sandbox().use { sandbox ->
            ActivityScenario.launch(MainActivity::class.java).use {
                sandbox.awaitActivity<LoginActivity>()
                awaitTag("auth_submit")
                assertNull(SessionStore(sandbox.context).load())
                assertFalse(sandbox.context.getDatabasePath("zhixue_learning.db").exists())
            }
        }
    }
    @Test fun fieldValidationRejectsLongPasswordsAndImeCanRegister() {
        Sandbox().use { sandbox ->
            ActivityScenario.launch(LoginActivity::class.java).use {
                awaitTag("auth_submit")
                tap("auth_switch")
                fill("auth_username", username())
                fill("auth_password", "x".repeat(129)); fill("auth_confirmation", "x".repeat(129))
                tap("auth_submit")
                compose.onNodeWithTag("auth_password").assert(SemanticsMatcher.keyIsDefined(SemanticsProperties.Error))
                fill("auth_password", "Network-test-password_123"); fill("auth_confirmation", "different-password")
                tap("auth_submit")
                compose.onNodeWithTag("auth_confirmation").assert(SemanticsMatcher.keyIsDefined(SemanticsProperties.Error))
                fill("auth_confirmation", "Network-test-password_123")
                compose.onNodeWithTag("auth_confirmation").performImeAction()
                awaitTag("home_start")
                sandbox.awaitActivity<MainActivity>()
                assertNotNull(SessionStore(sandbox.context).load())
            }
        }
    }
    @Test fun switchingModeClearsPreviousServerError() {
        Sandbox().use {
            val name = username()
            val session = api.authenticate(true, name, "Network-test-password_123")
            try {
                ActivityScenario.launch(LoginActivity::class.java).use {
                    awaitTag("auth_submit")
                    fill("auth_username", name); fill("auth_password", "wrong-password")
                    tap("auth_submit")
                    awaitTag("auth_message")
                    compose.onNodeWithTag("auth_message").assertTextEquals("账号或密码错误")
                    tap("auth_switch")
                    compose.onNodeWithTag("auth_message").assertDoesNotExist()
                    compose.onNodeWithTag("auth_confirmation").assertExists()
                }
            } finally { api.logout(session.token) }
        }
    }
    @Test fun offlineCachedLoginRestoresLearningFromLauncher() {
        Sandbox().use { sandbox ->
            val session = api.authenticate(true, username(), "Network-test-password_123")
            SessionStore(sandbox.context).save(session)
            AuthTestBridge.setOffline(true)
            ActivityScenario.launch(LoginActivity::class.java).use {
                awaitTag("home_start")
                val activity = sandbox.awaitActivity<MainActivity>()
                instrumentation.waitForIdleSync()
                assertNotNull(store(activity))
                assertEquals(session.userId, SessionStore(sandbox.context).load()!!.userId)
                compose.onNodeWithTag("auth_submit").assertDoesNotExist()
                compose.onNodeWithTag("home_nav_Libraries").performClick()
                onView(withText("SQL 基础知识")).perform(scrollTo()).check(matches(isDisplayed()))
            }
            AuthTestBridge.setOffline(false)
            api.logout(session.token)
        }
    }
    @Test fun expiredCachedLoginRequiresAuthenticationEvenOffline() {
        Sandbox().use { sandbox ->
            val session = api.authenticate(true, username(), "Network-test-password_123")
            SessionStore(sandbox.context).save(AuthSession(session.token, session.userId, session.username, 0))
            AuthTestBridge.setOffline(true)
            ActivityScenario.launch(LoginActivity::class.java).use {
                awaitTag("auth_submit")
                assertNull(SessionStore(sandbox.context).load())
                assertFalse(sandbox.activities.any { it is MainActivity })
            }
            AuthTestBridge.setOffline(false)
            api.logout(session.token)
        }
    }
    @Test fun legacySessionCacheRestoresOfflineAndMigratesAfterRenewal() {
        Sandbox().use { sandbox ->
            val session = api.authenticate(true, username(), "Network-test-password_123")
            // Build the previous release's on-disk format: encrypted raw token plus plain metadata.
            val encrypt = SessionStore::class.java.getDeclaredMethod("encrypt", String::class.java).apply { isAccessible = true }
            val prefs = sandbox.context.getSharedPreferences("online_auth", 0)
            prefs.edit().putString("token", encrypt.invoke(null, session.token) as String)
                .putString("userId", session.userId).putString("username", session.username).putLong("expiresAt", session.expiresAt).commit()
            AuthTestBridge.setOffline(true)
            ActivityScenario.launch(LoginActivity::class.java).use {
                awaitTag("home_start")
                val activity = sandbox.awaitActivity<MainActivity>()
                assertEquals(session.userId, SessionStore(sandbox.context).load()!!.userId)
                assertTrue(prefs.contains("userId"))
                AuthTestBridge.setOffline(false)
                instrumentation.runOnMainSync {
                    val gate = MainActivity::class.java.getDeclaredField("authGate").apply { isAccessible = true }.get(activity) as OnlineAuthGate
                    gate.resume()
                }
                compose.waitUntil(15_000) { !prefs.contains("userId") }
                assertEquals(session.token, SessionStore(sandbox.context).load()!!.token)
            }
            api.logout(session.token)
        }
    }
    @Test fun backgroundRenewalPersistsExpiryWithoutShowingLogin() {
        Sandbox().use { sandbox ->
            val session = api.authenticate(true, username(), "Network-test-password_123")
            val shortExpiry = System.currentTimeMillis() + 60_000
            SessionStore(sandbox.context).save(AuthSession(session.token, session.userId, session.username, shortExpiry))
            ActivityScenario.launch(LoginActivity::class.java).use {
                awaitTag("home_start")
                compose.waitUntil(15_000) { (SessionStore(sandbox.context).load()?.expiresAt ?: 0) > shortExpiry }
                assertEquals(session.token, SessionStore(sandbox.context).load()!!.token)
                compose.onNodeWithTag("auth_submit").assertDoesNotExist()
            }
            api.logout(session.token)
        }
    }
    @Test fun reconnectingAfterOfflineUseRejectsServerRevocation() {
        Sandbox().use { sandbox ->
            val session = api.authenticate(true, username(), "Network-test-password_123")
            SessionStore(sandbox.context).save(session)
            AuthTestBridge.setOffline(true)
            ActivityScenario.launch(MainActivity::class.java).use {
                awaitTag("home_start")
                val activity = sandbox.awaitActivity<MainActivity>()
                api.logout(session.token)
                assertEquals(session.token, SessionStore(sandbox.context).load()!!.token)
                AuthTestBridge.setOffline(false)
                instrumentation.runOnMainSync {
                    val gate = MainActivity::class.java.getDeclaredField("authGate").apply { isAccessible = true }.get(activity) as OnlineAuthGate
                    gate.resume()
                }
                awaitTag("auth_submit")
                assertNull(SessionStore(sandbox.context).load())
            }
        }
    }
    @Test fun unreachableServiceRetainsLocalSessionAndLearning() {
        Sandbox().use { sandbox ->
            val session = api.authenticate(true, username(), "Network-test-password_123")
            SessionStore(sandbox.context).save(session)
            AuthTestBridge.setBaseUrl("http://127.0.0.1:1")
            ActivityScenario.launch(MainActivity::class.java).use {
                awaitTag("home_start")
                val activity = sandbox.awaitActivity<MainActivity>()
                val gate = MainActivity::class.java.getDeclaredField("authGate").apply { isAccessible = true }.get(activity)
                compose.waitUntil(15_000) {
                    var finished = false
                    instrumentation.runOnMainSync {
                        finished = !OnlineAuthGate::class.java.getDeclaredField("checking").apply { isAccessible = true }.getBoolean(gate)
                    }
                    finished
                }
                assertFalse(activity.isFinishing)
                assertEquals(session.token, SessionStore(sandbox.context).load()!!.token)
                compose.onNodeWithTag("home_start").assertIsDisplayed()
            }
            AuthTestBridge.setBaseUrl("http://127.0.0.1:8088")
            api.logout(session.token)
        }
    }
    @Test fun staleRenewalsCannotUndoLogoutOrChangeAccount() {
        Sandbox().use { sandbox ->
            val first = SessionStore(sandbox.context)
            val second = SessionStore(sandbox.context)
            val a = AuthSession("first-token", "first-user", "first", System.currentTimeMillis() + 60_000)
            val b = AuthSession("second-token", "second-user", "second", a.expiresAt + 60_000)
            first.save(a)
            second.clear()
            assertFalse(first.saveIfCurrent(a, a))
            assertNull(second.load())
            second.save(b)
            assertFalse(first.saveIfCurrent(a, a))
            assertFalse(first.clearIfCurrent(a))
            assertEquals(b.userId, second.load()!!.userId)
            assertTrue(first.saveIfCurrent(b, AuthSession(b.token, b.userId, b.username, 1)))
            assertEquals(b.expiresAt, second.load()!!.expiresAt)
        }
    }
    @Test fun offlineLogoutClearsCacheAndRevokesWhenReconnected() {
        Sandbox().use { sandbox ->
            val session = api.authenticate(true, username(), "Network-test-password_123")
            SessionStore(sandbox.context).save(session)
            AuthTestBridge.setOffline(true)
            ActivityScenario.launch(MainActivity::class.java).use {
                awaitTag("home_start")
                val activity = sandbox.awaitActivity<MainActivity>()
                instrumentation.runOnMainSync {
                    val gate = MainActivity::class.java.getDeclaredField("authGate").apply { isAccessible = true }.get(activity) as OnlineAuthGate
                    gate.logout()
                }
                awaitTag("auth_submit")
                val sessions = SessionStore(sandbox.context)
                assertNull(sessions.load())
                assertEquals(session.token, sessions.pendingLogout())
                AuthTestBridge.setOffline(false)
                api.flushLogout(sessions)
                assertNull(sessions.pendingLogout())
                try { api.verify(session); fail("Offline logout was not revoked") } catch (failure: AuthApi.Failure) { assertEquals(401, failure.status) }
            }
        }
    }
    @Test fun registrationRealLearningLogoutAndReloginKeepAccountRecords() {
        Sandbox().use { sandbox ->
            val name = username()
            ActivityScenario.launch(LoginActivity::class.java).use {
                awaitTag("auth_submit")
                tap("auth_switch")
                fill("auth_username", name); fill("auth_password", "Network-test-password_123"); fill("auth_confirmation", "Network-test-password_123")
                tap("auth_submit")
                awaitTag("home_start")
                val first = sandbox.awaitActivity<MainActivity>()
                val data = store(first)
                instrumentation.runOnMainSync { first.getPreferences(0).edit().putBoolean("onboarded", true).commit() }
                compose.onNodeWithTag("home_nav_Libraries").performClick()
                onView(withText("SQL 基础知识")).perform(scrollTo(), click())
                onView(withText("开始自适应练习")).perform(scrollTo(), click())
                onView(allOf(isAssignableFrom(android.widget.RadioButton::class.java), withText(startsWith("A   ")))).perform(scrollTo(), click())
                onView(withText("确定")).perform(scrollTo(), click())
                onView(withText("提交答案")).perform(click())
                assertEquals(1L, data.count("SELECT COUNT(*) n FROM attempt"))
                val oldSession = SessionStore(sandbox.context).load()!!
                pressBack(); onView(withText("保存并退出")).perform(click())
                compose.onNodeWithTag("home_nav_Profile").performClick()
                onView(withText("退出登录  ›")).perform(scrollTo(), click())
                onView(withText("确认")).perform(click())
                awaitTag("auth_submit")
                assertNull(SessionStore(sandbox.context).load())
                fill("auth_username", name); fill("auth_password", "Network-test-password_123"); tap("auth_submit")
                awaitTag("home_start")
                val reopened = sandbox.awaitActivity<MainActivity>()
                assertEquals(1L, store(reopened).count("SELECT COUNT(*) n FROM attempt"))
                assertTrue(store(reopened).count("SELECT COUNT(*) n FROM state_change") > 0)
                try { api.verify(oldSession); fail("Logout did not revoke token") } catch (failure: AuthApi.Failure) { assertEquals(401, failure.status) }
            }
        }
    }
}
