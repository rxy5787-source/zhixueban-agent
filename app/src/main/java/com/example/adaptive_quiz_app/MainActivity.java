package com.example.adaptive_quiz_app;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.SystemClock;
import android.speech.tts.TextToSpeech;
import android.view.View;
import android.view.Gravity;
import android.widget.*;
import androidx.activity.OnBackPressedCallback;
import androidx.core.content.FileProvider;
import com.example.adaptive_quiz_app.learning.*;
import com.example.adaptive_quiz_app.auth.*;
import com.example.adaptive_quiz_app.ui.home.ComposeHomeUi;
import com.example.adaptive_quiz_app.ui.TypeScale;
import com.example.adaptive_quiz_app.ai.AiGenerationController;
import static com.example.adaptive_quiz_app.ui.TypeScale.Role.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.*;
public class MainActivity extends LearningUi  {
    public static final String EXTRA_HOME_ACTION="com.example.adaptive_quiz_app.HOME_ACTION";
    private static final String STATE_HOME_ACTION_CONSUMED="homeActionConsumed";
    private boolean homeActionConsumed;
    private LearningStore db;
    private OnlineAuthGate authGate;
    private AuthSession accountSession;
    private AccountScope accountScope;
    private AiGenerationController aiController;
    private String aiOrigin="libraries";
    private long aiOriginLibrary;
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private TextToSpeech tts;
    private String screen="today",fileAction="";
    private long libraryId,sessionId,referencePoint,startedAt,reportLibraryId;
    private int reportDays=30;
    private boolean sessionReportFromReport;
    private boolean busy,ttsReady,homeDataReady;
    private int librarySection=0;
    private final Set<String> expandedSubjects=new HashSet<>();
    private final Set<String> collapsedSubjects=new HashSet<>();
    private final Map<String,Integer> subjectPages=new HashMap<>();
    private String itemFilter="all",itemQuery="";
    private long itemPoint=-1;
    private int itemOffset=0,pointOffset=0;
    private int subjectOffset=0;
    private String librarySearch="";
    private boolean managementContext,onboardingReplay;
    private int onboardingStep;
    private String onboardingSubject="",onboardingGoal="打好基础";
    private final java.text.DateFormat date=new SimpleDateFormat("MM-dd HH:mm",Locale.CHINA);
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        authGate=new OnlineAuthGate(this,session->{
            accountSession=session;
            if(session!=null)accountScope=new AccountScope(getBaseContext(),session.userId);
            initializeLearning(saved);
        });
        authGate.start();
    }
    private void initializeLearning(Bundle saved) {
        homeActionConsumed=saved!=null&&saved.getBoolean(STATE_HOME_ACTION_CONSUMED,false);
        if(homeActionConsumed)getIntent().removeExtra(EXTRA_HOME_ACTION);
        db=new LearningStore(accountScope==null?this:accountScope.databaseContext());
        if(saved!=null) {
            tab=saved.getInt("tab",0);
            if(tab==2)tab=0;
            libraryId=saved.getLong("library");
            aiOrigin=saved.getString("aiOrigin","libraries");aiOriginLibrary=saved.getLong("aiOriginLibrary");
            referencePoint=saved.getLong("referencePoint");
            fileAction=saved.getString("fileAction","");
            librarySection=saved.getInt("librarySection",0);
            managementContext=saved.getBoolean("management",false);
            onboardingStep=saved.getInt("onboardingStep",0);
            onboardingReplay=saved.getBoolean("onboardingReplay",false);
            onboardingSubject=saved.getString("onboardingSubject","");
            onboardingGoal=saved.getString("onboardingGoal","打好基础");
            ArrayList<String> expanded=saved.getStringArrayList("expandedSubjects");
            if(expanded!=null)expandedSubjects.addAll(expanded);
            ArrayList<String> collapsed=saved.getStringArrayList("collapsedSubjects");
            if(collapsed!=null)collapsedSubjects.addAll(collapsed);
            librarySearch=saved.getString("librarySearch","");subjectOffset=saved.getInt("subjectOffset",0);
            Bundle pages=saved.getBundle("subjectPages");if(pages!=null)for(String key:pages.keySet())subjectPages.put(key,pages.getInt(key));
        }
        androidx.appcompat.app.AppCompatDelegate.setDefaultNightMode(androidx.appcompat.app.AppCompatDelegate.MODE_NIGHT_NO);
        ComposeHomeUi.showLoading(this);
        tts=new TextToSpeech(this,status-> {
            ttsReady=status==TextToSpeech.SUCCESS;
            if(ttsReady)tts.setLanguage(Locale.US);
        }
        );
        getOnBackPressedDispatcher().addCallback(this,new OnBackPressedCallback(true) {
            public void handleOnBackPressed() {
                back();
            }
        }
        );
        worker.execute(()-> {
            try {
                db.seed();
                runOnUiThread(()-> {
                    if(isFinishing()||isDestroyed())return;
                    homeDataReady=true;
                    if(saved!=null&&saved.getLong("session")>0&&"practice".equals(saved.getString("screen"))) {
                        sessionId=saved.getLong("session");
                        practice();
                    }
                    else if(saved!=null&&"welcome".equals(saved.getString("screen")))onboarding(onboardingStep);
                    else if(saved!=null&&"manageLibrary".equals(saved.getString("screen"))&&libraryId>0)manageLibrary(libraryId);
                    else if(saved!=null&&"library".equals(saved.getString("screen"))&&libraryId>0)librarySection(libraryId,librarySection);
                    else if(saved!=null&&"report".equals(saved.getString("screen")))report();
                    else if(saved!=null&&"ai".equals(saved.getString("screen")))openAi(libraryId,saved.getBundle("aiDraft"));
                    else {
                        boolean restoring=saved!=null&&!"today".equals(saved.getString("screen"));
                        if(restoring||!openRequestedHomeAction())home(saved==null?0:saved.getInt("tab",0));
                    }
                }
                );
            }
            catch(Exception e) {
                runOnUiThread(()-> {
                    page("加载失败",false,false);
                    note(e.getMessage());
                    button("重试",()->recreate());
                }
                );
            }
        }
        );
    }
    @Override protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        out.putBoolean(STATE_HOME_ACTION_CONSUMED,homeActionConsumed);
        out.putLong("session",sessionId);
        out.putString("screen",screen);
        out.putString("aiOrigin",aiOrigin);out.putLong("aiOriginLibrary",aiOriginLibrary);
        if("ai".equals(screen)&&aiController!=null)out.putBundle("aiDraft",aiController.saveState());
        out.putLong("library",libraryId);
        out.putLong("referencePoint",referencePoint);
        out.putString("fileAction",fileAction);
        out.putInt("librarySection",librarySection);
        out.putBoolean("management",managementContext);
        out.putInt("onboardingStep",onboardingStep);
        out.putBoolean("onboardingReplay",onboardingReplay);
        out.putString("onboardingSubject",onboardingSubject);
        out.putString("onboardingGoal",onboardingGoal);
        out.putStringArrayList("expandedSubjects",new ArrayList<>(expandedSubjects));
        out.putStringArrayList("collapsedSubjects",new ArrayList<>(collapsedSubjects));
        out.putInt("tab",tab);out.putString("librarySearch",librarySearch);out.putInt("subjectOffset",subjectOffset);
        Bundle pages=new Bundle();for(Map.Entry<String,Integer> entry:subjectPages.entrySet())pages.putInt(entry.getKey(),entry.getValue());out.putBundle("subjectPages",pages);
    }
    @Override protected void onResume() {
        super.onResume();
        if(authGate!=null)authGate.resume();
        if(homeDataReady&&"home".equals(screen)&&tab==0&&!busy)today();
    }
    @Override protected void onPause(){if(authGate!=null)authGate.pause();super.onPause();}
    @Override public android.content.SharedPreferences getPreferences(int mode) {
        return accountScope==null?super.getPreferences(mode):getSharedPreferences(accountScope.preferencesName(),mode);
    }
    @Override public File getFilesDir(){return accountScope==null?super.getFilesDir():accountScope.filesDirectory();}
    @Override protected String profileDescription(){return accountSession==null?"学习记录保存在本机":"账号："+accountSession.username;}
    @Override protected void onDestroy() {
        if(aiController!=null)aiController.close();
        if(authGate!=null)authGate.close();
        super.onDestroy();
        if(tts!=null)tts.shutdown();
        if(db!=null)worker.execute(db::close);
        worker.shutdown();
    }
    private void page(String name,boolean secondary) {
        page(name,secondary,!secondary&&"home".equals(screen));
    }
    private int daily() {
        return getPreferences(MODE_PRIVATE).getInt("daily",10);
    }
    private long dayStart() {
        Calendar c=Calendar.getInstance();
        c.set(Calendar.HOUR_OF_DAY,0);
        c.set(Calendar.MINUTE,0);
        c.set(Calendar.SECOND,0);
        c.set(Calendar.MILLISECOND,0);
        return c.getTimeInMillis();
    }
    private String skillName(String s) {
        return s.equals("question")?"题目练习":s.equals("recognition")?"识别测试":s.equals("context")?"语境应用":"拼写回忆";
    }
    private String confidenceName(int c) {
        return c==2?"确定":c==1?"犹豫":"猜的";
    }
    private JSONObject currentLibrary() {
        return db.one("SELECT * FROM library WHERE id=?",""+libraryId);
    }
    private void welcome() {
        onboardingSubject=getPreferences(MODE_PRIVATE).getString("focusSubject","");
        onboardingGoal=getPreferences(MODE_PRIVATE).getString("learningGoal","打好基础");
        onboarding(0);
    }
    private String[] subjects(boolean includeAll) {
        JSONArray rows=db.rows("SELECT DISTINCT subject FROM library WHERE archived=0 ORDER BY subject");
        String[] names=new String[rows.length()+(includeAll?1:0)];
        if(includeAll)names[0]="全部学科";
        for(int i=0;i<rows.length();i++)names[i+(includeAll?1:0)]=rows.optJSONObject(i).optString("subject");
        return names;
    }
    private void selectValue(Spinner spinner,String value) {
        for(int i=0;i<spinner.getCount();i++)if(value.equals(spinner.getItemAtPosition(i).toString()))spinner.setSelection(i);
    }
    private void saveGoal(String subject,String goal) {
        getPreferences(MODE_PRIVATE).edit().putString("focusSubject",subject).putString("learningGoal",goal).apply();
    }
    private void onboarding(int step) {
        onboardingStep=step;screen="welcome";
        page("认识知学伴 · "+(step+1)+" / 3",false,false);
        progress(3,step+1);
        if(step==0) {
            learningIntro("每次练习，都更懂你的学习。","本地知识追踪 · 自适应练习");
            headline("知道学什么，也知道为什么。");
            card("先评估，再练习","用真实答题估计知识掌握概率，优先巩固薄弱与到期内容。",null);
            note("支持题库与英语单词三种能力。登录后可在会话有效期内离线学习，记录保存在手机；内置示例仅供演示。");
            button("下一步：选择学习目标",()->onboarding(1));
        } else if(step==1) {
            headline("这次，想把什么学得更好？");
            text("学习科目",BODY,INK);Spinner subject=spinner(subjects(true));selectValue(subject,onboardingSubject);
            text("学习目标",BODY,INK);Spinner goal=spinner(new String[]{"打好基础","巩固薄弱知识","备考提升"});selectValue(goal,onboardingGoal);
            note("科目用于今日计划优先安排，不会隐藏其他学科。");
            button("下一步：初始能力测试",()->{
                onboardingSubject=subject.getSelectedItem().toString();onboardingGoal=goal.getSelectedItem().toString();
                saveGoal(onboardingSubject,onboardingGoal);onboarding(2);
            });
            link("上一步",()->onboarding(0));
        } else {
            headline("用几道题，找到合适的起点。");
            JSONArray libs=db.rows("SELECT l.*,(SELECT COUNT(*) FROM item i WHERE i.library_id=l.id AND i.archived=0) available FROM library l WHERE l.archived=0 AND (?='' OR ?='全部学科' OR l.subject=?) ORDER BY l.id",onboardingSubject,onboardingSubject,onboardingSubject);
            if(libs.length()==0) {
                note("此科目还没有知识库。完成引导后可在“我的 → 题库管理”创建或导入内容。");
                button("完成引导，稍后测试",()->finishOnboarding());
            } else {
                String[] names=new String[libs.length()];for(int i=0;i<names.length;i++)names[i]=libs.optJSONObject(i).optString("name")+" · "+libs.optJSONObject(i).optInt("available")+" 条";
                Spinner selected=spinner(names);
                note("最多 6 道不重复题目，尽量覆盖不同知识点。题目不足按实际数量；小样本只生成初步建议。已有状态会继续积累，重看引导不会重置记录。");
                button("开始初始测试",()->{
                    JSONObject l=libs.optJSONObject(selected.getSelectedItemPosition());
                    if(l.optInt("available")==0){toast("此库暂无内容，请选择其他知识库或稍后导入");return;}
                    saveGoal(onboardingSubject,onboardingGoal);
                    getPreferences(MODE_PRIVATE).edit().putBoolean("onboarded",true).apply();onboardingReplay=false;managementContext=false;
                    libraryId=l.optLong("id");
                    String mode="word".equals(l.optString("kind"))?(db.count("SELECT COUNT(DISTINCT meaning) n FROM item WHERE library_id=? AND archived=0",""+libraryId)>1?"recognition":"recall"):"question";
                    start(mode,6,"diagnostic",0);
                });
            }
            link("上一步",()->onboarding(1));
        }
        link("跳过引导",()->finishOnboarding());
    }
    private void finishOnboarding() {
        getPreferences(MODE_PRIVATE).edit().putBoolean("onboarded",true).apply();
        boolean replay=onboardingReplay;onboardingReplay=false;
        if(!openRequestedHomeAction())home(replay?3:0);
    }
    private boolean openRequestedHomeAction() {
        if(homeActionConsumed||!getIntent().hasExtra(EXTRA_HOME_ACTION))return false;
        String action=getIntent().getStringExtra(EXTRA_HOME_ACTION);
        // Keep the original pending learn action until the existing onboarding is completed.
        if("learn".equals(action)&&!getPreferences(MODE_PRIVATE).getBoolean("onboarded",false)) {
            welcome();return true;
        }
        homeActionConsumed=true;
        getIntent().removeExtra(EXTRA_HOME_ACTION);
        if("learn".equals(action))quickLearn();
        else if("libraries".equals(action))home(1);
        else if("report".equals(action))home(2);
        else if("profile".equals(action))home(3);
        else return false;
        return true;
    }
    @Override protected void home(int which) {
        if(busy){toast("正在处理文件，请稍候");return;}
        managementContext=false;
        sessionId=0;
        // Retain legacy report actions as secondary routes, never as a selected bottom tab.
        if(which==2){report();return;}
        tab=which;
        screen="home";
        if(which==0)today();
        else if(which==1)libraries();
        else settings();
    }
    private void today() {
        JSONArray candidates=runnableTasks();
        int runnable=0;
        for(int i=0;i<candidates.length();i++)if(taskRunnable(candidates.optJSONObject(i)))runnable++;
        JSONObject summary=HomeSummaryReader.read(db,daily(),System.currentTimeMillis(),dueStates().length(),runnable);
        ComposeHomeUi.show(this,summary,action->{
            if(busy){toast("正在处理文件，请稍候");return;}
            switch(action) {
                case "learn":
                    if(getPreferences(MODE_PRIVATE).getBoolean("onboarded",false))quickLearn();
                    else welcome();
                    break;
                case "plans":todayPlans(0);break;
                case "tasks":taskPage(0);break;
                case "review":duePage();break;
                case "resume":resumeList(0);break;
                case "libraries":home(1);break;
                case "progress":case "report":home(2);break;
                case "profile":home(3);break;
                case "focus":
                    JSONObject weak=summary.optJSONObject("weak");
                    if(weak==null)home(2);
                    else {libraryId=weak.optLong("library_id");point(weak.optLong("id"));}
                    break;
            }
        });
    }
    /** Retained for comparison during migration; no launcher or navigation calls this page. */
    @SuppressWarnings("unused")
    private void legacyTodayDisabled() {
        page("知学伴",false);
        JSONArray sessions=db.rows("SELECT s.*,l.name FROM session s JOIN library l ON l.id=s.library_id WHERE s.finished=0 AND l.archived=0 ORDER BY s.id DESC");
        long doneToday=db.count("SELECT COUNT(*) n FROM attempt WHERE at>=?",""+dayStart());
        long tasks=db.count("SELECT COUNT(*) n FROM task t JOIN library l ON l.id=t.library_id WHERE t.completed=0 AND l.archived=0");
        note(new SimpleDateFormat("M月d日，EEEE",Locale.CHINA).format(new Date()));
        learningIntro("把一点点，变成进步。","今天，从一小段专注开始。");
        JSONArray goals=db.rows("SELECT l.id,l.kind,(SELECT COUNT(*) FROM item i WHERE i.library_id=l.id AND i.archived=0) available FROM library l WHERE l.archived=0");
        int target=0,completed=0;
        for(int i=0;i<goals.length();i++) {
            JSONObject goal=goals.optJSONObject(i);int planned=Math.min(daily(),goal.optInt("available"));target+=planned;
            String mode="word".equals(goal.optString("kind"))?"recognition":"question";
            completed+=Math.min(planned,(int)db.count("SELECT COUNT(*) n FROM attempt a JOIN session s ON s.id=a.session_id WHERE s.library_id=? AND a.at>=?",""+goal.optLong("id"),""+dayStart()));
        }
        dailyPlan(target,completed,tasks,doneToday,"开始今日学习",()->beginToday(),()->todayPlans(0),daily());
        String focus=getPreferences(MODE_PRIVATE).getString("focusSubject","全部学科"),goal=getPreferences(MODE_PRIVATE).getString("learningGoal","打好基础");
        note("学习目标："+focus+" · "+goal);
        if(sessions.length()>0)card("继续上次学习",sessions.optJSONObject(0).optString("name")+" · 点击上方主按钮恢复，已提交答案不会丢失。",null);
        heading("今日学习任务");
        card("按学习证据安排下一步",tasks+" 项阶段任务 · 到期内容优先\n主按钮会依次处理：续学、可执行复习、到期内容、今日新练习。",()->taskPage(0));
        heading("个性化推荐");
        JSONObject weak=db.one("SELECT p.id,p.library_id,p.name,s.mastery,s.seen FROM state s JOIN point p ON p.id=s.owner_id JOIN library l ON l.id=p.library_id WHERE s.skill='knowledge' AND s.seen>0 AND p.archived=0 AND l.archived=0 ORDER BY s.mastery,p.id LIMIT 1");
        if(weak!=null) {
            card(weak.optString("name"),"掌握概率估计 "+percent(weak.optDouble("mastery"))+" · "+weak.optInt("seen")+" 次证据\n点击查看依据与知识点，再决定是否专项练习。",()->{
                libraryId=weak.optLong("library_id");point(weak.optLong("id"));
            });
        } else note("待评估：完成初始测试或练习后，将根据真实作答推荐巩固内容。");
        long due=dueStates().length();
        heading("待复习知识点与词汇");
        if(due>0)card(due+" 项状态已到期","按最后一次作答的间隔安排；到期不代表已经遗忘。",()->duePage());
        else note("暂无到期内容。练习后会自动安排复习日期。");
        long libraries=db.count("SELECT COUNT(*) n FROM library WHERE archived=0");
        if(libraries==0)card("还没有知识库","前往“我的 → 题库管理”创建或导入。",()->manageLibraries());
    }
    private void todayPlans(int offset) {
        screen="todayPlans";page("今日计划",true);
        long unfinished=db.count("SELECT COUNT(*) n FROM session s JOIN library l ON l.id=s.library_id WHERE s.finished=0 AND l.archived=0");
        if(unfinished>0)link("选择未完成练习 · "+unfinished+" 轮",()->resumeList(0));
        renderTodayPlans(10,offset);
        long total=db.count("SELECT COUNT(*) n FROM library WHERE archived=0");
        if(offset>0)link("上一页",()->todayPlans(offset-10));
        if(offset+10<total)link("下一页",()->todayPlans(offset+10));
    }
    private void resumeList(int offset) {
        screen="resumeList";page("继续练习",true);
        JSONArray list=db.rows("SELECT s.*,l.name FROM session s JOIN library l ON l.id=s.library_id WHERE s.finished=0 AND l.archived=0 ORDER BY s.id DESC LIMIT 10 OFFSET "+offset);
        for(int i=0;i<list.length();i++) {
            JSONObject s=list.optJSONObject(i);card(s.optString("name"),skillName(s.optString("mode"))+" · 已完成 "+s.optInt("position")+" 条",()->{sessionId=s.optLong("id");practice();});
        }
        long total=db.count("SELECT COUNT(*) n FROM session s JOIN library l ON l.id=s.library_id WHERE s.finished=0 AND l.archived=0");
        if(offset>0)link("上一页",()->resumeList(offset-10));
        if(offset+10<total)link("下一页",()->resumeList(offset+10));
    }
    private void renderTodayPlans(int limit,int offset) {
        JSONArray libs=db.rows("SELECT * FROM library WHERE archived=0 ORDER BY id LIMIT "+limit+" OFFSET "+offset);
        if(libs.length()==0)card("还没有知识库","前往“我的 → 题库管理”创建或导入。",()->manageLibraries());
        for(int i=0;i<libs.length();i++) {
            JSONObject l=libs.optJSONObject(i);
            long id=l.optLong("id");
            String mode=l.optString("kind").equals("word")?"recognition":"question";
            int done=(int)db.count("SELECT COUNT(*) n FROM attempt a JOIN session s ON a.session_id=s.id WHERE s.library_id=? AND a.at>=?",""+id,""+dayStart());
            int available=(int)db.count("SELECT COUNT(*) n FROM item WHERE library_id=? AND archived=0",""+id);
            int remaining=Math.max(0,Math.min(daily(),available)-done);
            long due=db.count("SELECT COUNT(*) n FROM state s JOIN item i ON i.id=s.owner_id WHERE s.skill=? AND i.library_id=? AND i.archived=0 AND s.due_at<=?",mode,""+id,""+System.currentTimeMillis());
            card(l.optString("name"),available==0?"知识库为空，先添加或导入内容。":remaining==0?"今日任务已完成 ✓":"剩余 "+remaining+" 条 · "+(mode.equals("recognition")?"到期复习 "+due+" 词":"根据知识点估计与间隔选题"),()-> {
                libraryId=id;
                if(remaining>0)start(mode,remaining,"adaptive",0);
                else library(id);
            }
            );
        }
    }
    private void beginToday() {
        JSONObject active=db.one("SELECT s.id FROM session s JOIN library l ON l.id=s.library_id WHERE s.finished=0 AND l.archived=0 ORDER BY s.id DESC LIMIT 1");
        if(active!=null){sessionId=active.optLong("id");practice();return;}
        JSONArray runnable=runnableTasks();
        for(int i=0;i<runnable.length();i++)if(taskRunnable(runnable.optJSONObject(i))){managementContext=false;launchTask(runnable.optJSONObject(i));return;}
        JSONArray due=dueStates();
        if(due.length()>0){launchDue(due.optJSONObject(0));return;}
        String subject=getPreferences(MODE_PRIVATE).getString("focusSubject","全部学科");
        JSONArray libraries=db.rows("SELECT * FROM library WHERE archived=0 ORDER BY CASE WHEN subject=? THEN 0 ELSE 1 END,id",subject);
        for(int i=0;i<libraries.length();i++) {
            JSONObject library=libraries.optJSONObject(i);long id=library.optLong("id");
            String mode="word".equals(library.optString("kind"))?"recognition":"question";
            int available=(int)db.count("SELECT COUNT(*) n FROM item WHERE library_id=? AND archived=0",""+id);
            int done=(int)db.count("SELECT COUNT(*) n FROM attempt a JOIN session s ON a.session_id=s.id WHERE s.library_id=? AND a.at>=?",""+id,""+dayStart());
            int remaining=Math.max(0,Math.min(daily(),available)-done);
            if(remaining>0){
                libraryId=id;
                boolean initial=db.count("SELECT COUNT(*) n FROM attempt a JOIN session s ON s.id=a.session_id WHERE s.library_id=?",""+id)==0;
                if(initial&&"recognition".equals(mode)&&db.count("SELECT COUNT(DISTINCT meaning) n FROM item WHERE library_id=? AND archived=0",""+id)<2)mode="recall";
                start(mode,initial?Math.min(6,remaining):remaining,initial?"diagnostic":"adaptive",0);return;
            }
        }
        toast("今日基础计划已完成，可到知识库选择专项练习");
        home(1);
    }
    private JSONArray runnableTasks() {
        return db.rows("SELECT t.* FROM task t JOIN library l ON l.id=t.library_id WHERE l.archived=0 AND t.completed=0 AND t.due_at<=? AND (t.stage='concept' OR EXISTS(SELECT 1 FROM task p WHERE p.source_session=t.source_session AND p.completed=1 AND p.stage=CASE t.stage WHEN 'basic' THEN 'concept' WHEN 'application' THEN 'basic' ELSE 'application' END)) ORDER BY t.due_at,t.id",""+System.currentTimeMillis());
    }
    private JSONArray dueStates() {
        String sql="SELECT p.id owner_id,p.name,l.id library_id,l.name library_name,'knowledge' skill,s.mastery,s.seen,s.due_at FROM state s JOIN point p ON p.id=s.owner_id JOIN library l ON l.id=p.library_id WHERE s.skill='knowledge' AND s.seen>0 AND s.due_at<=? AND p.archived=0 AND l.archived=0 AND EXISTS(SELECT 1 FROM item_point ip JOIN item i ON i.id=ip.item_id WHERE ip.point_id=p.id AND i.archived=0) UNION ALL SELECT i.id owner_id,i.prompt name,l.id library_id,l.name library_name,s.skill,s.mastery,s.seen,s.due_at FROM state s JOIN item i ON i.id=s.owner_id JOIN library l ON l.id=i.library_id WHERE s.skill IN ('recognition','recall','context') AND s.seen>0 AND s.due_at<=? AND i.archived=0 AND l.archived=0 ORDER BY due_at,mastery";
        String now=""+System.currentTimeMillis();return db.rows(sql,now,now);
    }
    private boolean taskRunnable(JSONObject task) {
        JSONObject l=db.one("SELECT kind FROM library WHERE id=? AND archived=0",""+task.optLong("library_id"));
        if(l==null)return false;
        String stage=task.optString("stage");long point=task.optLong("point_id");
        if("concept".equals(stage)&&point>0)return db.count("SELECT COUNT(*) n FROM point WHERE id=? AND archived=0",""+point)>0;
        String sql="SELECT COUNT(*) n FROM item WHERE library_id=? AND archived=0";
        if(point>0)sql+=" AND EXISTS(SELECT 1 FROM item_point ip WHERE ip.item_id=item.id AND ip.point_id="+point+")";
        if(!"word".equals(l.optString("kind"))){if("basic".equals(stage))sql+=" AND difficulty=1";else if("application".equals(stage))sql+=" AND difficulty>=2";}
        return db.count(sql,""+task.optLong("library_id"))>0;
    }
    private void duePage() {
        screen="due";page("到期复习",true);
        note("到期日期来自最近一次实际作答的复习间隔。选择一项开始巩固。");
        JSONArray due=dueStates();
        for(int i=0;i<Math.min(30,due.length());i++){
            JSONObject r=due.optJSONObject(i);card(r.optString("name"),r.optString("library_name")+" · "+("knowledge".equals(r.optString("skill"))?"知识点":skillName(r.optString("skill")))+"\n掌握概率估计 "+percent(r.optDouble("mastery")),()->launchDue(r));
        }
        if(due.length()==0)emptyState("暂无到期复习","先完成今天的学习，系统会安排下一次复习。");
        if(due.length()>30)note("显示最早到期的30项；完成后自动刷新后续内容。");
    }
    private void launchDue(JSONObject due) {
        libraryId=due.optLong("library_id");managementContext=false;
        String skill=due.optString("skill");
        if("knowledge".equals(skill))start("question",Math.min(5,daily()),"adaptive",due.optLong("owner_id"));
        else {
            safely(()->{
                sessionId=db.insert("session",LearningStore.obj("library_id",libraryId,"mode",skill,"strategy","adaptive","target_point",0,"created_at",System.currentTimeMillis(),"plan",new JSONArray().put(due.optLong("owner_id")).toString()));
                practice();
            });
        }
    }
    @Override protected void quickLearn() {if(busy){toast("正在处理文件，请稍候");return;}beginToday();}
    private void libraries() {
        page("知识库",false);
        button("上传资料出题",()->openAi(0));
        headline("把知识，收进自己的书架。");
        EditText search=input("搜索知识库、学科或内容",librarySearch);
        LinearLayout area=new LinearLayout(this);
        area.setOrientation(LinearLayout.VERTICAL);
        body.addView(area);
        renderLibraries(area,librarySearch);
        search.addTextChangedListener(new android.text.TextWatcher() {
            public void beforeTextChanged(CharSequence s,int a,int c,int f) {
            }
            public void onTextChanged(CharSequence s,int a,int b,int c) {
                subjectPages.clear();
                subjectOffset=0;
                librarySearch=s.toString();
                renderLibraries(area,s.toString());
            }
            public void afterTextChanged(android.text.Editable e) {
            }
        }
        );
        note("按学科展开知识库，再进入知识点与题目。创建、导入和编辑位于“我的 → 题库管理”。");
    }
    private void renderLibraries(LinearLayout area,String q) {
        area.removeAllViews();
        LinearLayout save=body;
        body=area;
        String match="%"+q.trim()+"%";
        String where="l.archived=0 AND (l.name LIKE ? OR l.subject LIKE ? OR EXISTS(SELECT 1 FROM item i WHERE i.library_id=l.id AND i.archived=0 AND (i.prompt LIKE ? OR i.meaning LIKE ?)))";
        JSONArray groups=db.rows("SELECT l.subject,COUNT(*) n,MIN(CASE WHEN l.kind='word' THEN 0 WHEN l.subject LIKE '%计算机%' THEN 1 ELSE 2 END) priority FROM library l WHERE "+where+" GROUP BY l.subject ORDER BY priority,l.subject LIMIT 20 OFFSET "+subjectOffset,match,match,match,match);
        for(int i=0;i<groups.length();i++) {
            JSONObject group=groups.optJSONObject(i);String subject=group.optString("subject");int count=group.optInt("n");
            boolean open=!q.trim().isEmpty()||expandedSubjects.contains(subject)||(count==1&&group.optInt("priority")<2&&!collapsedSubjects.contains(subject));
            disclosure(subject+" · "+count+" 个知识库",open,()->{
                if(open){expandedSubjects.remove(subject);collapsedSubjects.add(subject);}
                else {expandedSubjects.add(subject);collapsedSubjects.remove(subject);}
                renderLibraries(area,q);
            });
            if(!open)continue;
            int page=subjectPages.getOrDefault(subject,0);int maxPage=Math.max(0,(count-1)/10);page=Math.min(page,maxPage);
            JSONArray ls=db.rows("SELECT l.* FROM library l WHERE l.subject=? AND "+where+" ORDER BY l.name,l.id LIMIT 10 OFFSET "+(page*10),subject,match,match,match,match);
            LinearLayout nested=new LinearLayout(this);nested.setOrientation(LinearLayout.VERTICAL);nested.setPadding(0,0,0,dp(8));body.addView(nested);body=nested;
            for(int j=0;j<ls.length();j++) {
                JSONObject l=ls.optJSONObject(j);long id=l.optLong("id");
                long total=db.count("SELECT COUNT(*) n FROM item WHERE library_id=? AND archived=0",""+id),seen=db.count("SELECT COUNT(DISTINCT a.item_id) n FROM attempt a JOIN item i ON i.id=a.item_id WHERE i.library_id=? AND i.archived=0",""+id);
                libraryTile(l.optString("name"),subject,"word".equals(l.optString("kind")),total,seen,()->{if(managementContext)manageLibrary(id);else library(id);});
            }
            final int current=page;
            if(count>10) {
                note("第 "+(page+1)+" / "+(maxPage+1)+" 页");
                if(page>0)link("上一页",()->{subjectPages.put(subject,current-1);renderLibraries(area,q);});
                if(page<maxPage)link("下一页",()->{subjectPages.put(subject,current+1);renderLibraries(area,q);});
            }
            body=area;
        }
        if(groups.length()==0)emptyState("没有匹配的知识库。",q.trim().isEmpty()?"新建知识库，或导入题库与词表开始学习。":"试试更短的关键词，或清空搜索查看全部。");
        long subjects=db.count("SELECT COUNT(DISTINCT l.subject) n FROM library l WHERE "+where,match,match,match,match);
        if(subjectOffset>0)link("上一组学科",()->{subjectOffset-=20;renderLibraries(area,q);});
        if(subjectOffset+20<subjects)link("下一组学科",()->{subjectOffset+=20;renderLibraries(area,q);});
        body=save;
    }
    private void libraryForm(JSONObject old) {
        screen="libraryForm";
        page(old==null?"新建知识库":"编辑知识库",true);
        EditText n=input("名称",old==null?"":old.optString("name")),s=input("学科",old==null?"":old.optString("subject"));
        Spinner kind=spinner(new String[] {
            "题库 · 单选题","词库 · 英语"
        }
        );
        if(old!=null) {
            kind.setSelection(old.optString("kind").equals("word")?1:0);
            kind.setEnabled(false);
        }
        button("保存知识库",()->safely(()-> {
            if(n.getText().toString().trim().isEmpty()||s.getText().toString().trim().isEmpty())throw new Exception("名称和学科不能为空");
            JSONObject v=LearningStore.obj("name",n.getText().toString().trim(),"subject",s.getText().toString().trim(),"kind",kind.getSelectedItemPosition()==0?"question":"word");
            if(old==null)libraryId=db.insert("library",v);
            else {
                libraryId=old.optLong("id");
                db.edit("library",libraryId,v);
            }
            if(managementContext)manageLibrary(libraryId);else library(libraryId);
        }
        ));
    }
    private void library(long id) {
        managementContext=false;
        librarySection(id,0);
    }
    private void manageLibraries() {
        managementContext=true;screen="manageLibraries";page("题库管理",true);
        button("上传资料出题",()->openAi(0));
        note("这里创建、导入和整理内容；归档保留历史记录，学习入口仍在知识库。");
        button("＋ 新建知识库",()->libraryForm(null));
        link("导入题库／词表 JSON",()->pick("content","application/json"));
        link("导出导入模板",()->safely(()->export(LearningStore.sample().toString(2),"zhixue-template.json")));
        link("添加数学／公考／考研示例",()->safely(()->{toast(db.importContent(SubjectSamples.content()));manageLibraries();}));
        link("恢复归档内容",()->archived());
        EditText query=input("搜索知识库、学科或内容","");
        LinearLayout area=new LinearLayout(this);area.setOrientation(LinearLayout.VERTICAL);body.addView(area);renderLibraries(area,"");
        query.addTextChangedListener(new android.text.TextWatcher(){
            public void beforeTextChanged(CharSequence s,int start,int count,int after){}
            public void onTextChanged(CharSequence s,int start,int before,int count){subjectPages.clear();subjectOffset=0;renderLibraries(area,s.toString());}
            public void afterTextChanged(android.text.Editable e){}
        });
    }
    private void manageLibrary(long id) {
        managementContext=true;libraryId=id;screen="manageLibrary";
        JSONObject l=currentLibrary();if(l==null){manageLibraries();return;}
        page("管理 · "+l.optString("name"),true);
        boolean word="word".equals(l.optString("kind"));
        link("＋ 添加"+(word?"单词":"题目"),()->itemForm(null));
        if(!word){link("＋ 新建知识点",()->pointForm(null));link("维护知识点",()->points());}
        if(!word)link("从资料生成试题",()->openAi(id));
        link("内容维护",()->itemList("all"));
        link("按知识点查看内容",()->contentOutline());
        link("参考资料",()->references(0));
        link("编辑知识库",()->libraryForm(l));
        link("导入题库／词表 JSON",()->pick("content","application/json"));
        link("归档知识库",()->confirm("归档知识库","内容和历史保留，未完成任务会结束。可在“我的”恢复。",()->{db.archiveLibrary(id);manageLibraries();}));
    }
    private void openAi(long id) {
        openAi(id,null);
    }
    private void openAi(long id,Bundle draft) {
        if(accountSession==null){toast("AI 出题需要有效的联网账号");return;}
        if(draft==null){aiOrigin=screen;aiOriginLibrary=libraryId;}
        if(aiController!=null)aiController.close();libraryId=id;screen="ai";
        JSONObject library=db.one("SELECT * FROM library WHERE id=? AND archived=0",""+id);
        if(library!=null&&!"question".equals(library.optString("kind")))library=null;
        aiController=new AiGenerationController(this,db,accountSession,library,this::closeAi);aiController.setOpenLibrary(target->{if(aiController!=null)aiController.close();library(target);});aiController.show(draft);
    }
    private void closeAi() {
        if(aiController!=null)aiController.close();
        if("manageLibrary".equals(aiOrigin)&&aiOriginLibrary>0)manageLibrary(aiOriginLibrary);
        else if("library".equals(aiOrigin)&&aiOriginLibrary>0)library(aiOriginLibrary);
        else if("manageLibraries".equals(aiOrigin))manageLibraries();
        else home(1);
    }
    private void librarySection(long id,int section) {
        if(busy){toast("正在处理文件，请稍候");return;}
        if(section==2){manageLibrary(id);return;}
        managementContext=false;
        libraryId=id;
        librarySection=section;
        screen="library";
        JSONObject l=currentLibrary();
        page(l.optString("name"),true);
        boolean word=l.optString("kind").equals("word");
        if(!word){button("上传资料出题",()->openAi(id));link("按掌握情况生成新题",()->{openAi(id);aiController.enableAdaptiveGeneration();});}
        segments(new String[]{"学习","内容"},section,index->librarySection(id,index));
        if(section==1) {
            link("按知识点查看内容",()->contentOutline());
            if(!word)link("知识点与学习摘要",()->points());
            link("错题 · 待验证 · 收藏",()->historyMenu());
            link("参考资料",()->references(0));
            return;
        }
        long total=db.count("SELECT COUNT(*) n FROM item WHERE library_id=? AND archived=0",""+id),seen=db.count("SELECT COUNT(DISTINCT a.item_id) n FROM attempt a JOIN item i ON i.id=a.item_id WHERE i.library_id=? AND i.archived=0",""+id);
        card("学习进度","已测试 "+seen+" / "+total+" 条\n覆盖、正确率与掌握估计分开统计。",null);
        if(total==0) {
            emptyState("知识库为空","添加或导入内容后，再开始学习。");
            link(word?"去添加单词":"去添加题目",()->manageLibrary(id));
            if(!word)link("知识点与学习摘要",()->points());
            link("参考资料",()->references(0));
            return;
        }
        if(word) {
            button("开始单词学习",()->start("recognition",daily(),"adaptive",0));
            note("看单词选释义，从轻松识别开始。");
            heading("进阶练习");
            link("回忆测试 · 中文拼写",()->start("recall",daily(),"adaptive",0));
            link("语境应用 · 例句填空",()->start("context",daily(),"adaptive",0));
            link("逐词浏览 · 查看与自评",()->wordList());
        }
        else {
            button("开始自适应练习",()->start("question",daily(),"adaptive",0));
            note("每次一张题目卡片；提交答案和信心后更新知识点掌握估计，后续选题读取最新状态。");
            heading("题目卡片");
            JSONArray cards=db.rows("SELECT id,prompt FROM item WHERE library_id=? AND kind='question' AND archived=0 ORDER BY id DESC LIMIT 5",""+id);
            for(int i=0;i<cards.length();i++){JSONObject item=cards.optJSONObject(i);long itemId=item.optLong("id");card(item.optString("prompt"),"点击作答本题 · 提交后显示解析",()->safely(()->{managementContext=false;sessionId=db.startQuestion(id,itemId);practice();}));}
            if(total>5)link("查看全部题目卡片",()->itemList("all"));
            link("随机选题 · 对照入口",()->start("question",daily(),"random",0));
            link("知识点与学习摘要",()->points());
        }
        if(seen==0)link("初始能力测试",()->start(word?"recall":"question",6,"diagnostic",0));
        link("错题 · 待验证 · 收藏",()->historyMenu());
        link("参考资料",()->references(0));
    }
    private void points() {
        pointOffset=0;
        screen="points";
        page("知识点",true);
        EditText query=input("搜索知识点、摘要、示例或记忆方法","");
        LinearLayout results=new LinearLayout(this);results.setOrientation(LinearLayout.VERTICAL);body.addView(results);
        renderPoints(results,"");
        query.addTextChangedListener(new android.text.TextWatcher(){
            public void beforeTextChanged(CharSequence s,int start,int count,int after){}
            public void onTextChanged(CharSequence s,int start,int before,int count){pointOffset=0;renderPoints(results,s.toString());}
            public void afterTextChanged(android.text.Editable e){}
        });
    }
    private void renderPoints(LinearLayout results,String query){
        results.removeAllViews();LinearLayout previous=body;body=results;
        String match="%"+query+"%";
        String where="library_id=? AND archived=0 AND (name LIKE ? OR summary LIKE ? OR example LIKE ? OR mnemonic LIKE ?)";
        JSONArray ps=db.rows("SELECT * FROM point WHERE "+where+" ORDER BY id LIMIT 10 OFFSET "+pointOffset,""+libraryId,match,match,match,match);
        if(ps.length()==0)note(query.isEmpty()?"还没有知识点，请先新建。":"未找到匹配内容，请查阅参考资料或补充知识点。");
        for(int i=0;i<ps.length();i++) {
            JSONObject p=ps.optJSONObject(i),s=db.state(p.optLong("id"),"knowledge");
            card(p.optString("name"),s.optInt("seen")==0?"未测试 · 证据不足":"估计掌握 "+percent(s.optDouble("mastery"))+" · "+s.optInt("seen")+" 次证据",()->point(p.optLong("id")));
        }
        long total=db.count("SELECT COUNT(*) n FROM point WHERE "+where,""+libraryId,match,match,match,match);
        if(pointOffset>0)link("上一页",()->{pointOffset-=10;renderPoints(results,query);});
        if(pointOffset+10<total)link("下一页",()->{pointOffset+=10;renderPoints(results,query);});
        body=previous;
    }
    private void point(long id) {
        screen="point";
        JSONObject p=db.one("SELECT * FROM point WHERE id=?",""+id);
        page(p.optString("name"),true);
        JSONObject s=db.state(id,"knowledge");
        note(s.optInt("seen")==0?"待评估：暂无证据，不显示掌握百分比。":"掌握概率估计 "+percent(s.optDouble("mastery"))+" · "+s.optInt("seen")+" 次证据，未经校准，仅供参考");
        heading("知识摘要");
        text(p.optString("summary"),READING,INK);
        heading("示例");
        text(p.optString("example"),READING,INK);
        heading("记忆方法");
        text(p.optString("mnemonic"),BODY,INK);
        button("开始专项练习",()->start("question",daily(),"adaptive",id));
        link("关联参考资料",()->references(id));
        link("查看关联题目",()->showItemBrowser("all",id,"",0));
        link("掌握概率变化与计算过程",()->masteryHistory(id,"knowledge",p.optString("name")));
        if(managementContext)link("编辑知识点",()->pointForm(p));
        heading("最近练习记录");
        JSONArray a=db.rows("SELECT a.* FROM attempt a JOIN attempt_point p ON p.attempt_id=a.id WHERE p.point_id=? ORDER BY a.at DESC LIMIT 20",""+id);
        for(int i=0;i<a.length();i++) {
            JSONObject x=a.optJSONObject(i);
            card(x.optString("prompt"),(x.optInt("correct")==1?"答对":"答错")+" · "+confidenceName(x.optInt("confidence"))+" · "+date.format(new Date(x.optLong("at"))),null);
        }
        if(a.length()==0)note("暂无记录。");
    }
    private void pointForm(JSONObject old) {
        screen="pointForm";
        page(old==null?"新建知识点":"编辑知识点",true);
        EditText n=input("名称",old==null?"":old.optString("name")),s=input("摘要",old==null?"":old.optString("summary")),e=input("示例",old==null?"":old.optString("example")),m=input("记忆方法",old==null?"":old.optString("mnemonic"));
        button("保存知识点",()->safely(()-> {
            if(n.getText().toString().trim().isEmpty()||s.getText().toString().trim().isEmpty())throw new Exception("名称和摘要不能为空");
            JSONObject v=LearningStore.obj("library_id",libraryId,"name",n.getText().toString().trim(),"summary",s.getText().toString().trim(),"example",e.getText().toString(),"mnemonic",m.getText().toString());
            JSONObject dupe=db.one("SELECT id FROM point WHERE library_id=? AND name=? AND archived=0",""+libraryId,v.optString("name"));
            if(dupe!=null&&(old==null||dupe.optLong("id")!=old.optLong("id")))throw new Exception("知识点名称已存在");
            if(old==null)db.insert("point",v);
            else db.edit("point",old.optLong("id"),v);
            points();
        }
        ));
    }
    private void historyMenu() {
        screen="historyMenu";
        page("学习内容回顾",true);
        link("历史错题（再次答对仍保留历史）",()->itemList("wrong"));
        link("答对但不确定（保留复测证据）",()->itemList("verify"));
        link("收藏内容",()->itemList("star"));
    }
    private void itemList(String filter) {
        showItemBrowser(filter,-1,"",0);
    }
    private void contentOutline() {contentOutline(0);}
    private void contentOutline(int offset) {
        screen="contentOutline";page("按知识点查看内容",true);
        link("全部内容",()->showItemBrowser("all",-1,"",0));
        JSONArray points=db.rows("SELECT p.*,COUNT(i.id) n FROM point p LEFT JOIN item_point ip ON ip.point_id=p.id LEFT JOIN item i ON i.id=ip.item_id AND i.archived=0 AND i.library_id=p.library_id WHERE p.library_id=? AND p.archived=0 GROUP BY p.id ORDER BY p.name,p.id LIMIT 10 OFFSET "+offset,""+libraryId);
        for(int i=0;i<points.length();i++) {
            JSONObject point=points.optJSONObject(i);long id=point.optLong("id");
            card(point.optString("name"),point.optInt("n")+" 条关联内容",()->showItemBrowser("all",id,"",0));
        }
        link("未分类内容",()->showItemBrowser("all",0,"",0));
        long total=db.count("SELECT COUNT(*) n FROM point WHERE library_id=? AND archived=0",""+libraryId);
        if(offset>0)link("上一页",()->contentOutline(offset-10));
        if(offset+10<total)link("下一页",()->contentOutline(offset+10));
    }
    private void showItemBrowser(String filter,long point,String query,int offset) {
        itemFilter=filter;itemPoint=point;itemQuery=query;itemOffset=offset;
        screen="itemList";
        page(filter.equals("all")?(managementContext?"内容维护":"题目与单词"):filter.equals("wrong")?"历史错题":filter.equals("verify")?"待验证内容":"收藏",true);
        if(point>0)note(currentLibrary().optString("name")+" / "+db.one("SELECT name FROM point WHERE id=?",""+point).optString("name"));
        else if(point==0)note("未关联知识点的内容");
        EditText search=input("搜索题干、单词或释义",query);
        LinearLayout results=new LinearLayout(this);results.setOrientation(LinearLayout.VERTICAL);body.addView(results);
        renderItems(results);
        search.addTextChangedListener(new android.text.TextWatcher(){
            public void beforeTextChanged(CharSequence s,int a,int c,int f){}
            public void onTextChanged(CharSequence s,int a,int b,int c){itemQuery=s.toString();itemOffset=0;renderItems(results);}
            public void afterTextChanged(android.text.Editable e){}
        });
        if(!filter.equals("all"))button("重新练习",()->start(currentLibrary().optString("kind").equals("word")?"recall":"question",daily(),filter,0));
    }
    private void renderItems(LinearLayout results) {
        results.removeAllViews();LinearLayout previous=body;body=results;
        String where="i.library_id=? AND i.archived=0 AND (i.prompt LIKE ? OR i.meaning LIKE ?)";
        if(itemFilter.equals("star"))where+=" AND i.starred=1";
        if(itemFilter.equals("wrong"))where+=" AND EXISTS(SELECT 1 FROM attempt a WHERE a.item_id=i.id AND a.correct=0)";
        if(itemFilter.equals("verify"))where+=" AND EXISTS(SELECT 1 FROM attempt a WHERE a.item_id=i.id AND a.correct=1 AND a.confidence<2)";
        if(itemPoint>0)where+=" AND EXISTS(SELECT 1 FROM item_point ip WHERE ip.item_id=i.id AND ip.point_id="+itemPoint+")";
        else if(itemPoint==0)where+=" AND NOT EXISTS(SELECT 1 FROM item_point ip JOIN point p ON p.id=ip.point_id WHERE ip.item_id=i.id AND p.archived=0)";
        String match="%"+itemQuery.trim()+"%";
        long total=db.count("SELECT COUNT(*) n FROM item i WHERE "+where,""+libraryId,match,match);
        itemOffset=Math.min(itemOffset,Math.max(0,((int)total-1)/20*20));
        JSONArray items=db.rows("SELECT i.* FROM item i WHERE "+where+" ORDER BY i.id LIMIT 20 OFFSET "+itemOffset,""+libraryId,match,match);
        note("共 "+total+" 条 · 第 "+(itemOffset/20+1)+" / "+Math.max(1,(total+19)/20)+" 页");
        if(total>20)pager(itemOffset>0?()->{itemOffset-=20;renderItems(results);}:null,itemOffset+20<total?()->{itemOffset+=20;renderItems(results);}:null);
        for(int i=0;i<items.length();i++) {
            JSONObject x=items.optJSONObject(i);
            boolean question="question".equals(x.optString("kind"));
            card(x.optString("prompt"),question&&!managementContext?"难度 "+x.optInt("difficulty")+" · 点击卡片作答":x.optString("kind").equals("word")?x.optString("meaning"):"难度 "+x.optInt("difficulty")+" · 查看题目与历史",()->{if(question&&!managementContext)safely(()->{sessionId=db.startQuestion(libraryId,x.optLong("id"));practice();});else itemDetail(x);});
        }
        if(total==0)note("当前没有内容。");
        body=previous;
    }
    private void itemDetail(JSONObject x) {
        screen="itemDetail";
        page("内容详情",true);
        heading(x.optString("prompt"));
        if(x.optString("kind").equals("word"))text(x.optString("meaning")+"\n"+x.optString("example"),READING,INK);
        else  {
            safely(()-> {
                JSONArray opts=new JSONArray(x.optString("options"));
                for(int i=0;i<opts.length();i++)text("ABCD".charAt(i)+"  "+opts.getString(i),READING,INK);
            }
            );
            text("答案："+x.optString("answer")+"\n"+x.optString("explanation"),READING,INK);
        }
        long id=x.optLong("id");
        JSONObject aiSource=db.one("SELECT metadata FROM ai_source WHERE item_id=? ORDER BY id LIMIT 1",""+id);
        if(aiSource!=null)safely(()->{JSONObject source=new JSONObject(aiSource.getString("metadata"));heading("AI 题目来源");note(source.optString("sourceFile")+" · "+source.optString("sourceLocation")+"\n原文证据："+source.optString("evidenceQuote")+"\n生成："+source.optString("generationModel")+"；复核："+source.optString("reviewModel")+"\n自动初筛不代表正确性保证。");});
        link(x.optInt("starred")==1?"取消收藏":"收藏",()-> {
            db.edit("item",id,LearningStore.obj("starred",x.optInt("starred")==1?0:1));
            itemDetail(db.one("SELECT * FROM item WHERE id=?",""+id));
        }
        );
        if(managementContext)link("编辑内容",()->itemForm(x));
        if(managementContext)link("归档内容",()->confirm("归档内容","历史与掌握状态保留。含此内容的未完成任务会结束，可在“我的”恢复内容。",()-> {
            db.edit("item",id,LearningStore.obj("archived",1));
            finishLibrarySessions();
            manageLibrary(libraryId);
        }
        ));
        heading("历史作答");
        JSONArray a=db.rows("SELECT * FROM attempt WHERE item_id=? ORDER BY at DESC LIMIT 100",""+id);
        for(int i=0;i<a.length();i++) {
            JSONObject r=a.optJSONObject(i);
            card((r.optInt("correct")==1?"答对":"答错")+" · "+skillName(r.optString("skill")),"当时题目："+r.optString("prompt")+"\n作答："+r.optString("response")+" · 正解："+r.optString("expected")+"\n"+confidenceName(r.optInt("confidence"))+" · "+date.format(new Date(r.optLong("at")))+" · 用时 "+r.optLong("elapsed_ms")/1000+" 秒",null);
        }
        if(a.length()==0)note("尚无作答记录。");
    }
    private void finishLibrarySessions() {
        db.getWritableDatabase().execSQL("UPDATE session SET finished=2 WHERE library_id=? AND finished=0",new Object[] {
            libraryId
        }
        );
    }
    private void itemForm(JSONObject old) {
        screen="itemForm";
        boolean word=currentLibrary().optString("kind").equals("word");
        page(old==null?"添加内容":"编辑内容",true);
        note("修改内容会结束本库未完成任务，历史保留当时题干、答案与知识点关联。");
        EditText prompt=input(word?"英文拼写":"题干",old==null?"":old.optString("prompt"));
        EditText meaning=null,example=null,context=null,explain=null;
        EditText[] options=new EditText[4];
        Spinner answer=null;
        JSONArray ps=db.rows("SELECT * FROM point WHERE library_id=? AND archived=0",""+libraryId);
        List<CheckBox> checks=new ArrayList<>();
        if(word) {
            meaning=input("中文释义",old==null?"":old.optString("meaning"));
            example=input("完整例句",old==null?"":old.optString("example"));
            context=input("语境题（用 ____ 替换目标单词）",old==null?"":old.optString("context_prompt"));
        }
        else  {
            JSONArray os=new JSONArray();
            if(old!=null)try {
                os=new JSONArray(old.optString("options"));
            }
            catch(JSONException ignored) {
            }
            for(int i=0;i<4;i++)options[i]=input("选项 "+"ABCD".charAt(i),os.optString(i));
            answer=spinner(new String[] {
                "答案 A","答案 B","答案 C","答案 D"
            }
            );
            if(old!=null)answer.setSelection(Math.max(0,"ABCD".indexOf(old.optString("answer"))));
            explain=input("答案解析",old==null?"":old.optString("explanation"));
            heading("关联知识点（可多选）");
            for(int i=0;i<ps.length();i++) {
                JSONObject p=ps.optJSONObject(i);
                CheckBox cb=new CheckBox(this);
                cb.setText(p.optString("name"));
                if(old!=null)cb.setChecked(db.count("SELECT COUNT(*) n FROM item_point WHERE item_id=? AND point_id=?",""+old.optLong("id"),""+p.optLong("id"))>0);
                checks.add(cb);
                body.addView(cb);
            }
            if(ps.length()==0)note("请先返回知识库创建知识点。");
        }
        heading("难度");
        Spinner difficulty=spinner(new String[] {
            "1 · 基础","2 · 中等","3 · 应用"
        }
        );
        if(old!=null)difficulty.setSelection(old.optInt("difficulty")-1);
        final EditText fm=meaning,fe=example,fc=context,fx=explain;
        final Spinner fa=answer;
        button("保存内容",()->safely(()-> {
            JSONArray names=new JSONArray(),links=new JSONArray();
            Set<String> all=new HashSet<>();
            for(int i=0;i<ps.length();i++) {
                all.add(ps.optJSONObject(i).optString("name"));
                if(!word&&checks.get(i).isChecked()) {
                    names.put(ps.optJSONObject(i).optString("name"));
                    links.put(ps.optJSONObject(i).optLong("id"));
                }
            }
            JSONArray opts=new JSONArray();
            if(!word)for(EditText op:options)opts.put(op.getText().toString().trim());
            String p=prompt.getText().toString().trim();
            JSONObject validation=LearningStore.obj("kind",word?"word":"question","prompt",p,"difficulty",difficulty.getSelectedItemPosition()+1,"points",names,"options",opts,"answer",word?p:"ABCD".substring(fa.getSelectedItemPosition(),fa.getSelectedItemPosition()+1),"explanation",word?"":fx.getText().toString().trim(),"meaning",word?fm.getText().toString().trim():"","example",word?fe.getText().toString().trim():"","context_prompt",word?fc.getText().toString().trim():"");
            LearningStore.validateItem(validation,word?"word":"question",all);
            JSONObject dupe=db.one("SELECT id FROM item WHERE library_id=? AND prompt=? AND archived=0",""+libraryId,p);
            if(dupe!=null&&(old==null||dupe.optLong("id")!=old.optLong("id")))throw new Exception("同名内容已存在");
            validation.remove("points");
            validation.put("options",opts.toString());
            validation.put("library_id",libraryId);
            android.database.sqlite.SQLiteDatabase sql=db.getWritableDatabase();
            sql.beginTransaction();
            try {
                long id;
                if(old==null)id=db.insert("item",validation);
                else {
                    id=old.optLong("id");
                    db.edit("item",id,validation);
                    sql.delete("item_point","item_id=?",new String[] {
                        ""+id
                    }
                    );
                    finishLibrarySessions();
                }
                for(int i=0;i<links.length();i++)db.insert("item_point",LearningStore.obj("item_id",id,"point_id",links.getLong(i)));
                sql.setTransactionSuccessful();
            }
            finally {
                sql.endTransaction();
            }
            library(libraryId);
        }
        ));
    }
    private void start(String mode,int n,String filter,long point) {
        if("recognition".equals(mode)&&db.count("SELECT COUNT(DISTINCT meaning) n FROM item WHERE library_id=? AND kind='word' AND archived=0",""+libraryId)<2){
            toast("当前词库不足两种不同释义，改用拼写回忆测试");start("recall",n,filter,point);return;
        }
        safely(()-> {
            managementContext=false;
            JSONObject active=db.one("SELECT * FROM session WHERE library_id=? AND mode=? AND strategy=? AND target_point=? AND finished=0 ORDER BY id DESC LIMIT 1",""+libraryId,mode,filter,""+point);
            if(active!=null) {
                sessionId=active.optLong("id");
                toast("继续已保存的同类练习");
            }
            else sessionId=db.start(libraryId,mode,n,filter,point);
            if(sessionId==0) {
                toast("没有符合条件的内容，请先添加或调整筛选");
                return;
            }
            String notice=db.sessionNotice(sessionId,n);
            if(!notice.isEmpty())toast(notice);
            practice();
        }
        );
    }
    private void practice() {
        safely(()-> {
            screen="practice";
            JSONObject s=db.one("SELECT * FROM session WHERE id=?",""+sessionId);
            if(s==null) {
                home(0);
                return;
            }
            libraryId=s.optLong("library_id");
            JSONArray plan=new JSONArray(s.getString("plan"));
            int pos=s.optInt("position");
            if(s.optInt("finished")!=0||pos>=plan.length()) {
                sessionReport(sessionId);
                return;
            }
            long item=plan.getLong(pos);
            JSONObject x=db.one("SELECT * FROM item WHERE id=?",""+item);
            JSONObject attempt=db.one("SELECT * FROM attempt WHERE session_id=? AND position=?",""+sessionId,""+pos);
            String mode=s.getString("mode");
            if(mode.equals("recognition")) {
                recognition(x,attempt,pos,plan.length());
                return;
            }
            page(skillName(mode),true);
            note(currentLibrary().optString("name")+" · 第 "+(pos+1)+" / "+plan.length()+" 条");
            note(strategyName(s.optString("strategy"))+" · 已提交进度自动保存");
            link("为什么推荐？",()->showRecommendation(item,mode,s.optString("strategy")));
            progress(plan.length(),pos);
            LinearLayout practiceBody=body;
            if(mode.equals("question"))body=surface(android.graphics.Color.WHITE);
            String question=mode.equals("question")?x.optString("prompt"):mode.equals("recognition")?x.optString("prompt"):mode.equals("context")?x.optString("context_prompt"):x.optString("meaning");
            text(question,SECTION,INK);
            if(attempt!=null) {
                answerResult(x,attempt);
                body=practiceBody;
                return;
            }
            startedAt=SystemClock.elapsedRealtime();
            RadioGroup options=new RadioGroup(this);
            EditText typed=null;
            JSONArray optionValues=new JSONArray();
            String expected;
            if(mode.equals("question")) {
                optionValues=new JSONArray(x.optString("options"));
                expected=x.optString("answer");
            }
            else if(mode.equals("recognition")) {
                expected=x.optString("meaning");
                Set<String> distinct=new LinkedHashSet<>();
                distinct.add(expected);
                JSONArray distract=db.rows("SELECT meaning FROM item WHERE kind='word' AND archived=0 AND id<>? ORDER BY RANDOM() LIMIT 100",""+item);
                for(int i=0;i<distract.length()&&distinct.size()<4;i++)distinct.add(distract.optJSONObject(i).optString("meaning"));
                if(distinct.size()<2) {
                    note("识别测试至少需要两种不同释义，请补充词汇。");
                    button("返回知识库",()->library(libraryId));
                    return;
                }
                List<String> choices=new ArrayList<>(distinct);
                Collections.shuffle(choices);
                optionValues=new JSONArray(choices);
            }
            else {
                expected=x.optString("prompt");
                typed=input("请输入英文单词","");
                typed.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
            }
            if(optionValues.length()>0) {
                body.addView(options);
                for(int i=0;i<optionValues.length();i++) {
                    RadioButton r=new RadioButton(this);
                    r.setId(View.generateViewId());
                    r.setTag(i);
                    r.setText((mode.equals("question")?"ABCD".charAt(i)+"   ":"")+optionValues.getString(i));
                    choice(r,false);
                    options.addView(r);
                }
            }
            heading("你对本题的把握程度");
            RadioGroup confidence=new RadioGroup(this);
            confidence.setOrientation(LinearLayout.HORIZONTAL);
            body.addView(confidence);
            for(int i=0;i<3;i++) {
                RadioButton r=new RadioButton(this);
                r.setId(View.generateViewId());
                r.setTag(i);
                r.setText(confidenceName(i));
                choice(r,true);
                confidence.addView(r);
            }
            final EditText input=typed;
            final JSONArray choices=optionValues;
            final String correctAnswer=expected;
            Button submit=button("提交答案",()->safely(()-> {
                if(confidence.getCheckedRadioButtonId()==-1)throw new Exception("请选择作答信心");
                String response;
                if(input!=null) {
                    response=input.getText().toString().trim();
                    if(response.isEmpty())throw new Exception("请输入答案");
                }
                else {
                    RadioButton selected=options.findViewById(options.getCheckedRadioButtonId());
                    if(selected==null)throw new Exception("请选择答案");
                    int idx=(int)selected.getTag();
                    response=mode.equals("question")?"ABCD".substring(idx,idx+1):choices.getString(idx);
                }
                int c=(int)confidence.findViewById(confidence.getCheckedRadioButtonId()).getTag();
                boolean correct=mode.equals("question")||mode.equals("recognition")?response.equals(correctAnswer):LearningEngine.spellingMatches(response,correctAnswer);
                db.submit(sessionId,pos,item,question,correctAnswer,response,correct,c,mode,SystemClock.elapsedRealtime()-startedAt);
                practice();
            }
            ));
            fixedAction(submit);
            TextView readiness=text("",BODY,MUTED);
            readiness.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
            Runnable updateReadiness=()-> {
                boolean answered=input!=null?!input.getText().toString().trim().isEmpty():options.getCheckedRadioButtonId()!=-1;
                boolean confident=confidence.getCheckedRadioButtonId()!=-1;
                submit.setEnabled(answered&&confident);submit.setAlpha(answered&&confident?1f:.45f);
                readiness.setText(!answered?(input!=null?"先输入答案，再选择把握程度。":"先选择答案，再选择把握程度。"):
                    !confident?"答案已选好，请选择把握程度。":"准备好了，可以提交答案。");
            };
            options.setOnCheckedChangeListener((group,id)->updateReadiness.run());
            confidence.setOnCheckedChangeListener((group,id)->updateReadiness.run());
            if(input!=null)input.addTextChangedListener(new android.text.TextWatcher(){
                public void beforeTextChanged(CharSequence s,int start,int count,int after){}
                public void onTextChanged(CharSequence s,int start,int before,int count){updateReadiness.run();}
                public void afterTextChanged(android.text.Editable value){}
            });
            updateReadiness.run();
            note("未提交不会记作答错；返回可保存进度。提交后才展示解析。");
            body=practiceBody;
        }
        );
    }
    private void recognition(JSONObject word,JSONObject attempt,int position,int total) throws Exception {
        String expected=attempt==null?word.optString("meaning"):attempt.optString("expected");
        Set<String> distinct=new LinkedHashSet<>();distinct.add(expected);
        JSONArray distract=db.rows("SELECT meaning FROM item WHERE kind='word' AND library_id=? AND archived=0 AND id<>? ORDER BY id LIMIT 100",""+libraryId,""+word.optLong("id"));
        List<String> pool=new ArrayList<>();
        for(int i=0;i<distract.length();i++)pool.add(distract.optJSONObject(i).optString("meaning"));
        Collections.shuffle(pool,new Random(sessionId^word.optLong("id")));
        if(attempt!=null)distinct.add(attempt.optString("response"));
        for(String meaning:pool){if(distinct.size()>=4)break;if(!meaning.trim().isEmpty())distinct.add(meaning);}
        if(distinct.size()<2){
            page("单词学习",true);note("当前词库不足两种不同释义，可改用拼写回忆。原练习已提交记录会保留。");
            button("改做拼写回忆",()->{db.edit("session",sessionId,LearningStore.obj("finished",2));start("recall",daily(),"adaptive",0);});
            link("返回知识库",()->library(libraryId));return;
        }
        List<String> choices=new ArrayList<>(distinct);Collections.sort(choices);
        Collections.shuffle(choices,new Random(sessionId+word.optLong("id")));
        String prompt=attempt==null?word.optString("prompt"):attempt.optString("prompt");
        if(attempt==null)startedAt=SystemClock.elapsedRealtime();
        WordStudyView study=new WordStudyView(this,currentLibrary().optString("name"),prompt,phonetic(prompt),position,total,choices,
            attempt==null?null:attempt.optString("response"),expected,word.optString("example"),word.optInt("starred")==1,new WordStudyView.Actions(){
                public void speak(){speakWord(prompt);}
                public void exit(){back();}
                public void submit(String response,int confidence){safely(()->{
                    db.submit(sessionId,position,word.optLong("id"),prompt,expected,response,response.equals(expected),confidence,"recognition",SystemClock.elapsedRealtime()-startedAt);
                    practice();
                });}
                public void next(){safely(()->{db.advance(sessionId);practice();});}
                public void star(){db.edit("item",word.optLong("id"),LearningStore.obj("starred",word.optInt("starred")==1?0:1));practice();}
                public void why(){JSONObject s=db.one("SELECT strategy FROM session WHERE id=?",""+sessionId);showRecommendation(word.optLong("id"),"recognition",s==null?"adaptive":s.optString("strategy"));}
            });
        setContentView(study);
        // The view installs its inset listener before attachment; request delivery after mounting it.
        androidx.core.view.ViewCompat.requestApplyInsets(study);
        androidx.core.view.WindowInsetsControllerCompat bars=new androidx.core.view.WindowInsetsControllerCompat(getWindow(),study);
        bars.setAppearanceLightStatusBars(true);bars.setAppearanceLightNavigationBars(true);
        getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(BG);
        if(attempt==null&&getPreferences(MODE_PRIVATE).getBoolean("studyAutoSpeak",false))speakWord(prompt);
    }
    private String phonetic(String word) {
        // Bundled words only: do not invent IPA for user-imported vocabulary.
        String[] words={"abandon","achieve","benefit","confident","develop","efficient","focus","improve","knowledge","memory","review","strategy"};
        String[] ipa={"/əˈbændən/","/əˈtʃiːv/","/ˈbenɪfɪt/","/ˈkɒnfɪdənt/","/dɪˈveləp/","/ɪˈfɪʃənt/","/ˈfəʊkəs/","/ɪmˈpruːv/","/ˈnɒlɪdʒ/","/ˈmeməri/","/rɪˈvjuː/","/ˈstrætədʒi/"};
        for(int i=0;i<words.length;i++)if(words[i].equalsIgnoreCase(word.trim()))return ipa[i];
        return "";
    }
    private void speakWord(String word) {
        if(!ttsReady){toast("语音引擎尚未准备好，请稍候");return;}
        Set<android.speech.tts.Voice> voices=tts.getVoices();android.speech.tts.Voice offline=null;
        if(voices!=null)for(android.speech.tts.Voice voice:voices){if(voice.getLocale().getLanguage().equals("en")&&!voice.isNetworkConnectionRequired()){offline=voice;break;}}
        if(offline==null){toast("手机缺少英语语音包，请安装离线英语语音包");return;}
        tts.setVoice(offline);
        if(tts.speak(word,TextToSpeech.QUEUE_FLUSH,null,"word")==TextToSpeech.ERROR)toast("无法播放发音，请检查手机语音引擎");
    }
    private void answerResult(JSONObject x,JSONObject a) {
        boolean correct=a.optInt("correct")==1;
        feedback(correct,"你的答案："+a.optString("response")+"\n正确答案："+a.optString("expected"));
        if(correct&&a.optInt("confidence")<2)note("答对但不确定：保留待验证任务，后续复测。");
        if(!correct&&a.optInt("confidence")==2)note("答错且确定：可能需要概念辨析，单次结果不能断定原因。");
        heading("解析");
        text(x.optString("kind").equals("word")?x.optString("prompt")+" — "+x.optString("meaning")+"\n"+x.optString("example"):x.optString("explanation"),READING,INK);
        JSONArray ps=db.rows("SELECT p.* FROM point p JOIN item_point ip ON ip.point_id=p.id WHERE ip.item_id=?",""+x.optLong("id"));
        for(int i=0;i<ps.length();i++) {
            JSONObject p=ps.optJSONObject(i);
            card(p.optString("name"),p.optString("summary"),()->point(p.optLong("id")));
        }
        Button next=button("下一题／完成本轮",()->safely(()-> {
            db.advance(sessionId);
            practice();
        }
        ));
        fixedAction(next);
        link(x.optInt("starred")==1?"取消收藏":"收藏本题",()-> {
            db.edit("item",x.optLong("id"),LearningStore.obj("starred",x.optInt("starred")==1?0:1));
            practice();
        }
        );
    }
    private void wordList() {
        screen="wordList";
        page("单词学习",true);
        note("自评不作为测试正确率，也不提高掌握估计。复习时间由实际测试更新。");
        JSONArray ws=db.rows("SELECT * FROM item WHERE library_id=? AND archived=0 ORDER BY id",""+libraryId);
        for(int i=0;i<ws.length();i++) {
            JSONObject w=ws.optJSONObject(i);
            card(w.optString("prompt"),w.optString("meaning"),()->word(w));
        }
        if(ws.length()==0)note("暂无词汇。");
    }
    private void word(JSONObject w) {
        screen="word";
        page("单词学习 · 回忆",true);
        text(w.optString("prompt"),WORD,INK).setGravity(Gravity.CENTER);
        link("播放发音",()-> {
            if(!ttsReady){toast("语音引擎尚未准备好，请稍候");return;}
            Set<android.speech.tts.Voice> voices=tts.getVoices();
            android.speech.tts.Voice offline=null;
            if(voices!=null)for(android.speech.tts.Voice voice:voices){if(voice.getLocale().getLanguage().equals("en")&&!voice.isNetworkConnectionRequired()){offline=voice;break;}}
            if(offline==null){toast("手机缺少英语语音包，请安装离线英语语音包");return;}
            tts.setVoice(offline);
            if(tts.speak(w.optString("prompt"),TextToSpeech.QUEUE_FLUSH,null,"word")==TextToSpeech.ERROR)toast("无法播放发音，请检查手机语音引擎");
        });
        button("查看释义与例句",()->wordRevealed(w));
        link(w.optInt("starred")==1?"取消收藏":"收藏",()-> {
            db.edit("item",w.optLong("id"),LearningStore.obj("starred",w.optInt("starred")==1?0:1));
            word(db.one("SELECT * FROM item WHERE id=?",""+w.optLong("id")));
        }
        );
    }
    private void wordRevealed(JSONObject w) {
        screen="word";
        page("单词学习 · 自评",true);
        heading(w.optString("prompt"));
        text(w.optString("meaning")+"\n\n"+w.optString("example"),READING,INK);
        note("仅为揭示答案后的自评，与实际测试分开。");
        String[] labels= {
            "忘记","模糊","认识"
        }
        ;
        for(int i=0;i<3;i++) {
            final int r=i;
            button(labels[i],()-> {
                db.insert("self_rating",LearningStore.obj("item_id",w.optLong("id"),"rating",r,"at",System.currentTimeMillis()));
                toast("自评已保存");
                wordList();
            }
            );
        }
        for(String skill:new String[] {
            "recognition","recall","context"
        }
        ) {
            JSONObject s=db.state(w.optLong("id"),skill);
            note(skillName(skill)+"："+(s.optInt("seen")==0?"未测试":percent(s.optDouble("mastery"))+" · 下次复习 "+date.format(new Date(s.optLong("due_at")))));
        }
        button("开始拼写测试",()->start("recall",daily(),"adaptive",0));
    }
    private void sessionReport(long id) {
        if(!"sessionReport".equals(screen))sessionReportFromReport="report".equals(screen);
        screen="sessionReport";
        sessionId=id;
        JSONObject s=db.one("SELECT * FROM session WHERE id=?",""+id);
        libraryId=s.optLong("library_id");
        page("本轮练习报告",true);
        int total=0;
        try {
            total=new JSONArray(s.optString("plan")).length();
        }
        catch(JSONException ignored) {
        }
        long done=db.count("SELECT COUNT(*) n FROM attempt WHERE session_id=?",""+id),correct=db.count("SELECT COUNT(*) n FROM attempt WHERE session_id=? AND correct=1",""+id),verify=db.count("SELECT COUNT(*) n FROM attempt WHERE session_id=? AND correct=1 AND confidence<2",""+id);
        card(done==0?"暂无作答":percent((double)correct/done)+" 正确率","答对 "+correct+" · 答错 "+(done-correct)+" · 未作答 "+(total-done)+"\n答对待验证 "+verify+" 条（包含在答对中）",null);
        note("仅统计提交过的答案，未作答不计入正确率。选题方式："+strategyName(s.optString("strategy")));
        if("diagnostic".equals(s.optString("strategy"))){
            heading("初始学习建议");
            if(done==0)note("尚未提交答案，掌握情况待评估。");
            else {
                JSONObject low=db.one("SELECT p.name,st.mastery,st.seen FROM attempt_point ap JOIN attempt a ON a.id=ap.attempt_id JOIN point p ON p.id=ap.point_id JOIN state st ON st.owner_id=p.id AND st.skill='knowledge' WHERE a.session_id=? ORDER BY st.mastery,p.id LIMIT 1",""+id);
                if(low!=null)card("下一步先巩固："+low.optString("name"),"当前掌握概率估计 "+percent(low.optDouble("mastery"))+" · "+low.optInt("seen")+" 次证据\n根据本次涉及知识点的当前模型估计选取优先关注项，不等于本轮正确率。",null);
                else note("已保存 "+done+" 次真实作答，词汇能力分开评估；优先复习估计较低或到期的能力。");
                note("初测题量有限，未测内容仍待评估。后续练习会持续更新；重做初测不会重置旧状态。");
                if(s.optInt("finished")==1)button("开始自适应巩固",()->start("word".equals(currentLibrary().optString("kind"))?"recall":"question",daily(),"adaptive",0));
            }
        }
        weaknesses(libraryId,0);
        if(s.optInt("finished")==0)button("继续本轮练习",()->practice());
        else if(done>0) {
            sessionChanges(id);
            safely(()->db.createTasks(id));
            heading("推荐巩固任务");
            showTasks(id);
        }
        button("返回今日",()->home(0));
    }
    private String strategyName(String s) {
        return s.equals("card")?"卡片练习":s.equals("diagnostic")?"初始能力测试":s.equals("random")?"随机对照":s.equals("basic")?"基础辨析":s.equals("application")?"应用练习":s.equals("delayed")?"延迟复测":"自适应";
    }
    private String stageName(String s) {
        return s.equals("concept")?"概念回顾与辨析":s.equals("basic")?"基础辨析":s.equals("application")?"应用练习":"延迟复测";
    }
    private void showTasks(long source) {
        showTasks(source,0);
    }
    private void taskPage(int offset) {
        screen="tasks";page("巩固与复测",true);showTasks(0,offset);
        long total=db.count("SELECT COUNT(*) n FROM task t JOIN library l ON l.id=t.library_id WHERE t.completed=0 AND l.archived=0");
        if(offset>0)link("上一页",()->taskPage(offset-20));
        if(offset+20<total)link("下一页",()->taskPage(offset+20));
    }
    private void showTasks(long source,int offset) {
        JSONArray tasks=db.rows("SELECT t.*,l.name library_name,l.kind FROM task t JOIN library l ON l.id=t.library_id WHERE l.archived=0 "+(source>0?"AND source_session=? ":"AND completed=0 ")+"ORDER BY t.id LIMIT 20 OFFSET "+offset,source>0?new String[] {
            ""+source
        }
        :new String[] {
        }
        );
        if(tasks.length()==0)note("暂无待巩固任务。");
        for(int i=0;i<tasks.length();i++) {
            JSONObject task=tasks.optJSONObject(i);
            JSONObject p=db.one("SELECT name FROM point WHERE id=?",""+task.optLong("point_id"));
            String why=p==null?"按本轮单词测试表现复习":"本轮涉及的较薄弱知识点："+p.optString("name");
            String status=task.optInt("completed")==1?"已完成 ✓":task.optLong("due_at")>System.currentTimeMillis()?"安排于 "+date.format(new Date(task.optLong("due_at"))):"待完成";
            card(stageName(task.optString("stage"))+" · "+status,task.optString("library_name")+"\n"+why,()->launchTask(task));
        }
    }
    private void launchTask(JSONObject task) {
        safely(()-> {
            if(task.optInt("completed")==1) {
                toast("此阶段已完成");
                return;
            }
            long tid=task.optLong("id"),source=task.optLong("source_session"),point=task.optLong("point_id");
            String stage=task.optString("stage");
            if(task.optLong("due_at")>System.currentTimeMillis()) {
                toast("复测尚未到期，请在安排时间后回来");
                return;
            }
            String previous=stage.equals("basic")?"concept":stage.equals("application")?"basic":stage.equals("delayed")?"application":"";
            if(!previous.isEmpty()&&db.count("SELECT COUNT(*) n FROM task WHERE source_session=? AND stage=? AND completed=1",""+source,previous)==0) {
                toast("请先完成上一个巩固阶段");
                return;
            }
            libraryId=task.optLong("library_id");
            if(stage.equals("concept")) {
                if(point>0)point(point);
                else wordList();
                button("已回顾学习内容 · 完成本阶段",()-> {
                    db.edit("task",tid,LearningStore.obj("completed",1));
                    sessionReport(source);
                }
                );
                return;
            }
            if(!task.isNull("practice_session")) {
                JSONObject active=db.one("SELECT * FROM session WHERE id=? AND finished=0",""+task.optLong("practice_session"));
                if(active!=null) {
                    sessionId=active.optLong("id");
                    practice();
                    return;
                }
            }
            boolean word=currentLibrary().optString("kind").equals("word");
            String mode=word?(stage.equals("application")?"context":"recall"):"question";
            String filter=word?"adaptive":stage;
            sessionId=db.start(libraryId,mode,Math.min(daily(),5),filter,point);
            if(sessionId==0) {
                toast("此阶段题库不足，请补充对应难度内容后继续");
                return;
            }
            db.edit("task",tid,LearningStore.obj("practice_session",sessionId));
            db.edit("session",sessionId,LearningStore.obj("strategy",stage));
            practice();
        }
        );
    }
    private void report() {
        screen="report";
        page("学习报告",true);
        headline("让每次练习，都有迹可循。");
        JSONArray libraries=db.rows("SELECT * FROM library WHERE archived=0 ORDER BY id");
        String[] names=new String[libraries.length()+1];
        names[0]="全部知识库";
        for(int i=0;i<libraries.length();i++)names[i+1]=libraries.optJSONObject(i).optString("name");
        Spinner libraryFilter=spinner(names),period=spinner(new String[] {
            "近 7 天","近 30 天","全部记录"
        }
        );
        period.setSelection(reportDays==7?0:reportDays==0?2:1);
        for(int i=0;i<libraries.length();i++)if(libraries.optJSONObject(i).optLong("id")==reportLibraryId)libraryFilter.setSelection(i+1);
        body.removeView(libraryFilter);body.removeView(period);
        LinearLayout filters=new LinearLayout(this);filters.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams libraryParams=new LinearLayout.LayoutParams(0,-2,1.2f);libraryParams.setMarginEnd(dp(8));
        filters.addView(libraryFilter,libraryParams);filters.addView(period,new LinearLayout.LayoutParams(0,-2,1));
        LinearLayout.LayoutParams filterParams=new LinearLayout.LayoutParams(-1,-2);filterParams.bottomMargin=dp(14);body.addView(filters,filterParams);
        LinearLayout area=new LinearLayout(this);
        area.setOrientation(LinearLayout.VERTICAL);
        body.addView(area);
        AdapterView.OnItemSelectedListener listener=new AdapterView.OnItemSelectedListener() {
            public void onItemSelected(AdapterView<?> p,View v,int n,long id) {
                int selected=libraryFilter.getSelectedItemPosition();
                reportLibraryId=selected==0?0:libraries.optJSONObject(selected-1).optLong("id");
                reportDays=period.getSelectedItemPosition()==0?7:period.getSelectedItemPosition()==1?30:0;
                renderReport(area,reportDays);
            }
            public void onNothingSelected(AdapterView<?> p) {
            }
        }
        ;
        libraryFilter.setOnItemSelectedListener(listener);
        period.setOnItemSelectedListener(listener);
        renderReport(area,reportDays);
    }
    private void renderReport(LinearLayout area,int days) {
        area.removeAllViews();
        LinearLayout save=body;
        body=area;
        long since=days==0?0:System.currentTimeMillis()-days*86400000L;
        String where=" FROM attempt a JOIN session s ON s.id=a.session_id WHERE a.at>=?"+(reportLibraryId==0?"":" AND s.library_id="+reportLibraryId);
        long n=db.count("SELECT COUNT(*) n"+where,""+since),c=db.count("SELECT COUNT(*) n"+where+" AND a.correct=1",""+since),coverage=db.count("SELECT COUNT(DISTINCT a.item_id) n"+where,""+since);
        if(n==0)emptyState("暂无学习记录","完成练习后，这里会展示你的学习变化。可切换时间范围或知识库查看已有记录。");
        else metrics(new String[]{""+n,""+coverage,percent((double)c/n)},new String[]{"提交次数","测试内容","正确率"});
        note("学习轮次："+db.count("SELECT COUNT(DISTINCT s.id) n"+where,""+since)+" 轮（所选期间有实际提交的练习）");
        note("正确率 = 答对次数 / 已提交次数；知识掌握概率由下方 BKT 状态计算，两者含义不同。");
        probabilityTrend(reportLibraryId,since);
        if(n>0) {
            heading("近七天学习趋势");
            String[] dates=new String[7];int[] attempts=new int[7],correct=new int[7];
            Calendar day=Calendar.getInstance();day.set(Calendar.HOUR_OF_DAY,0);day.set(Calendar.MINUTE,0);day.set(Calendar.SECOND,0);day.set(Calendar.MILLISECOND,0);day.add(Calendar.DAY_OF_YEAR,-6);
            for(int i=0;i<7;i++) {
                long from=day.getTimeInMillis();dates[i]=new SimpleDateFormat("M/d",Locale.CHINA).format(day.getTime());
                day.add(Calendar.DAY_OF_YEAR,1);long to=day.getTimeInMillis();
                JSONObject observed=db.one("SELECT COUNT(*) n,COALESCE(SUM(a.correct),0) c FROM attempt a JOIN session s ON s.id=a.session_id WHERE a.at>=? AND a.at<?"+(reportLibraryId==0?"":" AND s.library_id="+reportLibraryId),""+from,""+to);
                attempts[i]=observed.optInt("n");correct[i]=observed.optInt("c");
            }
            LinearLayout reportBody=body;body=surface(android.graphics.Color.WHITE);
            body.addView(new LearningTrendView(this,dates,attempts,correct),new LinearLayout.LayoutParams(-1,dp(130)+(int)(TypeScale.pixels(this,CAPTION)*4)));
            note("日期："+dates[0]+"–"+dates[6]+" · 作答次数（次）");
            note("柱高为作答次数，下方为当天正确率；无作答的日期不计算正确率。");
            body=reportBody;
        }
        note("掌握估计基于全部历史，不等于期间正确率。参数未经学习数据校准。");
        if(reportLibraryId==0){heading("全部知识库 · 掌握分布");masteryDistribution(0);note("上方选择知识库，可查看薄弱点与作答依据。");}
        JSONArray libs=reportLibraryId==0?new JSONArray():db.rows("SELECT * FROM library WHERE archived=0 AND id=?",""+reportLibraryId);
        for(int i=0;i<libs.length();i++) {
            JSONObject l=libs.optJSONObject(i);
            if(reportLibraryId>0&&l.optLong("id")!=reportLibraryId)continue;
            heading(l.optString("name"));
            masteryDistribution(l.optLong("id"));
            weaknesses(l.optLong("id"),since);
        }
        heading("最近练习");
        JSONArray sessions=db.rows("SELECT s.*,l.name,(SELECT COUNT(*) FROM attempt a WHERE a.session_id=s.id) answers FROM session s JOIN library l ON l.id=s.library_id WHERE (s.created_at>=? OR EXISTS(SELECT 1 FROM attempt recent WHERE recent.session_id=s.id AND recent.at>=?))"+(reportLibraryId==0?"":" AND s.library_id="+reportLibraryId)+" ORDER BY s.id DESC LIMIT 20",""+since,""+since);
        for(int i=0;i<sessions.length();i++) {
            JSONObject s=sessions.optJSONObject(i);
            card(s.optString("name"),date.format(new Date(s.optLong("created_at")))+" · 已提交 "+s.optInt("answers")+" 条",()->sessionReport(s.optLong("id")));
        }
        body=save;
    }
    private void weaknesses(long lid,long since) {
        JSONObject l=db.one("SELECT * FROM library WHERE id=?",""+lid);
        boolean word=l.optString("kind").equals("word");
        JSONArray list=word?db.rows("SELECT i.id,i.prompt name,s.* FROM item i JOIN state s ON s.owner_id=i.id AND s.skill IN ('recognition','recall','context') WHERE i.library_id=? AND i.archived=0 ORDER BY s.mastery LIMIT 12",""+lid):db.rows("SELECT p.id,p.name,s.* FROM point p JOIN state s ON s.owner_id=p.id AND s.skill='knowledge' WHERE p.library_id=? AND p.archived=0 ORDER BY s.mastery LIMIT 12",""+lid);
        if(list.length()==0) {
            note("暂无测试证据，尚未估计掌握。");
            return;
        }
        for(int i=0;i<list.length();i++) {
            JSONObject r=list.optJSONObject(i);
            long owner=r.optLong("owner_id");
            String skill=r.optString("skill");
            JSONArray evidence=word?db.rows("SELECT correct,confidence,at FROM attempt WHERE item_id=? AND skill=? AND at>=? ORDER BY at DESC LIMIT 2",""+owner,skill,""+since):db.rows("SELECT a.correct,a.confidence,a.at FROM attempt a JOIN attempt_point p ON p.attempt_id=a.id WHERE p.point_id=? AND a.at>=? ORDER BY a.at DESC LIMIT 2",""+owner,""+since);
            String why=evidence.length()==0?"所选期间无证据，显示历史估计":evidence.length()<2?"期间仅一次作答，需更多验证":"最近两次："+(evidence.optJSONObject(0).optInt("correct")==1?"对":"错")+" / "+(evidence.optJSONObject(1).optInt("correct")==1?"对":"错");
            if(r.optLong("due_at")<=System.currentTimeMillis())why+=" · 复习已到期";
            JSONObject first=db.one("SELECT before_value FROM state_change WHERE owner_id=? AND skill=? AND at>=? ORDER BY id LIMIT 1",""+owner,skill,""+since);
            JSONObject last=db.one("SELECT after_value FROM state_change WHERE owner_id=? AND skill=? AND at>=? ORDER BY id DESC LIMIT 1",""+owner,skill,""+since);
            if(first!=null&&last!=null) {
                long delta=Math.round((last.optDouble("after_value")-first.optDouble("before_value"))*100);
                why+="\n期间估计变化："+(delta>=0?"+":"")+delta+" 个百分点";
            }
            final long id=owner;
            card(r.optString("name")+(word?" · "+skillName(skill):""),"估计掌握 "+percent(r.optDouble("mastery"))+" · 累计 "+r.optInt("seen")+" 次证据\n"+why,()-> {
                libraryId=lid;
                if(word)word(db.one("SELECT * FROM item WHERE id=?",""+id));
                else point(id);
            }
            );
            progress(100,(int)(r.optDouble("mastery")*100));
        }
    }
    private void masteryDistribution(long library) {
        boolean word=library>0&&db.one("SELECT kind FROM library WHERE id=?",""+library).optString("kind").equals("word");
        JSONArray states=library==0?db.rows("SELECT s.mastery,s.seen FROM state s JOIN point p ON p.id=s.owner_id JOIN library l ON l.id=p.library_id WHERE p.archived=0 AND l.archived=0 AND l.kind='question' AND s.skill='knowledge' UNION ALL SELECT s.mastery,s.seen FROM state s JOIN item i ON i.id=s.owner_id JOIN library l ON l.id=i.library_id WHERE i.archived=0 AND l.archived=0 AND l.kind='word' AND s.skill IN ('recognition','recall','context')"):
                word?db.rows("SELECT s.mastery,s.seen FROM state s JOIN item i ON i.id=s.owner_id WHERE i.library_id=? AND i.archived=0 AND s.skill IN ('recognition','recall','context')",""+library):db.rows("SELECT s.mastery,s.seen FROM state s JOIN point p ON p.id=s.owner_id WHERE p.library_id=? AND p.archived=0 AND s.skill='knowledge'",""+library);
        long total=library==0?db.count("SELECT COUNT(*) n FROM point p JOIN library l ON l.id=p.library_id WHERE p.archived=0 AND l.archived=0 AND l.kind='question'")+3*db.count("SELECT COUNT(*) n FROM item i JOIN library l ON l.id=i.library_id WHERE i.archived=0 AND l.archived=0 AND l.kind='word'"):
                word?3*db.count("SELECT COUNT(*) n FROM item WHERE library_id=? AND archived=0",""+library):db.count("SELECT COUNT(*) n FROM point WHERE library_id=? AND archived=0",""+library);
        if(total==0) {
            note("暂无可追踪内容。");
            return;
        }
        int[] counts=new int[4];
        counts[3]=(int)total-states.length();
        for(int i=0;i<states.length();i++) {
            double mastery=states.optJSONObject(i).optDouble("mastery");
            counts[mastery>=.8?0:mastery>=.6?1:2]++;
        }
        heading("掌握状态分布");
        body.addView(new MasteryChart(this,counts),new LinearLayout.LayoutParams(-1,-2));
        note(library==0?"按知识点和词汇能力状态计数，未测试不等于未掌握。":word?"按每个单词的三种能力分别计数，未测试不等于未掌握。":"按知识点计数，未测试不等于未掌握。阈值为初始展示设置。");
    }
    private void sessionChanges(long session) {
        JSONArray changes=db.rows("SELECT c.owner_id,c.skill,MIN(c.id) first_id,MAX(c.id) last_id FROM state_change c JOIN attempt a ON a.id=c.attempt_id WHERE a.session_id=? GROUP BY c.owner_id,c.skill",""+session);
        if(changes.length()==0)return;
        heading("与本轮开始时的估计变化");
        for(int i=0;i<changes.length();i++) {
            JSONObject r=changes.optJSONObject(i);
            JSONObject first=db.one("SELECT before_value FROM state_change WHERE id=?",""+r.optLong("first_id")),last=db.one("SELECT after_value FROM state_change WHERE id=?",""+r.optLong("last_id"));
            boolean knowledge=r.optString("skill").equals("knowledge");
            JSONObject content=db.one(knowledge?"SELECT name FROM point WHERE id=?":"SELECT prompt name FROM item WHERE id=?",""+r.optLong("owner_id"));
            note((content==null?"内容已移除":content.optString("name"))+(knowledge?"":" · "+skillName(r.optString("skill")))+"："+percent(first.optDouble("before_value"))+" → "+percent(last.optDouble("after_value")));
        }
    }
    private void settings() {
        page("我的",false);
        profileHeader();
        LinearLayout settingsBody=body;
        link("学习报告",()->home(2));
        heading("内容与数据");body=surface(android.graphics.Color.WHITE);
        link("题库管理",()->manageLibraries());
        link("导出学习数据备份",()->safely(()->export(learningBackup().toString(2),"zhixue-backup.json")));
        link("恢复学习数据备份",()->confirm("恢复备份","将覆盖当前内容与学习记录。请先导出备份。参考资料文件不包含在 JSON 备份中，需要重新添加。",()->pick("restore","application/json")));
        link("恢复归档内容",()->archived());
        link("使用帮助",()->help());
        link("算法说明",()->algorithm());body=settingsBody;
        if(accountSession!=null) {
            heading("账号");body=surface(android.graphics.Color.WHITE);
            link("退出登录",()->confirm("退出登录","退出后需要联网登录才能继续学习。已提交的记录仍保存在当前账号的本机学习空间。",()->authGate.logout()));
            body=settingsBody;
        }
        note("记录保存在这台手机。建议定期导出备份。");
    }
    private JSONObject learningBackup() throws JSONException {
        JSONObject result=db.backup();
        result.put("learning_preferences",LearningStore.obj("daily",daily(),"subject",getPreferences(MODE_PRIVATE).getString("focusSubject","全部学科"),"goal",getPreferences(MODE_PRIVATE).getString("learningGoal","打好基础")));
        return result;
    }
    private void help() {
        screen="help";page("使用帮助",true);
        headline("先选内容，后续交给学习证据。");
        link("重新查看三步引导",()->{onboardingReplay=true;welcome();});
        card("1 · 开始今天的学习","今日主按钮会恢复未完成练习，然后安排可执行复习、到期内容和目标学科练习。初次学习使用少量题建立起点。",null);
        card("2 · 在知识库专项练习","按学科 → 知识库 → 知识点 → 题目浏览；英语支持识别、拼写回忆与语境三种独立能力。",null);
        card("3 · 查看学习变化","在“我的 → 学习报告”查看学习记录。正确率是已提交答案的统计；掌握概率是 BKT 模型估计。点击每题“为什么推荐？”查看真实数据依据。无证据显示待评估。",null);
        card("保存与数据管理","练习返回可保存退出；已提交记录会保留，未提交输入需重新填写。题库编辑在“我的 → 题库管理”，建议定期备份。",null);
        link("算法说明",()->algorithm());
    }
    private void showRecommendation(long item,String mode,String strategy) {
        safely(()->{
            JSONObject why=db.recommendation(item,mode,strategy);
            String message=why.optString("summary")+"\n\n按当前数据解释；若已提交，本次显示的是更新后的估计。随机对照不按掌握概率排序。";
            TypeScale.dialog(new androidx.appcompat.app.AlertDialog.Builder(this).setTitle("为什么推荐？").setMessage(message).setPositiveButton("知道了",null).create());
        });
    }
    private JSONArray trackedStates(long library) {
        String scope=library==0?"":" AND l.id="+library;
        return db.rows("SELECT p.id owner_id,p.name,l.name library_name,s.skill,s.mastery,s.seen FROM state s JOIN point p ON p.id=s.owner_id JOIN library l ON l.id=p.library_id WHERE s.skill='knowledge' AND s.seen>0 AND p.archived=0 AND l.archived=0"+scope+" UNION ALL SELECT i.id owner_id,i.prompt name,l.name library_name,s.skill,s.mastery,s.seen FROM state s JOIN item i ON i.id=s.owner_id JOIN library l ON l.id=i.library_id WHERE s.skill IN ('recognition','recall','context') AND s.seen>0 AND i.archived=0 AND l.archived=0"+scope+" ORDER BY mastery,owner_id");
    }
    private void probabilityTrend(long library,long since) {
        heading("掌握概率变化趋势");
        JSONArray states=trackedStates(library);
        if(states.length()==0){note("待评估：尚无知识点或词汇能力的答题证据。初始值 25% 只是模型先验，不作为实测结果展示。");return;}
        String[] names=new String[states.length()];
        for(int i=0;i<states.length();i++){
            JSONObject s=states.optJSONObject(i);names[i]=s.optString("name")+("knowledge".equals(s.optString("skill"))?"":" · "+skillName(s.optString("skill")));
        }
        Spinner selected=spinner(names);LinearLayout graph=new LinearLayout(this);graph.setOrientation(LinearLayout.VERTICAL);body.addView(graph);
        java.util.function.IntConsumer render=index->{
            graph.removeAllViews();LinearLayout previous=body;body=graph;
            JSONObject s=states.optJSONObject(index);long owner=s.optLong("owner_id");String skill=s.optString("skill");
            text("掌握概率估计 "+percent(s.optDouble("mastery"))+" · "+s.optInt("seen")+" 次证据",SECTION,GREEN);
            renderMasteryGraph(owner,skill,since);
            link("查看计算过程与全部变化",()->masteryHistory(owner,skill,s.optString("name")));
            body=previous;
        };
        selected.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            public void onItemSelected(AdapterView<?> p,View v,int position,long id){render.accept(position);}
            public void onNothingSelected(AdapterView<?> p){}
        });render.accept(0);
        note("曲线来自同一个知识点/词汇能力的状态更新，当前值使用全部历史；模型参数未经校准，不等于正确率。");
        if(library==0){
            heading("优先关注的知识点与能力");
            for(int i=0;i<Math.min(4,states.length());i++){
                JSONObject s=states.optJSONObject(i);card(s.optString("name"),"掌握概率估计 "+percent(s.optDouble("mastery"))+" · "+s.optInt("seen")+" 次证据\n按当前概率从低到高排列，点击查看变化与计算。",()->masteryHistory(s.optLong("owner_id"),s.optString("skill"),s.optString("name")));
            }
        }
    }
    private void renderMasteryGraph(long owner,String skill,long since) {
        JSONArray reverse=db.rows("SELECT * FROM state_change WHERE owner_id=? AND skill=? AND at>=? ORDER BY id DESC LIMIT 30",""+owner,skill,""+since);
        if(reverse.length()==0){note("此时间范围暂无状态更新，可切换全部记录。旧版本未记录的变化不补造。");return;}
        String[] labels=new String[reverse.length()+1];double[] probabilities=new double[labels.length];
        JSONObject first=reverse.optJSONObject(reverse.length()-1);labels[0]="更新前";probabilities[0]=first.optDouble("before_value");
        for(int i=0;i<reverse.length();i++){
            JSONObject r=reverse.optJSONObject(reverse.length()-1-i);labels[i+1]=new SimpleDateFormat("M/d",Locale.CHINA).format(new Date(r.optLong("at")));probabilities[i+1]=r.optDouble("after_value");
        }
        body.addView(new MasteryHistoryView(this,labels,probabilities),new LinearLayout.LayoutParams(-1,-2));
        note("显示最近 "+reverse.length()+" 次实际更新及首条更新前状态；横轴按更新顺序排列。");
    }
    private void masteryHistory(long owner,String skill,String name) {
        screen="masteryHistory";page("掌握概率与计算过程",true);
        headline(name);JSONObject state=db.state(owner,skill);
        note(state.optInt("seen")==0?"待评估：尚无实际作答证据。":"当前概率估计 "+percent(state.optDouble("mastery"))+" · "+state.optInt("seen")+" 次证据");
        renderMasteryGraph(owner,skill,0);
        heading("最近计算记录");
        JSONArray changes=db.rows("SELECT c.*,a.correct,a.confidence FROM state_change c JOIN attempt a ON a.id=c.attempt_id WHERE c.owner_id=? AND c.skill=? ORDER BY c.id DESC LIMIT 8",""+owner,skill);
        for(int i=0;i<changes.length();i++){
            JSONObject c=changes.optJSONObject(i);
            String detail="更新前 "+percent(c.optDouble("before_value"))+" → 更新后 "+percent(c.optDouble("after_value"));
            if(c.isNull("posterior"))detail+="\n历史版本仅保存前后概率，缺少参数快照，不反推计算过程。";
            else detail+=String.format(Locale.CHINA,"\n先验 %.4f · 后验 %.4f\ng=%.2f · s=%.2f · t=%.2f\n后验 + (1−后验)×t = %.4f\n模型 %s",c.optDouble("before_value"),c.optDouble("posterior"),c.optDouble("guess"),c.optDouble("slip"),c.optDouble("learn"),c.optDouble("after_value"),c.optString("model_version"));
            card(date.format(new Date(c.optLong("at")))+" · "+(c.optInt("correct")==1?"答对":"答错")+" · "+confidenceName(c.optInt("confidence")),detail,null);
        }
        link("算法说明",()->algorithm());
    }
    private void archived() {
        screen="archived";
        page("归档内容",true);
        JSONArray libs=db.rows("SELECT * FROM library WHERE archived=1");
        for(int i=0;i<libs.length();i++) {
            JSONObject l=libs.optJSONObject(i);
            card(l.optString("name"),"点击恢复知识库",()-> {
                db.edit("library",l.optLong("id"),LearningStore.obj("archived",0));
                archived();
            }
            );
        }
        JSONArray items=db.rows("SELECT i.*,l.name library_name FROM item i JOIN library l ON i.library_id=l.id WHERE i.archived=1");
        for(int i=0;i<items.length();i++) {
            JSONObject x=items.optJSONObject(i);
            card(x.optString("prompt"),x.optString("library_name")+" · 点击恢复",()-> {
                db.edit("item",x.optLong("id"),LearningStore.obj("archived",0));
                archived();
            }
            );
        }
        if(libs.length()+items.length()==0)note("暂无归档内容。");
    }
    private void algorithm() {
        screen="algorithm";
        page("算法与数据说明",true);
        heading("信心辅助贝叶斯知识追踪");
        text("先验 p(L)，猜对参数 g、失误参数 s、学习转移 t。\n答对：后验 = p(1−s) / [p(1−s)+(1−p)g]\n答错：后验 = ps / [ps+(1−p)(1−g)]\n更新后 = 后验 + (1−后验)t，裁剪到 0.01–0.99。",READING,INK);
        note("初始 p=.25，t=.08，s=.10；确定/犹豫/猜测对应 g=.20/.28/.40。信心条件化是本项目 BKT 扩展，参数未经学习样本拟合；不含遗忘转移。多知识点题分别更新各点，不是联合归因模型。");
        LearningEngine.Trace correct=LearningEngine.trace(.25,true,2),wrong=LearningEngine.trace(.25,false,2);
        card("可复算示例",String.format(Locale.CHINA,"先验25%%，确定作答 g=.20、s=.10、t=.08：\n答对：后验 %.6f → 更新 %.6f\n答错：后验 %.6f → 更新 %.6f\n同一次作答正确率只能是0或100%%，模型估计是另一项指标。",correct.posterior,correct.after,wrong.posterior,wrong.after),null);
        heading("自适应选题");
        text("薄弱程度45% + 到期程度25% + 间隔15% + 难度匹配15% − 近24小时重复次数×0.25。掌握估计<45%目标难度1、45%–75%目标2、≥75%目标3；综合排序仍优先薄弱点。\n先选非近期题；不足时提示并回退近期题，同轮不重复凑数。约1/3新内容，剩余旧内容；提交后保留已答位置，动态调整未答候选。初测优先知识点覆盖，随机对照不按此分数排序。",READING,INK);
        heading("单词复习");
        text("识别、回忆、语境分别更新，不能互相替代。答错隔 1 天复习；答对但不确定安排 1–3 天；确定答对从 1 天起逐次翻倍，最多 60 天。延期保留到期状态，不自动算完成。自评单独保存。",READING,INK);
        heading("内容与学习证据");
        text("历史保留题干、答案、信心、能力、时间与知识点关联。收藏、自评、错误和待验证分别统计。用时仅辅助分析。算法在手机端执行，无外部 AI 调用。",READING,INK);
    }
    private void references(long point) {
        referencePoint=point;
        screen="references";
        page("参考资料",true);
        note("仅保存和查看资料，不自动理解或生成题目。文件复制到手机应用目录，卸载会移除。");
        if(managementContext)button("＋ 添加参考资料",()->pick("reference","*/*"));
        JSONArray refs=point==0?db.rows("SELECT * FROM reference WHERE library_id=? ORDER BY id DESC",""+libraryId):db.rows("SELECT * FROM reference WHERE library_id=? AND point_id=? ORDER BY id DESC",""+libraryId,""+point);
        for(int i=0;i<refs.length();i++) {
            JSONObject r=refs.optJSONObject(i);
            card(r.optString("name"),"点击使用手机查看应用打开",()->safely(()-> {
                File f=new File(getFilesDir(),r.optString("path"));
                if(!f.getCanonicalPath().startsWith(new File(getFilesDir(),"references").getCanonicalPath()+File.separator))
                    throw new Exception("资料不属于当前学习空间，请重新添加");
                if(!f.exists())throw new Exception("文件缺失，请重新添加");
                Uri u=FileProvider.getUriForFile(this,getPackageName()+".files",f);
                startActivity(new Intent(Intent.ACTION_VIEW).setDataAndType(u,r.optString("mime")).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION));
            }
            ));
        }
        if(refs.length()==0)note("暂无参考资料。");
    }
    private void pick(String action,String mime) {
        if(busy) {
            toast("正在处理文件，请稍候");
            return;
        }
        fileAction=action;
        Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.setType(mime);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        startActivityForResult(i,41);
    }
    private void export(String data,String name) {
        if(busy) {
            toast("正在处理文件，请稍候");
            return;
        }
        fileAction="export";
        try(FileOutputStream pending=new FileOutputStream(new File(getCacheDir(),"pending-export.json"))) {
            pending.write(data.getBytes(StandardCharsets.UTF_8));
        }
        catch(IOException e) {
            toast("无法准备导出文件");
            return;
        }
        Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);
        i.setType("application/json");
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.putExtra(Intent.EXTRA_TITLE,name);
        startActivityForResult(i,42);
    }
    @Override protected void onActivityResult(int req,int result,Intent data) {
        super.onActivityResult(req,result,data);
        if(req==AiGenerationController.PICK_FILES){if(result==RESULT_OK&&data!=null&&aiController!=null)aiController.selected(data);return;}
        if(result!=RESULT_OK||data==null||data.getData()==null)return;
        Uri uri=data.getData();
        String action=fileAction;
        long lid=libraryId,pid=referencePoint;
        busy=true;
        toast("正在处理文件…");
        worker.execute(()-> {
            String message="";
            try {
                if(req==42) {
                    try(OutputStream out=getContentResolver().openOutputStream(uri)) {
                        if(out==null)throw new IOException("无法写入文件");
                        try(InputStream pending=new FileInputStream(new File(getCacheDir(),"pending-export.json"))) {
                            copyLimited(pending,out,20*1024*1024);
                        }
                    }
                    message="文件已导出";
                }
                else if(action.equals("reference")) {
                    String name="参考资料",mime=getContentResolver().getType(uri);
                    try(android.database.Cursor c=getContentResolver().query(uri,null,null,null,null)) {
                        if(c!=null&&c.moveToFirst()) {
                            int col=c.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME);
                            if(col>=0)name=c.getString(col);
                        }
                    }
                    String path="references/"+UUID.randomUUID()+"-"+name.replaceAll("[^\\p{L}\\p{N}._-]","_");
                    File f=new File(getFilesDir(),path);
                    if(!f.getParentFile().exists()&&!f.getParentFile().mkdirs())throw new IOException("无法建立目录");
                    try(InputStream in=getContentResolver().openInputStream(uri);OutputStream out=new FileOutputStream(f)) {
                        copyLimited(in,out,30*1024*1024);
                    }
                    catch(Exception e) {
                        f.delete();
                        throw e;
                    }
                    db.insert("reference",LearningStore.obj("library_id",lid,"point_id",pid==0?JSONObject.NULL:pid,"name",name,"path",path,"mime",mime==null?"application/octet-stream":mime));
                    message="参考资料已保存";
                }
                else {
                    ByteArrayOutputStream out=new ByteArrayOutputStream();
                    try(InputStream in=getContentResolver().openInputStream(uri)) {
                copyLimited(in,out,(action.equals("restore")?20:5)*1024*1024);
                    }
                    JSONObject json=new JSONObject(out.toString("UTF-8"));
                    if(action.equals("restore")) {
                        db.restore(json);
                        JSONObject preferences=json.optJSONObject("learning_preferences");
                        if(preferences!=null){
                            int amount=preferences.optInt("daily",daily());
                            if(amount>=5&&amount<=50)getPreferences(MODE_PRIVATE).edit().putInt("daily",amount).apply();
                            saveGoal(preferences.optString("subject","全部学科"),preferences.optString("goal","打好基础"));
                        }
                        message="数据已恢复，请重新添加参考资料";
                    }
                    else message=db.importContent(json);
                }
            }
            catch(Exception e) {
                message="文件处理失败："+e.getMessage();
            }
            final String m=message;
            runOnUiThread(()-> {
                if(isFinishing()||isDestroyed())return;
                busy=false;
                toast(m);
                if(action.equals("reference")) {
                    libraryId=lid;
                    references(pid);
                }
                else if(action.equals("content"))manageLibraries();
                else if(action.equals("restore"))home(3);
            }
            );
        }
        );
    }
    private void copyLimited(InputStream in,OutputStream out,int max)throws IOException {
        if(in==null)throw new IOException("无法读取文件");
        byte[] b=new byte[8192];
        int count,total=0;
        while((count=in.read(b))!=-1) {
            total+=count;
            if(total>max)throw new IOException("文件过大，限制 "+max/1024/1024+" MB");
            out.write(b,0,count);
        }
    }
    @Override protected void back() {
        if(busy) {
            toast("正在处理文件，请稍候");
            return;
        }
        if(screen.equals("practice")) {
            TypeScale.dialog(new androidx.appcompat.app.AlertDialog.Builder(this).setTitle("离开练习？").setMessage("已提交答案和位置已保存，未提交输入需重新填写。").setNegativeButton("继续练习",null).setNeutralButton("结束并查看报告",(d,w)-> {
                db.edit("session",sessionId,LearningStore.obj("finished",2));
                sessionReport(sessionId);
            }
            ).setPositiveButton("保存并退出",(d,w)->home(0)).create());
        }
        else if(screen.equals("welcome")){if(onboardingStep>0)onboarding(onboardingStep-1);else finishOnboarding();}
        else if(screen.equals("home")){if(tab==0)finish();else home(0);}
        else if(screen.equals("ai"))closeAi();
        else if(screen.equals("report"))home(tab);
        else if(screen.equals("sessionReport")){if(sessionReportFromReport)home(2);else home(0);}
        else if(screen.equals("todayPlans")||screen.equals("tasks")||screen.equals("resumeList")||screen.equals("due"))home(0);
        else if(screen.equals("manageLibraries"))home(3);
        else if(screen.equals("manageLibrary"))manageLibraries();
        else if(screen.equals("libraryForm")){if(managementContext)manageLibraries();else home(1);}
        else if(screen.equals("library"))home(1);
        else if(screen.equals("masteryHistory"))home(2);
        else if(screen.equals("itemDetail"))showItemBrowser(itemFilter,itemPoint,itemQuery,itemOffset);
        else if(screen.equals("itemList")&&itemPoint>=0)contentOutline();
        else if(screen.equals("archived")||screen.equals("algorithm")||screen.equals("help"))home(3);
        else if(libraryId>0){if(managementContext)manageLibrary(libraryId);else librarySection(libraryId,librarySection);}
        else home(0);
    }
}
