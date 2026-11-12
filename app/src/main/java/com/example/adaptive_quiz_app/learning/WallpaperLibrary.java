package com.example.adaptive_quiz_app.learning;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;

/** Offline artwork catalog and preferences, independent of learning evidence. */
public final class WallpaperLibrary {
    public static final class Artwork {
        public final String id,title,artist,season,file,source;
        Artwork(JSONObject json) {
            id=json.optString("id"); title=json.optString("title");
            artist=json.optString("artist"); season=json.optString("season");
            file=json.optString("file"); source=json.optString("source");
        }
    }
    private final Context context;
    private final SharedPreferences prefs;
    private final java.util.function.LongSupplier clock;
    private final List<Artwork> catalog=new ArrayList<>();
    public WallpaperLibrary(Context context) {
        this(context,System::currentTimeMillis);
    }
    WallpaperLibrary(Context context,java.util.function.LongSupplier clock) {
        this.context=context.getApplicationContext();
        this.clock=clock;
        prefs=context.getSharedPreferences("art_wallpapers",Context.MODE_PRIVATE);
        try(InputStream in=context.getAssets().open("wallpapers/catalog.json")) {
            java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();
            byte[] bytes=new byte[4096]; int count;
            while((count=in.read(bytes))!=-1)out.write(bytes,0,count);
            JSONArray items=new JSONArray(out.toString("UTF-8"));
            for(int i=0;i<items.length();i++)catalog.add(new Artwork(items.getJSONObject(i)));
        } catch(Exception ignored) { /* Plain background remains available if assets are damaged. */ }
    }
    public List<Artwork> all() {return new ArrayList<>(catalog);}
    public boolean enabled() {return prefs.getBoolean("enabled",true);}
    public void setEnabled(boolean value) {prefs.edit().putBoolean("enabled",value).apply();}
    public boolean automatic() {return prefs.getBoolean("automatic",true);}
    public void setAutomatic(boolean value) {
        Artwork current=current();
        SharedPreferences.Editor edit=prefs.edit().putBoolean("automatic",value);
        if(!value&&current!=null)edit.putString("selected",current.id);
        edit.apply();
    }
    public boolean favorite(Artwork art) {return prefs.getBoolean("favorite_"+art.id,false);}
    public void toggleFavorite(Artwork art) {prefs.edit().putBoolean("favorite_"+art.id,!favorite(art)).apply();}
    public boolean pinned(Artwork art) {return prefs.getString("pinned","").equals(art.id);}
    public void pin(Artwork art) {prefs.edit().putString("pinned",pinned(art)?"":art.id).apply();}
    private String today() {
        Calendar c=calendar();
        return c.get(Calendar.YEAR)+"-"+c.get(Calendar.DAY_OF_YEAR);
    }
    private Calendar calendar(){Calendar c=Calendar.getInstance();c.setTimeInMillis(clock.getAsLong());return c;}
    public void select(Artwork art) {
        prefs.edit().putString("selected",art.id).putString("selected_day",today())
            .putString("pinned","").putBoolean("enabled",true).apply();
    }
    public Artwork current() {
        if(catalog.isEmpty())return null;
        String pinned=prefs.getString("pinned","");
        String selected=prefs.getString("selected","");
        String wanted=!pinned.isEmpty()?pinned:!automatic()||today().equals(prefs.getString("selected_day",""))?selected:"";
        for(Artwork art:catalog)if(art.id.equals(wanted))return art;
        Calendar c=calendar();
        // A local civil-date index avoids timezone and daylight-saving drift.
        Calendar civil=Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));civil.clear();
        civil.set(c.get(Calendar.YEAR),c.get(Calendar.MONTH),c.get(Calendar.DAY_OF_MONTH));
        long day=civil.getTimeInMillis()/86400000L;
        return catalog.get((int)Math.floorMod(day,catalog.size()));
    }
    public void next() {
        Artwork art=current();if(art==null)return;
        select(catalog.get((catalog.indexOf(art)+1)%catalog.size()));
    }
    public Bitmap decode(Artwork art,int maxWidth,int maxHeight) throws java.io.IOException {
        BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;
        try(InputStream in=context.getAssets().open("wallpapers/"+art.file)){BitmapFactory.decodeStream(in,null,options);}
        options.inSampleSize=1;
        while(options.outWidth/(options.inSampleSize*2)>=maxWidth&&options.outHeight/(options.inSampleSize*2)>=maxHeight)options.inSampleSize*=2;
        options.inJustDecodeBounds=false;options.inPreferredConfig=Bitmap.Config.RGB_565;
        try(InputStream in=context.getAssets().open("wallpapers/"+art.file)){return BitmapFactory.decodeStream(in,null,options);}
    }
    public static boolean dark(Bitmap bitmap) {
        double sum=0;int count=0;
        for(int y=0;y<bitmap.getHeight();y+=Math.max(1,bitmap.getHeight()/16))
            for(int x=0;x<bitmap.getWidth();x+=Math.max(1,bitmap.getWidth()/16)) {
                int color=bitmap.getPixel(x,y);sum+=.2126*Color.red(color)+.7152*Color.green(color)+.0722*Color.blue(color);count++;
            }
        return count>0&&sum/count<135;
    }
}
