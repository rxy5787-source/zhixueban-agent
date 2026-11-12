package com.example.adaptive_quiz_app.learning;
import java.util.Locale;
/** Pure Java BKT with confidence-conditioned guessing; parameters are not data calibrated. */
public final class LearningEngine  {
    private LearningEngine()  {
    }
    public static final double INITIAL = .25;
    public static final String MODEL_VERSION = "bkt-confidence-v1";
    public static final double SLIP = .10;
    public static final double LEARN = .08;
    /** Auditable observation update followed by the BKT learning transition. */
    public static final class Trace {
        public final double prior, posterior, guess, slip, learn, after;
        public final String modelVersion = MODEL_VERSION;
        private Trace(double prior,double posterior,double guess,double after) {
            this.prior=prior;this.posterior=posterior;this.guess=guess;
            this.slip=SLIP;this.learn=LEARN;this.after=after;
        }
    }
    public static Trace trace(double prior,boolean correct,int confidence) {
        if(!Double.isFinite(prior)||confidence<0||confidence>2)
            throw new IllegalArgumentException("Invalid BKT observation");
        prior=clamp(prior,.01,.99);
        double guess=confidence==0?.40:confidence==1?.28:.20;
        double masteredLikelihood=correct?1-SLIP:SLIP;
        double unmasteredLikelihood=correct?guess:1-guess;
        double posterior=prior*masteredLikelihood/(prior*masteredLikelihood+(1-prior)*unmasteredLikelihood);
        return new Trace(prior,posterior,guess,clamp(posterior+(1-posterior)*LEARN,.01,.99));
    }
    public static double update(double prior, boolean correct, int confidence)  {
        return trace(prior,correct,confidence).after;
    }
    public static int targetDifficulty(double mastery) {
        return mastery<.45?1:mastery<.75?2:3;
    }
    public static final class PriorityTrace {
        public final double weakness,overdue,spacing,difficultyFit,repetition,total;
        private PriorityTrace(double mastery,long due,long last,int difficulty,int recent,long now) {
            weakness=.45*(1-mastery);
            overdue=.25*(due>0&&due<=now?Math.min(1,.3+(now-due)/86400000.0/7):0);
            spacing=.15*(last==0?.5:Math.min(1,Math.max(0,now-last)/86400000.0/7));
            difficultyFit=.15*(1-Math.abs(difficulty-targetDifficulty(mastery))/2.0);
            repetition=-.25*recent;
            total=weakness+overdue+spacing+difficultyFit+repetition;
        }
    }
    public static PriorityTrace priorityTrace(double mastery,long due,long last,int difficulty,int recent,long now) {
        return new PriorityTrace(mastery,due,last,difficulty,recent,now);
    }
    public static double priority(double mastery, long due, long last, int difficulty,                                   int recent, long now)  {
        return priorityTrace(mastery,due,last,difficulty,recent,now).total;
    }
    public static int nextInterval(int oldDays, boolean correct, int confidence)  {
        if (!correct) return 1;
        if (confidence < 2) return Math.max(1, Math.min(3, oldDays));
        return oldDays == 0 ? 1 : Math.min(60, Math.max(2, oldDays * 2));
    }
    public static boolean spellingMatches(String answer, String expected)  {
        return answer.trim().toLowerCase(Locale.ROOT).equals(expected.trim().toLowerCase(Locale.ROOT));
    }
    private static double clamp(double n, double low, double high)  {
        return Math.max(low, Math.min(high, n));
    }
}
