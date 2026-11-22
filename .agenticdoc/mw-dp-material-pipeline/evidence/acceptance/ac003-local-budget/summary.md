# AC-003 本地预算与正式签收

2026-11-23，用户授权将 AC-003 改为本地预算，正式合同重冻结仅替换 `AC-003` 与 `VC-003`。宿主在共用投影入口检查最多 10 句及 `desc-local-v1`。规则用 LF 拼接原始 `desc` 数组，每个非 ASCII 码点计 1，全部 ASCII 码点每 4 个计 1 并向上取整。实际计数和是否超限都在发送前由宿主确定。 [spec](../../../spec.md) · [design](../../../design.md) · [重冻结回执](contract-freeze-receipt.log)

| 用例 | PM `dp-w-type` | Worker `dp-w-check-task` |
| --- | --- | --- |
| 1000 单位 | 1 次回环 POST，`codingA` | 1 次回环 POST，`continueA` |
| 1001 单位 | `input-incomplete`，0 次 POST | `input-incomplete`，0 次 POST |
| 10 句 | 1 次回环 POST | 1 次回环 POST |
| 11 句，尾句无标点 | `input-incomplete`，0 次 POST | `input-incomplete`，0 次 POST |

两角色超限诊断均指向 `preparation.model_context.desc`，带实际计数和上限。1000/1001 样例分别使用 999 个汉字加 LF 和 3/4 个 ASCII 字符，覆盖了拼接和向上取整。现场 Worker 终态为 `done`。回环捕获仅含预期的决策 POST。 [PM 工具及反馈](pm/normal-entry.json) · [PM 请求和回包](pm/loopback-transcript.json) · [Worker 工具及反馈](worker/normal-entry.json) · [Worker 请求和回包](worker/loopback-transcript.json) · [Worker 终态](worker/run.json)

T08 定向测试 170 通过、1 跳过。隔离源码副本的 `npm run check` 通过。v0.5 九例四段共 36 项，32 项差异有据、4 项符合预期拒绝。八个实际发送样例均从请求中实际发出的 `desc` 复算本地预算。旧 dp-auto 的当前 PM 零发送接回有据，历史回执仍为空。 [T08](t08-pytest.log) · [仓库检查](npm-check.log) · [36 项对账](v05-four-stage-comparison.md) · [旧 dp-auto 接回](dp-auto-current-pm-handoff.json)

T09 终态 Worker 独立确认 18 组 AC/VC 和 3 条流程。正式 QG 为 `verified / pass`，未关闭项为 0。`mw decide sign` 经 `pm-evidence` 入口返回 `finalize / written`，回读确认 `sign-final.md` 有效。首次签收在 Windows 沙箱的原子文件替换处受限，正式写入在同一次独审证据上重试完成。当前 key 阶段为 `VERIFY`。 [独立复核](../../../workers/cx-ee474fbc353feb7aba95/report.md) · [正式 QG](../../quality-gate-report-ac003-cx-ee474fbc353feb7aba95.md) · [QG 清单差异](open-criteria-diff.json) · [签收回执](official-sign-result.json) · [签收回读](official-sign-execution.json) · [签收文件](../../review/sign-final.md)
