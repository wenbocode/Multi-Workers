# T-02: 跨语言事件集合对齐（D3 守卫 + 新事件名单）

- 波次: **0** · 依赖: 无
- 写面（独占）: 
  - `packages/multi-workers/autopilot/timeline.py`（`EVENT_TYPES` 段）
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（`EVENT_TYPES` 段）
  - `packages/coding-agent/test/suite/autopilot-event-parity.test.ts`（新建）
- AC: AC-010, AC-021, AC-022 · VC: VC-012
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

两侧事件集合恢复相等，并把本 key 需要的 6 个新事件名先纳入允许集（生产者由 T-07/T-08 落）。判据是**排序后集合相等**，不是数量相等。

## 交付物

- TS 侧补既有缺失项 `target-config-rejected`（`status-model.ts:779-796` 现 16 类，Python `timeline.py:67-84` 有它）。
- 两侧同时加入 6 个新事件名：`gate-auto-decision` / `gate-auto-revoke` / `review-decided` / `review-escalated` / `evidence-reconciliation` / `stage-reopen-refused`。
- 新测试：读两侧常量并断言**集合相等**（无 `skipIf`、任一侧缺失即硬失败）；同时在卡内记录实际基数（T-02 完成后写进证据）。

## 契约（不得重定义）

- 事件名逐字一致，含连字符；不得改名、不得加别名。
- `EVENT_TYPES` 是允许集（fail-closed：未知类型被拒），**新增未生产的名是安全的**，不产生事件。
- TS 侧 `TIMELINE` 载荷白名单需允许可选 `data` 对象（供 `gate-auto-decision` 用）；不要顺手放开通配。

## [VERIFY]

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-event-parity.test.ts`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_timeline.py -q`

## 非空洞对照（必须附在回执里）

- 从 TS 侧删掉 `target-config-rejected` ⇒ 相等断言必须红。
- 把某个新事件名拼错一个字符 ⇒ 相等断言必须红。

## 风险与注意

- `timeline.py` 有 `ROTATE_GENERATIONS=2`（`:93-94`）等无关逻辑，**不要动**。
- design.md 的 VC-012 输出行原写 `count=18`（新事件加入前的示意值），已改为 `set equality, not count`；本卡以集合相等为准。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-02-ts-event-parity/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
