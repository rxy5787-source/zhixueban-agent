# 第41阶段：长期稳定质量门禁的迁移方案

> 这是草稿候选分支的工程配置，不是自动合并、正式发布或GitHub强制保护规则。
> 知学伴面向**所有有学习需求的群体**，不限定任何考试或职业。

## 本次已建立

- `.github/workflows/stable-quality-gate.yml`：统一且固定的工作流名称、Job名称与检查路径，供后续稳定候选复用。
- 能在该第41阶段分支、`integration/**`、`release/**` 分支推送时触发；支持到相应目标分支的PR，以及 `workflow_dispatch` 和 `workflow_call`。
- `concurrency` 限制同一个分支或PR上重复运行的过时检查，减少不必要的Actions消耗。
- 同一次运行包含：主分支祖先检查、Web构建、Python依赖、集成清单与审计测试、Agent测试、85项后端质量测试、ZIP验证器测试、实际打包ZIP、打包后API测试、SHA-256摘要。
- 不上传私有源代码ZIP为公开Artifact；GitHub Actions本身仍可能在仓库中保留运行日志。

## 特意没有修改的东西

- 未删除或禁用旧的 `phase34` 至 `phase40` 工作流，也未删除 `web-ci.yml`，它们仍用于历史分支回溯及目前main的检查。
- 尚未给 `main` 增加新 `pull_request` 触发器，避免与现有 `web-ci.yml` 重叠。正式迁移时需要另起PR，先验证旧CI和新CI一致，再安全切换。
- 未启用合并队列、自动合并、分支保护或Required Checks。当前私有仓库的GitHub Rulesets查询返回HTTP 403：“Upgrade to GitHub Pro or make this repository public to enable this feature”。因此不能宣称仓库已强制保护main。
- 没有采用部署生产密钥、外部付费大模型或真实用户数据。

## 实际使用和限制

稳定检查在当前全功能候选分支上测试。对比旧的阶段性CI，Job名称固定为 `Stable quality / Web + Agent + ZIP`，便于将来统一查看Checks。

该工作流依赖后端Agent、评测脚本和统一发布清单。如果一个较旧的 `integration/**` 或 `release/**` 分支缺少这些文件，会被检测为失败。这属于候选基线不满足完整验证所需组件，不应随意跳过检查来得到绿色。

对于未来希望长期维护的分支，如果 `docs/integration/phase40.json` 存在，将继续检查其固定SHA祖先；如果main或提交历史发生更新，要更新该审核快照并再运行CI，而不能把过时的Git历史当成现时证明。

## 正式迁移的人工审核步骤

1. 确认本PR的新CI完整通过，并记录head和Actions链接。
2. 在单独的PR中，处理仅在阶段开发分支生效的重复工作流：停用不再需要的触发器（或归档配置），保留历史PR/Actions证据。
3. 若要将稳定质量检查应用到main，先评估 `web-ci.yml` 的迁移，避免同一提交重复跑两组长CI；再由用户明确批准合并。
4. 重新审查8条仍分叉的侧链PR（#16/#18/#25/#26/#27/#33/#34/#35），不要仅凭功能移植就关闭它们。
5. 如果将来计划正式发布，仍必须完成真实Docker启动、实际Qwen生成与人工题目质量复核、Android设备验收和模型资源测量。

当前状态只能称作**离机稳定质量候选**，不能称为生产可用，也不应对外宣称项目已经上线。
