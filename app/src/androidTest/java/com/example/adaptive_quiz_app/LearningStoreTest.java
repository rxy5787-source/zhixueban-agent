package com.example.adaptive_quiz_app;
import android.content.Context;
import android.content.ContextWrapper;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.example.adaptive_quiz_app.learning.LearningStore;
import org.json.*;
import org.junit.*;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;
@RunWith(AndroidJUnit4.class) public class LearningStoreTest  {
    private LearningStore store;
    private Context context;
    @Before public void setup() throws Exception  {
        Context target=InstrumentationRegistry.getInstrumentation().getTargetContext();
        context=new ContextWrapper(target) {
            @Override public android.database.sqlite.SQLiteDatabase openOrCreateDatabase(String name,int mode,android.database.sqlite.SQLiteDatabase.CursorFactory factory,android.database.DatabaseErrorHandler handler) {
                return super.openOrCreateDatabase("test_"+name,mode,factory,handler);
            }
            @Override public java.io.File getDatabasePath(String name) {
                return super.getDatabasePath("test_"+name);
            }
        }
        ;
        target.deleteDatabase("test_zhixue_learning.db");
        store=new LearningStore(context);
        store.seed();
    }
    @After public void cleanup() {
        store.close();
        InstrumentationRegistry.getInstrumentation().getTargetContext().deleteDatabase("test_zhixue_learning.db");
    }
    @Test public void interruptedSessionDuplicateSubmissionAndHistory() throws Exception  {
        JSONObject l=store.one("SELECT * FROM library WHERE kind='question'");
        long sid=store.start(l.getLong("id"),"question",5,"adaptive",0);
        JSONObject s=store.one("SELECT * FROM session WHERE id=?",""+sid);
        JSONArray plan=new JSONArray(s.getString("plan"));
        java.util.Set<Long> unique=new java.util.HashSet<>();
        for(int i=0;i<plan.length();i++)unique.add(plan.getLong(i));
        assertEquals(plan.length(),unique.size());
        long item=plan.getLong(0);
        JSONObject x=store.one("SELECT * FROM item WHERE id=?",""+item);
        store.submit(sid,0,item,x.getString("prompt"),x.getString("answer"),x.getString("answer"),true,0,"question",2500);
        store.submit(sid,0,item,x.getString("prompt"),x.getString("answer"),x.getString("answer"),true,0,"question",2500);
        assertEquals(1,store.count("SELECT COUNT(*) n FROM attempt"));
        assertEquals(0,store.one("SELECT * FROM session WHERE id=?",""+sid).getInt("position"));
        store.advance(sid);
        assertEquals(1,store.one("SELECT * FROM session WHERE id=?",""+sid).getInt("position"));
        store.archiveLibrary(l.getLong("id"));
        assertEquals(1,store.count("SELECT COUNT(*) n FROM attempt"));
    }
    @Test public void wordAbilitiesAndSelfAssessmentAreIndependent() throws Exception  {
        long lid=store.one("SELECT * FROM library WHERE kind='word'").getLong("id");
        long sid=store.start(lid,"recall",1,"adaptive",0);
        long item=new JSONArray(store.one("SELECT * FROM session WHERE id=?",""+sid).getString("plan")).getLong(0);
        JSONObject x=store.one("SELECT * FROM item WHERE id=?",""+item);
        store.submit(sid,0,item,x.getString("meaning"),x.getString("prompt"),x.getString("prompt"),true,2,"recall",5000);
        assertEquals(1,store.state(item,"recall").getInt("seen"));
        assertEquals(0,store.state(item,"recognition").getInt("seen"));
        assertEquals(0,store.state(item,"context").getInt("seen"));
        store.insert("self_rating",LearningStore.obj("item_id",item,"rating",2,"at",System.currentTimeMillis()));
        assertEquals(1,store.count("SELECT COUNT(*) n FROM attempt"));
    }
    @Test public void invalidImportRollsBackAndDuplicateImportSkips() throws Exception  {
        long n=store.count("SELECT COUNT(*) n FROM item");
        store.importContent(LearningStore.sample());
        assertEquals(n,store.count("SELECT COUNT(*) n FROM item"));
        JSONObject bad=LearningStore.sample();
        bad.getJSONArray("libraries").getJSONObject(0).getJSONArray("items").getJSONObject(1).put("answer","Z");
        try {
            store.importContent(bad);
            fail("invalid answer accepted");
        }
        catch(JSONException expected) {
        }
        assertEquals(n,store.count("SELECT COUNT(*) n FROM item"));
    }
    @Test public void taskChainAndStateHistoryArePersistent() throws Exception {
        long library=store.one("SELECT id FROM library WHERE kind='question'").getLong("id");
        long session=store.start(library,"question",3,"adaptive",0);
        JSONArray plan=new JSONArray(store.one("SELECT plan FROM session WHERE id=?",""+session).getString("plan"));
        for(int i=0;i<plan.length();i++){
            plan=new JSONArray(store.one("SELECT plan FROM session WHERE id=?",""+session).getString("plan"));
            JSONObject item=store.one("SELECT * FROM item WHERE id=?",""+plan.getLong(i));
            store.submit(session,i,item.getLong("id"),item.getString("prompt"),item.getString("answer"),item.getString("answer"),true,2,"question",1000);
            store.advance(session);
        }
        assertEquals(1,store.one("SELECT finished FROM session WHERE id=?",""+session).getInt("finished"));
        assertEquals(4,store.count("SELECT COUNT(*) n FROM task WHERE source_session=?",""+session));
        store.createTasks(session);assertEquals(4,store.count("SELECT COUNT(*) n FROM task WHERE source_session=?",""+session));
        assertEquals(3,store.count("SELECT COUNT(*) n FROM state_change"));
        JSONObject delayed=store.one("SELECT * FROM task WHERE source_session=? AND stage='delayed'",""+session);
        assertTrue(delayed.getLong("due_at")>System.currentTimeMillis());
        long basic=store.start(library,"question",5,"basic",delayed.getLong("point_id"));
        JSONArray basics=new JSONArray(store.one("SELECT plan FROM session WHERE id=?",""+basic).getString("plan"));
        for(int i=0;i<basics.length();i++)assertEquals(1,store.one("SELECT difficulty FROM item WHERE id=?",""+basics.getLong(i)).getInt("difficulty"));
    }
    @Test public void wrongAnswerReranksRemainingItemsAndResumePreservesPlan() throws Exception {
        checkLiveSelection("adaptive",true);
    }
    @Test public void randomControlDoesNotRerankAfterAnswer() throws Exception {
        checkLiveSelection("random",false);
    }
    private void checkLiveSelection(String strategy,boolean adaptive) throws Exception {
        long library=store.one("SELECT id FROM library WHERE kind='question'").getLong("id");
        JSONArray items=store.rows("SELECT * FROM item WHERE library_id=? ORDER BY id LIMIT 3",""+library);
        long first=items.getJSONObject(0).getLong("id"),related=items.getJSONObject(1).getLong("id"),other=items.getJSONObject(2).getLong("id");
        store.getWritableDatabase().execSQL("UPDATE item SET archived=1 WHERE library_id=? AND id NOT IN (?,?,?)",new Object[]{library,first,related,other});
        long shared=store.insert("point",LearningStore.obj("library_id",library,"name","shared","summary","","example","","mnemonic",""));
        long separate=store.insert("point",LearningStore.obj("library_id",library,"name","separate","summary","","example","","mnemonic",""));
        for(long id:new long[]{first,related,other}) {
            store.getWritableDatabase().execSQL("DELETE FROM item_point WHERE item_id=?",new Object[]{id});
            store.insert("item_point",LearningStore.obj("item_id",id,"point_id",id==other?separate:shared));
            store.edit("item",id,LearningStore.obj("difficulty",1));
        }
        for(long id:new long[]{shared,separate})store.insert("state",LearningStore.obj("owner_id",id,"skill","knowledge","mastery",id==shared?.8:.4,"seen",1,"last_at",0,"due_at",0,"interval_days",1));
        // Other was preferred before the error; related should become preferred afterwards.
        String original=new JSONArray().put(first).put(other).put(related).toString();
        long session=store.insert("session",LearningStore.obj("library_id",library,"mode","question","plan",original,"created_at",System.currentTimeMillis(),"strategy",strategy));
        JSONObject item=items.getJSONObject(0);
        store.submit(session,0,first,item.getString("prompt"),item.getString("answer"),"wrong",false,2,"question",1000);
        JSONObject saved=store.one("SELECT * FROM session WHERE id=?",""+session);
        JSONArray result=new JSONArray(saved.getString("plan"));
        assertEquals(first,result.getLong(0));
        assertEquals(adaptive?related:other,result.getLong(1));
        assertEquals(adaptive?other:related,result.getLong(2));
        assertEquals(0,saved.getInt("position"));
        store.submit(session,0,first,item.getString("prompt"),item.getString("answer"),"wrong",false,2,"question",1000);
        assertEquals(1,store.count("SELECT COUNT(*) n FROM attempt WHERE session_id=?",""+session));
        assertEquals(result.toString(),store.one("SELECT plan FROM session WHERE id=?",""+session).getString("plan"));
        store.close();store=new LearningStore(context);
        assertEquals(result.toString(),store.one("SELECT plan FROM session WHERE id=?",""+session).getString("plan"));
        store.advance(session);
        assertEquals(1,store.one("SELECT position FROM session WHERE id=?",""+session).getInt("position"));
    }
    @Test public void diagnosticCoversDifferentPointsAndKeepsItsPersistedPlan() throws Exception {
        long library=store.one("SELECT id FROM library WHERE kind='question'").getLong("id");
        long session=store.start(library,"question",4,"diagnostic",0);
        String saved=store.one("SELECT plan FROM session WHERE id=?",""+session).getString("plan");
        JSONArray plan=new JSONArray(saved);
        java.util.Set<Long> covered=new java.util.HashSet<>(),unique=new java.util.HashSet<>();
        for(int i=0;i<plan.length();i++) {
            unique.add(plan.getLong(i));
            JSONArray points=store.rows("SELECT point_id FROM item_point WHERE item_id=?",""+plan.getLong(i));
            for(int j=0;j<points.length();j++)covered.add(points.getJSONObject(j).getLong("point_id"));
        }
        assertEquals(4,unique.size());assertEquals(4,covered.size());
        JSONObject first=store.one("SELECT * FROM item WHERE id=?",""+plan.getLong(0));
        store.submit(session,0,first.getLong("id"),first.getString("prompt"),first.getString("answer"),"wrong",false,2,"question",1000);
        assertEquals(saved,store.one("SELECT plan FROM session WHERE id=?",""+session).getString("plan"));
        assertTrue(store.recommendation(first.getLong("id"),"question","diagnostic").getString("reason").contains("初始测试"));
    }
    @Test public void recentItemIsAvoidedUntilAlternativesAreExhaustedWithoutDuplicatePadding() throws Exception {
        long library=store.one("SELECT id FROM library WHERE kind='question'").getLong("id");
        long firstSession=store.start(library,"question",1,"adaptive",0);
        long first=new JSONArray(store.one("SELECT plan FROM session WHERE id=?",""+firstSession).getString("plan")).getLong(0);
        JSONObject item=store.one("SELECT * FROM item WHERE id=?",""+first);
        store.submit(firstSession,0,first,item.getString("prompt"),item.getString("answer"),item.getString("answer"),true,2,"question",1000);
        store.advance(firstSession);
        int available=(int)store.count("SELECT COUNT(*) n FROM item WHERE library_id=? AND archived=0",""+library);
        long next=store.start(library,"question",available-1,"adaptive",0);
        JSONArray plan=new JSONArray(store.one("SELECT plan FROM session WHERE id=?",""+next).getString("plan"));
        for(int i=0;i<plan.length();i++)assertNotEquals(first,plan.getLong(i));
        long shortage=store.start(library,"question",100,"adaptive",0);
        plan=new JSONArray(store.one("SELECT plan FROM session WHERE id=?",""+shortage).getString("plan"));
        java.util.Set<Long> ids=new java.util.HashSet<>();
        for(int i=0;i<plan.length();i++)ids.add(plan.getLong(i));
        assertEquals(available,ids.size());assertEquals(available,plan.length());
        assertTrue(store.sessionNotice(shortage,100).contains("不重复填充"));
    }
    @Test public void wrongAnswerCanBringANewEligibleItemIntoTheUnansweredPlan() throws Exception {
        long library=store.one("SELECT id FROM library WHERE kind='question'").getLong("id");
        JSONArray items=store.rows("SELECT * FROM item WHERE library_id=? ORDER BY id LIMIT 3",""+library);
        long first=items.getJSONObject(0).getLong("id"),outside=items.getJSONObject(1).getLong("id"),other=items.getJSONObject(2).getLong("id");
        store.getWritableDatabase().execSQL("UPDATE item SET archived=1 WHERE library_id=? AND id NOT IN (?,?,?)",new Object[]{library,first,outside,other});
        long shared=store.insert("point",LearningStore.obj("library_id",library,"name","pool-shared","summary","","example","","mnemonic",""));
        long separate=store.insert("point",LearningStore.obj("library_id",library,"name","pool-other","summary","","example","","mnemonic",""));
        for(long id:new long[]{first,outside,other}) {
            store.getWritableDatabase().execSQL("DELETE FROM item_point WHERE item_id=?",new Object[]{id});
            store.insert("item_point",LearningStore.obj("item_id",id,"point_id",id==other?separate:shared));
            store.edit("item",id,LearningStore.obj("difficulty",1));
        }
        for(long point:new long[]{shared,separate})store.insert("state",LearningStore.obj("owner_id",point,"skill","knowledge","mastery",point==shared?.8:.4,"seen",1,"last_at",0,"due_at",0,"interval_days",1));
        long session=store.insert("session",LearningStore.obj("library_id",library,"mode","question","plan",new JSONArray().put(first).put(other).toString(),"created_at",System.currentTimeMillis(),"strategy","adaptive"));
        JSONObject item=items.getJSONObject(0);
        store.submit(session,0,first,item.getString("prompt"),item.getString("answer"),"wrong",false,2,"question",1000);
        JSONArray changed=new JSONArray(store.one("SELECT plan FROM session WHERE id=?",""+session).getString("plan"));
        assertEquals(2,changed.length());assertEquals(first,changed.getLong(0));assertEquals(outside,changed.getLong(1));
        assertEquals(1,store.count("SELECT COUNT(*) n FROM attempt WHERE session_id=?",""+session));
        store.close();store=new LearningStore(context);
        assertEquals(changed.toString(),store.one("SELECT plan FROM session WHERE id=?",""+session).getString("plan"));
    }
    @Test public void recommendationUsesIndependentBktEvidenceAndRecordedCalculation() throws Exception {
        long library=store.one("SELECT id FROM library WHERE kind='question'").getLong("id");
        long session=store.start(library,"question",1,"adaptive",0);
        long id=new JSONArray(store.one("SELECT plan FROM session WHERE id=?",""+session).getString("plan")).getLong(0);
        JSONObject before=store.recommendation(id,"question","adaptive");
        assertEquals(0,before.getInt("seen"));assertTrue(before.getString("summary").contains("待评估"));
        JSONObject item=store.one("SELECT * FROM item WHERE id=?",""+id);
        store.submit(session,0,id,item.getString("prompt"),item.getString("answer"),item.getString("answer"),true,2,"question",1000);
        JSONObject after=store.recommendation(id,"question","adaptive");
        assertEquals(1,after.getInt("recentCount"));assertEquals(1,after.getInt("recentCorrect"));
        assertEquals(.632,after.getDouble("mastery"),1e-12);
        JSONObject audit=store.one("SELECT * FROM state_change ORDER BY id LIMIT 1");
        assertEquals(.6,audit.getDouble("posterior"),1e-12);assertEquals(.20,audit.getDouble("guess"),0);
        assertEquals(.10,audit.getDouble("slip"),0);assertEquals(.08,audit.getDouble("learn"),0);
        assertEquals("bkt-confidence-v1",audit.getString("model_version"));
        JSONObject factors=after.getJSONObject("factors");
        assertEquals(factors.getDouble("weakness")+factors.getDouble("overdue")+factors.getDouble("spacing")+factors.getDouble("difficultyFit")+factors.getDouble("repetition"),factors.getDouble("total"),1e-12);
        assertTrue(store.recommendation(id,"question","random").getString("reason").contains("不依据掌握概率排序"));
    }
    @Test public void versionTwoBackupRestoresWithoutInventingHistoricalTrace() throws Exception {
        long library=store.one("SELECT id FROM library WHERE kind='question'").getLong("id");
        long session=store.start(library,"question",1,"adaptive",0);
        long id=new JSONArray(store.one("SELECT plan FROM session WHERE id=?",""+session).getString("plan")).getLong(0);
        JSONObject item=store.one("SELECT * FROM item WHERE id=?",""+id);
        store.submit(session,0,id,item.getString("prompt"),item.getString("answer"),item.getString("answer"),true,2,"question",1000);
        JSONObject backup=store.backup();backup.put("version",2);
        JSONArray changes=backup.getJSONArray("state_change");
        for(int i=0;i<changes.length();i++)for(String column:new String[]{"guess","slip","learn","posterior","model_version"})changes.getJSONObject(i).remove(column);
        store.restore(backup);
        JSONObject restored=store.one("SELECT * FROM state_change ORDER BY id LIMIT 1");
        assertEquals(.632,restored.getDouble("after_value"),1e-12);
        assertEquals("legacy-no-trace",restored.getString("model_version"));assertTrue(restored.isNull("posterior"));
        assertEquals(1,store.count("SELECT COUNT(*) n FROM attempt"));
    }
    @Test public void personalizedIntervalsAndDelayedTaskUsePersistedDueDates() throws Exception {
        JSONObject word=store.one("SELECT * FROM item WHERE kind='word' ORDER BY id LIMIT 1");
        long id=word.getLong("id"),library=word.getLong("library_id");
        store.insert("state",LearningStore.obj("owner_id",id,"skill","recall","mastery",.85,"seen",5,"last_at",0,"due_at",0,"interval_days",14));
        long session=store.insert("session",LearningStore.obj("library_id",library,"mode","recall","plan",new JSONArray().put(id).toString(),"created_at",System.currentTimeMillis(),"strategy","adaptive"));
        store.submit(session,0,id,word.getString("meaning"),word.getString("prompt"),word.getString("prompt"),true,2,"recall",1000);
        JSONObject state=store.state(id,"recall");
        assertEquals(28,state.getInt("interval_days"));
        assertEquals(state.getLong("last_at")+28*86400000L,state.getLong("due_at"));
        store.advance(session);
        JSONObject delayed=store.one("SELECT due_at FROM task WHERE source_session=? AND stage='delayed'",""+session);
        assertEquals(state.getLong("due_at"),delayed.getLong("due_at"));
        long wrong=store.insert("session",LearningStore.obj("library_id",library,"mode","recall","plan",new JSONArray().put(id).toString(),"created_at",System.currentTimeMillis(),"strategy","adaptive"));
        store.submit(wrong,0,id,word.getString("meaning"),word.getString("prompt"),"incorrect",false,2,"recall",1000);
        state=store.state(id,"recall");
        assertEquals(1,state.getInt("interval_days"));
        assertEquals(state.getLong("last_at")+86400000L,state.getLong("due_at"));
        assertEquals(2,store.count("SELECT COUNT(*) n FROM state_change WHERE owner_id=? AND skill='recall'",""+id));
    }
    @Test public void versionTwoDatabaseUpgradeIsAdditiveAndPreservesStateValues() throws Exception {
        store.close();
        InstrumentationRegistry.getInstrumentation().getTargetContext().deleteDatabase("test_zhixue_learning.db");
        android.database.sqlite.SQLiteDatabase legacy=android.database.sqlite.SQLiteDatabase.openOrCreateDatabase(context.getDatabasePath("zhixue_learning.db"),null);
        legacy.execSQL("CREATE TABLE state_change(id INTEGER PRIMARY KEY,attempt_id INTEGER NOT NULL,owner_id INTEGER NOT NULL,skill TEXT NOT NULL,before_value REAL NOT NULL,after_value REAL NOT NULL,at INTEGER NOT NULL)");
        legacy.execSQL("CREATE TABLE state(owner_id INTEGER NOT NULL,skill TEXT NOT NULL,mastery REAL NOT NULL,seen INTEGER NOT NULL,last_at INTEGER NOT NULL,due_at INTEGER NOT NULL,interval_days INTEGER NOT NULL,PRIMARY KEY(owner_id,skill))");
        legacy.execSQL("INSERT INTO state_change VALUES(7,3,2,'knowledge',.25,.42,1234)");
        legacy.execSQL("INSERT INTO state VALUES(2,'knowledge',.42,1,1234,5678,1)");
        legacy.setVersion(2);legacy.close();
        store=new LearningStore(context);
        assertEquals(4,store.getReadableDatabase().getVersion());
        JSONObject change=store.one("SELECT * FROM state_change WHERE id=7");
        assertEquals(.42,change.getDouble("after_value"),0);assertEquals(1234,change.getLong("at"));
        assertEquals("legacy-no-trace",change.getString("model_version"));assertTrue(change.isNull("guess"));
        assertEquals(.42,store.state(2,"knowledge").getDouble("mastery"),0);
        assertEquals(1,store.count("SELECT COUNT(*) n FROM state_change"));
    }
    @Test public void backupRoundTripAndMalformedRestoreAreAtomic() throws Exception  {
        JSONObject backup=store.backup();
        long n=store.count("SELECT COUNT(*) n FROM item");
        store.restore(backup);
        assertEquals(n,store.count("SELECT COUNT(*) n FROM item"));
        backup.remove("attempt");
        try {
            store.restore(backup);
            fail("malformed backup accepted");
        }
        catch(JSONException expected) {
        }
        assertEquals(n,store.count("SELECT COUNT(*) n FROM item"));
    }
}
