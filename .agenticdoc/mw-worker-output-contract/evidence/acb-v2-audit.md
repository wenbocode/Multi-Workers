# ACB-V2 · AC-010(b) 审查类探针 2：`renderCardSeedSections` 契约注入审计

- Key: mw-worker-output-contract
- Worker: acb-v2
- Date: 2026-10-15
- Type: review（静态审计，未修改任何代码）
- 审计目标：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1888`（`export function renderCardSeedSections` 定义处）

## 总判定

3/3 PASS。`renderCardSeedSections` 的契约清单注入已收窄到「卡片声明了 `type:`」这一条件，带去重守卫；`recoveryContractSection` 对契约外 type 返回 `""`。源码与两个已部署编译产物（`packages/multi-workers/dist` bundle、`packages/coding-agent/dist`）一致。

## (a) 注入条件 = `sections.type !== undefined`（非 writeless-only）— PASS

源码 `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1907`（位于 `renderCardSeedSections`，定义于 :1888）：

```ts
const contract = sections.type !== undefined ? recoveryContractSection(sections.type) : "";
if (contract !== "" && !parts.includes(RECOVERY_CONTRACT_HEADING)) {
	parts.push(contract, "");
}
```

- 条件仅为 `sections.type !== undefined`；渲染路径内无 `isWritelessRole` 调用。
- `ui-bridge.ts` 中仍存的三处 `isWritelessRole`（:1659、:2394、:2892）均为 AC-005a 写意图拒绝闸（writeless 角色无法满足外部写单），与清单注入无关，不构成二次收窄。
- 文档注释（:1880-1887）明确记录了 T-13/D-015 option C（2026-10-15）的放宽：门控从「writeless 报告角色」改为「卡片声明了 `type:`」，`coding` 亦纳入。
- 编译产物一致：
  - `packages/multi-workers/dist/extensions/agent-team-loop.js:25692`：`const contract = sections.type !== void 0 ? recoveryContractSection(sections.type) : "";`（`void 0` 即编译后的 `undefined`）
  - `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js:1588`：同一逻辑（`:1563` 起为函数体）。
- 回归锁定：`packages/coding-agent/test/suite/dispatch-card-injection.test.ts:181-192` 的 `EXPECTED_SECTIONS` 携带 `type: CARD_TYPE`（`CARD_TYPE = "coding"`，:127），:258 的逐字节 pin 期望因此包含 `## 交付段契约（本角色）` 清单（coding = 基础四段 + `改动清单`）。

## (b) 去重守卫 `!parts.includes(RECOVERY_CONTRACT_HEADING)` — PASS

源码 `ui-bridge.ts:1908`：

```ts
if (contract !== "" && !parts.includes(RECOVERY_CONTRACT_HEADING)) {
```

- `RECOVERY_CONTRACT_HEADING = "## 交付段契约（本角色）"`（`worker/output-sections.ts:67`，Python `dispatch.py::RECOVERY_CONTRACT_HEADING` 的镜像）。
- 卡片自身已声明该标题时 `parts.includes` 为真，不再注入 ⇒ 重渲染是字节不动点；与 Python 生产者 `dispatch.py::_envelope_card_body` 的同节注入不重复（幂等）。
- 编译产物一致：`agent-team-loop.js:25693`、`ui-bridge.js:1589`。
- 幂等回归：`dispatch-card-injection.test.ts`（"is idempotent: the seed block is a byte-level fixed point"，`applyCardSeedSections` 二次应用 `expect(twice).toBe(once)`，标题对恰 1 个）。

## (c) `recoveryContractSection` 对契约外 type 返回 `""` — PASS

源码 `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:115-117`：

```ts
export function recoveryContractSection(type: string | undefined): string {
	if (type === undefined || !RECOVERY_CONTRACT_TYPES.includes(type)) return "";
	...
}
```

- `RECOVERY_CONTRACT_TYPES = ["coding", "research", "review"]`（:63，`dispatch.py::RECOVERY_CONTRACT_TYPES` 的镜像，由 `test_mwoc_s2_sections.py::test_recovery_tables_match_the_ts_source` 锁两侧一致）。
- `type === undefined` 或不在表内（如 `debug`、自定义角色、直接构造的无 type `CardSections`）⇒ 返回 `""` ⇒ :1907-1908 处 `contract === ""` 不 push ⇒ 种子字节与无契约角色完全一致。
- 契约内 type 渲染为可复制标题行：`- \`## <段名>\``，段表 = `RECOVERY_SECTIONS`（结论/证据/残留与未验证/上下文来源，:48）+ 角色附加（coding: 改动清单；review: 未覆盖面声明，:51-54）。

## 附注：与判定闸的衔接（探针语境）

本探针自身即在新 bundle 下受判：`review` 属 `RECOVERY_CONTRACT_TYPES`，故本卡生成的 task.md 种子含 `## 交付段契约（本角色）`；受判产物（report.md）按标题判定（五段 H2）+ 机械段自动补齐（`MECHANICAL_SECTIONS = ["上下文来源"]`，`output-sections.ts:88`）判分。本 report 五段 H2 全部由 worker 自身成节。

## 证据坐标汇总

| 事实 | 文件:行 |
| --- | --- |
| `renderCardSeedSections` 定义 | `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1888` |
| (a) `sections.type !== undefined` 条件 | 同上 `:1907` |
| (b) 去重守卫 | 同上 `:1908` |
| 放宽记录（T-13/D-015 option C） | 同上 `:1880-1887`（doc comment） |
| (c) 契约外返回 `""` | `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:115-117` |
| `RECOVERY_CONTRACT_TYPES` / `RECOVERY_CONTRACT_HEADING` / `RECOVERY_SECTIONS` | 同上 `:63` / `:67` / `:48` |
| 部署 bundle（mw 服务加载） | `packages/multi-workers/dist/extensions/agent-team-loop.js:25673-25694` |
| 部署产物（coding-agent dist） | `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js:1563-1596` |
| 逐字节 pin 回归（coding 含清单） | `packages/coding-agent/test/suite/dispatch-card-injection.test.ts:127,181-192,258` |
| 无关 `isWritelessRole` 用点 | `ui-bridge.ts:1659,2394,2892`（AC-005a 写意图闸） |
