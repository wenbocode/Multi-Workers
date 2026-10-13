# RQ-3 证据：派发任务卡门禁该落在哪一层

- key：`mw-dispatch-card-gate`｜阶段：SPEC｜日期：2026-10-12｜基线 commit：`6c5189831`
- 唯一写入：本文件（`.agenticdoc/mw-dispatch-card-gate/evidence/research/spec-gate-layer-20261012.md`）
- 问题：门禁该落在 **工具层**（`dispatch_worker`）/ **服务层**（mw 队列消费）/ **独立校验器**，各自的拦截时机、覆盖面、可观测性、cutover 代价、误拒风险；两种入口如何同一判据。
- 方法：只读源码坐标 + 实测命令原始输出。未跑全量 vitest/pytest/`npm run check`/`build`/`mw build`；未做 git 操作。
- 机器/环境：Windows + PowerShell 5.1（bash 后端）；mw serve PID 79536 在跑；本 worker 由 launcher.py 派发（`PI_WORKER_TASK` 已设）。

---

## 0. 结论摘要（TL;DR）

1. **「两种入口」不完整，实测有 4 个入队生产者**（§1）。`dispatch_worker` 与 `/worker` 只是其中 2 个 TS 入口；第 3 个是 autopilot conductor 的 `autopilot/dispatch.py::dispatch`（纯 Python 直接写 task.md + 队列行，`origin: conductor`）；第 4 个是手写队列行（OverCode 事故类，已被 `_validate_task_path` 部分治理）。
2. **只有服务层（launcher 消费点）能拦到全部 4 个生产者**；工具层只能拦到 TS 的 2 个入口；独立校验器**不拦任何一次派发**（它只出报告/退出码），因此单靠它无法满足 AC-001「无卡派发 ⇒ 拒绝」。
3. **工具层是唯一能让 PM 显式传入「卡路径」的层**（新增 `card_path` 参数），从根上消除 task_key→卡文件名的映射歧义；服务层只能靠约定/glob 猜，`manual-*`、`ap-*` 与 `T-NN-slug` 三种命名并存 ⇒ 服务层单点误拒面显著更大。
4. **推荐：工具层为主拦截（同步、fail-closed、可带 card_path）+ 服务层为兜底（拦 conductor/手写行，失败转 `failed` 行），判据用一份黄金用例表跨 TS/Python 镜像 + parity 测试**（沿用 `keyNameRefusal` ↔ `key_name_refusal` 的既有范式）。代价 = 两处改动 + 一次 `mw build --install` + 一次 `mw stop/serve`。
5. **误拒（P-03）是本 key 最大风险，不是漏拦**：服务层按「卡必须存在」拦，会同时命中 `ap-*`（autopilot 全部派发）、`manual-*`（`/worker` 全部派发）与历史非终态行；必须按 `origin`/`type` 分轴或提供显式豁免，否则 autopilot 直接停摆。RQ-2 实测语料已把误拒上界量化：345 张卡在 T1 严口径下 301 张不合格（87.2%）、T1e 中口径 237 张（68.7%）——**默认 fail-closed 会让绝大多数历史卡变红**（见 §9）。

---

## 1. 派发/入队路径实测（候选落层的边界坐标）

### 1.1 入口 A：`dispatch_worker` 工具（PM 侧 TS）

注册：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1814`（`registerWorkerTools`）/ `:1825`（`name: "dispatch_worker"`）。

execute 内的**顺序**（坐标 = 同一文件）：

| # | 行 | 动作 | 是否副作用 |
|---|---|---|---|
| 1 | `:1906` | `validateRagEnabled(projectDir)` | 否 |
| 2 | `:1916` | `foreignLiveClaimRefusal(indexStore, ownerKey)`（跨 key 守卫） | 否 |
| 3 | `:1930` | `resolveDispatchType(cli, type)` | 否 |
| 4 | `:1941` | `dispatchDocGaps(...)`（相位文档门禁） | 否 |
| 5 | `:1959` | `fs.existsSync(taskDir)` 冲突检查 | 否 |
| 6 | `:1979` | `judgeWriteIntent(...)`（写面可满足性） | 否 |
| 7 | `:2010` | `planDispatchFrontmatter(...)`（模型覆盖） | 否 |
| 8 | **`:2026`** | **`writeDispatchTaskMd(...)` → `fs.mkdirSync` + `writeFileSync`** | **是（第一个）** |
| 9 | `:2041` | `dispatchTask(...)` → `WorkerStore.upsert`（写 `_workers.parallel`） | 是 |

⇒ 门禁必须插在 `:2026` 之前，才能保证「拒绝零副作用」。

### 1.2 入口 B：`/worker` slash 命令（PM 侧 TS）

注册：同文件 `:2355`（`registerWorkerCommands`）/ `:2365`（`pi.registerCommand("worker")`）。

关键坐标：`:2419` type 解析、`:2445` 跨 key 守卫、`:2454` writeless role 判定、`:2477` docs 门禁、`:2486` 模型计划、**`:2502` `writeDispatchTaskMd`（第一个副作用）**、`:2518` `dispatchTask`。

注意：**该入口的 task_key 是自动生成的**（`manual-` + `Date.now()`，见 `:2430` 一带），因此 `tasks/<task_key>.md` 这种约定在它身上**没有天然卡名**。

### 1.3 入口 C：autopilot conductor（Python，直接入队）

`packages/multi-workers/autopilot/dispatch.py::dispatch`：函数内 `task_md.write_text(...)` 后 `mw_common.upsert_worker_row(wpath, row)` 直接写队列（模块 docstring 即写「task.md is written first, then the queue row under .mw/workers.lock」）。task_key = `ap-{owner}-{stem}`（`task_key_for`），行带 `origin: mw_common.WORKER_ORIGIN_CONDUCTOR`。

⇒ 这条路径**完全不经过** `dispatch_worker` / `/worker`，也不经过任何 TS preflight。

### 1.4 入口 D：手写队列行 / 手写 task.md

历史事故（`launcher.py:449` 注释引用 OverCode pch-migration-s1）：在 `.agenticdoc` 根手写 task.md + 队列行绕过 `dispatch_worker` 的 workerTaskDir 放置。既有治理 = `_validate_task_path`。

### 1.5 消费者（不是入口）：`launcher.py::_poll_once`

`packages/multi-workers/launcher.py:872`。每 5s（`DEFAULT_POLL_INTERVAL = 5`，`:49`）执行一次：

- `:891` `archived = mw_common.archive_stale_entries(project_dir)` —— **既有服务层存在性门禁**：行非终态但 `task_path` 不存在 ⇒ 移入 `_workers.stale.parallel`（`mw_common.py:2138`，`STALE_REASON = "task.md not found"`，`:161`）。注意该通道**对 PM 静默**（`_workers.stale.parallel` 无 TS/Python 消费方，详见 RQ-1 §5.2）——「卡缺失」若照搬此通道就会静默消失，必须改用下面的 failed + worker.log 形态。
- `:923` 起 discover new pending；`:961` `_validate_task_path(project_dir, entry["task_path"])`；违规 ⇒ `:963` `_record_spawn_failure` + `:965` `_update_status(..., "failed")` + `continue`（**不 spawn**）。
- 空间足够 ⇒ `:971` `_spawn(entry, ...)`。
- `_spawn`（`:1055`）→ `_build_command`（`:523`）→ `_starter_prompt`（`:480`）→ `_require_task_file`（`:437`，task.md 不存在 ⇒ RuntimeError ⇒ `:1124` 记录 spawn 失败 + status failed）。

⇒ 服务层已有**两个**「派发前拦截点」的现成范式：discover 期（`_validate_task_path`）与 spawn 期（`_require_task_file`）。卡门禁插在 discover 期与既有范式同形。

---

## 2. ① 落层对照表

> 「两种入口」按 spec §2 的口径指（交互式 `dispatch_worker` + mw 服务队列消费）；本表同时给 4 生产者覆盖口径。

| 维度 | (a) 工具层：`dispatch_worker`（+`/worker`） | (b) 服务层：`launcher.py` 队列消费点 | (c) 独立校验器（脚本 / 测试） |
|---|---|---|---|
| **拦截时机** | PM 的同一 turn 内，`writeDispatchTaskMd`（`ui-bridge.ts:2026`/`:2502`）之前；同步。 | launcher 每 5s 轮询发现 `pending` 时（`launcher.py:872`），在 `:961` `_validate_task_path` 邻位、`_spawn` 之前；异步（≤5s + PM 侧 4s 轮询）。 | 手动/verify 时执行；**不在派发路径上**。 |
| **能否拦到 4 个生产者** | 只拦 A/B 两个 TS 入口；C（conductor `dispatch.py`）、D（手写行）**拦不到**。 | **全部拦到**（A/B/C/D 的产物都是同一队列行 + task.md）。 | 能**看到**全部，但**不拦**任何一次派发（无 goto 效应）。 |
| **失败可观测性** | PM 当前 turn 直接看到拒绝文本（tool 返回值，`ui-bridge.ts:1919` 形态）；`/worker` 走 `ctx.ui.notify(..., "warning")`。无退出码。可加审计行（§3 `[GATE]` 范式）。 | 行 `status=failed` + `worker.log` 写 `[launcher] spawn failed (<ts>): <reason>`（`_record_spawn_failure`，`launcher.py:57`）+ `launcher.log` stderr 行；PM 由 `startWorkerPollLoop`（`POLL_INTERVAL_MS = 4000`，`pm-orchestrator.ts:52`）以 `deliverWorkerResult`（triggerTurn）读到，**但仅当 `ownerKeyOf(entry) === watch.key`**（`pm-orchestrator.ts:972`），否则只在 widget 里（`readTerminalDetail`，`ui-bridge.ts:533`）。 | 退出码 0/1 + stdout 差集清单（`diff-installed.py` 范式）；或测试红 + `[FORMS]`/`[ANCHORS]` 式计数行（上一 key 范式）。离派发时刻很远。 |
| **cutover 代价（驻留？）** | **属驻留**：TS 经 esbuild 打包为 `packages/multi-workers/dist/extensions/agent-team-loop.js` 并**全局安装**到 `~/.pi/agent/extensions/agent-team-loop.js`（`mw.py:_deploy_bundle`, `:4435`）。改源码后必须 `mw build --install`（esbuild + `npm run build` dist）并**重启 pi 窗口**；`cmd_build` 结尾明确打印 `Restart open pi windows to load the new bundle and dist.`（`mw.py:4538`）。陈旧可由 `mw doctor` 的 `bundle.stale` 检出（`mw_common.py:2637`）。 | **属驻留**：`mw serve` 在 `mw.py:321` 用 `subprocess.Popen` 起一次 `launcher.py`，其 `run()` 是 `while True: _poll_once(...)`（`launcher.py:1020` 附近）。改 `.py` 需 `mw stop` + `mw serve`（无 build）；`serveStaleness`（`mw-runner.ts:272`，基线 = mw 目录 `.py`/`.json` 最新 mtime，跳过 `test_*`/`_*`/`dist`/`.tmp`/`__pycache__`）会提示陈旧。 | **不属于驻留**：`mw.py doctor` 每次 `subprocess` 重跑（`mw_runner.ts:414`），改脚本**零 cutover**；测试同理。 |
| **误拒风险（P-03）** | 中。PM 控制输入：类型轴可按 `type=coding/vision` 强制、`review/research` 豁免；`/worker` 的 `manual-*` 无天然卡名 ⇒ 必须豁免或自动落卡。可按入口分别给豁免，容易做窄。 | **高**。命名轴 `T-NN-slug`（`tasks/`）/ `mwgf-tNN-slug`（worker dir）/ `ap-*`（conductor）/ `manual-*` 四者不一一对应，服务层只能靠约定/glob 猜；不改判据就按 type/origin 分轴 ⇒ `ap-*` 与 `manual-*` 直接全红。 | 低（不拦派发）；但若被当门禁用（gate 语义）则把误报转成阻塞，风险等价于调用它的那层。 |
| **漏拦风险** | **高**：C/D 静默通过（正是 T-20 事故的同形洞）。 | 低：覆盖全部入队产物；但**行可被直接改状态**绕过（改 `_workers.parallel` 不经 launcher）。 | 无（不拦）。 |
| **「两种入口同一判据」的天然性** | 需人为抽公共函数（现有两入口是复制粘贴，见 §3）。 | 天然：一个队列消费点就是唯一判据点；但判据用 Python 重写。 | 判据可共享，但不生效。 |

### 2.1 关键差异一句话

**覆盖面**服务层 > 工具层 > 校验器；**可观测性/同步性**工具层 > 服务层 > 校验器；**cutover** 校验器(0) > 工具层/服务层（都需重启，工具层还要 build）；**误拒可控性**工具层 > 服务层。
---

## 3. ② 一致性要求：两种入口同一判据的实现建议

### 3.1 现状：两个 TS 入口是**复制粘贴**，不是共享 preflight

`dispatch_worker`（`ui-bridge.ts:1906`–`:2041`）与 `/worker`（`:2428`–`:2518`）各写一遍同样的顺序：RAG 校验 → 跨 key 守卫 → type → docs 门禁 → task dir 冲突 → write-intent → 模型计划 → `writeDispatchTaskMd` → `dispatchTask`。**没有**一个共享的 preflight 函数。今天的一致性靠：

- 两处同时改（人工），以及
- `CROSS_KEY_READ_ONLY_SURFACES`（`ui-bridge.ts:261`）+ 覆盖率测试 VC-011，保证「拒绝文本里点名的面」与「真实调用守卫的面」一致。

⇒ 新增门禁若只加在一个入口，P-04（工具层拦、另一处放行）会立刻成立。**必须抽一个共享判据函数，两处各调一次。**

### 3.2 建议的物理落点与依赖方向

新增纯判据模块（名字二选一，推荐前者）：

- `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts`
- 或并入 `shared/task-frontmatter.ts`（若只做「三段齐备 + 非空」的纯文本判定）

导出（建议形状）：

```ts
export interface CardCheckInput {
  cardPath: string;            // 已解析的 candidate 卡路径
  keyDir: string;              // .agenticdoc/<ownerKey>
  text?: string;               // 传入则不再读盘（测试/纯函数复用）
}
export type CardCheck =
  | { ok: true; path: string; sha256: string }
  | { ok: false; code: "card-missing" | "card-section-missing" | "card-outside-key";
      message: string; missingPath?: string; missingSections?: string[] };
export function checkDispatchCard(input: CardCheckInput): CardCheck;
```

调用点（两处，且都在第一个副作用之前）：

- `dispatch_worker`：`ui-bridge.ts:1959`（task dir 冲突检查）与 `:1979`（write-intent）之间，或紧邻 `:1916` 跨 key 守卫之后。
- `/worker`：`ui-bridge.ts:2445` 跨 key 守卫之后、`:2502` 之前。

依赖方向：

```
pm/ui-bridge.ts  ──import──▶  shared/dispatch-card.ts  ──import──▶  node:fs, node:path, ./paths.ts
worker/*.ts      ──import──▶  shared/dispatch-card.ts        （若 worker 侧也要复用）
```

- `shared/` 是叶子层：`shared/task-frontmatter.ts` 是「零 import 纯模块」的先例（其文件头注释明说 purity test 锁定零 import）；`shared/phase-docs.ts:3` 已经 import `../pm/goal-reader.ts`（shared→pm 的反向边**存在但不该扩散**）。
- 新模块**只允许** import `node:fs` / `node:path` / `./paths.ts`，**禁止** import `pm/` 或 `worker/`。这样 `pm→shared` 与 `worker→shared` 都是单向边，**不可能成环**（环只会出现在 shared 反向 import pm/worker 时）。

### 3.3 若服务层也要同一判据：跨语言镜像 + 黄金表 parity（既有范式）

TS 与 Python 不能共享函数。既有范式是**同一判据两份实现 + 一份黄金用例表 + 跨语言 diff 测试**：

- TS：`shared/index-store.ts:67` `keyNameRefusal`（codes：`empty-key` / `reserved-key-name` / `key-path-escape` / `key-illegal-shape`）。
- Python 镜像：`.agents/skills/agentic-task/scripts/update_index.py:118` `key_name_refusal`（同 4 个 code；`:173` `ERROR: refused key name (<code>): <message>` → stderr + rc 1）。
- parity 测试：`packages/multi-workers/test_update_index_key_refusal.py`（内含 node parity harness；本机实测 `23 passed in 0.72s`，原文见 §6）。

⇒ 卡门禁若要同时落工具层 + 服务层，判据的**单一来源**应是「黄金用例表 + 判据语义」，实现允许两份，但必须有 parity 测试锁死（否则两层漂移 = P-04 的跨层版本）。

### 3.4 卡路径解析是判据的前置输入，也是各层能力差异点（实测）

`tasks/` 与 worker 目录的命名**不一一对应**，实测（本 workspace）：

| worker task_key / 队列 | 对应 `tasks/*.md` | 关系 |
|---|---|---|
| `mwgf-t15-python-claim` | `T-15-python-claim.md` | 前缀不同（`mwgf-t15` vs `T-15`） |
| `mwgf-t20-final-fixes` | （T-20 卡缺失，事故本体） | — |
| `ap-k1-<stem>`（conductor） | 无 | conductor 不落 `tasks/`（`dispatch.py` 不写卡） |
| `manual-<ts>`（`/worker`） | 无 | 自动生成 key |

实证命令与原始输出（§6 有完整块）：`mw-guard-form-hardening/tasks/` 有 `T-01..T-19`（无 T-20），`workers/` 有 `mwgf-t15..mwgf-t20` 等。

唯一机器可读的既有映射逻辑在 autopilot conductor：`packages/multi-workers/autopilot/conductor.py:2417` `_plan_task_file_stems`（`T-NN-slug` 与去 `T-` 前缀的 stem 都是候选）+ `:2433` `_missing_plan_tasks`。它只覆盖 `T-NN-slug` 一种形态，且是 conductor 自用。

⇒ 工具层可以让 PM 用 `card_path` **显式**给出卡（消除歧义）；服务层只能 glob/约定猜（歧义不可消除）。
---

## 4. ③ 既有门禁形态对照（哪一层 / 什么失败形态 / 样例原文）

| 门禁 | 所在层 | 失败形态 | 坐标 | 样例（原文） |
|---|---|---|---|---|
| **写面守卫**（bash write-surface，AC-005b） | 运行期「工具钩子层」（worker 进程内，`pi.on("tool_call")`） | `{ block: true, reason }` + trace `[WRITE_SCOPE]` 审计行 + `[TOOL_ERR]` + run 尾 `[WRITE_SCOPE_SUMMARY]` | 钩子注册 `worker/worker-mode.ts:2164`；reason 文本 `:1608`–`:1623`；审计行 `:1660`–`:1676`；summary `:1677`–`:1691` | 见 §4.1 原始输出 |
| **跨 key 守卫** `foreignLiveClaimRefusal`（AC-024） | **工具层**（TS，三个 writer 面：`dispatch_worker` / `/worker` / `advance_phase`） | 稳定码 + 多行文本，作为**工具返回值** / `ctx.ui.notify`，**不抛异常、无退出码** | 定义 `pm/ui-bridge.ts:277`；码 `:251`；面清单 `:261`；调用点 `:1916`（tool）、`:2343`（advance_phase）、`:2445`（/worker） | `[cross-key-read-only] key 'mw-foreign' is held live by another window (claim <host:pid>) — ...`（`:289`–`:300`） |
| **key 名门禁** `keyNameRefusal`（AC-006） | **共享纯函数层**（TS）+ **Python 镜像**（rc/码） | TS：返回 `{code,message}`，由调用者拼拒绝文本；Python：`rc=1` + stderr | TS `shared/index-store.ts:67`（codes：`empty-key`/`reserved-key-name`/`key-path-escape`/`key-illegal-shape`）；Python `update_index.py:118`；stderr `:173` | Python：`ERROR: refused key name (reserved-key-name): '_scratch' is a reserved framework name, ...` |
| **实现入口门禁** `implementation-gate`（mw-implementation-gate） | **工具钩子层**（PM/worker/交互全模式，`pi.on("tool_call")`） | `{ block: true, reason }` + `.agenticdoc/_impl_gate.log` 审计行 `[GATE] <ISO> blocked tool=<t> target=<p> basis=<b>`；逃生舱 = 活跃 claim / `PI_WORKER_TASK` / 新鲜 mini-spec | 注册 `shared/implementation-gate.ts:registerImplementationGate`；审计 `recordImplGateAudit`；挂载 `index.ts:59`（在 `PI_WORKER_TASK` 分支之前 ⇒ 两模式都跑） | `[GATE] 2026-10-12T... blocked tool=write target=packages/x.ts basis=no-claim-no-mini` |
| **服务层位置门禁** `_validate_task_path` | **服务层**（launcher 队列消费） | 行 `status=failed` + `worker.log` 原因行 + launcher stderr；**不是**返回给 PM 的文本 | `launcher.py:449`（定义）/ `:961`（调用）/ `:963` `_record_spawn_failure` / `:965` `_update_status("failed")`；原因行 `:57` | worker.log：`[launcher] spawn failed (2026-...): invalid worker-task location: root-task/task.md - tasks must live under ...` |
| **服务层存在性门禁** `archive_stale_entries` | **服务层**（launcher 每次 poll 开头） | 行移入 `_workers.stale.parallel` 并附原因；**该文件无消费方 ⇒ 对 PM 静默**（RQ-1 §5.2） | `mw_common.py:2138` / `STALE_REASON` `:161` / 调用 `launcher.py:891` | stale 行：`<original row> | <ts> | task.md not found` |
| **服务层 spawn 存在性** `_require_task_file` | **服务层**（spawn 命令构建） | RuntimeError ⇒ spawn 失败记录 + failed | `launcher.py:437` / `_starter_prompt:480` / `_build_command:523` / 捕获 `:1124` | `RuntimeError("task.md not found: <path>")` |
| **tasks/ 存在性审计**（execute gate） | **审计层**（PM state guard，非阻塞 warning） | `warnings[]` 文本（`[audit] execute gate: ...`） | `shared/pm-state-guard.ts:186`（`tasks/` 无 `.md`）/ `:190`（目录缺失） | `[audit] execute gate: tasks/ has no .md files.` |
| **plan↔tasks 一致性**（autopilot，tasks→execute 边界） | **审计/校验层**（conductor，转成 synthetic blocking gap ⇒ 派 L2 verifier） | gap 条目，进入 verifier prompt，不是硬拒 | `autopilot/conductor.py:2433` `_missing_plan_tasks` / `:2417` `_plan_task_file_stems`；orphan 方向 `:1369` | `plan 任务 T-99-missing 在 tasks/ 缺失`（`rule=execute-gate`） |

### 4.1 写面守卫原始输出（本次会话实测，可复现）

Bash（PowerShell）写入本 worker 目录之外的 `.tmp/`：

```
> "probe" | Out-File -Encoding utf8 .tmp\rq3-probe.txt
write-scope: blocked bash write to .tmprq3-probe.txt: outside the worker write surface [rule=scope]; allowed: H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\workers\mwd-rq3-gate-layer or H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\evidence
```

对应 trace.log 审计行（本任务 `trace.log` 原文）：

```
[WRITE_SCOPE] 2026-10-12T08:27:41.976Z write-scope blocked=true rule=scope detail=outside-allowed-surface pattern=out-file target=.tmprq3-probe.txt cmd=cd H:\git\Multi-Workers; "probe" | Out-File -Encoding utf8 .tmp\rq3-probe.txt; if (Test-Path .tmp\rq3-probe.txt) { Write-Output "WROTE .tmp/rq3-probe.txt"; Get-Content .tmp/rq3-probe.txt } else { Writ
[TOOL_ERR] 2026-10-12T08:27:41.977Z bash write-scope: blocked bash write to .tmprq3-probe.txt: outside the worker write surface [rule=scope]; allowed: H:\git\Mu
```

**旁证（写面守卫的一处误拒，与卡门禁无关但同层同形）**：用**反斜杠相对路径**写允许目录内文件也被拦（守卫把 `\` 当路径分隔符剥离失败）：

```
> Set-Content -Path .agenticdoc\mw-dispatch-card-gate\evidence\research\_rq3-probe.md -Value "# probe" -Encoding UTF8
write-scope: blocked bash write to .agenticdocmw-dispatch-card-gateevidenceresearch_rq3-probe.md: outside the worker write surface [rule=scope]; allowed: H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\workers\mwd-rq3-gate-layer or H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\evidence
```

同一路径改成**正斜杠**后写入成功。⇒ 写面守卫的「误拒」是真实存在的代价维度；新门禁的路径规范化不能重蹈（尤其服务层要做 `paths` 比较时）。

### 4.2 形态一致性结论

- **工具层既有守卫的统一形态 = 「稳定码 + 多行拒绝文本」（可选审计行）**：`[cross-key-read-only] ...` / `[worker-write-surface] ...` / `[GATE] ...` 审计行。新门禁若落工具层，应沿用：`[<stable-code>] ...` 文本 + 缺失路径/缺失段指名 + 可选审计行。
- **服务层既有形态 = 「状态翻转 + worker.log 原因行」**：`status=failed` + `[launcher] spawn failed (<ts>): <reason>`。新门禁若落服务层，应沿用这一形态（`_validate_task_path` 邻位），**不要**试图在服务层造工具层式文本（PM 拿不到）。
- **跨语言共享判据的既有形态 = 「黄金表 + 双实现 + parity 测试」**（`keyNameRefusal` ↔ `key_name_refusal`）。
---

## 5. ④ 候选方案的改动面估计

> 行数为量级估计（非实测 diff）；「既有测试影响面」是最大隐性成本项。

### 方案 A：工具层单点（判定函数 + 两处调用，卡路径先用约定）

| 项 | 内容 |
|---|---|
| 文件与坐标 | 新增 `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts`（~90–150 行）；`pm/ui-bridge.ts` 两处调用（`:1959`–`:1979` 间、`:2445`–`:2502` 间，各 ~8–15 行） |
| 改动行数量级 | 判据模块 1 个（~100–150 行）+ 调用点 ~20–30 行 |
| 是否需要 cutover | **需要**：`mw build --install`（esbuild + `npm run build` dist）+ 全局安装 + **重启 pi 窗口**（`mw.py:4538` 原文）；`mw doctor` 的 `bundle.stale` 可自检 |
| 是否需要新测试文件 | 需要：`packages/coding-agent/test/suite/dispatch-card-gate.test.ts`（~150–250 行：无卡/缺段/等长篡改/合法卡放行 4 反例） |
| 既有测试影响面 | **大**：实测 8 个 TS 测试文件共 55 处 `dispatch_worker` 引用（`worker-crosskey-readonly` 16、`agent-team-loop` 16、`mwds-t01` 6、`pm-state-sync` 5、`vision-gate`/`vision-autoroute`/`rag-tools`/`mwds-t02` 各 3）+ 5 个文件直接调 `/worker` handler。默认 fail-closed 下这些 fixture 全部无卡 ⇒ 需补卡或引入测试开关 |
| 误拒风险 | 中：按 `type` 轴（coding/vision 强制、review/research 豁免）+ `manual-*` 自动落卡或豁免，可做窄 |
| 漏拦 | 拦不到 C/D（conductor、手写行） |

### 方案 B：服务层兜底（launcher 队列消费点）

| 项 | 内容 |
|---|---|
| 文件与坐标 | `packages/multi-workers/launcher.py` discover 循环 `:957`–`:971`（紧跟 `_validate_task_path` 之后，~10–18 行）；判据函数放 `mw_common.py`（~60–110 行）或新 `packages/multi-workers/dispatch_card.py` |
| 改动行数量级 | 判据 ~60–110 行 + launcher ~15 行 |
| 是否需要 cutover | **需要但轻**：无 build，`mw stop` + `mw serve`（launcher 是常驻子进程，`mw.py:321`）；`serveStaleness` 会提示陈旧 |
| 是否需要新测试文件 | 需要：`test_dispatch_card.py`（~100–200 行）+ `test_launcher.py` 既有 fixture 补卡（该文件 97 个 `def test_`，其中 `_poll_once` 出现在 8 处，队列构造 helper 需同步） |
| 既有测试影响面 | **大**：所有走 `_poll_once` 的用例的队列行 fixture 无卡；默认 fail-closed 会把它们推成 failed，需补卡/加开关 |
| 误拒风险 | **高**：`ap-*`（conductor 全部）、`manual-*`（`/worker` 全部）、历史非终态行；`tasks/` 命名四形态不一一对应（§3.4） |
| 漏拦 | 低（覆盖全部入队产物）；但直接改 `_workers.parallel` 状态可绕过 launcher |

### 方案 C：混合（工具层主拦截 + 服务层兜底 + 跨语言 parity）——推荐

| 项 | 内容 |
|---|---|
| 文件与坐标 | A + B + `packages/multi-workers/test_dispatch_card_parity.py`（黄金表 + node harness，参照 `test_update_index_key_refusal.py`，~80–150 行） |
| 改动行数量级 | ~300–500 行（含测试） |
| 是否需要 cutover | **需要两次但可一次做完**：`mw build --install` + `mw stop/serve` + 重启 pi 窗口 + 冒烟 |
| 是否需要新测试文件 | 需要：A 的 TS 测试 + B 的 Python 测试 + parity 测试（3 个） |
| 既有测试影响面 | A + B 的并集（最大） |
| 误拒风险 | 低（工具层可窄化 + `card_path` 显式化），但服务层兜底仍必须按 `origin`/`type` 分轴 |
| 漏拦 | 最低（4 生产者全覆盖） |
| 附加成本 | parity 测试要维护 TS↔Python 两份实现（既有 `keyNameRefusal` 已证明可行，实测 23 passed / 0.72s） |

### 明确不推荐：校验器单独承担 G1

独立脚本/测试（`diff-installed.py` 式）能满足「可执行检查」（P-02）与 AC-003 的一致性红/绿，但**不在派发路径上** ⇒ 不能实现 AC-001「无卡派发 ⇒ 拒绝」。它只能作为 AC-003/AC-005 的**审计工具**（`mw doctor` 每次 subprocess 重跑，零 cutover，`mw_runner.ts:414`），或作为方案 A/B/C 的判据实现载体（被它们调用）。`tasks/` 存在性的既有审计（`pm-state-guard.ts:186`）与 plan↔tasks 一致性（`conductor.py:2433`）都属于这个层级，且都**不阻塞**派发。
---

## 6. ⑤ 每个方案「怎么证明它真的生效」

### 方案 A（工具层）

| 断言 | 证据形态（运行期） |
|---|---|
| AC-001① 无卡 ⇒ 拒绝且文本含缺失路径 | `dispatch_worker` 返回的 tool 文本含 `[<stable-code>]` + 绝对缺失路径；同一断言在测试里是 `r.content[0].text`（既有 `worker-crosskey-readonly.test.ts` 范式：`expect(text).toContain("[cross-key-read-only]")`） |
| 零副作用 | `fs.existsSync(path.join(root, KEY, "workers", taskKey)) === false` 且 `store.readAll()` 无新行（同范式） |
| AC-005 误拒 = 0 | 对既有 `tasks/*.md` 语料逐条跑判据，放行数 == 总数（RQ-2 出语料后才有绝对值） |
| AC-003③ 判别力 | 等长篡改卡 ⇒ sha256 变 ⇒ 判据红；恢复 ⇒ 绿 |
| 可观测性 | transcript 内文本（PM 同一 turn 可见）；可选 `.agenticdoc/_impl_gate.log` 式审计行 |
| **无法验证** | PM 是否会读错误并纠正（行为面）；**C/D 生产者**在该层根本没有证据（这正是漏拦） |

### 方案 B（服务层）

| 断言 | 证据形态（运行期） |
|---|---|
| 拦截发生 | 队列行 `status == "failed"`；`workers/<task_key>/worker.log` 出现 `[launcher] spawn failed (<ts>): <reason>`；launcher stderr 行（`launcher.py:963/965`） |
| 未 spawn | `running_procs == {}`（`_poll_once` 单测范式和 `test_launcher.py::TestTaskLocationContract` 一致；本机实测 5 passed） |
| 失败原因指名卡路径 | worker.log 原因文本（可 `rg` 检索） |
| **无法验证** | 「PM 立刻看到」：PM 侧 `deliverWorkerResult` 只在 `ownerKeyOf(entry) === watch.key` 时触发（`pm-orchestrator.ts:972`），跨 key 行只落 widget（`ui-bridge.ts:533`）。要验证必须开真实窗口观测，本 RQ 未做 |
| 另需注意 | 服务层是 **check-then-use 的异步窗口**：工具层放行后、launcher 消费前卡被删，服务层会拦成 failed；但「这次派发是否被正确拒绝」在竞态下没有单一判定证据 |

### 方案 C（混合）

- = A 与 B 的证据之和（两层各自可独立证伪）。
- 跨层一致性：`test_dispatch_card_parity.py` 黄金表逐条比 TS/Python 同码同判（既有范式：`test_update_index_key_refusal.py` 内含 node parity harness，本机实测 23 passed in 0.72s）。
- **无法验证**：判据语义的「正确性」本身（三段是否齐备属结构判定，非语义质量——spec §2 明确 Out）；跨层 TOCTOU（同 B）。

---

## 7. ⑥ 未验证怀疑清单

1. **卡↔task_key 映射规则无机器可读约定**（本 RQ 实测到 4 种命名：`tasks/T-NN-slug.md`、worker dir `mwgf-tNN-slug`、`ap-*`、`manual-*`）。RQ-1 §6.2 已给出同向实测：key `mw-guard-form-hardening` 有 19 张卡 / 36 行队列，仅 18 行可机械匹配，另 18 行是 QC/RQ/DRQ/smoke 等**按设计无卡**的派发。⇒ 服务层「约定 glob」方案要么误拒这 18 行，要么需要显式映射规则；映射规则本身未见任何机器可读落点。
2. **AC-005 的绝对值已由 RQ-2 给出（本 RQ 未复算）**：345 张卡，T1 严口径不合格 301（87.2%）、T1e 中口径不合格 237（68.7%）、T2 宽口径 72（20.9%）；RQ-2 建议「新派发卡收紧到 T1、历史卡宽口径/记录卡另门」（详见 §9）。本 RQ 的落层结论不受该数值影响，但**误拒控制必须消费它**。
3. **服务层端到端未实测**：本 worker 的写入面禁止改 `_workers.parallel` / 其他 key，因此我只能引用 `_validate_task_path` 的既有同形测试（5 passed）来推演「卡缺失 ⇒ failed」。真实的「卡缺失行」行为未在本会话跑过。
4. **既有 TS 测试大面积变红的判断是推演**，非实测：我没有实际在 fixture 无卡的情况下跑 `dispatch_worker`（那需要改测试文件，越界）。上界依据是 8 文件 / 55 处引用的静态计数。
5. **cutover 的 dirty 守卫未实测**：`mw build --install` 在 `packages/coding-agent/src` 有未提交改动时会**拒绝**构建（`mw.py:_refuse_dirty_build`，`_BUILD_DIRTY_PATHS = ["packages/coding-agent/src"]`）。多会话共享 cwd 时这是实际阻塞点；需要先提交或 `--allow-dirty`。我没有跑过该命令。
6. **写面守卫的反斜杠路径误拒**（§4.1）我只观测到 1 例；是否还有其它路径形态（UNC、盘符相对、`..`）会误拒未系统测。若卡门禁也要做路径包含判定（服务层必然要做 `task_path` ↔ `card_path` 同 key 校验），这是要提前验证的坑。
7. **`/worker` 的 `manual-*` 是否应被覆盖**属 DESIGN 决策（spec D-001 说「所有类型」，但 QC/描述式派发的历史惯例是无卡）。本 RQ 只给代价，不给结论。

---

## 8. 附：原始输出

### 8.1 运行中的驻留服务 + bundle 陈旧自检（证明 cutover 基线）

```powershell
> python -X utf8 mw.py doctor --project=H:\git\Multi-Workers --json
{
 "service": {"running": true, "pid": 79536, "pid_file": "H:\\git\\Multi-Workers\\.mw\\mw.pid"},
 "bundle": {
  "available": true,
  "global_bundle_mtime": "2026-10-12T15:13:37.815351",
  "source_newest_mtime": "2026-10-12T15:05:44.321231",
  "source_available": true,
  "stale": false
 },
 "queue": {"non_terminal_count": 4, "rows_total": 333, "stale_count": 0,
           "archived_total": 1, "unparsable": [], "unparsable_count": 0,
           "version": 1, "alarm_delta": 50, "run_ledger_conflict": []}
}
```

- `mw serve` PID 79536 在跑（`.mw/serve.meta`：`{"pid": 79536, "started_at_ms": 1791789581837, "code_dir": "H:\\git\\Multi-Workers\\packages\\multi-workers"}`）；launcher 是其子进程（`mw.py:321`）。
- 全局 bundle 与仓库 bundle **字节相同**（SHA256 `0FE644319ACB25F5B16F1CD29FF2559281C78A71518B27A99E3435DDC4E026E9`，`equal=True`）⇒ 改 TS 源码**不会**自动生效，必须 rebuild+install+重启。

### 8.2 工具层守卫的实测（跨 key）

```powershell
> cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-crosskey-readonly.test.ts
 Test Files  1 passed (1)
      Tests  15 passed (15)
   Duration  1.09s
```

证明跨 key 拒绝是**返回值文本**（`expect(text).toContain("[cross-key-read-only]")`），不是异常/退出码。

### 8.3 跨语言判据 parity 的实测（既有范式）

```powershell
> cd packages/multi-workers; python -X utf8 -m pytest -q test_update_index_key_refusal.py
.......................                                                  [100%]
23 passed in 0.72s
```

### 8.4 服务层拦截范式的实测（同形于卡门禁）

```powershell
> cd packages/multi-workers; python -X utf8 -m pytest -q test_launcher.py -k TaskLocationContract
.....                                                                    [100%]
5 passed, 95 deselected in 0.10s
```

（断言形态：`_parse_workers_file(queue_file)[0]["status"] == "failed"` + `worker.log` 含 `invalid worker-task location`。）

### 8.5 卡/worker 命名不对应（实测）

```powershell
> Get-ChildItem .agenticdoc/mw-guard-form-hardening/tasks -File | Select-Object -ExpandProperty Name
T-01-form-inventory.md ... T-19-residual-fixes.md          # 无 T-20

> Get-ChildItem .agenticdoc/mw-guard-form-hardening/workers -Directory | Select-Object -ExpandProperty Name
mwgf-rq1-form-inventory ... mwgf-t19-residual-fixes mwgf-t20-final-fixes
```

### 8.6 `dispatch_worker` 在既有测试中的引用面（方案 A 的影响面）

```powershell
> Get-ChildItem packages/coding-agent/test -Recurse -Filter *.ts | ForEach-Object { ... count 'dispatch_worker' ... }
16  test/suite/worker-crosskey-readonly.test.ts
16  test/extensions/agent-team-loop.test.ts
6   test/suite/mwds-t01-worker-guard.test.ts
5   test/extensions/agent-team-loop-pm-state-sync.test.ts
3   test/suite/rag-tools.test.ts
3   test/suite/mwds-t02-write-intent.test.ts
3   test/extensions/agent-team-loop-vision-gate.test.ts
3   test/extensions/agent-team-loop-vision-autoroute.test.ts
```

### 8.7 写面守卫原始输出

见 §4.1（含零副作用 block 文本、trace 审计行、反斜杠路径误拒）。

---

## 9. 与 RQ-1 / RQ-2 的交叉引用（并行 SPEC 产物，独立取证）

本 RQ 与另两份 SPEC 证据在收尾时并行落盘，结论互证如下（仅引用其坐标与数字，未复算其原始输出）：

| 交叉点 | 本 RQ | RQ-1（`spec-dispatch-path-20261012.md`） | RQ-2（`spec-card-format-corpus-20261012.md`） |
|---|---|---|---|
| 入口数量 | §0.1 实测 4 个生产者（A `dispatch_worker` / B `/worker` / C conductor `dispatch.py` / D 手写行） | §1 同列 3 条路径（1(a) 工具 / 1(b) 队列消费 / 1(c) conductor 直写），并给出路径代码坐标 | — |
| 「两种入口不同一判据」 | §3.1 两 TS 入口是复制粘贴 | §3 实测：`type:`/角色/白名单共用，**卡片一致性两侧都没有**；结论「门禁必须同时挂工具层写入前 + 服务层 spawn 前」与本 RQ §5 方案 C 一致 | — |
| 卡↔task_key 映射 | §3.4 / §7.1（4 种命名） | §6.2：19 卡 / 36 行，18 行可机械匹配，18 行按设计无卡 | §3.1 C1–C4 给出机器判定契约（H1 + 三 H2 + 非空门槛 800B/15 行） |
| 误拒规模 | §7.2（本 RQ 未复算） | §5.2 / §6 定性 | §3.2 实测：T1fail=301/345（87.2%）、T1efail=237（68.7%）、T2fail=72（20.9%）；建议新派发卡收紧 T1、历史/记录卡走宽门 |
| 服务层归档通道可观测性 | §4 表（原按「移入 stale」表述）+ §1.5 | §5.2：`_workers.stale.parallel` **无消费方** ⇒ 对 PM 是「静默消失」 | — |
| 失败形态 | §4 表 / §4.2（工具层 = 稳定码 + 文本；服务层 = status + worker.log 原因行） | §5.1/§5.2 逐通道实测（含 `[worker-write-surface]` 原文与零侧效应断言 `store.readAll() == []`） | §3.3 记录卡体裁（键值 bullet 三键）需另门 |

**由交叉引用产生的两条 DESIGN 提示（本 RQ 不裁决）**：

1. RQ-2 的 T1/T1e/T2 三档差异把「误拒 = 0」变成**门槛选择问题**而非实现问题：AC-005 若要求对既有语料零误拒，则只能取 T2 宽口径（20.9% 仍不合规 ⇒ 必须有迁移/豁免）。落层结论不变：误拒控制点必须在**工具层可窄化**（按 type/origin），服务层兜底必须默认放行 `ap-*`/`manual-*` 或读取显式豁免标记。
2. RQ-1 §4 已列出现成可复用机件（`sha256_eol_normalized`、`parseTaskMd`、`phase-docs` 形状、`conductor.py:2433` plan↔tasks 差集）。本 RQ §5 方案 A/C 的判据模块应直接复用这些机件而不是另造（尤其 AC-003② 的卡 sha256 用 `mw_common.sha256_eol_normalized`，避免 CRLF 误报）。