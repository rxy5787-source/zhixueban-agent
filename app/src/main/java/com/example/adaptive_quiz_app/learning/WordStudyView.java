package com.example.adaptive_quiz_app.learning;

import android.app.Activity;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.view.Gravity;
import android.view.View;
import android.widget.*;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import com.example.adaptive_quiz_app.ui.TypeScale;
import com.example.adaptive_quiz_app.ui.TypeScale.Role;
import static com.example.adaptive_quiz_app.ui.TypeScale.Role.*;
import java.util.ArrayList;
import java.util.List;

/** Recognition stays independent from self-rating, with a fixed primary action. */
public final class WordStudyView extends FrameLayout {
    public interface Actions {
        void speak(); void exit(); void submit(String response, int confidence);
        void next(); void star();
        default void why() {}
    }
    private final Activity activity;
    private final int ink=UiTokens.INK,muted=UiTokens.MUTED,green=UiTokens.PRIMARY;
    private final View shade;
    private final TextView submit;
    private int confidence=-1;
    private String selected;

    public WordStudyView(Activity activity,String library,String word,String phonetic,
                         int position,int total,List<String> choices,String response,
                         String expected,String example,boolean starred,Actions actions) {
        super(activity);this.activity=activity;setBackgroundColor(UiTokens.BACKGROUND);
        shade=new View(activity);shade.setBackgroundColor(Color.WHITE);
        shade.setAlpha(activity.getPreferences(0).getBoolean("studyDark",false)?1f:0f);
        addView(shade,new LayoutParams(-1,-1));
        LinearLayout layout=new LinearLayout(activity);layout.setOrientation(LinearLayout.VERTICAL);addView(layout,new LayoutParams(-1,-1));
        ViewCompat.setOnApplyWindowInsetsListener(layout,(v,in)->{
            androidx.core.graphics.Insets x=in.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.ime());
            v.setPadding(x.left,x.top,x.right,x.bottom);return in;
        });
        ViewCompat.requestApplyInsets(layout);
        LinearLayout top=new LinearLayout(activity);top.setOrientation(LinearLayout.VERTICAL);top.setPadding(dp(24),dp(10),dp(24),dp(12));layout.addView(top);
        LinearLayout header=new LinearLayout(activity);header.setGravity(Gravity.CENTER_VERTICAL);top.addView(header);
        TextView back=control("‹",ink,Color.TRANSPARENT);back.setTextSize(android.util.TypedValue.COMPLEX_UNIT_DIP,24);back.setContentDescription("退出并保存学习进度");
        header.addView(back,new LinearLayout.LayoutParams(dp(48),dp(48)));back.setOnClickListener(v->actions.exit());
        TextView title=text("单词学习",PAGE,ink);title.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));
        header.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        TextView settings=control("设置",muted,Color.TRANSPARENT);settings.setContentDescription("学习设置");
        header.addView(settings);settings.setOnClickListener(v->settings());
        TextView subtitle=text(library+" · 第 "+(position+1)+" / "+total+" 词",SECONDARY,muted);subtitle.setPadding(0,dp(8),0,dp(12));top.addView(subtitle);
        ProgressBar progress=new ProgressBar(activity,null,android.R.attr.progressBarStyleHorizontal);
        progress.setMax(total);progress.setProgress(position+(response==null?0:1));
        progress.setProgressTintList(ColorStateList.valueOf(green));progress.setProgressBackgroundTintList(ColorStateList.valueOf(UiTokens.LINE));
        top.addView(progress,new LinearLayout.LayoutParams(-1,dp(5)));
        ScrollView scroll=new ScrollView(activity);scroll.setFillViewport(true);scroll.setVerticalScrollBarEnabled(false);
        layout.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout content=new LinearLayout(activity);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(24),dp(8),dp(24),dp(20));
        scroll.addView(content,new ScrollView.LayoutParams(-1,-2));
        TextView why=control("为什么推荐？",green,Color.TRANSPARENT);
        why.setContentDescription("为什么推荐这个单词？查看推荐依据");
        LinearLayout.LayoutParams whyParams=new LinearLayout.LayoutParams(-2,-2);whyParams.gravity=Gravity.END;
        content.addView(why,whyParams);why.setOnClickListener(v->actions.why());
        LinearLayout hero=new LinearLayout(activity);hero.setOrientation(LinearLayout.VERTICAL);hero.setGravity(Gravity.CENTER);hero.setPadding(0,dp(24),0,dp(28));content.addView(hero);
        TextView term=text(word,WORD,ink);term.setGravity(Gravity.CENTER);
        hero.addView(term,new LinearLayout.LayoutParams(-1,-2));
        if(!phonetic.isEmpty()){TextView ipa=text(phonetic,BODY,muted);ipa.setGravity(Gravity.CENTER);hero.addView(ipa);}
        TextView audio=control("播放发音",green,Color.TRANSPARENT);audio.setContentDescription("播放 "+word+" 的英语发音");
        hero.addView(audio);audio.setOnClickListener(v->actions.speak());
        TextView instruction=text(response==null?"选择最贴切的释义":response.equals(expected)?"回答正确 · 记得很好":"再巩固一下 · 已标出正确释义",ITEM,
                response==null?ink:response.equals(expected)?green:UiTokens.ERROR);
        instruction.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));instruction.setPadding(0,dp(8),0,dp(14));
        instruction.setAccessibilityLiveRegion(ACCESSIBILITY_LIVE_REGION_POLITE);content.addView(instruction);
        LinearLayout followup=new LinearLayout(activity);followup.setOrientation(LinearLayout.VERTICAL);
        List<LinearLayout> optionViews=new ArrayList<>();
        for(int i=0;i<choices.size();i++){
            String choice=choices.get(i);LinearLayout option=new LinearLayout(activity);option.setGravity(Gravity.CENTER_VERTICAL);
            option.setMinimumHeight(dp(60));option.setPadding(dp(16),dp(14),dp(16),dp(14));
            TextView letter=text(String.valueOf((char)('A'+i)),BODY,green);option.addView(letter,new LinearLayout.LayoutParams(dp(28),-2));
            TextView meaning=text(choice,READING,ink);option.addView(meaning,new LinearLayout.LayoutParams(0,-2,1));
            TextView mark=text("",READING,green);mark.setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);option.addView(mark);
            int fill=Color.WHITE,stroke=UiTokens.LINE;
            if(response!=null&&choice.equals(expected)){fill=UiTokens.SOFT;stroke=green;mark.setText("✓");}
            else if(response!=null&&choice.equals(response)){fill=UiTokens.ERROR_SOFT;stroke=UiTokens.ERROR;mark.setText("×");mark.setTextColor(UiTokens.ERROR);}
            option.setBackground(glass(fill,stroke));option.setFocusable(response==null);option.setClickable(response==null);
            option.setContentDescription(choice+(response==null?"":choice.equals(expected)?"，正确答案":choice.equals(response)?"，你的答案，错误":""));
            LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(12);content.addView(option,p);optionViews.add(option);
            if(response==null)option.setOnClickListener(v->{
                selected=choice;
                for(int j=0;j<optionViews.size();j++){
                    LinearLayout item=optionViews.get(j);boolean active=j==choices.indexOf(choice);
                    item.setBackground(glass(active?UiTokens.SOFT:Color.WHITE,active?green:UiTokens.LINE));item.setSelected(active);
                    ((TextView)item.getChildAt(2)).setText(active?"✓":"");
                }
                followup.setVisibility(VISIBLE);updateSubmit();
                scroll.post(()->scroll.smoothScrollTo(0,Math.max(0,followup.getTop()-dp(24))));
            });
        }
        content.addView(followup);
        Button action=new Button(activity);action.setText(response==null?"提交答案":position+1==total?"完成本轮":"下一词");
        action.setAllCaps(false);TypeScale.apply(action,BUTTON);action.setTextColor(Color.WHITE);
        action.setMinHeight(dp(52));action.setMinimumHeight(dp(52));action.setPadding(dp(16),dp(12),dp(16),dp(12));
        action.setBackground(glass(green,green));action.setBackgroundTintList(null);action.setStateListAnimator(null);submit=action;
        if(response==null){
            followup.setVisibility(GONE);
            TextView prompt=text("有多大把握？",ITEM,ink);prompt.setPadding(0,dp(8),0,dp(12));followup.addView(prompt);
            LinearLayout chips=new LinearLayout(activity);followup.addView(chips);
            String[] levels={"猜的","犹豫","确定"};
            for(int i=0;i<3;i++){
                final int level=i;TextView chip=control(levels[i],ink,Color.WHITE);
                LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-2,1);p.setMargins(i==0?0:dp(6),0,0,dp(12));chips.addView(chip,p);
                chip.setOnClickListener(v->{confidence=level;for(int j=0;j<3;j++){View item=chips.getChildAt(j);item.setBackground(glass(j==level?UiTokens.SOFT:Color.WHITE,j==level?green:UiTokens.LINE));item.setSelected(j==level);}updateSubmit();});
            }
            TextView tip=text("释义与把握程度选好后，再提交。",SECONDARY,muted);followup.addView(tip);
            submit.setOnClickListener(v->{if(selected!=null&&confidence>=0){submit.setEnabled(false);try{actions.submit(selected,confidence);}finally{submit.setEnabled(true);}}});
            updateSubmit();
        }else{
            TextView detail=text(expected+"\n"+example,READING,ink);detail.setPadding(dp(16),dp(16),dp(16),dp(16));detail.setBackground(glass(Color.WHITE,UiTokens.LINE));followup.addView(detail);
            TextView star=control(starred?"已收藏":"收藏",green,Color.TRANSPARENT);followup.addView(star);star.setOnClickListener(v->actions.star());
            submit.setOnClickListener(v->{submit.setEnabled(false);try{actions.next();}finally{submit.setEnabled(true);}});
        }
        View divider=new View(activity);divider.setBackgroundColor(UiTokens.LINE);layout.addView(divider,new LinearLayout.LayoutParams(-1,dp(1)));
        LinearLayout footer=new LinearLayout(activity);footer.setOrientation(LinearLayout.VERTICAL);footer.setBackgroundColor(Color.WHITE);footer.setPadding(dp(24),dp(12),dp(24),dp(12));layout.addView(footer);
        footer.addView(submit,new LinearLayout.LayoutParams(-1,-2));
    }
    private void settings(){
        boolean[] values={activity.getPreferences(0).getBoolean("studyDark",false),activity.getPreferences(0).getBoolean("studyAutoSpeak",false)};
        TypeScale.dialog(new androidx.appcompat.app.AlertDialog.Builder(activity).setTitle("学习设置")
            .setMultiChoiceItems(new String[]{"使用纯白背景","进入单词时自动发音"},values,(dialog,index,checked)->{
                activity.getPreferences(0).edit().putBoolean(index==0?"studyDark":"studyAutoSpeak",checked).apply();if(index==0)shade.setAlpha(checked?1f:0f);
            }).setPositiveButton("完成",null).create());
    }
    private void updateSubmit(){submit.setEnabled(selected!=null&&confidence>=0);submit.setAlpha(submit.isEnabled()?1:.45f);}
    private int dp(int value){return (int)(value*getResources().getDisplayMetrics().density+.5f);}
    private TextView text(String value,Role role,int color){TextView t=new TextView(activity);t.setText(value);TypeScale.apply(t,role);t.setTextColor(color);return t;}
    private TextView control(String value,int color,int fill){TextView t=text(value,BODY,color);t.setGravity(Gravity.CENTER);t.setPadding(dp(12),dp(12),dp(12),dp(12));t.setMinimumHeight(dp(48));t.setMinimumWidth(dp(48));t.setBackground(glass(fill,fill==Color.TRANSPARENT?Color.TRANSPARENT:UiTokens.LINE));t.setFocusable(true);return t;}
    private RippleDrawable glass(int fill,int border){GradientDrawable g=new GradientDrawable();g.setColor(fill);g.setCornerRadius(dp(fill==green?26:16));g.setStroke(dp(1),border);return new RippleDrawable(ColorStateList.valueOf(0x18137d73),g,null);}
}
