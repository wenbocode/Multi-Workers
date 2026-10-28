# T-07 拆分清单：`shared/split-manifest.ts`（coding）

- Key: claim-driven-review-orchestration
- 里程碑：M1（只读规划器）
- type: coding
- 性质：纯模块 + 测试，不接派发链（接线是 M2/M3）

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（文件驱动的去中心化协调：协调状态必须落盘成可机检的文件，而不是靠进程记忆）。
- 设计依据 `design.md` §2.3/§2.4：`evidence/split/review-<task>-manifest.json` 是**唯一真相**，
  merge 的母卡 id 集只从这里读。理由（`evidence/research/design-switch-and-seams-20261022.md` §2）：
  子/母卡的 `card_sha256` 今天**无链**（RQ-1 §6.3），不钉 sha 就发现不了"母卡被改过"。
- 复用契约：`Claim` 接口 `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:724`；
  `packClaims` 的 `PackUnit` / `PackingRow` 见 `shared/claim-pack.ts`。

## 要求

新增 `packages/coding-agent/src/extensions/agent-team-loop/shared/split-manifest.ts`：

1. 类型
   ```ts
   export interface SplitUnitRef { k: number; taskKey: string; ids: string[]; budgetSum: number; slots: number; writeFace: string; sha256: string }
   export interface SplitPackingRow { cluster: string[]; unit: number; why: string }
   export interface SplitManifest {
     v: 1; parent: string; mode: "plan" | "on";
     parentSha256: string; ids: string[]; units: SplitUnitRef[];
     packing: SplitPackingRow[];
     l0: { asks: number; mapped: number; unmapped: string[] };
     selfSha256: string;
   }
   ```
2. `sha256Hex(text: string): string`（`node:crypto`，UTF-8，十六进制小写）——与既有 `card_sha256` 口径一致。
3. `buildSplitManifest(input): SplitManifest`：
   - `input` 含 `parent`、`mode`、`parentText`、`units: Array<{k, taskKey, ids, budgetSum, slots, writeFace, text}>`、
     `packing`、`l0`；
   - `units[*].sha256 = sha256Hex(text)`；`selfSha256 = sha256Hex(JSON.stringify(payloadWithoutSelf))`，
     key 顺序固定（按上面字段顺序显式构造，不用对象展开猜顺序）；
   - 校验：`ids` 必须等于各 unit `ids` 的并集（顺序按 unit 顺序）且**无重复**，否则抛 `Error`
     （构建期是编程错误，不是用户输入；P-048 的宽容只用于解析期）。
4. `verifySplitManifest(manifest, ctx): string[]`（**不抛异常**，只回 gaps）：
   - `ctx = { parentText?: string; unitTexts?: Record<string,string> }`
   - `selfSha256` 不符 → `split:manifest:self-sha`
   - `parentText` 给出且父卡 sha 不符 → `split:manifest:parent-sha`
   - 某 unit 文本 sha 不符 → `split:manifest:unit-sha:<taskKey>`
   - `ids` 与 units 并集不等 → `split:manifest:id-set:<missing|extra>:<id>`
   - `packing` 里出现未知 unit 号 → `split:manifest:packing-unit:<n>`
5. `serializeSplitManifest(m)`：稳定输出（2 空格缩进 + 末尾换行），`JSON.parse(serialize(x))` 深等于 `x`。
6. 纯函数：不读写文件、不调模型。

## 交付格式

- 新增 `packages/coding-agent/src/extensions/agent-team-loop/shared/split-manifest.ts`
- 新增测试 `packages/coding-agent/test/suite/split-manifest.test.ts`，至少 9 条：
  ① 构建后 `selfSha256` 稳定（同输入两次相同）；② 改一个 unit 文本 → `verify` 报 `split:manifest:unit-sha`；
  ③ 改父卡文本 → `split:manifest:parent-sha`；④ 删一条 id → `split:manifest:id-set:missing`；
  ⑤ 多一条 id → `extra`；⑥ 篡改 `selfSha256` → `self-sha`；⑦ 未知 packing 单元号；
  ⑧ `serialize` 往返深等；⑨ `buildSplitManifest` 遇重复 id 抛错。
- 报告 `report.md` 四段；`## 未覆盖面声明` 必须写"未接派发/未接 merge 门禁"。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/split-manifest.ts`
- `packages/coding-agent/test/suite/split-manifest.test.ts`

## 写入禁止面

- 任何既有文件（含 `claim-pack.ts` / `dispatch-card.ts`）、`.mw/**`、`.agenticdoc/**`、`dist/**`

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/split-manifest.test.ts`（≥9 passed）

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡 | design.md §2.3/§2.4、RQ-1 §6.3（sha 无链） |
