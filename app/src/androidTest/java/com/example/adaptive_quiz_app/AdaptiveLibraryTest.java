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

@RunWith(AndroidJUnit4.class)
public class AdaptiveLibraryTest {
    private LearningStore store;
    @Before public void setup() throws Exception {
        Context target=InstrumentationRegistry.getInstrumentation().getTargetContext();
        target.deleteDatabase("adaptive_test_zhixue_learning.db");
        store=new LearningStore(new ContextWrapper(target){
            @Override public android.database.sqlite.SQLiteDatabase openOrCreateDatabase(String name,int mode,android.database.sqlite.SQLiteDatabase.CursorFactory factory,android.database.DatabaseErrorHandler handler){return super.openOrCreateDatabase("adaptive_test_"+name,mode,factory,handler);}
            @Override public java.io.File getDatabasePath(String name){return super.getDatabasePath("adaptive_test_"+name);}
        });
        store.getWritableDatabase();
        store.importContent(content("我的自定义题库"));store.importContent(content("另一个题库"));
    }
    @After public void cleanup(){store.close();InstrumentationRegistry.getInstrumentation().getTargetContext().deleteDatabase("adaptive_test_zhixue_learning.db");}
    private JSONObject content(String name) throws Exception {
        JSONArray points=new JSONArray().put(LearningStore.obj("name","筛选","summary","WHERE 子句用于筛选符合条件的数据行。","example","","mnemonic","")).put(LearningStore.obj("name","排序","summary","ORDER BY 子句用于排序查询结果。","example","","mnemonic",""));
        JSONObject item=LearningStore.obj("kind","question","prompt","用于筛选数据行的子句是什么？","options",new JSONArray().put("WHERE").put("ORDER BY").put("JOIN").put("GROUP BY"),"answer","A","explanation","WHERE 子句用于筛选符合条件的数据行。","difficulty",1,"points",new JSONArray().put("筛选"));
        return LearningStore.obj("format","zhixue-content","version",1,"libraries",new JSONArray().put(LearningStore.obj("name",name,"subject","SQL","kind","question","points",points,"items",new JSONArray().put(item))));
    }
    private long library(String name){return store.one("SELECT id FROM library WHERE name=?",name).optLong("id");}
    private long first(long library){return store.one("SELECT id FROM item WHERE library_id=?",""+library).optLong("id");}
    private void answer(long library,long item,boolean correct) throws Exception {
        long sid=store.startQuestion(library,item);JSONObject q=store.one("SELECT * FROM item WHERE id=?",""+item);
        store.submit(sid,0,item,q.getString("prompt"),"A",correct?"A":"B",correct,2,"question",1200);store.advance(sid);
    }
    @Test public void cardAnswersRefreshOnlyTheirLibraryGenerationTargets() throws Exception {
        long lid=library("我的自定义题库"),item=first(lid);
        JSONObject cold=store.generationPlan(lid);assertTrue(cold.getJSONArray("evidence").getJSONObject(0).isNull("mastery"));
        assertTrue(cold.getString("requirements").contains("待评估"));
        answer(lid,item,false);
        JSONObject weak=store.generationPlan(lid),proof=weak.getJSONArray("evidence").getJSONObject(0);
        assertEquals("筛选",proof.getString("name"));assertEquals(1,proof.getInt("seen"));
        double before=proof.getDouble("mastery");assertTrue(before<.25);assertEquals(1,weak.getInt("difficulty"));
        assertTrue(store.generationPlan(library("另一个题库")).getJSONArray("evidence").getJSONObject(0).isNull("mastery"));
        String snapshot=store.rows("SELECT * FROM state").toString();store.generationPlan(lid);
        assertEquals(snapshot,store.rows("SELECT * FROM state").toString());
        answer(lid,item,true);
        assertTrue(store.generationPlan(lid).getJSONArray("evidence").getJSONObject(0).getDouble("mastery")>before);
        assertEquals(2,store.count("SELECT COUNT(*) n FROM attempt"));assertEquals(2,store.count("SELECT COUNT(*) n FROM state_change"));
        assertFalse(store.recommendation(item,"question","card").getBoolean("scoreUsedForSelection"));
        try{store.startQuestion(library("另一个题库"),item);fail("Cross-library card accepted");}catch(JSONException expected){}
    }
    @Test public void generatedContentMergesIntoChosenLibraryWithoutResettingMastery() throws Exception {
        long lid=library("我的自定义题库");answer(lid,first(lid),false);String states=store.rows("SELECT * FROM state").toString();
        JSONObject content=content("我的自定义题库");JSONObject q=content.getJSONArray("libraries").getJSONObject(0).getJSONArray("items").getJSONObject(0);
        q.put("prompt","筛选符合条件的数据行应使用哪个子句？");
        q.put("ai",LearningStore.obj("questionId","new-question","sourceFileId","f","sourceFile","note.txt","sourceHash","hash","sourceLocation","TXT全文","evidenceQuote",q.getString("explanation"),"generationModel","test-model","reviewModel","test-review","reviewStatus","auto_prechecked","visualAssisted",false));
        JSONObject result=LearningStore.obj("format","zhixue-ai-result","version",1,"ownerId","owner","serviceId","service","jobId","job","content",content);
        store.importAiResult(result,"owner");store.importAiResult(result,"owner");
        assertEquals(2,store.count("SELECT COUNT(*) n FROM library"));assertEquals(2,store.count("SELECT COUNT(*) n FROM item WHERE library_id=?",""+lid));
        assertEquals(1,store.count("SELECT COUNT(*) n FROM item WHERE library_id=?",""+library("另一个题库")));
        assertEquals(1,store.count("SELECT COUNT(*) n FROM ai_source"));assertEquals(states,store.rows("SELECT * FROM state").toString());
    }
}
