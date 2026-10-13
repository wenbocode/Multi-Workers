# T-21 回收契约写入判据健全化（否定感知 + 按 worker 归属 + 词元卫生）

- Key: mw-dispatch-card-gate｜Wave: 14（与 T-20/T-22 并行）｜type: coding

## 上下文（实测：连续两张卡的假 `needs-clarification`）
T-18、T-19 均在实质完成、验收全绿的情况下被判 `needs-clarification`，理由是 `recovery-incomplete: unrecorded write(s)`，而清单里同时出现三类垃圾：

- **否定盲区**：worker 报告写"未写入 `src/**`、`packages/multi-workers/**`"⇒ 被当成写入意图（**而我每张卡都含"写入禁止面"段，故每张卡必然中招**）；
- **无按 worker 归属**：清单里的 `packages/multi-workers/**`、`src/**` 是**并行 worker（T-13/T-14/T-19/T-20）**的改动，被算到 T-18 头上；
- **词元碎片**：`coding/ncard_path:`、`^/s@|`、`/n$`、`（仅金样本/期望重基线）`、`host/pid`、`notice/refusal`、`（watched、/ORPHANED）` —— 卡面文本按反引号/`|` 切碎后的残渣。

真实语料：`.agenticdoc/mw-dispatch-card-gate/workers/mwd-t18-ts-producer-identity/report.md` 与 `.../mwd-t19-orphan-ownership/report.md`（**只读**）。

## 要求（逐条可验收）

1. **定位真源**：找出产生 `recovery-incomplete: unrecorded write(s)` 的判定链（写入意图提取 + 与 trace `[WRITE_FILE]` 事件清单的比对 + 结论包装），把每个环节的**文件+行号**写进报告。已知相关点：`pm/ui-bridge.ts::collectWriteIntentHits`（约 :1565，T-16 已加注释/围栏剥离）、`shared/change-ledger.ts`、`worker/output-writer.ts`。**若结论包装位于 `pm/pm-orchestrator.ts`，你不得修改它**（T-22 正在写该文件）；改为在共享函数语义内解决，做不到则报告并停手，由 PM 串行安排。
2. **否定感知**：命中处处于**否定/禁止语境**时不得计为写入意图。语境判定必须在**同句/同列表项范围内**（`未写入`、`不写`、`禁止`、`不得`、`写面：… 无`、`not written`、`unrecorded`、`forbidden` 等，且否定标记与该路径在同一片段内）；**禁止**用"整份报告出现'禁止'即全豁免"的粗放实现。反例必须仍命中：真实声明 `写入 packages/x/y.ts`、`我修改了 …`、`wrote …` 一律仍计。
3. **按 worker 归属**：比对对象只能是**该 worker 自身**的改动证据（其 trace 的 `[WRITE_FILE]` 事件 + 其 `task.md` 的允许面），**不得**用全仓 `git status`/全仓 diff 作为依据。当前把并发 worker 的文件算到本 worker 头上是错的。
4. **词元卫生**：提取出的候选必须是**形态合法的路径**（白名单字符集；**排除** `^ $ \` （） | :: /n /s 等残渣、纯英文单词对如 `host/pid`、以 `（` 开头的中文碎片）；且**不得**从**卡面契约段**或**代码围栏内的正则/模式**中提取（在注释/围栏剥离后的文本上提取）。非法候选计入 `malformed_candidates`（仅 warn 计数），**不参与** `recovery-incomplete` 判定。
5. **判据不得放宽**：真实"声明了写却无事件/越界写"仍必须判 `needs-clarification`。必须给出**五条正反例**：①真实越界声明 ⇒ 仍红；②否定语境 ⇒ 不红；③并发 worker 的文件 ⇒ 不红；④卡面/围栏内模式 ⇒ 不红；⑤词元残渣 ⇒ 不红且计入 `malformed_candidates`。
6. **测试与真实语料**：
   - 新建 `packages/coding-agent/test/suite/mwds-t21-write-intent-soundness.test.ts`（夹具须**逐字摘取** T-18/T-19 报告中的真实片段）；
   - 用 T-18/T-19 的**真实 `report.md`（只读）**跑一遍，输出修复前后对照：`unrecorded` 项数与**逐项**判定（哪些是垃圾、哪些是真实项）；要求垃圾项归零。
7. **回归**：`test/suite/mwds-t02-write-intent.test.ts`（39 用例，含 AC-010 语料回放，`false_positives` 必须仍为 0）、`test/suite/dispatch-recovery-terminal.test.ts`、`test/suite/output-recovery-contract.test.ts`、`test/suite/change-ledger.test.ts` 全绿。

## 交付格式
- 写入允许面：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`、`shared/change-ledger.ts`、`worker/output-writer.ts`、新建 `packages/coding-agent/test/suite/mwds-t21-write-intent-soundness.test.ts`、`test/suite/mwds-t02-write-intent.test.ts`（仅语料/期望）。
- 写入禁止面：`pm/pm-orchestrator.ts`（T-22 在写）、`shared/index-store.ts`（T-22）、`packages/multi-workers/**`、`test/extensions/**`、`.agenticdoc/**`（除本 worker 目录 taskDir）。
- 验收命令（在 `packages/coding-agent` 下）：
  - `node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t21-write-intent-soundness.test.ts test/suite/mwds-t02-write-intent.test.ts` 全绿；
  - `node ../../node_modules/vitest/dist/cli.js --run test/suite/change-ledger.test.ts test/suite/dispatch-recovery-terminal.test.ts test/suite/output-recovery-contract.test.ts` 全绿；
  - `npm run check` 退出码 0；若 biome 会改写你写面之外的文件，**先停下在报告中说明**。
- 报告须含：结论、证据（原始命令与输出；判定链文件+行号；五条正反例；真实语料修复前后逐项对照）、改动清单、残留与未验证、上下文来源清单。
- 不做 cutover；不改 task 卡；不得弱化或删除既有断言；如认为卡有误，在报告中提出供 PM 裁定。
