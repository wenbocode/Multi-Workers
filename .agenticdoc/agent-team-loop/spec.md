# Spec: Agent Team Loop MVP

> Key: agent-team-loop
> 创建时间: 2026-08-10
> 状态: confirmed（AC-001~031 locked 2026-08-10；AC-032~036 locked 2026-08-11）

## §1 功能概述

### 1.1 目标

构建一个可运行的 Agent Team Loop MVP，以 **pi CLI 为唯一用户入口**。

Pi CLI 在两种模式下运行：
- **PM 模式**（主进程，无 `PI_WORKER_TASK`）：加载 `pm-orchestrator.ts` Extension，
  用户在 pi TUI 内完成需求澄清、任务派发、结果验收。PM 逻辑完整实现为 TypeScript，
  不调用 AgenticTask Python 脚本。
- **Worker 模式**（子进程，`PI_WORKER_TASK` 已设）：加载 `worker-mode.ts` Extension，
  headless 执行单个任务，写 output.md，以 exit(0/1/2/130) 上报结果。

**`mw serve`（独立后台服务）**：管理 proxy_multi.py 和 launcher.py 的完整生命周期。
服务独立于 pi 进程，pi 退出后 mw serve 继续运行，正在执行的 worker 不被中止。

**部署模型**：`mw init <project-dir>` 创建目标项目目录，同步框架，并将预编译的
`agent-team-loop.js` Extension 安装到 `<project-dir>/.pi/extensions/`；
pi 以 cwd 为项目根启动，自动发现并加载该 Extension。

### 1.2 技术栈 / 语言

| 组件 | 语言 / 运行时 | 角色 |
|------|-------------|------|
| pm-orchestrator.ts | TypeScript（Pi Extension，Node.js ≥ 18） | PM Agent 完整实现（读写 pm-state.md / _index.parallel / _workers.parallel / goal.md / task.md） |
| worker-mode.ts | TypeScript（Pi Extension，Node.js ≥ 18） | Pi worker 模式（headless 执行，写 output.md + trace.log） |
| mw.py（serve/init/stop/status 子命令） | Python ≥ 3.10 | 项目初始化 + 后台服务管理（PID 文件防重复） |
| launcher.py | Python ≥ 3.10 | 轮询 _workers.parallel + spawn worker 进程（由 mw serve 管理） |
| proxy_multi.py | Python ≥ 3.10（依赖 timi-proxy-cli） | 多端口 LLM 路由（由 mw serve 管理） |
| smoke_test.sh | Bash（Git Bash on Windows） | 端到端验证 |
| dispatch-table.md | Markdown | 路由规则参考文档 |

### 1.3 核心用户场景

1. **S1 正常分派**：用户在 pi PM 模式下发出指令，pm-orchestrator.ts 将
   `Status=pending, Cli=codex` 写入 `_workers.parallel` 并创建 task.md；
   mw serve（launcher.py）在 5 秒内检测到，spawn codex worker 并注入 proxy URL 和 API key；
   codex 完成后 launcher 更新 `_workers.parallel` status 为 done；pm-orchestrator 轮询到 done
   后读取 output.md，在 pi TUI 呈现验收结果。

2. **S2 worker 失败 / 澄清**：worker 以如下 exit code 退出，launcher 更新 `_workers.parallel`
   status，output.md 在任何情况下都被落盘：

   | exit code | 含义 | output.md 要求 |
   |-----------|------|---------------|
   | 0 | 成功 | 4 节完整，> 50 bytes |
   | 1 | 失败（模型/工具错误、超时） | 含 Exit Reason 节说明失败原因 |
   | 2 | 需澄清（信息不足） | Verification Steps 节替换为 Questions 节 |
   | 130 | 取消（SIGINT） | 写已完成部分，各节可部分填充 |

   pm-orchestrator 轮询到非 done 状态后在 pi TUI 提示用户决定重试或人工干预。

3. **S3 Pi worker 模式**：pi 以 `PI_WORKER_TASK` 环境变量激活 worker-mode.ts extension，
   自动读取 task.md、限制工具集、执行任务、写 output.md 和 trace.log，
   以 process.exit(0/1/2/130) 上报结果。

4. **S4 Goal-Anchored 多阶段执行**：task.md 含 `phases` 字段时，worker 每完成
   一个阶段写入 `progress/phase-N.md` 并读取 `.agenticdoc/goal.md` 检查目标变更；
   pm-orchestrator 可在任意时刻修订 goal.md，worker 下一检查点感知变更。

5. **S5 项目初始化**：用户执行 `python mw.py init <project-dir>`，创建
   `.agenticdoc/` 目录结构，将 `dist/extensions/agent-team-loop.js` 安装到
   `<project-dir>/.pi/extensions/`，并引导 goal.md 多轮对话；
   `mw serve --project <project-dir>` 启动后台服务，`cd <project-dir> && pi` 进入 PM 模式。

### 1.4 范围说明（不做什么）

- 不实现 codex / claude worker-mode extension（两者直接接受命令行提示）
- 不实现自动化 CI 集成
- 不实现 Web UI / dashboard
- 不支持 macOS / Linux（保留空扩展桩）
- 不做超过 3 个 worker 同时并行的压测
- pm-orchestrator.ts 不调用 AgenticTask Python 脚本（纯 TypeScript 实现）
- mw init 不执行 TypeScript 编译，Extension 以预编译 JS 文件分发

---

## §2 业务约束

### 2.1 平台 / 环境

- **主平台**：Windows 11，Git Bash（用于 shell 脚本）
- **其他平台**：代码中保留 `if (process.platform === 'win32')` / `if sys.platform == 'win32'` 分支，其他平台抛出 `NotImplementedError` 占位
- **用户入口**：`cd <project-dir> && pi`（PM 模式，pm-orchestrator.ts 已加载）
- **mw serve**：`mw serve --project <project-dir>` 独立后台运行，PID 文件在 `<project-dir>/.mw/mw.pid`
- **Multi-Workers（框架源）**：存放 mw.py、launcher.py、proxy_multi.py、pm-orchestrator.ts 源码，以及预编译产物 `dist/extensions/agent-team-loop.js`
- **目标项目结构（`mw init` 后）**：
  ```
  <project-dir>/
    .agenticdoc/
      goal.md                ← pi PM 模式 goal elicitation 产出，可修订
      _index.md              ← AgenticTask 活跃 key 记录
      _index.parallel        ← AgenticTask PM claim 状态（Key|Status|Phase|ClaimId|Deps|Desc|Updated）
      _workers.parallel      ← worker 任务队列（Task-Key|Status|Cli|Provider|TaskPath|DispatchedAt|UpdatedAt）
      <key>/
        pm-state.md          ← pm-orchestrator.ts 维护
        task.md
        output.md
        progress/            ← Goal-Anchored 检查点（phase-1.md, phase-2.md…）
    .mw/
      mw.pid                 ← mw serve PID 文件，防重复实例
    .pi/
      extensions/
        agent-team-loop.js   ← mw init 从 Multi-Workers dist/ 复制，pi 自动发现加载
  ```
- **timi-proxy-cli 已安装**：`LocalProxyServer`、`StableRelay`、`ProxyWatchdog` 可 import
- **pi 已安装**：`pi` 在 PATH 中；Pi Extension API 可用

### 2.2 性能指标

| 指标 | 要求 |
|------|------|
| 新任务检测延迟 | mw serve（launcher.py）轮询间隔 ≤ 5 秒 |
| status 更新延迟 | worker 退出后 3 秒内完成 _workers.parallel status 更新 |
| pm-orchestrator 轮询间隔 | ≤ 5 秒（侦测 _workers.parallel status=done/failed） |
| 并发 worker 数 | 无硬性上限，`--max-workers` 可调 |

### 2.3 安全约束

- API key 通过环境变量传递，不写入任何文件
- launcher.py 使用列表形式传参给 subprocess（禁止 `shell=True`）
- task.md / output.md 只写入 `.agenticdoc/` 目录

### 2.4 集成依赖

| 依赖 | 版本约束 | 集成方式 |
|------|---------|---------|
| timi-proxy-cli | 已在用版本 | import LocalProxyServer / StableRelay |
| AgenticTask | 已安装版本 | 文件格式参考（`_index.parallel` 格式兼容）；mw init 时同步 .claude/；pm-orchestrator.ts 不调用其 Python 脚本 |
| Pi Extension API | Node.js ≥ 18 | pm-orchestrator.ts / worker-mode.ts 宿主；自动发现 `.pi/extensions/` |
| codex CLI | 最新版 | subprocess spawn，OPENAI_BASE_URL 已确认支持 |
| claude CLI | 已安装版本 | subprocess spawn，ANTHROPIC_BASE_URL 注入 |
| goal.md | 项目级文件 | pm-orchestrator.ts goal elicitation 产出；worker 在检查点读取 |
| `_workers.parallel` | 项目级文件 | task-dispatcher.ts 写（PM 派发）；launcher.py 读写（spawn + status 更新）；与 AgenticTask `_index.parallel` 格式独立 |

---

## §3 验收标准（AC）

> 🔒 AC-001~031 locked 2026-08-10；AC-032~036 locked 2026-08-11，编号永不回收

| AC 编号 | 描述 |
|---------|------|
| AC-001 | 在 `_workers.parallel` 新增一条 `Status=pending, Cli=<任意>` 的行后，`mw serve`（launcher.py）在 5 秒内检测到并进入 spawn 流程（`--poll-interval` 默认值 ≤ 5 秒） |
| AC-002 | 在 `mw serve` 检测到 `Cli=pi`（无 `Provider` 或 `Provider=claude`）的 pending task 时，spawn 的进程环境变量包含 `ANTHROPIC_BASE_URL=http://localhost:{pi-port}` 且 `PI_WORKER_TASK=<task.md 绝对路径>` |
| AC-003 | 在 `mw serve` 检测到 `Cli=codex` 的 pending task 时，spawn 的进程环境变量包含 `OPENAI_BASE_URL=http://localhost:{codex-port}` 且 `OPENAI_API_KEY=<config.api_key>` |
| AC-004 | 在 `mw serve` 检测到 `Cli=claude` 的 pending task 时，spawn 的进程环境变量包含 `ANTHROPIC_BASE_URL=http://localhost:{claude-port}` 且 `ANTHROPIC_AUTH_TOKEN=<config.api_key>` |
| AC-005 | 在 worker 进程以 exit code 0 退出时，`mw serve` 在进程退出后 3 秒内将 `_workers.parallel` 中该行 Status 更新为 `done` |
| AC-006 | 在 worker 进程以 exit code 1 退出时，`_workers.parallel` 该行 Status 更新为 `failed`；exit code 2 时更新为 `needs-clarification`；exit code 130 时更新为 `failed`；其他 exit code 兜底为 `failed` |
| AC-007 | 在 `mw serve --max-workers N` 运行且已有 N 个活跃 worker 时，新发现的 pending task 进入等待队列不立即 spawn，直到有 worker 退出后才 spawn 队列中的下一个 |
| AC-008 | 在同一 task 的 worker 已在 `running_procs` 中时，`mw serve` 对该 task 不 spawn 第 2 个 worker 进程 |
| AC-009 | 在 `mw serve --dry-run` 执行时，stdout 输出所有 `_workers.parallel` 中 pending task 对应的 CLI 命令和 task.md 路径，exit code 0，不创建任何子进程 |
| AC-010 | 在 `PI_WORKER_TASK=<task.md路径>` 环境变量存在时，pi 启动时 `worker-mode.ts` 读取 task.md，调用 `pi.setActiveTools(allowlist)` 将 `task.type` 对应的工具列表设为激活，allowlist 外的工具不出现在工具列表中 |
| AC-011 | 在 pi worker `agent_settled` 事件触发（任务执行完毕，无更多 retry）后，`<task-key>/output.md` 存在且包含 `Summary`、`Changed Files`、`Verification Steps`、`Exit Reason` 四节，文件大小 > 50 bytes，随后 `process.exit(0)` |
| AC-012 | 在 pi worker 运行期间产生至少一次工具调用时，`evidence/runs/<key>/trace.log` 包含至少一行以 `[FLOW]` 开头的记录 |
| AC-013 | 在 `proxy_multi.py --pi-port 7001 --codex-port 7002 --claude-port 7003` 启动后，Windows `netstat -an` 输出中三个端口均显示 `LISTENING` 状态 |
| AC-014 | 在 `dispatch-table.md` 更新后，`grep -c "| pi |"` 输出 ≥ 2，`grep -c "| codex |"` 输出 ≥ 1，`grep -c "| claude |"` 输出 ≥ 2 |
| AC-015 | 在 Windows 含空格或反斜杠的路径作为 task.md 路径时，`mw serve` spawn 的进程能正确读取该文件（`pathlib.Path` 处理，不依赖路径分隔符类型） |
| AC-016 | 在 task.md 包含 `phases:` 字段（列表非空）时，worker 每完成一个 phase 后在 `<key>/progress/phase-<N>.md` 写入阶段摘要（N 为 1-indexed），且该文件大小 > 20 bytes |
| AC-017 | 在 worker 写入 `progress/phase-<N>.md` 后、下一 phase 启动前，worker 读取 `.agenticdoc/goal.md`，并在 `trace.log` 写入至少一行 `[GOAL_CHECK] phase=<N> goal_mtime=<timestamp>` 格式的记录 |
| AC-018 | 在 worker 执行期间 `goal.md` 被修订（mtime 变化）时，worker 在下一个 `[GOAL_CHECK]` 节点读取到修订后的内容（`trace.log` 中该节点的 `goal_mtime` 与修订后文件的 mtime 一致） |
| AC-019 | 在 task.md 不含 `phases:` 字段或字段为空时，worker 跳过所有 Goal-Anchored 检查点，不创建 `progress/` 目录，以单阶段模式完成任务后写 output.md |
| AC-020 | 在执行 `python mw.py init <project-dir>` 时：（1）目录结构创建成功（`.agenticdoc/_index.md` 存在）；（2）`<project-dir>/.pi/extensions/` 目录创建，`agent-team-loop.js` 从 `dist/extensions/` 复制到该目录；（3）exit code 0 |
| AC-021 | 在 `pi`（cwd 为 `<project-dir>`）启动且 `.agenticdoc/goal.md` 不存在时，pm-orchestrator.ts 以 goal elicitation 模式启动对话，产出 `goal.md` 包含 `## Goal`、`## Context`、`## Key Constraints` 三节且各节内容非空 |
| AC-022 | 在 `mw init --sync-agentictask <source-dir>` 传入时，AgenticTask 框架从 `<source-dir>` 同步到 `<project-dir>/.claude/`，同步后 `<project-dir>/.claude/scripts/update_index.py` 存在；目标项目中已有且不在源目录的文件不被删除 |
| AC-023 | 在 `mw serve --project <project-dir>` 运行时，所有文件路径（task.md、output.md、goal.md、`_workers.parallel`）均相对于 `<project-dir>/.agenticdoc/` 解析；`--dry-run` 输出的 task.md 路径以 `<project-dir>\.agenticdoc\` 为绝对路径前缀 |
| AC-024 | 在 task.md 包含 `Provider: <name>` 字段（如 `deepseek`）时，`mw serve` 从 `providers.json` 查找对应端口和 env var 名称，spawn pi worker 时注入正确的 base URL 和 API key env var（不使用 ANTHROPIC_BASE_URL） |
| AC-025 | 在 `mw serve --dry-run` 且 task.md 含 `Provider: deepseek` 时，stdout 输出的 env var 列表中包含 `DEEPSEEK_BASE_URL`，不包含 `ANTHROPIC_BASE_URL` |
| AC-026 | 在 pi 以 `PI_WORKER_TASK` 未设方式启动时，Extension `activate()` 加载 PM mode handler；以 `PI_WORKER_TASK` 已设方式启动时，加载 Worker mode handler；两者互斥，均为**顶层 import**（不使用动态 `await import()`） |
| AC-027 | 在 pm-orchestrator.ts 写入 `_index.parallel` 后，文件格式与 AgenticTask 规范兼容（管道分隔，列顺序：Key \| Status \| Phase \| ClaimId \| Deps \| Desc \| Updated），`python update_index.py list` 能无错读取 |
| AC-028 | 在 pi PM 模式下输入 `/pm-key new <name>`、`/pm-key switch <name>`、`/pm-key list` 时，pm-orchestrator.ts 分别执行对应操作并在 pi TUI 输出结果（无需退出 pi 进程） |
| AC-029 | 在两个进程并发写入 `_workers.parallel`（分别操作**不同** task key）时：（1）文件无半写行；（2）两个 key 的行均存在于最终文件中（无更新丢失）。写操作须先获取 `.mw/workers.lock` 文件锁，再执行 read-modify-rename |
| AC-030 | 在 pm-orchestrator.ts 轮询检测到 `_workers.parallel` 中 task Status=done 时，读取 `<key>/output.md` 并在 pi TUI 展示 Summary 节内容（非空） |
| AC-031 | 在 pm-orchestrator.ts 的 `StateManager.write()` 被传入非法 Phase 值（如 `"UNKNOWN"`）时，函数抛出 Error 且 pm-state.md 内容不变（TypeScript 类型约束 + 运行时枚举校验） |
| AC-032 | `_workers.parallel` 格式为 7 列管道分隔：`Task-Key \| Status \| Cli \| Provider \| TaskPath \| DispatchedAt \| UpdatedAt`；Status 值域：`pending / running / done / failed / needs-clarification`；与 AgenticTask `_index.parallel` 为独立文件，不共用 |
| AC-033 | 在 pi worker 以 exit code 1 退出时，`<task-key>/output.md` 存在且包含 `Exit Reason` 节（说明失败原因，内容非空）；以 exit code 2 退出时，output.md 存在且包含 `Questions` 节（替代 Verification Steps）；以 exit code 130 退出时，output.md 存在（各节可部分填充） |
| AC-034 | `mw serve` 启动后将 PID 写入 `<project-dir>/.mw/mw.pid`；第二个 `mw serve` 实例检测到 PID 文件且进程仍存活时，输出错误信息（含 PID）并 exit 1；进程退出时自动清理 PID 文件 |
| AC-035 | `pi` 进程退出（正常或异常）后，`mw serve` 及其管理的 worker 子进程继续运行，直到当前 task 完成并将 `_workers.parallel` 中该行 Status 更新为 done/failed/needs-clarification |
| AC-036 | `mw init <project-dir>` 执行后 `<project-dir>/.pi/extensions/agent-team-loop.js` 文件存在（从 Multi-Workers `dist/extensions/` 复制）；若 `mw.py` 所在目录的 `dist/extensions/agent-team-loop.js` 不存在，`mw init` exit 1 并输出明确错误信息，不创建不完整的项目目录 |

---

## §4 风险与未决项

| 类型 | 描述 | 处置 |
|------|------|------|
| 风险 | timi-proxy-cli `LocalProxyServer` 多实例共享上游连接时可能出现竞争 | proxy_multi.py 实现时加压测，三端口并发 10 请求验证 |
| 风险 | Pi Extension `agent_settled` 事件时序在某些工具并发场景下可能延迟触发 | smoke test 加超时断言，超时后强制 exit(1) |
| 风险 | Windows 路径含中文或特殊字符时 pathlib.Path 可能行为不一致 | smoke_test.sh 使用含空格的路径作为测试用例 |
| 风险 | `mw init --sync-agentictask` 同步时可能覆盖目标项目用户已自定义的文件 | sync 只更新源中存在的文件，保留目标中独有的文件；实现前验证 install.py 当前的覆盖行为 |
| 风险 | _workers.parallel 的 `.mw/workers.lock` 跨 Python/Node 文件锁在 Windows 上行为可能不一致 | MVP 用独占文件创建（O_CREAT | O_EXCL）实现，smoke test 验证并发写无丢失 |
| 风险 | path.resolve + startsWith 不能可靠地检测 Windows 路径包含关系（junction/symlink；C:\foo2 误匹配 C:\foo） | 使用 path.relative + !startsWith('..') 做 containment 检查 |
| 待确认 | claude CLI 的确切 env var 名称（`ANTHROPIC_AUTH_TOKEN` vs `ANTHROPIC_API_KEY`） | T-05 实现前 `claude --help` 验证 |
| 待确认 | Pi Extension API 中 `.pi/extensions/` 自动发现机制是否已实现 | system-design 阶段已确认需要查 Pi Extension API 文档 |

---

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

项目首个 key，`_arch_snapshot.md` 为空，无历史资产可复用。

### 需规避坑点

项目首个 key，`_pitfalls.md` 为空，无历史坑点记录。
