# T-18 TS 侧 producer 身份行（R-1）

- Key: mw-dispatch-card-gate｜Wave: 12（与 T-19 并行，写面不相交）｜依赖: T-02/T-12（终态）｜type: coding

## 上下文
T-08 cutover 的残留 **R-1**：`envelope_producer:` 目前**只有 Python conductor 渲染器**（`packages/multi-workers/autopilot/dispatch.py`，T-13 落地）会写；**TS 侧 `/worker` 路径**（`pm/ui-bridge.ts::mergeCardHeader`）只写 `card_path:` + `card_sha256:`。

后果：服务层（T-14）的"**版本偏移 vs 真缺段**"三分支只在生产者**声明身份**时才能区分。TS 派发的 task.md 没有身份行 ⇒ 服务层只能按 **legacy/unknown** 分支处理（fail-closed + 指引），拿不到"你是旧版本、这样升级"的**可操作**诊断。F-10 的修法（PM 改用带卡派发）走的正是 TS 路径 ⇒ 这个缺口必须补。

## 要求（逐条可验收）

1. **补身份行**：TS 派发物（`task.md` 头部区）在写入 `card_path:` / `card_sha256:` 的同时写入 `envelope_producer: <producer-id>@<version>`。
   - `producer-id` 必须能区分 TS 工具路径与 conductor 路径（例如 `agent-team-loop-pm` / 与既有常量一致）；
   - `version` **必须来自既有版本源**（不得新增无来源的硬编码常量）。优先用现有可读版本（例如 `packages/coding-agent/package.json` 的 version，或仓内既有版本常量）；在报告中写明取值出处与运行期读取方式。
2. **与 Python 侧契约一致**：行的**形态与解析口径**必须与 `dispatch.py`（T-13）的 `envelope_producer: <producer-id>@<version>` 完全一致（同一正则/同一分隔符），否则服务层解析会出现新的不一致。请**读 T-13 的实现**（`packages/multi-workers/autopilot/dispatch.py` 的 `PRODUCER_IDENTITY_KEY` 与其渲染/解析点）并在报告中逐字引用该形态。
3. **不破坏既有字节金样本**：T-02/T-12 的字节级金样本若因新增一行而失效，必须**带 diff 显式重新基线**（不得放宽断言、不得删除断言）。
4. **回归**：`dispatch-card-envelope` / `dispatch-card-injection` / `change-ledger` / `dispatch-recovery-terminal` / `output-recovery-contract` / `mwds-t02-write-intent` 全部保持绿。
5. **服务层可识别（静态证据）**：在报告中给出"TS 写出的 task.md 文本 + 服务层解析该身份行的代码路径/行号"，证明两者匹配（无需真的 spawn）。

## 交付格式
- 写入允许面：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`、`packages/coding-agent/test/suite/dispatch-card-injection.test.ts`、`packages/coding-agent/test/suite/dispatch-card-envelope.test.ts`（仅金样本/期望）。
- 写入禁止面：`packages/multi-workers/**`（T-13/T-14 已定稿）、其它 `src/**`、`.agenticdoc/**`（除本 worker 目录 taskDir）、`test/extensions/**`。
- 验收命令（在 `packages/coding-agent` 下）：
  - `node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-card-injection.test.ts test/suite/dispatch-card-envelope.test.ts` 全绿（含重新基线的字节样本）；
  - `node ../../node_modules/vitest/dist/cli.js --run test/suite/change-ledger.test.ts test/suite/dispatch-recovery-terminal.test.ts test/suite/output-recovery-contract.test.ts test/suite/mwds-t02-write-intent.test.ts` 全绿；
  - `npm run check` 退出码 0（若 biome 会改写你写面之外的文件，先停下来在报告中说明）。
- 报告（`report.md`）须含：结论、证据（原始命令与输出；TS 写出的 task.md 头部原文；T-13 形态的逐字引用 + 服务层解析路径）、改动清单、残留与未验证、上下文来源清单。
- 不做 cutover；不改 task 卡；不得弱化或删除既有断言；如认为卡有误，在报告中提出供 PM 裁定。
