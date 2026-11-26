# Web 账号会话与文字资料

## 测试入口

在测试账号库执行 V001，并用 Spring Boot 参数 `--auth.learning-space.enabled=true` 开启空间解析。在打包后的 Web FastAPI 服务配置 `AI_AUTH_URL` 指向受信任的账号服务，设置 `TRIAL_ACCOUNT_LOGIN=1`，打开同源的 `/account`。账号功能默认关闭。正式入口需要 HTTPS，HTTP 例外仅限既有本地预览模式的回环请求。跨主机的账号服务连接应使用受信任的 HTTPS 链路或等价的受保护网络边界。账号服务和数据目录不应经公共反向代理直接开放。

Web 通过同源 JSON 调用 `POST /api/account/login` 或 `POST /api/account/register`。FastAPI 复用原账号服务，再用返回的 Bearer 会话查询已验证身份及空间 ID。浏览器仅收到账号显示名和 HttpOnly 会话 Cookie。注册或登录后进入 `/learn#home/study`。学习接口重新验证会话，检查页面声明的当前账号与验证身份一致，再进入账号本身的 Web 学习 SQLite。游客仍由独立的游客入口进入。退出会调用原账号服务销毁会话。所有可写请求要求精确 Origin 及自定义请求头，本应用不启用跨域凭证。

## 本轮范围

- `GET /api/account/session` 恢复登录状态，`POST /api/account/logout` 撤销会话。
- `GET /api/account/materials` 列出文字资料，`POST /api/account/materials` 新建。
- `GET /api/account/materials/{id}` 读取，`PUT` 修改，`DELETE` 删除。
- 文字资料保存在服务端绑定的 `account-spaces/<spaceId>/materials.sqlite3`，最多 100 条，每条正文最多 20,000 字符。库内所有者标记能识别误绑到另一账号已初始化的目录。访客 API、Android 原接口和 IndexedDB 各自沿用现有访问方式。

账号学习页复用原有学习对话、知识库和任务界面。独立的文字资料编辑器仍可通过学习页访问，其资料尚未接入 AI 出题。HTTPS 反向代理、Android 真机及多实例部署仍待联调。现有账号密码哈希、登录限流与会话续期策略沿用账号服务。正式开启前需确认反向代理边界、数据库持久化和备份，账号资料与学习 SQLite 应和绑定表一起纳入恢复演练。

## 验证

在交付仓库根目录运行 `./tools/test-web-account.ps1`。脚本构建 Spring Boot，启动仅监听回环地址且随机端口的真实 Java 服务。数据库使用临时内存 H2。账号网关通过 FastAPI TestClient 以 HTTPS 请求语义驱动，Python 到 Java 通过真实 HTTP，资料写入临时 SQLite。账号过期用例使用真实 60 秒会话。不可用服务与错误绑定由测试替身注入。脚本还运行已有访客和 Agent 回归。关闭 `TRIAL_ACCOUNT_LOGIN` 可撤下 Web 账号入口，现有绑定和资料文件仍保留。
