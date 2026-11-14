---
name: systematic-debugging
description: 在代码报错、测试失败、CI异常、性能问题或Android/Web/FastAPI/Ollama集成故障时使用，先收集证据定位根因，再做最小修复，禁止靠猜测反复改代码。
---

# Systematic Debugging — 知学伴适配版

目标：解决真正的故障根因，而不是掩盖症状。**不得重置、删除、覆盖用户已有代码、数据或未提交修改。**

## 诊断步骤

1. **复现**：记录输入、环境、分支、版本、报错、预期与实际行为。尽可能确定最小复现；不能复现时先补日志与可观测性。
2. **定位**：只按需读取相关代码及调用链。对知学伴重点检查 Web → FastAPI → Worker → Ollama/Qwen → 复核 → 数据库存储之间的边界；或 Android → 接口 → 账号服务。查看近期 `git diff` 和配置变化。
3. **假设**：明确写出“怀疑原因 → 对应证据 → 用什么最小实验排除/确认”。一次只验证一个主要假设。不得把暂时相关当成因果。
4. **修复**：确定根因后，先添加或确定能重现问题的测试，再进行最小修改。优先兼容现有数据与API。
5. **验证**：运行对应测试和相关回归；出具命令、结果、修改文件和仍待验证的问题。没运行不宣称通过。

## 特别规则

- 禁止打印或记录用户上传的学习材料全文、密钥、Token或密码以排查问题；改用脱敏摘要、任务ID、错误类型和时间指标。
- 不要擅自执行外部脚本、删除缓存目录、停止服务、修改生产数据或更改Git历史。
- 如果不同修复尝试连续失败，停止叠加补丁，重新检查假设及架构。
- 需要单元测试设计时调用 `test-driven-development`；准备宣布完成时调用 `verification-before-completion`。

输出模板：**复现证据 / 根因与置信度 / 最小修复 / 实际测试 / 未解决风险**。

来源与许可：根据 Jesse Vincent 的 MIT 开源项目 `obra/superpowers` 之 `systematic-debugging` 精简适配。原文：https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging 。项目内许可证：`.agents/skills/THIRD_PARTY_NOTICES.md`。
