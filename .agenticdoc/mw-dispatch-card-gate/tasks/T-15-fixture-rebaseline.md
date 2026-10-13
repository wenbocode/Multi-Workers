# T-15 compliant-card 夹具 rebaseline（收紧后的真实欠判）

- Key: mw-dispatch-card-gate｜Wave: 8（可与 T-13/T-14 并行）｜依赖: T-12（终态）｜type: coding

## 上下文
T-12 按 QG 的 F-02/F-05 收紧 G-1 后，**非本卡允许面**的 TS 集成夹具出现 41 条新红（`Tests 29 failed | 67 passed` 合并汇总，另 `agent-team-loop.test.ts` 单文件 `13 failed | 184 passed`）。失败形态一律是：

```
[dispatch-card] ... is not a complete dispatch envelope (missing=[写入允许面, 写入禁止面, 验收命令, 改动历史, seed:goal.md, seed:path:line])
```

PM 裁定（已定）：**这不是回归，是真实欠判** —— 这些测试的 `writeCompliantCard` 只写三段信封、既无 `coding` 的 4 个 extras，也无最小种子项；在 G-1 收紧前它们"合规"，现在被如实判为不合规。因此本卡的职责是**只改夹具**，让夹具重新符合（而不是让判据变松）。

## 要求（逐条可验收）

1. **只改夹具，不改判据**：给受影响文件的 compliant-card 构造器（`writeCompliantCard` 及同类 helper）补足：
   - `coding` 的 4 个 extras 段（写入允许面、写入禁止面、验收命令、改动历史），内容须为该测试语义下的真实示例，不得写空骨架；
   - 最小种子项：至少一处 `goal.md` 引用 + 至少一处 `路径:行号` 形式引用（`seedItemsMissing` 口径）。
2. **禁止面**：不得修改 `packages/coding-agent/src/**`（判据已定稿）；不得删除、跳过（`skip`/`todo`/`.only`）或放宽任何断言；不得修改其它测试的期望值来"顺带变绿"。若你判定某条红是**判据本身**的问题，**不要改判据**，在报告中单列并给出证据供 PM 裁定。
3. **已知不属本卡的一条**：`test/extensions/agent-team-loop.test.ts` 的 `T-17/B-1 anchor integrity`（`unresolved: .agenticdoc/mw-guard-form-hardening/design.md worker-mode.ts:2149`）是**另一 key 的文档锚点漂移**（PM 自认，属 C-27），**不得**修改 `.agenticdoc/mw-guard-form-hardening/**`（其它 key 目录禁止写入）。该条允许保持红，但必须在报告中明确它是唯一残留红并给出该文件与行。
4. **范围**（以实测失败文件为准，含但不限于）：`packages/coding-agent/test/extensions/agent-team-loop.test.ts`、`test/extensions/agent-team-loop-vision-gate.test.ts`、`test/extensions/agent-team-loop-vision-autoroute.test.ts`、`test/extensions/agent-team-loop-pm-state-sync.test.ts`、`test/suite/worker-crosskey-readonly.test.ts`、`test/suite/mwds-t01-worker-guard.test.ts`、`test/suite/mwds-t02-write-intent.test.ts`。先跑一遍确认清单与红数，再动手。

## 交付格式
- 写入允许面：上述 `packages/coding-agent/test/**` 下的受影响测试文件（**仅测试**）。
- 写入禁止面：`packages/coding-agent/src/**`、`packages/multi-workers/**`、`.agenticdoc/**`（含其它 key 目录与本 key 目录，除本 worker 目录 taskDir）。
- 验收命令（在 `packages/coding-agent` 下）：
  - `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-vision-gate.test.ts test/extensions/agent-team-loop-vision-autoroute.test.ts test/extensions/agent-team-loop-pm-state-sync.test.ts test/suite/worker-crosskey-readonly.test.ts test/suite/mwds-t01-worker-guard.test.ts test/suite/mwds-t02-write-intent.test.ts`
    预期：**除第 3 条那 1 条锚点红以外全部绿**；
  - 回归确认（T-12 的验收面不得因此变红）：`node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-card-envelope.test.ts test/suite/dispatch-card-injection.test.ts test/suite/change-ledger.test.ts test/suite/dispatch-recovery-terminal.test.ts test/suite/output-recovery-contract.test.ts` 全绿；
  - `npm run check` 退出码 0（若 biome 会改写你写面之外的任何文件，停下来在报告中说明，不要让它跑）。
- 报告（`report.md`）须含：结论、证据（改前/改后的失败数与原始汇总输出、最后一轮全绿输出、那 1 条残留红的原文）、改动清单（文件 + 意图，并说明**只新增夹具内容、未改动任何断言**）、残留与未验证、上下文来源清单。
- 不做 cutover；不改 task 卡；如认为卡有误，在报告中提出供 PM 裁定。
