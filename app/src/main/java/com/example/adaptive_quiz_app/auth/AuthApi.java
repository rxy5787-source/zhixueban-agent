package com.example.adaptive_quiz_app.auth;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import com.example.adaptive_quiz_app.BuildConfig;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

public final class AuthApi {
    private final String base;
    public static final class Failure extends Exception {
        public final int status;
        public Failure(int status,String message) { super(message);this.status=status; }
    }
    public AuthApi() { this(AuthTestBridge.baseUrl()); }
    public AuthApi(String base) { this.base=base.replaceAll("/+$",""); }
    public static boolean connected(Context context) {
        if(AuthTestBridge.offline())return false;
        ConnectivityManager manager=(ConnectivityManager)context.getSystemService(Context.CONNECTIVITY_SERVICE);
        NetworkCapabilities capabilities=manager.getNetworkCapabilities(manager.getActiveNetwork());
        return capabilities!=null&&capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }
    public AuthSession authenticate(boolean register,String username,String password) throws Exception {
        JSONObject payload=new JSONObject().put("username",username).put("password",password);
        JSONObject response=request("POST",register?"register":"login",null,payload);
        return session(response);
    }
    private static AuthSession session(JSONObject response) throws Exception {
        JSONObject user=response.getJSONObject("user");
        return new AuthSession(response.getString("token"),user.getString("id"),user.getString("username"),response.getLong("expiresAt"));
    }
    public AuthSession renew(AuthSession previous) throws Exception {
        AuthSession renewed=session(request("POST","renew",previous.token,new JSONObject()));
        if(!previous.userId.equals(renewed.userId)||!previous.token.equals(renewed.token))
            throw new Failure(401,"登录状态已变化，请重新登录");
        if(!renewed.usableAt(System.currentTimeMillis()))throw new Failure(502,"账号服务响应异常");
        return renewed;
    }
    public AuthSession verify(AuthSession session) throws Exception {
        JSONObject user=request("GET","me",session.token,null);
        if(!session.userId.equals(user.getString("id")))throw new Failure(401,"登录状态已变化，请重新登录");
        return new AuthSession(session.token,user.getString("id"),user.getString("username"),session.expiresAt);
    }
    public void logout(String token) throws Exception { request("POST","logout",token,new JSONObject()); }
    public void flushLogout(SessionStore store) {
        String token=store.pendingLogout();if(token==null)return;
        try { logout(token);store.clearPendingLogout(token); } catch(Exception ignored) { /* Retried on the next successful connection. */ }
    }
    private JSONObject request(String method,String route,String token,JSONObject body) throws Exception {
        if(base.isEmpty())throw new Failure(503,"账号服务尚未配置，请联系维护人员");
        URL url=new URL(base+"/api/auth/"+route);
        if(!"https".equals(url.getProtocol())&&!(BuildConfig.DEBUG&&"http".equals(url.getProtocol())&&developmentHost(url.getHost())))
            throw new Failure(503,"账号服务连接不安全，请联系维护人员");
        HttpURLConnection connection=(HttpURLConnection)url.openConnection();
        try {
            connection.setConnectTimeout(6000);connection.setReadTimeout(6000);connection.setUseCaches(false);
            connection.setInstanceFollowRedirects(false);connection.setRequestMethod(method);
            connection.setRequestProperty("Accept","application/json");
            if(token!=null)connection.setRequestProperty("Authorization","Bearer "+token);
            if(body!=null) {
                byte[] bytes=body.toString().getBytes(StandardCharsets.UTF_8);connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type","application/json; charset=utf-8");connection.setFixedLengthStreamingMode(bytes.length);
                try(java.io.OutputStream out=connection.getOutputStream()){out.write(bytes);}
            }
            int status=connection.getResponseCode();
            JSONObject response;
            try(InputStream stream=status>=200&&status<300?connection.getInputStream():connection.getErrorStream()) {
                ByteArrayOutputStream bytes=new ByteArrayOutputStream();byte[] buffer=new byte[2048];int count;
                if(stream!=null)while((count=stream.read(buffer))!=-1){if(bytes.size()+count>16384)throw new Failure(502,"账号服务响应异常");bytes.write(buffer,0,count);}
                String text=bytes.toString("UTF-8");response=text.isEmpty()?new JSONObject():new JSONObject(text);
            }
            if(status<200||status>=300)throw new Failure(status,response.optString("message",status==401?"登录已失效，请重新登录":"暂时无法连接账号服务"));
            return response;
        } finally { connection.disconnect(); }
    }
    private static boolean developmentHost(String host) {
        if(host.equals("localhost")||host.equals("127.0.0.1")||host.equals("10.0.2.2"))return true;
        if(host.matches("192\\.168\\.\\d{1,3}\\.\\d{1,3}")||host.matches("10\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}"))return true;
        return host.matches("172\\.(1[6-9]|2\\d|3[01])\\.\\d{1,3}\\.\\d{1,3}");
    }
}
