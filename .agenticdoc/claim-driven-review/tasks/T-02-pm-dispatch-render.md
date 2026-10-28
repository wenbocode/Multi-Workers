# T-02: PM 派发层 —— claims gate、read_scope 渲染、claims 块注入（coding）

- Key: claim-driven-review
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「不修改 pi 核心：所有功能通过 Extension API」）。
- 设计依据：`design.md` §3.2、§5（G1 门禁表）、§7 D-002/D-005/D-006。
- 上游事实（`evidence/research/spec-rq2-seams-20261020.md`，不要重新调研）：
  - gate 唯一插入点：`pm/ui-bridge.ts:2585` 的 `missing` 聚合处；`fs` 已在该文件顶部导入，`input.projectDir` 是现有参数（2557-2562）。
  - 拒绝形态既有实现：`DISPATCH_CARD_CODE`（`:2188`）、`dispatchCardRefusal`（`:2603-2616`，尾句必须是 `nothing was written.`）。
  - 零副作用测试形态：`dispatch-card-injection.test.ts:344-483`（断言 `fs.existsSync(taskDir) === false` 且队列行数不变）。
  - 卡种子注入只按 heading 切片（`:2258-2325`），**HTML 注释块不会被自动带进 task.md** → 必须显式注入。
  - PM 侧目前**没有任何** `read_scope`/caps 渲染；`writeDispatchTaskMd`（`:2624-2699`）只合并 `write_scope`（`mergeWriteScope` 2146）与卡头（`mergeCardHeader` 2468）。
  - `triage-dispatch.test.ts:355-357` 对无 triage 的回执做了全文 `toBe` 比较 → advisory 行只能在卡确实含 claims 时追加。
- 依赖：T-01 已导出 `parseClaimsBlock` / `claimsGaps` / `claimBudgetCaps` / `CLAIM_GATE_DEFAULT`（若签名与 T-01 卡不一致，以 T-01 实际导出为准并在 `output.md` 里注明）。

## 要求

1. `readDispatchCard`（`:2556-2601`）：
   - 调用 `parseClaimsBlock(text)`；`claimsGaps(block, {projectDir, enforce})` 的结果并入 `missing`（advisory 下软 gap 不进 `missing`，改为随返回的 `warnings` 数组）。
   - `DispatchCardGate`（`:2531-2545`）扩为 `{ ..., claims: Claim[], caps: {fileCap, byteCap} | null, warnings: string[] }`；无 claims 块时 `claims=[]`、`caps=null`、`warnings=[]`。
   - 新拒绝码 `dispatch-claims`（与 `dispatch-card` 分开）；文案沿用 `dispatchCardRefusal` 结构，`missing=[claim:C2:locator, claims:budget-sum:48>40]` 这种条目原样透出。
2. `writeDispatchTaskMd`（`:2624-2699`）：
   - 新增入参 `readScope?: string[]`、`readFileCap?: number`、`readByteCap?: number`；
   - 新增 `mergeReadScope`（紧邻 `mergeWriteScope` 2146，同形态）：有值时写 `read_scope:` block list + `l2_read_file_cap: <n>` + `l2_read_byte_cap: <n>`，字段顺序固定，缺失时**不写任何行**（保证既有卡字节不变）；
   - 把 claims 块原文注入 `<!-- mw-dispatch-card: v1 -->` 标记区内（与卡种子同区），确保结算期能从 task.md 读到。
3. 两个调用点（工具 `:2930`、`/worker` `:3448`）透传 `cardGate.caps`；`read_scope` 值固定为 `[".agenticdoc/<key>", ".agenticdoc/goal.md"]` 形态（与该 key 现有 conductor 派发一致），`<key>` 取本次派发的 owner key。
4. 灰度：`MW_CLAIM_GATE` 环境变量覆盖 `CLAIM_GATE_DEFAULT`（两处读取都要用它，非法值回落 `advisory`）；enforce 下软 gap 全部升为 `missing`。
5. 测试：
   - 新增 `test/suite/dispatch-claims-render.test.ts`：caps 随 claims 变、`read_scope` 行序、claims 块注入位置、advisory 回执追加行、无 claims 卡字节不变（与改动前 golden 比对）。
   - 在 `dispatch-card-injection.test.ts` 追加 7 条零副作用用例（缺类型/缺陈述/缺反证/缺定位/缺判据/缺预算/预算和超限），每条断言 `taskDir` 不存在 + 队列行数不变 + 拒绝文案含 `claim:<id>:`。
6. 不得修改既有测试的既有断言；`triage-dispatch.test.ts` 必须原样通过。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/test/suite/dispatch-claims-render.test.ts`
- `packages/coding-agent/test/suite/dispatch-card-injection.test.ts`

## 写入禁止面

- `shared/**`、`worker/**`、`autopilot/**`（含 `status-model.ts`）、`packages/multi-workers/**`、`dist/**`

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-claims-render.test.ts test/suite/dispatch-card-injection.test.ts test/suite/triage-dispatch.test.ts
cd ../..
npm run check
```

三条文件必须 0 fail；`triage-dispatch.test.ts` 不得有断言改动。

## 改动历史

- 2026-10-21 创建（无既有改动）

## 交付格式

`output.md` 四段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。证据段给：`ui-bridge.ts` 改动行号、渲染出的 4 行 frontmatter 原文样例、零副作用用例计数、三条测试输出摘要。残留段写明未覆盖的 `/worker` flag 形态。
