---
name: zhixueban-test-review
description: 在知学伴修改代码后进行测试、代码审查、PR提交前验收、定位CI失败或检查AI生成代码回归风险时使用。按变更范围选择最小充分测试并报告真实结果。
---

# 知学伴：测试与代码审查

## 先审查差异

1. 查看 `git status`、`git diff --stat`、`git diff`，明确改动文件、接口契约和依赖关系；已有用户修改不覆盖、不重置。
2. 重点检查：异常处理与重试边界、重复写入、权限隔离、个人资料与密钥泄露、数据库迁移、前后端接口一致性、日志、测试用例是否真正覆盖变更。
3. 不能用“CI通过”替代人工审查，也不能根据一次模型输出宣称题目内容正确。

## 按需运行测试

仅运行与改动有关的命令，先确认依赖及运行环境是否具备：

- Web UI：仓库根目录运行 `npm.cmd --prefix web-prototype ci`，再运行 `npm.cmd --prefix web-prototype run build`；如已有依赖，可省略 ci。
- Python Web API：参考 `.github/workflows/web-ci.yml`，在Windows / PowerShell运行 `web-prototype/deploy/prepare.ps1` 打包后，对解压目录的 `server` 设置 `PYTHONPATH`，再运行 `python -m pytest -q web-prototype/deploy/test_web_trial.py`。先检查当前版本的脚本参数。
- Agent Skill 调度：仅当当前分支存在 `python-ai/test_agent_runtime.py` 时，将 `PYTHONPATH` 设为 `python-ai` 并运行 `python -m pytest -q python-ai/test_agent_runtime.py`。
- Android/Java模块：仅当改动涉及 `app/` 或 `auth-server/` 时查看 Gradle 已定义任务，再选择对应构建或测试；不要未经检查就承诺某条任务可运行。
- Ollama/Qwen：真实推理是额外的集成验证，只有用户希望实测且服务可访问时才运行；记录模型版本、输入样本、耗时和复核结果。自动测试不能代替实际推理验证。

不要为了测试去删除用户数据、覆盖运行目录或对生产环境发起写操作。

## 交付格式

按照“变更摘要 → 发现的问题（文件与位置、严重程度） → 已执行测试及结果 → 没执行的测试与原因 → 合并前建议”报告。若没有发现问题也说明测试覆盖范围；禁止推测或虚构通过数量。
