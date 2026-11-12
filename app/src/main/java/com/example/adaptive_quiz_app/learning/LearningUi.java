package com.example.adaptive_quiz_app.learning;

import android.content.res.ColorStateList;
import android.graphics.*;
import android.graphics.drawable.*;
import android.view.Gravity;
import android.view.View;
import android.widget.*;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import com.example.adaptive_quiz_app.ui.TypeScale;
import com.example.adaptive_quiz_app.ui.TypeScale.Role;
import static com.example.adaptive_quiz_app.ui.TypeScale.Role.*;

/** Shared native components; dimensions respect device density and text scaling. */
public abstract class LearningUi extends AppCompatActivity {
    protected final int GREEN=UiTokens.PRIMARY,INK=UiTokens.INK,
        MUTED=UiTokens.MUTED,BG=UiTokens.BACKGROUND,
        LINE=UiTokens.LINE,SOFT=UiTokens.SOFT;
    protected LinearLayout root,body;
    protected int tab=0;
    protected abstract void home(int tab);
    protected abstract void back();
    protected abstract void quickLearn();
    protected int dp(int n) {return (int)(n*getResources().getDisplayMetrics().density+.5f);}
    protected GradientDrawable shape(int color,int radius) {
        GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(radius));return d;
    }
    private GradientDrawable outlined(int color,int radius,int stroke) {
        GradientDrawable d=shape(color,radius);d.setStroke(dp(1),stroke);return d;
    }
    private RippleDrawable ripple(int color,int radius) {
        return new RippleDrawable(ColorStateList.valueOf(Color.argb(28,26,105,94)),shape(color,radius),shape(Color.WHITE,radius));
    }
    private RippleDrawable warmButton(int radius) {
        return ripple(GREEN,radius);
    }
    protected TextView label(String s,Role role,int color,boolean emphasis) {
        TextView t=new TextView(this);t.setText(s);TypeScale.apply(t,role);t.setTextColor(color);
        t.setFontFeatureSettings("tnum");
        if(emphasis&&!role.medium)t.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));
        return t;
    }
    protected void page(String name,boolean secondary,boolean navigation) {
        androidx.core.view.WindowInsetsControllerCompat bars=new androidx.core.view.WindowInsetsControllerCompat(getWindow(),getWindow().getDecorView());
        bars.setAppearanceLightStatusBars(true);bars.setAppearanceLightNavigationBars(true);
        getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(Color.WHITE);
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(BG);setContentView(root);
        ViewCompat.setOnApplyWindowInsetsListener(root,(v,in)->{
            androidx.core.graphics.Insets x=in.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.ime());
            v.setPadding(x.left,x.top,x.right,x.bottom);return in;
        });
        ViewCompat.requestApplyInsets(root);
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(24),dp(10),dp(24),dp(10));root.addView(header);
        if(secondary) {
            FrameLayout arrow=new FrameLayout(this);arrow.setBackground(ripple(Color.WHITE,16));arrow.setContentDescription("返回");
            arrow.setOnClickListener(v->back());arrow.setFocusable(true);
            arrow.addView(new LineIcon("back",INK),new FrameLayout.LayoutParams(dp(22),dp(22),Gravity.CENTER));
            LinearLayout.LayoutParams ap=new LinearLayout.LayoutParams(dp(48),dp(48));ap.setMarginEnd(dp(12));header.addView(arrow,ap);
        }
        header.addView(label(name,PAGE,INK,true),new LinearLayout.LayoutParams(0,-2,1));
        if(navigation) {
            ImageView mark=new ImageView(this);mark.setImageResource(com.example.adaptive_quiz_app.R.drawable.ic_zhixue);
            mark.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);header.addView(mark,new LinearLayout.LayoutParams(dp(28),dp(28)));
        }
        ScrollView scroll=new ScrollView(this) {
            @Override public boolean requestChildRectangleOnScreen(View child,Rect rectangle,boolean immediate) {
                // Keep focused controls comfortably above gesture navigation, including large fonts.
                Rect visible=new Rect(rectangle);visible.top-=dp(12);visible.bottom+=dp(48);
                return super.requestChildRectangleOnScreen(child,visible,immediate);
            }
        };scroll.setFillViewport(true);scroll.setVerticalScrollBarEnabled(false);
        root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(24),dp(8),dp(24),dp(64));body.setClipToPadding(false);body.setClipChildren(false);
        scroll.addView(body,new ScrollView.LayoutParams(Math.min(getResources().getDisplayMetrics().widthPixels,dp(680)),-2,Gravity.CENTER_HORIZONTAL));
        if(navigation) {
            View line=new View(this);line.setBackgroundColor(LINE);root.addView(line,new LinearLayout.LayoutParams(-1,dp(1)));
            LinearLayout nav=new LinearLayout(this);nav.setPadding(dp(6),dp(8),dp(6),dp(6));nav.setBackgroundColor(Color.WHITE);root.addView(nav);
            String[] names={"今日","知识库","我的"},icons={"home","book","person"};
            int[] destinations={0,1,3};
            for(int i=0;i<names.length;i++) {
                final int index=destinations[i];boolean active=tab==index;
                LinearLayout item=new LinearLayout(this);item.setOrientation(LinearLayout.VERTICAL);item.setGravity(Gravity.CENTER);
                item.setMinimumHeight(dp(62));item.setPadding(dp(2),dp(4),dp(2),dp(4));
                item.setBackground(ripple(Color.WHITE,16));item.setSelected(active);item.setFocusable(true);
                item.setContentDescription(index<0?"开始学习":names[i]+(active?"，当前页面":""));item.setOnClickListener(v->{if(index<0)quickLearn();else home(index);});
                if(index<0) {
                    FrameLayout circle=new FrameLayout(this);circle.setBackground(warmButton(32));
                    circle.addView(new LineIcon("play",INK),new FrameLayout.LayoutParams(dp(22),dp(22),Gravity.CENTER));
                    item.addView(circle,new LinearLayout.LayoutParams(dp(48),dp(48)));
                } else {
                    FrameLayout indicator=new FrameLayout(this);
                    indicator.addView(new LineIcon(icons[i],active?GREEN:MUTED),new FrameLayout.LayoutParams(dp(22),dp(22),Gravity.CENTER));
                    item.addView(indicator,new LinearLayout.LayoutParams(dp(56),dp(32)));
                }
                TextView caption=label(names[i],SECONDARY,active?GREEN:MUTED,active);caption.setGravity(Gravity.CENTER);
                LinearLayout.LayoutParams cp=new LinearLayout.LayoutParams(-1,-2);cp.topMargin=dp(5);item.addView(caption,cp);
                LinearLayout.LayoutParams np=new LinearLayout.LayoutParams(0,-2,1);np.setMargins(dp(3),0,dp(3),0);nav.addView(item,np);
            }
        }
    }
    protected TextView text(String s,Role role,int color) {
        TextView t=label(s,role,color,false);t.setPadding(0,dp(6),0,dp(8));body.addView(t);return t;
    }
    protected void heading(String s) {
        TextView t=text(s,SECTION,INK);t.setPadding(0,dp(16),0,dp(12));
    }
    protected void headline(String s) {
        TextView t=text(s,HERO,INK);t.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));t.setPadding(0,dp(4),0,dp(16));
    }
    protected void note(String s) {text(s,SECONDARY,MUTED);}
    protected void card(String h,String detail,Runnable action) {
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(16),dp(18),dp(14),dp(18));
        row.setBackground(action==null?shape(Color.WHITE,20):ripple(Color.WHITE,20));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(10);body.addView(row,p);
        LinearLayout copy=new LinearLayout(this);copy.setOrientation(LinearLayout.VERTICAL);row.addView(copy,new LinearLayout.LayoutParams(0,-2,1));
        copy.addView(label(h,ITEM,INK,true));TextView detailView=label(detail,BODY,MUTED,false);
        LinearLayout.LayoutParams bp=new LinearLayout.LayoutParams(-1,-2);bp.topMargin=dp(8);copy.addView(detailView,bp);
        if(action!=null) {
            LinearLayout.LayoutParams ip=new LinearLayout.LayoutParams(dp(20),dp(20));ip.setMarginStart(dp(10));row.addView(new LineIcon("chevron",GREEN),ip);
            row.setOnClickListener(v->action.run());row.setFocusable(true);
        }
    }
    protected Button button(String s,Runnable action) {
        Button b=new Button(this);b.setText(s);b.setTextColor(Color.WHITE);TypeScale.apply(b,BUTTON);b.setAllCaps(false);
        b.setMinHeight(dp(52));b.setMinimumHeight(dp(52));
        b.setTextColor(Color.WHITE);b.setPadding(dp(16),dp(12),dp(16),dp(12));b.setBackground(warmButton(26));b.setBackgroundTintList(null);b.setStateListAnimator(null);
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(8);p.bottomMargin=dp(12);body.addView(b,p);b.setOnClickListener(v->action.run());return b;
    }
    /** Keep the primary practice action visible while content scrolls or the IME opens. */
    protected void fixedAction(Button button) {
        ((android.view.ViewGroup)button.getParent()).removeView(button);
        LinearLayout footer=new LinearLayout(this);footer.setPadding(dp(24),dp(12),dp(24),dp(12));footer.setBackgroundColor(Color.WHITE);
        View divider=new View(this);divider.setBackgroundColor(LINE);root.addView(divider,new LinearLayout.LayoutParams(-1,dp(1)));
        root.addView(footer,new LinearLayout.LayoutParams(-1,-2));footer.addView(button,new LinearLayout.LayoutParams(-1,-2));
    }
    protected LinearLayout surface(int color) {
        LinearLayout group=new LinearLayout(this);group.setOrientation(LinearLayout.VERTICAL);group.setPadding(dp(18),dp(16),dp(18),dp(12));group.setBackground(shape(color,20));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(14);body.addView(group,p);return group;
    }
    protected void feedback(boolean correct,String detail) {
        LinearLayout saved=body;body=surface(correct?SOFT:UiTokens.ERROR_SOFT);
        text(correct?"回答正确":"再巩固一下",SECTION,correct?GREEN:UiTokens.ERROR);
        text(detail,ITEM,INK);body=saved;
    }
    protected void profileHeader() {
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(0,dp(8),0,dp(20));body.addView(row);
        ImageView mark=new ImageView(this);mark.setImageResource(com.example.adaptive_quiz_app.R.drawable.ic_zhixue);mark.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        mark.setBackground(shape(SOFT,18));mark.setPadding(dp(10),dp(10),dp(10),dp(10));LinearLayout.LayoutParams mp=new LinearLayout.LayoutParams(dp(56),dp(56));mp.setMarginEnd(dp(14));row.addView(mark,mp);
        LinearLayout copy=new LinearLayout(this);copy.setOrientation(LinearLayout.VERTICAL);row.addView(copy,new LinearLayout.LayoutParams(0,-2,1));copy.addView(label("我的学习空间",PAGE,INK,true));
        TextView subtitle=label(profileDescription(),SECONDARY,MUTED,false);subtitle.setPadding(0,dp(6),0,0);copy.addView(subtitle);
    }
    protected String profileDescription(){return "联网学习 · 记录保存在本机";}
    protected void link(String s,Runnable action) {
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setMinimumHeight(dp(52));
        row.setPadding(dp(14),dp(14),dp(12),dp(14));row.setBackground(ripple(Color.WHITE,12));row.setFocusable(true);
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(5);body.addView(row,p);
        row.addView(label(s+"  ›",BODY,GREEN,false),new LinearLayout.LayoutParams(-1,-2));row.setOnClickListener(v->action.run());
    }
    protected EditText input(String hint,String value) {
        EditText e=new EditText(this);e.setText(value);e.setHint(hint);TypeScale.apply(e,BODY);e.setTextColor(INK);e.setHintTextColor(MUTED);
        e.setMinimumHeight(dp(52));e.setPadding(dp(14),dp(14),dp(14),dp(14));
        StateListDrawable state=new StateListDrawable();state.addState(new int[]{android.R.attr.state_focused},outlined(Color.WHITE,14,GREEN));state.addState(new int[]{},outlined(Color.WHITE,14,LINE));e.setBackground(state);
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(12);p.topMargin=dp(6);body.addView(e,p);return e;
    }
    protected Spinner spinner(String[] entries) {
        Spinner s=new Spinner(this);
        s.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,entries) {
            @Override public View getView(int position,View convert,android.view.ViewGroup parent) {
                TextView t=label(getItem(position),BODY,INK,false);t.setSingleLine(true);t.setEllipsize(android.text.TextUtils.TruncateAt.END);
                t.setPadding(dp(4),dp(14),dp(4),dp(14));t.setCompoundDrawablePadding(dp(6));
                t.setCompoundDrawablesWithIntrinsicBounds(0,0,android.R.drawable.arrow_down_float,0);t.setContentDescription(getItem(position));return t;
            }
            @Override public View getDropDownView(int position,View convert,android.view.ViewGroup parent) {
                TextView t=label(getItem(position),BODY,INK,false);t.setPadding(dp(16),dp(14),dp(16),dp(14));t.setMinHeight(dp(48));return t;
            }
        });
        s.setBackground(outlined(Color.WHITE,12,LINE));s.setPadding(dp(10),0,dp(10),0);
        s.setMinimumHeight(dp(52));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(8);body.addView(s,p);return s;
    }
    protected void choice(RadioButton r,boolean compact) {
        TypeScale.apply(r,compact?BODY:READING);r.setTextColor(INK);r.setMinHeight(dp(compact?48:60));r.setPadding(dp(compact?4:16),dp(12),dp(compact?4:16),dp(12));r.setButtonTintList(ColorStateList.valueOf(GREEN));
        r.setButtonDrawable(null);r.setGravity(compact?Gravity.CENTER:Gravity.CENTER_VERTICAL);
        StateListDrawable states=new StateListDrawable();states.addState(new int[]{android.R.attr.state_checked},outlined(SOFT,16,GREEN));states.addState(new int[]{},outlined(Color.WHITE,16,LINE));r.setBackground(states);
        RadioGroup.LayoutParams p=new RadioGroup.LayoutParams(compact?0:-1,-2,compact?1:0);p.bottomMargin=dp(10);
        if(compact)p.setMargins(dp(2),0,dp(2),dp(10));r.setLayoutParams(p);
    }
    protected ProgressBar progress(int max,int value) {
        ProgressBar p=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);p.setMax(Math.max(1,max));p.setProgress(value);
        p.setProgressTintList(ColorStateList.valueOf(GREEN));p.setProgressBackgroundTintList(ColorStateList.valueOf(LINE));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(5));lp.bottomMargin=dp(8);body.addView(p,lp);return p;
    }
    protected void learningIntro(String title,String detail) {
        LinearLayout saved=body;body=surface(SOFT);
        TextView h=text(title,PAGE,INK);h.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));
        if(!detail.isEmpty())note(detail);
        body=saved;
    }
    protected void dailyPlan(int target,int completed,long tasks,long submitted,String action,Runnable run,Runnable plans,int dailyAmount) {
        LinearLayout saved=body;body=surface(Color.WHITE);
        LinearLayout heading=new LinearLayout(this);heading.setGravity(Gravity.CENTER_VERTICAL);body.addView(heading);
        heading.addView(label("今日计划",SECTION,INK,true),new LinearLayout.LayoutParams(0,-2,1));
        // A single detailed-plan link follows the summary; keep the primary action unambiguous.
        metrics(new String[]{completed+" / "+target,String.valueOf(tasks)},new String[]{"完成 / 基础计划","待巩固任务"});
        progress(target,completed);Button start=button(action,run);
        LinearLayout.LayoutParams sp=(LinearLayout.LayoutParams)start.getLayoutParams();sp.topMargin=0;sp.bottomMargin=dp(4);start.setLayoutParams(sp);
        note("每库每日 "+dailyAmount+" 条 · 今日已作答 "+submitted+" 次");
        body=saved;
        link("查看全部今日计划",plans);
    }
    protected void illustration(String scene,int height) {
        body.addView(new StudyIllustration(this,scene),new LinearLayout.LayoutParams(-1,dp(height)));
    }
    protected void quickEntries(String first,String firstDetail,Runnable firstRun,String second,String secondDetail,Runnable secondRun) {
        LinearLayout row=new LinearLayout(this);LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(-1,-2);rp.bottomMargin=dp(12);body.addView(row,rp);
        String[] titles={first,second},details={firstDetail,secondDetail};Runnable[] actions={firstRun,secondRun};
        for(int i=0;i<2;i++) {
            LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(14),dp(16),dp(14),dp(16));
            box.setMinimumHeight(dp(88));box.setBackground(ripple(i==0?SOFT:UiTokens.SAND,20));
            TextView title=label(titles[i],ITEM,INK,true);box.addView(title);
            TextView detail=label(details[i],SECONDARY,MUTED,false);detail.setPadding(0,dp(8),0,0);box.addView(detail);
            LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-2,1);if(i==0)p.setMarginEnd(dp(10));row.addView(box,p);
            final Runnable run=actions[i];box.setFocusable(true);box.setOnClickListener(v->run.run());
        }
    }
    protected void emptyState(String title,String detail) {
        illustration("search",100);TextView h=text(title,SECTION,INK);h.setGravity(Gravity.CENTER);
        TextView description=text(detail,BODY,MUTED);description.setGravity(Gravity.CENTER);
    }
    protected void toggle(String title,boolean checked,java.util.function.Consumer<Boolean> action) {
        com.google.android.material.materialswitch.MaterialSwitch control=new com.google.android.material.materialswitch.MaterialSwitch(this);
        control.setText(title);control.setTextColor(INK);TypeScale.apply(control,BODY);control.setMinHeight(dp(56));
        control.setChecked(checked);body.addView(control,new LinearLayout.LayoutParams(-1,-2));
        control.setOnCheckedChangeListener((button,value)->action.accept(value));
    }
    protected void libraryTile(String name,String subject,boolean word,long total,long seen,Runnable run) {
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(16),dp(16),dp(16),dp(16));box.setBackground(ripple(Color.WHITE,20));box.setFocusable(true);
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(12);body.addView(box,p);
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);box.addView(row);
        FrameLayout tile=new FrameLayout(this);tile.setBackground(shape(SOFT,10));
        TextView cover=label(word?"EN":subject.contains("计算机")?"SQL":subject.substring(0,Math.min(2,subject.length())),BODY,GREEN,true);cover.setGravity(Gravity.CENTER);
        tile.addView(cover,new FrameLayout.LayoutParams(-1,-1));
        LinearLayout.LayoutParams tp=new LinearLayout.LayoutParams(dp(46),dp(64));tp.setMarginEnd(dp(12));row.addView(tile,tp);
        LinearLayout copy=new LinearLayout(this);copy.setOrientation(LinearLayout.VERTICAL);row.addView(copy,new LinearLayout.LayoutParams(0,-2,1));
        copy.addView(label(name,SECTION,INK,true));TextView type=label((word?"词库":"题库")+" · "+total+" 条",SECONDARY,MUTED,false);type.setPadding(0,dp(6),0,0);copy.addView(type);
        TextView status=label(total==0?"知识库为空，先添加或导入内容。":"已测试 "+seen+" / "+total+" 条",CAPTION,GREEN,false);status.setPadding(0,dp(6),0,0);copy.addView(status);
        row.addView(new LineIcon("chevron",MUTED),new LinearLayout.LayoutParams(dp(18),dp(18)));
        box.setOnClickListener(v->run.run());
    }
    protected void metrics(String[] values,String[] names) {
        LinearLayout row=new LinearLayout(this);row.setPadding(0,dp(4),0,dp(4));
        LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(-1,-2);rp.bottomMargin=dp(12);body.addView(row,rp);
        for(int i=0;i<values.length;i++) {
            LinearLayout metric=new LinearLayout(this);metric.setOrientation(LinearLayout.VERTICAL);metric.setPadding(dp(5),0,dp(5),0);
            row.addView(metric,new LinearLayout.LayoutParams(0,-2,1));TextView value=label(values[i],METRIC,GREEN,true);
            metric.addView(value,new LinearLayout.LayoutParams(-1,-2));
            TextView name=label(names[i],CAPTION,MUTED,false);name.setPadding(0,dp(8),0,0);metric.addView(name);
        }
    }
    protected void disclosure(String name,boolean expanded,Runnable action) {
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(14),dp(18),dp(14),dp(18));row.setMinimumHeight(dp(56));
        row.setBackground(ripple(Color.TRANSPARENT,12));row.setFocusable(true);row.setContentDescription(name+(expanded?"，已展开":"，已收起"));
        row.addView(label(name,ITEM,INK,true),new LinearLayout.LayoutParams(0,-2,1));
        LineIcon icon=new LineIcon("chevron",GREEN);icon.setRotation(expanded?90:0);row.addView(icon,new LinearLayout.LayoutParams(dp(18),dp(18)));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(10);body.addView(row,p);row.setOnClickListener(v->action.run());
    }
    protected void segments(String[] names,int selected,java.util.function.IntConsumer action) {
        LinearLayout row=new LinearLayout(this);row.setPadding(dp(4),dp(4),dp(4),dp(4));row.setBackground(shape(SOFT,18));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(18);body.addView(row,p);
        for(int i=0;i<names.length;i++) {
            final int index=i;TextView t=label(names[i],BODY,i==selected?GREEN:MUTED,i==selected);t.setGravity(Gravity.CENTER);t.setMinHeight(dp(48));t.setPadding(dp(4),dp(12),dp(4),dp(12));
            t.setBackground(ripple(i==selected?Color.WHITE:SOFT,14));t.setSelected(i==selected);t.setFocusable(true);t.setOnClickListener(v->action.accept(index));
            row.addView(t,new LinearLayout.LayoutParams(0,-2,1));
        }
    }
    protected void pager(Runnable previous,Runnable next) {
        LinearLayout row=new LinearLayout(this);LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(-1,-2);rp.bottomMargin=dp(12);body.addView(row,rp);
        String[] names={"上一页","下一页"};Runnable[] actions={previous,next};
        for(int i=0;i<2;i++) {
            TextView t=label(names[i],BODY,actions[i]==null?MUTED:GREEN,true);t.setGravity(Gravity.CENTER);t.setMinHeight(dp(48));t.setPadding(dp(8),dp(12),dp(8),dp(12));
            t.setBackground(ripple(SOFT,14));t.setEnabled(actions[i]!=null);t.setAlpha(actions[i]==null?.45f:1f);t.setFocusable(actions[i]!=null);
            final Runnable action=actions[i];if(action!=null)t.setOnClickListener(v->action.run());
            LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-2,1);p.setMargins(dp(3),0,dp(3),0);row.addView(t,p);
        }
    }
    /** Locally drawn line icons avoid symbol-font and network dependencies. */
    private final class LineIcon extends View {
        private final String kind;private final Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);
        LineIcon(String kind,int color) {super(LearningUi.this);this.kind=kind;p.setColor(color);p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(1.7f);p.setStrokeCap(Paint.Cap.ROUND);p.setStrokeJoin(Paint.Join.ROUND);setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);}
        @Override protected void onDraw(Canvas c) {
            super.onDraw(c);c.save();c.scale(getWidth()/24f,getHeight()/24f);Path path=new Path();
            switch(kind) {
                case "home":path.moveTo(3,11);path.lineTo(12,3);path.lineTo(21,11);path.moveTo(5,10);path.lineTo(5,21);path.lineTo(10,21);path.lineTo(10,15);path.lineTo(14,15);path.lineTo(14,21);path.lineTo(19,21);path.lineTo(19,10);break;
                case "book":c.drawRoundRect(3,4,21,20,2,2,p);c.drawLine(12,4,12,20,p);c.drawLine(6,8,9,8,p);c.drawLine(15,8,18,8,p);c.drawLine(6,12,9,12,p);c.drawLine(15,12,18,12,p);break;
                case "chart":path.moveTo(4,4);path.lineTo(4,20);path.lineTo(21,20);path.moveTo(8,16);path.lineTo(8,12);path.moveTo(13,16);path.lineTo(13,8);path.moveTo(18,16);path.lineTo(18,4);break;
                case "person":c.drawCircle(12,7,4,p);c.drawArc(4,13,20,27,180,180,false,p);break;
                case "play":path.moveTo(8,4);path.lineTo(19,12);path.lineTo(8,20);path.close();p.setStyle(Paint.Style.FILL);break;
                case "word":path.moveTo(3,19);path.lineTo(9,4);path.lineTo(15,19);path.moveTo(5,14);path.lineTo(13,14);path.moveTo(17,9);path.lineTo(22,9);path.moveTo(19.5f,9);path.lineTo(19.5f,19);break;
                case "back":path.moveTo(15,5);path.lineTo(8,12);path.lineTo(15,19);break;
                default:path.moveTo(9,6);path.lineTo(15,12);path.lineTo(9,18);
            }
            c.drawPath(path,p);c.restore();
        }
    }
    protected void toast(String s) {Toast.makeText(this,s,Toast.LENGTH_LONG).show();}
    protected void confirm(String name,String detail,Runnable r) {TypeScale.dialog(new androidx.appcompat.app.AlertDialog.Builder(this).setTitle(name).setMessage(detail).setNegativeButton("取消",null).setPositiveButton("确认",(d,w)->r.run()).create());}
    protected void safely(Work work) {try{work.run();}catch(Exception e){toast("操作失败："+e.getMessage());}}
    protected interface Work {void run() throws Exception;}
    protected String percent(double x) {return Math.round(x*100)+"%";}
}
