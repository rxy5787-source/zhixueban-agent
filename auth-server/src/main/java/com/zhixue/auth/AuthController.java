package com.zhixue.auth;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import jakarta.validation.constraints.NotNull;
import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    public record Credentials(@NotNull @Pattern(regexp="[A-Za-z0-9_]{4,32}") String username,
                              @NotNull @Size(min=8,max=128) String password) { }
    private final AuthService service;
    private final RequestLimits limits = new RequestLimits();
    public AuthController(AuthService service) { this.service = service; }
    @GetMapping("/health") public Map<String,String> health() { return Map.of("status", "ok", "service", "zhixue-auth"); }
    @PostMapping("/register") public AuthService.Login register(@Valid @RequestBody Credentials form, HttpServletRequest request) {
        limits.check("register:" + request.getRemoteAddr(), 20, 3_600_000);
        return service.register(form.username(), form.password());
    }
    @PostMapping("/login") public AuthService.Login login(@Valid @RequestBody Credentials form, HttpServletRequest request) {
        limits.check("login-ip:" + request.getRemoteAddr(), 60, 60_000);
        limits.check("login-user:" + form.username().toLowerCase(java.util.Locale.ROOT), 15, 60_000);
        return service.login(form.username(), form.password());
    }
    @GetMapping("/me") public AuthService.User me(@RequestHeader(value="Authorization",required=false) String auth) { return service.current(auth); }
    @PostMapping("/renew") public AuthService.Login renew(@RequestHeader(value="Authorization",required=false) String auth) { return service.renew(auth); }
    @PostMapping("/logout") public Map<String,Boolean> logout(@RequestHeader(value="Authorization",required=false) String auth) {
        service.logout(auth); return Map.of("success", true);
    }
}
