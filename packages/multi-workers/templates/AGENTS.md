## Multi-Workers 协作约定

直接收到用户需求的 Agent 默认担任 PM。收到 MW 派发的 `task.md` 时，以 worker 身份执行卡上的工作项，沿用卡上的 key。

阅读项目已有的 `CLAUDE.md` 或 `CLAUDE.MD` 中的项目约定。流程入口为已安装的 `agentic-task` skill。

### 开始工作

- **讨论时**可以直接阅读代码、核对现状、比较方案。进入开发时，先读控制工作区的 `.agenticdoc/goal.md`，按 AgenticTask 建立或认领对应的 key。
- **实施前**在 `.agenticdoc/<key>/` 完成正常流程：在 `spec.md` 确定验收标准，在 `design.md` 明确实现和验证方法，在 `plan.md` 划分工作项和依赖，将可执行的任务写进 `tasks/`。按框架门禁推进阶段。项目已有的极小修复约定仍可使用。
- **接续时**从 `.agenticdoc/_index.parallel` 核对 key 和认领者，打开该 key 的 `pm-state.md` 查看 PM 方式、阶段和下一步。有在途任务先查状态与产物。

### 每个 key 选择一个 PM

在框架生成完整的 `pm-state.md` 后，由认领该 key 的 PM 在 `Snapshot` 中写入下表的一行。恢复已有 key 时沿用已记录的方式。双方约定移交 PM 时，在 `Decisions` 记录原方式、新方式、在途任务和接手人，并按框架流程交接认领，再更新 `Snapshot`。

| `pm-state.md` 中的记录 | 谁负责计划、执行和验收 |
| --- | --- |
| `- PM mode: mw` | 由 MW PM 按现有编排流程组织任务、派工和验收。 |
| `- PM mode: codex` | 由 Codex 担任 PM，使用内置流程推进同一份计划，也可把其中一项派给 MW worker。仅 Codex PM 创建、阅读和维护本 key 的 `codex_doc.md`。 |

Codex PM 从 `.agenticdoc/templates/codex_doc.md` 复制模板到本 key，已有执行记录时继续更新。该记录引用共享的计划、卡片和证据。MW PM 和 worker 按共享文档及派发的任务卡工作。

### PM、worker 如何交接

- PM 从同一 key 的 `tasks/` 派出任务，卡上写明对应验收标准、剩余交付、依赖、已有证据、目标工作区、可改文件和验收命令。任务卡应足以让 worker 独立开工。派出单项工作后，当前 PM 继续负责整个 key。
- Worker 依派发的任务卡实施，在目标工作区验证，并在控制工作区的本次运行目录用 `output.md` 交付改动、验证结果和遗留。
- PM 检查实际改动和报告，按卡验收，在本 key 的 `evidence/` 留存结果，并在 `pm-state.md` 更新任务状态和下一步。

### 完成与交接

逐条对照验收标准，区分实现者自验和另一执行者的复核。仍有未验证项时，写明缺什么证据、由谁继续。PM 汇总证据，按当前 AgenticTask 流程完成质量门禁、结案和释放认领。项目的构建、测试和代码风格沿用本项目已有约定。

<!-- mw:agent-collaboration -->
<!-- mw:agent-collaboration-version: 2 -->
