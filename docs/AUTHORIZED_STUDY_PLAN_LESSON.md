# 第五关：将学习 Planner 只读接入真实 BKT 记录

这个实验叠加在 [PR #17](https://github.com/rxy5787-source/zhixueban-agent/pull/17) 上。
它只提供计划，**不会自动生成题目、改写掌握度或提交练习**。

## 实现

- `python-ai/backend/study_plan_service.py`：校验本空间知识库是否存在且未删除；读取现有 `web_practice.history(db, library_id)["points"]`；调用 `plan_study_from_progress`。
- `web-prototype/deploy/web_trial.py`：`GET /api/study-plans/{library_id}`。只从验证过的浏览器会话确定 `TrialStore`；路径参数只允许在当前空间内选库。
- `web-prototype/deploy/prepare.ps1`：把试验 Planner、Registry 和只读服务一起放入 Web 后端部署包。
- `web-prototype/deploy/test_web_trial.py`：通过 TestClient 验证空历史、不同空间同名库、跨空间不可读、删除后的库、非法标识、坏数据、只读不修改记录。

响应沿用 `StudyPlan`：

```json
{
  "status": "ready",
  "next_action": "prepare_targeted_practice",
  "topics": ["HAVING"],
  "reason": "evidence_backed_weak_points",
  "visited_skills": ["get_weak_knowledge_points", "plan_targeted"]
}
```

## 权限与异常

1. 已验证的Cookie会话映射到独立的服务端学习空间；没有有效会话返回401。
2. 只在当前空间的SQLite连接内查库；不存在、别人的库、已删除库统一返回404。
3. 只允许格式合法的库ID；非法格式返回422。
4. 已持久化的学习进度不符合证据约束时返回409；不进行模型猜测或默认复习。
5. 遵守既有Origin、Host和访问码边界，不开放通用文件读取或自定义数据库路径。

**局限**：这是试用版「按浏览器空间」隔离，**不是正式账号的跨设备权限系统**。没有创建自动出题任务，没有评测BKT阈值的预测效果，且目前依赖已有记录而非实时同步Android进度。

## 验收

```powershell
$env:PYTHONPATH = "python-ai"
python -m pytest -q python-ai/test_agent_runtime.py python-ai/test_weak_points_skill.py python-ai/test_study_skill_planner.py
# Web试用API打包测试通过以下已有脚本执行：
# web-prototype/deploy/prepare.ps1 -PythonProject (Resolve-Path python-ai).Path -OutputZip <新ZIP路径>
```

正式合并之前，需要先协调 PR #14、#16、#17 和更新版 PR #18 的集成顺序，并确保完整Web CI通过。
