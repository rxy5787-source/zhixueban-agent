# Agent Harness 评测方案与实际结果

## 口径

- 确定性测试：schema、权限、日志隐私、幂等、恢复、BKT 计算；模型替身只证明这些契约。
- 真实模型测试：记录提交、模型标签、资料、要求、步骤与工具轨迹、质检和归档结果；不得将替身结果称作真实 AI。
- 质量：沿用 STUDY_GENERATION_EVAL.md 的 20 请求，不另造成功分母；人工审核、自动放行、拒绝和超时分别统计。
- 原有功能：Web 构建、打包后的 API、账号真实 HTTP、Python 质检、Android JVM；Android 真机与生产反代单列。
- Phase 10 最终检查包括真实薄弱点、历史资料、模型不同路径、强制质量门、取消/恢复、幂等归档与真实提交后的 BKT 更新。

## Phase 01

状态：服务端基线 **PASSED**；Android 真机回归 **BLOCKED：无连接设备**，是全目标完成前仍需补验的独立缺口。历史与新证据分别见 evidence/agent-harness-audit-20261125.md、[本阶段证据](evidence/phase01-harness-baseline.md)。

本阶段必须通过：

1. 原有 Web 打包回归及真实账号登录/过期/注销/隔离。
2. 无身份/篡改/过期 Cookie 拒绝；跨空间 timing、任务、练习拒绝且无副作用。
3. 日志和 timing 仅含白名单枚举、数字及服务器任务 ID；用敏感标记验证 stage、异常和输入不泄漏。
4. 领取与归档计时能回溯；旧任务未知耗时为 null；回调失败时事务回滚。
5. 前端构建、既有 Python 质量回归通过。

来源：ZH-04 PR #13 `abf18617d197d3788b6909b0e3bb19633109a110`；ZH-05 PR #26 `4d52ca893b023de4b8746540b2ca0f1221a9038d` / #37 `36aa633e7dd828f849d469c860417e0406289a93` 的 job_timing.py 内容一致。当前分支是兼容移植候选，不是把这些 PR 合并进 main。

实际结果：

- 最终 `test-agent-harness.ps1`：依赖检查与 Web 构建通过；打包 API **26 passed / 1 warning，43.75s**，源码单测 **46 passed / 1 warning，17.41s**。
- 同阶段真实账号脚本：Web/账号 **27 passed / 1 warning，110.89s**，账号/Agent 重复子集 **22 passed / 1 warning，10.00s**；不是额外 22 个独立测试。
- 过期凭证加强为有效 HMAC 但过期，单独复核 **2 passed / 4 deselected**；已纳入最终 26 项，不重复累计。
- 真实 qwen3:1.7b SQL 冒烟：首轮因未覆盖目标而拒绝；第 1 轮命题提示修复后成功，1 题归档，实际 HTTP 作答与 BKT 更新、双访客隔离通过。只报告这个样本，不算 20 例人工分数。
- Starlette/httpx 弃用警告仍存在，本轮未更换依赖。Android JVM 与 Java 认证此前强制重跑分别 13/8 项通过，未当作本轮新执行。

可重放原始运行目录：`.verification/harness-8b8af031415446f8a54ecbeca3656704/`（最终 pytest.xml/unit.xml）、`.verification/harness-phase01-real-scope-fix1-20261126/`（真实任务），目录均被忽略。

## Phase 02

状态 PASSED。执行 `./tools/test-agent-harness.ps1`，打包接口与工具 **30 passed**（71.08s），源码 **46 passed**（12.89s），两组各出现一条已知 Starlette 弃用警告。Web 构建和依赖检查通过。原报告在 `.verification/harness-f20efee6475f4374b9e6af1faaefc3b5/`。

工具用例覆盖真实 TXT/SQLite 学习空间，严格输入输出、拒绝跨库和属主不匹配、超时回收与异常脱敏。生成、知识点提取及审核通过测试替身验证适配器调用契约，真实 Qwen 动态决策列入 Phase 03。

## Phase 03

状态 PASSED。使用打包后的 server，设置 `PYTHONPATH` 指向该目录、`ZHIXUE_TEST_LIVE_AGENT=1`、`OLLAMA_URL=http://127.0.0.1:11434/api/chat`、`AI_TEXT_MODEL=qwen3:1.7b`，执行 `python -m pytest -q -s web-prototype/deploy/test_study_tools.py`。结果 **8 passed，63.68 秒**。打包目录为 `.verification/phase03-fix1-6ee11ff1e8ff4b728cf2505e9ff3de59/`。

真实 Qwen 分别走 `read_progress → proposed_finish` 和 `parse_material → proposed_finish`。学情使用临时 SQLite 合成样例（WHERE 掌握估计 33%），资料使用自编 SQL 文本。复测显示模型基于工具结果回答。两条轨迹覆盖动态选工具和结果反馈。真实练习生成、恢复及目标验收仍由后续阶段完成。

## Phase 04

2026-11-26 使用 `./tools/test-agent-harness.ps1` 执行本阶段。打包测试 34 项通过，2 项真实模型用例按开关跳过，源码测试 46 项通过，Web 构建和依赖检查通过。两组均保留已知的 Starlette 弃用警告。报告目录 `.verification/harness-7a113edadf8840dbb4c0b5d1081ebfef/`。

测试从已保存的工具结果恢复同一任务，验证旧尝试、取消和异主访问的拒绝。中断由确定性测试触发。完整用户入口上的进程中断与归档恢复留待集成阶段。

## Phase 05

2026-11-26 使用 `./tools/test-agent-harness.ps1`。打包测试 **35 passed / 2 skipped**，源码测试 **46 passed**，Web 构建与依赖检查通过。跳过的两项为 Phase 03 的本地 Ollama 用例。报告目录 `.verification/harness-f739448c1cb746eba9e9a2a792e3c4d1/`。

打包后的独立进程验证了摘要发现、按名称读取正文和内容哈希，并检查越界名称、缺少授权及教学策略未扩大工具权限。模型在 Web 流程中的选择留待集成验证。
