# MW 精简批 0/1 Review List

2026-11-24 后续收尾已提交并安装 MW `61e40b198`，八项目 AgenticTask 已更新为 `84bbc27`。下文保留精简批首次交付的历史基线；当前版本、逐文件 key 归属和复验证据见[剩余开发收尾清单](mw-remaining-review-list-20261124.md)。

复核基线为 Multi-Workers `606ee4014`、AgenticTask `df8ecf6` 和已安装的用户级版本 `mw-lean-2395dd1af7`。AgenticTask 的 `origin/master` 已核对指向 `df8ecf6`。设计中的 RenderPerformance 试点另行验收。 [设计](mw-lean-design-plan-20261124.md) [源码结案](../.agenticdoc/mw-lean-execution/achieved.md) [发布结案](../.agenticdoc/mw-lean-global-release/achieved.md)

## 功能与边界

| 设计项 | 修改面 | 复核清单 |
| --- | --- | --- |
| §2.1 用量终态 | `launcher.py`、`mw_common.py`、`usage.py` | 核对进程退出 0 且 `run.json` 需澄清时队列和账本一致。缺产品时记录退出码来源，缺少 Worker run ID 的样本单列。同卡 exit 3 重派先结算旧轮次。重启回收还要核对项目、当前轮次及旧 `[END]`。 |
| §2.2 账本警告 | `worker/output-writer.ts`、`worker/worker-mode.ts` | 核对未记录写入和无法判断的文件仍见于警告。缺段、断言和动作时写面限制继续生效。 |
| §2.3 只读交付 | `shared/deliverable-evidence.ts`、`worker/worker-mode.ts` | 核对本次 trace 记录的非空、新鲜、位于本 key `evidence/` 内的报告可用于收尾。覆盖简短裁决或链接、已有完整本地报告、旧轮次产物、其他 key、越界路径和链接指向。 |
| §2.4 只读预算 | `worker/worker-mode.ts` | 核对 research/review 卡片显式超时取至少 30 分钟。45 分钟预算仍为 45 分钟，coding 按原规则计算。核对硬墙钟、固定预算和有进展时的人工续期入口。 |
| §2.5 PM replan | `replan_tasks.py`、`pm/replan.ts`、`pm/decision-tool.ts`、`pm/pm-orchestrator.ts`、`docs/task-replanning.md` | 核对 split、narrow、direct-exec 在无 DP 裁决时可由 PM 发布并留来源。显式裁决继续校验，escalate 仍需裁决。覆盖在途 Worker、快照变化、卡名冲突和超时后继。 |
| §2.6 项目规则与派发 | 根 `AGENTS.md`、各项目 `.mw/dispatch.yml` | 核对一版协作约定、一页 spec、单 key 一条竖切、最多 5 条 AC 和 10 张卡。七个项目的 research 与三组备用模型链核对见下节。 |
| §2.7 PM 默认路径和阶段推进 | `pm/pm-orchestrator.ts`、`shared/phase-docs.ts`、`shared/pm-state-guard.ts`、`autopilot/audit_evidence.py`、AgenticTask `advance_phase.py` | 对照同一条用户路径，检查三张计划表、并行派发、按需调研和规模提示。分别走原生推进、交互派发、后台扫描和 Autopilot，核对缺调研文件时可继续，文档显式引用的证据仍须存在。 |

回归重点是 PM 根据 Worker 结果继续推进的循环。可同时核对写面守卫、DP 升级裁决、QG、签收和验收证据的原有入口。 [源码验收](../.agenticdoc/mw-lean-execution/evidence/verification.md)

## 配置与安装

- [ ] 七个项目已回读派发配置。项目为 Multi-Workers、Bearing、AssetsGate、Gaze、RenderPerformance、SceneProfiler 和 UEPerformanceFlow。`models.research` 为 `timi/deepseek-v4.1-flash`。备用链使用原有同模型重试后的切换入口。

  | 角色 | 备用模型顺序 |
  | --- | --- |
  | `coding` | `zhient/gpt-6.1-sol` → `toa/hy4` |
  | `research` | `zhient/gpt-6.1-sol` → `toa/hy4-flash` |
  | `review` | `timi/deepseek-v4.1-flash` → `zhient/gpt-6.1-sol` |

- [ ] 用户级 `mw`、`pi`、MW 扩展和路径 sidecar 指向同一冻结发布。核对 `mw version`、`pi --version`、扩展加载和 `deployment-backup`。已有窗口及项目后台以各自运行时版本为准。 [全局安装与回滚](../.agenticdoc/mw-lean-global-release/achieved.md)
- [x] AgenticTask `df8ecf6` 已安装到 Multi-Workers、Bearing、Overcode、AssetsGate、Gaze、RenderPerformance、SceneProfiler、UEPerformanceFlow 八个项目。逐项核对 skill HEAD、全部框架文件和 Claude 四个目录。Multi-Workers 开发克隆保留原修改及 junction，其余项目为干净副本。 [安装核对报告](../.agenticdoc/agentictask-df8ecf6-rollout/evidence/installed.json)
- [ ] `mw-repo-check-baseline` 修复了 Biome 嵌套根配置扫描和 AI 源码模型目录漂移，作为复验前置。两处修复由该 key 独立记录。 [基线验收](../.agenticdoc/mw-repo-check-baseline/achieved.md)

## AgenticTask 如何分发到现有项目

1. 从 AgenticTask 的 `origin/master` 获取 `df8ecf6`，或者选用已包含这条提交、经确认的后继版本。用全局 `mw pull-agentictask --branch master` 更新缓存，并取输出中的框架目录作为安装源。核对安装源的提交和工作区清洁度。 [MW 缓存入口](../packages/multi-workers/mw.py) [AgenticTask 安装入口](../packages/multi-workers/.tmp/agentic-task/install.py)

   ```powershell
   mw pull-agentictask --branch master
   ```

2. 逐项目检查 `.agents/skills/agentic-task` 的工作区、分支上游和快进条件。保留 `.claude/commands`、`.claude/agents`、`.claude/skills`、`.claude/scripts` 中的项目定制，因为安装器会重建这四个目录。先在一个项目验证，再对其余项目重复。现存项目可直接运行框架安装器。

   ```powershell
   # $framework 是步骤 1 核对过的独立 AgenticTask 源目录。
   $project = 'E:/MWWS/RenderPerformance'
   $skill = Join-Path $project '.agents/skills/agentic-task'
   git -C $skill status --short --branch
   python (Join-Path $framework 'install.py') $project
   if ($LASTEXITCODE -ne 0) { throw "AgenticTask install failed for $project" }
   git -C $skill rev-parse --short HEAD
   Get-Content -LiteralPath (Join-Path $project '.agentic-framework')
   Get-FileHash -LiteralPath (Join-Path $project '.claude/scripts/advance_phase.py'), (Join-Path $framework 'claude/scripts/advance_phase.py')
   ```

3. 核对项目 skill 的实际 Git HEAD 与选定版本一致，Claude 脚本哈希和安装源一致。之后重开或重载窗口，刷新会话内已载入的技能。`.agentic-framework` 记录安装源版本，核验时同时检查实际文件。

本轮安装使用 `E:/gitlite/Multi-Workers/.mw/agentictask-df8ecf6` 这个干净源。Multi-Workers 的 `.agents/skills/agentic-task` junction 继续指向开发克隆，HEAD 为 `df8ecf6`，原有正式签收门禁及测试修改逐字节保留。八个项目的 `.claude` 均由干净源刷新，七个普通项目的 skill 安装为干净克隆。原 skill、Claude 副本和安装记录保存在各项目 `.mw/agentictask-df8ecf6-rollout/`，SceneProfiler 和 UEPerformanceFlow 的旧本地修改随旧 skill 完整备份。 [逐项报告](../.agenticdoc/agentictask-df8ecf6-rollout/evidence/installed.json)

## 验收与复核入口

- [ ] 对照最新复验日志的 `npm run check`、548 项定向测试和七项目配置回读。历史回放包括 33 条账本误判、仍可见的 95 个警告路径和 5 条只读交付。Windows junction 子用例在本机受沙箱限制。 [验收与历史回放](../.agenticdoc/mw-lean-execution/evidence/verification.md)
- [ ] 最后做成对的运行入口核对。新进程检查用户级 `mw`、`pi` 和扩展版本，项目内检查 AgenticTask 的两套适配器。RenderPerformance 试点中另记实际运行版本和从需求确认到主流程走通的耗时。 [安装验收输出](../.agenticdoc/mw-lean-global-release/evidence/codex-pm/self/1795519159497742300-uirvw8nh/command.log)

两个提交的完整文件清单与 diff 可从以下命令取得。

```powershell
git show --name-status 606ee4014
$repo = 'E:/gitlite/Multi-Workers/packages/multi-workers/.tmp/agentic-task'
git -c "safe.directory=$repo" -C $repo show --name-status df8ecf6
```
