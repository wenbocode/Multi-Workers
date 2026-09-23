# Task T-14-PHASE-AXIS: task.md `phase:` 头双侧落地 + worker 末态 `rag-required-missing` 发射

## 基本信息
- Stage: 5
- 依赖: T-04（工具面/worker 注入）、T-05（证据行）、T-09（`research-doc.ts::researchDocEvidence`）、T-10（audit 的 `phase:` 解析）
- 完成状态: 未开始
- 验证状态: 未验证
- 完成 Agent: worker（`coding` 类型）
- ac_refs: [AC-010, AC-015, AC-016]
- vc_refs: [VC-014, VC-020, VC-021]
- pattern_refs: []

- **`[VERIFY]` 行的发射通道**：本仓库 vitest `silent: "passed-only"` 会吞掉绿灯用例的 `console.log` —— TS 侧必须用
  `process.stdout.write("[VERIFY] ...\n")`；Python 侧 `print` + `pytest -q -s`。

## 背景（为什么必须做）
`required = role.require OR phase.require` 是 spec 的硬语义（AC-015 / VC-020），但**阶段轴现在是死的**：

- `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts:118` 会**解析** task.md 的 `phase:`；
  `packages/multi-workers/mw.py:1779-1787`（T-10 的 audit）也**解析**它；
- 但**没有任何代码写它**：TS 的 `dispatch_worker` 只写 `type:`/`model:`/`model-reason:`（`pm/ui-bridge.ts:857-917`，落盘在 `:1080-1081`）；
  Python conductor 的 `render_task_md`（`autopilot/dispatch.py:175-224`）只写 `type:`/`model:`/`origin:`/`loop:`/`attempt:`/`read_scope`/`deny_globs`。
- 后果：`target.yml` 里 `phases.<X>.require` 在生产中永远不会触发；AC-015 的“仅 phase.require 为真也要告警”只有手写 fixture 能测到。
- 另外 VC-014 的 **TS 面**（worker 末态发 `rag-required-missing` + 在 `output.md` 标注）也还没落地 —— T-09 已把发射函数备好
  （`rag/research-doc.ts::researchDocEvidence(report, role, phase, server)` → T-05 的 `ragRequiredMissingLine`），但无人调用。

## 源码
1. **Python conductor 侧写入**：`packages/multi-workers/autopilot/dispatch.py`
   - `render_task_md(...)` 增可选 `phase: str = ""`；**非空才**在 frontmatter 里 `type:` 之后输出 `phase: <P>`（空 = 零字节变化，既有 task.md 与既有测试不变）。
   - `dispatch(...)` 在能确定所属 key 的当前阶段时传入（从 key 的 `pm-state.md` 的 `- Phase:` 行读；`_scratch`/未知 → 不传）。
2. **TS `/worker` 侧写入**：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
   - `dispatch_worker` 的 frontmatter 构造（`:857-917` 一带）在能确定 owner key 的阶段时追加 `phase: <P>`；
     owner key 为 `_scratch` 或阶段未知 → **不追加**（保持既有 task.md 逐字节不变）。
3. **worker 侧解析**：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
   - `parseTaskMd` 增读 `phase:` → `TaskMeta.phase?: string`（与既有 `type:`/`model:` 同级；注意别和该文件里心跳用的 `phases` 数组混淆）。
4. **worker 末态发射（VC-014 TS 面）**：同一文件的任务收尾路径
   - 当该任务 `requiredFor(role, phase)` 为真、但全程**没有可核对引用**（无 `citation` 且 `exists` 可判定的结果）时：
     追加 `rag-required-missing role=<R> phase=<P> server=<S>` 证据行（复用 T-09 的 `researchDocEvidence`，**不要**自建第二个机制），
     并在 worker `output.md` 里加可机读标注（如 `## RAG` 段内的 `RAG 未生效：required but unused` 行）。
   - **幂等**：重复收尾/重跑不产生重复行；RAG 未启用或未 required → **零写入**（D-014）。
   - phase 取 task.md 的 `phase:` 头；缺失时用 `unknown`（**不要**猜）。

## 测试
- 新增 `packages/coding-agent/test/suite/rag-required.test.ts`：
  - `parseTaskMd` 能读出 `phase:`（有 = 该值、无 = undefined）；
  - required-but-unused → trace 出现 `rag-required-missing` 且 `output.md` 被标注；重复运行不重复追加；
  - 有可核对引用时不发该行；RAG 未启用时零写入；
  - 未启用/未 required 的回归：既有 task.md 解析与工具面行为逐字节不变。
- Python：新增 `packages/multi-workers/test_rag_phase.py`：
  - `render_task_md(..., phase="DESIGN")` 输出含 `phase: DESIGN` 行，且 `phase=""` 时输出与改动前**逐字节相同**；
  - conductor `dispatch` 在未知阶段时不写该行；
  - 与 T-10 的 audit 串起来：带 `phase:` 的任务 + 空引用 → `required_missing` 非空（复用 T-10 的测试辅助，不要复制它的断言逻辑）。
- **既有测试零修改**：`test_autopilot_l0.py`、`test_autopilot_dispatch.py`、`test_partition_dispatch.py`、`test_dispatch_models.py`、`test/suite/agent-team-loop*.test.ts` 必须不改且全绿。

## 完成判定
- [ ] TS：`node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-required.test.ts`（包根 `packages/coding-agent`）全绿
- [ ] TS 零回归：`test/suite/rag-*.test.ts` 全量 + `test/extensions/agent-team-loop*.test.ts` + `test/suite/autopilot-*.test.ts`
- [ ] Python：`python -m pytest test_rag_phase.py -q -s` 全绿并打印 `[VERIFY]`（包根 `packages/multi-workers`）
- [ ] Python 零回归：`python -m pytest -q`（非 e2e）
- [ ] 仓根 `npm run check` 0 error / 0 warning / 0 info
- [ ] 证据行（TS 用 `process.stdout.write`）：
      `[VERIFY] VC-014: required_unused_emitted=true output_marked=true idempotent=true`
      `[VERIFY] VC-020: phase_written=true worker_reads_phase=true audit_consistent=true`
- [ ] 不新增依赖；不 commit；不改 `rag/config.ts` 的配置 schema；不动 `index.ts`

## 注意
- **空 `phase` 必须零字节变化** —— 这是不让既有测试与既有 task.md 抖动的关键；先写“不传 phase”的等价性断言，再写新行为。
- `mw.py` 的 audit 已经按 key=value 读 `phase:`，**不要改 `mw.py`**（属 T-10 产物，且本任务的阶段写入必须让它的既有断言继续成立）。
- `pm-state.md` 的 `- Phase:` 行是脚本拥有的（`advance_phase.py`），只读不写。
- 若发现 worker 收尾路径（`worker-mode.ts`）拿不到 `output.md` 的写入点或没有“末态”钩子，**停下并在 output.md 写清**（附最小复现），由 PM 决定接线位置，不要自造第三个机制。
