# 知学伴开发路线

更新：2026-11-25。知学伴面向各类学习者，保留 Android、Web、FastAPI、本地 Ollama/Qwen、BKT 和数据库，在已有能力上逐阶段建立工程化 Agent Harness。

用户已授权持续完成 Phase 01～10，每阶段验收通过后自动继续。设计、文件、依赖、风险与逐阶段验收见 [AGENT_HARNESS_SPEC.md](AGENT_HARNESS_SPEC.md)，最新状态与证据见 [AGENT_PROGRESS.md](AGENT_PROGRESS.md)、[AGENT_EVALUATION.md](AGENT_EVALUATION.md)。此前只做审计的范围已经结束；仍不增加必付费 API、不重做界面、不推送或合并远程 main。

## 版本与任务事实来源

当前目录是保留 Android 原有改动的 Gitee 工作台；GitHub 项目为 [rxy5787-source/zhixueban-agent](https://github.com/rxy5787-source/zhixueban-agent)。本次核对 main=`d76e9e8`，ZH-04 PR #13=`abf1861`。本地 `artifacts/zhixueban-development` 和 `artifacts/zhixueban-agent-learning` 是不同进度的副本，不等同 main。具体完整 SHA 与审计范围见规范第 1 节。

下面沿用既有 ZH-01～10 和 Issues #2～11。阶段 1～10 是原任务内的验收拆分，不是十个新 Issue。草稿 PR 的代码与 CI、main 合入和真实业务验收分别记录。

## P0：可复现启动与 CI（沿用原任务）

- [x] **[ZH-01 / #2](https://github.com/rxy5787-source/zhixueban-agent/issues/2)**：GitHub 已关闭，有历史本地真实 SQL 演示；本次不重跑模型，也不把旧演示当作当前质量保证。
- [x] **[ZH-02 / #3](https://github.com/rxy5787-source/zhixueban-agent/issues/3)**：PR #1 已合入，main CI 已核对 success；本次固定 main 的打包 Web API 13 项通过。
- [x] **阶段 0：架构审计与规范**：本轮文档交付。明确版本、已实现/未实现、17 章机制映射、10 阶段依赖及验收，检查现有 ZH-04。业务运行时代码未改。

## P1：任务可靠性、权限与日志

- [x] **[ZH-03 / #4](https://github.com/rxy5787-source/zhixueban-agent/issues/4)**：PR #12 已合入；现有取消、重启、超时和幂等重试回归本次在固定 main 通过。Agent 步骤恢复属于后续增量验收，不能据此声称所有模型调用可断点续算。
- [ ] **[ZH-04 / #5](https://github.com/rxy5787-source/zhixueban-agent/issues/5)**：现有 [PR #13](https://github.com/rxy5787-source/zhixueban-agent/pull/13) 未合入 main。本次固定 head 的 14 项接口测试通过，历史 CI 也为 success；已有双访客的实际上传、归档、作答和双向越权回归，不重复开发。
  - 下一步只在原任务内：选定集成基础提交、保留增强用例，补充账号与未来 Tool 的作用域、失效关闭和无副作用验证。未授权不合并 PR、不关闭 Issue。
- [ ] **[ZH-05 / #6](https://github.com/rxy5787-source/zhixueban-agent/issues/6)**：已有计时与安全错误的实验 PR，先审查复用。区分原始业务审计与普通日志，补齐脱敏、耗时、错误类别和隐私验证。

**阶段 1 准入与验收**：先完成选定版本的权限基线，任何测试失败先定位。跨空间操作应拒绝且无副作用；普通日志不包含私有正文、凭证、文件路径和异常原文。

## P2：质量与容量（贯穿开发，不延后测试）

- [ ] **[ZH-06 / #7](https://github.com/rxy5787-source/zhixueban-agent/issues/7)**：沿用现有 20 条请求与评测 CLI，不另建同题单。学习副本已有真实执行记录，但人工有效分母为 0，未通过完整验收；不能用自动初筛保留率冒充正确率。
- [ ] **[ZH-07 / #8](https://github.com/rxy5787-source/zhixueban-agent/issues/8)**：沿用现有排队/并发测试候选，真实 1/3/5 用户提交的模型容量仍需独立测量。模拟任务通过不是 Qwen 吞吐结论。

固定题单和失败回归从第一个行为变更开始使用；阶段 8 再完善对照、人工质量和可观测发布门槛。

## P3：有边界地演进 Harness

- [ ] **[ZH-08 / #9](https://github.com/rxy5787-source/zhixueban-agent/issues/9)**：扩展已有 Registry 候选为标准工具契约，适配既有解析、证据、生成、复核和归档能力；每次调用验证授权和结果。
- [ ] **[ZH-09 / #10](https://github.com/rxy5787-source/zhixueban-agent/issues/10)**：在下列阶段逐项验收，不以“已有 Skill 名称”或条件路由替代模型驱动的 Agent Loop。
- [ ] **[ZH-10 / #11](https://github.com/rxy5787-source/zhixueban-agent/issues/11)**：用实际已验证版本形成架构说明、真实失败复盘与演示。本轮规范可复用，不因写完架构文档就标整个作品验收完成。

### 一次只推进一个子阶段

1. **工程基线、权限和日志：服务端候选 PASSED**。沿用 ZH-01～05；26 项打包 API、46 项源码测试、27 项真实账号与真实 Qwen SQL 样本通过。Android 真机因无设备 BLOCKED；远程 PR 未合并。
2. **Tool Registry：PASSED**。ZH-08，五项现有业务适配通过接口契约、权限与超时验收。本阶段提供只读和候选工具。
3. **Agent Loop 与 Ollama 适配器：PASSED**。ZH-09，真实 Qwen 按两个目标选择不同工具并基于结果作答。
4. **规划、持久化与恢复：服务端检查点 PASSED**。ZH-03/09，现有 SQLite 保存轮次、工具结果与终态，集成阶段验证实际归档恢复。
5. **按需 Skill：PASSED**。ZH-08/09，摘要发现、自适应练习、资料出题及审核策略按需读取。
6. **上下文管理**：ZH-09，有界片段、可授权取回的引用、保留目标和工具配对的压缩。
7. **学习记忆与 BKT**：ZH-09，先只读现有学习状态；两端数据未同步，模型不写掌握概率。
8. **Evaluation 与观测**：ZH-05/06/07，固定题单、实际分母、人工核对和真实容量。
9. **Agent 与固定工作流集成**：ZH-08/09，保留稳定 Worker、取消/重试、判分/归档和 BKT，不创建双状态源。
10. **Goal Loop**：ZH-09/10，独立验证目标证据，再决定结束；预算耗尽或验收器失败不标成功。

每阶段的候选文件、前置依赖、风险、测试和验收标准均在规范第 6 节。s06 子 Agent、s12 定时 Agent、s13 多 Agent、s14 MCP 当前暂缓，不为对应教程而增加机制。

## 阶段交付纪律

- 一个阶段先建立通过的基线，再做最小变更；验收通过后自动进入下一阶段，失败先修复当前阶段。
- 每次报告：业务问题、对应教程机制、修改文件、执行原理、独立测试步骤、实际结果/未测项、技术讲解要点。
- 不把未合入分支、固定模型响应测试或未执行的验证写成产品成果；不删除旧功能，不重写现有 UI。
- 在本地 `codex/agent-harness` 持续开发，保留原 Issues 编号；未修改 GitHub Issues、发布新 PR 或合并 main。
