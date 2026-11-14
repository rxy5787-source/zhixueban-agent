# 第四关：Skill Registry + Planner 动态调度

本分支**叠加**PR #14中的 `agent_runtime.py` 和PR #16中的只读 `weak_points_skill.py`，用于学习模块衔接。不要将它视为两份PR已经合并进main。

新增 `python-ai/backend/study_skill_planner.py`：独立规划器，只返回下一步建议，不生成题目，不访问数据库，不调用Qwen。

## 三个角色

1. **Skill Registry** 管理白名单、检查每个Skill的输入/输出契约。
2. **get_weak_knowledge_points** 依据已有Web BKT记录计算证据充足程度，返回 `ready`、`needs_diagnosis` 或 `no_weak_points`。
3. **LearningPlanner** 每执行一步重新读取state，选择下一Skill。根据结果选 `plan_targeted`、`plan_diagnostic` 或 `plan_review`。

## 例子

```python
from backend.study_skill_planner import plan_study_from_progress

progress = [{
    "point": "HAVING", "observations": 1, "correct": 0, "mastery": 0.20,
}]
result = plan_study_from_progress(progress)
print(result.model_dump())
# status: needs_diagnosis
# next_action: prepare_diagnostic
# visited_skills: ["get_weak_knowledge_points", "plan_diagnostic"]
```

这个例子中，出现的 `progress` 是模拟数据；正式接入时必须由后端先校验当前登录主体的知识库权限，并通过 `web_practice.history(db, library_id)["points"]` 提供经过授权的数据。

**安全边界**：模型无权自己选择任意技能或传入其他用户ID；规划器没有Shell、数据库写入或网络能力。它只输出建议，不能宣称已自动生成诊断题。完整任务保存、断点恢复、模型出题仍由未来集成负责。

## 单元测试（无需模型）

在仓库根目录 PowerShell：

```powershell
$env:PYTHONPATH = "python-ai"
python -m pytest -q python-ai/test_agent_runtime.py python-ai/test_weak_points_skill.py python-ai/test_study_skill_planner.py
```

测试验证：没历史 → 诊断，1次答错 → 诊断，有证据弱项 → 定向复习，无弱项 → 综合复习，以及注册白名单、字段缺失和非法历史。
