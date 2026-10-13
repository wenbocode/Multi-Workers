# T-10b — 110 列预算下的可见性共存（DRIFT 与 reason/age 不互斥）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-001（原因与时长恒可见）, AC-012（不回归既有 DRIFT 契约）
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/design.md` §2 D1（"reason 与 age 最后丢"）、D5；本卡由 T-10 的回归触发

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（"阻塞无感知"是本 key 第一性目标）。
- **本卡要修的具体回归**（PM 已复跑确认）：`packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts:534`（用例名含 `renders one line per pending gate with age and DRIFT, all <= 110 columns`）在 `:552` 断言 `expect(gateLines[0]).toContain("DRIFT(")`，实测失败：`expected 'gates: 2 pending - gate-0008 (stage-c…' to contain 'DRIFT('`。
- 该文件 `:6-9` 的记录性约定：每行 ≤110 列、`created_at` age 可见、证据漂移标记 `DRIFT(` 在（**这是既有 AC-012 的呈现契约**）。本 key 的 AC-001 要求 reason/age 恒可见。
- T-10 的实现：`monitor.ts` 的 drop 序被改为 `DRIFT→code→scope-unresolved→scope→reminders→age→reason` ⇒ **DRIFT 最先丢**，因此上述断言失败。T-10 的写入面不含该测试文件，故未修（其报告已给出算术说明）。
- **PM 裁定：不接受"丢任一侧"。** 两条契约必须共存；若确实放不下，允许**压缩编码**，但**永不丢 reason**、**DRIFT 语义必须保留**（可以是更短的记号，但必须有）。

## 要求

1. **压缩编码共存**：在 ≤110 列内同时表达 DRIFT 与 reason + age，采用紧凑记号（例：`D` 或 `~D` 表漂移；原因用短码如 `R:flight` / `R:cap` / `R:term` / `R:due` / `R:queue` / `R:scope`；age 用紧凑写法如 `12m` / `3h` / `2d`）。给出**编码表**（码 → 含义）并写进代码注释与报告。
2. **确定性降级规则**：若某组合在 110 列内仍不可行，必须（a）用构造性反例证明，（b）给出确定性的压缩优先级，（c）在被压缩处留下可见痕迹（如末列 `+2` 表示压掉 N 个次要字段），（d）**reason 与 DRIFT 永不被丢**（可被编码，不可消失）。
3. **更新测试，但不删断言**：`test/suite/autopilot-gate-presentation.test.ts:534-575` 只允许把期望**编码形态**改为新形态；**`DRIFT` 语义断言必须保留**（可改为断言等价记号，但不得删除该契约）；并**新增**"reason 与 age 也可见"的断言。`:384-389` 的 `GateView` 断言与其他既有用例**不得改动**。
4. **不得放宽既有判据**（P-03）：本卡是"在不牺牲可见性的前提下化解冲突"，不是"把断言改宽松"。
5. 需在报告中说明：新 drop 序（或新压缩规则）下，最坏情况（最多 gate、最长 key、最长 reason）呈现什么，以及为什么仍满足两条契约。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`（仅渲染/编码相关函数）
- `packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts`（`DRIFT` 断言只改编码形态、不删语义；其余用例不动）
- 新增：`packages/coding-agent/test/suite/mwgal-t10b-presentation-budget.test.ts`

## 写入禁止面

- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（除非新增编码常量确有必要，且不得改六值枚举语义）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/**`、`shared/**`
- `packages/multi-workers/**`（T-11/T-13 正在改）
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-gate-presentation.test.ts test/suite/mwgal-t10b-presentation-budget.test.ts test/suite/autopilot-console.test.ts`

## 改动历史

（填写：编码表、drop 序/压缩规则的最终形态、以及为什么这样能在 110 列内同时满足 AC-001 与既有 AC-012；说明被否决的替代方案。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
