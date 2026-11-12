package com.example.adaptive_quiz_app.ai;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.InputFilter;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.*;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import com.example.adaptive_quiz_app.R;
import com.example.adaptive_quiz_app.auth.*;
import com.example.adaptive_quiz_app.learning.*;
import com.example.adaptive_quiz_app.ui.TypeScale;
import org.json.*;
import java.util.*;
import java.util.concurrent.*;

/** Upload first, describe the desired questions, then run a durable server task. */
public final class AiGenerationController implements AutoCloseable {
    public static final int PICK_FILES=75;
    private final Activity activity;
    private final LearningStore db;
    private final AuthSession session;
    private final Runnable back;
    private final long initialLibrary;
    private final AiApi api;
    private final AiJobStore jobs;
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final ExecutorService pollWorker=Executors.newSingleThreadExecutor();
    private final ExecutorService cancelWorker=Executors.newSingleThreadExecutor();
    private final Handler ui=new Handler(Looper.getMainLooper());
    private final Runnable pollTask=this::poll;
    private final List<String> names=new ArrayList<>();
    private JSONArray uploadedIds=new JSONArray(),uploadWarnings=new JSONArray(),libraries,points=new JSONArray();
    private long targetLibrary;
    private EditText requirements,libraryName;
    private Spinner countPicker,difficultyPicker,pointPicker;
    private TextView selected,status,plan;
    private LinearLayout results,taskActions;
    private LinearLayout destinationOptions;
    private CheckBox adaptive;
    private TextView adaptiveSummary;
    private JSONObject adaptivePlan;
    private ScrollView scroll;
    private Button generate,upload,importButton,cancel,retry,target;
    private JSONObject result;
    private String job="";
    private String terminalJob="";
    private String uploadNote="";
    private volatile boolean closed;
    private boolean loading,jobRunning,imported,uploading;
    private boolean polling,cancelling,cancelRequested;
    private int jobVersion;
    private java.util.function.LongConsumer openLibrary;
    public void setOpenLibrary(java.util.function.LongConsumer action){openLibrary=action;}
    public void enableAdaptiveGeneration(){if(adaptive!=null&&adaptive.isEnabled())adaptive.setChecked(true);}

    public AiGenerationController(Activity activity,LearningStore db,AuthSession session,JSONObject library,Runnable back) {
        this(activity,db,session,library,back,new AiApi());
    }
    public AiGenerationController(Activity activity,LearningStore db,AuthSession session,JSONObject library,Runnable back,AiApi api) {
        this.api=api;
        this.activity=activity;this.db=db;this.session=session;this.back=back;
        initialLibrary=library==null?0:library.optLong("id");targetLibrary=initialLibrary;
        jobs=new AiJobStore(activity,session.userId,api.base);job=jobs.load();
    }
    private int dp(int n){return (int)(n*activity.getResources().getDisplayMetrics().density+.5f);}
    private LinearLayout column(){LinearLayout v=new LinearLayout(activity);v.setOrientation(LinearLayout.VERTICAL);return v;}
    private GradientDrawable shape(int color,int radius,boolean dashed) {
        GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(radius));
        if(dashed)d.setStroke(dp(1),UiTokens.PRIMARY,dp(6),dp(4));
        return d;
    }
    private TextView text(LinearLayout root,String value,TypeScale.Role role) {
        TextView v=new TextView(activity);v.setText(value);v.setTextColor(UiTokens.INK);TypeScale.apply(v,role);
        v.setPadding(0,dp(5),0,dp(7));root.addView(v);return v;
    }
    private Button button(LinearLayout root,String label,Runnable action,boolean primary) {
        Button v=new Button(activity);v.setText(label);v.setAllCaps(false);TypeScale.apply(v,TypeScale.Role.BUTTON);
        v.setMinHeight(dp(48));v.setPadding(dp(12),dp(10),dp(12),dp(10));v.setElevation(0);v.setStateListAnimator(null);
        v.setBackground(shape(primary?UiTokens.PRIMARY:UiTokens.SOFT,14,false));v.setBackgroundTintList(null);
        v.setTextColor(primary?Color.WHITE:UiTokens.PRIMARY);
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(5);lp.bottomMargin=dp(5);root.addView(v,lp);
        v.setOnClickListener(view->action.run());return v;
    }
    private EditText input(LinearLayout root,String hint,int minLines) {
        EditText v=new EditText(activity);v.setHint(hint);v.setTextColor(UiTokens.INK);v.setHintTextColor(UiTokens.MUTED);
        TypeScale.apply(v,TypeScale.Role.BODY);v.setMinLines(minLines);v.setGravity(Gravity.TOP|Gravity.START);
        v.setPadding(dp(12),dp(12),dp(12),dp(12));v.setBackground(shape(Color.WHITE,12,false));
        root.addView(v,new LinearLayout.LayoutParams(-1,-2));return v;
    }
    private ArrayAdapter<String> choices(String[] labels) {
        return new ArrayAdapter<String>(activity,android.R.layout.simple_spinner_dropdown_item,labels) {
            @Override public View getView(int p,View reuse,ViewGroup parent){View v=super.getView(p,reuse,parent);style(v);return v;}
            @Override public View getDropDownView(int p,View reuse,ViewGroup parent){View v=super.getDropDownView(p,reuse,parent);style(v);return v;}
            private void style(View v){if(v instanceof TextView){TypeScale.apply((TextView)v,TypeScale.Role.BODY);((TextView)v).setTextColor(UiTokens.INK);((TextView)v).setSingleLine(true);((TextView)v).setEllipsize(android.text.TextUtils.TruncateAt.END);}}
        };
    }
    public void show(){show(null);}
    public void show(Bundle saved) {
        LinearLayout root=column();root.setBackgroundColor(UiTokens.BACKGROUND);activity.setContentView(root);
        ViewCompat.setOnApplyWindowInsetsListener(root,(v,in)->{
            androidx.core.graphics.Insets x=in.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.ime());
            v.setPadding(x.left,x.top,x.right,x.bottom);return in;
        });ViewCompat.requestApplyInsets(root);
        LinearLayout toolbar=new LinearLayout(activity);toolbar.setGravity(Gravity.CENTER_VERTICAL);toolbar.setPadding(dp(12),dp(4),dp(16),dp(4));root.addView(toolbar);
        TextView close=new TextView(activity);close.setText("‹");close.setTextColor(UiTokens.PRIMARY);TypeScale.apply(close,TypeScale.Role.WORD);close.setGravity(Gravity.CENTER);
        close.setContentDescription("返回");close.setOnClickListener(v->back.run());toolbar.addView(close,new LinearLayout.LayoutParams(dp(44),dp(44)));
        TextView title=new TextView(activity);title.setText("资料出题");TypeScale.apply(title,TypeScale.Role.PAGE);title.setTextColor(UiTokens.INK);toolbar.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        TextView history=new TextView(activity);history.setText("任务记录");TypeScale.apply(history,TypeScale.Role.BODY);history.setTextColor(UiTokens.PRIMARY);history.setGravity(Gravity.CENTER);history.setMinHeight(dp(44));history.setOnClickListener(v->history());toolbar.addView(history);
        scroll=new ScrollView(activity);scroll.setFillViewport(true);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout body=column();body.setPadding(dp(20),dp(8),dp(20),dp(20));scroll.addView(body);

        LinearLayout zone=column();zone.setPadding(dp(14),dp(10),dp(14),dp(10));zone.setGravity(Gravity.CENTER);zone.setBackground(shape(Color.WHITE,16,true));body.addView(zone,new LinearLayout.LayoutParams(-1,-2));
        text(zone,"上传你的学习资料",TypeScale.Role.SECTION).setGravity(Gravity.CENTER);
        upload=button(zone,"点击上传资料",this::choose,true);upload.setId(R.id.ai_upload);
        TextView supported=text(zone,"PDF / Word / TXT / 图片 · 最多 5 份，每份 20 MB",TypeScale.Role.CAPTION);supported.setGravity(Gravity.CENTER);supported.setTextColor(UiTokens.MUTED);
        selected=text(body,"尚未上传资料",TypeScale.Role.SECONDARY);selected.setId(R.id.ai_upload_status);
        text(body,"生成后先预览，确认导入才会保存到手机知识库。题型为四选一单选题，练习提交后显示答案和解析。",TypeScale.Role.CAPTION).setTextColor(UiTokens.MUTED);
        text(body,"你的出题要求",TypeScale.Role.SECTION);
        requirements=input(body,"例如：出 5 道中等难度单选题，重点考查本章核心概念。",3);requirements.setId(R.id.ai_requirements);requirements.setFilters(new InputFilter[]{new InputFilter.LengthFilter(1200)});
        text(body,"可写考查重点和提问方式；识别到题数、难度后会同步到下面。",TypeScale.Role.CAPTION).setTextColor(UiTokens.MUTED);
        LinearLayout options=new LinearLayout(activity);body.addView(options);
        LinearLayout counts=column(),difficulties=column();options.addView(counts,new LinearLayout.LayoutParams(0,-2,1));options.addView(difficulties,new LinearLayout.LayoutParams(0,-2,1));
        text(counts,"题数",TypeScale.Role.SECONDARY);countPicker=new Spinner(activity);String[] labels=new String[12];for(int i=0;i<12;i++)labels[i]=(i+1)+" 道";countPicker.setAdapter(choices(labels));counts.addView(countPicker,new LinearLayout.LayoutParams(-1,-2));countPicker.setSelection(2);
        text(difficulties,"难度",TypeScale.Role.SECONDARY);difficultyPicker=new Spinner(activity);difficultyPicker.setAdapter(choices(new String[]{"自动","简单","中等","困难"}));difficulties.addView(difficultyPicker,new LinearLayout.LayoutParams(-1,-2));
        plan=text(body,"",TypeScale.Role.SECONDARY);
        target=button(body,"",this::chooseTarget,false);target.setId(R.id.ai_target);
        adaptive=new CheckBox(activity);adaptive.setText("按掌握情况生成：优先薄弱和待评估知识点");TypeScale.apply(adaptive,TypeScale.Role.BODY);adaptive.setId(R.id.ai_adaptive);body.addView(adaptive);
        adaptiveSummary=text(body,"",TypeScale.Role.CAPTION);adaptiveSummary.setId(R.id.ai_adaptive_summary);adaptiveSummary.setTextColor(UiTokens.MUTED);
        adaptive.setOnCheckedChangeListener((button,checked)->updateAdaptivePlan());
        LinearLayout destination=column();destinationOptions=destination;destination.setVisibility(View.GONE);body.addView(destination);
        button(body,"题库名称与知识点设置  ▾",()->destination.setVisibility(destination.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE),false);
        text(destination,"自定义题库名称",TypeScale.Role.SECONDARY);libraryName=input(destination,"填写你的题库名；留空则按资料文件名命名",1);libraryName.setId(R.id.ai_library_name);libraryName.setSingleLine(true);libraryName.setFilters(new InputFilter[]{new InputFilter.LengthFilter(100)});
        text(destination,"知识点",TypeScale.Role.SECONDARY);pointPicker=new Spinner(activity);destination.addView(pointPicker);
        libraries=db.rows("SELECT * FROM library WHERE kind='question' AND archived=0 ORDER BY id");
        boolean restoring=saved!=null&&session.userId.equals(saved.getString("owner"));
        if(restoring) {
            targetLibrary=saved.getLong("target",initialLibrary);requirements.setText(saved.getString("requirements",""));libraryName.setText(saved.getString("libraryName",""));
            countPicker.setSelection(saved.getInt("count",2));difficultyPicker.setSelection(saved.getInt("difficulty",0));job=saved.getString("job",job);
            try{uploadedIds=new JSONArray(saved.getString("uploaded","[]"));uploadWarnings=new JSONArray(saved.getString("warnings","[]"));JSONArray ns=new JSONArray(saved.getString("names","[]"));for(int i=0;i<ns.length();i++)names.add(ns.getString(i));}catch(JSONException ignored){uploadedIds=new JSONArray();names.clear();}
        }
        updateTarget();if(restoring){pointPicker.setSelection(Math.min(saved.getInt("point",0),pointPicker.getCount()-1));adaptive.setChecked(adaptive.isEnabled()&&saved.getBoolean("adaptive",false));}
        button(body,"支持格式与处理范围  ▾",()->TypeScale.dialog(new androidx.appcompat.app.AlertDialog.Builder(activity).setTitle("资料出题范围").setMessage("可上传 PDF、DOCX、TXT、JPG、PNG、BMP、WebP。扫描页和图片先识别文字，再依据完整文字出题；识别结果可能有错，可在生成结果中查看并对照原页。未填的公式、缺失答案及需要查看图形才能作答的题不自动入库。每份 PDF 最多前 5 页，每份资料最多 3 段文字；当前只生成四选一单选题。通过初筛仍可能有错，请核对结果和原文证据。").setPositiveButton("知道了",null).create()),false);
        status=text(body,"上传资料并填写要求后，点击下方开始生成。",TypeScale.Role.BODY);status.setId(R.id.ai_status);
        results=column();results.setId(R.id.ai_results);body.addView(results);
        taskActions=column();body.addView(taskActions);cancel=button(taskActions,"取消当前任务",this::cancelJob,false);cancel.setId(R.id.ai_cancel);retry=button(taskActions,"重试这次任务",()->action("retry"),false);
        importButton=button(taskActions,"确认导入通过初筛的题目",this::importResult,true);importButton.setId(R.id.ai_import);taskActions.setVisibility(View.GONE);
        LinearLayout footer=column();footer.setPadding(dp(20),dp(6),dp(20),dp(8));footer.setBackgroundColor(Color.WHITE);root.addView(footer);
        generate=button(footer,"根据要求生成题目",this::start,true);generate.setId(R.id.ai_generate);
        requirements.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){Integer n=AiRequirements.countIn(s.toString());if(n!=null&&n>=1&&n<=12)countPicker.setSelection(n-1);int d=AiRequirements.difficultyIn(s.toString());if(d>0)difficultyPicker.setSelection(d);updatePlan();}public void afterTextChanged(Editable e){}});
        AdapterView.OnItemSelectedListener changes=new AdapterView.OnItemSelectedListener(){public void onItemSelected(AdapterView<?> p,View v,int n,long id){updatePlan();}public void onNothingSelected(AdapterView<?> p){}};
        countPicker.setOnItemSelectedListener(changes);difficultyPicker.setOnItemSelectedListener(changes);
        updateSelection();updatePlan();controls();poll();
    }
    private void updateTarget() {
        JSONObject chosen=null;for(int i=0;i<libraries.length();i++)if(libraries.optJSONObject(i).optLong("id")==targetLibrary)chosen=libraries.optJSONObject(i);
        if(chosen==null)targetLibrary=0;
        target.setText(chosen==null?"题目放入：新建自定义题库  ›":"题目放入："+chosen.optString("name")+"  ›");
        points=chosen==null?new JSONArray():db.rows("SELECT name,summary FROM point WHERE library_id=? AND archived=0 ORDER BY id LIMIT 12",""+targetLibrary);
        String[] entries=new String[points.length()+1];entries[0]="从资料自动识别（推荐）";for(int i=0;i<points.length();i++)entries[i+1]=points.optJSONObject(i).optString("name");pointPicker.setAdapter(choices(entries));
        libraryName.setEnabled(targetLibrary==0);
        destinationOptions.setVisibility(targetLibrary==0?View.VISIBLE:View.GONE);
        updateAdaptivePlan();
    }
    private void chooseTarget() {
        String[] labels=new String[libraries.length()+1];labels[0]="＋ 新建自定义题库";for(int i=0;i<libraries.length();i++)labels[i+1]=libraries.optJSONObject(i).optString("name");
        TypeScale.dialog(new androidx.appcompat.app.AlertDialog.Builder(activity).setTitle("生成后保存到").setItems(labels,(d,n)->{targetLibrary=n==0?0:libraries.optJSONObject(n-1).optLong("id");updateTarget();}).setNegativeButton("取消",null).create());
    }
    private void updateAdaptivePlan(){
        if(adaptive==null||pointPicker==null)return;
        try{adaptivePlan=db.generationPlan(targetLibrary);}catch(JSONException error){adaptivePlan=null;}
        JSONArray targets=adaptivePlan==null?null:adaptivePlan.optJSONArray("points");boolean available=targets!=null&&targets.length()>0;
        adaptive.setEnabled(available);if(!available)adaptive.setChecked(false);
        pointPicker.setEnabled(!adaptive.isChecked());
        adaptiveSummary.setText(!available?"选择已有知识点的题库后，可按最新掌握情况生成；新题库先从资料识别知识点。":adaptive.isChecked()?adaptivePlan.optString("requirements")+"\n难度选“自动”时按当前掌握估计安排；仍需上传包含这些知识点的资料。":"启用后读取所选题库的最新作答记录；不把未测试的知识点当作已测薄弱点。");
        updatePlan();
    }
    private void updatePlan(){if(plan!=null)plan.setText("单项选择题 · "+(countPicker.getSelectedItemPosition()+1)+" 道 · "+(difficultyPicker.getSelectedItemPosition()==0&&adaptive!=null&&adaptive.isChecked()&&adaptivePlan!=null?new String[]{"","简单","中等","困难"}[adaptivePlan.optInt("difficulty",1)]+"（依据掌握估计）":difficultyPicker.getSelectedItem()));}
    private void updateSelection(){selected.setText(uploading?"资料上传中…":uploadedIds.length()==0?(uploadNote.isEmpty()?"尚未上传资料":uploadNote):"已上传 "+uploadedIds.length()+" 份资料\n"+android.text.TextUtils.join("\n",names)+(uploadNote.isEmpty()?"":"\n"+uploadNote));if(upload!=null)upload.setText(uploadedIds.length()==0?"点击上传资料":"重新选择并上传资料");}
    private void controls(){if(generate==null)return;generate.setEnabled(!loading&&!jobRunning&&uploadedIds.length()>0);generate.setAlpha(generate.isEnabled()?1f:.5f);upload.setEnabled(!loading&&!jobRunning);cancel.setVisibility(jobRunning?View.VISIBLE:View.GONE);cancel.setEnabled(!cancelling&&!cancelRequested);cancel.setText(cancelling||cancelRequested?"正在取消…":"取消当前任务");retry.setVisibility(!job.isEmpty()&&!jobRunning?View.VISIBLE:View.GONE);importButton.setVisibility(result!=null&&result.optInt("accepted")>0?View.VISIBLE:View.GONE);importButton.setEnabled(!loading&&!imported);}
    private boolean current(){AuthSession now=new SessionStore(activity).load();return !closed&&!activity.isDestroyed()&&!activity.isFinishing()&&now!=null&&now.userId.equals(session.userId)&&now.token.equals(session.token);}
    private interface Work{void run()throws Exception;}
    private void execute(Work action){if(loading||!current())return;boolean fileWork=uploading;loading=true;controls();worker.execute(()->{try{action.run();}catch(Exception error){ui.post(()->{if(current()){status.setText("处理失败："+error.getMessage());if(fileWork){uploadNote="上传失败："+error.getMessage();updateSelection();}else scroll.post(()->scroll.smoothScrollTo(0,status.getTop()));controls();}});}finally{ui.post(()->{loading=false;if(current())controls();});}});}
    private void choose(){Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_ALLOW_MULTIPLE,true);activity.startActivityForResult(intent,PICK_FILES);}
    public void selected(Intent data) {
        if(loading||jobRunning)return;
        List<Uri> uris=new ArrayList<>();List<String> filenames=new ArrayList<>();
        if(data.getClipData()!=null)for(int i=0;i<data.getClipData().getItemCount();i++)uris.add(data.getClipData().getItemAt(i).getUri());else if(data.getData()!=null)uris.add(data.getData());
        if(uris.isEmpty()||uris.size()>5){status.setText("请选择 1–5 份资料");return;}
        for(Uri uri:uris){String name=uri.getLastPathSegment();try(android.database.Cursor c=activity.getContentResolver().query(uri,new String[]{android.provider.OpenableColumns.DISPLAY_NAME},null,null,null)){if(c!=null&&c.moveToFirst())name=c.getString(0);}catch(Exception ignored){}filenames.add(name==null?"资料.txt":name);}
        uploading=true;uploadNote="";job="";jobVersion++;cancelling=false;cancelRequested=false;result=null;uploadedIds=new JSONArray();names.clear();results.removeAllViews();taskActions.setVisibility(View.GONE);ui.removeCallbacks(pollTask);updateSelection();status.setText("正在上传资料，请稍候…");
        execute(()->{try{JSONObject response=api.upload(activity,uris,filenames,session);JSONArray files=response.getJSONArray("files"),ids=new JSONArray(),warnings=new JSONArray();List<String> accepted=new ArrayList<>();StringBuilder errors=new StringBuilder();for(int i=0;i<files.length();i++){JSONObject file=files.getJSONObject(i);if("ready".equals(file.optString("status"))){ids.put(file.getString("fileId"));accepted.add(file.getString("name"));}else{String error=file.optString("name")+"："+file.optString("error");warnings.put(error);errors.append(error).append('\n');}}ui.post(()->{if(!current())return;uploadedIds=ids;uploadWarnings=warnings;uploadNote=errors.toString().trim();names.clear();names.addAll(accepted);status.setText(ids.length()>0?"资料已上传。填写出题要求后即可开始。\n"+errors:"上传失败："+errors);updateSelection();controls();});}finally{ui.post(()->{uploading=false;if(current())updateSelection();});}});
    }
    private void start() {
        if(uploadedIds.length()==0){status.setText("请先点击上方上传资料");return;}
        String request=requirements.getText().toString().trim();Integer described=AiRequirements.countIn(request);
        if(described!=null&&(described<1||described>12)){requirements.setError("每次支持生成 1–12 道题");requirements.requestFocus();return;}
        if(AiRequirements.unsupportedType(request)){requirements.setError("当前支持四选一单选题");requirements.requestFocus();return;}
        JSONArray selectedPoints=new JSONArray();int p=pointPicker.getSelectedItemPosition();if(p>0)selectedPoints.put(points.optJSONObject(p-1));
        int effectiveDifficulty=difficultyPicker.getSelectedItemPosition();
        if(adaptive.isChecked())try{
            adaptivePlan=db.generationPlan(targetLibrary);selectedPoints=adaptivePlan.getJSONArray("points");
            if(selectedPoints.length()==0){status.setText("当前题库暂无可用知识点，请先从资料识别知识点。");return;}
            request=request+"\n\n"+adaptivePlan.getString("requirements");
            if(request.length()>1200){requirements.setError("请缩短出题要求，为掌握情况说明预留空间");return;}
            if(effectiveDifficulty==0)effectiveDifficulty=adaptivePlan.getInt("difficulty");
        }catch(JSONException error){status.setText(error.getMessage());return;}
        JSONObject chosen=null;for(int i=0;i<libraries.length();i++)if(libraries.optJSONObject(i).optLong("id")==targetLibrary)chosen=libraries.optJSONObject(i);
        String name=libraryName.getText().toString().trim();if(chosen!=null)name=chosen.optString("name");else if(name.isEmpty()){name=names.get(0).replaceFirst("\\.[^.]+$","");if(name.length()>80)name=name.substring(0,80);name+=" · 资料题库";}
        JSONObject payload=new JSONObject();try{payload.put("fileIds",uploadedIds).put("uploadWarnings",uploadWarnings).put("libraryName",name).put("subject",chosen==null?"资料学习":chosen.optString("subject")).put("points",selectedPoints).put("questionCount",countPicker.getSelectedItemPosition()+1).put("requirements",request).put("difficulty",effectiveDifficulty);}catch(JSONException error){status.setText(error.getMessage());return;}
        result=null;imported=false;results.removeAllViews();status.setText("正在提交出题要求…");
        execute(()->{JSONObject value=api.request("POST","jobs",session,payload);String created=value.getString("jobId");ui.post(()->{if(!current())return;job=created;jobVersion++;jobs.save(job);cancelling=false;cancelRequested=false;jobRunning=true;taskActions.setVisibility(View.VISIBLE);status.setText("已开始生成，可离开此页，稍后从任务记录查看。");scroll.post(()->scroll.smoothScrollTo(0,status.getTop()));controls();ui.removeCallbacks(pollTask);ui.postDelayed(pollTask,500);});});
    }
    private void poll() {
        if(job.isEmpty()||!current())return;
        if(polling){ui.removeCallbacks(pollTask);ui.postDelayed(pollTask,1000);return;}
        String queried=job;int version=jobVersion;polling=true;
        pollWorker.execute(()->{
            try {
                JSONObject value=api.request("GET","jobs/"+queried,session,null);
                boolean running=isRunning(value);
                JSONObject bundle=running?null:api.request("GET","jobs/"+queried+"/result",session,null);
                ui.post(()->{if(current()&&job.equals(queried)&&version==jobVersion)applyJob(value,bundle);});
            } catch(Exception error) {
                ui.post(()->{if(current()&&job.equals(queried)&&version==jobVersion&&!cancelling&&!cancelRequested){status.setText("暂时无法更新进度，将自动重试；仍可取消任务。\n"+error.getMessage());ui.removeCallbacks(pollTask);ui.postDelayed(pollTask,3000);}});
            } finally {
                ui.post(()->{polling=false;if(current()&&!job.isEmpty()&&(jobRunning||!job.equals(queried))){ui.removeCallbacks(pollTask);ui.postDelayed(pollTask,1500);}});
            }
        });
    }
    private boolean isRunning(JSONObject value){String state=value.optString("state");return state.equals("queued")||state.equals("running");}
    private void applyJob(JSONObject value,JSONObject bundle){
        if(isRunning(value)&&terminalJob.equals(job))return;
        jobRunning=isRunning(value);cancelRequested=jobRunning&&(cancelRequested||value.optBoolean("cancelRequested"));result=bundle;taskActions.setVisibility(View.VISIBLE);
        if(!jobRunning){terminalJob=job;cancelling=false;}
        status.setText((cancelRequested?"正在取消":stateName(value.optString("state")))+" · "+value.optString("stage")+"\n可导入 "+value.optInt("accepted")+" 题"+(value.optString("error").isEmpty()?"":"\n"+value.optString("error")));
        if(bundle!=null)renderResult(bundle);controls();
    }
    /** Cancellation must bypass a slow status request and never wait for the normal work queue. */
    private void cancelJob(){
        if(job.isEmpty()||!jobRunning||cancelling||cancelRequested||!current())return;
        String queried=job;int version=++jobVersion;cancelling=true;ui.removeCallbacks(pollTask);status.setText("正在取消任务，已保存的结果会保留…");controls();
        cancelWorker.execute(()->{
            try {
                JSONObject value=api.request("POST","jobs/"+queried+"/cancel",session,new JSONObject());
                JSONObject bundle=isRunning(value)?null:api.request("GET","jobs/"+queried+"/result",session,null);
                ui.post(()->{if(!current()||!job.equals(queried)||version!=jobVersion)return;cancelling=false;applyJob(value,bundle);if(jobRunning)ui.postDelayed(pollTask,300);});
            } catch(Exception error){
                ui.post(()->{if(!current()||!job.equals(queried)||version!=jobVersion)return;cancelling=false;cancelRequested=false;status.setText("取消请求未确认，请重试。\n"+error.getMessage());controls();ui.postDelayed(pollTask,1500);});
            }
        });
    }
    private String stateName(String state){switch(state){case "queued":return "等待生成";case "running":return "正在处理";case "succeeded":return "生成完成";case "partial":return "部分完成";case "cancelled":return "已取消";case "interrupted":return "处理已中断";default:return "未生成可用题目";}}
    private void renderResult(JSONObject bundle) {
        results.removeAllViews();text(results,"生成结果",TypeScale.Role.SECTION);
        JSONObject requested=bundle.optJSONObject("generationRequest");if(requested!=null&&!requested.optString("requirements").isEmpty())text(results,"本次要求："+requested.optString("requirements"),TypeScale.Role.SECONDARY);
        text(results,bundle.optString("reviewNote"),TypeScale.Role.CAPTION).setTextColor(UiTokens.MUTED);
        JSONArray files=bundle.optJSONArray("files"),bad=bundle.optJSONArray("rejected");
        StringBuilder extracted=new StringBuilder();
        if(files!=null)for(int i=0;i<files.length();i++){
            JSONObject f=files.optJSONObject(i);if("error".equals(f.optString("status")))text(results,f.optString("name")+"："+f.optString("error"),TypeScale.Role.SECONDARY);
            JSONArray pages=f.optJSONArray("parsing");if(pages!=null)for(int p=0;p<pages.length();p++){
                JSONObject page=pages.optJSONObject(p);extracted.append(f.optString("name")).append(" · ").append(page.optString("location")).append('\n');
                if("ocr".equals(page.optString("extraction")))extracted.append("低置信度文字已排除 ").append(page.optInt("lowConfidenceLines")).append(" 处，未填完整内容已排除 ").append(page.optInt("incompleteLines")).append(" 处。\n");
                if(!page.isNull("parsingNote"))extracted.append(page.optString("parsingNote")).append('\n');
                if(!page.isNull("parsingError"))extracted.append(page.optString("parsingError")).append('\n');
                extracted.append(page.isNull("textPreview")?"旧任务未保存识别文字，可重试获取。":page.optString("textPreview")).append("\n\n");
            }
        }
        if(extracted.length()>0){String recognized=extracted.toString();button(results,"查看资料识别结果",()->TypeScale.dialog(new androidx.appcompat.app.AlertDialog.Builder(activity).setTitle("资料识别结果").setMessage(recognized).setPositiveButton("关闭",null).create()),false).setId(R.id.ai_extracted_text);}
        Map<String,Set<String>> reasons=new LinkedHashMap<>();
        if(bad!=null)for(int i=0;i<bad.length();i++){
            JSONObject row=bad.optJSONObject(i);if(row==null)continue;JSONArray notes=row.optJSONArray("reasons");if(notes==null)continue;
            for(int n=0;n<notes.length();n++)reasons.computeIfAbsent(notes.optString(n),key->new LinkedHashSet<>()).add(row.optString("sourceLocation",row.optString("sourceFile","")));
        }
        int shown=0;for(Map.Entry<String,Set<String>> entry:reasons.entrySet()){if(shown++>=6)break;text(results,"未通过："+entry.getKey()+(entry.getValue().isEmpty()?"":"\n"+android.text.TextUtils.join("、",entry.getValue())),TypeScale.Role.CAPTION);}
        JSONObject content=bundle.optJSONObject("content");JSONArray ls=content==null?null:content.optJSONArray("libraries");if(ls==null)return;
        if(bundle.optInt("accepted")==0)text(results,"本次没有题目入库。上方为处理失败或未通过初筛的原因；修复后可重试。",TypeScale.Role.SECONDARY);
        else text(results,imported?"已导入手机知识库，可进入题库开始练习。":"以下为待导入预览，尚未写入手机知识库。",TypeScale.Role.SECONDARY);
        for(int n=0;n<ls.length();n++){JSONObject l=ls.optJSONObject(n);text(results,(imported?"已导入题库：":"目标题库（确认导入后保存）：")+l.optString("name"),TypeScale.Role.SECONDARY);JSONArray items=l.optJSONArray("items");if(items==null)continue;
            for(int i=0;i<items.length();i++){JSONObject q=items.optJSONObject(i),source=q.optJSONObject("ai");text(results,(i+1)+". "+q.optString("prompt"),TypeScale.Role.ITEM);JSONArray options=q.optJSONArray("options");if(options!=null)for(int k=0;k<options.length();k++)text(results,(char)('A'+k)+". "+options.optString(k),TypeScale.Role.BODY);text(results,"答案："+q.optString("answer")+"\n原文解析："+q.optString("explanation"),TypeScale.Role.SECONDARY);if(source!=null)text(results,"来源："+source.optString("sourceFile")+" · "+source.optString("sourceLocation")+"\n证据："+source.optString("evidenceQuote"),TypeScale.Role.CAPTION);}}
    }
    private void action(String route){if(job.isEmpty())return;String queried=job;execute(()->{JSONObject value=api.request("POST","jobs/"+queried+"/"+route,session,new JSONObject());String created=value.getString("jobId");ui.post(()->{if(!current()||!job.equals(queried))return;job=created;jobVersion++;jobs.save(job);imported=false;cancelling=false;cancelRequested=false;jobRunning=true;result=null;results.removeAllViews();controls();ui.removeCallbacks(pollTask);ui.postDelayed(pollTask,100);});});}
    private void history(){execute(()->{JSONArray rows=api.request("GET","jobs",session,null).getJSONArray("jobs");String[] labels=new String[rows.length()];for(int i=0;i<labels.length;i++){JSONObject r=rows.getJSONObject(i);labels[i]=r.optString("libraryName")+" · "+stateName(r.optString("state"));}ui.post(()->{if(!current())return;if(rows.length()==0){status.setText("当前账号还没有生成任务");return;}TypeScale.dialog(new androidx.appcompat.app.AlertDialog.Builder(activity).setTitle("最近生成任务").setItems(labels,(d,n)->{job=rows.optJSONObject(n).optString("jobId");jobVersion++;jobs.save(job);imported=false;cancelling=false;cancelRequested=false;jobRunning=isRunning(rows.optJSONObject(n));result=null;results.removeAllViews();controls();ui.removeCallbacks(pollTask);ui.postDelayed(pollTask,100);scroll.post(()->scroll.smoothScrollTo(0,status.getTop()));}).setNegativeButton("关闭",null).create());});});}
    private void importResult(){JSONObject bundle=result;if(bundle==null)return;execute(()->{if(!current())return;String message=db.importAiResult(bundle,session.userId);JSONObject destination=bundle.getJSONObject("content").getJSONArray("libraries").getJSONObject(0);JSONObject library=db.one("SELECT id FROM library WHERE name=? AND subject=? AND kind='question' AND archived=0",destination.getString("name"),destination.getString("subject"));long importedLibrary=library==null?0:library.optLong("id");ui.post(()->{if(current()){imported=true;status.setText(message+"\n查看位置：知识库 → "+destination.optString("name")+" → 开始自适应练习");renderResult(bundle);if(openLibrary!=null&&importedLibrary>0)button(results,"进入题库练习",()->openLibrary.accept(importedLibrary),true);controls();}});});}
    public Bundle saveState(){Bundle b=new Bundle();b.putString("owner",session.userId);b.putLong("target",targetLibrary);b.putString("job",job);b.putString("requirements",requirements.getText().toString());b.putString("libraryName",libraryName.getText().toString());b.putInt("count",countPicker.getSelectedItemPosition());b.putInt("difficulty",difficultyPicker.getSelectedItemPosition());b.putInt("point",pointPicker.getSelectedItemPosition());b.putBoolean("adaptive",adaptive.isChecked());b.putString("uploaded",uploadedIds.toString());b.putString("warnings",uploadWarnings.toString());b.putString("names",new JSONArray(names).toString());return b;}
    @Override public void close(){closed=true;ui.removeCallbacks(pollTask);worker.shutdownNow();pollWorker.shutdownNow();cancelWorker.shutdownNow();}
}
