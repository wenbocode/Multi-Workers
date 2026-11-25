## Multi-Workers 协作约定

本节取代前面版本化的 MW 协作章节；项目其它约定继续有效。直接收到用户需求的 Agent 默认担任 PM；收到 MW 派发的 `task.md` 时，以 Worker 身份执行卡上的工作项，沿用卡上的 key。

先阅读项目已有的 `CLAUDE.md` 或 `CLAUDE.MD`，以及控制工作区的 `.agenticdoc/goal.md`。MW PM 使用已安装的 `agentic-task` skill；Codex PM 按下面的轻量入口工作。讨论和只读调查可以直接进行，实施前必须有已认领的 key。

### Key 和任务卡规模

- 一个 key 只交付一个能在目标环境走通的用户竖切。Spec 控制在一页，最多 5 条 AC 和 10 张卡。超过任一数量时，PM 在 spec 阶段拆 key 后再推进。
- `research` 和 `review` 卡片的 `timeout:` 至少 30 分钟。
- 每张卡写明可观察结果和验收命令的预期退出码，并至少经真实入口调用一次；脚本或测试能触达就不拉真机，重型真机留证只在竖切收口做一次。中间 `coding` 卡验编译通过、最小正例和必要的破坏性负例（中途取消、目标失效、底层不可用时不得报就绪）。PM 先复核实际 diff，改动涉及异步、取消、绑定或失败态路径时另派独立评审。防伪走宿主工具，非 `spec_goal` 产品不自写证据一致性脚本。卡片的 `write_face` 覆盖正文点名的每个编辑目标。

### 每个 key 选择一个 PM

| PM 与流程记录 | 计划、执行和验收方式 |
| --- | --- |
| `pm-state.md` 中 `- PM mode: mw` | 完整 AgenticTask：`spec → design → plan → tasks → execute → verify → done`，沿用原阶段、质量和签收门禁。 |
| `codex_doc.md` 中 `- Workflow: codex-lite` | Codex PM 轻量流程：主记录保存目标、范围、编号验收标准、决定、进度和接续信息；`achieved.md` 保存实际交付与遗留。 |

已有完整 SDD key 继续原流程；`PM mode: codex` 本身不把已有任务转换为轻量任务。PM 交接需记录原方式、新方式、在途任务和接手人，再按目标流程完成认领。

### 完整 SDD 的 PM 接续状态

- 将 `pm-state.md` 当作当前接续页，原位更新目标、在途任务、阻塞、下一步、仍有效的决定和证据引用。轮末检查结论记入对应小节，历史轮次、过期快照、原始日志和详细报告存于证据、任务卡或归档。
- 建议正文控制在 8 KiB 以内；超过 16 KiB 时参考 MW checkout 的 `packages/multi-workers/docs/pm-state.md`，使用 `python packages/multi-workers/mw.py pm-state compact` 预演并压缩。框架维护的字段与质量门禁条目由命令保留。

### Codex PM 开始、恢复和结案

- 使用 `packages/multi-workers/codex_pm.py init --project <控制工作区> --key <key>` 建立轻量 key，填写生成的 `codex_doc.md`。任务只需要一份主记录；实施前明确目标、范围、`- AC-001: ...` 验收标准和接续须知。
- `init` 从 `SPEC` 开始；`advance --phase EXECUTE` 通过主记录校验后进入实施，`advance --phase VERIFY` 进入验收。所有命令显式指定 `--key`；多个 `ClaimId: codex` 不能用于猜测当前任务，也不用于区分窗口。同一个 key 由一个 PM 推进。
- `_index.parallel` 保留真实的 `SPEC / EXECUTE / VERIFY / DONE`、active/idle 和认领信息；活动轻量认领统一为 `codex`。`_index.md` 的 `active_keys` 是共享锁内生成的完整投影，不是授权依据。轻量状态由 Codex 接口同步维护，不手改索引或机器字段。
- 轻量 key 的 `pm-state.md` 仅保留认领接口和 `Phase: init`。AgenticTask 原脚本保持原语义；它的“尚无 SDD 阶段可审计”不是轻量任务验收通过。
- 接续时先运行 `status --project <控制工作区> --key <key>`，核对主记录、索引、在途 Worker 和证据。`release` 只释放认领并保留阶段；`claim` 恢复未结案的轻量 key，保持已有交付记录。已完成或完整 SDD key 不自动转换。
- Codex 自己执行的验证用 `check --ac AC-001 -- <程序及参数>` 保存命令和结果；按实际需要区分自验与另一执行者复核。证据绑定目标工作区、源码快照以及主记录的目标、范围和验收标准；同一工作区的其它源码改动也会使旧证据失效，最后一批编辑后重新验证。主记录引用证据路径，不重复复制日志。
- 完成全部验收后写 `achieved.md`，记录系统行为变化、验收证据和遗留去向，再运行 `done --summary <交付摘要>`。结案接口检查证据、在途任务和归属，写入回溯记录，把索引设为 `DONE / idle` 并释放 ClaimId。存在未验证项时保留任务状态和下一步。

### Codex PM 与 MW Worker 交接

- 只有转派工作才在同一 key 的 `tasks/` 建卡。卡片须写明目标及对应 AC、剩余交付、依赖、已有证据、目标工作区、可改文件和验收命令，使 Worker 可以独立开工。
- `dispatch --card <卡名> --claim-id codex` 使用 Codex 专属的轻量派发适配。任务卡、工作区、模型和写入范围等共享检查继续生效；普通 MW 派发仍检查原 SDD 文档。
- Worker 按卡片实施和验证，在本次运行目录用 `output.md` 交付改动、验证结果和遗留。Worker 无需创建 PM 过程文档；派出单项工作后，当前 Codex PM 继续负责整个 key。
- PM 阅读实际改动和报告，再用派发时的验收命令执行 `verify --card <卡名> --claim-id codex -- <程序及参数>`，将结果记回主记录。失败时明确修复项和已有证据，再派新卡。

项目的构建、测试、代码风格和提交授权沿用已有约定。

<!-- mw:agent-collaboration -->
<!-- mw:agent-collaboration-version: 3 -->
