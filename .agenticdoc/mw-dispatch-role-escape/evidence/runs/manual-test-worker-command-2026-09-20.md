# 手工测试用例：`/worker` 命令路径（RPC live 窗口执行）

> 目的：补上质检欠债 Q-AC-003 / Q-VC-002（`/worker` 命令路径只有单测，无 live 证据）。
>
> 2026-09-21 修订：
> - **执行方式改为 RPC 模式真实 pi 进程**（`pi --mode rpc --no-session`，cwd = 本仓）。
>   RPC 协议中 extension command 可经 `prompt` 命令直接执行，notify 以
>   `extension_ui_request(method=notify)` 回传 stdout，无需 TTY/tmux 即可采集通知原文。
>   （原报告认为「缺 tmux、`pi -p` 无法执行 slash 命令」，RPC 模式补齐了这一路径。）
> - **测试项目改为本仓 `H:\git\Multi-Workers`**。本仓 `.mw/dispatch.yml` 为 `{}`，
>   TC-0（给 review 档设值）从「仅框架仓需要」变为**必做前置**。
> - **核对路径修正**：`/worker` 生成的任务目录是 `_scratch\workers\manual-<timestamp>\`；
>   `[mwtest-N]` 只是描述文本标记（用于 grep task.md / trace.log 定位），不参与目录命名。
>   任务 key 从 notify 文本 `Dispatched pi worker (manual-...)` 中提取。
> - E2Feature 的 `.mw/dispatch.yml` 仍是错 id `timi/gpt-5.6.sol`（原 TC-6 的修复目标），
>   本轮不触碰，留待该项目的窗口自行 `/mw model set review timi/gpt-5.6-sol` 修正。
>
> 说明：每次「接受」的派工都会真的起一个 worker（真实模型调用）。用例描述统一写
> `Do nothing: reply 'no work needed' immediately, make no tool calls.` 以压低开销。
> 全部用例使用 `--key _scratch`，绕开 docs 门禁。

## 执行载体

临时 Node driver（用后删除）：spawn `pi --mode rpc --no-session`，cwd = 本仓，
逐条发送 `{"type":"prompt","message":"<命令>"}`，监听 stdout 采集：

- `{"type":"response","command":"prompt","success":true|false}`（命令是否被接受）
- `{"type":"extension_ui_request","method":"notify","message":"...","notifyType":"..."}`（通知原文）

全程日志落盘 `evidence\runs\rpc-driver-2026-09-21.log` 作为证据。

## TC-0 给 review 档设值（必做：本仓 dispatch.yml 为 `{}`）

```
/mw model set review timi/gpt-5.6-sol
```
期望 notify 成功；核对 `.mw/dispatch.yml` 出现 `review: timi/gpt-5.6-sol`。
若不先做本步，TC-1 会因 effective 值（`{}` → 无配置）走 `route default` 分支，
且 TC-2/TC-3/TC-7 失去「覆盖配置默认值」的对照前提。

## TC-1 type 可声明 → review role 与白名单可达

```
/worker pi --type review --key _scratch Do nothing: reply 'no work needed' immediately, make no tool calls. [mwtest-1]
```
期望 notify 含：`type: review, role: review` 与 `model: dispatch.yml review=timi/gpt-5.6-sol`。
从 notify 提取任务 key（`manual-<ts>`）后核对：
```powershell
$P = "H:\git\Multi-Workers"
$k = "<notify 中的 manual-*>"
Get-Content "$P\.agenticdoc\_scratch\workers\$k\task.md" -TotalCount 3   # 期望首行 type: review，无 model 行；正文含 [mwtest-1]
Select-String -Path "$P\.mw\launcher.log" -Pattern $k                     # 期望 source=config:review
Select-String -Path "$P\.agenticdoc\_scratch\workers\$k\trace.log" -Pattern "type=|\[MODEL\]|tool_call"
# 期望 type=review、model=gpt-5.6-sol（配置档模型）、仅 read/find/grep/ls 类工具
```

## TC-2 覆盖 role 默认值但不给理由 → 拒绝（无半成品）

```
/worker pi --type review --model timi/gpt-5.6-luna --key _scratch Do nothing. [mwtest-2]
```
期望 notify 报 `needs model_reason` 且点名 `dispatch.yml review=timi/gpt-5.6-sol`；
不存在 task.md 正文含 `[mwtest-2]` 的目录：
```powershell
Get-ChildItem "H:\git\Multi-Workers\.agenticdoc\_scratch\workers" -Recurse -Filter task.md |
  Select-String -Pattern "\[mwtest-2\]"        # 期望无结果
```

## TC-3 覆盖 + 理由 → 通过、落盘、留痕

```
/worker pi --type review --model timi/gpt-5.6-luna --reason "luna for the longer diff" --key _scratch Do nothing. [mwtest-3]
```
期望 notify 含 `model override: role default review=timi/gpt-5.6-sol -> timi/gpt-5.6-luna (reason: luna for the longer diff)`。
核对：
```powershell
Get-Content "$P\.agenticdoc\_scratch\workers\$k\task.md" -TotalCount 4
# 期望：type: review / model: timi/gpt-5.6-luna / model-reason: luna for the longer diff
Select-String -Path "$P\.mw\launcher.log" -Pattern $k
# 期望两行：model=timi/gpt-5.6-luna source=task  和  model-override task=timi/gpt-5.6-luna config:review=timi/gpt-5.6-sol
```

## TC-4 非法 type → 拒绝

```
/worker pi --type bogus --key _scratch Do nothing. [mwtest-4]
```
期望 notify 列出合法值 `coding|review|research`，且无 `[mwtest-4]` 的 task.md。

## TC-5 不存在的模型 id → 拒绝（AC-007 fail-closed）

```
/worker pi --type review --model timi/gpt-5.6.sol --reason "should be rejected" --key _scratch Do nothing. [mwtest-5]
```
期望 notify 报 `not found for provider 'timi'`，且无 `[mwtest-5]` 的 task.md。
（该 id 正是 E2Feature dispatch.yml 里遗留的错 id，本用例同时证明 registry 校验兜底。）

## TC-6 `/mw model set` 的 registry 校验（对齐原 TC-6 的命令面）

```
/mw model set review timi/gpt-5.6.sol     # 期望 notify: not found for provider 'timi'（不写盘）
/mw model set review timi/gpt-5.6-sol     # 期望成功（幂等重设）
```
核对 `.mw/dispatch.yml` 始终为 `review: timi/gpt-5.6-sol`。

## TC-7 等值不 pin（配置保持唯一事实来源）

```
/worker pi --type review --model timi/gpt-5.6-sol --key _scratch Do nothing. [mwtest-7]
```
期望 notify 报 `matches the configured default; not pinned`，
task.md **不含** `model:` 行（首行仅 `type: review`）。

## 结果记录（2026-09-21 执行，RPC live 窗口）

执行环境：`pi --mode rpc --no-session`（0.83.0，cwd = 本仓，加载全局安装的
`~/.pi/agent/extensions/agent-team-loop.js`，2026-09-20 20:49 构建）；serve PID 59560
（2026-09-21 14:24 启动，新代码）。全程序日志：`rpc-driver-2026-09-21.log`。

| 用例 | 结果 | 证据（通知原文 / 文件） |
|------|------|----------------------|
| TC-0 | ✅ | notify `[mw model set] review = timi/gpt-5.6-sol`；`.mw/dispatch.yml` → `review: timi/gpt-5.6-sol` |
| TC-1 | ✅ | notify `Dispatched pi worker (manual-1789974535494) under key '_scratch' [type: review, role: review, model: dispatch.yml review=timi/gpt-5.6-sol]`；task.md 首行 `type: review`、无 model 行；launcher.log `model=timi/gpt-5.6-sol source=config:review`；trace.log `type=review` + `[MODEL] model=gpt-5.6-sol` + 仅 `read` 工具；worker done，output.md `no work needed` |
| TC-2 | ✅ | warning `Model override for role 'review' needs model_reason: dispatch.yml review=timi/gpt-5.6-sol, requested=timi/gpt-5.6-luna. ...`；全树无 `[mwtest-2]` task.md |
| TC-3 | ✅（TC-3b 单词 reason 重跑） | notify `model override: role default review=timi/gpt-5.6-sol -> timi/gpt-5.6-luna (reason: luna-for-the-longer-diff)`；task.md `type:`/`model: timi/gpt-5.6-luna`/`model-reason: luna-for-the-longer-diff`；launcher 两行 `model=timi/gpt-5.6-luna source=task` + `model-override task=timi/gpt-5.6-luna config:review=timi/gpt-5.6-sol`；trace `model=gpt-5.6-luna`。首跑（带引号 reason）暴露发现 F-1 |
| TC-4 | ✅ | warning `Invalid type 'bogus'. Must be one of: coding, review, research.`；无 `[mwtest-4]` task.md |
| TC-5 | ✅ | warning `Model 'timi/gpt-5.6.sol' not found for provider 'timi' (known ids include: ...)`；无 `[mwtest-5]` task.md |
| TC-6 | ✅ | TC6a `/mw model set review timi/gpt-5.6.sol` → error 同上拒绝、不写盘；TC6b 重设成功；dispatch.yml 始终 `review: timi/gpt-5.6-sol` |
| TC-7 | ✅ | notify `... model: dispatch.yml review=timi/gpt-5.6-sol (requested value matches the configured default; not pinned)`；task.md 仅 `type: review`（无 model 行）；launcher `source=config:review` |

## 执行发现

- **F-1（行为特性，非回归）**：`/worker` 命令的 flag 解析按空白切分，不支持带引号的多词
  `--reason` 值。首跑 TC-3 用 `--reason "luna for the longer diff"` 时：reason 只取到
  `"luna`，`--key _scratch` 被吞进描述文本，任务落到 active key `mw-worker-tree-kill`
  下（`.agenticdoc/mw-worker-tree-kill/workers/manual-1789974567567/`，已完成，保留作证）。
  多词理由需用连字符（如 `luna-for-the-longer-diff`）或改用 `dispatch_worker` 工具
  （`model_reason` 参数无此限制）。可作为后续改进项（如支持引号解析或文档明示单词限制）。
- 本仓 `.mw/dispatch.yml` 因 TC-0 从 `{}` 变为 `review: timi/gpt-5.6-sol`（有意保留，
  框架仓 review 档自此有值）。
- E2Feature 的错 id 修正不在本轮范围（见文首说明）。

任一条失败：把 RPC 日志中的通知原文带回 PM 窗口，重新打开 key `mw-dispatch-role-escape`（EXECUTE）修复，不要就地改代码。
全部通过：本 key 质检欠债 **Q-AC-003 / Q-VC-002 已于 2026-09-21 采集 live 证据关闭**，
同步更新 `evidence\quality-gate-report-2026-09-20.md` 的欠债表与 `achieved.md`。
