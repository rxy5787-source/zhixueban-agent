# Agent Harness 架构审计：测试与证据

日期：2026-11-25（Asia/Shanghai）。目的：核对既有基线与 ZH-04，支持架构规范；不执行新 Agent 功能开发。

## 1. 固定输入

- GitHub main：`d76e9e8d675ab4df5e7e4ab39ef44e1eea62e825`。
- ZH-04 PR #13：`abf18617d197d3788b6909b0e3bb19633109a110`。
- 本机 Web/账号开发副本：`artifacts/zhixueban-development`，`codex/web-account-session`，`d7ae77a07b4114674df147a334827dbbca384a18`。
- 本机学习副本：`artifacts/zhixueban-agent-learning`，`codex/agent-learning-week1`，`05a42c69279da9b9805b08fda564873575bb5162`。
- 当前工作台：HEAD `d01928d` 加原有未提交 Android/认证改动；此版本不能用 HEAD 单独还原，不能当作干净 GitHub 提交。
- 参考课程：`shareAI-lab/learn-claude-code`，main `448c75bb596917ad196cc1fb7558f459c5c50fdd`，读取当前 s01–s17 根目录教程。

使用 `git fetch` 只读取 GitHub main/ZH-04，并用 `git archive` 解出两个固定快照。没有 checkout、pull、merge、push，没有覆盖任何既有源码。临时快照与打包产物位于当前工作台已忽略的 `.gradle/agent-harness-audit-20261125/`。此目录是可重新生成的本机测试输出，不作为项目源码依赖。

## 2. 环境和依赖

- Windows、PowerShell；Python 3.12.3，使用开发副本已有 `.venv`。
- Node.js v24.10.0、npm 11.6.1。
- JDK 21.0.9（Android Studio jbr）、Gradle wrapper 9.3.1。
- `python -m pip check`：`No broken requirements found.`。没有安装或升级依赖；这证明现有环境依赖一致，不代表本轮从空缓存重装成功。
- Web `npm run build`：TypeScript 和 Vite 生产构建通过。使用已有 node_modules，没有本轮重新执行 `npm ci`。
- 两份固定快照和开发副本分别执行自己的 `deploy/prepare.ps1` 并成功应用部署补丁；pytest 的 `PYTHONPATH` 指向各自的打包 `server/`。

## 3. 实际运行结果

### GitHub main 固定快照

`pytest -q web-prototype/deploy/test_web_trial.py`

**13 passed，1 warning，18.39 秒。** 覆盖既有访客边界、上传续传/回执、请求大小、任务重启、超时、取消及并发重试/归档。使用临时 SQLite 与固定处理响应，不是模型质量评测。

### ZH-04 PR #13 固定快照

相同命令，使用此 head 自己的测试文件和打包产物。

**14 passed，1 warning，19.54 秒。** 其中新增的双访客测试走实际上传、Runner、归档和作答，模型生成函数被固定响应替代。逐项核对双向拒绝任务、题目、回执、保存、练习提交、追问和移除对方资料，并检查列表和知识点观察次数。

额外诊断运行只选 `test_uploaded_material_questions_and_practice_are_isolated`：**1 passed，13 deselected，1 warning**。它是完整 14 项中的重复诊断，不另计独立测试数。

在线读取的 [PR #13 CI](https://github.com/rxy5787-source/zhixueban-agent/actions/runs/43390006261) 为 completed/success，head=`abf18617…`。main 的 [Web CI](https://github.com/rxy5787-source/zhixueban-agent/actions/runs/43389660386) 也是 completed/success，head=`d76e9e8…`。本次没有新触发远程 CI。

### 本机 Web/账号开发副本

`pytest -q web-prototype/deploy/test_web_trial.py web-prototype/deploy/test_account_web.py`

首次未设置真实账号测试服务地址：**24 passed，3 skipped，1 warning，19.52 秒**。跳过的三项通过 `live_auth` fixture 明确要求 `ZHIXUE_TEST_AUTH_URL`；不能计作通过。

`pytest -q python-ai/test_account_space.py python-ai/test_agent_api.py python-ai/test_practice_coverage.py python-ai/test_web_question_review.py`

**40 passed，1 warning，7.38 秒。** 覆盖账号空间解析失效关闭、只读 Agent 凭证与空间限制、覆盖计划和题目校验；身份服务响应为测试替身，SQLite 为真实临时数据库。

### 本机学习/Agent 实验副本

`pytest -q python-ai/test_agent_runtime.py python-ai/test_study_skill_planner.py python-ai/test_weak_points_skill.py`

**48 passed，1.51 秒。** 验证有界循环、已注册处理函数、契约、重试、学习证据与规划；固定测试函数不代表模型驱动 Loop 已通过本地推理验收。

### Android 与 Java 认证基线

在当前工作台用 JDK 21 执行：

```powershell
.\gradlew.bat :app:testDebugUnitTest :auth-server:test --offline --no-daemon --console=plain
```

增量构建成功，测试任务显示 UP-TO-DATE，**不将其算作本轮重新执行单测**。为取得新结果，另行仅强制重跑两个测试任务：

```powershell
.\gradlew.bat :app:testDebugUnitTest --rerun :auth-server:test --rerun --offline --no-daemon --console=plain
```

最终结果与账号联调补测记录在本文件第 7 节；不能根据旧 XML 时间戳宣称新验收。

## 4. 首次停滞的定位

沙盒内 TestClient 测试没有到达业务断言。设置 `faulthandler_timeout=45` 后，线程堆栈显示：

```text
socket.accept
  ← socket.socketpair
  ← asyncio Windows ProactorEventLoop._make_self_pipe
  ← anyio.start_blocking_portal
  ← starlette TestClient
```

手动终止这几次停滞进程，在本机隔离测试目录执行相同代码后通过。结论是本轮沙盒的回环 socketpair 限制；没有修改权限代码或削弱测试来绕过业务失败。中断运行不计为测试通过。

每组 TestClient 测试出现一条 Starlette 关于 httpx 的弃用警告。本次未修改依赖；未来兼容性升级在独立任务处理。

## 5. 用户独立复现

先明确代码来源。当前根工作台没有 python-ai；下列命令应在包含 python-ai 和 web-prototype 的独立仓库或固定快照内运行。Python 虚拟环境须已有 requirements 中的依赖。

```powershell
# 给每次验收一个新目录，不连接已有学习数据。
$AuditRoot = Join-Path (Get-Location) ('.verification/harness-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $AuditRoot | Out-Null
$Python = (Resolve-Path 'python-ai/.venv/Scripts/python.exe').Path
& $Python -m pip check
npm.cmd --prefix web-prototype run build
& ./web-prototype/deploy/prepare.ps1 -PythonProject (Resolve-Path python-ai).Path -OutputZip (Join-Path $AuditRoot 'backend.zip')
Expand-Archive -LiteralPath (Join-Path $AuditRoot 'backend.zip') -DestinationPath (Join-Path $AuditRoot 'package')
$env:PYTHONPATH = Join-Path $AuditRoot 'package/server'
$env:AI_WEB_DATA_DIR = Join-Path $AuditRoot 'adapter'
$env:PYTHONUTF8 = '1'
$Report = Join-Path $AuditRoot 'web-results.xml'
& $Python -m pytest -q web-prototype/deploy/test_web_trial.py "--junitxml=$Report"
```

如果使用固定归档快照而没有自己的 `.venv`，将 `$Python` 指向已按相应 requirements 配置的绝对解释器路径。不要从测试文件目录绕开打包步骤直接导入另一个 checkout 的 backend。

验证 PR #13 的方式：先确认 main/head 与上文 SHA 一致，在现有 GitHub 关联仓库用 `git archive <SHA>` 导出独立目录，分别按上述步骤打包和运行。无需切换正在开发的分支或合并 PR。

开发副本中的真实账号联调使用已有脚本：

```powershell
# 在 artifacts/zhixueban-development 或相同版本的仓库内。
$env:JAVA_HOME = 'D:\Android Studio\jbr' # 改为本机 JDK 21 路径
& ./tools/test-web-account.ps1
```

它使用随机回环端口、内存 H2 和临时 SQLite，真实启动 Java 认证服务并验证 60 秒过期、注销和账号绑定；末尾会停止它自己启动的服务。测试可能超过一分钟。脚本不存在的版本不能凭空调用，应先核对选定分支。

不需要为了跑权限回归启动模型；这里的固定模型响应仅用于权限/事务测试。真实 Qwen 质量验收应按既有 ZH-06 手册单独执行并人工核对。

## 6. 未验收边界

- 未执行真实 Qwen/Ollama 推理、视觉空响应复验、各格式真实生成或新的人工质量评分。
- 未重新跑 20 请求评测；学习副本历史结果与当前 Web 开发副本不能混用。
- 未连接手机、安装 APK、执行 Android 仪器测试；历史数据库测试失败不因 JVM 测试通过而自动解决。
- 未验证生产 HTTPS 反代、真实多实例、跨设备学习同步、数据库增量迁移或还原演练。
- 未对全部堆叠 PR 做逐行安全审查、试合并和集成运行；没有修改远程 Issue/PR 或合并 main。
- 本次规范中的 Harness 包、模型工具协议、上下文压缩、长期记忆与 GoalEvaluator 都是设计，未作为功能实现或测试通过。

## 7. 最终补测

### Android / Java 强制重跑

`--rerun` 对两个测试任务实际生效，Gradle 返回 BUILD SUCCESSFUL；没有对已缓存的结果重复计数。

- 当前工作台 Android JVM：**13 tests，0 failures，0 errors，0 skipped**；XML 最后写入为 2026-11-25 20:09:42。
- 当前工作台 Java 认证：**8 tests，0 failures，0 errors，0 skipped**；XML 最后写入为 2026-11-25 20:10:20。
- 本次重新执行的是本机已有修改状态；没有声称干净 GitHub main 或 Android 真机也获得相同结果。

### 真实 Java 账号联调补测

在开发副本运行既有 `tools/test-web-account.ps1`，使用临时内存 H2、随机回环端口、真实 Java HTTP 和临时 SQLite。脚本正常退出（exit code 0），末尾回收自己创建的认证服务。

- 打包 Web/账号 API：**27 passed，1 warning，90.99 秒，无跳过**。此前 3 个跳过项均在这一轮实际执行，覆盖真实注册/登录、账号切换、60 秒过期和注销后的访问拒绝。
- 账号解析与只读 Agent API 子集：**22 passed，1 warning，3.84 秒**。这是上文 40 项中的重复子集，不与 40 相加。
- 脚本的 Gradle 构建/认证测试检查成功但显示 UP-TO-DATE，不作为额外新运行计数。当前工作台的 8 项认证强制重跑与此开发副本的真实 HTTP 测试分别记录，不混为同一提交。
- 本次没有补测生产 HTTPS、反向代理或 Android 登录界面；不能把临时账号服务联调扩大为正式部署验收。

### 本轮交付检查

只新增/更新三份文档：`docs/AGENT_HARNESS_SPEC.md`、`docs/AGENT_ROADMAP.md` 和本记录。两个独立开发/学习副本的工作树在运行后均保持干净；没有提交或推送。

检查文档的代码围栏配对、相对本地链接和尾随空白；正式交付不保留“等待补测”的结果占位。主分支与 ZH-04 的基线没有出现业务断言失败。已定位的运行问题是首次沙盒 socketpair 停滞；Starlette 弃用警告仍保留。
