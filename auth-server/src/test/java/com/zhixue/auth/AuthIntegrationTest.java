package com.zhixue.auth;

import com.jayway.jsonpath.JsonPath;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties={"spring.datasource.url=jdbc:h2:mem:auth-tests;DB_CLOSE_DELAY=-1", "auth.session-seconds=3600"})
class AuthIntegrationTest {
    @Value("${local.server.port}") int port;
    @Autowired JdbcTemplate sql;
    final HttpClient http=HttpClient.newHttpClient();
    String name(){return "test_"+UUID.randomUUID().toString().replace("-","").substring(0,16);}
    HttpResponse<String> call(String method,String route,String body,String token) throws Exception {
        var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/auth/"+route));
        if(token!=null)request.header("Authorization","Bearer "+token);
        if(body!=null)request.header("Content-Type","application/json");
        request.method(method,body==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofString(body));
        return http.send(request.build(),HttpResponse.BodyHandlers.ofString());
    }
    String credentials(String username,String password){return "{\"username\":\""+username+"\",\"password\":\""+password+"\"}";}
    @Test void registrationLoginLogoutAndStoredSecrets() throws Exception {
        String username=name(),password="Long-test-password_123";
        var registered=call("POST","register",credentials(username,password),null);assertEquals(200,registered.statusCode(),registered.body());
        String token=JsonPath.read(registered.body(),"$.token"),id=JsonPath.read(registered.body(),"$.user.id");
        assertEquals("no-store",registered.headers().firstValue("Cache-Control").orElse(""));
        assertEquals(200,call("GET","me",null,token).statusCode());
        assertEquals(401,call("POST","login",credentials(username,"wrong-password"),null).statusCode());
        var loggedIn=call("POST","login",credentials(username.toUpperCase(java.util.Locale.ROOT),password),null);
        assertEquals(200,loggedIn.statusCode());assertEquals(id,JsonPath.read(loggedIn.body(),"$.user.id"));
        String stored=sql.queryForObject("SELECT password_hash FROM auth_user WHERE id=?",String.class,id);
        assertNotEquals(password,stored);assertTrue(stored.startsWith("600000$"));assertTrue(PasswordHash.matches(password,stored));
        assertEquals(0,sql.queryForObject("SELECT COUNT(*) FROM auth_session WHERE token_hash=?",Integer.class,token));
        assertEquals(409,call("POST","register",credentials(username.toUpperCase(java.util.Locale.ROOT),password),null).statusCode());
        assertEquals(1,sql.queryForObject("SELECT COUNT(*) FROM auth_user WHERE username=?",Integer.class,username));
        assertEquals(200,call("POST","logout","{}",token).statusCode());
        assertEquals(401,call("GET","me",null,token).statusCode());
    }
    @Test void nullMalformedAndShortCredentialsAreRejected() throws Exception {
        for(String input:new String[]{"{}","null","{\"username\":null,\"password\":null}",credentials("bad","123"),credentials("x' OR 1=1","password123")})
            assertEquals(400,call("POST","register",input,null).statusCode(),input);
        assertEquals(401,call("GET","me",null,null).statusCode());
        assertEquals(401,call("GET","me",null,"not-a-token").statusCode());
    }
    @Test void expiryAndRevocationAreEnforcedByServer() throws Exception {
        var created=call("POST","register",credentials(name(),"password123"),null);
        String token=JsonPath.read(created.body(),"$.token");
        sql.update("UPDATE auth_session SET expires_at=0 WHERE token_hash=?",AuthService.digest(token));
        assertEquals(401,call("GET","me",null,token).statusCode());
    }
    @Test void repeatedPasswordGuessingIsLimited() throws Exception {
        String username=name();
        for(int i=0;i<15;i++)assertEquals(401,call("POST","login",credentials(username,"incorrect-password"),null).statusCode());
        assertEquals(429,call("POST","login",credentials(username,"incorrect-password"),null).statusCode());
    }
    @Test void renewalExtendsOnlyExistingValidSessions() throws Exception {
        var created=call("POST","register",credentials(name(),"password123"),null);
        String token=JsonPath.read(created.body(),"$.token"),id=JsonPath.read(created.body(),"$.user.id");
        long shortExpiry=System.currentTimeMillis()+60_000;
        sql.update("UPDATE auth_session SET expires_at=? WHERE token_hash=?",shortExpiry,AuthService.digest(token));
        var renewed=call("POST","renew","{}",token);
        assertEquals(200,renewed.statusCode(),renewed.body());
        assertEquals(token,JsonPath.read(renewed.body(),"$.token"));
        assertEquals(id,JsonPath.read(renewed.body(),"$.user.id"));
        assertTrue(((Number)JsonPath.read(renewed.body(),"$.expiresAt")).longValue()>shortExpiry);
        assertEquals("no-store",renewed.headers().firstValue("Cache-Control").orElse(""));
        assertEquals(200,call("POST","logout","{}",token).statusCode());
        assertEquals(401,call("POST","renew","{}",token).statusCode());
        assertEquals(0,sql.queryForObject("SELECT COUNT(*) FROM auth_session WHERE token_hash=?",Integer.class,AuthService.digest(token)));
        assertEquals(401,call("POST","renew","{}",null).statusCode());
        assertEquals(401,call("POST","renew","{}","not-a-token").statusCode());
    }
    @Test void renewalCannotReviveExpiredSessionsOrShortenLongerExpiry() throws Exception {
        var created=call("POST","register",credentials(name(),"password123"),null);
        String token=JsonPath.read(created.body(),"$.token");
        long longerExpiry=System.currentTimeMillis()+7_200_000;
        sql.update("UPDATE auth_session SET expires_at=? WHERE token_hash=?",longerExpiry,AuthService.digest(token));
        var renewed=call("POST","renew","{}",token);
        assertEquals(200,renewed.statusCode());
        assertEquals(longerExpiry,((Number)JsonPath.read(renewed.body(),"$.expiresAt")).longValue());
        sql.update("UPDATE auth_session SET expires_at=0 WHERE token_hash=?",AuthService.digest(token));
        assertEquals(401,call("POST","renew","{}",token).statusCode());
        assertEquals(0L,sql.queryForObject("SELECT expires_at FROM auth_session WHERE token_hash=?",Long.class,AuthService.digest(token)));
    }
    @Test void concurrentLogoutAndRenewalCannotRestoreARevokedToken() throws Exception {
        var created=call("POST","register",credentials(name(),"password123"),null);
        String token=JsonPath.read(created.body(),"$.token");
        var executor=java.util.concurrent.Executors.newFixedThreadPool(2);
        var start=new java.util.concurrent.CountDownLatch(1);
        try {
            var renew=executor.submit(()->{start.await();return call("POST","renew","{}",token).statusCode();});
            var logout=executor.submit(()->{start.await();return call("POST","logout","{}",token).statusCode();});
            start.countDown();
            int status=renew.get(10,java.util.concurrent.TimeUnit.SECONDS);
            assertTrue(status==200||status==401);
            assertEquals(200,logout.get(10,java.util.concurrent.TimeUnit.SECONDS));
            assertEquals(401,call("GET","me",null,token).statusCode());
            assertEquals(401,call("POST","renew","{}",token).statusCode());
        } finally {executor.shutdownNow();}
    }
    @Test void passwordSaltsAreUniqueAndWhitespaceIsNotTrimmed() {
        String a=PasswordHash.create(" password123 "),b=PasswordHash.create(" password123 ");
        assertNotEquals(a,b);assertTrue(PasswordHash.matches(" password123 ",a));assertFalse(PasswordHash.matches("password123",a));
    }
}
