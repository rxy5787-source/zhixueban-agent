---
name: verification-before-completion
description: 在声称代码已完成、Bug已修好、测试已通过、准备提交PR或合并之前使用，用真实命令输出、Git差异和验收标准逐项核查，避免虚报测试结果。
---

# Verification Before Completion — 知学伴适配版

核心原则：**先有最新的验证证据，再声称成功。** 代码写入仓库 ≠ 本地部署成功；模拟单测通过 ≠ Ollama真实推理通过。

## 完成前核验

1. 核对任务要求、当前分支、`git status` 与 `git diff`；检查是否修改了不属于当前任务的文件。
2. 列出每个结论所需的验证方法。按需执行真实构建、单元测试、集成测试或人工验收。
3. 读取**本次运行**的完整退出码、错误数、测试数量与关键日志。不能用以前的CI结果或“看起来正确”代替。
4. 分别报告：**已执行并通过 / 已执行但失败 / 未执行及原因**。
5. 检查边界条件：任务失败/取消/重试、重复归档、权限隔离、隐私日志、API兼容性、异常恢复。
6. 提交PR时附变更摘要、实际测试命令及结果、截图或运行链接（如适用），并说明真实模型与Android/Web集成是否验证。

## 与项目现有检查结合

- 如果已配置 `zhixueban-test-review`，先按该Skill选择正确的模块验证命令，避免没必要的全量测试。
- 通过GitHub Actions时核对**当前PR或当前提交SHA**；不同分支的绿色CI不证明本次提交通过。
- 当环境缺少Ollama、本地Android SDK或依赖时，明确写“未实测”，不得将成功编译等同于功能质量验收。
- 不要为“验证”擅自删除用户文件、重置Git、执行危险命令或访问生产数据。

输出格式：**验证项目 | 执行命令/证据 | 结果 | 未覆盖风险**。

来源与许可：根据 Jesse Vincent 的 MIT 开源项目 `obra/superpowers` 之 `verification-before-completion` 精简适配。原文：https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/verification-before-completion 。项目内许可证：`.agents/skills/THIRD_PARTY_NOTICES.md`。
