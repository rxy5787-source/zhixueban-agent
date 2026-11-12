package com.example.adaptive_quiz_app.learning;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.util.Arrays;

/** Original small practice sets, not official exam questions or learner evidence. */
public final class SubjectSamples {
    private SubjectSamples(){}
    public static JSONObject content() throws JSONException {
        JSONArray libraries=new JSONArray();
        libraries.put(library("数学基础 · 示例","数学",new String[][]{
            {"函数与导数","导数描述函数的局部变化率。幂函数 x^n 的导数为 n*x^(n-1)。","f(x)=x^2，f'(x)=2x。"},
            {"概率基础","等可能结果的概率为有利结果数除以全部结果数。独立事件交集概率相乘。","独立抛两枚硬币，同时正面的概率为 1/4。"}
        },new String[][]{
            {"函数与导数","f(x)=x^2，f'(x) 是？","x|2x|x^3|2","B","按幂函数求导规则，导数为 2x。","1"},
            {"函数与导数","f(x)=3x^2+2x，在 x=1 处的导数为？","3|5|6|8","D","f'(x)=6x+2，代入 x=1 得 8。","2"},
            {"函数与导数","f(x)=x^3-3x，在开区间 (-1,1) 上的变化情况是？","严格递增|严格递减|恒定|先增后减","B","f'(x)=3x^2-3，在 (-1,1) 内小于零，因此严格递减。","3"},
            {"概率基础","掷一枚均匀六面骰子，点数为偶数的概率为？","1/6|1/3|1/2|2/3","C","偶数为 2、4、6，占六个等可能结果中的三个。","1"},
            {"概率基础","独立抛两枚均匀硬币，恰有一枚正面的概率为？","1/4|1/2|3/4|1","B","四个等可能结果中，正反、反正符合条件。","2"},
            {"概率基础","袋中有 3 个红球、2 个蓝球，不放回抽两球，都为红球的概率为？","3/10|9/25|1/5|3/5","A","第一次红球概率 3/5，之后剩 2 红、2 蓝共 4 球；概率为 (3/5)*(2/4)=3/10。","3"}
        }));
        libraries.put(library("公考推理 · 示例","公考",new String[][]{
            {"数列规律","观察相邻差值、倍数与周期；有限数列可能有多种延拓，练习按题目给定规律。","按连续奇数递增：1、4、9、16，下一项为 25。"},
            {"条件推理","若 P 则 Q 的逆否命题为若非 Q 则非 P；不能直接推出若 Q 则 P。","若下雨则路湿；路不湿可推出没下雨。"}
        },new String[][]{
            {"数列规律","按等差规律：3、6、9、12，下一项为？","13|14|15|18","C","每次增加 3，下一项为 15。","1"},
            {"数列规律","相邻差值依次为 3、5、7、9：1、4、9、16，下一项为？","20|23|24|25","D","16+9=25，与平方数规律一致。","2"},
            {"数列规律","按前两项相加得到下一项：2、3、5、8、13，下一项为？","18|20|21|26","C","下一项为 8+13=21。","3"},
            {"条件推理","若通过考试则获得证书。小林通过了考试，可推出？","获得证书|未获证书|没有复习|无法推出任何结论","A","由充分条件和前件成立，可推出后件成立。","1"},
            {"条件推理","若参加训练则佩戴护具。小林没有佩戴护具，可推出？","参加训练|没有参加训练|一定受伤|拥有护具","B","由逆否命题，未佩戴护具推出未参加训练。","2"},
            {"条件推理","若 P 则 Q，若 Q 则 R，已知非 R，可以推出？","P|Q|非 P|不能推理","C","非 R 推出非 Q，再推出非 P。","3"}
        }));
        libraries.put(library("考研数学 · 示例","考研",new String[][]{
            {"极限基础","连续函数可代入计算极限；sin(x)/x 在 x 趋于零时的极限为 1，角度采用弧度。","当 x 趋于 0，sin(2x)/x 趋于 2。"},
            {"定积分","定积分可由原函数在区间端点的差计算。","从 0 到 1 对 x 积分，结果为 1/2。"}
        },new String[][]{
            {"极限基础","当 x 趋于 2，x^2 的极限为？","2|4|8|不存在","B","多项式连续，直接代入 x=2 得 4。","1"},
            {"极限基础","角度为弧度，当 x 趋于 0，sin(3x)/x 的极限为？","0|1|3|不存在","C","写成 3*sin(3x)/(3x)，应用基本极限得 3。","2"},
            {"极限基础","当 x 趋于 1，(x^2-1)/(x-1) 的极限为？","0|1|2|不存在","C","在 x 不等于 1 时约分为 x+1，极限为 2。","3"},
            {"定积分","从 0 到 1 对常数函数 1 积分，结果为？","0|1/2|1|2","C","原函数为 x，端点差为 1-0。","1"},
            {"定积分","从 0 到 2 对 x 积分，结果为？","1|2|3|4","B","原函数 x^2/2，在端点的差为 2。","2"},
            {"定积分","从 -1 到 1 对 x^3+x^2 积分，结果为？","0|1/3|2/3|2","C","奇函数 x^3 在对称区间积分为 0，x^2 积分为 2/3。","3"}
        }));
        return LearningStore.obj("format","zhixue-content","version",1,"libraries",libraries);
    }
    private static JSONObject library(String name,String subject,String[][] concepts,String[][] questions) throws JSONException {
        JSONArray points=new JSONArray(),items=new JSONArray();
        for(String[] point:concepts)points.put(LearningStore.obj("name",point[0],"summary",point[1],"example",point[2],"mnemonic",""));
        for(String[] question:questions)items.put(LearningStore.obj("kind","question","prompt",question[1],"options",new JSONArray(Arrays.asList(question[2].split("\\|"))),"answer",question[3],"explanation",question[4],"difficulty",Integer.parseInt(question[5]),"points",new JSONArray().put(question[0])));
        return LearningStore.obj("name",name,"subject",subject,"kind","question","points",points,"items",items);
    }
}
