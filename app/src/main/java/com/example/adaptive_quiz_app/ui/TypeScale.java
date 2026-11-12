package com.example.adaptive_quiz_app.ui;

import android.content.Context;
import android.content.res.Resources;
import android.graphics.Typeface;
import android.text.Layout;
import android.util.TypedValue;
import android.widget.TextView;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ListView;
import androidx.appcompat.app.AlertDialog;
import androidx.core.widget.TextViewCompat;
import com.example.adaptive_quiz_app.R;

/** One sp scale for Compose, native screens, charts and dialogs. Never overrides fontScale. */
public final class TypeScale {
    private TypeScale() {}
    public enum Role {
        DISPLAY_LARGE(R.dimen.type_display_large,R.dimen.line_display_large,true),
        DISPLAY_MEDIUM(R.dimen.type_display_medium,R.dimen.line_display_medium,true),
        DISPLAY_SMALL(R.dimen.type_display_small,R.dimen.line_display_small,true),
        HEADLINE_LARGE(R.dimen.type_headline_large,R.dimen.line_headline_large,true),
        HERO(R.dimen.type_hero,R.dimen.line_hero,true),
        PAGE(R.dimen.type_page,R.dimen.line_page,true),
        SECTION(R.dimen.type_section,R.dimen.line_section,true),
        ITEM(R.dimen.type_item,R.dimen.line_item,true),
        READING(R.dimen.type_item,R.dimen.line_item,false),
        BODY(R.dimen.type_body,R.dimen.line_body,false),
        SECONDARY(R.dimen.type_secondary,R.dimen.line_secondary,false),
        CAPTION(R.dimen.type_caption,R.dimen.line_caption,false),
        BUTTON(R.dimen.type_body,R.dimen.line_body,true),
        METRIC(R.dimen.type_metric,R.dimen.line_metric,true),
        WORD(R.dimen.type_word,R.dimen.line_word,true);
        public final int sizeResource,lineResource;
        public final boolean medium;
        Role(int size,int line,boolean medium){sizeResource=size;lineResource=line;this.medium=medium;}
    }
    /** Read the authored sp number for Compose; dimensionResource().value.sp would scale twice. */
    public static float authoredSp(Resources resources,int id) {
        TypedValue value=new TypedValue();resources.getValue(id,value,true);
        if(value.type!=TypedValue.TYPE_DIMENSION||(value.data&TypedValue.COMPLEX_UNIT_MASK)!=TypedValue.COMPLEX_UNIT_SP)
            throw new IllegalArgumentException("Typography resources must use sp");
        return TypedValue.complexToFloat(value.data);
    }
    public static float pixels(Context context,Role role){return context.getResources().getDimension(role.sizeResource);}
    public static void apply(TextView view,Role role) {
        view.setTextSize(TypedValue.COMPLEX_UNIT_PX,pixels(view.getContext(),role));
        view.setIncludeFontPadding(false);
        view.setTypeface(Typeface.create(role.medium?"sans-serif-medium":"sans-serif",Typeface.NORMAL));
        TextViewCompat.setLineHeight(view,view.getResources().getDimensionPixelSize(role.lineResource));
        if(role==Role.HERO||role==Role.PAGE||role==Role.SECTION)
            view.setBreakStrategy(Layout.BREAK_STRATEGY_BALANCED);
    }
    /** Apply after show(), including AppCompat dialogs which have their own title appearance. */
    public static AlertDialog dialog(AlertDialog dialog) {
        dialog.show();
        TextView title=dialog.findViewById(androidx.appcompat.R.id.alertTitle);
        if(title!=null)apply(title,Role.PAGE);
        TextView message=dialog.findViewById(android.R.id.message);
        if(message!=null)apply(message,Role.READING);
        for(int which:new int[]{AlertDialog.BUTTON_POSITIVE,AlertDialog.BUTTON_NEGATIVE,AlertDialog.BUTTON_NEUTRAL})
            if(dialog.getButton(which)!=null)apply(dialog.getButton(which),Role.BUTTON);
        ListView list=dialog.getListView();
        if(list!=null) {
            for(int i=0;i<list.getChildCount();i++)styleListItem(list.getChildAt(i));
            list.setOnHierarchyChangeListener(new ViewGroup.OnHierarchyChangeListener() {
                public void onChildViewAdded(View parent,View child){styleListItem(child);}
                public void onChildViewRemoved(View parent,View child){}
            });
        }
        return dialog;
    }
    private static void styleListItem(View view) {
        if(view instanceof TextView)apply((TextView)view,Role.READING);
        else if(view instanceof ViewGroup) {
            ViewGroup group=(ViewGroup)view;
            for(int i=0;i<group.getChildCount();i++)styleListItem(group.getChildAt(i));
        }
    }
}
