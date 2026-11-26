# 知学伴 Zhixueban

知学伴面向有学习需求的用户，从课程资料、读书笔记和其他学习材料生成有原文依据的解释、口诀和练习，并根据作答记录更新知识点掌握情况。

## 从这里开始

- **运行项目** → [Windows 本地演示](#windows-本地演示)
- **找下一项任务** → [开发任务与验收](#开发任务与验收) · [Issues](https://github.com/rxy5787-source/zhixueban-agent/issues)
- **看正在审查的代码和测试** → [Pull requests](https://github.com/rxy5787-source/zhixueban-agent/pulls) · [Actions](https://github.com/rxy5787-source/zhixueban-agent/actions)
- **看设计、评测和部署** → [开发路线图](docs/AGENT_ROADMAP.md) · [生成质量评测](docs/STUDY_GENERATION_EVAL.md) · [Web 部署](web-prototype/deploy/README.md)

## 项目目录

- [Android 客户端](app/) · Java、Kotlin 和 Compose，部分页面使用传统 View。
- [Web 试用端](web-prototype/) · React 和 TypeScript，提供学习对话、知识库、出题任务与练习。
- [AI 生成服务](python-ai/) · FastAPI、后台任务和本地 Ollama，负责资料解析、生成与复核。
- [账号服务](auth-server/) · 独立 Java 服务。

## 开发任务与验收

- **P0 · 可复现启动与 CI** · [ZH-01 让新开发者能启动项目](https://github.com/rxy5787-source/zhixueban-agent/issues/2) · [ZH-02 设置 CI 和版本基线](https://github.com/rxy5787-source/zhixueban-agent/issues/3)
- **P1 · 可靠性与权限** · [ZH-03 验证任务重启和重试](https://github.com/rxy5787-source/zhixueban-agent/issues/4) · [ZH-04 验证学习空间隔离](https://github.com/rxy5787-source/zhixueban-agent/issues/5) · [ZH-05 建立分阶段日志](https://github.com/rxy5787-source/zhixueban-agent/issues/6)
- **P2 · 质量与容量** · [ZH-06 固定口诀和出题评测集](https://github.com/rxy5787-source/zhixueban-agent/issues/7) · [ZH-07 测量单机并发容量](https://github.com/rxy5787-source/zhixueban-agent/issues/8)
- **P3 · Agent 与作品展示** · [ZH-08 提取可验证的 Agent 工具接口](https://github.com/rxy5787-source/zhixueban-agent/issues/9) · [ZH-09 加入有边界的任务路由](https://github.com/rxy5787-source/zhixueban-agent/issues/10) · [ZH-10 完成项目演示与技术说明](https://github.com/rxy5787-source/zhixueban-agent/issues/11)

每个 Issue 记录目标、验收条件和相关 PR。查看 PR 的 **Files changed** 回顾代码，查看 **Checks** 核对自动测试。改动合入后，在 Issue 留下提交和验收结果，再关闭任务。

当前优先验证和修复 Web 学习闭环，覆盖对话、上传、真实模型出题、答题、知识库和针对薄弱点的练习。Android UI 适配和真机测试暂缓。[知学伴 Web 端功能测试报告](docs/WEB_FUNCTIONAL_TEST_REPORT.md)

## Windows 本地演示

准备 Git、PowerShell 7、Python 3.12、Node.js 22.12+ 和 Ollama。在仓库根目录执行以下命令。

```powershell
py -3.12 -m venv python-ai/.venv
& ./python-ai/.venv/Scripts/python.exe -m pip install -r python-ai/requirements.txt
npm.cmd --prefix web-prototype ci
ollama pull qwen3:1.7b
& ./tools/start-web-study-preview.ps1 -PythonProject (Resolve-Path python-ai).Path
```

运行命令前先打开 Ollama。如果 `ollama list` 提示连接失败，在另一个终端运行 `ollama serve`。下面的文字资料演示只需要文本模型。

1. 打开 [本机预览](http://127.0.0.1:8095/#home)，上传仓库内自编的 [SQL 短文本资料](web-prototype/test-materials/SQL短文本资料.txt)。
2. 输入「生成 1 道 SQL 基础四选一单选题，考查 WHERE 过滤数据行的作用」，选择知识库并提交。
3. 等待质检和归档完成，打开结果中的练习，提交答案后查看知识点报告。

本地预览数据保存在 `web-prototype/.verification/study-local`，按 `Ctrl+C` 停止预览。自动验收脚本 `web-prototype/deploy/smoke_trial.py` 使用独立数据目录，检查真实模型调用、自动归档、答题报告和第二个访客的访问隔离。

## 部署与实现边界

[Web 试用部署说明](web-prototype/deploy/README.md)包含 Docker Compose 配置与启动方法。打包时通过 -PythonProject 指向仓库中的 python-ai。当前实现适合开发和小规模演示。并发吞吐、重启恢复和权限隔离的完整验收见开发路线。
