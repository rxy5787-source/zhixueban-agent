package com.example.adaptive_quiz_app.auth;

import org.junit.Test;
import static org.junit.Assert.*;

public class AuthSessionTest {
    @Test public void localAccessStopsAtTheSavedExpiry() {
        AuthSession session=new AuthSession("token","user","name",1000);
        assertTrue(session.usableAt(999));
        assertFalse(session.usableAt(1000));
        assertFalse(session.usableAt(1001));
    }
    @Test public void missingIdentityCannotOpenLocalLearning() {
        assertFalse(new AuthSession("","user","name",1000).usableAt(1));
        assertFalse(new AuthSession("token","","name",1000).usableAt(1));
        assertFalse(new AuthSession("token","user","",1000).usableAt(1));
        assertFalse(new AuthSession(null,"user","name",1000).usableAt(1));
    }
}
