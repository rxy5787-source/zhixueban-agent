package com.example.adaptive_quiz_app.learning;
import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.widget.*;
import com.example.adaptive_quiz_app.ui.TypeScale;

/** A state-count strip and native text legend; no fabricated probabilities. */
public final class MasteryChart extends LinearLayout {
    public MasteryChart(Context context,int[] values) {
        super(context);setOrientation(VERTICAL);
        float density=getResources().getDisplayMetrics().density;
        int pad=(int)(16*density+.5f);setPadding(pad,pad,pad,pad);
        GradientDrawable bg=new GradientDrawable();bg.setColor(Color.WHITE);bg.setCornerRadius(20*density);setBackground(bg);
        int[] colors={UiTokens.PRIMARY,0xff75ad98,0xffc4a578,UiTokens.LINE};
        String[] labels={"较稳 ≥80%","发展 60–79%","待巩固 <60%","尚未测试"};
        int total=0;for(int n:values)total+=n;
        LinearLayout strip=new LinearLayout(context);strip.setBackgroundColor(UiTokens.LINE);
        LayoutParams stripParams=new LayoutParams(-1,(int)(8*density));stripParams.bottomMargin=pad;addView(strip,stripParams);
        for(int i=0;i<4;i++)if(values[i]>0){android.view.View segment=new android.view.View(context);segment.setBackgroundColor(colors[i]);strip.addView(segment,new LayoutParams(0,-1,values[i]));}
        for(int rowIndex=0;rowIndex<2;rowIndex++){
            LinearLayout row=new LinearLayout(context);addView(row);
            for(int j=0;j<2;j++){
                int i=rowIndex*2+j;LinearLayout cell=new LinearLayout(context);cell.setOrientation(VERTICAL);cell.setPadding(0,0,(int)(8*density),(int)(12*density));row.addView(cell,new LayoutParams(0,-2,1));
                TextView label=new TextView(context);label.setText(labels[i]);TypeScale.apply(label,TypeScale.Role.SECONDARY);label.setTextColor(UiTokens.MUTED);cell.addView(label);
                TextView count=new TextView(context);count.setText(values[i]+" 项");TypeScale.apply(count,TypeScale.Role.ITEM);count.setTextColor(UiTokens.INK);cell.addView(count);
                cell.setContentDescription(labels[i]+"，"+values[i]+" 项，共 "+total+" 项状态");
            }
        }
    }
}
