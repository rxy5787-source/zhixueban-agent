# 知学伴 Agent Harness 开发规范与架构审计

历史架构审计日期：2026-11-25（Asia/Shanghai）。用户随后已授权持续完成 Phase 01～10；本地集成分支为 `codex/agent-harness`，当前事实优先读 [AGENT_PROGRESS.md](AGENT_PROGRESS.md) 与 [AGENT_EVALUATION.md](AGENT_EVALUATION.md)。以下审计保留版本边界，后续实现状态以持续记录为准；不合并或推送远程 main。

## 1. 结论与版本边界

知学伴已经有可复用的资料解析、模型生成、质量检查、任务存储、账号服务和学习算法。适合在现有 Python 服务内逐步增加薄层 Harness，继续让稳定流程承担上传、判分、归档和 BKT 更新，让模型在有边界的工具集合内决定需要判断的下一步。无需引入付费 API、另建账号系统、另建任务队列或重写客户端。

**目前不能宣称已完成工程化 Agent Harness。** GitHub 主分支仍以固定 Worker 为核心；实验分支已有有界 Skill 调度及学习规划等机制，其中本次实际读取的两个 Planner 通过代码条件分支选择步骤，不是通用的模型工具调用循环。

### 1.1 实际存在的仓库与副本

- 当前工作台 `D:\adaptivequizapp`：Git HEAD `d01928d`，origin 指向 Gitee，存在大量原有未提交修改；根目录没有 `python-ai/`。本次规范与路线图保存在这里，不把它误称为 GitHub 主分支。
- GitHub 独立项目：[`rxy5787-source/zhixueban-agent`](https://github.com/rxy5787-source/zhixueban-agent)。本次在线核对的 `main` 为 `d76e9e8d675ab4df5e7e4ab39ef44e1eea62e825`。使用 Git 归档出的固定快照执行测试，没有切换或合并工作分支。
- `artifacts/zhixueban-development/`：本机 Web/账号开发副本，分支 `codex/web-account-session`，HEAD `d7ae77a07b4114674df147a334827dbbca384a18`；origin 指向本机导出仓库。此副本包含账号学习空间、Web 注册登录、只读 Agent 查询接口等额外代码，**不能算作 main 已有功能**。
- `artifacts/zhixueban-agent-learning/`：学习与评测副本，分支 `codex/agent-learning-week1`，HEAD `05a42c69279da9b9805b08fda564873575bb5162`；origin 指向上述 GitHub。已有 `agent_runtime.py`、学习 Planner、评测工具，不能把整份目录复制回 main。
- 原独立 Python 项目仍在 `E:\GraduationProject\AdaptiveQuestionAI`。根工作台历史启动脚本默认使用此目录；GitHub 项目启动脚本和 CI 使用仓库内 `python-ai/`。后续每条证据必须记录实际 Python 源码目录与提交，避免测到另一版服务。

除工作台说明与本次文档路径外，下文的 `python-ai/`、`web-prototype/`、`auth-server/`、`app/` 等均是**独立 GitHub 仓库内的相对路径**。当前工作台不应凭文档直接新建一套重复 Python 项目。实施前先在选定的现有副本核对基础提交。

### 1.2 GitHub 任务状态

- ZH-01 / Issue #2、ZH-02 / #3、ZH-03 / #4：在线核对均已关闭；PR #1、#12 已合入 main。部分旧 README、Issue 正文仍留有“待合入”字样，应以实际 PR 合并状态与提交为准。
- **ZH-04 / Issue #5：仍开放，PR #13 已有实现分支及通过的 CI，尚未合入 main。** 本次复测见第 4 节。不另建“空间隔离”Issue，不直接关闭原任务。
- ZH-05～ZH-10：分别沿用 Issues #6～#11；新路线拆成这些任务下的验收子阶段，不另建相同主题的编号。
- Issue #32 是长期接力入口。其内容包含多条堆叠草稿 PR 的历史，不能代替当前代码和合并状态。
- PR #14、#16、#17、#19～#24 等包含 Agent/学习规划/评测方向的既有实现；PR #26/#27 与后续 #37～#48 包含计时、并发和集成候选；#49～#51 是另一组 Web 改动。审计时仍存在未合并分支。本次仅核查其元数据及本地实际读取的模块，**没有逐行审查全部 PR 或完成跨分支集成验收**。

## 2. 当前架构：可以复用什么

### 2.1 客户端与身份

- Android：Java 学习业务与传统 View、Kotlin Compose 界面、SQLite。`MainActivity.java`、`learning/LearningStore.java`、`learning/LearningEngine.java` 和 `ai/`、`auth/` 继续保留。不是全项目已经改成 Compose。
- Android 学习库版本 4，包含题库、知识点、题目关联、作答、状态轨迹、复习任务和 AI 来源；追加迁移保留旧数据。既有导入、备份、账号空间与离线学习能力继续复用。
- Web：React、TypeScript、Vite；已有资料上传、任务进度、学习对话、题目归档、作答与知识点统计。部署入口和基础适配器是不同的边界。
- Java 账号服务：Spring Boot、JDBC，默认文件 H2，也有 PostgreSQL 驱动配置。实际密码使用带盐 **PBKDF2-HMAC-SHA256，600,000 次迭代**；会话为 32 字节随机数编码的 Bearer 令牌，服务端保存令牌摘要和有效期。**不是 JWT，也不是 BCrypt**。不为 Harness 更换账号协议。
- Web 试用部署入口 `web-prototype/deploy/web_trial.py` 使用 HMAC 签名、有效期与 HttpOnly Cookie 识别访客，按空间选择独立 SQLite。`Secure` 用于 HTTPS，现有回环预览另有明确例外。Cookie 签名不等于任意客户端提供的空间 ID 都可信。
- 开发副本的账号入口通过 Java `POST /api/auth/learning-space` 获得服务端绑定，使用 `account-spaces/`，访客使用 `spaces/`。账号接口默认关闭。`X-Zhixue-Learner` 用于核对当前页面账号，不能单独证明身份。

### 2.2 资料、模型与持久任务

主链路：

```text
Android Bearer / Web 签名会话
  → 对应 FastAPI 身份入口
  → 校验上传 / 任务请求 / 资源归属
  → SQLite 持久任务及上传回执
  → 现有队列领取 + 独立子进程 Runner
  → multimodal_reader → 知识点提取 → 生成 → 自动复核
  → 事务归档 → 客户端展示 → 实际作答 → 对应学习库 BKT 更新
```

- `backend/main.py` 是 Android Bearer 接口：现有 Java `/api/auth/me` 验证账号；资料、任务等按 owner 查询。
- `backend/web_api.py` 基础适配器为本机用途，不能单独作为公网多用户接口。部署打包的 `backend.patch` 会引入 `ContextVar` 请求空间，`web_trial.py` 负责验证会话并在请求结束后复原上下文。
- `deploy/prepare.ps1` 复制 Python 模块并应用 `backend.patch`、`study_backend.patch`，最终得到 `backend.web_trial` 部署入口。**必须测试打包产物；只测原文件不足以证明实际部署正确。** 暂时保留此流程，后续若消除补丁机制应单独验收。
- `backend/job_store.py` 保存 files、jobs、job_events、model_call 等；`web_content.py`、`web_practice.py` 保存 Web 题库、归档、作答与掌握估计；上传回执、续传另有既有模块。
- `backend/worker.py` 已有领取、独立子进程、取消、checkpoint、恢复状态保护。恢复时运行中任务成为 interrupted，排队任务可以继续；这**不等于任意模型调用能从中间 token 无损续跑**。
- `multimodal_reader.py` 复用 PyMuPDF、python-docx、RapidOCR 和 Qwen-VL；`generate_from_file.py` 与质检模块使用现有本地 Ollama。当前默认文本模型 `qwen3:1.7b`、视觉模型 `qwen3-vl:2b-instruct`。
- 资料处理有页数、图片数、上下文与题量预算。不能把截断输入描述为“整份资料已读完”；需保留实际覆盖范围。
- `file_storage.py` 已拒绝空文件并校验 DOCX 容器等。代码存在不能替代本次各格式真实推理验收。

### 2.3 BKT 与学习记忆现状

- Android `LearningEngine.trace()`：观测后验 → 学习转移，guess 随信心取 0.40 / 0.28 / 0.20，slip=0.10、learn=0.08；保存参数轨迹。模型参数未经过实测校准。
- Web `backend/web_practice.py`：已有 BKT，initial=0.25、guess=0.28、slip=0.10、learn=0.08。`save_session()` 按 sessionId 防止相同提交重复更新；相同 ID 换题目/答案会拒绝。
- 两端目前是**不同学习数据存储和不同参数口径**，没有经本次验证的统一事件同步与冲突处理。不能将其直接合并为一个“全端统一掌握概率”。
- 持久作答、掌握估计和任务状态是已有业务事实；它们还不是可选择、可撤销、可追溯的自然语言长期记忆系统。
- 学习副本 `study_plan_service.py` 从已验证空间中的知识库读取 BKT，`study_skill_planner.py` 区分待诊断、针对薄弱点练习和一般复习。保留这些规则，不让模型编造作答或直接修改 mastery。

### 2.4 明确缺口与风险

1. 缺少主分支内统一的 ToolSpec、调用策略、不可由模型覆盖的 ExecutionContext 与标准 ToolResult。
2. 缺少经过本地 Qwen 实测的模型驱动工具调用协议；现有有界调度不等于已具备这一能力。
3. 缺少统一的 Agent run、步骤账本、版本关联与恢复协议。优先扩展已有 SQLite/Job Store，不并列建立第二套真实任务状态。
4. 缺少按目录发现、按需展开的运行时 Skill 文档、上下文压缩、学习记忆与独立 Goal 验收。Python 注册处理函数和开发者 `.agents/skills` 不是同一种 Skill。
5. `model_call.response` 会保存原始模型响应；错误路径中还有异常文本和原始 stage。它们可能含正文、文件名或路径。私有业务证据与普通运行日志必须区分；ZH-05 尚未实现全链路脱敏、访问和保留期验收。
6. 自动质检存在漏放行历史。学习副本的真实 20 请求评测记录为程序预期行为符合 14/20、正向输出 13/19，人工有效分母为 0，Day 1 未验收。它是另一提交的历史结果，本次未重跑，不能称答案正确率或当前版本质量分数。
7. Qwen-VL 空响应、OCR/图形题、DOCX 的边界与语义正确性不能因安装模型或单条样本通过就宣告解决。本次没有执行新的真实模型推理。
8. 多分支进度、根工作台/原 Python/部署补丁之间存在漂移。统一代码来源和发布证据是进入下一阶段的前提。

## 3. 目标架构与执行契约（均为设计）

```text
既有 Android / Web
    → 既有认证与学习空间解析
    → 既有 Job Store / Worker
         ├─ 固定工作流：解析、判分、事务归档、BKT 更新
         └─ 可选 Agent Harness
             → ContextBuilder + Skill 目录
             → 本地 Ollama ModelAdapter：提出结构化动作
             → 参数校验 / 授权 / 预算 / 前置条件
             → Tool Registry：复用既有业务处理函数
             → 结果验证 / 事务提交 / 步骤账本
             → 把结构化结果交还模型，继续或提出停止
             → 独立 GoalEvaluator 检查验收证据
```

### 3.1 模型、Harness 与固定工作流的分工

- 模型：解释目标、选择允许的动作、提出所需资料或诊断、参考工具结果调整计划。不能决定自己的账号、文件系统根、数据库连接、权限或执行预算。
- Harness：验证身份与作用域，限制工具，执行与取消，保存状态，记录安全日志，校验结果。模型输出始终视为未受信输入。
- 固定工作流：上传校验、归属查询、题目判分、提交去重、事务归档、BKT 数值更新等继续用确定性代码。生成与复核仍复用现有函数。
- 禁止给教育 Agent 通用 shell、任意 Python 执行、任意 SQL、任意本机路径或任意 URL 请求。默认仅允许业务工具；不复制教程的 bash 工具。
- 初期单进程协调、单模型受控队列；不新增 LangChain/LangGraph、Redis/Celery、向量库、多 Agent 团队或 MCP 服务来凑机制。以后有业务证据才单独提出依赖。

### 3.2 标准 Tool Registry

建议在既有 Python 服务内新增 `backend/harness/` 包，文件名是后续设计，**本次均未创建**。

`ToolSpec` 至少描述：name、version、说明、Pydantic 输入/输出 schema、所需 capability、读写属性、超时、输入/输出预算、幂等要求、结果验证器和执行函数。复用已有依赖。

`ExecutionContext` 由认证后的服务器建立：principal/space 引用、当前 job/run、取消信号、预算、可用资源集合。调用参数中不允许出现可覆盖的 owner、space 路径、连接字符串或令牌。即使参数 schema 合法，也要逐资源检查归属。

首批候选工具只适配已有能力：

- `read_material`：通过当前空间的 materialId 读取有界片段和覆盖说明。
- `retrieve_evidence`：返回同空间资料中的原文片段、定位和证据 ID。
- `read_learning_progress`：只读现有知识点状态、观察数和模型版本。
- `generate_practice` / `review_candidates`：复用 Qwen 生成与现有结构、独立解答和证据校验。
- `archive_validated_questions`：仅接收已验证候选的服务器引用；写入前检查知识库、审核状态与幂等键，复用现有事务归档。

不要把这些名字当作已存在接口。ToolResult 统一包含 status（ok/rejected/retryable_error/fatal_error）、受限数据或 artifact 引用、稳定 errorCode、可重试性和验证摘要；不把异常原文作为模型或客户端错误。

### 3.3 调用、恢复与验收规则

1. 加载已验证空间、目标、允许工具和当前状态；构建有界上下文。
2. ModelAdapter 请求本地 Ollama，返回 `call_tool / ask_user / finish` 之一。
3. 严格校验 JSON、动作枚举、工具名、参数、调用数量与长度。可按模型实测采用原生 tool_calls 或 JSON schema 动作；不依赖未验证的模型能力。
4. 未知工具、额外权限字段、提示注入或非法参数都不执行；不得退回 eval/exec 或静默降级为无校验执行。
5. Harness 重新鉴权、检查资源归属/取消/预算；写操作沿用原流程的授权范围并检查幂等键。现有用户提交后自动归档不新增逐步确认；超出任务范围的删除、覆盖或恢复需有对应的明确授权，不能采信模型自报“用户同意”。Hook 可做观测，不得绕开必经授权。
6. 保存步骤已准备/执行中/已验证等账本信息，运行工具，限制耗时和结果大小。写入与归档尽量复用同一数据库事务。
7. 校验输出，再保存结果、版本和证据引用；反馈给模型。重复恢复先查已经提交的副作用，不能仅靠“调用前写了日志”声称 exactly-once。
8. 模型提出 finish 后，阶段 10 的独立验收器检查业务证据。工具未完成、候选未达标或题数不足时不能成功；预算耗尽、取消、服务故障要返回真实状态。

未来 run 记录需关联原 jobId、space、目标、模型/提示/工具/schema/流程版本、输入内容摘要、步骤、检查结果和终态。幂等键包括空间、原任务、操作及输入版本；跨空间不可共享结果缓存。模型请求期间不要持有长 SQLite 写事务。

### 3.4 权限、数据与隐私最低要求

- deny by default：没有可验证身份、作用域或已授权资源就拒绝；客户端或模型传入 ID 不能充当授权。
- 沿用现有角色/会话，不创建“Agent 超级用户”；只读学习计划默认不获得写库能力。
- Tool 调用与 HTTP 入口同时限制路径穿越、符号链接逃逸及不属于当前空间的资源。解析上传不执行文档宏、脚本或内容中的指令。
- 资料正文、OCR、引用、Skill 文本都不能更改系统权限。Skill 只从服务器受控目录加载，学生上传的文件不成为可执行 Skill。
- 取消后停止后续生成和写入；重启恢复重新验证可用权限。长期任务的会话过期与继续执行策略需明确，写入不能凭旧上下文永久授权。
- 普通观测事件仅记录脱敏关联 ID、操作/版本、结果类别、耗时、计数、验证状态；不记录 Cookie、Bearer、密码、正文、提示、模型原文、文件名/路径或异常消息。
- 原始质量证据保存在当前空间受控存储，单独规定访问、保留期与删除，公开评测只使用经确认可公开的样本。
- BKT 真值是已提交的作答事件及确定性更新；模型摘要、用户偏好和临时上下文不能覆盖它。

## 4. ZH-04 检查结论

原任务：[Issue #5](https://github.com/rxy5787-source/zhixueban-agent/issues/5)。现有实现：[PR #13](https://github.com/rxy5787-source/zhixueban-agent/pull/13)，head `abf18617d197d3788b6909b0e3bb19633109a110`。

与本次 main 比较，PR #13 只修改 `docs/AGENT_ROADMAP.md` 和 `web-prototype/deploy/test_web_trial.py`，没有新增一套身份实现。其价值是补上现有空间隔离的实际上传、归档和作答回归。

本次核对的真实执行链是：签名 Cookie → `existing_space()` → 当前空间 Store → `request_store_override` → 资源查询 / `web_tasks` 关联 → 当前空间 SQLite。owner 常量 `web-local` 本身不构成访客隔离，数据库选择才是关键边界；未来 Tool 不能直接取全局 Store。

PR 的增强用例使用两个访客、同名知识库、各自的资料与任务，固定模型响应但实际走上传、Runner、事务归档和作答。双向拒绝跨空间的任务/题目/上传回执查询、保存、提交答案、追问和移除资料，并确认任务列表、题库和 BKT 记录只含自己的数据。

实际结果：

- 固定 main 快照：**13 passed**。
- PR #13 固定快照：**14 passed**，含新增隔离用例。
- 在线核对 [PR #13 CI](https://github.com/rxy5787-source/zhixueban-agent/actions/runs/43390006261)：completed / success，head 与上述 SHA 相同。
- 本机 Web 账号开发副本：首次打包接口 **24 passed，3 skipped**；随后使用现有脚本启动隔离的真实 Java 服务补测，**27 passed，无跳过**，覆盖实际登录、60 秒过期、注销与账号隔离。身份/只读 Agent/覆盖/质检另有 **40 passed**；脚本重复验证的其中 22 项不额外计数。

**结论：原 PR 的访客空间回归在固定版本复测通过；ZH-04 尚未完成 main 集成验收。** 不将其升级为完整多账号、全客户端、所有 Agent 工具的权限证明。

后续在原 Issue 继续补充、不要另开重复任务：

- 选定最终集成提交，保留 PR #13 的回归，并核对与 Web/账号/Agent 分支的重叠改动。
- 覆盖伪造/篡改/过期/撤销凭证、账号切换、重复资源 ID、读写越权、取消/重试、下载、续传、恢复后的跨空间访问。
- 覆盖未来 Tool 的直接调用和模型注入 space/owner/path；保证未授权调用不触发处理函数，也无数据库副作用。
- 使用真实 Java 测试实例验证 Web 账号绑定与失效关闭；访客隔离与账号绑定分别报告。
- 集成后在 main 对应提交跑打包回归，记录 CI 和本机证据，再判断是否关闭 Issue。合并仍按用户授权执行，本次未合并。

## 5. learn-claude-code s01–s17 与教育业务对应

参考仓库当前根目录的 17 章路线；不能把旧 `agents/`、`docs/` 的 12 课编号混用。本次核对 main 为 [`448c75bb596917ad196cc1fb7558f459c5c50fdd`](https://github.com/shareAI-lab/learn-claude-code/commit/448c75bb596917ad196cc1fb7558f459c5c50fdd)。以下是迁移设计，不是已经实现的清单。

- **s01 Agent Loop**：学习要求 → 模型动作 → 工具结果 → 再决策。有步数、时长和取消约束。现有固定 Worker 保留；模型驱动版待实测。
- **s02 Tool Use**：注册解析、证据读取、生成、复核等业务工具。复用处理函数，不开放 shell；已有 SkillRegistry 是候选，不等同统一 ToolSpec。
- **s03 Permission**：每次执行前校验身份、空间、资源和能力。基于 ZH-04 继续完善，拒绝优先，模型无法扩大权限。
- **s04 Hooks**：在工具前后加入安全事件、计时和验证。必经授权不是可选插件，不允许 Hook 关闭校验。
- **s05 TodoWrite**：把用户的“做一组针对弱点的练习”分成可解释步骤；已有规则计划继续复用，计划本身不代表已执行。
- **s06 Subagent**：暂缓。将来若需要分离讲解与审题上下文，可使用独立模型请求；消息隔离不是文件、进程或账号安全隔离。
- **s07 Skill Loading**：先加载学习 Skill 的名称、适用范围、契约，选中后才读完整指导。现有 Python skill handler 不是按需加载 SKILL.md 的实现。
- **s08 Context Compact**：先限制工具结果，再以有权限的 artifact 引用替换旧大结果，必要时压缩历史。保留当前要求、权限、未完成工具配对、证据与已提交副作用。
- **s09 Memory**：按用户/知识库选择学习偏好、可靠错因与证据；提取、去重、失效和删除。BKT 由原算法维护，不让记忆摘要写回掌握概率。
- **s10 Task System**：在已有 SQLite 任务和步骤记录上增加计划依赖与恢复依据，不照搬文件任务系统建第二个事实源。
- **s11 Background Tasks**：复用已有独立子进程和受控队列；Agent 等待/查询同一 job，取消与重启仍能找到原结果。后台启动不代表完成。
- **s12 Cron Scheduler**：暂缓服务端定时 Agent。已有复习到期是业务调度，不等同持续后台模型代理；有实际提醒需求后再定义时区、授权和去重。
- **s13 Agent Teams**：暂缓多 Agent、邮箱与 worktree 系统。本地小模型和当前业务没有足够证据支持这些成本。
- **s14 MCP Plugin**：暂缓。先完善内部业务工具；未来确有外部教育资源接入时，再把 MCP 工具纳入同一权限与版本控制。
- **s15 Integrated Harness**：单一入口装配已有鉴权、工具、状态和验证；客户端选用同一服务契约，不让每端复制一套 Harness。
- **s16 Workflow Runtime**：固定生成/复核/归档用代码规定顺序，保留 checkpoint 与恢复。只借鉴编排和日志思想，不复制任意脚本执行或多 Agent 编排。
- **s17 Goal Loop**：模型提出停止，独立验收器检查请求题量、知识点覆盖、原文证据、质检和目标库归档。工作流结束与用户目标达成都需分别判断；失败、预算耗尽或验收器故障不能标成功。

章节原文：[s01–s17 总目录](https://github.com/shareAI-lab/learn-claude-code/tree/448c75bb596917ad196cc1fb7558f459c5c50fdd)，重点参考 [s03](https://github.com/shareAI-lab/learn-claude-code/tree/448c75bb596917ad196cc1fb7558f459c5c50fdd/s03_permission)、[s07](https://github.com/shareAI-lab/learn-claude-code/tree/448c75bb596917ad196cc1fb7558f459c5c50fdd/s07_skill_loading)、[s16](https://github.com/shareAI-lab/learn-claude-code/tree/448c75bb596917ad196cc1fb7558f459c5c50fdd/s16_workflow_runtime)、[s17](https://github.com/shareAI-lab/learn-claude-code/tree/448c75bb596917ad196cc1fb7558f459c5c50fdd/s17_goal_loop)。

## 6. 分阶段实施、文件、风险与验收

下述新增文件都是**候选路径，不是本次创建清单**；实施时先对照已有 PR，已有合适模块就修改/扩展，不另建平行实现。每阶段一次只推进一个可验收子目标，测试失败先定位，不能顺带重构下一阶段。

### 阶段 0：审计与规范（本次）

- 业务问题：避免重复开发、混淆分支功能和忽略现有权限边界。
- 文件：本规范、`docs/AGENT_ROADMAP.md`、本次审计证据；不改产品代码和依赖。
- 验收：记录各实际版本、原 Issue 映射、ZH-04 差异、运行的测试与未验证范围，给出后续准入条件。
- 当前状态：文档交付；具体测试结果及限制见第 7 节和证据文件。

### 阶段 1：工程基线、权限隔离与日志

- 沿用 ZH-01～05（Issues #2～#6），优先在原 ZH-04 中完成选定版本的集成验收，再推进 ZH-05 子阶段。
- 复用/修改：`deploy/web_trial.py`、`backend/main.py`、`account_space.py`（选定分支已有时）、`job_store.py`、`worker.py`、部署打包和现有测试。候选新增 `backend/harness/context.py`、`permissions.py`、`events.py`，仅在现有边界明确后提取。
- 依赖：锁定仓库/提交/部署入口；无新服务依赖。
- 风险：ContextVar 泄漏、全局 Store 回退、账号/访客混绑、日志泄露、迁移错误。
- 测试：双访客/双账号正反向访问，伪造/过期身份、并发请求、相同资源 ID、任务重启和日志敏感标记扫描。
- 验收：有效用户原业务可用；所有非法身份/跨空间访问均无副作用；错误分类和耗时可关联但不泄露内容；打包产物、CI 与本机版本一致。

### 阶段 2：Tool Registry 与标准工具接口

- 沿用 ZH-08 / Issue #9；先审查 PR #14/#17 的 Registry。
- 复用：`agent_runtime.py` 的注册与契约思想（分支代码），现有解析、生成、复核、归档函数。候选新增 `harness/tools.py`、`tool_registry.py`、`tool_adapters.py` 和契约测试。
- 依赖：阶段 1 的受信上下文；使用既有 Pydantic，不新增 Agent 框架。
- 风险：工具适配器绕开归属检查、异常契约不一致、重复归档。
- 测试：schema 错误、未知工具、无权限、超时、取消、输出无效、重复执行；使用固定候选验证真实 SQLite 事务。
- 验收：所有入口经过同一授权与结果验证；每个工具可独立验证；原固定流程输出契约不变。

### 阶段 3：Agent Loop 与本地模型适配器

- 沿用 ZH-09 / Issue #10；不把已有条件路由改名当作交付。
- 候选新增 `harness/model_adapter.py`、`loop.py`；修改 `config.py`、既有可选运行入口和打包白名单。Ollama 保持本机。
- 依赖：阶段 2。先用契约替身，再实测 qwen3:1.7b 的工具选择或结构化动作，不承诺模型支持尚未测试的协议。
- 风险：坏 JSON、未知工具、循环、资料提示注入、模型超时、重复写入。
- 测试：正常调用→读结果→再决策、拒绝错误动作、ask_user、finish、步数/总时长/输出上限和取消；至少一条真实 Qwen 多步任务，记录实际模型标签和版本。
- 验收：模型确实根据工具结果选择后续动作；非法动作零执行；失败/部分结果明确；原固定流程可继续独立使用。

### 阶段 4：任务规划、持久化与恢复

- 在 ZH-03 / #4 的既有能力和 ZH-09 / #10 下扩展验收，不重开恢复任务。
- 修改：`job_store.py`、`worker.py`、`harness/loop.py`；候选新增 `harness/run_store.py`、`plans.py` 和步骤账本增量迁移。复用原 jobId、取消与重试语义。
- 依赖：阶段 3；SQLite 事务、版本化 schema、现有队列。
- 风险：副作用已提交但步骤未标记、陈旧 worker 回写、旧流程版本被新代码错误续跑。
- 测试：在调用前、调用后、事务提交后、结果反馈前强制停止；同 run 恢复、并发恢复、过期权限和输入版本变更。
- 验收：已提交归档不重复，原证据保留；不安全续跑明确 interrupted/需重试，不伪造无损恢复；所有计划依赖可解释。

### 阶段 5：按需加载的学习 Skill

- 沿用 ZH-08/#9、ZH-09/#10；复用已有学习 Planner，不与开发者 Codex Skill 混用。
- 候选新增 `harness/skill_loader.py`、`python-ai/skills/<学习场景>/SKILL.md`；修改上下文构造。只有职责明确时才创建必要的学习 Skill。
- 依赖：阶段 2～4；先用受控目录和简单元数据，不加包市场或动态执行。
- 风险：上传资料冒充 Skill、Skill 获得新权限、一次加载全部说明、热更新破坏恢复。
- 测试：目录发现、按名加载、未知/越界/非法元数据、版本固定和上下文大小。
- 验收：只加载所选 Skill；文档不能授权新工具；恢复使用相同 Skill 版本。

### 阶段 6：上下文管理

- 沿用 ZH-09/#10；候选新增 `harness/context_builder.py`、`context_compaction.py`，复用当前空间资料片段与安全 artifact 引用。
- 依赖：阶段 4～5；按本地模型上下文配置预算。
- 风险：压缩丢失用户要求、孤立工具结果、忘记已提交写操作、缓存跨空间泄漏。
- 测试：长 OCR、巨大工具结果、多轮对话、压缩前后任务/证据/工具配对、上下文超限一次受控恢复。
- 验收：预算可测，关键目标和权限不能压缩覆盖；大结果可在授权后重取；不能因摘要声称不存在的证据。

### 阶段 7：学习记忆与 BKT 集成

- 沿用 ZH-09/#10，复用 PR #16/#17/#19 的弱点与学习计划；不重新实现 BKT。
- 修改：`web_practice.py`、`study_plan_service.py`（选定分支已有时）；候选新增 `harness/learning_memory.py`。Android `LearningEngine`、`LearningStore` 此阶段默认不改。
- 依赖：阶段 1/4/6；先只读同一 Web 学习空间。跨端同步须另行明确作答事件 ID、知识点 ID、算法版本与唯一更新责任，不默默迁移。
- 风险：稀疏证据误判薄弱、无依据记忆、跨账号召回、重复 BKT 更新。
- 测试：无记录/少量记录/有证据薄弱点、记忆版本/过期/删除、事务回滚、幂等作答、空间隔离。
- 验收：学习建议引用实际观察数和模型版本；LLM 不写 mastery；Android 离线学习继续可用；未知学习效果标待验证。

### 阶段 8：Evaluation 与可观测系统

- 沿用 ZH-05/#6、ZH-06/#7、ZH-07/#8；复用已有计时/回放分支和 `evaluation/zh06.py`，不再建第二份 20 例题单。
- 修改：现有评测脚本、测试、打包与 CI、质量报告；按需增加工具执行契约评测，复用前述安全 events。
- 依赖：观测基线在阶段 1 先落地，固定评测题单从首个行为改动开始保留；此阶段完善对照与发布门槛，而非到这时才开始测试。
- 风险：把 mock CI 当模型质量、自动保留比例当正确率、评测资料泄漏、统计分母选择性排除失败。
- 测试：契约/权限/恢复确定性评测，固定真实模型题单、人工盲审、缺依据负例；1/3/5 提交的真实队列容量，生成与排队分别计时。
- 验收：报告提交/模型/输入/实际分母、拒绝与失败原因、中位/P95（样本足够时）及人工未审数量；未达阈值不能发布为质量达标。

### 阶段 9：Agent 与固定工作流集成

- 沿用 ZH-08/#9、ZH-09/#10；保留 ZH-03 回归。
- 修改：既有 Worker/路由与部署入口；候选新增 `harness/workflows.py`。客户端只在确需展示计划/确认/状态时最小修改现有 API 客户端，不重做导航或复制业务。
- 依赖：阶段 1～8 的已验证组件。
- 风险：双队列、双重状态、双重 BKT、默认切到实验路径、确认后条件变化。
- 测试：同一业务分别走固定与 Agent 路径，对比权限、归档、判分和报告；确认失效、重启、取消、回滚开关。
- 验收：固定路径保留；流程可恢复；实验路径默认关闭或明确选择；一份作答只更新一次，客户端不依赖模型内部文本驱动状态。

### 阶段 10：Goal Loop 与独立目标验收

- 沿用 ZH-09/#10，将可演示成果纳入 ZH-10/#11。现在不创建新 Goal Issue 或运行时后台目标。
- 候选新增 `harness/goals.py`、`goal_evaluator.py`，修改 Loop 停止边界和持久状态。
- 依赖：阶段 4/8/9。先用确定性规则判断数量、覆盖、归档等；语义判断可另起本地模型请求或人工复核，不复用执行者的成功自述。
- 风险：同一小模型共同偏差、无穷重试、无证据成功、评价器故障、无结果时仍写报告。
- 测试：提前 finish、题数/覆盖不足、缺图/证据不符、已取消任务、未完成后台工具、预算耗尽、验收器不可用及用户停止。
- 验收：只有独立证据满足所有目标才 succeeded；其余明确 partial/failed/cancelled/interrupted/需用户介入等状态，并保存原因。步数、总时长和重试上限可配置、可停止。

## 7. 本次测试与未完成验证

详细命令、固定 SHA、环境、结果及故障定位见 [审计测试记录](evidence/agent-harness-audit-20261125.md)。

- 开发副本 Python 3.12.3，`pip check` 通过；Node.js v24.10.0、npm 11.6.1，Web `npm run build` 通过。
- 固定 main 的打包 Web API 13 项通过；固定 ZH-04 的打包 Web API 14 项通过。
- 开发副本打包 Web/账号 API：首次 24 项通过、3 项跳过；使用隔离真实账号服务补测后 **27 项全部通过**。4 组 Python 权限/覆盖/质检测试 **40 项通过**；重复执行的子集不累加。
- 学习副本 Registry/Planner/弱点测试 48 项通过，使用确定性测试，不代表真实模型 Agent 能力。
- 各 TestClient 组均有 1 条 Starlette/httpx 弃用警告。本次未为消除警告升级依赖。
- 沙盒首次运行在 Windows asyncio 的 `socketpair → accept` 停滞；手动终止后，在本机隔离环境复测通过。不是业务断言失败，也不能把中断运行算通过。
- Android JVM 13 项、Java 账号 8 项强制重跑通过；首轮 UP-TO-DATE 结果没有当作新测试执行。Android 真机/仪器测试、HTTPS 反向代理、多实例与数据库迁移、真实模型质量和完整跨端学习闭环本次未验收。

**下一阶段准入**：先选定单一集成基础提交，将现有 ZH-04 回归纳入该基线，明确账号联调及现有失败/跳过项的处置，再在原 Issue 下推进最小权限/日志子阶段。本次不自动开始阶段 1 运行时代码。

## 8. 开发纪律与每次交付模板

1. 一个子阶段对应现有 Issue 的明确验收项，代码审查前注明 base/head 与依赖 PR；不把所有实验分支合并成一轮工作。
2. 每次先跑相关已有基线。失败先记录复现、范围、证据和原因，必要的最小修复单独说明；不以重构掩盖失败。
3. 优先适配已有模块；引入新框架、数据库、后台调度或外部服务前，要有实际需求与验证收益。默认本地 Ollama，无必付费 API。
4. 不删除旧功能、旧学习证据或失败任务；数据库仅增量迁移并验证恢复；禁止用模拟数据标为真实生成或真实掌握结果。
5. 每次交付明确：业务问题、对应教程机制、修改文件、执行原理、用户独立测试步骤、实际结果、跳过/未做验证及技术说明。阶段验收后才启动下一阶段。
6. 未经明确授权不合并 main；只读审计不修改 GitHub Issue 状态或向他人发送消息。本次未创建重复 Issue。

本阶段技术要点：Harness 与模型的职责、固定工作流与 Agent Loop 的区别、认证与逐资源授权、Cookie 签名与随机 Bearer 令牌的区别、ContextVar 的请求隔离、SQLite 事务与幂等、两端 BKT 的数据边界、自动质检与真实质量评测的区别、工作流结束与 Goal 验收的区别。
