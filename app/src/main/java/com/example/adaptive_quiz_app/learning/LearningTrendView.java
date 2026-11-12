package com.example.adaptive_quiz_app.learning;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.View;
import com.example.adaptive_quiz_app.ui.TypeScale;

/** Seven civil days: bar height is submissions, annotations are observed accuracy. */
public final class LearningTrendView extends View {
    private final String[] dates;
    private final int[] attempts,correct;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    public LearningTrendView(Context context,String[] dates,int[] attempts,int[] correct) {
        super(context);this.dates=dates.clone();this.attempts=attempts.clone();this.correct=correct.clone();
        StringBuilder description=new StringBuilder("近七天学习情况。");
        for(int i=0;i<dates.length;i++)description.append(dates[i]).append("，作答 ").append(attempts[i])
            .append(" 次，").append(attempts[i]==0?"无正确率":("正确率 "+Math.round(100.0*correct[i]/attempts[i])+"%" )).append("。");
        setContentDescription(description.toString());setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);float density=getResources().getDisplayMetrics().density;
        float font=TypeScale.pixels(getContext(),TypeScale.Role.CAPTION);
        float top=font*2.5f,bottom=getHeight()-font*4;
        float step=getWidth()/(float)dates.length;
        int max=1;for(int count:attempts)max=Math.max(max,count);
        paint.setColor(UiTokens.LINE);paint.setStrokeWidth(density);canvas.drawLine(0,bottom,getWidth(),bottom,paint);
        paint.setTextAlign(Paint.Align.CENTER);paint.setTextSize(font);
        for(int i=0;i<dates.length;i++) {
            float center=step*(i+.5f),height=(bottom-top)*attempts[i]/max;
            paint.setColor(attempts[i]==max?UiTokens.PRIMARY:0xffbad9cb);
            if(attempts[i]>0)canvas.drawRoundRect(center-step*.22f,bottom-height,center+step*.22f,bottom,3*density,3*density,paint);
            paint.setColor(UiTokens.INK);canvas.drawText(String.valueOf(attempts[i]),center,bottom-height-font*.5f,paint);
            String day=dates[i].substring(dates[i].lastIndexOf('/')+1);
            paint.setColor(UiTokens.MUTED);canvas.drawText(day,center,bottom+font*1.5f,paint);
            canvas.drawText(attempts[i]==0?"—":Math.round(100.0*correct[i]/attempts[i])+"%",center,bottom+font*3,paint);
        }
    }
}
