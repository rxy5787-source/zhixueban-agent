package com.example.adaptive_quiz_app.learning;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.view.View;

/** Original book-and-sprout companion. Decorative, local and resolution independent. */
public final class StudyIllustration extends View {
    private final Paint pen=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final String scene;
    public StudyIllustration(Context context,String scene) {
        super(context);this.scene=scene;
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
    }
    private void stroke(Canvas canvas,float... points) {
        Path path=new Path();path.moveTo(points[0],points[1]);
        for(int i=2;i<points.length;i+=2)path.lineTo(points[i],points[i+1]);
        canvas.drawPath(path,pen);
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);canvas.save();
        float scale=Math.min(getWidth()/260f,getHeight()/150f);
        canvas.translate((getWidth()-260*scale)/2,(getHeight()-150*scale)/2);canvas.scale(scale,scale);
        pen.setStyle(Paint.Style.FILL);pen.setColor(Color.rgb(232,238,221));
        canvas.drawOval(60,18,207,143,pen);
        pen.setColor(Color.rgb(243,217,135));canvas.drawCircle(211,33,9,pen);
        pen.setStyle(Paint.Style.STROKE);pen.setStrokeWidth(3.1f);
        pen.setStrokeCap(Paint.Cap.ROUND);pen.setStrokeJoin(Paint.Join.ROUND);
        pen.setColor(Color.rgb(43,48,42));
        Path book=new Path();book.moveTo(65,60);
        book.cubicTo(84,50,111,50,130,64);
        book.cubicTo(150,50,176,50,195,60);
        book.lineTo(191,117);book.cubicTo(169,110,147,111,130,123);
        book.cubicTo(109,111,87,111,68,117);book.close();
        pen.setStyle(Paint.Style.FILL);pen.setColor(Color.rgb(255,254,249));canvas.drawPath(book,pen);
        pen.setStyle(Paint.Style.STROKE);pen.setColor(Color.rgb(43,48,42));canvas.drawPath(book,pen);
        stroke(canvas,130,64,130,123);
        canvas.drawArc(83,75,99,86,195,145,false,pen);canvas.drawArc(158,75,174,86,195,145,false,pen);
        canvas.drawArc(109,84,151,102,20,140,false,pen);
        stroke(canvas,66,86,52,79,43,84);stroke(canvas,193,87,204,78,213,83);
        stroke(canvas,97,117,93,132,84,134);stroke(canvas,161,117,166,132,176,133);
        pen.setColor(Color.rgb(64,108,74));
        Path stem=new Path();stem.moveTo(130,60);stem.cubicTo(129,45,139,38,135,22);canvas.drawPath(stem,pen);
        Path leaf=new Path();leaf.moveTo(135,39);leaf.cubicTo(115,41,112,24,116,18);leaf.cubicTo(133,19,140,25,135,39);
        pen.setStyle(Paint.Style.FILL);canvas.drawPath(leaf,pen);
        leaf.reset();leaf.moveTo(136,31);leaf.cubicTo(143,16,157,17,162,20);leaf.cubicTo(159,34,149,38,136,31);canvas.drawPath(leaf,pen);
        pen.setStyle(Paint.Style.STROKE);pen.setStrokeWidth(2);
        if("grow".equals(scene)) {
            stroke(canvas,22,111,30,111,30,98,41,98,41,83);
            stroke(canvas,220,119,220,102,230,102,230,85,242,85,242,67);
        } else if("search".equals(scene)) {
            canvas.drawCircle(218,110,12,pen);stroke(canvas,227,119,238,130);
        } else {
            stroke(canvas,28,40,28,50);stroke(canvas,23,45,33,45);
            stroke(canvas,224,58,224,68);stroke(canvas,219,63,229,63);
        }
        canvas.restore();
    }
}
