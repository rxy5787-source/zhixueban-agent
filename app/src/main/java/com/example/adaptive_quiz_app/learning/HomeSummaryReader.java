package com.example.adaptive_quiz_app.learning;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Calendar;

/** Read-only presentation summary; learning order and state changes remain with the existing flow. */
public final class HomeSummaryReader {
    private HomeSummaryReader() {}

    /**
     * Uses the same daily-plan and evidence rules as the existing home.
     * Due and runnable-task counts come from the host's existing scheduling predicates.
     */
    public static JSONObject read(LearningStore db, int daily, long now,
                                  int dueCount, int runnableTaskCount) {
        Calendar today = Calendar.getInstance();
        today.setTimeInMillis(now);
        today.set(Calendar.HOUR_OF_DAY, 0);
        today.set(Calendar.MINUTE, 0);
        today.set(Calendar.SECOND, 0);
        today.set(Calendar.MILLISECOND, 0);
        long dayStart = today.getTimeInMillis();

        JSONArray goals = db.rows("SELECT l.id,l.kind,(SELECT COUNT(*) FROM item i " +
                "WHERE i.library_id=l.id AND i.archived=0) available " +
                "FROM library l WHERE l.archived=0");
        int target = 0;
        int completed = 0;
        for (int i = 0; i < goals.length(); i++) {
            JSONObject goal = goals.optJSONObject(i);
            int planned = Math.min(daily, goal.optInt("available"));
            target += planned;
            completed += Math.min(planned, count(db,
                    "SELECT COUNT(*) n FROM attempt a JOIN session s ON s.id=a.session_id " +
                            "WHERE s.library_id=? AND a.at>=?",
                    String.valueOf(goal.optLong("id")), String.valueOf(dayStart)));
        }

        int doneToday = count(db, "SELECT COUNT(*) n FROM attempt WHERE at>=?",
                String.valueOf(dayStart));
        int tasks = count(db, "SELECT COUNT(*) n FROM task t JOIN library l ON l.id=t.library_id " +
                "WHERE t.completed=0 AND l.archived=0");
        int resumeCount = count(db, "SELECT COUNT(*) n FROM session s " +
                "JOIN library l ON l.id=s.library_id WHERE s.finished=0 AND l.archived=0");
        JSONObject activeSession = db.one("SELECT s.*,l.name FROM session s " +
                "JOIN library l ON l.id=s.library_id WHERE s.finished=0 AND l.archived=0 " +
                "ORDER BY s.id DESC LIMIT 1");
        JSONObject weak = db.one("SELECT p.id,p.library_id,p.name,s.mastery,s.seen,l.name library_name " +
                "FROM state s JOIN point p ON p.id=s.owner_id JOIN library l ON l.id=p.library_id " +
                "WHERE s.skill='knowledge' AND s.seen>0 AND p.archived=0 AND l.archived=0 " +
                "ORDER BY s.mastery,p.id LIMIT 1");

        Calendar day = (Calendar) today.clone();
        int daysSinceMonday = (day.get(Calendar.DAY_OF_WEEK) + 5) % 7;
        day.add(Calendar.DAY_OF_MONTH, -daysSinceMonday);
        String[] labels = {"一", "二", "三", "四", "五", "六", "日"};
        JSONArray days = new JSONArray();
        int studiedDays = 0;
        for (String label : labels) {
            long start = day.getTimeInMillis();
            Calendar next = (Calendar) day.clone();
            // Calendar arithmetic respects local daylight-saving changes between midnights.
            next.add(Calendar.DAY_OF_MONTH, 1);
            long end = next.getTimeInMillis();
            boolean studied = start <= now && count(db,
                    "SELECT COUNT(*) n FROM attempt WHERE at>=? AND at<?",
                    String.valueOf(start), String.valueOf(end)) > 0;
            if (studied) studiedDays++;
            days.put(LearningStore.obj("label", label, "studied", studied, "isToday", start == dayStart));
            day = next;
        }

        return LearningStore.obj("now", now, "target", target, "completed", completed,
                "doneToday", doneToday, "tasks", tasks, "runnableTasks", runnableTaskCount,
                "due", dueCount, "resumeCount", resumeCount,
                "activeSession", activeSession == null ? JSONObject.NULL : activeSession,
                "weak", weak == null ? JSONObject.NULL : weak,
                "days", days, "studiedDays", studiedDays);
    }

    private static int count(LearningStore db, String sql, String... args) {
        return (int) Math.min(Integer.MAX_VALUE, db.count(sql, args));
    }
}
