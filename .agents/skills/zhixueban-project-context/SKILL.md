---
name: zhixueban-project-context
description: 在知学伴仓库中接手陌生功能、分析前后端调用链、定位模块职责或评估跨模块修改影响时使用。按需读取相关代码，避免每次扫描全仓库。
---

# 知学伴：按需理解项目

本 Skill 服务于**项目理解和变更影响分析**，不是要求把整个代码仓库全部读进上下文。

## 操作顺序

1. 先查看 `README.md` 的目录说明，必要时再打开 `docs/AGENT_ROADMAP.md`。以上文件仅作入口，实际实现以当前分支代码为准。
2. 根据用户问题，只选择相关部分：
   - Android：`app/`（Kotlin / Compose，部分 Java / View）。
   - Web：`web-prototype/src/`（React / TypeScript）。
   - Python Agent/出题：`python-ai/backend/`、`python-ai/generate_from_file.py`、`python-ai/automatic_question_validator.py`。
   - 账号服务：`auth-server/`。
   - Web部署与接口适配：`web-prototype/deploy/`。
3. 需要追踪出题流程时，按“请求入口 → 任务保存 → Worker → 模型生成/复核 → 结果归档 → 客户端展示”的顺序逐段核实；不要只靠文件名推测行为。
4. 先搜索符号、接口、调用方和相关测试，再读取必要函数附近的代码。不要默认读取构建产物、模型缓存、用户上传资料、私有运行数据。
5. 对于「已实现／在当前分支存在／路线图计划中」分别标注，不能把计划或其他PR中的代码当成当前分支已完成的功能。
6. 提出修改建议时，报告：关键文件、真实调用链、变更范围、兼容性与回归风险、尚未核实的点。

## 输出方式

优先用一张简洁的调用链或少量文件定位回答；只有用户要求改代码时才进入实现步骤。遇到证据不足，明确指出待检查的文件，不要编造架构。
