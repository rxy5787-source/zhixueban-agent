package com.example.adaptive_quiz_app;
import com.example.adaptive_quiz_app.learning.LearningEngine;
import org.junit.Test;
import static org.junit.Assert.*;
public class LearningEngineTest  {
    @Test public void bktTraceMatchesBayesObservationAndLearningTransition() {
        LearningEngine.Trace correct=LearningEngine.trace(.25,true,2);
        assertEquals(.60,correct.posterior,1e-12);
        assertEquals(.632,correct.after,1e-12);
        assertEquals(.20,correct.guess,0);
        assertEquals(.10,correct.slip,0);
        assertEquals(.08,correct.learn,0);
        assertEquals(LearningEngine.MODEL_VERSION,correct.modelVersion);
        LearningEngine.Trace wrong=LearningEngine.trace(.25,false,2);
        assertEquals(.04,wrong.posterior,1e-12);
        assertEquals(.1168,wrong.after,1e-12);
        // Neither a single right answer nor its 100% accuracy is a 100% mastery estimate.
        assertNotEquals(1,correct.after,0);
        for(int confidence=0;confidence<=2;confidence++)
            for(boolean response:new boolean[]{true,false})
                assertEquals(LearningEngine.trace(.42,response,confidence).after,LearningEngine.update(.42,response,confidence),0);
    }
    @Test public void invalidEvidenceCannotWriteNonFiniteProbabilities() {
        for(double invalid:new double[]{Double.NaN,Double.POSITIVE_INFINITY,Double.NEGATIVE_INFINITY}) {
            try { LearningEngine.trace(invalid,true,2);fail("invalid prior accepted"); }
            catch(IllegalArgumentException expected) {}
        }
        try { LearningEngine.trace(.25,true,3);fail("invalid confidence accepted"); }
        catch(IllegalArgumentException expected) {}
    }
    @Test public void strongerMasteryRaisesThePreferredDifficultyAndScoresAreExplainable() {
        long now=10*86400000L;
        assertEquals(1,LearningEngine.targetDifficulty(.25));
        assertEquals(2,LearningEngine.targetDifficulty(.65));
        assertEquals(3,LearningEngine.targetDifficulty(.85));
        assertTrue(LearningEngine.priority(.85,0,0,3,0,now)>LearningEngine.priority(.85,0,0,1,0,now));
        assertTrue(LearningEngine.priority(.25,0,0,1,0,now)>LearningEngine.priority(.25,0,0,3,0,now));
        LearningEngine.PriorityTrace score=LearningEngine.priorityTrace(.4,now-86400000L,now-86400000L,1,1,now);
        assertEquals(score.weakness+score.overdue+score.spacing+score.difficultyFit+score.repetition,score.total,1e-12);
        assertEquals(score.total,LearningEngine.priority(.4,now-86400000L,now-86400000L,1,1,now),0);
    }
    @Test public void certaintyIsStrongerEvidenceThanGuessing()  {
        assertTrue(LearningEngine.update(.25,true,2)>LearningEngine.update(.25,true,0));
        assertTrue(LearningEngine.update(.7,false,2)<.7);
    }
    @Test public void repeatedEvidenceRemainsBounded()  {
        double good=.25,bad=.25;
        for(int i=0;i<1000;i++) {
            good=LearningEngine.update(good,true,2);
            bad=LearningEngine.update(bad,false,2);
        }
        assertTrue(good>=.01&&good<=.99);
        assertTrue(bad>=.01&&bad<=.99);
        assertTrue(good>bad);
    }
    @Test public void forgettingAndUncertainAnswersScheduleEarlierReview()  {
        assertEquals(1,LearningEngine.nextInterval(30,false,2));
        assertEquals(3,LearningEngine.nextInterval(30,true,1));
        assertEquals(1,LearningEngine.nextInterval(0,true,2));
        assertEquals(60,LearningEngine.nextInterval(60,true,2));
    }
    @Test public void recentRepetitionIsPenalizedAndDueContentIsPrioritized()  {
        long now=10*86400000L;
        double normal=LearningEngine.priority(.4,now+86400000L,now-86400000L,1,0,now);
        assertTrue(LearningEngine.priority(.4,now-86400000L,now-86400000L,1,0,now)>normal);
        assertTrue(LearningEngine.priority(.4,now+86400000L,now-86400000L,1,1,now)<normal);
    }
    @Test public void spellingIsCaseInsensitiveButDoesNotIgnoreInternalMistakes()  {
        assertTrue(LearningEngine.spellingMatches("  Abandon ","abandon"));
        assertFalse(LearningEngine.spellingMatches("aban don","abandon"));
        assertFalse(LearningEngine.spellingMatches("abandonn","abandon"));
    }
}
