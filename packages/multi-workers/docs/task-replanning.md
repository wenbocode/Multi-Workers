# PM 重规划

在已认领 key 的 MW PM 窗口输入 `/mw replan` 检查剩余工作。输入 `/mw replan <任务 ID 或卡名>` 检查一张卡。PM 在 spec 阶段按可独立验收的结果划分 key，在 design 阶段核对接口、共享资源和集成验收的归属。执行中的重规划沿用该 key 已确认的目标和验收标准。

| PM 工具操作 | 输入 | 结果 |
| --- | --- | --- |
| `replan_tasks inspect` | 当前 key，可选任务 | key 的复盘事项、卡和在途任务。指定任务还会返回原卡、运行分类、报告和产物位置，以及本次检查的 `issue` 和 `snapshot`。 |
| `preview` | 相同 key、issue、snapshot，以及 PM 提出的 plan | 校验 AC 覆盖、卡片、写入范围、资源和依赖。返回版本、裁决依据 ID、可先派发的卡及等待原因。 |
| `apply` | 相同 key、issue、snapshot、version，涉及编排变化时附匹配的 decision_id | 发布后继任务卡并持久化依赖。恢复时使用相同版本重试。正常派发入口仍负责投递队列和执行时检查。 |

每张后继卡提供新卡名、完整 Markdown、`covers`、`depends_on`、`resources`、可复用产物、首个验证动作和预期证据。资源数组为空表示明确没有独占资源。两个单元都要写同一文件或使用同一独占资源时，PM 应写明先后依赖。已经完成或另有归属的 AC 在 `retained` 中逐项列出证据或负责人。

`split`、`narrow`、`direct-exec`、`escalate` 复用 `ask_decision(dp-pm-steer)`。PM 将 preview 返回的 `basis_id` 放入对应分支的现有 `basis_catalog` 项，使用原协议要求的真实材料和引用。已有运行使用 `facts.task` 作为 `task_key`，未开工卡使用 key 级裁决。apply 核对项目、key、任务、选择和依据。裁决支持其它分支时，PM 按该分支重新预览。接手或上抛时先执行动作，以显式 `event_id` 写 executed 回执，apply 时将同一个 ID 作为 `action_evidence`。单纯调整已有独立卡的顺序可使用 `schedule` 和 `ready_existing`，重新派 worker 时继续使用原有 `dp-w-type`。

Launcher 为当前运行已确认的 wall 或 idle 硬超时保存复盘事项。启动补扫和 PM 检查可恢复离线期间的事项。队列锁内的检查覆盖交互派发和 autopilot。原卡改派任务 ID、已发布卡重复派发、未就绪依赖及半发布版本都会被拦截。只排其它工作或确认已读会保留原任务的阻塞。模型不可用或进程启动失败可在 PM 检查后换新的运行 ID 重试。每次运行的复盘记录在对应 key 的 `evidence/replan/`，原始 worker 产物可继续复核。
