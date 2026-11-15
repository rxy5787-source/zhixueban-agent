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

每条逐一执行直至完成或超时；保存到 case-01.json 等文件。失败和超时如实保留，不计入人工正确率。脚本发现已有同编号结果时拒绝覆盖；缺失案例可以使用 --cases 5,6 精确补跑。提交后断网应先查看服务器任务是否已经创建，避免人为重复运行。原始输出可能含课堂资料和模型内容，已对默认 artifacts/zh06-eval/ 路径添加 .gitignore。

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
