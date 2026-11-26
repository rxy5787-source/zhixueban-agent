# Phase 01 工程基线证据

日期：2026-11-26，Asia/Shanghai。代码在本地 `codex/agent-harness`，基于 `d7ae77a`；未发布到 GitHub main。

## 改动与原理

- 复用 ZH-04 的访客与账号空间回归。新增 timing 只读接口先经过原身份中间件，再由 task() 校验当前 Store 和 web_tasks 关联；没有通过客户端路径选择数据库。
- 兼容移植 PR #26/#37 的 job_timing.py。领取事件与状态写入同一事务；归档回调计时和结果共同提交，失败共同回滚。未知旧数据不填虚假耗时。
- 普通观测日志采用固定字段与枚举；请求 ID 由服务器随机生成，不反射客户端标识。内部错误和 422 不回显异常/原始输入。原 model_call 属于空间内私有证据，不对普通日志展开。
- 关闭本地预览的 URL access log；保留阶段、模型元数据和归档耗时。没有更改 UI、账号协议或 BKT 公式。
- 新增本地/CI验收入口，打包接口与源码单测分进程运行，保留原取消、重启和权限断言。

## 真实模型冒烟

沿用现有 smoke_trial.py、自编 SQL 短资料、本机 Ollama 0.40.16、qwen3:1.7b，不使用替身或模板题。

首轮任务 `bacde910064a4a02b2ac6eac953b7cdc`：两次真实生成与两次复核发生，但题干/正确选项都未保留指定术语 WHERE，原覆盖门正确拒绝；0 题归档，冒烟失败。该失败没有删除，也没有放松原门槛。

第 1 轮修复：命题提示保留完整用户要求，明确作用题应点名、识别题应使用同类术语选项。随后真实任务 `8fc4efc1ea354700b7183156a9d8d6a3` succeeded，1 题归档。

核对样本：

- 题干：下列哪项描述了 WHERE 子句的作用？
- 正确选项 A：按条件筛选原始数据行。
- 其他选项：按条件排序／更新／统计数据行。
- 原文与解析：WHERE 按条件筛选原始数据行。
- 数据库记录 generation 和 batch_review 均来自 qwen3:1.7b，Ollama total_duration 分别约 20.420 秒、5.070 秒；任务终态墙钟约 33.861 秒。单样本不能当平均速度。
- 实际 HTTP 提交答案后，answered=1、correct=1、observations=1、mastery≈0.555862（初始 0.25）。脚本确认另一访客无权读任务、题库和学习历史。
- 普通 uvicorn 日志中检查不到资料名 sql-study、原文 WHERE/按条件筛选、Bearer 或 Cookie；可见固定阶段、任务 ID、模型耗时和归档 3ms。它不是完整隐私证明，注入标记另由回归测试验证。

本次对照原文核对的是这个公开短资料样本，不是 20 例人工质量评分，也不证明知识追踪准确性。

## 复测命令

```powershell
& ./tools/test-agent-harness.ps1 -WithAccounts -JavaHome 'D:\Android Studio\jbr'
```

真实冒烟使用当前打包 server、Web dist、自编 SQL 文件和独立输出目录，示例参数：

```powershell
& ./python-ai/.venv/Scripts/python.exe -X utf8 web-prototype/deploy/smoke_trial.py --server <本次打包目录/server> --frontend web-prototype/dist --material web-prototype/test-materials/SQL短文本资料.txt --output <新的隔离输出目录> --port 18361
```

原失败及成功的原始 SQLite/日志分别保留在 `.verification/harness-phase01-real-20261126/` 和 `.verification/harness-phase01-real-scope-fix1-20261126/`，均被忽略，不入源码提交。

## 已定位问题

1. 打包补丁原上下文包含被修改的 Worker 异常日志行；缩小到稳定上下文后恢复，不删除学习对话功能。
2. 初版测试脚本混合收集源码与部署测试，Windows spawn 导入源码 backend，取消用例失败。分进程后原断言通过；首轮 70 pass / 1 fail 保留为失败记录。
3. 新增原要求保留测试发现“用英文出”被误判为考点。加长资料未解决；任务诊断定位后修复数量指令语言前缀，相关 24 项通过。没有削弱考点识别或生成结果检查。

## 验证边界

- 已运行的真实生成仅为 SQL 单样本。视觉推理、其他格式真实生成和完整 20 请求质量评测待后续阶段。
- ADB 本次只读检查设备列表为空；Android 真机/仪器测试 **BLOCKED：无连接设备**。既有 Android JVM/认证强制重跑记录仍为前次审计证据，不冒充新真机通过。
- 本地权限/日志候选通过不等于原 ZH-04/#13、ZH-05/#26 已合入 main。远程任务状态保持原样。
