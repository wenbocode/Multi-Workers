# Task T-5: 真模型冒烟（VC-011）

## 元信息
- Stage: 3
- 依赖: T-3、T-4
- 风险: 高（真模型调用；会写临时项目目录）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-009, AC-011]
- vc_refs: [VC-011]

## 目标

用**真模型**跑一次只读角色 worker，证明：检查点机器行由框架落盘；终稿不再出现「无法写入 / 请编排方代为追加」这类指令请求；进程 exit=0。

## 运行命令（PM 已实测可用，PowerShell）

本机 shell 是 PowerShell，`./pi-test.sh` 不能直接跑（`.sh` 无法在管道中执行）；用 tsx 直接跑 CLI（已验证 `--version` → `0.83.0`）。**cwd 必须是临时项目根**：

```powershell
$repo = "H:/git/Multi-Workers"
$tsx  = "$repo/node_modules/tsx/dist/cli.mjs"
$proj = "$env:TEMP/mwpp-smoke-1"
$key  = "mwpp-smoke-review"
$task = "$proj/.agenticdoc/_scratch/workers/$key/task.md"

# 1) 任务书
New-Item -ItemType Directory -Force (Split-Path $task) | Out-Null
@"
...
"@ | Set-Content -Encoding utf8 $task

# 2) 真模型跑 worker（源码扩展，不装全局、不构建）
# PI_WORKER_TASK 必须是 **绝对 task.md 路径**：worker-mode 做 path.resolve()+existsSync，
# 相对 key 会解析到 <cwd>/<key> 不存在 → 在任何 agent turn 之前 process.exit(1)
# （launcher.py 也始终写绝对路径）。
$env:PI_WORKER_TASK = $task
Set-Location $proj
node $tsx --tsconfig "$repo/tsconfig.json" "$repo/packages/coding-agent/src/cli.ts" `
  --no-extensions -e "$repo/packages/coding-agent/src/extensions/agent-team-loop/index.ts" `
  --no-skills --provider timi -p "执行你的 worker 任务"
"exit=$LASTEXITCODE"
```

要点：

- `PI_WORKER_TASK` 必须是**绝对 task.md 路径**（见上）；只给 key 名会在任何 agent turn 之前 `exit 1`。
- `timeout: 2` → budget 120s → 检查点锚点 60s；提示词要求逐个读 6 个文件，保证运行 > 60s（否则检查点不触发 → 假阴性）。**实测：6 个文件只跑了 30.9s 未触发锚点，改 `timeout: 1`（锚点 30s）+ 9 个文件后在 39s 内命中**。若第一次未触发，按此回退。
- `--no-extensions` 关闭扩展发现，`-e` 只加载**源码这一份** agent-team-loop（不得同时加载全局 `~/.pi/agent/extensions/agent-team-loop`）。
- **不允许 `mw build --install`**（会改全局扩展目录、影响其他窗口）；不启停 `mw serve`。
- 若 `-p` 模式下扩展未起转（临时项目里没有 trace.log），改试交互模式：`tmux` 起 `node $tsx ... "$repo/packages/coding-agent/src/cli.ts" -e ... --provider timi`，`send-keys` 提交提示词，等模型回复后再看产物（照 AGENTS.md 的 tmux 配方）。仍失败则记录降级原因。
- 凭证：worker 进程已由 launcher 注入 timi 路由所需凭证；若 `--provider timi` 报鉴权错误，如实记录为降级（不要改用其他 provider 掩盖）。

## 交付物

`evidence/verify-run-2026-09-23.md`，含：

1. 运行的完整命令、时间、临时项目路径、task_key、provider/model。
2. 三条断言的**原始证据**（命令 + 输出片段，逐字复制，不转述）：
   - (a) `<taskDir>/progress.md` 存在，且 `Select-String '^CKPT [0-9]+m \[machine\]'` ≥ 1 行；或 `trace.log` 含 `worker_file` / `[TOOL] worker_file`；
   - (b) 终稿文本（`output.md` 的 `## Summary` 或 stdout 尾部）**不含**「无法写入」「代为追加」「PM 代记」（给出 `rg` 命令 + 空结果证据）；
   - (c) `exit=0` 的原文。
3. `trace.log` 尾部（含 `[CHECKPOINT]` 与机器行/工具行）与 `progress.md` 全文。
4. **降级说明**：任何一条未达成（额度不足、provider 不可用、运行时长不足触发检查点、环境缺凭证）必须显式写「降级 + 原因 + 已获得的替代证据」，不得静默标 PASS。

## 约束

- 除 `evidence/verify-run-2026-09-23.md` 与临时项目目录外不得改仓库文件。
- 临时项目留在磁盘上（不要删）以便 PM 复核，路径写进证据文件。
- 冒烟任务必须自称冒烟（不得伪装成正式审查结论）；不得修改被审文件。
- 不 commit；不 `mw build --install`；不改 `~/.pi/agent`。

## 验收命令

```powershell
Select-String -Path <taskDir>/progress.md -Pattern '^CKPT [0-9]+m \[machine\]'
rg -n '无法写入|代为追加|PM 代记' <taskDir>/output.md
Select-String -Path <taskDir>/trace.log -Pattern 'worker_file|\[CHECKPOINT\]' | Select-Object -Last 5
```

## 报告要求

最终消息第一行给单行结论（PASS / 降级）；随后给三项断言各自的原始证据、`progress.md` 全文、以及任何偏离本任务书之处。
