# RQ-2：worker 产物契约实况（`mw-dispatch-settle-gates`，AC-006/AC-007 判据来源）

## 0. 口径与边界

**语料**：`.agenticdoc/mw-gate-verdict-hardening/workers/` 下全部 worker 目录，`ls -d */ | wc -l` = **30**。
覆盖 2026-10-09 ~ 2026-10-10 的真实运行（同 key）。本报告只读观测，未修改仓库任何文件。

**代码锚点基线**：工作树 `HEAD=776b82d7f`（`chore: ignore the local .tmp scratch dir`），`git status --porcelain | wc -l` = **72**（其它 session 的并发改动）。
本报告所有 `文件:行号` 均为**当前工作树**行号（与 spec 里引用的 `pm-orchestrator.ts:487-492` 一致）。注意被引文件本身是 dirty 的：`git diff --stat` 显示 `pm-orchestrator.ts +412`、`ui-bridge.ts +103`、`worker-mode.ts +84`、`output-writer.ts +9`（4 files changed, 585 insertions(+), 23 deletions(-)）。⇒ 行号有漂移风险，实现阶段应重新 grep 锚名而非直接跳行号。

**"合规交付"定义**（本报告统一口径）：
- `report.md` 非空；或
- `output.md` 存在，且（a）不是全占位符块，且（b）至少有一条交付信号：line-start 机器行（`^\[VERIFY\]` / `^VERDICT=` / `^TASKS=`）／文档内任意位置的 `[VERIFY]` token／`output.md` 内引用的 `.md` 交付物路径在磁盘上**存在**／`run.json.artifacts` 含 `output.md` 以外的产物。
  判定实现在临时脚本里（`node` 逐目录扫描 30 个目录的 `output.md`/`report.md`/`run.json`/`progress.md` 与路径存在性）。

**边界/限制**：
- `run.json` 在该语料 **0/30 存在** ⇒ `artifacts` 通道只能用"前向"论证，历史样本无法验证。
- `trace.log` 的 `tool_call` 计数是 `[FLOW] … tool_call <name>` 行数（按 `[START] pid=` 分段），不是框架自己的 `toolCallCount`。
- 只统计本 key；跨 key 的先例未纳入。
- 未读取任何 worker 的模型/凭证信息。

---

## 1. 交付通道实况

### 1.1 命令与实测数字

```bash
cd <key>/workers
ls -d */ | wc -l                                    # 30
ls */report.md | wc -l                              # 24
for d in */; do [ -f "$d/report.md" ] || echo "$d"; done   # 6 个无 report.md
for d in */; do [ -f "$d/report.md" ] && wc -c < "$d/report.md"; done  # 字节数
ls */output.md | wc -l                              # 27
ls */trace.log | wc -l                              # 28
ls */run.json 2>/dev/null | wc -l                   # 0
grep -h '^## TL;DR' */output.md | wc -l             # 47
grep -h '^(worker exited without writing output)$' */output.md | wc -l  # 22 (= 11 个占位块 × 2 行)
grep -h '^## Changed Files' */output.md | wc -l     # 36
grep -h '^(none)$' */output.md | wc -l              # 0
```

| 指标 | 值 |
| --- | --- |
| worker 目录总数 | 30 |
| 有 `report.md` | 24（字节区间 **2517 B … 57337 B**；min=`mgh-rq3-gate-authz`，max=`mwg-qg2a-evidence-chain`） |
| 无 `report.md` | 6 |
| 有 `output.md` | 27（`mwg-t08b-g2-surfaces`、`t-03-event-names`、`t-21-integrity-tests` 无） |
| 有 `trace.log` | 28 |
| 有 `run.json` | **0** |
| `## TL;DR` 总块数 | 47（其中 11 块是崩溃占位符，23%） |
| `## Changed Files` 总段数 | 36，**全部为空 body**（`(none)` 出现 0 次） |

24 个有 `report.md` 的目录：`mgh-drq1-l3-wiring, mgh-drq2-reminder-wiring, mgh-drq3-authz-wiring, mgh-rq3-gate-authz, mgh-rq5-launcher-requeue, mwg-qg2a-evidence-chain, mwg-qg2b-code-adversarial, mwg-t01-l3-aborted, mwg-t02-config-keys, mwg-t04-contract-guard, mwg-t05-ts-mirror, mwg-t06-l3-tests, mwg-t07-gate-reminder, mwg-t08-g2-surfaces, mwg-t09-pm-consumer, mwg-t10-g3-done-guard, mwg-t11-g3-cli-doctor, mwg-t12-g3-writer-g4-rearm, mwg-t13-g4-freshness, mwg-t14-count-locks, mwg-t16-docs-closure, mwg-t23-g3-anchor, t-03-event-names, t-21-integrity-tests`。

6 个无 `report.md` 的目录：`mgh-rq1-l3-abort, mgh-rq2-gate-alert, mgh-rq4-monitor-freeze, mwg-qg-review-20261010, mwg-t03-event-names, mwg-t08b-g2-surfaces`。

### 1.2 逐目录判定表（6 个无 `report.md`）

`run` = `grep -c '^\[START\] pid='`；`END` = `grep -c '^\[END\]'`；`工具行` = `awk` 按 `[START] pid=` 分段统计 `tool_call` 行。

| 目录 | type | output.md B | run/END | 首个 `## TL;DR` | 占位块 / 总块 | line-start 机器行 | 内联 `[VERIFY]` | 引用交付物存在 | 判定 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mgh-rq1-l3-abort` | research | 7604 | 3/3 | `STATUS: DONE — RQ-1 只读调研完成…` | 0/3 | 0 | 4 | **2/2**（`evidence/research/spec-l3-abort-taxonomy-20261009.md`，28803 B 实存） | **合规（reply/output.md + 外部交付物）** |
| `mgh-rq2-gate-alert` | research | 6455 | 4/2 | `(worker exited without writing output)` ⚠ | 1/3 | 0 | 4 | **1/1**（`spec-pending-gate-alert-surfaces-20261009.md`，20475 B 实存） | **合规**（末块 `STATUS: DONE`），但**首块是占位符** |
| `mgh-rq4-monitor-freeze` | research | 7078 | 3/2 | `status: done — the RQ-4 note is written (30,724 B…)` | 0/2 | 0 | 0 | **1/1**（`spec-monitor-freeze-20261009.md`，30884 B 实存） | **合规**（无 `[VERIFY]`，靠交付物路径） |
| `mwg-qg-review-20261010` | review | 1962 | 1/1 | `This is a large review task. Let me organize my work:` ⚠ | 0/1 | 0 | 0 | **0/1**（`evidence/quality-gate-report-review-20261010.md` **不存在**；`ls evidence/` 只有 `-a-`/`-b-` 两个兄弟产物） | **空转未交付（事故实例）** |
| `mwg-t03-event-names` | coding | 1959 | 1/1 | `Status: 完成 — Python 半边落地（EVENT_TYPES 23 → 26…）` | 0/1 | 0 | 1 | **2/2**（`evidence/runs/t-03-event-names-report.md` 9020 B；`workers/t-03-event-names/report.md` 9020 B） | **合规**（report.md 落在兄弟目录 + evidence/runs 副本） |
| `mwg-t08b-g2-surfaces` | coding | **无** | 1/**0** | — | — | — | — | 0/0 | **硬杀中止，零产物**（`worker.log` 只有 `[worker] start …`，无 `[worker] done`；65 行 `tool_call` 后进程消失 ⇒ 连 `process.on("exit")` 兜底都没跑） |

工具行数（证据强度）：rq1 `168/193/44`（3 run 全 `exit=0`）、rq2 `91/40/58/105`（仅 run2/run3 有 `[END]`）、rq4 `174/70/45`（仅前 2 run 有 `[END]`）、qg-review `8`、t03 `33`、t08b `65`。

### 1.3 结论：合规通道比例

- 6 个无 `report.md` 里 **4 个是合规交付**（**4/6 = 67%**），全部走 **reply/`output.md` + 外部交付物**通道；其中 **3/4 完全没有任何 line-start 机器行**，只有内联 `[VERIFY]` 或交付物路径。
- 真正"跑完没产出"的只有 **1 个**：`mwg-qg-review-20261010`（type=review，8 次 read/ls，0 写，TL;DR 是开场白）。另 1 个（`mwg-t08b-g2-surfaces`）是**硬杀**，与交付通道无关。
- 按 AC-006 的适用角色（`research`/`review` 等无 write/edit）过滤：**11 个只读角色目录**（8 research + 3 review），其中无 `report.md` 的 **4 个**：3 个合规（rq1/rq2/rq4，全 research）+ 1 个事故（qg-review，review）。
- ⇒ **AC-006 的谓词必须接受 reply/`output.md` 通道，且必须接受内联 `[VERIFY]` 与"外部交付物路径存在"两种弱信号**；否则会把 3/4（75%）历史合规 run 判成异常（见 §6）。

---

## 2. `hasProductEvidence()` 的双语义

定义在 `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:487-492`：

```ts
function hasProductEvidence(taskDir: string): boolean {
	for (const name of ["output.md", "report.md", "run.json", "trace.log"]) {
		if (fs.existsSync(path.join(taskDir, name))) return true;
	}
	return false;
}
```

唯一调用点：`pm-orchestrator.ts:653`（`if (queueIsEmpty && undispatched.some((t) => hasProductEvidence(path.dirname(t.taskMdPath))))` → `onAlarm({kind:"queue-unreadable"})` 并 `return`，即整轮 scan 拒绝派发）。它是一个**纯 `existsSync`（文件存在即真）**谓词。

### 2.1 字段级写入时机

| 文件 | 谁在什么时候写 | 锚点 |
| --- | --- | --- |
| `trace.log` | **worker 进程自己在 spawn 最开始写**（`[START] pid=`），早于第一次 agent turn | `worker-mode.ts:467-477`（`appendStartPidLine`），调用点 `worker-mode.ts:708`；随后 `appendStart` `worker-mode.ts:806`（`output-writer.ts:122`） |
| `trace.log` | 心跳 `[HEARTBEAT]`（纯代码定时器）、`[TOOL]`/`[TOOL_ERR]`/`[CHECKPOINT]`/`[PHASE]`/`[TIMEOUT]`/`[END]` | 心跳 `worker-mode.ts:1322-1334`；`[END]` = `recordEnd` `worker-mode.ts:1075-1085` → `output-writer.ts:264` |
| `run.json` | **worker 进程自己在 spawn 最开始写** `status:"running"`，早于第一次 agent turn | 记录构造 `worker-mode.ts:719-733`，`writeRunState` `worker-mode.ts:734`（`run-store.ts:153`） |
| `run.json` | 心跳刷新 `last_heartbeat_at` | `worker-mode.ts:1333-1334` |
| `run.json` | 每个终态路径写终态 + 重收 `artifacts` | `finishRun` `worker-mode.ts:796-802`；调用者 `recordEnd:1075`（成功 1375 / 超时 1151 / 异常 1436）、启动拒绝 752、`exit` 兜底 887 |
| `run.json` | Python launcher **唯一**允许追加 `status:"lost"` | `mw_common.py:1768-1801`（`mark_run_lost`，保留 `run_id/artifacts/supersedes/pid` 原文） |
| `output.md` | 每条**退出路径**的 harness 写入 | 启动拒绝 `worker-mode.ts:743`、image-cap 拒绝 `:824`、`exit` 兜底（占位符）`:872`、超时 `:1144`、成功 settle `:1354`、`agent_settled` 异常 `:1429`；实现 `output-writer.ts:52-96` |
| `output.md` | 追加 `## Read Scope Rejections`（仅有拦截时） | `worker-mode.ts:527-546` |
| `output.md` | 追加 `## RAG` 标记（仅 required-but-unused） | `worker-mode.ts:626-651` |
| `report.md` | **只有 worker 自己写**，且仅限无 `write` 工具的角色（工具注册 `worker_file`） | `worker-mode.ts:910-913`（`const hasWriteTools = toolsForType(meta.type).includes("write")`）；工具实现 `worker-file-tool.ts:82-108`；basename 白名单 `worker-file-tool.ts:30-42`（`progress.md` / `report.md` / `report-<slug>.md`） |
| `progress.md` | 仅当越过收敛检查点（`min(30m, budget/2)`）由代码写 `[machine]` 行；或 worker 自报 | `worker-mode.ts:1185-1201` → `output-writer.ts:190-215` |

⇒ **`trace.log`、`run.json` 是"spawn 即存在"的文件**，与"是否产出"无关；`output.md` 在**任何**受控退出路径（含硬崩溃兜底）都会被创建；只有 `report.md` 是真正的产物信号。

### 2.2 判定：该谓词**不能**区分"跑过"与"产出了东西"

- `hasProductEvidence()` 在历史语料上与"该目录曾经 spawn 过 worker"**几乎等价**：28/30 目录有 `trace.log`（仅在 spawn 中途被硬杀时也可能有），另 2 个（`t-03`/`t-21`）有 `report.md`。30/30 全为 `true`。**唯一为 `false` 的形态是"只有 `task.md` 的从未跑过的目录"**（`pm-orchestrator.ts:485-486` 注释自述的目标恰恰就是这个）。
- **反例（近确定性论证）**：任何一个 worker 只要启动，`appendStartPidLine`（`worker-mode.ts:708`）就先写 `trace.log`、`writeRunState`（`:734`）就写 `run.json`，两者都在第一 turn 之前、在任何产物之前。
- **本次事故实例即反例**：`mwg-qg-review-20261010` 有 `trace.log`（1532 B）、有 `output.md`（1962 B）⇒ `hasProductEvidence` = `true`；但它的交付物 `evidence/quality-gate-report-review-20261010.md` 不存在、`output.md` 里 0 条机器行、TL;DR 是"Let me organize my work:" ⇒ **零产物**。
- 而且 `output.md` 的证据性被**占位符**进一步削弱：崩溃兜底（`worker-mode.ts:872-878`）写的 `output.md` 与"成功交付"的 `output.md` 在 `existsSync` 视角完全等价。语料里 **11/47** 个 `## TL;DR` 块正是这个占位符（3 个目录首块即占位符，其中 `mwg-t11-g3-cli-doctor` 9 个块里 8 个是占位符、第 9 块才是 `PASS`）。

⇒ **AC-006 若复用 `hasProductEvidence` 会全程误判**（该 key 内 30/30 为真）；结算期必须另立"内容级"判据（§6）。

---

## 3. `run.json` 能承载什么产物事实

Schema：`shared/run-store.ts:36-53`（`RunState`），`RUN_SCHEMA=1`（`:26`），`RUN_FILE_NAME="run.json"`（`:25`）。

| 字段 | 写入者 | 行号 | 可否用于产物判据 |
| --- | --- | --- | --- |
| `schema` | worker（spawn） | `run-store.ts:37` / 写 `worker-mode.ts:719` | 版本门，否 |
| `task_key` | worker（spawn） | `:39` / `:720` | 身份，否 |
| `run_id` = `<task_key>@<iso>` | worker（spawn） | `:41` / `:721`（`newRunId` `:107`） | 身份/去重，否 |
| `owner_key` | worker（spawn） | `:42` / `:723` | 归属，否 |
| `kind` = task.md `type:` | worker（spawn） | `:44` / `:724` | **是**：AC-006 的"只读角色"筛选可用（历史语料无 `run.json`，需回退 `task.md` 的 `type:`） |
| `status` | worker（spawn=`running`，终态）+ launcher（仅 `lost`） | `:46` / `:726`、`finishRun:797`、`mw_common.py:1786` | **是**：终态集合 `RUN_TERMINAL_STATUSES` `:31` |
| `started_at` / `ended_at` / `exit` | worker | `:47-51` / `:727`、`finishRun:798-799` | 是（时长/退出码），非产物 |
| `supersedes` | worker（task.md header） | `:50` / `:729`（`parseSupersedes` `:170`） | 否 |
| **`artifacts`** | worker，`collectArtifacts(taskDir)` | 声明 `:52`；收集器 `:119-138`；初值 `worker-mode.ts:730 = []`；**唯一非空赋值 `worker-mode.ts:800`**（`finishRun` 内） | **是（forward）** |
| `pid` / `last_heartbeat_at` | worker | `:53-54` / `:731-733`、`:1333` | 活性，非产物 |

### 3.1 `artifacts` 的赋值点（全仓 grep 证据）

```bash
grep -rn "artifacts" packages/coding-agent/src/extensions/agent-team-loop/
# run-store.ts:52  声明 artifacts: string[]
# run-store.ts:119 export function collectArtifacts(taskDir)
# worker-mode.ts:730  artifacts: []
# worker-mode.ts:800  runState.artifacts = collectArtifacts(taskDir)   ← 唯一赋值
```

`collectArtifacts`（`run-store.ts:119-138`）收集的是**任务目录内**的文件：固定名 `output.md` / `report.md` / `progress.md`（`:121`），加上 `phase-*.md` / `stage-N*.md`（`:130-133`），排序返回。**不含任何仓库源码路径**。Python 侧只读/保留（`mw_common.py:1788` "Everything else … preserved verbatim"），不重算。

### 3.2 worker 能否自报改动文件？——**不能**

- `TOOL_ALLOWLISTS`（`worker-mode.ts:57-99`）里 `coding`/`research`/`repair`/`phase-writer`/`vision`/`fallback` 有 `bash`，`review`/`reviewer`/`verifier` **没有** `bash`；**没有任何角色有 `diff`/`git` 专用工具**。
- `grep -rn "registerTool(" src/extensions/agent-team-loop/worker/` 只有 `worker-file-tool.ts:83`；RAG 工具在 `rag/tools.ts`；PM 工具在 `ui-bridge.ts`。⇒ 无 diff 能力。
- 框架侧从未解析过改动：`grep -rn "changedFiles" src/` 只有 3 处 —— `output-writer.ts:9`（类型）、`output-writer.ts:65`（拼接）、`worker-mode.ts:1359`（**硬编码 `[]`**）。全仓也没有 `git diff --name-only` 的调用。
- ⇒ `## Changed Files` **在当前实现下永远是空**（见 §4.2）。

---

## 4. `output.md` 写入形态与占位符

### 4.1 append 还是 overwrite：**混合（空则覆写，非空则追加）**

`output-writer.ts:95`：

```ts
fs.writeFileSync(outputPath, existing.trim() === "" ? body : `${existing.trimEnd()}\n\n---\n\n${body}`, "utf8");
```

- 现有内容为空/仅空白 ⇒ 覆写为 harness-only body；
- 现有内容非空 ⇒ **原文逐字保留 + `\n\n---\n\n` 分隔 + 追加新 harness 块**（D-117 防 clobber 合并）。
- 注释依据：`output-writer.ts:77-88`（"When the file already carries agent content, preserve it verbatim — its first line keeps the machine-readable contract — and append the harness sections below a separator"）。
- 注释里 "worker-mode guarantees one writeOutput call per process (outputWritten guard)" **只对 `process.on("exit")` 兜底成立**（守卫 `worker-mode.ts:856` / `:870`），对 settle 路径不成立（见 §4.3b）。

### 4.2 占位符常量与分支

| 常量原文 | 分支 | 行号 |
| --- | --- | --- |
| `(no conclusion)` | `headline()` 空输入 | `output-writer.ts:49` |
| `(no summary)` | `## Summary` body 空 | `output-writer.ts:62` |
| `(none)` | `## Changed Files` 的 `?? "(none)"` | `output-writer.ts:65`（**实测不可达**，见下） |
| `(none)` | `## Verification Steps` body 空 | `output-writer.ts:67` |
| `Task completed successfully.` | exit 0 `## Exit Reason` 缺省 | `output-writer.ts:68` |
| `Task failed.` | exit 1 `## Exit Reason` 缺省 | `output-writer.ts:70` |
| `(no questions provided)` | exit 2 `## Questions` | `output-writer.ts:72` |
| `Task was cancelled (exit 130).` | exit 130 `## Exit Reason` | `output-writer.ts:74` |
| `(worker exited without writing output)` + `Process exited before output.md was written (crash or unexpected exit).` | `process.on("exit")` 硬崩溃兜底 | `worker-mode.ts:876-877` |
| `Task refused at startup (fail-closed).` | 启动 fail-closed 拒绝 | `worker-mode.ts:747` |
| `Task refused (image capability).` | image-cap 拒绝 | `worker-mode.ts:828` |
| `Worker timed out (idle\|wall).` | 看门狗 | `worker-mode.ts:1134-1152`（`timeoutExit`） |
| `Task failed during output writing.` | `agent_settled` 异常分支 | `worker-mode.ts:1433` |

**`## Changed Files` 实测永远是空 body**：`worker-mode.ts:1359` 传 `changedFiles: []`，而 `output-writer.ts:65` 用 `opts.changedFiles?.join("\n") ?? "(none)"` —— `[]` 不是 nullish，`[].join("\n") === ""`，`??` 不触发 ⇒ body = `""`。实测：36 个 `## Changed Files` 段 **36/36 body 为空**，全仓 `^(none)$` 命中 **0**。占位符分布实测：`(worker exited without writing output)` 22 行 = 11 块（3 个目录）；`See task output for details.` 36/36（每个 exit-0 块都写）。

### 4.3 同一 worker 目录出现多段 `## TL;DR` 的成因

唯一写 `## TL;DR` 的代码是 `output-writer.ts:61`。三类路径：

- **(a) 跨 run 追加（主因）**：`output-writer.ts:95` 的 D-117 合并。每次对同一 task_key 重新派发（重跑 / launcher requeue / orphan reconcile 后重派）都新起一个进程、再 `writeOutput` 一次，旧块从不清理。实测 **10/27** 个目录多块（`mgh-drq1(2), mgh-drq2(2), mgh-drq3(2), mgh-rq1(3), mgh-rq2(3), mgh-rq3(2), mgh-rq4(2), mgh-rq5(2), mwg-t11(9), mwg-t16(3)`），对应 `[START] pid=` 次数 2~9。
- **(b) 同一进程内多次 settle**：`pi.on("agent_settled")` 的无 phase / phase 走完分支直接 `finishSuccess()`（`worker-mode.ts:1392`、`:1423`）；`finishSuccess`（`:1350-1378`）**无幂等守卫**（`taskDone` 只赋值不检查；`outputWritten` 只在 `process.on("exit")` 里被读，`worker-mode.ts:856`/`:870`）。第二次 settle ⇒ `existing` 非空 ⇒ 再追加一块。测试 `suite/rag-required.test.ts:323` 正是 `emit("agent_settled")` 两次（该测试只断言 `## RAG`/marker 恰好一次，未断言块数）。
- **(c) agent 自己写**：任务模板要求 worker 把机器行/小节写进 `output.md`（`output-writer.ts:78-80` 注释），harness 块随后追加。语料里 `mwg-t16-docs-closure` 有 line-start `[VERIFY]`（`grep -c '^\[VERIFY\]'` = 1）即属此类。

**对读侧语义的实测影响（AC-007 关键）**：`readOutputSection`（`ui-bridge.ts:339-353`）取**第一个**匹配，`readTerminalDetail(done)` = 首个 `## TL;DR`（`ui-bridge.ts:470-480`）。`node` 复算首匹配结果：
- `mgh-rq2-gate-alert` → `"(worker exited without writing output)"`（末块 `STATUS: DONE`、交付物 20475 B 实存）；
- `mwg-t11-g3-cli-doctor` → 同占位符（第 9 块才是 `PASS — T-11 done…`）；
- `mwg-t16-docs-closure` → 同占位符。
⇒ 首块占位符在 27 个有 `output.md` 的目录里占 **3 个（11%）**，且这 3 个目录都**实际交付了**。任何"读首块"的谓词/展示会把它们判成异常；AC-006/AC-007 必须**扫描全部块**（且以"存在任一非占位块"为准，而非"全部非占位"——`mwg-t11` 8/9 块是占位符）。

---

## 5. 回归面清单（AC-006/AC-007 的测试影响面）

计数口径：`packages/coding-agent/test/**` 中断言 `exitReason` / `changedFiles` / `## Changed Files` / `## TL;DR` / `output.md` 形态 / `readOutputSection` / `readTerminalDetail` / `run.json.artifacts` / `hasProductEvidence`（queue-unreadable 守卫）的**测试用例**，共 **28** 个，分布在 10 个文件。

| # | 测试 文件:行号 | 断言摘要 | 改判据是否红 |
| --- | --- | --- | --- |
| 1 | `extensions/agent-team-loop-output.test.ts:75` | `## TL;DR` 必须是 exit 0/1/2 的**第一段**，`## Summary` 逐字保留（`:93` `out.startsWith("## TL;DR\n\n…\n\n## Summary")`） | 红：若改首段顺序/格式 |
| 2 | `extensions/agent-team-loop-output.test.ts:102` | TL;DR ≤100 字符、无 markdown 前缀 | 红：若动 `headline()` |
| 3 | `extensions/agent-team-loop-output.test.ts:121` | 空 summary ⇒ `(no conclusion)`；`:127` `readOutputSummary` = `(no summary)` | 红：若改占位符常量 |
| 4 | `extensions/agent-team-loop.test.ts:389` | exit 0 写四段，含 `## Changed Files`（`:398` 传 `changedFiles:["x.ts"]`，`:403` 断言段名存在） | **红**：AC-007"无 artifacts 则整段省略"会直接打掉此断言 |
| 5 | `extensions/agent-team-loop.test.ts:410` | exit 1 写 `## Exit Reason` 自定义文本 | 红：若改 exitReason 装配 |
| 6 | `extensions/agent-team-loop.test.ts:419` | exit 2 写 `## Questions` | 红：若改占位符 |
| 7 | `extensions/agent-team-loop.test.ts:428` | exit 130 仍写文件 | 红：若新谓词对 exit 130 fail-closed |
| 8 | `extensions/agent-team-loop.test.ts:437` | D-117 合并：agent body 在 `---` 之上、harness 在下方（`:457` 断言 `\n---\n\n## TL;DR`） | 红：若改成覆写或单块格式 |
| 9 | `extensions/agent-team-loop.test.ts:465` | 空白-only 文件 ⇒ harness-only，**不含** `---\n\n## TL;DR` | 红：若改"占位符-only"判定 |
| 10 | `extensions/agent-team-loop.test.ts:2621` | `readOutputSection` **首匹配**语义 + 缺文件返回 undefined | 红：若改为"末块/多块"读取（AC-006/007 的可能配套改动） |
| 11 | `extensions/agent-team-loop.test.ts:2694` | done 详情 = 首个 `## TL;DR` ?? Summary 首行 | 红：若改展示源 |
| 12 | `extensions/agent-team-loop.test.ts:2713` | `renderWatchLines` 接 `readTerminalDetail` | 红：若详情形态变 |
| 13 | `extensions/agent-team-loop-image-cap.test.ts:118` | 拒绝输出的 `output.md` **不得**含崩溃占位符（`:149`） | 红：若结算谓词把 `(worker exited without writing output)` 写到拒绝路径上 |
| 14 | `extensions/agent-team-loop-worker-tree-kill.test.ts:205` | `exit` 兜底**必须**写占位符（`:224`） | 红：若 AC-006 抑制该占位写入 |
| 15 | `suite/worker-run-identity.test.ts:77` | spawn 起手即写 `run.json status=running` + pid/heartbeat | 红：若 run.json 写入挪到某个门之后 |
| 16 | `suite/worker-run-identity.test.ts:98` | 干净 settle ⇒ `status=done`、`exit=0`、**`artifacts` 含 `output.md`**、marker 为文件首行（`:110-113`） | 红：若改 `finishRun`/`collectArtifacts`/终态映射 |
| 17 | `suite/worker-run-identity.test.ts:116` | D-117：agent 机器行仍是首行，marker 在 `---` 之后（`:130-134`） | 红：若改合并格式 |
| 18 | `suite/run-store.test.ts:143` | `collectArtifacts` 排序等值 `["output.md","phase-1-impl.md","progress.md"]`（`:149`） | 红：若 AC-007 扩 `collectArtifacts`（例如纳入源码文件） |
| 19 | `suite/rag-required.test.ts:323` | 二次 settle 后 `RAG 未生效` 恰好 1 次、`## RAG` 存在（`:334-343`） | 红：若第二次 settle 不再追加块（幂等化）或改 marker 去重 |
| 20 | `suite/autopilot-protocol.test.ts:272` | 未注册 conductor type：exit 1 + 理由落 `output.md`（`:279`） | 红：若结算谓词覆盖/拒绝该输出 |
| 21 | `suite/autopilot-protocol.test.ts:294` | `type: fallback` 同样 fail-closed，理由落 `output.md`（`:300`） | 同上 |
| 22 | `suite/autopilot-protocol.test.ts:310` | 无 `read_scope` 的 verifier fail-closed，理由落 `output.md`（`:318`/`:332`） | 同上 |
| 23 | `suite/worker-dispatch-guard.test.ts:240` | **唯一** `hasProductEvidence` 行为测试：空队列 + 任务目录里有 `output.md`（内容 `"already ran\n"`，`writeTask` helper `:57-64`）⇒ `queue-unreadable` 告警 + 零队列行；反例（只有 `task.md`）⇒ 正常派发 | 红：若把 `hasProductEvidence` 收窄成"要求机器行"（fixture 无机器行）；若只加"非占位符"则仍绿 |
| 24 | `suite/worker-dispatch-guard.test.ts:297` | 自身 run 已终态 ⇒ 拒绝派发（AC-022） | 红：若改 run.json 终态语义 |
| 25 | `suite/worker-dispatch-guard.test.ts:319` | 活 run ⇒ 拒绝（不产生第二写者） | 同上 |
| 26 | `suite/worker-dispatch-guard.test.ts:449` | 终态 run 不再入队且给理由（队列行保留） | 同上 |
| 27 | `suite/worker-dispatch-guard.test.ts:496` | `supersedes` 替换 run 放行、旧目录不动 | 同上 |
| 28 | `suite/dual-root-worker.test.ts:115`（+ `suite/cross-drive-worker.test.ts:210`） | settle 后 `output.md` 必须存在，且只落在 control root | 红：若结算谓词在崩坏/拒绝路径上不再写 `output.md` |

**必须红的（若按 AC-006/AC-007 字面实现）**：**4**（省略 `## Changed Files`）、**10/11**（改读块语义）、**13/14**（占位符语义反转）、**23**（收窄 `hasProductEvidence`）。其余 24 个是"不该被误伤"的护栏（尤其 20-22 的拒绝路径、19 的二次 settle、16/18 的 `artifacts`）。

Python 侧（Q5 未要求，仅提示）：`packages/multi-workers/test_launcher.py:1265-1390`（run.json reconcile 阶梯）、`test_run_identity.py`（`mark_run_lost`）。结算落 `done` 的既有实现是 `launcher.py:367-374`（`_exit_to_status`，注释自称 "AC-006"）+ reap `launcher.py:842-844`，**只看退出码、不看产物** —— 这是事故"仍记成 done"的直接成因。

---

## 6. 推荐谓词与填充来源

### 6.1 AC-006 推荐机器谓词（含与 spec 字面版的实测对照）

**spec 字面谓词的实测后果（先看这个）**：spec 的判据是"`report.md` 非空 **或** `output.md` 含 `^\[VERIFY\]` / `^VERDICT=` / `^TASKS=`"。在 4 个 AC-006 适用角色（`research`/`review`）且无 `report.md` 的目录上：

```bash
grep -c '^\[VERIFY\]'  workers/<d>/output.md   # rq1=0 rq2=0 rq4=0 qg-review=0
grep -c '^VERDICT='    workers/<d>/output.md   # 全 30 个目录 = 0
grep -c '^TASKS='      workers/<d>/output.md   # 全 30 个目录 = 0
grep -c '^<!-- mw-run:' workers/<d>/output.md  # 全 30 个目录 = 0
```

| 目录 | spec 字面谓词 | 事实 | 结果 |
| --- | --- | --- | --- |
| `mgh-rq1-l3-abort` (research) | `needs-clarification` | 交付 28803 B 笔记、4 处内联 `[VERIFY]`、3/3 run `exit=0` | **假阳性** |
| `mgh-rq2-gate-alert` (research) | `needs-clarification` | 交付 20475 B 笔记、末 run `STATUS: DONE` | **假阳性** |
| `mgh-rq4-monitor-freeze` (research) | `needs-clarification` | 交付 30884 B 笔记（无 `[VERIFY]`） | **假阳性** |
| `mwg-qg-review-20261010` (review) | `needs-clarification` | 交付物不存在，0 机器行 | 正确 |

⇒ **假阳性率 3/4 = 75%；在"历史合规 run"上 **3/3 = 100%**。**全语料只有 1/30 目录存在 line-start `[VERIFY]`（`mwg-t16-docs-closure`，且它本来就有 `report.md`）；`^VERDICT=`/`^TASKS=` 全语料 0/30。** 根因：只读角色的 `[VERIFY]` 习惯写在 `## Summary` 散文句子里或 fenced code block 里，不在行首；`VERDICT=`/`TASKS=` 是**派发任务书要求**写的，而本 key 的 read-only 调研任务书没有这条要求。

**推荐谓词**（分层，fail-closed 方向正确；`isReadOnly(type)` 复用 `activeToolsForType` / `TOOL_ALLOWLISTS`（`worker-mode.ts:57-99,110-118`）单一真相源）：

```
delivered(dir, type):
  if !isReadOnly(type): return true                          # AC-006 只约束无 write/edit 角色
  if reportFileNonEmpty(dir): return true                    # report.md | report-<slug>.md, size > 0
  out = read(dir/output.md); if out == "" : return false
  blocks = allBlocks(out,"TL;DR") ++ allBlocks(out,"Summary")# 必须扫全部块（§4.3 首块占位符陷阱）
  if blocks != [] && allPlaceholder(blocks): return false     # 占位符-only 非产物
  if not blocks: return false                                # 无任何 TL;DR/Summary 的 output.md 不算
  if runJson(dir).artifacts.any(n => n != "output.md"): return true      # 强通道（run.json）
  if /^(?:\[VERIFY\]|VERDICT=|TASKS=)/m.test(out): return true           # spec 原定机器行
  if /\[VERIFY\]/.test(out): return true                                 # 内联 token（实测必需）
  if referencedDeliverableExists(dir, out): return true                   # 引用的 .md 实存（实测必需）
  return false
```

**在语料上的实测评估**（临时 `node` 脚本，对 30 个目录判定）：

| 谓词 | 合规 3 run 判成 delivered | 事故 run 判成 delivered | 30 目录总判定 |
| --- | --- | --- | --- |
| spec 字面版 | 0/3 | 0/1（正确） | 27 delivered / 3 → NC（含 3 假阳性） |
| 推荐版 | **3/3** | **0/1（正确）** | **28 delivered / 2 → NC**（`mwg-qg-review-20261010` + `mwg-t08b-g2-surfaces` 硬杀） |

推荐版里各通道的**必要性实测**：`[VERIFY]` 内联覆盖 rq1/rq2（rq4 = 0 个 `[VERIFY]`）；`referencedDeliverableExists` 覆盖 rq1（2/2）、rq2（1/1）、rq4（1/1）；`run.json.artifacts` 覆盖 **0/3**（历史语料无 `run.json`，纯前向通道）。**任一通道单独使用都不够**：只留 `[VERIFY]` ⇒ rq4 假阳性；只留 artifacts ⇒ 3/3 假阳性。

**风险与缓解**：
1. `referencedDeliverableExists` 是启发式：worker 可以把一个它**只读过**的既有路径写进 `output.md` 从而"假过"。缓解：只认 **key 根下 `evidence/**` 且不在本 worker 目录内** 的 `.md`，并加 `mtime >= run.json.started_at`（无 run.json 时退化为只看存在性 + 路径前缀）。实测三个合规例子的引用都在 `evidence/research/`；事故例引用 `evidence/quality-gate-report-review-20261010.md` 不存在 ⇒ 仍判 NC。
2. 内联 `[VERIFY]` 可能只是引用任务书模板措辞。缓解：放在 `referencedDeliverableExists`/`artifacts` 之后作二级通道，且必须与"非占位符 TL;DR/Summary"同时成立（上方已保证）。
3. `reportFileNonEmpty` 必须同时接受 `report-<slug>.md`：白名单 `worker-file-tool.ts:30-42` 允许，但 `collectArtifacts`（`run-store.ts:121`）只认 `report.md` ⇒ 只写 `report-foo.md` 的 worker 对**谓词与 artifacts 都不可见**。本 key 实测 `find . -name "report-*.md"` = 0，属前向风险。
4. 必须**扫全部块**：`readOutputSection`（`ui-bridge.ts:339-353`）是首匹配，直接复用会把 `mgh-rq2-gate-alert`/`mwg-t11-g3-cli-doctor`/`mwg-t16-docs-closure` 判成异常（3/27 = 11%）。
5. `needs-clarification` 降级**不得**动摇既有输出契约：不得抑制 `exit` 兜底占位符（测试 14）、不得覆盖拒绝路径的 `output.md`（测试 13、20-22）、不得改 `finishRun`/`artifacts` 口径（测试 16、18）、不得让二次 settle 变成不追加（测试 19）。
6. 零回填：历史目录没有 `run.json`，谓词必须在缺 `run.json` 时按上面顺序降级，绝不因缺文件而 fail-closed 到 NC。

### 6.2 AC-007 的 `changedFiles` 填充来源

| 方案 | 理由 | 风险 |
| --- | --- | --- |
| **(a) `run.json.artifacts`** | 现成机器数据，终态时已收集（`worker-mode.ts:800` → `run-store.ts:119-138`），Python 保留原文（`mw_common.py:1788`），不依赖 LLM | ① **语义错**：`collectArtifacts` 只列任务目录产物（`output.md`/`report.md`/`progress.md`/`phase-*.md`/`stage-N*.md`），**从不含源码改动** —— 编码角色改了 `packages/**/src`，这里一个都不会出现；② 历史 0/30 目录有 `run.json` ⇒ 全历史只剩"省略"分支；③ 需过滤掉 `output.md`/`progress.md` 自身，否则又是"自指产物列表"；④ 测试 18（`run-store.test.ts:143`）钉死收集器的确切输出 |
| **(b) worker 自报** | 只有 worker 知道自己改了哪些文件；语义最准 | ① **能力缺失**：无任何角色有 diff/git 工具（`worker/` 下唯一 `registerTool` 是 `worker-file-tool.ts:83`），`review`/`reviewer`/`verifier` 连 `bash` 都没有（`worker-mode.ts:57-99`）；② 需要新机器行 + 解析器 + "不得伪造"反例测试；③ LLM 自报易漂移。成本高、收益中 |
| **(c) 无 artifacts 时整段省略（推荐）** | 无消费者：`grep -rn "Changed Files" src/ packages/multi-workers` **只有写者** `output-writer.ts:66`；现状本来就是空 body 36/36（§4.2），省略是"把空段变没"，信息量不降反升；诚实信号交给 `## Exit Reason` | 只有测试 4（`agent-team-loop.test.ts:389-407`，硬断言 `## Changed Files` 段名存在且 `changedFiles:["x.ts"]` 可注入）会红，必须同步改；任何仓外的脚本抓这个段名会失去锚（仓内实测无读者） |

**推荐组合**：
1. 有 `run.json` 且过滤后 `artifacts` 非空 ⇒ 写 `## Deliverables`（段名换成语义诚实的名字；若要保留 `## Changed Files` 段名，则只列排除 `output.md`/`progress.md` 后的名字，并接受测试 4 的改写）。
2. 无 `run.json` / artifacts 为空 ⇒ **整段省略**（绝不写空 body，更不写 `(none)`；注意 `output-writer.ts:65` 的 `?? "(none)"` 因 `[]` 非 nullish 而不可达，改判据时顺带清理）。
3. `## Exit Reason` 补足"是否实交付"：成功路径现在是 `Agent settled after ${toolCallCount} tool call(s).`（`worker-mode.ts:1365`，已含 `toolCallCount`），追加 `writes=report.md|progress.md|none`（来源：`collectArtifacts` 结果，或 `progress.md` 的 `CKPT … [machine] … writes=<n>` 行 `formatMachineCheckpoint`（`output-writer.ts:227`）—— 但后者**只在越过 `min(30m, budget/2)` 的长 run 才存在**，实测本语料仅 **2/28** 目录有 `[CHECKPOINT]`，所以只能作辅助而非判据）。

---

[VERIFY] RQ2: worker_dirs=30 with_report=24 without_report=6 compliant_reply_channel=4 regression_tests=28


---

## PM 现场复核（2026-10-10 21:35，`mw-dispatch-settle-gates` PM）

本文件 = worker `mds-rq2-product-contract` 的 `report.md` **逐字收录**（34,459 B / 327 行），正文未改写。
PM 独立复现的实测数字（脚本 `.tmp/t24-rq2-verify.py`，语料 = `mw-gate-verdict-hardening/workers/`）：

| 指标 | worker 报 | PM 实测 | 结论 |
|---|---|---|---|
| worker 目录总数 | 30 | **30** | ✓ |
| 有 `report.md` | 24 | **24**（另 6 个无） | ✓ |
| 无 `report.md` 中合规走 reply/`output.md` | 4/6 | **4**（`mgh-rq1-l3-abort` 7,604 B 内联 `[VERIFY]`×4、`mgh-rq2-gate-alert` 6,455 B 内联 `[VERIFY]`×4、`mgh-rq4-monitor-freeze` 7,078 B、`mwg-t03-event-names` 1 次机器行） | ✓ |
| 唯一真空转 | `mwg-qg-review-20261010` | `output.md` 1,962 B、行首机器行 0、内联 `[VERIFY]` 0、`trace.log` 1,532 B | ✓ |
| 硬杀 | `mwg-t08b-g2-surfaces` | 无 `output.md`、无 `[END]` | ✓ |
| 行首机器行（`^[VERIFY]`/`^VERDICT=`/`^TASKS=`） | 0/30 量级 | **全语料 1 次**（`mwg-t16-docs-closure`） | ✓ ⇒ spec 初版单通道=空集 |
| `run.json` 语料 | 0/30 | **0/30**（运行身份未上线） | ✓ ⇒ 谓词 ②(b) 只能前瞻 |
| 含占位符的 output.md | 3/27 | **3**（`mwg-t11`、`mwg-t16`、`mgh-rq2`） | ✓ |
| 多段 `## TL;DR` | 10/27 | **10**（最多 9 段 = `mwg-t11`） | ✓ |
| `(none)` 出现次数 | — | **0/30** | ✓ **并更正 PM 自己的说法**（见下） |

### PM 自我更正（写进 spec）

- 我此前（spec 初版 §0/§G-g/AC-007）称「`output.md` 对真实改动也写 `(none)`」。**错**：`changedFiles` 传的是 `[]`（`worker-mode.ts:1359`），`[]?.join("\n") ?? "(none)"`（`output-writer.ts:65-66`）**不会**落到 `??` 分支 ⇒ 段体是**空字符串**，实测 0/30 出现 `(none)`。实质问题（该段无信息量）成立，字面说法已改。

### 锚点确认（PM 看到的行）

| 结论 | 证据 |
|---|---|
| `hasProductEvidence()` 是纯 `existsSync`、语义=「跑过」 | `pm-orchestrator.ts:487-492`（4 个文件名），注释 `:485-486` 自陈，唯一调用 `:653` |
| 结算只看退出码 | `launcher.py:367-373` `_exit_to_status`（0→done、2→needs-clarification、其余→failed）+ `:842-844` reap |
| `output.md` 写形态 | `output-writer.ts:95`（`existing.trim()==="" ? body : existing + "\n---\n" + body`，D-117 有意保留 worker 自写机器行） |
| 读侧首匹配 | `ui-bridge.ts:339`（注释「first match」）+ `:344` `readOutputSection` |
| `artifacts` 唯一赋值 + 收集范围 | `worker-mode.ts:800` `runState.artifacts = collectArtifacts(taskDir)`；`run-store.ts:119-138` 只收任务目录产物、**不含源码改动** |

### PM 采纳

- AC-006 谓词改用 RQ-2 校准版（三级通道，§3.1）；语料回放 **28 delivered / 2 正确 NC / 0 假阳性**（初版 75% 假阳性）。
- AC-007 口径改为「有 artifacts ⇒ 改名 `## Deliverables` 并排除 `output.md`/`progress.md`；无 artifacts ⇒ 整段省略」+ `Exit Reason` 补 `toolCallCount` / `writes=`。
- 新增 **AC-010**（多段 section 遮蔽真报告 + settle 幂等），依据来源见 §3.2。
- 回归面 28 条（10 文件）**照收**，design/execute 阶段按新口径**更新而非放宽**断言。
- 注意：worker 报告的锚点基于 `HEAD=776b82d7f` 的**脏树**（`pm-orchestrator.ts +412`、`worker-mode.ts +84`），跨阶段复用到行号时必须重锚。
