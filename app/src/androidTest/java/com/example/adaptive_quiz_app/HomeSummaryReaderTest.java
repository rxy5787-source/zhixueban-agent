package com.example.adaptive_quiz_app;

import android.content.Context;
import android.content.ContextWrapper;
import android.database.DatabaseErrorHandler;
import android.database.sqlite.SQLiteDatabase;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import com.example.adaptive_quiz_app.learning.HomeSummaryReader;
import com.example.adaptive_quiz_app.learning.LearningStore;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

import java.io.File;
import java.util.Calendar;

import static org.junit.Assert.*;

/** Summary fixtures use a separate database and never add evidence to the user's records. */
@RunWith(AndroidJUnit4.class)
public class HomeSummaryReaderTest {
    private static final String PREFIX = "test_home_summary_";
    private static final String DATABASE = PREFIX + "zhixue_learning.db";
    private LearningStore store;
    private int attemptPosition;

    @Before public void setup() {
        Context target = InstrumentationRegistry.getInstrumentation().getTargetContext();
        target.deleteDatabase(DATABASE);
        Context isolated = new ContextWrapper(target) {
            @Override public SQLiteDatabase openOrCreateDatabase(String name, int mode,
                    SQLiteDatabase.CursorFactory factory, DatabaseErrorHandler handler) {
                return super.openOrCreateDatabase(PREFIX + name, mode, factory, handler);
            }

            @Override public File getDatabasePath(String name) {
                return super.getDatabasePath(PREFIX + name);
            }
        };
        store = new LearningStore(isolated);
        store.getWritableDatabase();
    }

    @After public void cleanup() {
        if (store != null) store.close();
        InstrumentationRegistry.getInstrumentation().getTargetContext().deleteDatabase(DATABASE);
    }

    @Test public void dailyCompletionIsCappedPerActiveLibraryButAllSubmissionsRemainVisible() throws Exception {
        long now = localTime(2026, Calendar.OCTOBER, 12, 12);
        long first = library("First", false);
        long firstItem = item(first);
        item(first);
        item(first);
        long firstSession = session(first, firstItem, 1, now);
        for (int i = 0; i < 3; i++) attempt(firstSession, firstItem, now - 1000 - i);

        long second = library("Second", false);
        long secondItem = item(second);
        session(second, secondItem, 2, now);

        long archived = library("Archived", true);
        long archivedItem = item(archived);
        long archivedSession = session(archived, archivedItem, 0, now);
        attempt(archivedSession, archivedItem, now - 500);
        attempt(archivedSession, archivedItem, now - 400);
        task(firstSession, first, "concept", now - 1000, false);
        task(firstSession, first, "basic", now + 86400000L, false);
        task(firstSession, first, "application", now, true);
        task(archivedSession, archived, "concept", now, false);

        JSONObject summary = readWithoutChanges(2, now, 7, 1);
        assertEquals(3, summary.getInt("target"));
        assertEquals(2, summary.getInt("completed"));
        assertEquals(5, summary.getInt("doneToday"));
        assertEquals(2, summary.getInt("tasks"));
        // Eligibility stays with the host; a future/blocked task is still an unfinished task.
        assertEquals(1, summary.getInt("runnableTasks"));
        assertEquals(7, summary.getInt("due"));
        assertEquals(0, summary.getInt("resumeCount"));
        assertTrue(summary.isNull("activeSession"));
    }

    @Test public void resumeAndWeakEvidenceExcludeFinishedArchivedAndUnseenRecords() throws Exception {
        long now = localTime(2026, Calendar.OCTOBER, 12, 12);
        long active = library("Active", false);
        long activeItem = item(active);
        session(active, activeItem, 0, now - 10000);
        session(active, activeItem, 1, now - 9000);
        session(active, activeItem, 2, now - 8000);
        long archived = library("Archived", true);
        long archivedItem = item(archived);
        session(archived, archivedItem, 0, now - 7000);
        long newest = session(active, activeItem, 0, now - 6000);

        long unseen = point(active, "Unseen", false);
        long assessed = point(active, "Assessed", false);
        long archivedPoint = point(active, "Archived point", true);
        long archivedLibraryPoint = point(archived, "Archived library point", false);
        state(unseen, "knowledge", .01, 0, now);
        state(assessed, "knowledge", .4, 2, now);
        state(archivedPoint, "knowledge", .02, 3, now);
        state(archivedLibraryPoint, "knowledge", .03, 4, now);
        state(activeItem, "recall", .001, 5, now);

        JSONObject summary = readWithoutChanges(2, now, 0, 0);
        assertEquals(2, summary.getInt("resumeCount"));
        JSONObject resume = summary.getJSONObject("activeSession");
        assertEquals(newest, resume.getLong("id"));
        assertEquals("Active", resume.getString("name"));
        assertEquals(new JSONArray().put(activeItem).toString(), resume.getString("plan"));
        JSONObject weak = summary.getJSONObject("weak");
        assertEquals(assessed, weak.getLong("id"));
        assertEquals(2, weak.getInt("seen"));
        assertEquals("Active", weak.getString("library_name"));

        store.edit("point", assessed, LearningStore.obj("archived", 1));
        assertTrue(readWithoutChanges(2, now, 0, 0).isNull("weak"));
    }

    @Test public void weekFootprintsRespectLocalMidnightWeekBoundaryAndFutureDays() throws Exception {
        long monday = localTime(2026, Calendar.OCTOBER, 12, 0);
        long tuesday = localTime(2026, Calendar.OCTOBER, 13, 0);
        long sunday = localTime(2026, Calendar.OCTOBER, 18, 0);
        long nextMonday = localTime(2026, Calendar.OCTOBER, 19, 0);
        long library = library("Week", false);
        long item = item(library);
        long session = session(library, item, 1, monday);
        attempt(session, item, monday - 1);
        attempt(session, item, monday);
        attempt(session, item, tuesday);
        attempt(session, item, sunday);
        attempt(session, item, nextMonday);

        JSONObject mondaySummary = readWithoutChanges(2, localTime(2026, Calendar.OCTOBER, 12, 12), 0, 0);
        assertWeek(mondaySummary, 0, new boolean[]{true, false, false, false, false, false, false});
        JSONObject sundaySummary = readWithoutChanges(2, localTime(2026, Calendar.OCTOBER, 18, 12), 0, 0);
        assertWeek(sundaySummary, 6, new boolean[]{true, true, false, false, false, false, true});
        JSONObject nextWeek = readWithoutChanges(2, localTime(2026, Calendar.OCTOBER, 19, 12), 0, 0);
        assertWeek(nextWeek, 0, new boolean[]{true, false, false, false, false, false, false});
    }

    private JSONObject readWithoutChanges(int daily, long now, int due, int runnable) throws Exception {
        JSONObject before = store.backup();
        before.remove("at");
        String schema = store.rows("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").toString();
        int version = store.getReadableDatabase().getVersion();
        JSONObject summary = HomeSummaryReader.read(store, daily, now, due, runnable);
        JSONObject after = store.backup();
        after.remove("at");
        assertEquals("Reading the home must preserve every table and learner record", before.toString(), after.toString());
        assertEquals(schema, store.rows("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").toString());
        assertEquals(version, store.getReadableDatabase().getVersion());
        return summary;
    }

    private void assertWeek(JSONObject summary, int today, boolean[] expected) throws Exception {
        JSONArray days = summary.getJSONArray("days");
        assertEquals(7, days.length());
        String[] labels = {"一", "二", "三", "四", "五", "六", "日"};
        int studied = 0;
        for (int i = 0; i < expected.length; i++) {
            JSONObject day = days.getJSONObject(i);
            assertEquals(labels[i], day.getString("label"));
            assertEquals("Footprint index " + i, expected[i], day.getBoolean("studied"));
            assertEquals(i == today, day.getBoolean("isToday"));
            if (expected[i]) studied++;
        }
        assertEquals(studied, summary.getInt("studiedDays"));
    }

    private long library(String name, boolean archived) {
        return store.insert("library", LearningStore.obj("name", name, "subject", "Test", "kind", "question", "archived", archived ? 1 : 0));
    }

    private long item(long library) {
        return store.insert("item", LearningStore.obj("library_id", library, "kind", "question",
                "prompt", "Question", "options", "[\"A\",\"B\"]", "answer", "A", "explanation", "",
                "difficulty", 1, "meaning", "", "example", "", "context_prompt", ""));
    }

    private long session(long library, long item, int finished, long createdAt) {
        return store.insert("session", LearningStore.obj("library_id", library, "mode", "question",
                "plan", new JSONArray().put(item).toString(), "created_at", createdAt, "finished", finished));
    }

    private void attempt(long session, long item, long at) {
        store.insert("attempt", LearningStore.obj("session_id", session, "position", attemptPosition++,
                "item_id", item, "prompt", "Question", "expected", "A", "response", "A", "correct", 1,
                "confidence", 2, "skill", "question", "elapsed_ms", 1000, "at", at));
    }

    private void task(long source, long library, String stage, long dueAt, boolean completed) {
        store.insert("task", LearningStore.obj("source_session", source, "library_id", library,
                "stage", stage, "due_at", dueAt, "completed", completed ? 1 : 0));
    }

    private long point(long library, String name, boolean archived) {
        return store.insert("point", LearningStore.obj("library_id", library, "name", name,
                "summary", "", "example", "", "mnemonic", "", "archived", archived ? 1 : 0));
    }

    private void state(long owner, String skill, double mastery, int seen, long now) {
        store.insert("state", LearningStore.obj("owner_id", owner, "skill", skill, "mastery", mastery,
                "seen", seen, "last_at", now, "due_at", now, "interval_days", 1));
    }

    private static long localTime(int year, int month, int day, int hour) {
        Calendar calendar = Calendar.getInstance();
        calendar.clear();
        calendar.set(year, month, day, hour, 0, 0);
        return calendar.getTimeInMillis();
    }
}
