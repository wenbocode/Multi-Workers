# T-16 自注入 marker 不得触发自身守卫（AC-010 / C-29）

- Key: mw-dispatch-card-gate｜Wave: 9（与 T-13/T-14 写面不相交）｜依赖: T-02（写面契约注入）、T-15（终态，发现者）｜type: coding

## 上下文
T-15 在夹具 rebaseline 时发现一条**与它无关的既有红**（改前改后逐字一致，`corpus=357 … false_positives=2`）：本 key 的 T-02 会往派发物/卡里幂等注入写面标记

```
<!-- mw-write-surface: v1 -->
```

而写面意图的 hit 收集器把该 HTML 注释**当成写入目标文本**解析，命中 `-surface:` 形态 ⇒ 在**真实语料**上产生 **2 个 false positive**。

性质：**本 key 自己的注入触发本 key 自己的守卫** —— 这是 E8/AC-009「投递机制反噬」命题的第二个实例（第一个是 conductor 瘫痪），方向是**过拦**（诚实产物被判为可疑写入意图）。PM 裁定：**在本 key 内修**（AC-010），因为：① 该 marker 由本 key 引入；② 它使仓库留下一条**真实**红（非豁免项），本 key 不能以"新红为零"收官；③ 修法局部且低风险。

## 要求（逐条可验收）

1. **剥离注释后再匹配**：写面意图/目标的提取路径必须先剔除 HTML 注释（`<!-- ... -->`，含跨行与行内两形态）再匹配，使 marker 本身不产生任何 hit；不得通过对 marker 文本做特例硬编码（例如不得写 `if line.contains("mw-write-surface")` 这种点名跳过；要求结构性剥离注释）。
2. **防过修（反例必须进报告）**：
   - marker 原文（含多行/行内两种写法）喂入收集器 ⇒ 结果为空集；
   - **注释外的真实写入目标仍必须命中**（同一行、相邻行、注释与被注释混排三种排布各一例）；
   - 注释内**包含真实路径文本**（如 `<!-- 例如 src/a.ts 会被改 -->`）⇒ 仍不得命中（证明是剥离注释而非只跳过 marker）。
3. **真实语料归零**：对当前真实语料（`corpus=357`，以 `test/suite/mwds-t02-write-intent.test.ts` 的 corpus replay 用例为准）判定 `false_positives == 0`；该用例的期望值按**收紧后的真实口径**更新（这是**修正判据**，允许改该用例的期望，但**不得**通过缩小语料/跳过用例达成）。
4. **不得放宽其它判据**：本次只允许让命中集**变小到正确值**；不得删除既有的正例断言、不得放宽 `write_scope` 相关判定、不得改动 `mw-write-surface` marker 的注入文本与版本（v1 形态保持字节不变）。
5. **回归确认**：T-12/T-15 的验收面保持全绿（`dispatch-card-envelope` / `dispatch-card-injection` / `change-ledger` / `dispatch-recovery-terminal` / `output-recovery-contract`；`mwds-t02-write-intent` 的其余用例）。

## 交付格式
- 写入允许面：写面意图/hit 提取的实现文件（在 `packages/coding-agent/src/extensions/agent-team-loop/**` 中，按符号定位：hit 收集器与其调用点）、`packages/coding-agent/test/suite/mwds-t02-write-intent.test.ts`（仅该文件的期望/夹具与新用例）。
- 写入禁止面：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` 的 marker 注入文本（保持 v1 字节不变）、`packages/multi-workers/**`（T-13/T-14 曾写；本卡不动）、`.agenticdoc/**`（其它 key 目录与本 key 目录，除本 worker 目录 taskDir）、其他 `test/**` 文件。
- 验收命令（在 `packages/coding-agent` 下）：
  - `node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t02-write-intent.test.ts` 全绿（含 corpus replay `false_positives=0`）；
  - `node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-card-envelope.test.ts test/suite/dispatch-card-injection.test.ts test/suite/change-ledger.test.ts test/suite/dispatch-recovery-terminal.test.ts test/suite/output-recovery-contract.test.ts` 全绿（93 passed 基线）；
  - `npm run check` 退出码 0（若 biome 会改写你写面之外的任何文件，先停下来在报告中说明）。
- 报告（`report.md`）须含：结论、证据（原始命令与输出：marker 原文 ⇒ 空集、三种排布的真实目标仍命中、注释内路径文本不命中、corpus replay 的 false_positives=0）、改动清单（文件 + 意图）、残留与未验证、上下文来源清单。
- 不做 cutover；不改 task 卡；如认为卡有误，在报告中提出供 PM 裁定。
