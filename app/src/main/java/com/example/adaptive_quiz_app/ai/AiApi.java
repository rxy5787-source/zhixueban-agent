package com.example.adaptive_quiz_app.ai;

import android.content.Context;
import android.net.Uri;
import com.example.adaptive_quiz_app.BuildConfig;
import com.example.adaptive_quiz_app.auth.AuthSession;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.json.*;

/** Short task requests only. Model inference stays in the server worker. */
public final class AiApi {
    public final String base;
    public static final class Failure extends IOException {public final int status;Failure(int s,String m){super(m);status=s;}}
    public AiApi(){this(BuildConfig.AI_BASE_URL);}
    public AiApi(String url){base=url.replaceAll("/+$","");}
    private HttpURLConnection connection(String route,String method,AuthSession session)throws Exception {
        if(base.isEmpty())throw new IOException("AI 服务尚未配置");
        URL url=new URL(base+"/api/ai/"+route);
        String host=url.getHost();boolean local=host.equals("127.0.0.1")||host.equals("localhost")||host.equals("10.0.2.2")||host.matches("192\\.168\\.\\d+\\.\\d+|10\\.\\d+\\.\\d+\\.\\d+|172\\.(1[6-9]|2\\d|3[01])\\.\\d+\\.\\d+");
        if(!url.getProtocol().equals("https")&&!(BuildConfig.DEBUG&&local&&url.getProtocol().equals("http")))throw new IOException("AI 服务需要 HTTPS 连接");
        HttpURLConnection c=(HttpURLConnection)url.openConnection();c.setConnectTimeout(6000);c.setReadTimeout(30000);c.setInstanceFollowRedirects(false);c.setUseCaches(false);c.setRequestMethod(method);c.setRequestProperty("Authorization","Bearer "+session.token);c.setRequestProperty("Accept","application/json");return c;
    }
    public JSONObject request(String method,String route,AuthSession session,JSONObject body)throws Exception {
        HttpURLConnection c=connection(route,method,session);
        try {
            if(body!=null){byte[] data=body.toString().getBytes(StandardCharsets.UTF_8);c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json; charset=utf-8");c.setFixedLengthStreamingMode(data.length);try(OutputStream o=c.getOutputStream()){o.write(data);}}
            return response(c);
        } catch(IOException error) {throw connectionFailure(error);} finally {c.disconnect();}
    }
    public JSONObject upload(Context context,List<Uri> uris,List<String> names,AuthSession session)throws Exception {
        if(uris.isEmpty()||uris.size()>5)throw new IOException("请选择 1–5 份资料");
        String boundary="zhixue"+UUID.randomUUID().toString().replace("-","");HttpURLConnection c=connection("files","POST",session);
        try {
            c.setDoOutput(true);c.setChunkedStreamingMode(65536);c.setRequestProperty("Content-Type","multipart/form-data; boundary="+boundary);
            try(OutputStream out=c.getOutputStream()) {
                for(int i=0;i<uris.size();i++) {
                    String name=names.get(i).replaceAll("[\\r\\n\\\"\\\\]","_");
                    out.write(("--"+boundary+"\r\nContent-Disposition: form-data; name=\"files\"; filename=\""+name+"\"\r\nContent-Type: application/octet-stream\r\n\r\n").getBytes(StandardCharsets.UTF_8));
                    int total=0,count;byte[] buffer=new byte[65536];
                    try(InputStream in=context.getContentResolver().openInputStream(uris.get(i))){if(in==null)throw new IOException("无法读取资料");while((count=in.read(buffer))!=-1){total+=count;if(total>20*1024*1024)throw new IOException("单文件超过 20 MB");out.write(buffer,0,count);}}
                    out.write("\r\n".getBytes(StandardCharsets.UTF_8));
                }
                out.write(("--"+boundary+"--\r\n").getBytes(StandardCharsets.UTF_8));
            }
            return response(c);
        } catch(IOException error) {throw connectionFailure(error);} finally {c.disconnect();}
    }
    private IOException connectionFailure(IOException error){
        if(error instanceof SocketTimeoutException)return new IOException("连接资料服务超时。请检查手机与电脑的 Wi-Fi 连接，并确认电脑服务正在运行。",error);
        if(error instanceof SocketException||error instanceof UnknownHostException){
            boolean usb=base.startsWith("http://127.0.0.1:")||base.startsWith("http://localhost:");
            return new IOException(usb?"当前版本通过 USB 连接电脑服务。请连接 USB 并恢复服务连接，或安装 Wi-Fi 连接版。":"无法连接电脑上的资料服务。请确认手机与电脑连接同一 Wi-Fi，电脑服务已启动；更换网络后需更新连接地址。",error);
        }
        return error;
    }
    private JSONObject response(HttpURLConnection c)throws Exception {
        int status=c.getResponseCode();ByteArrayOutputStream out=new ByteArrayOutputStream();
        try(InputStream in=status>=200&&status<300?c.getInputStream():c.getErrorStream()){
            byte[] buffer=new byte[8192];int n;if(in!=null)while((n=in.read(buffer))!=-1){if(out.size()+n>2*1024*1024)throw new IOException("AI 响应超过 2 MB，请减少题量");out.write(buffer,0,n);}
        }
        JSONObject value=new JSONObject(out.toString("UTF-8"));
        if(status<200||status>=300){Object detail=value.opt("detail");throw new Failure(status,detail instanceof String?(String)detail:"请求失败，请检查资料和账号状态（"+status+"）");}
        return value;
    }
}
