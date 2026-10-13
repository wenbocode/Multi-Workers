# T-23 cutover 后运行期复验（T-18 身份行 / T-21 判据 / 越界仍红 / dotless 风险）

- Key: mw-dispatch-card-gate｜Wave: 15｜type: coding｜依赖: T-18/T-19/T-20/T-21/T-22（全部终态）+ cutover（bundle `975D4066…978D`，服务已重启 PID 158412）
- **本卡自身即活体样本**：它是由**新 bundle** 渲染并投递的第一批卡之一。

## 上下文
cutover 前，配置与结论都由旧 bundle 产生，故 T-18/T-19/T-21/T-22 的运行期效果**无法观测**。现已 `build --install`（bundle sha256 `A5B0FC9C…4932` → **`975D4066967E35CC7F23713827F5CA85809578B96A07D3283206931341F9978D`**，len 1,073,639 → 1,088,235）并重启服务（PID 79536 → 158412）。本卡验证：这些改动在**真实运行链路**上是否生效、且**没有把真实越界判据放松**。

## 要求（逐条可验收，**只报告事实，不得粉饰**）

1. **身份行（T-18 运行期证据）**：读**本卡自己的 `task.md`**（路径见本卡 seed），逐字转载其头部区（首个 H2 之前的卡前区），并判定以下三行是否齐备且取值正确：
   - `card_path:`、`card_sha256:`、`envelope_producer: agent-team-loop-pm@<version>`。
   - 若缺任一行 ⇒ **如实报告"T-18 在运行期未生效"** 并附 task.md 头部原文（这是硬证据，不要解释成别的原因）。
2. **服务层判定**：运行 `card_audit`（`packages/multi-workers/autopilot/card_audit.py`，用法以其 `--help` 为准）针对本 key，报告 `cards / dispatched / missing / unlisted* / tampered_cards` 字段与**退出码**；判定本卡是否被计为 `dispatched`（不得跌入 `unlisted_after_boundary`）。
3. **T-21 判据：正例必须不红、反例必须仍红**（用**直接调用**，不得只靠肉眼看报告）：
   - **正例（不红）**：把本卡 `task.md` 的"写入禁止面"整段 + 一段含「未写入 `src/**`、`packages/multi-workers/**`」的散文，喂入账本判定链（`shared/change-ledger.ts` 的 `diffLedger` / `worker-mode.ts` 的 `readTerminalGaps` 口径）；断言 `extra` **不含**这些禁止面路径，也不含 `host/pid`、`/workers`、`/task.md`、`trace.log` 之类空洞残渣。
   - **反例（仍红）**：构造"声明写入 `packages/multi-workers/launcher.py` 但 trace 无对应 `[WRITE_FILE]` 事件" ⇒ 断言 `extra` **必须包含**该路径（判据不得被放松）。
   - **dotless 复验（PM 登记的风险）**：声明写入 `scripts/deploy`（无扩展名，带分隔符）**且** trace 有对应事件 ⇒ 报告它是否被判为 `malformed_candidates`（即**漏红**）。给结论：当前白名单规则下，无扩展名真实路径是否会被漏判；若是，给出最小修法建议（不得在本卡实现）。
4. **全局安装面同源校验**：比较全局安装 bundle 与 repo bundle 的 sha256（期望 = 上面那串 `975D4066…978D`）。
   **注意**：任何含 `~/.pi/agent` 字面的 bash 命令可能被运行期守卫拦截（"protected-config"）。**若被拦截，改用只读方式（如 python `glob` 遍历）或直接报告"未完成 + 阻拦原因"，绝对不要绕过守卫、不要改任何配置文件。**
5. **不得**：再次 cutover、重启任何服务、改 task 卡、改 `src/**`、写 `.agenticdoc/**`（除本 worker 目录 taskDir）、写其它 key。

## 交付格式
- 写入允许面：`packages/coding-agent/test/suite/mwds-t23-cutover-recheck.test.ts`（新建，用于第 3 条的正反例与 dotless 复验）、本 worker 目录 taskDir 内的临时脚本。
- 写入禁止面：`packages/coding-agent/src/**`、`packages/multi-workers/**`、`.agenticdoc/**`（除本 worker 目录任务目录）、其它 key 目录。
- 验收命令（在 `packages/coding-agent` 下）：`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t23-cutover-recheck.test.ts` 全绿（若确有断言失败，全绿不是目标 —— **报告真相**是目标）。
- 报告须含：①头部区原文与三行判定；②`card_audit` 原始输出与退出码；③正例/反例/dotless 三组输出；④同源校验结果（或未完成原因）；⑤结论：T-18 是否生效、T-21 是否生效、判据是否被放松、dotless 是否漏红；⑥残留与未验证；⑦上下文来源清单。

## 种子（seed）
- **目标锚点**：`.agenticdoc/goal.md`（「核心交付」与「Key Constraints」段）—— 本卡验证的正是该目标所要求的「worker 任务投递与回收契约」在真实运行链路上是否成立。
- **锚点**（以符号名定位；行号为 cutover 后基线，漂移时以符号名为准）：
  - `packages/multi-workers/autopilot/card_audit.py:189`（`audit()` —— 第 2 条）
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts:480`（`diffLedger` 内接入点 —— 第 3 条）
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts:244`（`stripNonDeclarativeSpans`）、`:337`（`isNegatedInScope`）、`:431`（`collectMalformedCandidates`）
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts:195`（`keyHasOwnerTraces`）
  - `packages/multi-workers/autopilot/roadmap.py:283`（`add_key_row` 的 `len(cells) != 3` 抛错点 —— 理解 T-20 修法用）

## 改动历史（本卡依赖的上游改动）
- **T-18**：`pm/ui-bridge.ts::mergeCardHeader` 追加 `envelope_producer: <id>@<version>` 身份行（第 1 条的验证对象）。
- **T-19**：`pm-orchestrator.ts` claim-free 修复派发 + `orphaned-keys` notice（按 kind 分流文案）；`index-store.ts::conductorClaimState`（`free|live|dead|stale`）。
- **T-20**：`autopilot/roadmap.py` keys 表行级容错（M>N 按首列/末列/中间拼回 role 恢复）+ `autopilot/conductor.py` 限频告警与降级局部化。
- **T-21**：`shared/change-ledger.ts` 否定感知 + 词元卫生 + 按 worker 归属修正（第 3 条的验证对象）。
- **T-22**：`pm-orchestrator.ts` 准入放宽为「index 行 ∨ key owner 痕迹」，无痕迹者仅告警不建档；`index-store.ts::keyHasOwnerTraces`。
- **cutover**：`python -X utf8 packages/multi-workers/mw.py build --install --allow-dirty`（`built + self-check OK`），repo/global bundle `A5B0FC9C…4932` → `975D4066…978D`；服务重启 PID 79536 → **158412**。
