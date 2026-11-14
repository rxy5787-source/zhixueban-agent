---
name: test-driven-development
description: 新增Python、TypeScript、Android模块或修复可复现Bug时使用，采用Red-Green-Refactor，先定义可观察行为和失败测试，再做最小实现，保护已有代码。
---

# Test-Driven Development — 知学伴适配版

目标：让新增功能和缺陷修复有**能够捕捉回归的证据**，不是为了覆盖率而编写测试。

## RED → GREEN → REFACTOR

1. **明确契约**：描述用户可观察行为、输入输出、异常分支、权限边界、兼容条件；先决定“什么实现变坏会让这条测试失败”。
2. **RED**：对新增功能或可重现Bug先写最小测试，执行并确认因目标行为缺失而失败，而不是导入报错、测试环境缺失或拼写错误。
3. **GREEN**：只修改必要代码，让刚才的测试通过。保留现有公开接口和用户未提交修改。
4. **REFACTOR**：在测试通过基础上移除重复、改善命名或边界；再次运行对应测试。
5. **REGRESSION**：运行与改动相关的模块测试、跨模块回归；真实Qwen输出需单独做集成/内容质量验证。

## 项目中的起点

- Python / FastAPI：优先使用已有 `pytest` 与 `web-prototype/deploy/test_web_trial.py` 的测试夹具。
- Agent规划与Skills：当前分支若存在 `python-ai/test_agent_runtime.py`，复用其Skill白名单、重试预算、错误处理测试；**不要假设其他PR已经合入**。
- Web：查看 `web-prototype/package.json` 决定如何运行 `npm run build`、类型检查或已有测试。
- Android：先查看 Gradle 定义及现有测试，再选择可运行的测试任务。

## 安全与真实性

- **绝不因现有代码缺少先行测试而删除、丢弃或重建它。** 对遗留模块使用“现状刻画测试 → 最小改动 → 回归”。
- 外部模型、数据库和网络调用可以在明确契约的边界使用测试替身，但核心业务判断应验证真实实现，不要仅断言Mock被调用。
- 无法运行测试时标记为**未验证**并说明原因；不得编造Red/Green结果。

输出：**行为契约 / RED失败记录 / GREEN通过记录 / 相关回归 / 风险与待验证项**。

来源与许可：根据 Jesse Vincent 的 MIT 开源项目 `obra/superpowers` 之 `test-driven-development` 精简适配。原文：https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/test-driven-development 。项目内许可证：`.agents/skills/THIRD_PARTY_NOTICES.md`。
