# T-14b — `blocker_class` 接到 monitor 可见面（补 T-14 自报的可见性缺口）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-007, AC-012, AC-001
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/workers/mwgal-t14-blocker-class/report.md`（`## 残留与未验证` 第 1 条）；
      `evidence/research/design-drq1-field-registration-20261013.md`（**monitor `scanPendingGate` 漏注册 ⇒ 字段静默消失**）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（阻塞必须**可分类且可见**：分类若只落在判定层、不落在面板上，无人值守时人依旧看不出"该自动放行还是必须等人"）。
- T-14 已把 `blocker_class`（值域闭集 `{paperwork, judgment}`，`None` 折叠为 `judgment` = 不自动放行）注册到 **Py 4 / TS 3 + 1 materialize** 登记点；但 **`monitor.ts` 不在 T-14 的写入允许面**，因此：
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts:234 scanPendingGate`（`parsePendingGateText`）**没有 `blocker_class` 分支**；
  - 后果：**不丢 gate、非 fail-open**，但面板上看不到分类 ⇒ **DRQ-1 预言的"静默消失"缺口**在 monitor 面**部分成立**（字段进了状态模型，却没进面板）。
- 已落的相关机制（本卡必须复用，不得另起一套）：
  - `monitor.ts:130-131`（`reasonCode` 解析先例：`verbatim when present`，空串折 `null`）、`:330`（`reason_code` 的赋值形态）。
  - **T-10b 落的压缩编码与 fit ladder**：`renderPendingGateLine()` 与 `~D` / `R:*` 短码、紧凑 age、末列 `+N` 计数；**DRIFT / reason / age 永不被丢**（`autopilot-gate-presentation.test.ts` 有 110 列契约断言）。
  - `status-model.ts` 侧 `blocker_class` 已注册（T-14 报告给出 `:876/:940-946/:846+1040-1045+1114`）与本卡要保持一致。

## 要求

1. **解析**：`monitor.ts` 的 pending-gate 文本解析必须识别 `blocker_class`（照 `reasonCode:130-131` 先例：存在即取值、空串折 `null`），并落到 `MonitorGate` 的可选字段（命名须与 T-10 已扩的 `MonitorGate` 风格一致）。
2. **呈现（不得压掉 trio）**：面板行必须让 `blocker_class` **可见**，且**不得**因此丢掉 DRIFT / reason / age（T-10b 的 110 列预算与此前契约）：必须走**同一条 fit ladder**，把 `blocker_class` 作为**可压缩的次要字段**（与 `code=`/`scope=`/`stage=`/`key=`/`reminders=` 同一档），被压掉时**必须计入末列 `+N`**（保底留痕）。
3. **不得回归既有契约**：`autopilot-gate-presentation.test.ts` 的既有断言（DRIFT 语义、110 列上限、console `GateView` 的 `toEqual` 锁）**不得删改语义**；如确需改动，只允许改**编码形态**并逐条说明。**不得**动 `GateView`（`autopilot-console.test.ts:384-389` 精确锁死）。
4. **缺省语义一致**：`blocker_class` 缺失（v1 存量 gate，51/56）⇒ 面板**不得**显示为健康/无分类；须与 `status-model.ts` 的 `None → judgment` 折叠方向**一致**，并给出两侧对照。
5. **测试**：① 解析出 `blocker_class` 的两值；② 缺字段（v1）⇒ 与判定层折叠一致；③ 最坏压力下 trio（DRIFT/reason/age）存活且 `+N` 计数含 `blocker_class`；④ 既有 110 列与 DRIFT 断言仍绿。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`
- 新增：`packages/coding-agent/test/suite/mwgal-t14b-monitor-blocker-class.test.ts`
- `packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts`（**仅允许改编码形态的断言**，逐条在报告说明；不得删语义断言）

## 写入禁止面

- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`、`packages/multi-workers/**`（T-16 正在改 claim/owner 轴）
- `packages/coding-agent/test/suite/autopilot-console.test.ts`（`GateView` 锁）
- `shared/change-ledger.ts`、`worker/**`
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t14b-monitor-blocker-class.test.ts test/suite/autopilot-gate-presentation.test.ts test/suite/autopilot-console.test.ts test/suite/mwgal-t10-state-surface.test.ts test/suite/mwgal-t10b-presentation-budget.test.ts`

## 改动历史

（填写：字段命名与解析落点、在 fit ladder 中的档位、`+N` 计数方式、与 `status-model` 折叠的一致性对照、被否决的替代方案（例如"永不压缩 blocker_class"为何不成立）。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
