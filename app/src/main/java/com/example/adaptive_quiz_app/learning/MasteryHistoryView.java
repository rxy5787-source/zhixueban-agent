package com.example.adaptive_quiz_app.learning;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.view.View;
import com.example.adaptive_quiz_app.ui.TypeScale;

/** Observed model updates only. NaN, infinity and out-of-range values leave gaps. */
public final class MasteryHistoryView extends View {
    private final String[] labels;
    private final double[] mastery;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);

    public MasteryHistoryView(Context context,String[] labels,double[] mastery) {
        super(context);
        if(labels==null||mastery==null||labels.length!=mastery.length)
            throw new IllegalArgumentException("Dates and mastery values must have equal lengths");
        this.labels=labels.clone();this.mastery=mastery.clone();
        StringBuilder description=new StringBuilder("知识掌握概率变化，按记录顺序展示。");
        int observed=0;
        for(int i=0;i<mastery.length;i++) {
            description.append(label(i)).append("，");
            if(valid(mastery[i])) {description.append(Math.round(mastery[i]*100)).append("%");observed++;}
            else description.append("无状态记录");
            description.append("。");
        }
        if(observed==0)description.append("暂无掌握状态更新记录。");
        setContentDescription(description.toString());
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
    }

    @Override protected void onMeasure(int widthMeasureSpec,int heightMeasureSpec) {
        float density=getResources().getDisplayMetrics().density;
        float font=TypeScale.pixels(getContext(),TypeScale.Role.CAPTION);
        int desiredWidth=(int)(320*density+.5f);
        int desiredHeight=(int)(150*density+font*5+.5f);
        setMeasuredDimension(resolveSize(Math.max(desiredWidth,getSuggestedMinimumWidth()),widthMeasureSpec),
            resolveSize(Math.max(desiredHeight,getSuggestedMinimumHeight()),heightMeasureSpec));
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float density=getResources().getDisplayMetrics().density;
        float font=TypeScale.pixels(getContext(),TypeScale.Role.CAPTION);
        paint.setTextSize(font);paint.setStyle(Paint.Style.FILL);
        float left=getPaddingLeft()+paint.measureText("100%")+8*density;
        float right=getWidth()-getPaddingRight()-8*density;
        float top=getPaddingTop()+font*1.5f;
        float bottom=getHeight()-getPaddingBottom()-font*4;
        if(right<=left||bottom<=top)return;

        paint.setStrokeWidth(density);
        double[] ticks={0,.5,1};
        for(double tick:ticks) {
            float y=bottom-(float)tick*(bottom-top);
            paint.setColor(UiTokens.LINE);canvas.drawLine(left,y,right,y,paint);
            paint.setColor(UiTokens.MUTED);paint.setTextAlign(Paint.Align.RIGHT);
            canvas.drawText(Math.round(tick*100)+"%",left-8*density,y+font*.35f,paint);
        }

        int observed=0;
        float previousX=0,previousY=0;
        boolean hasPrevious=false;
        for(int i=0;i<mastery.length;i++) {
            if(!valid(mastery[i])) {hasPrevious=false;continue;}
            float x=x(i,left,right),y=bottom-(float)mastery[i]*(bottom-top);
            paint.setColor(UiTokens.PRIMARY);paint.setStrokeWidth(2*density);
            if(hasPrevious)canvas.drawLine(previousX,previousY,x,y,paint);
            canvas.drawCircle(x,y,3*density,paint);
            previousX=x;previousY=y;hasPrevious=true;observed++;
        }
        if(observed==0) {
            paint.setColor(UiTokens.MUTED);paint.setTextAlign(Paint.Align.CENTER);
            canvas.drawText(fit("暂无掌握状态更新记录",right-left),(left+right)/2,(top+bottom)/2,paint);
        }

        paint.setColor(UiTokens.MUTED);paint.setStrokeWidth(density);
        if(labels.length>0) {
            int last=labels.length-1;
            float firstEnd=drawDate(canvas,0,left,right,bottom+font*1.7f);
            if(last>0) {
                String lastText=fit(label(last),Math.max(font*2,(right-left)/2-4*density));
                float lastStart=right-paint.measureText(lastText);
                if(lastStart>=firstEnd+4*density) {
                    paint.setTextAlign(Paint.Align.RIGHT);canvas.drawText(lastText,right,bottom+font*1.7f,paint);
                    int middle=last/2;
                    if(middle>0&&middle<last) {
                        String text=fit(label(middle),(right-left)/3);
                        float center=x(middle,left,right),half=paint.measureText(text)/2;
                        if(center-half>firstEnd+8*density&&center+half<lastStart-8*density) {
                            paint.setTextAlign(Paint.Align.CENTER);canvas.drawText(text,center,bottom+font*1.7f,paint);
                        }
                    }
                }
            }
        }
        paint.setTextAlign(Paint.Align.CENTER);
        canvas.drawText("日期 · 按状态更新顺序",(left+right)/2,bottom+font*3.3f,paint);
    }

    private float drawDate(Canvas canvas,int index,float left,float right,float y) {
        String text=fit(label(index),labels.length==1?right-left:Math.max(1,(right-left)/2-4*getResources().getDisplayMetrics().density));
        if(labels.length==1) {
            paint.setTextAlign(Paint.Align.CENTER);canvas.drawText(text,(left+right)/2,y,paint);
            return (left+right+paint.measureText(text))/2;
        }
        paint.setTextAlign(Paint.Align.LEFT);canvas.drawText(text,left,y,paint);
        return left+paint.measureText(text);
    }

    private String fit(String text,float width) {
        if(paint.measureText(text)<=width)return text;
        String ellipsis="…";
        if(paint.measureText(ellipsis)>width)return "";
        int count=paint.breakText(text,true,width-paint.measureText(ellipsis),null);
        return text.substring(0,count)+ellipsis;
    }

    private String label(int index) {return labels[index]==null?"":labels[index];}
    private float x(int index,float left,float right) {
        return labels.length==1?(left+right)/2:left+(right-left)*index/(labels.length-1);
    }
    private static boolean valid(double value) {return !Double.isNaN(value)&&!Double.isInfinite(value)&&value>=0&&value<=1;}
}
