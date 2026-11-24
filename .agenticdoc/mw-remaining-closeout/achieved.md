# 剩余开发收尾交付

## 系统行为变化

- Multi-Workers 源码提交 `61e40b19882b3676b8baae9cbb2cb02eb1a491a7`，126 个文件。原 key 与逐文件归属见 `docs/mw-remaining-review-list-20261124.md`；精确冻结输入为 `evidence/scoped-files.json`。
- 接续签收冻结元数据、UE 插件框架安装、检查基线、版本入口、GLM-5.4 和遗留回归。修复值守中“通知未发出却显示允许发送”和“reserved 崩溃恢复被误当作确定 queued”问题。DP/PM 的循环与权限、证据检查保留。
- 检查模型快照固定为 `90ace0f6f942ff8b6f2cc51cf6f0cb5456b45fba` 的目录与 manifest，提交新版运行模型目录后仍可复现检查基线。运行模型目录继续保留 GLM-5.4。
- 全局 MW、pi 和扩展已切到 `mw-remaining-closeout-20261124`，pi 0.83.0。本仓库无 pending/running Worker 时重启后台，PID 71188，实际运行路径与全局默认一致。旧入口和扩展保存在新发布的 `deployment-backup`。
- AgenticTask 独立审查提交为 `dd0e6f3`。推送时发现远端 `84bbc2788c9555b350821056f206a698dc6db375` 已包含完全相同的源码树；核对零差异后快进独立克隆，无强推或重复提交。八项目实际 skill HEAD 与 Claude 适配器均已更新并逐文件核对为 `84bbc27`。
- 原开发克隆仍在 `packages/multi-workers/.tmp/agentic-task`，HEAD=df8ecf6，原索引、全部跟踪文件字节和 diff 均保持。Multi-Workers 的旧 skill junction 与其他项目旧 skill、Claude 四目录保存在各项目 `.mw/agentictask-signoff-rollout-20261124/`；当前八个 skill 都是干净的正式安装克隆。

## 验收

本轮是 Codex 自验，没有新增独立执行者复核。原 key 的历史独审与失败记录不改写。

| 标准 | 结果与证据 |
| --- | --- |
| AC-001 | 根 `npm run check` 通过；Python 983 项、TS 436 项、值守 30 项、UE 模板 10 项、AgenticTask 54 项，共 1513 项定向回归通过。日志分别为 `evidence/root-check-final.log`、`python.log`、`typescript.log`、`duty.log`、`template.log`、`framework.log`。 |
| AC-002 | 值守旧 27/3 红测收敛到 30/30；其他遗留夹具按现有注册、配置、当前候选和独立证据合同更新，没有减少拒绝分支或修改 DP 产品逻辑。对应最终联合回归通过。 |
| AC-003 | 冻结 MW 自检、pi 编译与启动通过；125 项源码及安装产物哈希与提交核对通过。八项目适配器与原开发克隆保全通过。见 `evidence/frozen-build.log`、`candidate.json`、`framework-installed.json`、`final-reconciliation.json`。 |

三条 AC 的正式证据：`evidence/codex-pm/self/1795524474968860000-2t6sy2yc/result.json`，verdict=passed；同目录 `command.log` 记录最终实际路径、版本和复核结果。

## 遗留

- 已打开的 pi 窗口仍保留其进程内版本，需 `/reload` 或重开；其他项目正在运行的后台不在本轮重启。新启动默认入口已经是新冻结版。
- 原完整 SDD key 的旧阶段、行政停止记录及其他仍存活 PM 的认领保留，不以本轮自验伪造其 QG、独审或原生结案。
- 根工作区残留的历史运行台账、临时快照与其他 dist 生成物未混入源码提交。原开发克隆的未提交内容按用户要求保留。
- 无新增业务功能待实施。真实 UE/UBT、付费模型请求及 RenderPerformance 试点仍按原约定另行验证。
