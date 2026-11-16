# 第42阶段：CI去重与发布前验收清单

> 范围：**仅在独立集成草稿分支实施**。保留原仓库main及所有历史PR/CI记录；不自动合并、不宣称正式发布。
> 产品定位：知学伴是面向**任何有学习需求的人**的通用AI自适应学习助手，不限软件设计师备考。

## 一、本阶段CI去重

原发布候选含10个GitHub Actions配置：8条阶段性（Agent audit、phase34–40）、`stable-quality-gate.yml`与`web-ci.yml`。

当前候选**已删除8条仅服务历史开发阶段的工作流文件**，仓库当前候选只保留：

- `.github/workflows/stable-quality-gate.yml`：稳定集成和发布候选质量门禁，复用Agent、质量、ZIP、打包Web API、历史/部署审计；支持手动触发、复用调用，并自动取消同分支过时CI。
- `.github/workflows/web-ci.yml`：保留原 `main` 的Web/Agent基础检查，不更改任何main现有行为。

新的 `scripts/check_ci_consolidation.py` 与 `scripts/tests/test_ci_consolidation.py` 检查恰好保留两条工作流、关键检查项未丢失、权限仍是只读、Git祖先核验可用、main的检查入口未改变；新的稳定CI将运行这些校验。**删除操作只发生于本草稿分支**；其它草稿PR、历史提交和GitHub Actions运行记录不受影响。

注意：现在尚未把稳定CI设置成main的Required Check。私有仓库的Rulesets API以前返回403（套餐/权限限制），不能虚构强制保护已经开启。

## 二、正式发布前不可跳过的检查

| 验收项 | 现有客观证据 | 状态 |
| --- | --- | --- |
| 全量离机单测 | 第41阶段PR #44：7项集成审计、59项Agent、85项后端质量、13项ZIP门禁、45项打包Web API，通过 [Actions #43917010331](https://github.com/rxy5787-source/zhixueban-agent/actions/runs/43917010331) | 已在**上阶段候选**完成；本阶段需重跑 |
| CI去重完整性 | 新增静态核查和失败用例，检查旧流程删除后没有丢失核心门禁 | 待本阶段CI验收 |
| 发布ZIP内容、SHA-256 | 包含关键后端模块，不允许误打包密钥/SQLite/缓存等开发资料 | 第41阶段已通过，本阶段需重跑 |
| Git审计和合并审查 | PR #43冻结了主链SHA与8条仍分叉侧链的审计记录 | 自动祖先审计已具备，人工处理未完成 |
| Docker镜像构建、启动、健康检查 | CI当前只验证离线ZIP及API测试，没有实际容器启动 | **未验证** |
| 真实Ollama/Qwen题目生成与证据质量 | 现有单测采用模拟模型，尚缺真实推理与人工质量评审 | **未验证** |
| Qwen推理吞吐、并发、显存/内存峰值 | 离线多访客入队不能代表同时完成多次模型推理 | **未验证** |
| Android安装、联调、真实设备交互 | Android离机构建曾在独立PR #25开发，但此候选不等于真机验收 | **未验证** |
| 漏洞、依赖锁定、数据保留与隐私策略 | 尚无完整生产环境安全审计 | **未完成** |
| UI/产品适用性 | 软件设计师备考只是样例；应用面向广大学习者 | 需在完整Web/Android体验里验收 |

## 三、发布门槛和审核策略

1. **本阶段CI先通过**：`Stable quality / Web + Agent + ZIP`，包含新的CI去重测试和全部原有回归。保留运行URL和最新提交SHA。
2. **PR整体审核**：按主链真实祖先关系核对已集成行为；对仍分叉的#16、#18、#25、#26、#27、#33、#34、#35逐项判定是否移植、保持独立或明确弃用，不将“代码大致相似”视为已合并。
3. **main分支治理**：若将来需要将稳定CI替换`web-ci.yml`，另提专门PR，由用户明确授权后再执行；暂不自动触发两个重复的main长CI。
4. **运行环境验收**：真实Docker启动和带Qwen的端到端答题闭环、性能测量、Android设备测试完成前，不设置正式发布标签，不声称生产可用。
5. **开放场景验证**：至少选不同学科/考试/职业学习材料进行质量测试；明确题目依据、置信度与用户反馈闭环，不能把面向单一考试样本的效果泛化给所有用户。

## 四、后续可重复执行的命令

```powershell
python -m pytest -q scripts/tests/test_ci_consolidation.py
python scripts/check_ci_consolidation.py --output ci-consolidation-audit.json
```

这些检查不能替代实际Docker、真实模型、Android或生产安全审计。所有变更尚在草稿PR，未经授权不合并`main`。
