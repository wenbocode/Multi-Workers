# VC-011 真模型端到端冒烟证据（T-5）

- Key: `mw-worker-progress-persist`
- Task: `T-5-BUILD-SMOKE`（`.agenticdoc/mw-worker-progress-persist/tasks/T-5-BUILD-SMOKE.md`）
- 结论: **PASS**（三条断言 a/b/c 全部成立，无降级；run-1 假阴性见 §5）
- 本报告性质: 冒烟（smoke）证据，非正式审查结论；被审文件未被修改
- 证据生成时间: 2026-09-23 16:49–16:52 (+08:00)
- 执行角色: coding worker（`read/write/edit/bash/find/grep/ls`），任务 `mwpp-t5-real-smoke`

---

## 1. 运行环境与命令

### 1.1 临时项目路径（保留在磁盘上，未删除）

```
C:\Users\wenbozhou\AppData\Local\Temp\mwpp-smoke-t5
```

- 通过 run: `<proj>\.agenticdoc\_scratch\workers\mwpp-smoke-review-b\`
- run-1 假阴性: `<proj>\.agenticdoc\_scratch\workers\mwpp-smoke-review\`（同样保留）
- task_key: `mwpp-smoke-review-b`（run-1: `mwpp-smoke-review`）
- agenticdocRoot 解析: `controlRootFromTaskPath()` → owner key `_scratch`，taskKey = 任务目录名（正确落到 `_scratch\workers\<taskKey>\`）

### 1.2 task.md（run-2，命中检查点的那次）

```markdown
type: review
timeout: 1

这是冒烟测试（smoke test），不是正式审查结论；不得修改任何被审文件。

逐个 read 下列 9 个文件，严格串行执行：读完一个文件后，先用三行给出该文件的结论，然后再读下一个文件。不要并行批量读取，不要跳过任何一个：

1. H:/git/Multi-Workers/AGENTS.md
2. H:/git/Multi-Workers/README.md
3. H:/git/Multi-Workers/packages/multi-workers/README.md
4. H:/git/Multi-Workers/packages/coding-agent/README.md
5. H:/git/Multi-Workers/packages/coding-agent/CHANGELOG.md
6. H:/git/Multi-Workers/.agenticdoc/_pitfalls.md
7. H:/git/Multi-Workers/packages/multi-workers/CHANGELOG.md
8. H:/git/Multi-Workers/package.json
9. H:/git/Multi-Workers/packages/multi-workers/providers.json

九个文件读完后，最后给一段简短总结（3 行以内）。
```

### 1.3 完整执行命令（PowerShell）

```powershell
$repo = "H:/git/Multi-Workers"
$tsx  = "$repo/node_modules/tsx/dist/cli.mjs"
$proj = "C:/Users/wenbozhou/AppData/Local/Temp/mwpp-smoke-t5"
$task = "$proj/.agenticdoc/_scratch/workers/mwpp-smoke-review-b/task.md"
Set-Location $proj
$env:PI_WORKER_TASK = $task
$start = Get-Date
Write-Output "START=$($start.ToString('o'))"
node $tsx --tsconfig "$repo/tsconfig.json" "$repo/packages/coding-agent/src/cli.ts" `
  --no-extensions -e "$repo/packages/coding-agent/src/extensions/agent-team-loop/index.ts" `
  --no-skills --provider timi -p "执行你的 worker 任务" *> "$proj/worker.log"
$code = $LASTEXITCODE
$end = Get-Date
Write-Output "exit=$code"
Write-Output "ELAPSED_S=$([math]::Round(($end-$start).TotalSeconds,1))"
Write-Output "END=$($end.ToString('o'))"
```

命令输出（逐字复制，run-2）：

```
START=2026-09-23T16:48:45.9852886+08:00
TASK=C:/Users/wenbozhou/AppData/Local/Temp/mwpp-smoke-t5/.agenticdoc/_scratch/workers/mwpp-smoke-review-b/task.md
exit=0
ELAPSED_S=42.1
END=2026-09-23T16:49:28.0932496+08:00
```

- provider: `timi`（`--provider timi`）
- model（框架记录的解析结果）: `deepseek-v4.1-flash`（trace.log `[MODEL]` 行；来自注入的 `PI_MODEL`）
- 退出码: `exit=0`
- 生效方式: `--no-extensions` + `-e` 只加载**源码** `packages/coding-agent/src/extensions/agent-team-loop/index.ts`；未加载全局 `~/.pi/agent/extensions/agent-team-loop`；未执行 `mw build --install`；未启停 `mw serve`；未改 `~/.pi/agent`。

---

## 2. 断言 (a): `progress.md` 存在且含机器行

### 命令与逐字输出

```powershell
Select-String -Path "<taskDir>/progress.md" -Pattern '^CKPT [0-9]+m \[machine\]' | ForEach-Object { "L$($_.LineNumber): $($_.Line)" }
```

```
L1: CKPT 1m [machine] ts=2026-09-23T08:49:18.818Z reads=16 writes=0 phases=- repeat_top=2 risk=high
```

（`<taskDir>` = `C:\Users\wenbozhou\AppData\Local\Temp\mwpp-smoke-t5\.agenticdoc\_scratch\workers\mwpp-smoke-review-b`）

任务目录列表（文件真实存在）：

```
Name        Length LastWriteTime
----        ------ -------------
output.md      686 2026/9/23 16:49:28
progress.md    668 2026/9/23 16:49:25
task.md        848 2026/9/23 16:48:42
trace.log     3005 2026/9/23 16:49:28
```

### 附加证据：`trace.log` 的 `[CHECKPOINT]` 与 `worker_file` 工具落盘行

```powershell
Select-String -Path "<taskDir>/trace.log" -Pattern 'worker_file|\[CHECKPOINT\]' | Select-Object -Last 5 | ForEach-Object { $_.Line }
```

```
[CHECKPOINT] 2026-09-23T08:49:18.817Z elapsed=30s reads=16 writes=0 phases=- uniq_targets=0 repeat_top=2 risk=high
[FLOW] 2026-09-23T08:49:25.855Z tool_call worker_file
[TOOL] 2026-09-23T08:49:25.856Z worker_file progress.md
```

即：机器行由框架代码写入（`appendProgressLine`），随后该只读角色还通过窄工具 `worker_file`（append 模式）追加了自评行 —— 本 key 的两条落盘通道在真模型路径上同时观测到。

**断言 (a) 成立。**

---

## 3. 断言 (b): 终稿不含「无法写入 / 代为追加 / PM 代记」

### 命令与逐字输出（`rg`）

```powershell
& rg -n '无法写入|代为追加|PM 代记' "<taskDir>/output.md"; "rg_exit=$LASTEXITCODE"
```

```
rg_exit=1
```

（rg 无匹配时退出码 1、无 stdout —— 即空结果。）

### 扫描有效性对照（避免「绿但未检查」的假阴性）

先把同一正则在**含目标文本的对照文件**上跑一次，证明正则确实能命中：

对照文件 `<proj>\_control_forbidden.md` 内容（逐字）：

```
无法写入 progress.md，请编排方代为追加。PM 代记。
```

```powershell
& rg -n '无法写入|代为追加|PM 代记' "<proj>/_control_forbidden.md"; "rg_exit=$LASTEXITCODE"
```

```
1:无法写入 progress.md，请编排方代为追加。PM 代记。
rg_exit=0
```

同一命令对 `output.md` 返回 `rg_exit=1`（空），对对照文件返回 `rg_exit=0`（命中）→ 空结果不是扫描失效。

### stdout 尾部（worker.log）同样无该文本

```powershell
Select-String -Path "<proj>/worker.log" -Pattern '无法写入|代为追加|PM 代记'
```

```
NO MATCH (empty)
```

`worker.log` 的 stdout 尾部（逐字，注意该文件由 PowerShell `*>` 写成 UTF-16LE，ASCII 部分不受影响）：

```
[worker] start task=mwpp-smoke-review-b type=review phases=-
[worker] done exit=0 elapsed=39s tools=18 tool_errors=1
自评已写入 `progress.md`（append，571 B 内容 + 1 B 换行）。
**收敛状态：yes，eta≈0m。**
- 9 个文件全部严格串行 `read` 完毕，每个都给出了结论，末尾总结在 3 行内。
- 未修改任何被审文件（符合冒烟测试约束）。
- 残差仅为长文档的历史段落未逐行核对（`coding-agent/CHANGELOG.md` 约 5280 行），已在总结与 progress.md 中显式标注，不再展开新工作。
```

**断言 (b) 成立。**

---

## 4. 断言 (c): `exit=0`

### 命令输出的原文

```
exit=0
```

### `trace.log` 终止行（逐字）

```
[END] 2026-09-23T08:49:28.058Z exit=0 elapsed=39s tools=18 phases=-
```

### `worker.log` 的 `done exit=0`（AC-011(c) 的等价机器行）

```
[worker] done exit=0 elapsed=39s tools=18 tool_errors=1
```

（`tool_errors=1` 是模型一次越界 `read offset=101` 的工具错误，与落盘/退出无关，见 §6 trace.log。）

**断言 (c) 成立。**

---

## 5. 降级说明

**本次最终结果无降级**：三条断言均由真模型（timi / deepseek-v4.1-flash）实跑获得，无替代证据、无静默 PASS。

但记录两处过程事实，避免读者误判：

1. **run-1 假阴性（未命中检查点，已重跑修复）**：
   - run-1 使用任务书原始参数 `timeout: 2`（budget 120s → 检查点锚点 60s）+ 6 个文件；
   - 实跑 `ELAPSED_S=30.9`，`exit=0`，`output.md` 无违规文本，但进程在 60s 前结束 → `progress.md` **不存在**（`(no progress.md)`），断言 (a) 不成立；
   - 该次 run 的目录 `mwpp-smoke-review\` 保留在磁盘上（trace.log `[END] ... elapsed=28s` 可复核）。
   - 这正是任务书预告的假阴性模式（运行时长不足触发检查点）；按任务书给出的回退项「改用 `timeout: 1`（锚点 30s）」重跑，run-2 命中锚点（trace `[CHECKPOINT] elapsed=30s`）。

2. **`PI_WORKER_TASK` 取值偏离任务书原文（必要修正，非降级）**：
   - 任务书写作 `$env:PI_WORKER_TASK = $key`（相对 key）；
   - 但 `worker-mode.ts::workerModeActivate` 做 `path.resolve(taskPathEnv)` 后 `fs.existsSync`，相对 key 会解析成 `<cwd>/<key>`（不存在）→ `process.exit(1)`；`launcher.py:248/266/275/298/326` 也始终写 `str(task_path.resolve())` 的绝对路径；
   - 因此本次设置 `$env:PI_WORKER_TASK = <绝对 task.md 路径>`。若按任务书原文执行，worker 会在任何 agent turn 之前退出，冒烟无法开始。

---

## 6. `trace.log` 尾部（含 `[CHECKPOINT]` 与工具行）

run-2 完整 `trace.log`（`<taskDir>\trace.log`，逐字）：

```
[START] pid=13704
[START] 2026-09-23T08:48:48.808Z task=mwpp-smoke-review-b type=review phases=-
[MODEL] 2026-09-23T08:48:48.825Z model=deepseek-v4.1-flash
[FLOW] 2026-09-23T08:48:51.219Z tool_call ls
[TOOL] 2026-09-23T08:48:51.219Z ls C:/Users/wenbozhou/AppData/Local/Temp/mwpp-smoke-t5
[FLOW] 2026-09-23T08:48:51.220Z tool_call find
[TOOL] 2026-09-23T08:48:51.221Z find C:/Users/wenbozhou/AppData/Local/Temp/mwpp-smoke-t5
[FLOW] 2026-09-23T08:48:53.098Z tool_call read
[TOOL] 2026-09-23T08:48:53.098Z read C:/Users/wenbozhou/AppData/Local/Temp/mwpp-smoke-t5/worker.log
[FLOW] 2026-09-23T08:48:53.099Z tool_call ls
[TOOL] 2026-09-23T08:48:53.099Z ls C:/Users/wenbozhou/AppData/Local/Temp/mwpp-smoke-t5/.agenticdoc/_scratch/workers
[FLOW] 2026-09-23T08:48:55.883Z tool_call read
[TOOL] 2026-09-23T08:48:55.883Z read C:/Users/wenbozhou/AppData/Local/Temp/mwpp-smoke-t5/.agenticdoc/_scratch/worker<?>
[FLOW] 2026-09-23T08:48:55.884Z tool_call read
[TOOL] 2026-09-23T08:48:55.884Z read C:/Users/wenbozhou/AppData/Local/Temp/mwpp-smoke-t5/.agenticdoc/_scratch/worker<?>
[FLOW] 2026-09-23T08:48:55.884Z tool_call read
[TOOL] 2026-09-23T08:48:55.885Z read C:/Users/wenbozhou/AppData/Local/Temp/mwpp-smoke-t5/.agenticdoc/_scratch/worker<?>
[FLOW] 2026-09-23T08:48:57.905Z tool_call read
[TOOL] 2026-09-23T08:48:57.906Z read H:/git/Multi-Workers/AGENTS.md
[FLOW] 2026-09-23T08:49:00.183Z tool_call read
[TOOL] 2026-09-23T08:49:00.184Z read H:/git/Multi-Workers/README.md
[FLOW] 2026-09-23T08:49:01.945Z tool_call read
[TOOL] 2026-09-23T08:49:01.945Z read H:/git/Multi-Workers/packages/multi-workers/README.md
[FLOW] 2026-09-23T08:49:03.816Z tool_call read
[TOOL] 2026-09-23T08:49:03.816Z read H:/git/Multi-Workers/packages/coding-agent/README.md
[FLOW] 2026-09-23T08:49:06.370Z tool_call read
[TOOL] 2026-09-23T08:49:06.370Z read H:/git/Multi-Workers/packages/coding-agent/CHANGELOG.md
[FLOW] 2026-09-23T08:49:09.198Z tool_call read
[TOOL] 2026-09-23T08:49:09.198Z read H:/git/Multi-Workers/.agenticdoc/_pitfalls.md
[FLOW] 2026-09-23T08:49:12.025Z tool_call read
[TOOL] 2026-09-23T08:49:12.026Z read H:/git/Multi-Workers/packages/multi-workers/CHANGELOG.md
[FLOW] 2026-09-23T08:49:14.474Z tool_call read
[TOOL] 2026-09-23T08:49:14.475Z read H:/git/Multi-Workers/packages/multi-workers/CHANGELOG.md
[TOOL_ERR] 2026-09-23T08:49:14.476Z read Offset 101 is beyond end of file (52 lines total)
[FLOW] 2026-09-23T08:49:16.669Z tool_call read
[TOOL] 2026-09-23T08:49:16.670Z read H:/git/Multi-Workers/package.json
[CHECKPOINT] 2026-09-23T08:49:18.817Z elapsed=30s reads=16 writes=0 phases=- uniq_targets=0 repeat_top=2 risk=high
[HEARTBEAT] 2026-09-23T08:49:18.819Z task=mwpp-smoke-review-b phase=-
[FLOW] 2026-09-23T08:49:19.675Z tool_call read
[TOOL] 2026-09-23T08:49:19.675Z read H:/git/Multi-Workers/packages/multi-workers/providers.json
[FLOW] 2026-09-23T08:49:25.855Z tool_call worker_file
[TOOL] 2026-09-23T08:49:25.856Z worker_file progress.md
[END] 2026-09-23T08:49:28.058Z exit=0 elapsed=39s tools=18 phases=-
```

> 注：三行 `read C:/.../worker<?>` 的尾部在命令输出中因 PowerShell 控制台编码截断显示为 `worker<?>`；原文件为 UTF-8，目标是被模型探索读取的 worker 目录，不影响本报告任何断言。

---

## 7. `progress.md` 全文（逐字）

```
CKPT 1m [machine] ts=2026-09-23T08:49:18.818Z reads=16 writes=0 phases=- repeat_top=2 risk=high
CKPT 1m converging=yes eta≈0m — 任务要求的 9 个文件已严格串行逐个 read 完毕（AGENTS.md / README.md / multi-workers README.md / coding-agent README.md / coding-agent CHANGELOG.md[前 120 行，[Unreleased] 段] / _pitfalls.md / multi-workers CHANGELOG.md / package.json / providers.json），每个文件已给出结论，末尾总结已交付；未修改任何被审文件。残差：coding-agent CHANGELOG.md 其余 ~5280 行历史段落未逐行核对（冒烟任务未要求），multi-workers CHANGELOG.md 行数统计异常待字节级确认。
```

第 1 行 = 框架机器行（`appendProgressLine` → `formatMachineCheckpoint`，D-105）；第 2 行 = 只读角色经窄工具 `worker_file`（append）写入的自评行。

---

## 8. `output.md` 终稿全文（逐字，仅供 (b) 复核）

```
## TL;DR

自评已写入 `progress.md`（append，571 B 内容 + 1 B 换行）。

## Summary

自评已写入 `progress.md`（append，571 B 内容 + 1 B 换行）。
**收敛状态：yes，eta≈0m。**
- 9 个文件全部严格串行 `read` 完毕，每个都给出了结论，末尾总结在 3 行内。
- 未修改任何被审文件（符合冒烟测试约束）。
- 残差仅为长文档的历史段落未逐行核对（`coding-agent/CHANGELOG.md` 约 5280 行），已在总结与 progress.md 中显式标注，不再展开新工作。
Tools used: find, ls, read, worker_file (18 calls).

## Changed Files
## Verification Steps

See task output for details.

## Exit Reason

Agent settled after 18 tool call(s).
```

（`## Changed Files` / `## Verification Steps` 之间的空行按原文件存在；此处为压缩展示，原文以磁盘文件为准。）

---

## 9. 约束遵守清单

- 未执行 `mw build --install`；未启停 `mw serve`；未改 `~/.pi/agent`。
- 扩展以源码单份加载（`--no-extensions` + `-e`），未同时加载全局 bundle。
- 未修改任何被审文件；除本证据文件与临时项目目录外未改仓库文件。
- 临时项目目录保留在磁盘（`C:\Users\wenbozhou\AppData\Local\Temp\mwpp-smoke-t5`）。
- 未 commit。
