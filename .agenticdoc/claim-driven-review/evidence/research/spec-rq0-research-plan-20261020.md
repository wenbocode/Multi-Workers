# spec-rq0: 调研计划与前馈（claim-driven-review）

> 类型：research plan（零调研声明 + 任务分配）。本文件不承载结论，只登记本相位的调研单元、
> 各自唯一证据文件、以及 PM 已确认的事实边界，避免 worker 重复发现或越界。

## 1. 本相位的调研单元

| 单元 | 问题 | 唯一证据文件 | 卡 |
|---|---|---|---|
| RQ-1 | review 类 run 的成本标定：取数次数、tokens/次取数、每次取数对应的判定单元数、失败形态分布 | `evidence/research/spec-rq1-review-corpus-20261020.md` | `tasks/RQ-1-review-corpus-calibration.md` |
| RQ-2 | 五个接缝（卡校验链 / 结算链 / 读面预算 / 类型与词汇表 / 度量）的最小插入点与破坏面 | `evidence/research/spec-rq2-seams-20261020.md` | `tasks/RQ-2-seams-inventory.md` |
| RQ-3 | 断言分类法、误拒反例集、绕过反例集、`## 断言裁决` schema、manual 档位 | `evidence/research/spec-rq3-claim-taxonomy-20261020.md` | `tasks/RQ-3-claim-taxonomy.md` |

三个单元互不重叠写面，可全并行；均只读仓库，除唯一证据文件外不写任何路径。

## 2. PM 已确认的事实（worker 不要重复发现）

- `ds-qg-review-2` 死于 214k 上下文：`trace.log` 记录 236 次工具调用（read 159 / grep 53 / find 10 / ls 10 / worker_file 4），read 覆盖 66 个不同文件；三次 attempt 后 `[MODEL_FALLBACK]` 落到 `timi/glm-5.3`。
- 压缩只在两处评估：`packages/coding-agent/src/core/agent-session.ts:1098`（整个 run 结束后）与 `:1209`（发送用户 prompt 前）；工具循环内不评估。
- `_checkCompaction` 的 overflow 分支认不出 `stream closed`：`packages/ai/src/utils/overflow.ts` 的 `OVERFLOW_PATTERNS` 无匹配项，且 usage 型判定要求 `stopReason` 为 `stop`/`length`。
- `read_scope` 拦截仅在任务带 `read_scope:` 或 `deny_globs:` 时装载：`packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts:254-275`；默认 caps 为 8 次 / 65536 B（`:31-32`）。
- PM 手工 `dispatch_worker` 没有 `read_scope`/`deny_globs` 参数（`pm/ui-bridge.ts` 内无该字段），conductor 才有渲染（`autopilot/dispatch.py:977-987`）。

## 3. 本相位的判据

- 三份证据文件齐备后，方可 `advance_phase claim-driven-review design`。
- 每份证据文件须带 `## 未覆盖面声明`，且每个数字附实测命令与输出摘要。
- 任何与第 2 节事实冲突的发现，必须在证据文件里显式标 `[CONFLICT]` 并给出反证。

## 4. 未覆盖面声明

本计划文件本身不做调研；不含任何结论性数字。三类问题不在本相位范围：pi 核心的循环内压缩改造、review 角色是否携带 `bash` 的决策、`read_scope` 既有默认值的调整。
