# 知学伴 Agent 动态规划与 Skill 调度（独立试验版）

新增 python-ai/backend/agent_runtime.py 和 python-ai/run_agent_pilot.py。本版本不修改 Android / Web 现有 API、不替换生产 Worker、不写入正式题库。

## 核心能力

- SkillRegistry：只允许运行已注册的技能，并校验输入/输出字段。
- BoundedPlanner：根据当前任务状态重新选择下一技能，默认最多8步、最多2轮生成尝试。
- 复用现有模块完成准备资料、知识点提取、Qwen出题、独立校验。失败时把审核反馈传回下一轮生成。
- 记录技能名称、耗时、执行状态，不在事件日志中写入原始资料、模型输出或私有上下文。
- 不开放任意Shell、SQL、联网工具或生产数据库写入。

这里的动态规划是**状态驱动的有界技能选择**，不是语言模型自由规划，也不是多Agent/A2A。这是更稳妥的第一阶段。

## 本地使用

先安装 python-ai/requirements.txt，启动本地 Ollama 并准备 qwen3:1.7b。仓库根目录执行：

    python python-ai/run_agent_pilot.py --source "web-prototype/test-materials/SQL短文本资料.txt" --goal "生成一道考查 WHERE 作用的四选一单选题" --count 1 --output "agent-pilot-output.json"

运行后查看 status、accepted、rejected、events 和 attempts。模型未能生成可核验题目时，可能返回失败，不为凑题数放行。

## 无模型单元测试

    $env:PYTHONPATH="python-ai"
    python -m pytest -q python-ai/test_agent_runtime.py

测试覆盖动态技能选择、重试、已有知识点跳过提取、技能白名单、超步数与隐私错误日志。不能替代本地 Ollama 实测。

## 下一步

1. 完成真实模型验收，固定20例评测集并测量正确率、耗时和失败原因。
2. 与现有 Worker 安全集成，先用特性开关、原流程回归测试保护现有功能，同时更新 Web 打包清单。
3. 再引入模型提出候选计划，但所有候选必须通过技能白名单、权限、参数及资源预算验证。
4. 完善渐进式上下文和状态持久化，之后再考虑多Agent协作。
