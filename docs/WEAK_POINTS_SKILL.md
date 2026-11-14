# get_weak_knowledge_points：第一个业务Skill（独立练习版）

文件：`python-ai/backend/weak_points_skill.py`

这个模块只接收**已授权加载**的学习进度列表，不连接数据库，不调用模型，不读取其他用户资料，也不修改正式出题任务链。它对接Web后端现有的 `web_practice.point_view()` 结构：`point`、`observations`、`correct`、`mastery`。

## 输入、输出及契约

输入：已从受信任Web接口/服务端读取的知识点进度数组（按知识库范围过滤），默认至少3次作答记录才纳入薄弱点排序，阈值 `mastery < 0.45`。这些是第一版**启发式阈值**，并未证明具有统计校准意义。

输出：`WeakPointResult`：
- `ready`：有足够证据且存在低于阈值的知识点 → 可制定针对性练习计划
- `needs_diagnosis`：无记录或均为稀疏样本 → 进入诊断题流程；若没有可用学习资料，先请求资料
- `no_weak_points`：有足够证据，但未检测到低于阈值的点 → 综合巩固/提高练习
- 非法数据 → Pydantic/ValueError，不伪装成“用户没有历史数据”

输出的 `mastery_estimate` 是项目BKT的模型估计，不是直接正确率；项目模型参数未充分校准。若部分知识点样本少，它们不计入 `ready` 列表；后续应加入“待评估点”输出以避免遗漏。

## 纯函数测试

从仓库根目录：

```powershell
$env:PYTHONPATH = "python-ai"
python -m pytest -q python-ai/test_weak_points_skill.py
```

无需Ollama。当前Skill**尚未**注册到 PR #14 的 `SkillRegistry`，也未接入Android/Web正式工作流。接入前需要制定拥有者隔离、API鉴权、错题/诊断任务的端到端设计，并覆盖回归测试。

注意：Web端目前按知识库保存进度，Android端有自己的BKT存储。两端不能假设数据自动同步。
