# 在 Codex 中开发、派工和验收

Codex 负责需求、任务卡、验收和 key 结案。MW 服务负责运行 worker。此入口使用 pi 的 coding worker，沿用项目已有的模型路由、写入范围和派发门禁。命令输出 JSON，支持在独立的 Codex 会话或终端里继续同一项工作。

## 1. 建立开发基线

在已完成 MW bootstrap 的控制工作区使用 AgenticTask skill。按项目 goal 编写 spec 和编号 AC，认领 key，保存返回的 ClaimId。通过 `advance_phase.py` 依次推进 design、plan、tasks 和 execute，设计中写明每条 AC 怎么验证。以下 PowerShell 示例从 Multi-Workers 仓库根运行。用于其他项目时，把 `$project` 设为控制工作区，把 `$pm`、`$mw` 指向本仓库的绝对路径。

```powershell
$project = (Resolve-Path .).Path
$pm = (Resolve-Path packages/multi-workers/codex_pm.py).Path
$mw = (Resolve-Path packages/multi-workers/mw.py).Path
$key = 'counter'
$card = 'T-01'
$pmClaim = 'HOST:PID'  # 填本次 AgenticTask claim 返回的原值
python $mw status --project $project
```

服务尚未运行时执行 `python $mw start --project $project`。Codex PM 从本地 checkout 调用 pi 的 PM 工具，需有项目依赖、可加载的 pi SDK 和支持直接运行项目 TypeScript 的 Node。验收使用 Python 3.11+。

在 `.agenticdoc/counter/tasks/T-01.md` 写 coding 卡。以下示例约定项目已含 `tests/test_counter.py`，其中检查对输入 4 调用 increment 的结果等于 5。验收命令使用一个 JSON 字符串数组，数组的每项是一个进程参数。有多条检查时，可调用仓库已有的验收脚本。

````markdown
type: coding

## 上下文
.agenticdoc/goal.md 和 counter.py:1 定义计数器行为，对应 AC-001。

## 要求
实现 increment，返回输入加一。

## 交付格式
交付工作区改动，在本次 worker 的 output.md 列出改动、证据和遗留。

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

## 2. 派工和恢复

```powershell
python $pm dispatch --project $project --key $key --claim-id $pmClaim --card $card
python $pm status --project $project --key $key
```

`dispatch` 成功表示已入队。相同 key 与卡名生成稳定的 worker ID，重复调用返回已有回执。原卡改动后要返工时，新增卡名，并在卡里引用原任务与失败证据。Codex 可以关闭会话，MW 在后台继续运行。

同一 key 由一个 PM 推进。已列入启用的 Autopilot roadmap 的 key 由 conductor 派工，Codex 可用 `status` 观察其 worker。手动派发的 key 在结案前应保持由 Codex 管理。

新会话先运行 `status`。返回的 `phase`、`pm_state`、`cards`、`pending_gates` 和 `tasks` 用于恢复工作。每个任务分别给出队列状态、worker 自身运行状态、产物、验收结果和历次证据路径。失败时从 `worker.log`、`trace.log` 和 `output.md` 定位原因。处于 pending 时检查服务与队列。遇到 gate 时用现有 `mw.py autopilot gates --project <目录> --json` 核对问题和证据，按项目授权答复。

## 3. 独立验收与结案

worker 完成后，Codex 先读改动和 output.md，再用卡上约定的参数运行验收。开发阶段可以早验；所有卡执行完成后通过 AgenticTask 进入 VERIFY。

```powershell
python $pm verify --project $project --key $key --claim-id $pmClaim --card $card -- python -m pytest -q tests/test_counter.py
python $pm status --project $project --key $key
```

验收在派工时约定的目标工作区运行。PM 会核对终态、非空产物、命令参数和目标目录。每次执行在 `<key>/evidence/codex-pm/<task>/<run>/` 保存 `command.log` 与 `result.json`，包含 argv、cwd、退出码、时间及派工单和 worker 报告的摘要。退出码 0 表示本次命令通过，1 表示验收失败或失效，2 表示调用被拒或运行环境异常。查询显示最近一次运行的结论；源代码或测试变化后应重新执行验收。

失败时把日志关联到原 AC，修复后重跑同一命令。通过后把证据路径及 AC/VC 对应关系写入质量报告和 pm-state，完成 review 和 achieved.md，使用 `advance_phase.py <key> done --summary "..."` 并运行 `audit_phase.py <key>`。如该 key 配置了额外签收门禁，按门禁返回的要求完成签收。最后通过 `update_index.py release <key>` 释放认领。
