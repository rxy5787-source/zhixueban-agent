package com.example.adaptive_quiz_app.learning;

import android.content.Context;
import android.content.ContextWrapper;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.util.Calendar;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class WallpaperLibraryTest {
    @Test public void offlineAssetsAndPreferenceLifecycle() throws Exception {
        Context target=InstrumentationRegistry.getInstrumentation().getTargetContext();
        Context isolated=new ContextWrapper(target){
            @Override public Context getApplicationContext(){return this;}
            @Override public android.content.SharedPreferences getSharedPreferences(String name,int mode){return super.getSharedPreferences("test_"+name,mode);}
        };
        isolated.getSharedPreferences("art_wallpapers",0).edit().clear().commit();
        Calendar day=Calendar.getInstance();day.set(2026,Calendar.DECEMBER,31,12,0,0);
        long[] now={day.getTimeInMillis()};
        WallpaperLibrary library=new WallpaperLibrary(isolated,()->now[0]);
        try {
            assertEquals(16,library.all().size());
            java.util.Set<String> seasons=new java.util.HashSet<>();
            for(WallpaperLibrary.Artwork art:library.all()) {
                seasons.add(art.season);
                android.graphics.Bitmap bitmap=library.decode(art,240,180);
                assertNotNull(art.title,bitmap);assertTrue(bitmap.getWidth()>0&&bitmap.getHeight()>0);bitmap.recycle();
            }
            assertEquals(4,seasons.size());
            String first=library.current().id;
            day.add(Calendar.DAY_OF_YEAR,1);now[0]=day.getTimeInMillis();
            assertNotEquals("Daily rotation survives a year boundary",first,library.current().id);
            WallpaperLibrary.Artwork chosen=library.all().get(4);
            library.select(chosen);library.toggleFavorite(chosen);library.pin(chosen);
            day.add(Calendar.DAY_OF_YEAR,2);now[0]=day.getTimeInMillis();
            WallpaperLibrary reopened=new WallpaperLibrary(isolated,()->now[0]);
            assertEquals(chosen.id,reopened.current().id);assertTrue(reopened.favorite(chosen));
            reopened.pin(chosen);reopened.setAutomatic(false);
            String fixed=reopened.current().id;
            day.add(Calendar.DAY_OF_YEAR,3);now[0]=day.getTimeInMillis();
            assertEquals(fixed,new WallpaperLibrary(isolated,()->now[0]).current().id);
            reopened.setEnabled(false);assertFalse(new WallpaperLibrary(isolated,()->now[0]).enabled());
            reopened.next();assertTrue(reopened.enabled());assertNotEquals(fixed,reopened.current().id);
        } finally {isolated.getSharedPreferences("art_wallpapers",0).edit().clear().commit();}
    }
}
