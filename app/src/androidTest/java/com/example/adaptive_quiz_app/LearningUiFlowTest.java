package com.example.adaptive_quiz_app;

import android.content.Context;
import android.content.SharedPreferences;
import android.widget.RadioButton;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.example.adaptive_quiz_app.learning.LearningStore;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.HashSet;
import java.util.Set;
import static androidx.test.espresso.Espresso.onView;
import static androidx.test.espresso.Espresso.onData;
import static androidx.test.espresso.Espresso.pressBack;
import static androidx.test.espresso.action.ViewActions.*;
import static androidx.test.espresso.assertion.ViewAssertions.*;
import static androidx.test.espresso.matcher.ViewMatchers.*;
import static org.hamcrest.Matchers.*;
import static org.junit.Assert.*;

/** Real Activity, isolated database: test submissions do not become user learning evidence. */
@RunWith(AndroidJUnit4.class)
public class LearningUiFlowTest {
    @org.junit.Rule public final ComposeTestDriver compose=new ComposeTestDriver();
    private static void call(MainActivity a,String name,Class<?> parameter,Object value) {
        try {Method m=parameter==null?MainActivity.class.getDeclaredMethod(name):MainActivity.class.getDeclaredMethod(name,parameter);m.setAccessible(true);if(parameter==null)m.invoke(a);else m.invoke(a,value);}
        catch(Exception e){throw new AssertionError(e);}
    }
    private static void shellAndWait(String command) throws Exception {
        android.os.ParcelFileDescriptor descriptor=InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand(command);
        try(java.io.InputStream input=new android.os.ParcelFileDescriptor.AutoCloseInputStream(descriptor)) {
            byte[] buffer=new byte[256];while(input.read(buffer)!=-1) { /* EOF means command finished. */ }
        }
    }
    /** Every Activity lifecycle, including initialization, is isolated from user records. */
    private static final class IsolatedActivity implements AutoCloseable {
        final Context target=InstrumentationRegistry.getInstrumentation().getTargetContext();
        MainBridgeSandbox sandbox;
        LearningStore store;
        ActivityScenario<MainActivity> scenario;
        IsolatedActivity(boolean onboarded) throws Exception {
            try {
                sandbox=new MainBridgeSandbox(onboarded);
                shellAndWait("input keyevent KEYCODE_WAKEUP");
                shellAndWait("wm dismiss-keyguard");
                scenario=ActivityScenario.launch(MainActivity.class);
                scenario.moveToState(androidx.lifecycle.Lifecycle.State.RESUMED);
                store=sandbox.store(sandbox.awaitMainScreen("home",12000));
                scenario.onActivity(a->a.getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON));
            } catch(Exception|AssertionError error) {close();throw error;}
        }
        SharedPreferences learningPreferences() {
            java.util.concurrent.atomic.AtomicReference<SharedPreferences> result=new java.util.concurrent.atomic.AtomicReference<>();
            scenario.onActivity(a->result.set(a.getPreferences(Context.MODE_PRIVATE)));
            return result.get();
        }
        @Override public void close() {
            try {
                if(scenario!=null)scenario.close();
            } finally {
                if(sandbox!=null)sandbox.close();
            }
        }
    }
    @Test public void answerResumeSpellingAndReport() throws Exception {
        try(IsolatedActivity fixture=new IsolatedActivity(true)) {
            Context target=fixture.target;LearningStore store=fixture.store;ActivityScenario<MainActivity> scenario=fixture.scenario;
            store.insert("library",LearningStore.obj("name","空库验证","subject","测试","kind","question"));
            scenario.onActivity(a->call(a,"home",int.class,0));
            onView(withText("知识库为空，先添加或导入内容。")).check(doesNotExist());
            compose.openStudyAction("home_today_plans");
            onView(withText("知识库为空，先添加或导入内容。")).perform(scrollTo()).check(matches(isDisplayed()));
            scenario.onActivity(a->call(a,"library",long.class,store.one("SELECT id FROM library WHERE kind='question' ORDER BY id LIMIT 1").optLong("id")));
            onView(withText("开始自适应练习")).perform(scrollTo(),click());
            JSONObject session=store.one("SELECT * FROM session ORDER BY id DESC LIMIT 1");long sid=session.getLong("id");long item=new org.json.JSONArray(session.getString("plan")).getLong(0);
            onView(withText(store.one("SELECT explanation FROM item WHERE id=?",""+item).getString("explanation"))).check(doesNotExist());
            onView(allOf(isAssignableFrom(RadioButton.class),withText(startsWith("A   ")))).perform(scrollTo(),click());
            onView(withText("提交答案")).check(matches(allOf(isDisplayed(),not(isEnabled()))));
            onView(withText("确定")).perform(scrollTo(),click());capture(target,"ui-quiz-selected");onView(withText("提交答案")).check(matches(isDisplayed())).perform(click());
            onView(withText("解析")).perform(scrollTo()).check(matches(isDisplayed()));
            assertEquals(1,store.count("SELECT COUNT(*) n FROM attempt"));
            pressBack();onView(withText("保存并退出")).perform(click());
            compose.clickTag("home_start");
            onView(withText("下一题／完成本轮")).check(matches(isDisplayed())).perform(click());
            assertEquals(1,store.one("SELECT position FROM session WHERE id=?",""+sid).getInt("position"));
            assertEquals(1,store.count("SELECT COUNT(*) n FROM attempt"));
            pressBack();onView(withText("保存并退出")).perform(click());
            scenario.onActivity(a->call(a,"library",long.class,store.one("SELECT id FROM library WHERE kind='word'").optLong("id")));
            onView(withText(startsWith("回忆测试"))).perform(scrollTo(),click());
            onView(withHint("请输入英文单词")).perform(replaceText("wrongspelling"),closeSoftKeyboard());
            onView(withText("犹豫")).perform(scrollTo(),click());onView(withText("提交答案")).check(matches(isDisplayed())).perform(click());
            JSONObject attempt=store.one("SELECT * FROM attempt WHERE skill='recall'");assertEquals(0,attempt.getInt("correct"));
            assertEquals(0,store.state(attempt.getLong("item_id"),"recognition").getInt("seen"));
            scenario.onActivity(a->call(a,"library",long.class,store.one("SELECT id FROM library WHERE kind='word'").optLong("id")));
            onView(withText("开始单词学习")).perform(scrollTo(),click());
            onView(withText("有多大把握？")).check(matches(withEffectiveVisibility(Visibility.GONE)));
            onView(withText("提交答案")).check(matches(not(isEnabled())));
            capture(target,"study-initial");
            JSONObject recognitionSession=store.one("SELECT * FROM session ORDER BY id DESC LIMIT 1");
            long recognitionItem=new org.json.JSONArray(recognitionSession.getString("plan")).getLong(0);
            String meaning=store.one("SELECT meaning FROM item WHERE id=?",""+recognitionItem).getString("meaning");
            onView(allOf(withText(meaning),withParent(isAssignableFrom(android.widget.LinearLayout.class)))).perform(scrollTo(),click());
            onView(withText("提交答案")).check(matches(not(isEnabled())));
            onView(withContentDescription("学习设置")).perform(click());
            onView(withText("完成")).perform(click());
            onView(withText("确定")).perform(scrollTo(),click());
            capture(target,"study-selected");
            onView(withText("提交答案")).check(matches(isDisplayed())).perform(click());
            onView(withText("回答正确 · 记得很好")).perform(scrollTo()).check(matches(isDisplayed()));
            JSONObject recognitionAttempt=store.one("SELECT * FROM attempt WHERE session_id=?",""+recognitionSession.getLong("id"));
            assertEquals(1,recognitionAttempt.getInt("correct"));
            capture(target,"study-correct");
            pressBack();onView(withText("保存并退出")).perform(click());
            scenario.onActivity(a->{try{Field f=MainActivity.class.getDeclaredField("sessionId");f.setAccessible(true);f.setLong(a,recognitionSession.optLong("id"));call(a,"practice",null,null);}catch(Exception e){throw new AssertionError(e);}});
            onView(withText("下一词")).check(matches(isDisplayed())).perform(click());
            assertEquals(1,store.one("SELECT position FROM session WHERE id=?",""+recognitionSession.getLong("id")).getInt("position"));
            scenario.onActivity(a->call(a,"home",int.class,2));
            onView(withText("学习报告")).check(matches(isDisplayed()));
            capture(target,"ui-report");
            scenario.onActivity(a->call(a,"library",long.class,store.one("SELECT id FROM library WHERE kind='question' ORDER BY id LIMIT 1").optLong("id")));
            onView(withText(startsWith("知识点与学习摘要"))).perform(scrollTo(),click());
            onView(withHint("搜索知识点、摘要、示例或记忆方法")).perform(replaceText("unlikelykeyword"),closeSoftKeyboard());
            onView(withText("未找到匹配内容，请查阅参考资料或补充知识点。")).check(matches(isDisplayed()));
            for(int i=0;i<25;i++)store.insert("library",LearningStore.obj("name",String.format(java.util.Locale.ROOT,"测试库 %02d",i),"subject","扩展学科","kind","question"));
            scenario.onActivity(a->call(a,"home",int.class,1));
            capture(target,"ui-libraries");
            onView(withText("测试库 00")).check(doesNotExist());
            onView(withText("扩展学科 · 25 个知识库")).perform(scrollTo(),click());
            onView(withText("测试库 00")).perform(scrollTo()).check(matches(isDisplayed()));
            onView(withText("测试库 24")).check(doesNotExist());
            onView(withText(startsWith("下一页"))).perform(scrollTo(),click());
            onView(withText("测试库 10")).perform(scrollTo()).check(matches(isDisplayed()));
            onView(withHint("搜索知识库、学科或内容")).perform(scrollTo(),replaceText("测试库 24"),closeSoftKeyboard());
            onView(allOf(withText("测试库 24"),not(isAssignableFrom(android.widget.EditText.class)))).perform(scrollTo()).check(matches(isDisplayed()));
            long questionLibrary=store.one("SELECT id FROM library WHERE kind='question' ORDER BY id LIMIT 1").getLong("id");
            JSONObject template=store.one("SELECT * FROM item WHERE library_id=? ORDER BY id LIMIT 1",""+questionLibrary);
            for(int i=0;i<25;i++) {
                JSONObject extra=new JSONObject(template.toString());extra.remove("id");extra.put("prompt",String.format(java.util.Locale.ROOT,"扩展题 %02d",i));store.insert("item",extra);
            }
            scenario.onActivity(a->call(a,"library",long.class,questionLibrary));
            onView(withText("＋ 添加题目  ›")).check(doesNotExist());
            onView(withText("管理")).check(doesNotExist());
            scenario.onActivity(a->call(a,"manageLibrary",long.class,questionLibrary));
            onView(withText("＋ 添加题目  ›")).perform(scrollTo()).check(matches(isDisplayed()));
            onView(withText("开始自适应练习")).check(doesNotExist());
            scenario.onActivity(a->call(a,"library",long.class,questionLibrary));
            onView(withText("内容")).perform(scrollTo(),click());
            onView(withText("内容维护  ›")).check(doesNotExist());
            onView(withText("按知识点查看内容  ›")).perform(scrollTo(),click());
            onView(withText("全部内容  ›")).perform(scrollTo(),click());
            onView(withText("扩展题 24")).check(doesNotExist());
            onView(withText(startsWith("下一页"))).perform(scrollTo(),click());
            onView(withText("扩展题 04")).perform(scrollTo()).check(matches(isDisplayed()));
            onView(withText(startsWith("下一页"))).perform(scrollTo(),click());
            onView(withText("扩展题 24")).perform(scrollTo()).check(matches(isDisplayed()));
            onView(withHint("搜索题干、单词或释义")).perform(replaceText("unlikelykeyword"),closeSoftKeyboard());
            onView(withText("当前没有内容。")).check(matches(isDisplayed()));
            pressBack();
            onView(withText("内容")).check(matches(isSelected()));
            scenario.onActivity(a->call(a,"home",int.class,3));capture(target,"ui-profile");
        }
    }
    @Test public void onboardingCanSkipReplayAndKeepsLearningSeparateFromManagement() throws Exception {
        try(IsolatedActivity fixture=new IsolatedActivity(false)) {
            LearningStore store=fixture.store;ActivityScenario<MainActivity> scenario=fixture.scenario;
            compose.assertDisplayed("home_greeting");
            compose.clickTag("home_start");
            onView(withText("认识知学伴 · 1 / 3")).check(matches(isDisplayed()));
            onView(withText("跳过引导  ›")).perform(scrollTo(),click());
            compose.assertDisplayed("home_start");
            assertTrue(fixture.learningPreferences().getBoolean("onboarded",false));
            assertEquals(0,store.count("SELECT COUNT(*) n FROM attempt"));

            scenario.onActivity(a->call(a,"home",int.class,3));
            onView(withText("使用帮助  ›")).perform(scrollTo(),click());
            onView(withText("重新查看三步引导  ›")).perform(scrollTo(),click());
            onView(withText("下一步：选择学习目标")).perform(scrollTo(),click());
            onView(withText("认识知学伴 · 2 / 3")).check(matches(isDisplayed()));
            onView(withText("跳过引导  ›")).perform(scrollTo(),click());
            onView(withText("我的学习空间")).check(matches(isDisplayed()));
            assertEquals(0,store.count("SELECT COUNT(*) n FROM attempt"));

            scenario.onActivity(a->call(a,"home",int.class,1));
            onView(withText("＋ 新建知识库")).check(doesNotExist());
            onView(withText("导入题库／词表 JSON  ›")).check(doesNotExist());
            onView(withText("SQL 基础知识")).perform(scrollTo(),click());
            onView(withText("学习")).check(matches(isSelected()));
            onView(withText("管理")).check(doesNotExist());
            onView(withText("＋ 添加题目  ›")).check(doesNotExist());
            onView(withText("内容")).perform(click());
            onView(withText("内容维护  ›")).check(doesNotExist());
            onView(withText("按知识点查看内容  ›")).perform(scrollTo(),click());
            onView(withText("全部内容  ›")).perform(scrollTo(),click());
            onView(withText(startsWith("编辑"))).check(doesNotExist());
            onView(withText(startsWith("归档"))).check(doesNotExist());

            scenario.onActivity(a->call(a,"home",int.class,3));
            onView(withText("题库管理  ›")).perform(scrollTo(),click());
            onView(withText("＋ 新建知识库")).perform(scrollTo()).check(matches(isDisplayed()));
            onView(withText("SQL 基础知识")).perform(scrollTo(),click());
            onView(withText("＋ 添加题目  ›")).perform(scrollTo()).check(matches(isDisplayed()));
            onView(withText("内容维护  ›")).perform(scrollTo()).check(matches(isDisplayed()));
            onView(withText("开始自适应练习")).check(doesNotExist());
        }
    }
    @Test public void diagnosticUsesRealAnswersAndProducesKnowledgeEvidence() throws Exception {
        try(IsolatedActivity fixture=new IsolatedActivity(false)) {
            LearningStore store=fixture.store;ActivityScenario<MainActivity> scenario=fixture.scenario;
            compose.clickTag("home_start");
            onView(withText("下一步：选择学习目标")).perform(scrollTo(),click());
            onView(allOf(isAssignableFrom(android.widget.Spinner.class),withSpinnerText("全部学科"))).perform(click());
            onData(allOf(is(instanceOf(String.class)),is("计算机"))).perform(click());
            onView(withText("下一步：初始能力测试")).perform(scrollTo(),click());
            onView(withText("认识知学伴 · 3 / 3")).check(matches(isDisplayed()));
            onView(withText("开始初始测试")).perform(scrollTo(),click());
            JSONObject session=store.one("SELECT * FROM session ORDER BY id DESC LIMIT 1");
            long sessionId=session.getLong("id");org.json.JSONArray plan=new org.json.JSONArray(session.getString("plan"));
            assertEquals("diagnostic",session.getString("strategy"));
            assertEquals(6,plan.length());
            assertEquals("计算机",fixture.learningPreferences().getString("focusSubject",""));
            Set<Long> unique=new HashSet<>();for(int i=0;i<plan.length();i++)assertTrue(unique.add(plan.getLong(i)));
            onView(withText("为什么推荐？  ›")).perform(scrollTo(),click());
            onView(withText("为什么推荐？")).check(matches(isDisplayed()));
            onView(withText(containsString("初始测试"))).check(matches(isDisplayed()));
            onView(withText("知道了")).perform(click());
            for(int position=0;position<plan.length();position++) {
                JSONObject item=store.one("SELECT * FROM item WHERE id=?",""+plan.getLong(position));
                // Alternate actual correct/incorrect answers, so suggestions have observed weak evidence.
                String answer=item.getString("answer");
                String response=position%2==0?answer:("A".equals(answer)?"B":"A");
                onView(allOf(isAssignableFrom(RadioButton.class),withText(startsWith(response+"   ")))).perform(scrollTo(),click());
                onView(withText("确定")).perform(scrollTo(),click());
                onView(withText("提交答案")).check(matches(isDisplayed())).perform(click());
                assertEquals(position+1,store.count("SELECT COUNT(*) n FROM attempt WHERE session_id=?",""+sessionId));
                onView(withText("下一题／完成本轮")).check(matches(isDisplayed())).perform(click());
            }
            assertEquals(1,store.one("SELECT finished FROM session WHERE id=?",""+sessionId).getInt("finished"));
            assertEquals(3,store.count("SELECT COUNT(*) n FROM attempt WHERE session_id=? AND correct=1",""+sessionId));
            assertTrue(store.count("SELECT COUNT(*) n FROM state WHERE skill='knowledge' AND seen>0")>0);
            assertEquals(6,store.count("SELECT COUNT(*) n FROM state_change sc JOIN attempt a ON a.id=sc.attempt_id WHERE a.session_id=?",""+sessionId));
            assertTrue(store.count("SELECT COUNT(*) n FROM state_change sc JOIN attempt a ON a.id=sc.attempt_id WHERE a.session_id=? AND sc.before_value<>sc.after_value AND sc.posterior IS NOT NULL",""+sessionId)>0);
            onView(withText("本轮练习报告")).check(matches(isDisplayed()));
            onView(withText("初始学习建议")).perform(scrollTo()).check(matches(isDisplayed()));
            capture(fixture.target,"system-diagnostic-report");
            scenario.onActivity(a->call(a,"home",int.class,2));
            onView(withText("学习报告")).check(matches(isDisplayed()));
            onView(withText("掌握概率变化趋势")).perform(scrollTo()).check(matches(isDisplayed()));
            assertEquals(6,store.count("SELECT COUNT(*) n FROM attempt"));
            assertEquals(3,store.count("SELECT COUNT(*) n FROM attempt WHERE correct=1"));
        }
    }
    @Test public void singleMeaningFallsBackToRecallAndAllWordSkillsCountTowardToday() throws Exception {
        try(IsolatedActivity fixture=new IsolatedActivity(true)) {
            LearningStore store=fixture.store;ActivityScenario<MainActivity> scenario=fixture.scenario;
            org.json.JSONArray words=store.rows("SELECT * FROM item WHERE kind='word' ORDER BY id LIMIT 2");
            store.getWritableDatabase().execSQL("UPDATE library SET archived=1");
            long library=store.insert("library",LearningStore.obj("name","单释义边界词库","subject","边界测试","kind","word"));
            for(int i=0;i<words.length();i++) {
                JSONObject word=new JSONObject(words.getJSONObject(i).toString());word.remove("id");
                word.put("library_id",library);word.put("meaning","同一测试释义");store.insert("item",word);
            }
            scenario.onActivity(a->call(a,"library",long.class,library));
            onView(withText("开始单词学习")).perform(scrollTo(),click());
            JSONObject recall=store.one("SELECT * FROM session ORDER BY id DESC LIMIT 1");
            assertEquals("recall",recall.getString("mode"));
            assertEquals(0,store.count("SELECT COUNT(*) n FROM session WHERE mode='recognition'"));
            long recallItem=new org.json.JSONArray(recall.getString("plan")).getLong(0);
            String recallAnswer=store.one("SELECT prompt FROM item WHERE id=?",""+recallItem).getString("prompt");
            onView(withHint("请输入英文单词")).perform(replaceText(recallAnswer),closeSoftKeyboard());
            onView(withText("确定")).perform(scrollTo(),click());
            onView(withText("提交答案")).perform(click());
            assertEquals(1,store.count("SELECT COUNT(*) n FROM attempt WHERE skill='recall' AND correct=1"));
            pressBack();onView(withText("保存并退出")).perform(click());
            compose.assertText("home_progress","1 / 2");

            scenario.onActivity(a->call(a,"library",long.class,library));
            onView(withText("语境应用 · 例句填空  ›")).perform(scrollTo(),click());
            JSONObject context=store.one("SELECT * FROM session ORDER BY id DESC LIMIT 1");
            assertEquals("context",context.getString("mode"));
            long contextItem=new org.json.JSONArray(context.getString("plan")).getLong(0);
            String contextAnswer=store.one("SELECT prompt FROM item WHERE id=?",""+contextItem).getString("prompt");
            onView(withHint("请输入英文单词")).perform(replaceText(contextAnswer),closeSoftKeyboard());
            onView(withText("确定")).perform(scrollTo(),click());
            onView(withText("提交答案")).perform(click());
            assertEquals(1,store.count("SELECT COUNT(*) n FROM attempt WHERE skill='context' AND correct=1"));
            pressBack();onView(withText("保存并退出")).perform(click());
            compose.assertText("home_progress","2 / 2");
            compose.openStudyAction("home_today_plans");
            onView(withText("今日任务已完成 ✓")).perform(scrollTo()).check(matches(isDisplayed()));
        }
    }
    @Test public void unavailableApplicationTaskDoesNotBlockTodayLearning() throws Exception {
        try(IsolatedActivity fixture=new IsolatedActivity(true)) {
            LearningStore store=fixture.store;ActivityScenario<MainActivity> scenario=fixture.scenario;
            JSONObject template=store.one("SELECT * FROM item WHERE kind='question' ORDER BY id LIMIT 1");
            store.getWritableDatabase().execSQL("UPDATE library SET archived=1");
            long library=store.insert("library",LearningStore.obj("name","只有基础题","subject","边界测试","kind","question"));
            JSONObject item=new JSONObject(template.toString());item.remove("id");item.put("library_id",library);item.put("difficulty",1);
            store.insert("item",item);
            long source=store.start(library,"question",1,"diagnostic",0);
            store.edit("session",source,LearningStore.obj("finished",1));
            long now=System.currentTimeMillis();
            store.insert("task",LearningStore.obj("source_session",source,"library_id",library,"point_id",0,"stage","basic","due_at",now-2000,"completed",1));
            long blocked=store.insert("task",LearningStore.obj("source_session",source,"library_id",library,"point_id",0,"stage","application","due_at",now-1000,"completed",0));
            scenario.onActivity(a->call(a,"home",int.class,0));
            compose.clickTag("home_start");
            onView(withText("提交答案")).check(matches(allOf(isDisplayed(),not(isEnabled()))));
            JSONObject active=store.one("SELECT * FROM session WHERE finished=0 ORDER BY id DESC LIMIT 1");
            assertNotNull(active);assertEquals(library,active.getLong("library_id"));
            assertEquals("diagnostic",active.getString("strategy"));
            assertEquals(0,store.one("SELECT completed FROM task WHERE id=?",""+blocked).getInt("completed"));
            assertEquals(0,store.count("SELECT COUNT(*) n FROM attempt"));
        }
    }
    @Test public void longStudyWordWrapsWithoutLosingText() throws Exception {
        try(IsolatedActivity fixture=new IsolatedActivity(true)) {
            String word="pneumonoultramicroscopicsilicovolcanoconiosis";
            fixture.scenario.onActivity(a->a.setContentView(new com.example.adaptive_quiz_app.learning.WordStudyView(
                    a,"排版验证词库",word,"",0,1,java.util.Arrays.asList("第一种释义","第二种释义"),null,
                    "第一种释义","A readable example.",false,new com.example.adaptive_quiz_app.learning.WordStudyView.Actions() {
                        public void speak(){} public void exit(){} public void submit(String value,int confidence){}
                        public void next(){} public void star(){}
                    })));
            onView(withText(word)).perform(scrollTo()).check(matches(isDisplayed())).check((view,error)->{
                if(error!=null)throw error;
                android.widget.TextView term=(android.widget.TextView)view;
                android.text.Layout layout=term.getLayout();
                assertNotNull(layout);
                assertTrue("Long words should wrap instead of shrinking",layout.getLineCount()>1);
                assertEquals(word.length(),layout.getLineEnd(layout.getLineCount()-1));
                for(int line=0;line<layout.getLineCount();line++)assertEquals(0,layout.getEllipsisCount(line));
                assertTrue("All lines fit the text container",term.getHeight()-term.getCompoundPaddingTop()-term.getCompoundPaddingBottom()>=layout.getHeight());
            });
            capture(fixture.target,"typography-long-word");
        }
    }
    private static void capture(Context context,String name) throws Exception {
        InstrumentationRegistry.getInstrumentation().waitForIdleSync();
        InstrumentationRegistry.getInstrumentation().getUiAutomation().waitForIdle(100,3000);
        android.graphics.Bitmap screenshot=InstrumentationRegistry.getInstrumentation().getUiAutomation().takeScreenshot();
        try(java.io.FileOutputStream output=new java.io.FileOutputStream(new java.io.File(context.getExternalFilesDir(null),name+".png"))){
            screenshot.compress(android.graphics.Bitmap.CompressFormat.PNG,100,output);
        }finally{screenshot.recycle();}
    }
}
