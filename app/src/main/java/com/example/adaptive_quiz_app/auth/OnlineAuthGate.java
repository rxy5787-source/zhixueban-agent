package com.example.adaptive_quiz_app.auth;

import android.content.Context;
import android.content.Intent;
import android.net.ConnectivityManager;
import android.net.Network;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import com.example.adaptive_quiz_app.LoginActivity;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

/** Restore local learning immediately; confirm and renew the saved session in the background. */
public final class OnlineAuthGate implements AutoCloseable {
    private static final long FOREGROUND_CHECK_MS=5*60_000L;
    private static final long BACKGROUND_CHECK_MS=30*60_000L;
    private final AppCompatActivity activity;
    private final Consumer<AuthSession> firstReady;
    private final SessionStore sessions;
    private final AuthApi api=new AuthApi();
    private final Handler ui=new Handler(Looper.getMainLooper());
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final ConnectivityManager connectivity;
    private boolean active,closed,checking,initialized,registered,redirecting;
    private long lastAttempt=-1;
    private String initialUser;
    private final Runnable checkAgain=()->verify(true);
    private final Runnable expiry=()->{
        AuthSession session=localSession();
        if(session!=null)scheduleExpiry(session);
    };
    private final ConnectivityManager.NetworkCallback network=new ConnectivityManager.NetworkCallback() {
        @Override public void onAvailable(Network value){ui.post(()->verify(true));}
        // A lost connection does not invalidate a previously authenticated local identity.
    };
    public OnlineAuthGate(AppCompatActivity activity,Consumer<AuthSession> ready) {
        this.activity=activity;firstReady=ready;sessions=new SessionStore(activity);
        connectivity=(ConnectivityManager)activity.getSystemService(Context.CONNECTIVITY_SERVICE);
    }
    public void start() {
        active=true;
        if(AuthTestBridge.isEnabled()){initialized=true;firstReady.accept(null);return;}
        if(localSession()==null)return;
        connectivity.registerDefaultNetworkCallback(network);registered=true;
        verify(false);
    }
    public void resume() {
        active=true;
        if(!AuthTestBridge.isEnabled())verify(false);
    }
    public void pause(){active=false;ui.removeCallbacks(checkAgain);ui.removeCallbacks(expiry);}
    private AuthSession localSession() {
        if(closed||!active||redirecting||activity.isFinishing()||activity.isDestroyed())return null;
        AuthSession session=sessions.load();
        if(session==null||!session.usableAt(System.currentTimeMillis())) {
            if(session!=null)sessions.clearIfCurrent(session);
            redirect();return null;
        }
        if(initialUser!=null&&!initialUser.equals(session.userId)){redirect();return null;}
        if(!initialized) {
            initialized=true;initialUser=session.userId;firstReady.accept(session);
        }
        return session;
    }
    private void verify(boolean force) {
        if(AuthTestBridge.isEnabled())return;
        AuthSession session=localSession();
        if(session==null)return;
        scheduleExpiry(session);
        if(checking)return;
        if(!AuthApi.connected(activity)){scheduleCheck(FOREGROUND_CHECK_MS);return;}
        long elapsed=SystemClock.elapsedRealtime();
        if(!force&&lastAttempt>=0&&elapsed-lastAttempt<FOREGROUND_CHECK_MS) {
            scheduleCheck(FOREGROUND_CHECK_MS-(elapsed-lastAttempt));return;
        }
        checking=true;lastAttempt=elapsed;
        worker.execute(()->{
            Exception failure=null;
            try {
                api.flushLogout(sessions);
                AuthSession renewed=api.renew(session);
                sessions.saveIfCurrent(session,renewed);
            } catch(Exception error) {
                failure=error;
                // Timeouts and service failures retain the cached identity.
                if(error instanceof AuthApi.Failure&&((AuthApi.Failure)error).status==401)
                    sessions.clearIfCurrent(session);
            }
            Exception error=failure;
            ui.post(()->{
                checking=false;
                AuthSession current=localSession();
                if(current==null)return;
                scheduleExpiry(current);
                scheduleCheck(error==null?BACKGROUND_CHECK_MS:FOREGROUND_CHECK_MS);
            });
        });
    }
    private void scheduleCheck(long delay) {
        ui.removeCallbacks(checkAgain);
        if(active&&!closed&&!redirecting)ui.postDelayed(checkAgain,Math.max(1,delay));
    }
    private void scheduleExpiry(AuthSession session) {
        ui.removeCallbacks(expiry);
        if(active&&!closed&&!redirecting)
            ui.postDelayed(expiry,Math.max(1,session.expiresAt-System.currentTimeMillis()));
    }
    public void logout() {
        AuthSession session=sessions.load();
        try {
            if(session!=null)sessions.queueLogout(session.token);
            sessions.clear();
        } catch(Exception error) {
            Toast.makeText(activity,"暂时无法退出登录，请稍后重试",Toast.LENGTH_LONG).show();return;
        }
        ui.removeCallbacks(checkAgain);ui.removeCallbacks(expiry);
        worker.execute(()->{if(AuthApi.connected(activity))api.flushLogout(sessions);});
        redirect();
    }
    private void redirect() {
        if(closed||redirecting||activity.isFinishing()||activity.isDestroyed())return;
        redirecting=true;
        activity.startActivity(new Intent(activity,LoginActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));
        activity.finish();
    }
    @Override public void close() {
        closed=true;ui.removeCallbacksAndMessages(null);
        if(registered)try{connectivity.unregisterNetworkCallback(network);}catch(IllegalArgumentException ignored){}
        worker.shutdown();
    }
}
