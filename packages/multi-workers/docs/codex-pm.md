# Codex PM 轻量开发、派工和验收

Codex PM 用 `codex_doc.md` 保存一项任务的目标、范围、验收标准、关键决定、进度和接续信息，用 `achieved.md` 保存结案结果。只有转派给 MW Worker 的工作才建立任务卡。AgenticTask 原脚本和 MW Worker 执行逻辑保持原样；MW PM 仍走完整 SDD 流程。

## 1. 建立或恢复任务

在已完成 MW bootstrap 的控制工作区运行以下命令。用于其他项目时，把 `$project` 设为控制工作区，把 `$pm`、`$mw` 指向 MW checkout 的绝对路径。

```powershell
$project = (Resolve-Path .).Path
$pm = (Resolve-Path packages/multi-workers/codex_pm.py).Path
$mw = (Resolve-Path packages/multi-workers/mw.py).Path
$key = 'counter'
python $pm init --project $project --key $key
```

`init` 生成 `.agenticdoc/<key>/codex_doc.md`，以 `SPEC / active / codex` 登记索引。填写主记录的 `## 目标`、`## 范围`、`## 验收标准` 和 `## 接续须知`，验收标准使用 `- AC-001: 可观察的结果` 格式。目标应对应 `.agenticdoc/goal.md`，范围应写明控制工作区、目标工作区和允许的改动。

用两三句话在「目标」段写清交付结果、与项目目标的关系和完成时可观察的结果。这一段就是轻量 key 的 `spec_goal`，MW 宿主只提取该段供派到此 key 的 Worker 使用。定稿后，replan 沿用原文。

`init` 优先使用控制工作区的 `.agenticdoc/templates/codex_doc.md`，缺失时使用发行版模板。已有的旧版自定义模板会保留；使用轻量入口前须把它的机器字段对齐下列 schema，格式不符时命令会明确报错，不会覆盖定制内容。

主记录中的机器接口是：

```markdown
- Workflow: codex-lite
- Key: counter
- Phase: SPEC
- Claim-Id: codex
- Status: active
```

这些字段由 Codex 命令维护。`_index.parallel` 记录同一 key 的真实阶段、状态和 ClaimId；`_index.md` 保持共享锁内生成的完整 `active_keys` 数组。`codex` 是共享的 PM 类型标识，不区分窗口；每条命令都必须显式给 `--key`，同一个 key 由一个 PM 推进。

```powershell
python $pm status --project $project --key $key
python $pm advance --project $project --key $key --phase EXECUTE
```

主记录完整后才可进入 `EXECUTE`。接续已有任务先查 `status`，再读主记录和在途 Worker 产物。`release` 只把认领设为 idle，保留当前阶段；`claim` 恢复未结案的轻量 key。`DONE` key 和完整 SDD key 不自动转成轻量任务。

```powershell
python $pm release --project $project --key $key
python $pm claim --project $project --key $key
```

轻量 key 的 `pm-state.md` 只保留机器认领接口，`Phase: init` 表示没有启用 SDD。实际轻量阶段从主记录和索引读取。不要为满足 SDD 门禁生成空的 spec/design/research，也不要把 `audit_phase.py` 的“尚无阶段可审计”视为验收通过。原有完整 SDD key 继续使用原阶段和质量门禁，仅有 `PM mode: codex` 不会获得轻量派发资格。

## 2. Codex 直接执行和验证

完整 SDD key 在 `VERIFY` 阶段调用 MW PM 的 `advance_phase` 进入 Done 时，交互式 PM 和 autopilot 会先检查已有签收，或从原工作区已成功终止的独审 Worker 复用证据。若逐项验收和结案摘要保存在单独文件中，Worker 报告须用反引号引用 key 内的证据路径。证据或人工批准存在缺口时，流程会停在 Done 门禁。

需要指定独审时，可以直接调用正式签收 CLI。

```powershell
$request = @{
    decision_source = 'pm-evidence'
    review_task = 'release-review'
    review_source = 'workers/release-review/report.md'
}
$request | ConvertTo-Json -Compress | python $mw decide sign $key --project $project --stdin --json
```

该入口重新验证当前冻结合同、逐项证据哈希、独审终态、`achieved.md` 及正式批准。签收后使用完整 SDD 的正式 Done 入口。签收及后续校验可在 PM 交接后执行。

Codex 按主记录实施，把关键决定、进度和下一步直接记回本页。实现者自验与另一执行者的复核分别说明；只有自验时如实记录。

进入验收后，用 `check` 保存与 AC 对应的真实命令及结果；同一命令可重复提供 `--ac` 覆盖多个验收标准：

```powershell
python $pm advance --project $project --key $key --phase VERIFY
python $pm check --project $project --key $key --ac AC-001 -- python -m pytest -q tests/test_counter.py
```

验证证据保存在本 key 的 `evidence/`，主记录只引用其路径。证据绑定运行时的目标工作区、源码快照，以及主记录的目标、范围和验收标准；其中任一项变化都会使旧证据失效。同一工作区中与本任务无关的源码改动也会触发失效，任务状态和生成目录按程序排除。最后一批编辑完成后重新验证，再结案。命令失败、证据失效或验收未覆盖时继续修复和复验。

## 3. 按需派给 MW Worker

首次派发前必须显式选择工作区模式。控制和开发目录相同时，在 `.agenticdoc/target.yml` 写 `active: single`；dual/partition 配置目标根，见 [工作区配置](../README.md#双工作区代码目录与工作目录分离)。无配置时查询显示的 `single/default` 不授予派发资格。

服务未运行时执行 `python $mw start --project $project`。派发需要项目依赖、可加载的 pi SDK 和支持直接运行项目 TypeScript 的 Node；验收使用 Python 3.11+。

只有需要转派时才在 `.agenticdoc/<key>/tasks/` 建卡。卡片应包含目标、对应 AC、剩余交付、依赖、已有证据、目标工作区、写入边界和验收命令。以下示例假定已有 `counter.py` 和验收测试。

````markdown
type: coding

## 上下文
.agenticdoc/goal.md 和 counter.py:1 定义计数器行为，对应 AC-001。

## 要求
实现 increment，返回输入加一。

## 交付格式
交付工作区改动，在本次 worker 的 output.md 列出改动、验证结果和遗留。

## 写入允许面
- counter.py

## 写入禁止面
- tests/

## 验收命令
```json
["python", "-m", "pytest", "-q", "tests/test_counter.py"]
```

## 改动历史
首版任务卡。
````

```powershell
$card = 'T-01'
python $pm dispatch --project $project --key $key --claim-id codex --card $card
python $pm status --project $project --key $key
```

只能在 `EXECUTE` 派发。Codex 专属入口核对主记录、索引和 ClaimId 后启用轻量适配；普通 MW 入口仍检查原 SDD 文档。两者继续执行相同的任务卡、工作区、模型、写入范围和队列检查。Worker 按任务卡执行，无需读取或创建 PM 过程文档。

派发成功表示已入队。相同 key 和卡名生成稳定任务 ID，重复派发返回已有回执。原卡修改后需要返工时，新增卡名并引用原失败证据。Codex 可以关闭会话，MW 在后台继续运行；下一次先查 `status`，从 `worker.log`、`trace.log` 和 `output.md` 恢复。

Worker 完成后，PM 阅读实际改动与报告，执行派发时的同一验收命令：

```powershell
python $pm verify --project $project --key $key --claim-id codex --card $card -- python -m pytest -q tests/test_counter.py
```

验收固定在派发时约定的目标工作区。每次执行保存命令、cwd、退出码和 Worker 产物绑定。退出码 0 表示通过，1 表示验收失败或失效，2 表示调用被拒或运行环境异常。把证据和 AC 对应关系记回主记录；失败时修复并重新验证。

同一 key 仍由 Codex PM 负责整个交付。已列入启用的 Autopilot roadmap 的 key 由 conductor 管理，Codex 只能查询，不能从此入口重复派发。

## 4. 结案与回溯

逐条检查验收标准和实际证据，确认在途任务已收尾，在 `achieved.md` 记录：

- 系统行为变化、改动触达面和关键决定。
- `## 修改面`：逐条列出本 key 实际写入的代码路径（见第 5 节）；没有写入时明确写“无改动”。
- 对应验收证据，区分自验与独立复核。
- 遗留项及明确去向；没有遗留也写明。

```powershell
python $pm done --project $project --key $key --summary 'Counter implemented and verified'
python $pm status --project $project --key $key
```

结案接口验证验收覆盖、Worker 状态、结案记录和当前归属，把 key 设为 `DONE / idle`、ClaimId 清为 `—`，从完整 `active_keys` 投影中移除，再更新项目回溯记录。缺少验证或仍有未完成工作时保留任务状态，并在接续须知明确下一步。

项目回溯记录的 Codex 写入有独立锁，但与 AgenticTask 原写入器没有跨流程原子保证。状态已完成而回溯记录写入失败时，命令会报告 `PARTIAL WRITE`；检查实际状态和日志后恢复，不能把部分写入当作完整成功。

## 5. 结案修改面留底

pi PM 窗口每次成功的 `write` / `edit` / 可静态解析的 `bash` 写入由宿主追加到 `.agenticdoc/<key>/write-journal.jsonl`。追加前在索引锁内确认当前窗口仍持有该 key 的有效认领。MW Worker 沿用 `workers/<task>/trace.log` 的 `[WRITE_FILE]` / `[WRITE_UNRESOLVED]`。Codex CLI/桌面 PM 的 `apply_patch` 不经过 pi 工具层，因此 `achieved.md` 的 `## 修改面` 是这一分支的显式写入声明。

两种 done 入口都调用 `change_set.py` 生成 `change-set.json` 与 `change-set.md`，并在 `completion.json` 写入 `change_set` 指针。记录内容：去重后的实际写入路径、每条路径的 `sources`（`worker-trace` / `pm-tool-result` / `pm-declared`）、首末写时间、工具、卡、结案时 `sha256` 和 `coverage`。整个 `.agenticdoc/` 是过程状态，全部排除；记录来自写事件本身，不做仓库对比、不依赖 git、不生成补丁。

`done` 缺 `## 修改面` 或该段没有有效路径时 exit 2 拒绝结案。带空格的路径用反引号括起来。文件存在时记录结案哈希。机器记录里有而声明里没有的路径列在 `coverage.machine_paths_missing_from_declared`，声明中缺少机器记录的路径列在 `coverage.declared_paths_missing_from_machine`。任一列表有路径时 `coverage.complete=false`。复核时先打开 `change-set.md`，再看 `coverage` 与对应卡片的 `output.md`。
