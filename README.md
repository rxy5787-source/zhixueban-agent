# 知学伴 Zhixueban

知学伴从学习资料生成有原文依据的口诀和练习，并根据作答记录更新知识点掌握情况。这个仓库包含 Android 客户端、Web 原型、Python 生成服务和独立的账号服务。

- Web 使用 React 和 TypeScript 展示学习空间、资料与生成任务。
- Python 使用 FastAPI、持久任务与本地 Ollama，执行资料解析、生成和复核。
- Android 使用原生 Java、Kotlin 和 Compose，部分页面仍为传统 View。

开发路线与验收标准见 [Agent 开发路线](docs/AGENT_ROADMAP.md)。生成质量的样本和实测边界见 [评测用例](docs/STUDY_GENERATION_EVAL.md)。

## Windows 本地演示

准备 Python 3.12、Node.js 22.12+ 和 Git。在 PowerShell 中执行。

```powershell
py -3.12 -m venv python-ai/.venv
& ./python-ai/.venv/Scripts/python.exe -m pip install -r python-ai/requirements.txt
npm.cmd --prefix web-prototype ci
& ./tools/start-web-study-preview.ps1 -PythonProject (Resolve-Path python-ai).Path
```

打开 [本机预览](http://127.0.0.1:8095/#home)。需要真实生成时，请先在本机启动 Ollama，准备 qwen3:1.7b。演示用文字资料可以使用仓库内自编的 SQL 示例。本地预览数据保存在 .verification 目录。

## 部署与实现边界

[Web 试用部署说明](web-prototype/deploy/README.md)包含 Docker Compose 配置与启动方法。打包时通过 -PythonProject 指向仓库中的 python-ai。当前实现适合开发和小规模演示。并发吞吐、重启恢复和权限隔离的完整验收见开发路线。
