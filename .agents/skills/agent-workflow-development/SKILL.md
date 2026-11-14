---
name: agent-workflow-development
description: 在知学伴开发或修改 Agent 任务规划、Skills/工具调用、任务状态、失败恢复、上下文管理和模型出题复核流程时使用。复用现有模块，按可测试的最小改动交付。
---

# 知学伴：Agent 工作流开发

## 先核实

1. 阅读 `docs/AGENT_ROADMAP.md` 中对应的 Issue 与验收范围，只打开相关代码。
2. 根据变更内容检查：`python-ai/backend/web_api.py`、`worker.py`、`job_store.py`、`knowledge_extractor.py`、`web_question_review.py`，以及 `python-ai/generate_from_file.py` 和 `automatic_question_validator.py`。不要假设每个文件都与当前任务相关。
3. 当前分支若存在 `python-ai/backend/agent_runtime.py`，先检查其行为与测试再复用；它曾在独立试验PR中开发，**不可默认已合入 main**。

## 开发规约

1. 先写任务 Spec：目标、输入/输出结构、可访问的资料、允许调用的 Skill、完成条件、失败结果和验收测试。
2. 只在存在真实分支决策时引入动态规划；固定的“解析→生成→复核”可优先使用确定性流程。不要为了称为 Agent 就增加多Agent或自由执行能力。
3. Skill 必须有明确名称、输入/输出契约和白名单注册；不要让模型响应直接决定任意文件访问、Shell命令、SQL执行或外部网络操作。
4. 规划器明确状态及转移：queued / running / succeeded / partial / failed / cancelled；设置调用步数、超时、重试预算与终止条件。
5. 保持重试幂等、取消有效、数据按用户/学习空间隔离；日志记录任务ID、步骤、耗时、错误类型，不泄露原文、密钥或认证信息。
6. 评测成功与“代码能运行”分开。至少测试正常路径、无证据、模型异常、重复提交、超限与恢复；原文依据和自动复核不是事实正确性的最终保证。
7. 尽量小范围修改，保留现有接口兼容性。若涉及 Web 部署包，检查 `web-prototype/deploy/prepare.ps1` 中的后端文件列表和补丁是否需要同步。

## 交付

说明本次任务的**状态图或执行路径**、Skill契约、实际修改文件、运行过的测试、未测试项及剩余风险。不要声称本地Qwen验证通过，除非真的运行了模型。
