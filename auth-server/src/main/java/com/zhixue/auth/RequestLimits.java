package com.zhixue.auth;

import java.util.HashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

final class RequestLimits {
    private record Bucket(long until, int count) { }
    private final Map<String,Bucket> buckets = new HashMap<>();
    synchronized void check(String key, int limit, long window) {
        long now = System.currentTimeMillis();
        buckets.entrySet().removeIf(entry -> entry.getValue().until <= now);
        Bucket current = buckets.get(key);
        if ((current != null && current.count >= limit) || (current == null && buckets.size() >= 10_000))
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS, "操作过于频繁，请稍后重试");
        buckets.put(key, current == null ? new Bucket(now + window, 1) : new Bucket(current.until, current.count + 1));
    }
}
