# T-12 回执：G3 答案面（gate-writer 闭集校验）+ G4 重臂（autoStartMonitor）

- Key: `mw-gate-verdict-hardening`（phase=EXECUTE）
- 卡: `.agenticdoc/mw-gate-verdict-hardening/tasks/T-12-g3-writer-g4-rearm.md`
- Worker task: `.agenticdoc/mw-gate-verdict-hardening/workers/mwg-t12-g3-writer-g4-rearm/task.md`（含文末「PM 追记（2026-10-10 20:35）」）
- 基线 HEAD: `776b82d7f`
- 依赖：T-08 ✓ + T-11 ✓ 已 done + acked
- AC: AC-009 / AC-012 / AC-018 · VC: VC-012 / VC-023
- 结果：**PASS**。三条 `[VERIFY]` 全绿（40 / 190 / 43 passed）；四组非空洞对照（A/B/C/D）全部按预期转红并已逐字节还原；`tsgo` 0 错误；`biome check`（5 个改动文件）Clean。

## 0. 结论摘要

1. **G3 答案面**：`gate-writer.ts` 只重写已存在的行；闭集 `{contract-change, retry}` 在写前 fail-closed 校验（错误点名合法集合）；门文件没有 `authorizes:` 行时，带 `--authorizes` 的应答**明确拒绝 + 提示**，绝不静默丢弃。
2. **G4 重臂**：`autoStartMonitor` 的幂等早退改为「同 ctx 幂等；ctx 不同 ⇒ 先 `stopMonitor` 再 `startMonitor`」，修掉会话替换后面板永久消失；`stopMonitor` 语义未动。
3. **TS 镜像（PM 追记）**：`status-model.ts` 的 `GATE_JSON_LIST_FIELDS` 加 `authorizes`，未知字段检查放宽为「`GATE_FRONTMATTER_FIELDS` **或** `GATE_JSON_LIST_FIELDS`」，值校验加同闭集；`GATE_FRONTMATTER_FIELDS` 40 名顺序一字未改。闭集在 TS 侧只有**一份**声明（`AUTHORIZES_ACTIONS`），并被跨语言 parity 用例锁死与 Python `gates.AUTHORIZES_ACTIONS` 同集。
4. 闭集校验是**非空洞**的：摘掉写侧校验/JSON-list 注册/ctx 变化分支/缺失行拒绝分支，对应用例分别转红（见 §4）。

## 1. 交付物与坐标（符号名 + 实际行号）

行号按最终工作树（biome 后）。起始快照：`gate-writer.ts`、`console.ts`、`test/suite/autopilot-gate-presentation.test.ts` 为 clean；`status-model.ts`、`test/extensions/agent-team-loop.test.ts` 带有**其它并发会话**的未提交改动（T-05 等），本次未回退、未重排其既有内容。

### 1.1 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts`

| 位置 | 内容 |
|---|---|
| `:25` | `import { AUTHORIZES_ACTIONS } from "./status-model.ts"`（唯一闭集来源，不另写一份） |
| `:42-48` | `AnswerGateOptions.authorizes?: string[]`（闭集、空/未给 = 不写、行必须已存在） |
| `:63` | `ANSWER_FIELDS = ["status", "answered_at", "answered_by", "note", "authorizes"]` |
| `:136-139` | **只重写 replacements 里给出的字段**：`if (!replacements.has(name)) continue;`（否则未传 `--authorizes` 时会把 `authorizes: []` 清成 `authorizes:`） |
| `:152-161` | 缺失行拒绝：`if (replacements.has("authorizes") && !rewritten.has("authorizes"))` ⇒ `{ok:false}`，错误串点名 `'authorizes:'`、给出 `authorizes: []` 修复提示、并给「或不带 --authorizes 应答」的出路 |
| `:177-188` | 写前闭集校验：越界 ⇒ `{ok:false}`，错误串 `... are not in the closed set (expected one of: contract-change, retry)` |
| `:196` | 渲染：`authorizes: '["retry","contract-change"]'`（单引号 JSON 数组，`renderScalar` 自动引用） |

回归点：正常应答（不传 `--authorizes`）仍只改 status/answered_at/answered_by/note，既有 4 字段字节级行为不变（`autopilot-console.test.ts` 既有断言全绿）。

### 1.2 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts`（只动 cmdGate / autoStartMonitor 两处）

| 位置 | 内容 |
|---|---|
| `:455` `cmdGate` | 新增 `--authorizes <a,b>` 解析：`:477-486` 从 `--authorizes` 起收集 token 直到下一个 `--flag`，按逗号 split、trim、丢空串；空值/未给 ⇒ `undefined`（不写）；`:493` 传入 `answerGate` |
| `:459` | cmdGate 自身的 usage 提示补 `[--authorizes <a,b>]` |
| `:709` | 新增模块级 `monitorCtx: ExtensionContext \| null`（当前活动面板所属 ctx；扩展工厂跨 `/new` `/resume` `/fork` `/import` 复用，interval 与 apply 回调存活） |
| `:736-743` | `autoStartMonitor`：`isMonitorActive()` 时同 ctx ⇒ 幂等 `return true`；ctx 不同 ⇒ `stopMonitor()`（用捕获的旧 apply 清 widget）后继续走 start 分支 |
| `:753` | start 成功后记录 `monitorCtx = ctx` |

未动：全局 `USAGE`（`:100`，属「只两处」约束外，见 §6 handoff）、`console.ts` 门行呈现段（T-08）、`monitor.ts`、`stopMonitor` 语义。

### 1.3 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（PM 追记镜像）

| 位置 | 内容 |
|---|---|
| `:646-652` | `export const AUTHORIZES_ACTIONS = ["contract-change", "retry"] as const;` + 内部 `AUTHORIZES_ACTION_SET`（TS 侧唯一闭集声明；gate-writer 复用） |
| `:739` | `GateRecord.authorizes: string[]` |
| `:756-764` | `export const GATE_JSON_LIST_FIELDS = new Set([..., "authorizes"])` |
| `:827-830` | 未知字段检查放宽：`!(GATE_FRONTMATTER_FIELDS.includes(name)) && !GATE_JSON_LIST_FIELDS.has(name)` ⇒ 报错 |
| `:916-921` | 值校验：`jsonStringList("authorizes")` + 越界 `GateFormatError`（`expected one of: contract-change, retry`） |
| `:990` | `return { ..., authorizes, ... }`（解析并保留该字段） |

`GATE_FRONTMATTER_FIELDS`（`:661-700`）40 名顺序一字未改。

### 1.4 测试

| 文件:行 | 内容 |
|---|---|
| `test/suite/autopilot-gate-presentation.test.ts:249` | VC-012 TS 侧：`authorizes: ["contract-change"]` 解析并保留；`[]` = 未授权；`["install"]` 越界拒绝且错误点名合法集；40 名单不含 `authorizes`；打印 `[VERIFY] VC-012: closed_set=2 listed_only=true` |
| `test/suite/autopilot-gate-presentation.test.ts:284` | 跨语言 parity：TS `AUTHORIZES_ACTIONS` 与 `GATE_JSON_LIST_FIELDS` 对 Python `gates.AUTHORIZES_ACTIONS` / `gates._JSON_LIST_FIELDS` 逐项相等 |
| `test/extensions/agent-team-loop.test.ts:5646-5836` | G3 gate-writer 用例段（`:5680` describe）：1) `--authorizes` 重写 materialized 行 + 其余行字节保持；2) CF-A 越界拒绝 + 门文件字节不变；3) CF-D 无行拒绝 + 提示；4) 不传 `--authorizes` 行不变；5) `/autopilot gate ... --authorizes` 端到端（含越界拒绝） |
| `test/extensions/agent-team-loop.test.ts:5845` | G4 重臂：同 ctx 幂等（无新帧）+ 新 ctx 必须重挂；打印 `[VERIFY] VC-023: rearmed=true panel_present=true` |

按 task.md：**未改** `test/suite/autopilot-console.test.ts`（T-14 保留），也未向其追加用例；新增用例全部放进 `agent-team-loop.test.ts`。

## 2. `[VERIFY]`（命令原文 + 真实输出）

### 2.1

```
cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts test/suite/autopilot-gate-presentation.test.ts
```

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[VERIFY] VC-011: age_shown=true blocked_marker=true
···········[VERIFY] VC-020: stamp_advances=true stale_warned=true
[VERIFY] VC-021: followed_within_cycles=2
[VERIFY] VC-022: degraded_frame=true silent_frames=0
················[VERIFY] VC-012: closed_set=2 listed_only=true
·············

 Test Files  2 passed (2)
      Tests  40 passed (40)
   Start at  18:53:36
   Duration  910ms (transform 503ms, setup 0ms, import 886ms, tests 512ms, environment 0ms)
```

### 2.2

```
cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
```

```
[VERIFY] VC-012: closed_set=2 listed_only=true
[VERIFY] VC-023: rearmed=true panel_present=true
 Test Files  1 passed (1)
      Tests  190 passed (190)
   Duration  4.14s (transform 384ms, setup 0ms, import 721ms, tests 3.31ms, environment 0ms)
```

（完整输出含 worker/poll 日志与既有 `[VERIFY]` 行；上列为本卡相关 marker 与汇总。）

### 2.3

```
cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts test/extensions/agent-team-loop-pm-state-sync.test.ts
```

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[VERIFY] VC-010: claim_ids_equal=true headings=7 updated_lines=1 crlf=27->27
[VERIFY] VC-011: claim_ok=true warnings=0 claim_ids_equal=true headings=7 updated_lines=1
[VERIFY] VC-012: coding_at_spec_allowed=true
···········································

 Test Files  2 passed (2)
      Tests  43 passed (43)
   Start at  18:53:48
   Duration  1.01s (transform 529ms, setup 0ms, import 963ms, tests 453ms, environment 0ms)
```

### 2.4 类型与格式（收尾）

```
> npx tsgo --noEmit -p tsconfig.json
tsgo exit: 0
```

> task.md 给的 `packages/coding-agent/tsconfig.json` 不存在（该包只有 `tsconfig.build.json`，指向已构建的 dist d.ts）；按仓库实际，从根用 `tsconfig.json`（含 `packages/*/src` + `packages/*/test`，即本卡全部写面）跑 `--noEmit`，0 错误。

```
> npx biome check <本卡 5 个改动文件>
Checked 5 files in 87ms. No fixes applied.
biome exit: 0
```

（biome `--write` 只作用于上面显式列出的 5 个文件，未触及其它会话文件。）

## 3. 非空洞对照（真跑红/绿，已逐字节还原）

对照前备份三个 src 文件；每次还原后校验 SHA256 与对照前完全相同。

对照前/final SHA256：

| 文件 | SHA256 |
|---|---|
| `gate-writer.ts` | `3CCF65682B403442462DADDA3A6375111131456A9D41A8E42CB31246900A860E` |
| `console.ts` | `0F5CD0EBE4C1C7301A38A7BC033E43023A666DC89133B14189E29C99D3324C2C` |
| `status-model.ts` | `78BE81CB8052D819C8CD4A040552078E42D2A0D1A2A59F4EA8D22AB7D36B09C6` |

### CF-A 摘掉写侧闭集校验 ⇒ 越界值被写入、用例转红

临时把 `gate-writer.ts:181` 的 `if (outOfSet.length > 0)` 改为 `if (false)`：

```
FAIL test/extensions/agent-team-loop.test.ts > G3 gate answer authorizes (T-12: AC-009/AC-012) > VC-012 CF-A: an out-of-set action is refused fail-closed and the gate file is byte-identical
AssertionError: expected true to be false // Object.is equality
  expect(result.ok).toBe(false);
 Tests  1 failed | 189 skipped (190)
```

还原后 `gate-writer.ts` sha 不变；该用例复绿（见 §2.2）。

### CF-B 摘掉 `GATE_JSON_LIST_FIELDS` 的 `"authorizes"` ⇒ TS 解析转红

临时删除 `status-model.ts:763` 的 `"authorizes",`：

```
FAIL ... > VC-012: authorizes is a recognized JSON-list extension field outside the frozen 40, closed set enforced
  expect(GATE_JSON_LIST_FIELDS.has("authorizes")).toBe(true)  -> false
FAIL ... > VC-012: the TS authorizes closed set and JSON-list registration mirror Python exactly
  expected [ 'constraints', 'open_items', ... ] to deeply equal [ 'authorizes', 'constraints', ... ]
 Tests  2 failed | 12 skipped (14)
```

⇒ 带 `authorizes: ["contract-change"]` 的门在 TS 侧被当未知字段跳过，镜像用例立刻转红。还原后 `status-model.ts` sha 不变。

### CF-C 摘掉 `autoStartMonitor` 的 ctx 变化分支 ⇒ VC-023 转红

临时把 `console.ts:736-743` 恢复为 `if (isMonitorActive()) return true;`：

```
FAIL test/extensions/agent-team-loop.test.ts > G4 monitor rearm after session replacement (AC-018/VC-023) > VC-023: an active panel bound to a different ctx is stopped and re-armed on the new ctx
AssertionError: expected false to be true
  expect(rearmed).toBe(true);
 Tests  1 failed | 1 passed | 188 skipped (190)
```

⇒ 新 ctx 上没有任何帧 ⇒ `/new` 后面板消失的形态被用例抓住。还原后 `console.ts` sha 不变。

### CF-D 摘掉「无 `authorizes:` 行」拒绝分支 ⇒ 应答被静默接受、用例转红

临时把 `gate-writer.ts:152` 的 `if (replacements.has("authorizes") && ...)` 改为 `if (false && ...)`：

```
FAIL test/extensions/agent-team-loop.test.ts > G3 gate answer authorizes (T-12: AC-009/AC-012) > VC-012 CF-D: asking to authorize on a gate with no authorizes line is refused with a hint (never dropped)
AssertionError: expected true to be false // Object.is equality
  expect(result.ok).toBe(false);
 Tests  1 failed | 189 skipped (190)
```

⇒ 这正是卡文要求覆盖的「门文件原本没有该行」边界。还原后 `gate-writer.ts` sha 不变。

还原校验：CF 结束后三个 src 文件 SHA256 与对照前逐字节相同（见上表）；随后 §2 三条 `[VERIFY]` 全绿。

## 4. 契约与写面纪律

- 闭集逐字 `{retry, contract-change}`：TS 侧仅 `status-model.ts:651` 一处声明，`gate-writer.ts` import 复用；`:284` 的 parity 用例对 Python `gates.AUTHORIZES_ACTIONS` 做集合相等锁。
- **只有人**能写 `authorizes`：写路径只有 `gate-writer.ts`（`/autopilot gate` 与手工编辑）；worker 侧由既有 `xkey-gate-guard.ts`（L0）拦截，本卡未改。
- `rewriteAnswerFields` 只重写已存在行：`gate-writer.ts:139` 的 `if (!replacements.has(name)) continue;` 保证「未传 `--authorizes` 时 materialized 行不动」；:152-161 保证「传了但行不存在 ⇒ 拒绝 + 提示」。
- `stopMonitor` 语义未动（非活动时不清 widget，`monitor.ts` 未改）；T-08 门行呈现段（`console.ts` `renderGateCards`/`cmdGates`）未动。
- 未 commit；未 `git add -A`/`git add .`/`git checkout .`/`git stash`/`git reset`/`git clean`；未碰 `.agenticdoc/_workers.parallel`/`_workers.acked`；未 kill 进程；未跑 `npm run build`/`npm test`/全量 vitest/`npm run check`。
- 测试只用 `mkdtemp` 临时目录；`autopilot-console.test.ts`（T-14 保留）未被改动。
- 既有 4 字段应答行为保持：`autopilot-console.test.ts` 的「changed == 4」等精确断言全绿（§2.3）。

## 5. 边界自查

- **门文件无 `authorizes:` 行 + 人传 `--authorizes`** ⇒ `answerGate` 返回 `{ok:false}`，错误串含 `no 'authorizes:' line` 与 `authorizes: []` 修复提示；门文件字节不变（CF-D 用例，`:5746`）。
- **锁已持有**：闭集校验在取锁之前，越界值不会进入读-改-写；`gates.lock` 也保持释放（CF-A 用例断言 `existsSync(gatesLockPath(root)) === false`）。
- **空/未给 `--authorizes`** ⇒ 不写（`undefined`），`authorizes: []` 保持原样（`:5773` 用例）。
- **无 UI / opt-out / suppressed** 早退顺序不变；只有「已有活动且 ctx 不同」才走 stop+start。

## 6. 注意事项 / handoff

1. **全局 `USAGE` 未加 `--authorizes`**：受 task.md「console.ts 只 cmdGate 与 autoStartMonitor 两处」约束，`:100` 的顶层 `USAGE` 未动；cmdGate 自身的 usage 提示（`:459`）已含该参数。若 PM 认为需要，可由持有 console.ts 其它段的卡补一行。
2. **`monitorCtx` 只在 `autoStartMonitor` 写入**：`cmdMonitor`（T-08/T-13 段）显式 `/autopilot monitor on` 不更新 `monitorCtx`。最坏情况是下一次 `autoStartMonitor` 多一次无害 stop+start；未扩写入面到 `cmdMonitor`。
3. **`status-model.ts` 与 `agent-team-loop.test.ts` 携带其它会话未提交改动**（前者 T-05，后者 T-15/其它），本卡新增均为追加式，未回退/重排其内容；`git diff` 中相应 hunk 可据此区分。
4. 门文件形态依赖 T-10 的 `authorizes: []` 物化（`conductor._gate_default_fields`），已在用例夹具中逐字复刻（`_stamp_gate_defaults` 的插入位置与 `default_action` 相邻）。
5. 三处 `[VERIFY]` marker 与 design §7 一致：`VC-012: closed_set=2 listed_only=true`、`VC-023: rearmed=true panel_present=true`。
