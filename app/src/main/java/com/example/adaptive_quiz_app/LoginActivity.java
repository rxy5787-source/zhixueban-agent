package com.example.adaptive_quiz_app;

import android.content.Intent;
import android.os.Bundle;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import com.example.adaptive_quiz_app.auth.*;
import com.example.adaptive_quiz_app.ui.auth.AuthForm;
import com.example.adaptive_quiz_app.ui.auth.AuthUi;
import com.example.adaptive_quiz_app.ui.TypeScale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Online account entry. The original XML and local legacy account database are retained. */
public class LoginActivity extends AppCompatActivity {
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final AuthApi api=new AuthApi();
    private SessionStore sessions;
    private boolean busy;
    protected boolean initialRegistration(){return false;}
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        androidx.appcompat.app.AppCompatDelegate.setDefaultNightMode(androidx.appcompat.app.AppCompatDelegate.MODE_NIGHT_NO);
        sessions=new SessionStore(this);
        AuthSession cached=sessions.load();
        if(cached!=null&&cached.usableAt(System.currentTimeMillis())) {
            continueWith(cached);
        } else {
            if(cached!=null)sessions.clearIfCurrent(cached);
            render(cached==null?"":"登录已过期，请重新登录");
        }
    }
    private void render(String message) {
        if(isFinishing()||isDestroyed())return;
        AuthUi.show(this,message,busy,sessions.load()!=null,initialRegistration(),this::submit);
    }
    private void submit(AuthForm form) {
        if(busy)return;
        if("retry".equals(form.getAction())){verifyExisting();return;}
        if(!form.getUsername().matches("[A-Za-z0-9_]{4,32}")){render("账号需为4–32位字母、数字或下划线");return;}
        if(form.getPassword().length()<8||form.getPassword().length()>128){render("密码需为8–128位");return;}
        if(form.getRegister()&&!form.getPassword().equals(form.getConfirmation())){render("两次输入的密码不一致");return;}
        runOnline(()->{
            api.flushLogout(sessions);
            AuthSession result=api.authenticate(form.getRegister(),form.getUsername(),form.getPassword());
            AuthSession previous=sessions.load();
            if(previous!=null){sessions.queueLogout(previous.token);api.flushLogout(sessions);}
            sessions.save(result);return result;
        });
    }
    private void verifyExisting() {
        AuthSession session=sessions.load();if(session==null){render("");return;}
        if(session.usableAt(System.currentTimeMillis()))continueWith(session);
        else {sessions.clearIfCurrent(session);render("登录已过期，请重新登录");}
    }
    private interface LoginWork { AuthSession run() throws Exception; }
    private void runOnline(LoginWork work) {
        if(busy)return;
        if(!AuthApi.connected(this)){render("请先连接网络，再登录或注册");return;}
        busy=true;render("");
        worker.execute(()->{
            AuthSession session=null;String error=null;
            try { session=work.run(); }
            catch(AuthApi.Failure failure){error=failure.getMessage();}
            catch(Exception failure){error="暂时无法连接账号服务，请检查网络后重试";}
            AuthSession result=session;String message=error;
            runOnUiThread(()->{
                busy=false;if(isFinishing()||isDestroyed())return;
                if(result!=null)continueWith(result);else render(message);
            });
        });
    }
    private void continueWith(AuthSession session) {
        if(AccountScope.needsLegacyChoice(this,session.userId)) {
            TypeScale.dialog(new AlertDialog.Builder(this).setTitle("保留原有学习记录")
                    .setMessage("这台手机已有题库和学习记录。是否关联到当前账号？其他账号会使用独立的学习空间。")
                    .setCancelable(false)
                    .setPositiveButton("关联并继续",(d,w)->chooseSpace(session,true))
                    .setNegativeButton("新建学习空间",(d,w)->chooseSpace(session,false)).create());
        } else openHome();
    }
    private void chooseSpace(AuthSession session,boolean claim) {
        try { AccountScope.choose(this,session.userId,claim);openHome(); }
        catch(Exception error){render(error.getMessage());}
    }
    private void openHome() {
        startActivity(new Intent(this,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));finish();
    }
    @Override protected void onDestroy(){worker.shutdown();super.onDestroy();}
}
