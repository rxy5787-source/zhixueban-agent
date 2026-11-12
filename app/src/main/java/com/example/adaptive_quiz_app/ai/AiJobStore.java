package com.example.adaptive_quiz_app.ai;
import android.content.Context;
import android.content.SharedPreferences;
public final class AiJobStore {
    private final SharedPreferences prefs;private final String base;
    public AiJobStore(Context c,String owner,String base){prefs=c.getSharedPreferences("ai_job_"+owner,Context.MODE_PRIVATE);this.base=base;}
    public String load(){return base.equals(prefs.getString("base",""))?prefs.getString("job",""):"";}
    public void save(String job){if(!prefs.edit().putString("base",base).putString("job",job).commit())throw new IllegalStateException("无法保存任务编号");}
}
