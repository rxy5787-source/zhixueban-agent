# ZH-06：Qwen真实出题质量评测使用手册

**唯一评测题单**：docs/STUDY_GENERATION_EVAL.md 现有20条原始要求（12条计算机系统，8条SQL短资料）。脚本从原文读取并转换成可直接发送给模型的请求，保存请求、原始任务响应和人工评价；不虚构结果。

这不是新的Agent Skill，而是独立实验工具。程序不自动下载模型，不运行网络评测；实际运行必须显式加 --confirm-live，并且只接受本机回环地址。

## 第一阶段：预览固定题单（不运行模型）

    python python-ai/evaluation/zh06.py plan

原题型分布：口诀5、问答4、填空4、单选6、越界依据负例1。第20条只提供SQL短资料，要求解释TCP三次握手序号变化；人工核对是否正确拒绝无原文依据的请求，不能提前将预期判定喂给模型。

## 第二阶段：本机准备

- 本地安装并启动Ollama，安装 qwen3:1.7b（或明确记录其他模型）及仓库要求的Python依赖。
- 使用独立的 Web Trial 本地环境，TRIAL_LOCAL_PREVIEW=1，地址只绑定127.0.0.1。默认公众试用的8次任务配额不足以完成20条，不能绕过公共配额在公网运行。
- 完整实验必须提供计算机系统原始讲义（Word、PDF或TXT）；本仓库只包含SQL短文本样例 web-prototype/test-materials/SQL短文本资料.txt。若缺失原讲义，脚本拒绝执行前12条，不会使用编造的替代原文。
- 运行时请用非敏感讲义，新建隔离的数据目录，不使用个人真实学习数据。CI里的测试为离线模拟，不是实际Qwen质量结果。

参考Windows PowerShell启动方法（从仓库根目录执行）：

    python -m pip install -r python-ai/requirements.txt
    npm --prefix web-prototype ci
    npm --prefix web-prototype run build
    pwsh -File web-prototype/deploy/prepare.ps1 -PythonProject (Resolve-Path python-ai).Path -OutputZip ((Resolve-Path .).Path + '/artifacts/zh06-server.zip')
    Expand-Archive 'artifacts/zh06-server.zip' -DestinationPath 'artifacts/zh06-server'
    $env:PYTHONPATH = (Resolve-Path 'artifacts/zh06-server/server').Path
    $env:TRIAL_FRONTEND_DIR = (Resolve-Path 'web-prototype/dist').Path
    $env:TRIAL_DATA_DIR = Join-Path (Resolve-Path 'artifacts').Path 'zh06-runtime'
    $env:TRIAL_PUBLIC_ORIGIN = 'http://127.0.0.1:8095'
    $env:TRIAL_SECRET = ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))
    $env:TRIAL_LOCAL_PREVIEW = '1'
    $env:OLLAMA_URL = 'http://127.0.0.1:11434/api/chat'
    $env:AI_TEXT_MODEL = 'qwen3:1.7b'
    python -m uvicorn backend.web_trial:from_environment --factory --host 127.0.0.1 --port 8095

若打包目标已存在，换一个干净目录。此启动示例需要你电脑上对应的依赖和模型；不可直接在公网运行此本地评测服务。

## 第三阶段：先做SQL冒烟，再跑全20条

在第二个PowerShell窗口运行：

    python python-ai/evaluation/zh06.py run --confirm-live --cases 13,20 --output artifacts/zh06-eval/sql-smoke

确认本地模型运行正常，准备好原始讲义后再使用新的输出目录：

    python python-ai/evaluation/zh06.py run --confirm-live --cases all --system-source "D:/path/to/original-computer-systems.docx" --output artifacts/zh06-eval/full-qwen3-1.7b

每条案例在提交之前先把随机 `clientRequestId` 和输入摘要写到 `case-XX.json`。本地浏览器会话保存在同一输出目录的隐藏文件 `.local-trial.cookies`，该文件**包含敏感登录凭据**：不要共享、上传、加入Git或复制到公开目录。Linux/macOS将限制权限为仅当前用户；Windows应将此目录保存在自己的用户文件夹中。

每次只执行一个任务；成功收到任务ID后会保存回执。发生断线、超时、工具意外终止时，使用**相同输出目录、相同资料、相同案例**并明确开启恢复：

    python python-ai/evaluation/zh06.py run --confirm-live --resume --cases 13,20 --output artifacts/zh06-eval/sql-smoke

恢复流程先读取原会话并校验其有效性，再使用 `GET /api/generation-submissions/{clientRequestId}` 查询已接收的任务。如果任务已存在，只查询进度；如果服务端明确没有收到上传，才用同一提交标识重新提交。已完成案例不覆盖，资料SHA256或请求内容变化时拒绝混合结果。

评测开始前，CLI访问会话保护的 `/api/evaluation-preflight`，确认服务端明确处于**仅本机运行**的 `TRIAL_LOCAL_PREVIEW=1` 模式，并且Qwen就绪；否则不开始提交。本功能不会对公开试用服务开放。

失败和超时如实保留，不计入人工正确率。缺失案例可用 `--cases 5,6` 补跑；如果当前输出目录已经有会话或运行记录，必须使用 `--resume`，不能隐式换浏览器空间。原始输出包含学习资料或模型内容，默认 `artifacts/zh06-eval/` 已在 `.gitignore` 中。

## 第四阶段：人工核查并生成报告

全部执行结束后：

    python python-ai/evaluation/zh06.py review-template --output artifacts/zh06-eval/full-qwen3-1.7b

human_review.csv 由人工填写，reviewed= yes 才被视为已审；facts_correct、source_supported、goal_covered、usable 需对照原文逐项填 yes/no/na。第20例只填 refusal_correct，判断是否明确拒绝对没有原文依据的TCP问题编造答案；不能当成正向正确率案例。评分列未填写不计入分母。failure_category和notes记录具体失败原因。

为盲评，可将多个版本的生成输出隐去版本信息再混排交给评审者。同一个版本每次运行需保留模型、输入文件SHA256、运行日期及实际输出。最好至少两人独立评分并协商分歧。

生成报告：

    python python-ai/evaluation/zh06.py report --output artifacts/zh06-eval/full-qwen3-1.7b

输出 report.md 和 report.json。报告逐项说明人工分子和有效分母；没有人工结果时显示“尚无人工有效样本”。脚本不会把自动质检接纳率当成事实正确率，也不会把GitHub CI的测试通过当作Qwen生成质量。

## 已知局限

- 客户端只可观测任务墙钟耗时，不从阶段事件推测单次模型token或模型调用次数（当前API不提供）。
- 本次没有提前计算任何质量结果：只有你电脑真实运行、人工评价后才可能得到结论。
- 如后续基于真实失败原因发现必要的自动反馈职责，再由我先说明收益和边界，与你确认是否创建 quality_feedback_skill。
