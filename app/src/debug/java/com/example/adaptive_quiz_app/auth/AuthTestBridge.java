package com.example.adaptive_quiz_app.auth;

/** In-process instrumentation hook. Not reachable from intents, preferences, or release builds. */
public final class AuthTestBridge {
    private static volatile boolean enabled;
    private static volatile String baseUrl;
    private static volatile boolean offline;
    public static boolean isEnabled(){return enabled;}
    public static void setEnabled(boolean value){enabled=value;}
    public static String baseUrl(){return baseUrl==null?com.example.adaptive_quiz_app.BuildConfig.AUTH_BASE_URL:baseUrl;}
    public static void setBaseUrl(String value){baseUrl=value;}
    public static boolean offline(){return offline;}
    public static void setOffline(boolean value){offline=value;}
}
