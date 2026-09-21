# 基线：缺陷态事实记录（改动前）

> key: mw-dispatch-role-escape / 2026-09-20
> 说明：本 key 的「基线」是**缺陷态事实**（外部产物 + 改动前源码），不是 L2 运行基线 ——
> 新参数与新门禁在改动前根本不存在，无法构造等价运行基线。质量门禁如需运行基线，按此口径判定。

## B-1 外部产物（H:\git\E2Feature，2026-09-19 ~ 2026-09-20）

| 事实 | 值 | 来源 |
|------|-----|------|
| 任务类型 | 14/14 worker task.md 均为 `type: coding`（含 review 语义任务 `review-slicing-algorithm-spec`） | `.agenticdoc/slicing-algorithm-spec/workers/*/task.md` |
| 任务模型 | 其中 13 个带 `model: gpt-5.6-sol`（review 档模型） | 同上 |
| 配置 | `.mw/dispatch.yml` = `models: {coding/main/research: timi/deepseek-v4.1-flash, review: timi/gpt-5.6.sol}` | `.mw/dispatch.yml`（145B） |
| 后果 | coding 档配置从未生效；review 档值 `timi/gpt-5.6.sol` 是错 id（timi 表无此 id） | 用户审计报告 2026-09-20 |

## B-2 改动前源码事实（本仓 HEAD a395b0af2）

| 事实 | 位置 |
|------|------|
| 任务类型由 cli 推导，pi 恒为 `coding` | `ui-bridge.ts:925`（dispatch_worker）/ `:1219`（/worker） |
| `model` 直写 task.md，无校验/无理由/无回显 | `ui-bridge.ts:859,930,942` |
| 结果文本把 cli 当 type 回显 | `ui-bridge.ts:942`（`type: ${cli}`） |
| 合法 id 集合中无 `gpt-5.6.sol` | `packages/ai/src/providers/data/timi.json`（有 `gpt-5.6-sol`） |
| 未知 id 在 pi 侧被静默当 custom model id | `core/model-resolver.ts:174-190,590-598` |
| 无 type/override 相关测试用例 | `agent-team-loop.test.ts`（改动前 158 用例，grep `model_reason`=0） |

## B-3 判定口径

- 修复前：`dispatch_worker` 无法产出 `type: review`；`model` 覆盖无理由约束；错 id 不被拦。
- 修复后：见 `evidence/runs/run-2026-09-20.md`（端到端 smoke + 168/692 测试 + check 0/0/0）。
- 因此本 key 的「充分性」以**修复后证据**为准，基线仅用于说明缺陷态与回归对照面
  （回归对照 = agent-team-loop 原 158 用例 + multi-workers 原 688 用例全绿）。
