# 知学伴长期开发规则

## 入口与范围

- 先读 `docs/AGENT_PROGRESS.md`，再读当前阶段相关文件；规范是 `docs/AGENT_HARNESS_SPEC.md`，路线是 `docs/AGENT_ROADMAP.md`，结果在 `docs/AGENT_EVALUATION.md`。
- 当前集成基线为 `d7ae77a07b4114674df147a334827dbbca384a18`，本地分支 `codex/agent-harness`。不要把其能力称作 GitHub main 已发布。
- 每次只推进一个阶段；验收通过后自动进入下一阶段。遇缺设备/模型/权限，标受影响验证 BLOCKED，继续独立工作。
- 修改前审查既有模块和 PR，实现优先复用；ZH-04/05/06/08/09 沿用原 Issues，不建立平行任务体系。

## 业务与安全

- 保留 Android、Web、FastAPI、Ollama/Qwen、BKT 和现有数据，不重写 UI，不引入必须付费的 API。
- 模型做推理和动态决策；Harness 控制工具、身份、预算、状态与验证。确定性判分、归档、BKT 更新由代码执行。
- 服务器身份与空间不可由模型参数覆盖；逐资源授权，拒绝跨空间读写；不提供任意 shell、SQL、路径或 URL 工具。
- 新工具必须声明 schema、权限、超时、结果验证与写入幂等。模型、上传资料和 Skill 内容都不能扩大权限。
- 普通日志不记录正文、提示、题目、文件名/路径、令牌、Cookie、密码或异常原文。私有模型证据只能保存在授权空间。
- 作答事件和既有 BKT 是学习事实；不让 LLM 修改 mastery，不重复更新，不把正确率当掌握概率。
- 数据库只做追加迁移，保留旧记录。新流程默认可撤回到原固定 Worker。

## 验证与交付

- Web 部署会应用 backend/study 补丁，必须测试打包后的 backend，不以原模块测试代替。
- 已有入口：`npm.cmd --prefix web-prototype run build`、`tools/test-web-account.ps1`；阶段脚本及新测试见进度。
- TestClient 在 Windows 沙盒 socketpair 停滞时先确认堆栈，再用已授权的本机隔离环境复测，不能删测试绕过。
- 每个问题最多三轮有依据修复，保留失败原因与测试证据；不降低标准、不制造模型/质量结果。
- 每阶段记录：业务问题、教程机制、文件、原理、命令/结果、局限、技术要点及是否需要开发 Skill。
- 阶段未验收不记完成；全部十阶段、原有回归、真实模型端到端及目标检查未验证前不宣告 Goal 完成。
- 不重置用户修改，不自动推送/合并 main，不自动修改远程 Issues。只在独立本地分支开发。
- 必要开发 Skill 先说明职责与成本；普通实现和测试优先直接维护代码。
