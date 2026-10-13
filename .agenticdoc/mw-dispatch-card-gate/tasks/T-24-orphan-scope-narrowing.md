# T-24 ORPHANED 准入收窄：工作判据 + owner 证据时效 + idle/终态 key 不修（C-30）

- Key: mw-dispatch-card-gate｜Wave: 16｜type: coding｜依赖: T-19/T-22（终态）+ cutover（bundle `975D4066…978D`，服务 PID 158412）

## 上下文（C-30：修复路径在别的 key 上误触发，实测）
cutover 后本仓第一次自动触发修复，通知为：
`2 orphaned key(s) with undispatched work, no live claim and no live run (agent-team-loop,mw-dispatch-reliability) — claim-free repair dispatch applied`

实测它做了什么（PM 独立核对）：

| 观测 | 值 |
|---|---|
| 新增队列行 | `ga-spec-review-1`（key `agent-team-loop`）、`mw-dr-glm53`、`mw-dr-keyed-probe`（key `mw-dispatch-reliability`） |
| 状态与耗时 | 三条全部 `done`，派发→done 仅 **4 秒**（`17:25:33 → 17:25:37`） |
| 对应 worker 目录 mtime | `agent-team-loop/workers/ga-spec-review-1` = **09-07**；`mw-dispatch-reliability/workers/*` = **08-28** |
| index 状态 | 两 key 均 **`idle`**，Claim-Id = `20260808-174558-3176` / `20260828-160111-8496`（**8 月历史 claim**） |
| 为何立刻 done | 那些历史目录里**早有 `output.md`** ⇒ 按"产物优先"被 reap 成 done |

⇒ **两个缺陷**：
1. **"未派发工作"判据太宽**：把"worker 目录存在 `task.md` 且队列无对应行"当作未派发工作 ⇒ **历史目录天然满足**（老队列行早被轮转/裁剪）。
2. **"owner 证据"无时效**（T-22 放宽带来的洞）：8 月的 Claim-Id 也算 owner 证据 ⇒ `idle` 半个月的 key 变成可修复对象。

本次无实质伤害（未建目录、未真派活、未写那两个 key 的任何文件），但**污染了全局队列**，且会在其它 idle key 上重复犯，与项目目标要求的**隔离**冲突。

## 要求（逐条可验收）

1. **工作判据收窄**：一个任务算"未派发工作"必须同时满足
   a) `workers/<task-key>/task.md` 存在；
   b) **`output.md` 不存在**（无终态产物）；
   c) 被该 key **当前状态**引用（该 task-key 出现在 `pm-state.md` 或 `plan.md` 中）。
   ⇒ 历史目录（有 `output.md`）**一律不算**未派发工作。
2. **owner 证据必须当前有效**：
   `_index.parallel` 有行 **且状态 ∉ {`idle`}**（或该 key 的 `pm-state.md` 在近期窗口内被更新，或 claim 的宿主 `host:pid` 仍存活）**∨** 该 key 自身 owner 痕迹且满足上述时效。
   ⇒ `idle` + 8 月 Claim-Id ⇒ **不可修复**。
3. **idle / 终态 key 一律不修**：只产生一条 notice（notice 措辞，不得用"已拒绝"），内容含 key、被判定的工作、以及为何不可自动修（如"index 状态 idle"）。**0 修复、0 行写入**（须断言 `_workers.parallel` 与 `_index.parallel` 均未被本路径写入）。
4. **反例必测（用本次真实语料作夹具，逐字摘取）**：
   - ① `agent-team-loop`：index `idle` + Claim-Id `20260808-174558-3176` + `workers/ga-spec-review-1`（**有 output.md**，09-07）⇒ **0 修复、0 行、仅 notice**（C-30 回归钉）；
   - ② `mw-dispatch-reliability` 的 `mw-dr-glm53` / `mw-dr-keyed-probe`（08-28，有 output.md）⇒ 同上；
   - ③ **正例仍工作**：非 idle、owner 痕迹齐、工作满足 1a/b/c ⇒ 走 claim-free 修复，且 `_index.parallel` **不变**；
   - ④ 有活 claim ⇒ writer=0（AC-019 不变）；
   - ⑤ notice 每 key 每 session 一次。
5. **回归**：`test/suite/mwds-t19-orphan-ownership.test.ts`（13）、`test/suite/mwds-t22-orphan-evidence.test.ts`（10）、`worker-crosskey-readonly.test.ts`、`worker-store.test.ts`、`run-store.test.ts` 全绿。若 T-22 的 10 用例中有与本卡收窄**冲突**者，**先报告再改**，不得直接放宽。

## 种子（seed）
- **目标锚点**：`.agenticdoc/goal.md`（「Key Constraints」段：*不引入中心化调度器* / *Worker 进程级隔离* / *工具白名单按任务类型* —— 本卡收窄正是为了让"自动修复"不越过 key 边界）。
- **锚点**（符号名定位，行号为 cutover 后基线）：
  - `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1005`（T-22 放宽的准入分支 `row === undefined && !keyHasOwnerTraces(...)`）
  - `pm/pm-orchestrator.ts:810`（`repairDispatchOrphanedKey`）、`:903`（`orphaned-keys` alarm 构造）、`:436`（`NOTICE_DISPATCH_ALARM_KINDS`）
  - `shared/index-store.ts:195`（`keyHasOwnerTraces`）、`:134`（`conductorClaimState`）

## 改动历史（依赖的上游改动）
- **T-19**：claim-free 修复派发 + `orphaned-keys` notice（按 kind 分流文案）；`index-store.ts::conductorClaimState`。
- **T-22**：准入放宽为「index 行 ∨ key owner 痕迹」+ 无痕迹者仅告警（**本卡收窄其时效与工作判据**）。
- **cutover**：`build --install`（bundle `A5B0FC9C…4932` → `975D4066…978D`）、服务重启 PID 79536 → 158412；**C-30 即在 cutover 后首次自动触发时暴露**。

## 交付格式
- 写入允许面：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`、`shared/index-store.ts`、新建 `packages/coding-agent/test/suite/mwds-t24-orphan-scope-narrowing.test.ts`。
- 写入禁止面：`pm/ui-bridge.ts`、`shared/change-ledger.ts`、`worker/**`、`packages/multi-workers/**`、`test/extensions/**`、`.agenticdoc/**`（除本 worker 目录 taskDir）、其它 key 目录。
- 验收命令（在 `packages/coding-agent` 下）：
  - `node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t24-orphan-scope-narrowing.test.ts` 全绿；
  - `node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t19-orphan-ownership.test.ts test/suite/mwds-t22-orphan-evidence.test.ts test/suite/worker-crosskey-readonly.test.ts test/suite/worker-store.test.ts test/suite/run-store.test.ts` 全绿；
  - `npm run check` 退出码 0；若 biome 会改写你写面之外的文件，**先停下在报告中说明**。
- 报告须含：结论、证据（原始命令与输出；①②③④⑤ 场景输出；`_workers.parallel` 与 `_index.parallel` 未被写入的断言）、改动清单、残留与未验证、上下文来源清单。
- 不做 cutover、不重启服务；不改 task 卡；不得弱化或删除既有断言；如认为卡有误，在报告中提出供 PM 裁定。
