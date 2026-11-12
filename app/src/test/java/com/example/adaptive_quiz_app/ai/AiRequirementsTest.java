package com.example.adaptive_quiz_app.ai;
import org.junit.Test;
import static org.junit.Assert.*;
public class AiRequirementsTest {
    @Test public void recognizesCountsInActualChineseRequests(){assertEquals(Integer.valueOf(5),AiRequirements.countIn("请出5道中等难度题"));assertEquals(Integer.valueOf(1),AiRequirements.countIn("出一道简单单选题"));assertEquals(Integer.valueOf(12),AiRequirements.countIn("生成十二道题"));assertEquals(Integer.valueOf(21),AiRequirements.countIn("二十一道题"));assertNull(AiRequirements.countIn("重点考查筛选用途"));}
    @Test public void recognizesDifficultyAndRejectsUnsupportedRequests(){assertEquals(2,AiRequirements.difficultyIn("中等难度"));assertEquals(1,AiRequirements.difficultyIn("简单单选题"));assertTrue(AiRequirements.unsupportedType("出五道多选题"));assertFalse(AiRequirements.unsupportedType("单选题，不要多选题"));}
}
