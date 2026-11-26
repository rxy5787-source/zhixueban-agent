# 账号与 Web 学习空间绑定

## 使用边界

Spring Boot 的 `POST /api/auth/learning-space` 供可信后端调用。请求只需要现有账号会话的 `Authorization: Bearer …`，返回 `{"spaceId":"…"}`。接口默认关闭，响应禁止缓存。绑定在首次解析时惰性建立，Android 的注册、登录和续期接口保持原契约。访客 Cookie 对该端点无效。

账号服务先验证会话，然后在同一事务中锁定账号行、查找或创建绑定。账号 ID 是主键及 `auth_user.id` 的外键，空间 ID 有唯一约束。同一个账号的并发首次请求串行执行。重新登录产生的新会话继续使用已有绑定。

Python 的 `backend.account_space.resolve_account_space` 仅接受 Bearer 会话和服务端配置的数据根目录。解析结果是 `<数据根>/account-spaces/<spaceId>`。游客仍使用 `spaces/<spaceId>`。本轮解析器不创建数据库、不挂载学习路由，也不读取历史游客数据。空间 ID 仅供后端定位，后续开放账号学习路由时仍需逐请求验证会话。

## 迁移与回滚

1. 保持端点关闭。核对运行实例的数据库类型、有效配置来源和持久化位置。对账号库做一致性备份，在隔离副本确认还原可用。
2. 使用目标数据库的管理工具执行 `auth-server/src/main/resources/migrations/V001__account_learning_space.sql`。这是增量 SQL。它保留已存在的用户、会话、访客空间和学习记录。测试启动时才显式把此文件追加到 Spring 的 schema 初始化列表。
3. 检查新表及主键、外键和唯一约束后，以 `--auth.learning-space.enabled=true` 在测试实例启用接口。账号接口在内部服务边界使用，避免对浏览器公开空间 ID。
4. 应用回滚先撤掉启用参数或设为 `false`。保留表和绑定，重新启用时仍能找到同一个空间。隔离测试库需要撤销 DDL 时，在确认没有绑定数据后可执行 `DROP TABLE account_learning_space`。一旦部署已产生绑定或学习空间，先备份映射及目录并验证恢复。直接删表会丢失定位已有学习空间所需的映射。

## 回归命令

在交付仓库根目录执行：

```powershell
.\gradlew.bat :auth-server:test --offline --no-daemon
.\python-ai\.venv\Scripts\python.exe -m pytest -q python-ai/test_account_space.py python-ai/test_agent_api.py
```

Java 集成测试启动 Spring Boot 和临时内存 H2，并通过真实 HTTP 检查会话和映射。Python 测试使用测试替身模拟账号服务响应，另外在临时路径创建真实 SQLite，验证存储命名空间分离。
