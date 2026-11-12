package com.example.adaptive_quiz_app.ai;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
/** Deterministic form hints; the full request is also sent to the real model. */
public final class AiRequirements {
    private AiRequirements() {}
    public static Integer countIn(String text) {
        Matcher m=Pattern.compile("(\\d{1,3}|[一二两三四五六七八九十]{1,3})\\s*(?:道|题)").matcher(text);
        if(!m.find())return null;
        String value=m.group(1);
        if(value.matches("\\d+"))return Integer.parseInt(value);
        int ten=value.indexOf('十');
        if(ten>=0)return (ten==0?1:digit(value.charAt(0)))*10+(ten==value.length()-1?0:digit(value.charAt(ten+1)));
        return value.length()==1?digit(value.charAt(0)):null;
    }
    private static int digit(char value){return value=='两'?2:"零一二三四五六七八九".indexOf(value);}
    public static int difficultyIn(String text){if(text.contains("中等"))return 2;if(text.contains("困难")||text.contains("较难"))return 3;if(text.contains("简单")||text.contains("基础难度"))return 1;return 0;}
    public static boolean unsupportedType(String text){String requested=text.replaceAll("(不要|不出|不需要|不含|不包含)(多选题?|填空题?|简答题?|问答题?|判断题?)","");return Pattern.compile("多选|填空|简答|问答题|判断题|证明题").matcher(requested).find();}
}
