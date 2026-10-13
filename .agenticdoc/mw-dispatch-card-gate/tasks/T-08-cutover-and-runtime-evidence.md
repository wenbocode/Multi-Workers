# T-08 cutover 与运行期证据（含 F-10 首张带卡派发）

- Key: mw-dispatch-card-gate｜Wave: 11（收口）｜依赖: T-12/T-13/T-14/T-15/T-16 全绿 + T-17 QG 第二轮 PASS｜type: coding
- PM 预授权：D-003（用户「可以 cutover」）

## 上下文
源码与单测已全绿（全量 `packages/multi-workers` = `2 failed, 1722 passed`，两条为既有基线；TS 定向面 93 + 39 passed）。本轮把改动**落到运行期**：源码改的是**驻留服务**（P-01），不 cutover 则行为不变。同时修 F-10：本 key 今日 18 条派发均为**无卡手写形态**，在 F-06 之后被判 `unlisted_after_boundary`（QG R-07），cutover 后 PM 必须以**带卡**形态派发。

## 要求（逐条可验收）

1. **构建与安装**（不询问用户，已预授权）：
   - `python -X utf8 packages/multi-workers/mw.py build --install --allow-dirty`（或仓内既有等价入口，按 `mw.py --help` 实证的参数为准；把实际命令写进报告）；
   - 重建 TS 侧产物：`packages/coding-agent/dist`（按仓内既有构建脚本）；
   - 重启驻留服务与窗口扩展：记录 `mw status` / 进程 pid / 版本证据。**注意**：`/mw restart` 与 `/reload` 是 PM 窗口的交互命令，由 PM 执行；你负责构建/安装/重建产物，并在报告中给出 PM 需要执行的两条命令与预期输出。
2. **一正一负运行期证据**（必须落在 `evidence/runs/`，文件名含日期）：
   - **正**：用**带卡**形态派发一张真实任务（本卡自身即可 —— 它的 `task.md` 必须含 `card_path:` + `card_sha256:` + `envelope_producer:` 三行，且三段 canon 段 + `coding` 的 4 个 extras 齐备），断言：`task.md` 真落盘这三行、`card_audit` 把它计为 `dispatched` 而**不是** `unlisted_after_boundary`、服务层放行（`spawn` 成功）。
   - **负**：构造一条**晚于边界且无信封**的派发，断言服务层的**新分支**真实生效：行状态为可检索的 `failed(producer-skew …)`（带 `envelope_producer` 行时）或 `envelope missing` + 指引（无身份行时），且 **`spawned=[]`**、且**不静默**（聚合告警 `[ENVELOPE-SKEW]` 或等价出口有记录）。
   - 两条证据都要含**原始命令与原始输出**。
3. **`[WRITE_FILE]` 事件运行期复测**：cutover 后（PM 执行 `/reload` 之后）跑一张**极小**的 coding worker（或本卡自身的收尾步骤），断言 `trace.log` 出现 `[WRITE_FILE]` 事件、且 `output.md`/回收判据面能据此做 ⊆ 校验。若必须由 PM 在 `/reload` 后触发，在报告中写清"需 PM 执行的触发步骤 + 预期证据位置"。
4. **验收命令（你必须在报告中给出原始输出）**：
   - `python -X utf8 -m pytest packages/multi-workers -q` ⇒ 失败数 == **2**（既有基线），不得新增；
   - 在 `packages/coding-agent` 下：`node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-card-envelope.test.ts test/suite/dispatch-card-injection.test.ts test/suite/change-ledger.test.ts test/suite/dispatch-recovery-terminal.test.ts test/suite/output-recovery-contract.test.ts test/suite/mwds-t02-write-intent.test.ts` ⇒ 全绿（93 + 39 基线）。
5. **禁止面**：不得改判据与断言（本轮只做构建/安装/证据）；不得修改任何 task 卡；不得写其它 key 目录；不得提交 git（PM 决定）。

## 交付格式
- 写入允许面：`evidence/runs/**`（本 key 目录下）、`packages/multi-workers/dist/**` 与 `packages/coding-agent/dist/**`（构建产物）、以及构建/安装过程必须触及的仓内产物目录。
- 写入禁止面：`packages/multi-workers/*.py`、`packages/coding-agent/src/**`、`packages/coding-agent/test/**`、`.agenticdoc/**`（除本 key 的 `evidence/runs/` 与本 worker 目录 taskDir）。
- 报告（`report.md`）须含：结论、构建/安装的**实际命令与原始输出**、一正一负两条运行期证据、`[WRITE_FILE]` 复测（或 PM 触发步骤）、两条验收命令的原始输出、**PM 需要执行的命令清单**（`/mw restart`、`/reload` 与确认方式）、残留与未验证、上下文来源清单。
