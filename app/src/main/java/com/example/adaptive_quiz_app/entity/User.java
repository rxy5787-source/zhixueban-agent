package com.example.adaptive_quiz_app.entity;

import androidx.room.Entity;
import androidx.room.PrimaryKey;

@Entity(tableName = "user")
public class User {

    @PrimaryKey(autoGenerate = true)
    public int id;

    public String username;

    public String password;

    public User(String username, String password) {
        this.username = username;
        this.password = password;
    }
}
