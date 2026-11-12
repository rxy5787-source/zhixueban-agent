package com.example.adaptive_quiz_app.auth;

import android.content.Context;
import android.content.ContextWrapper;
import android.content.SharedPreferences;
import android.database.DatabaseErrorHandler;
import android.database.sqlite.SQLiteDatabase;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** Account isolation is a context mapping; the original schema and evidence stay untouched. */
public final class AccountScope {
    private final Context original;
    private final boolean legacy;
    private final String prefix;
    public AccountScope(Context context,String userId) {
        original=context;prefix="account_"+key(userId)+"_";
        legacy=userId.equals(registry(context).getString("legacyOwner",""));
    }
    public static boolean needsLegacyChoice(Context context,String userId) {
        return !registry(context).getBoolean("chosen_"+key(userId),false)
                &&registry(context).getString("legacyOwner","").isEmpty()
                &&context.getDatabasePath("zhixue_learning.db").exists();
    }
    public static synchronized void choose(Context context,String userId,boolean claim) {
        SharedPreferences prefs=registry(context);
        SharedPreferences.Editor edit=prefs.edit().putBoolean("chosen_"+key(userId),true);
        if(claim) {
            String owner=prefs.getString("legacyOwner","");
            if(!owner.isEmpty()&&!owner.equals(userId))throw new IllegalStateException("原有记录已经关联其他账号");
            edit.putString("legacyOwner",userId);
        }
        if(!edit.commit())throw new IllegalStateException("无法保存账号关联，请重试");
    }
    private static SharedPreferences registry(Context c){return c.getSharedPreferences("account_spaces",Context.MODE_PRIVATE);}
    public String preferencesName(){return legacy?"MainActivity":prefix+"MainActivity";}
    public File filesDirectory() {
        File file=legacy?original.getFilesDir():new File(original.getFilesDir(),"account_files/"+prefix);
        if(!file.exists()&&!file.mkdirs())throw new IllegalStateException("无法创建学习空间");return file;
    }
    public Context databaseContext() {
        return new ContextWrapper(original) {
            private String map(String name){return legacy?name:prefix+name;}
            @Override public SQLiteDatabase openOrCreateDatabase(String name,int mode,SQLiteDatabase.CursorFactory factory){return original.openOrCreateDatabase(map(name),mode,factory);}
            @Override public SQLiteDatabase openOrCreateDatabase(String name,int mode,SQLiteDatabase.CursorFactory factory,DatabaseErrorHandler handler){return original.openOrCreateDatabase(map(name),mode,factory,handler);}
            @Override public File getDatabasePath(String name){return original.getDatabasePath(map(name));}
        };
    }
    private static String key(String userId) {
        try { byte[] bytes=MessageDigest.getInstance("SHA-256").digest(userId.getBytes(StandardCharsets.UTF_8));StringBuilder text=new StringBuilder();for(byte b:bytes)text.append(String.format(java.util.Locale.ROOT,"%02x",b));return text.toString(); }
        catch(Exception error){throw new IllegalStateException(error);}
    }
}
