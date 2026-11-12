package com.example.adaptive_quiz_app.dao;

import androidx.room.Dao;
import androidx.room.Insert;
import androidx.room.Query;

import com.example.adaptive_quiz_app.entity.User;

@Dao
public interface UserDao {

    // 注册：插入用户，返回新行的 id
    @Insert
    long register(User user);

    // 登录：按账号 + 密码查询，查不到返回 null
    @Query("SELECT * FROM user WHERE username = :username AND password = :password LIMIT 1")
    User login(String username, String password);

    // 注册前检查：按账号查询，查不到返回 null
    @Query("SELECT * FROM user WHERE username = :username LIMIT 1")
    User findByUsername(String username);
}
