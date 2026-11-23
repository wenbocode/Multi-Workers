# mw-key-spec-goal · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-key-spec-goal
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

使 PM 和 Worker 在长会话、恢复和交接中保持对当前 key 交付目标的理解。通过稳定的简短目标延续项目 goal 对各阶段开发的指导。

## 范围

控制与目标工作区均为本仓库。负责目标的唯一来源、当前 key 绑定、PM/Worker 上下文注入与缓存验证。入口为 `shared/phase-docs.ts`、`pm/pm-orchestrator.ts` 和 Worker 扩展的会话启动与恢复路径。

## 验收标准

- AC-001: 完整 SDD 从 spec 的 §0 读取 spec_goal，codex-lite 从主记录的目标段读取。目标用两三句话说明交付结果、与项目 goal 的关系和完成事实。用一份 replan 前后夹具验证，规划变化时读取的目标文本相同。
- AC-002: 核对 PM 和 Worker 的实际模型请求。连续轮次、压缩、重启和 Worker 恢复时，请求中只有一份当前 key 的目标。切换 key 后使用对应目标，Worker 继续以卡片约束其操作范围。
- AC-003: 同一 key 连续轮次的 system prompt 中，目标段的字节、位置及其之前的静态前缀相同。用实际请求捕获做比较。运行时提供缓存读写数据时一并记录，缓存验收范围限于同一 key。

## 关键决策

- spec_goal 随 spec 定稿固定。replan 以同一目标为前提，可调整设计、任务拆分、依赖和顺序。PM 和在途 Worker 继续使用同一目标。PM 按现有任务卡流程处理需要重派的工作。
- 宿主复用已有 PM 和 Worker 的 system prompt 扩展入口，在原有静态指令后加入当前 key 的目标。每次装配从已绑定的 key 取目标，只放一份；进度、时间戳和重试次数沿用原有运行上下文。旧 key 缺少可读取的目标段时，继续原有流程。

## 设计

### 目标来源和定稿

- 完整 SDD 在 `spec.md` 的 §0 下使用 `### spec_goal`。把本 key 的交付、与项目 goal 的关系和可观察的完成结果写在这里，正文保留现有 §0 门禁所需的「预期收益」。Codex-lite 直接复用 `codex_doc.md` 的 `## 目标`，由 MW 宿主提取这一段供其运行的 Worker 使用。
- 共用一个目标读取函数。输入为控制工作区的 `.agenticdoc` 根和已确认的 key，按现有 `Workflow: codex-lite` 标记或完整 SDD 文档选择来源。读取指定段落，按 Markdown 标题边界截取，忽略注释中的模板占位并统一换行。由 PM 在规格阶段校对内容和项目目标的关系。
- replan 沿用已定稿的目标原文。计划更新时只读取规格目标；如果现有流程归档后重建 `spec.md`，把确认过的目标原样留在新文件的 §0。使用现有文档和版本记录追溯，避免额外存一份目标或建立独立门禁。

### 请求装配

| 入口 | 取值和行为 |
| --- | --- |
| MW PM | `pm-orchestrator.ts` 在每轮 `before_agent_start` 用当前 `watch.key` 和 `claimedPmKey` 校验当前窗口认领。会话重启复用 `restoreWatch`。切换或释放后，下一轮按最新绑定重建目标段。只有观察权或缺少有效绑定时，请求只带原有提示。 |
| MW Worker | `worker-mode.ts` 在通用入口按当前运行的 `owner_key` 和 `trueAgenticdocRoot` 读取目标。接卡和恢复都按这一归属取目标。只把目标段交给模型，卡片及现有工具读写权限继续约束执行。 |
| 两种角色 | 在基础 system prompt 和原有角色指令后追加一份固定格式的目标段。每轮从基础 prompt 组装，轮内工具续跑沿用该轮的 prompt。压缩后的首个工作请求仍使用同一目标。旧 key、`_scratch` 或目标段不可读时直接沿用原有提示。 |

注入在 MW 的 pi 扩展内完成。缓存比较固定同一 key、模型、工具配置和其他系统指令，记录实际请求里目标开始的位置和此前的字节；进度变更留在原有消息上下文。

### 实施和验证顺序

1. 实现共享读取和固定格式渲染。用完整 SDD、codex-lite 和缺少目标的旧 key 做测试夹具。对同一个 key 更改设计、计划，另测归档重建规格后目标段原样保留，验证渲染结果一致。
2. 接入 MW PM 和 Worker 的扩展钩子，用可捕获请求的测试 provider 验证首轮、多轮、工具续跑、压缩后的工作请求和恢复。切换到另一个有不同目标的 key 后，只出现新目标；释放认领后无残留。Worker 用其所属 key 的目标，并验证原有写入边界仍有效。
3. 在同一 key 的两轮之间改变进度或计划，逐字节比较实际请求的静态前缀和目标段。测试 provider 验证请求结构；实际运行环境报告缓存读写时保存指标，未报告时记为不可观测。

## 执行与验收

已接入 PM 和 Worker 的 system prompt 装配。Codex PM 自验覆盖三条 AC 和相邻回归，共 31 项通过。另有两项既有 PM 常驻规则测试通过。完整 npm 检查在隔离源码副本通过，验收所用改动文件与工作树字节一致。 [AC 验收记录](evidence/codex-pm/self/1795450266406064500-jbdbv8qx/result.json) [npm 检查](evidence/npm-check.txt)

## 接续须知

后续真实窗口验收归入 `mw-dp-window-acceptance`。本 key 的源码和验证结果见 [交付记录](achieved.md)。

恢复时先运行 `python -B packages/multi-workers/codex_pm.py status --project . --key mw-key-spec-goal` 核对认领与阶段。
