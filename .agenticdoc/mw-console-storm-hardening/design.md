# Design: mw-console-storm-hardening

> Key: mw-console-storm-hardening · date: 2026-10-15 · status: draft
> 输入: spec.md (AC-001..010) + evidence/research/ 三份 design note（RQ-1 PM 直执 / RQ-2 / RQ-3）

## §0 架构总览

四层交付，Python 侧两个新模块 + 一处 mw.py 修复，TS 侧 agent-team-loop 一个入口，共享文件仅 `mw.py` 与 `packages/multi-workers` 下的测试清单：

```
L0  mw.py cmd_start 除雷          —— serve 树获得隐藏控制台，继承兜底全部后代
L1  console_run.py + mw run-detached —— 后台命令唯一入口（flag 契约 + heartbeat/marker）
L2  mw_console_guard/ (sitecustomize) —— runner 注入，测试面裸 spawn 结构性禁窗
L3  守卫测试 + 文档 checklist      —— DETACHED_PROCESS 防回潮
TS  mw_run_detached 工具 + /mw run-detached —— 共用 runDetachedMw()，仅 shell 角色
```

## §1 机制前提（全部实证，出处见 evidence）

| # | 事实 | 出处 |
|---|------|------|
| M1 | 无控制台父 + `CREATE_NO_WINDOW\|NEW_GROUP` → 子得**隐藏控制台**（`GetConsoleProcessList>0`、`GetConsoleWindow=0`——后者不能区分隐藏/无，**conlist 计数是唯一判据**），孙代 `flags=0` 继承，0 弹窗 | RQ-1 E1 |
| M2 | DETACHED + 裸 spawn → 每子进程一个 WT 可见窗口（10/10 复现，owner=WindowsTerminal.exe） | RQ-1 E2 |
| M3 | `DETACHED\|NO_WINDOW` 组合下 NO_WINDOW 被忽略（conlist=0），孙代各自弹窗（~8/10 采样） | RQ-1 E3 |
| M4 | PYTHONPATH 前置 sitecustomize 在 `python -c` 与 `python -X utf8 -m pytest` 链上稳定加载；venv 同名冲突时 PYTHONPATH 胜出；`-S` 跳过（记录为已知限制） | RQ-3 Q1 |
| M5 | patch `subprocess.Popen.__init__` 一处覆盖 `run()`/`Popen()`；`creationflags=0` 补 OR、显式 `CREATE_NEW_CONSOLE/DETACHED_PROCESS` 不动、kwargs 透传完整、幂等 | RQ-3 Q2 |
| M6 | env 开关 `MW_CONSOLE_GUARD=1` 激活、未激活 import 零副作用、fail-open（恢复原 Popen + 单行 stderr 告警） | RQ-3 Q3 |
| M7 | guard 端到端：事故复现 off=弹窗/on=严格 0 ×2 轮；sitecustomize 在 DETACHED 子树内确认加载 | RQ-3 Q4 |
| M8 | TS 双激活路径注册先例（`registerRagTools`: pm-orchestrator.ts:1769 + worker-mode.ts:2773）；esbuild 入口图自动收编（mw.py:4642/4662），仅 `mw build` | RQ-2 D3/D4 |

## §2 设计决策

### D-001 L0：cmd_start 除雷（AC-001）

`mw.py cmd_start`（现 :506）：`creationflags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`（**去 DETACHED_PROCESS**），并新增 stdout/stderr 重定向到 `.mw/serve-console.log`（追加模式；现 DETACHED 下输出凭空消失，是既有观测盲点）。机制依据 M1：serve 获隐藏控制台 → conductor/proxy/launcher/worker 及一切后代继承兜底（结构性，不再依赖每站点记得打 flag）。现有已正确的站点（mw.py:231/376/393/4441、launcher.py:2007、mw_common.py:1580）**不改**。
posix 分支不变（`start_new_session=True`）。

### D-002 L1：console_run.py 两层结构（AC-003/004）

```
mw run-detached [--cwd D] [--run-dir D] [--timeout-min N] [--heartbeat-s S] -- <cmd...>
  └─ 前台 CLI 进程：校验参数 → Popen(监督进程, CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP) → 立即返回
      监督进程（内部子命令 _run_supervisor，隐藏控制台，用户 bash 不阻塞）
        └─ Popen(用户命令, flags=0) → 继承监督进程的隐藏控制台（M1）
            职责：写 heartbeat.json（默认 5s，atomic replace）→ 等待退出 → 写 marker.json → 超时(默认无)→ taskkill /T / 前缀 kill
```

- **新模块** `packages/multi-workers/console_run.py`：`build_parser()`（argparse，挂到 mw.py 主 parser）+ `cmd_run_detached(args)` + `run_supervisor(args)`（监督逻辑，可单测的纯函数面：`_write_marker`/`_beat` seam 注入）。
- **run_dir 文件集**（沿用 mw-ue-toolchain 惯例，mw.py:1118-1132）：`cmd.txt`（原样 argv）、`run.log`（stdout+stderr 合流）、`heartbeat.json` `{schema:"mw-heartbeat/1", pid, ts_ms}`、`marker.json` `{schema:"mw-run/1", rc, timed_out, started_at_ms, ended_at_ms, wall_sec, pid, argv}`。默认 run_dir：`<cwd>/.mw/runs/run-<YYYYMMDD-HHMMSS>/`。
- rc 哨兵：timeout 致死 `rc=124`（对齐 advance.py 的 timeout 语义）、spawn 失败 `rc=127`（marker 标 `spawn_failed=true`）。
- CLI stdout（≤4 行，调用方可解析）：`[mw run-detached] pid=<supervisor_pid>`、`marker=<path>`、`heartbeat=<path>`、`log=<path>`。
- guard 注入（D-004）默认开启：监督进程给用户命令的 env 追加 `MW_CONSOLE_GUARD=1` + `PYTHONPATH` 前置 guard 目录（os.pathsep）；`MW_CONSOLE_GUARD=0` 显式退出。
- posix：`start_new_session=True`、无 creationflags、不注入 guard（M4/M6 的 no-op 语义本就保证，但显式跳过省一次 PYTHONPATH 污染）。

### D-003 L2：mw_console_guard/ 包（AC-005/006/007）

**新目录** `packages/multi-workers/mw_console_guard/`（PYTHONPATH 直指该目录）：
- `sitecustomize.py`：3 行激活器 `import mw_console_guard`（site 启动钩子，M4）。
- `mw_console_guard.py`：RQ-3 产出的 58 行骨架为**实现基线**（证据文件含全文），保留 `_patched` 幂等标志、env 判据、fail-open、POSIX no-op。
- 硬化点（design 补充）：patched 签名为 `(*args, creationflags=0, **kwargs)`——**creationflags 位置传参不受保护**（13 个位置参数的调用形态全仓 grep 为 0，风险记录于 docstring + 守卫测试注释，不做签名镜像的过度工程）。
- runner 解析 guard 目录：`pathlib.Path(__file__).resolve().parent / "mw_console_guard"`，存在性校验 fail-open（缺目录仅 stderr 告警，不阻塞命令）。

### D-004 L3：守卫测试 + 文档（AC-002/009）

- **新测试** `packages/multi-workers/test_console_storm_guard.py`：
  1. 全仓非测试 .py **剥注释与 docstring 后**（stdlib tokenize）grep `DETACHED_PROCESS` = 0（防回潮守卫）；`mw_console_guard/` 子包豁免——其引用 DETACHED_PROCESS 是 AC-005 合同性代码（显式 flag 比较掩码，自身不 spawn），入 scan 会误红（W-04b 实施决策，2026-10-15）；
  2. cmd_start flags 集合断言（monkeypatch Popen 捕获 kwargs）+ serve-console.log 重定向断言；
  3. run-detached 集成：真实短命令（`cmd /c exit` / `true`）跑监督全链，断言 marker rc 一致、heartbeat 更新、win32 flags 契约（Popen 捕获）；
  4. guard 单测：激活/未激活/显式 flag 不动/fail-open/幂等（从 RQ-3 探针移植，platform seam 沿用 `_probe_spawn_kwargs(platform=...)` 模式）。
- **文档**：`packages/multi-workers/README.md` 新节「Windows detached-run checklist」：三事实（互斥、DETACHED 静默胜出、后代外溢）+ M1 判据（conlist）+ `mw run-detached` 用法；`UPDATE.md` 指令矩阵补一行。

### D-005 TS 入口（AC-008，依据 RQ-2 D1-D4）

- `packages/coding-agent/src/extensions/agent-team-loop/shared/run-detached.ts`：`runDetachedMw()` 共用内部函数（spawn `python mw.py run-detached ...`，解析 4 行 stdout 返回 `{pid, marker, heartbeat, log}`）。
- 注册**双激活路径**（M8 先例）：pm-orchestrator.ts PM 激活处 + worker-mode.ts 激活处，注册工具 `mw_run_detached`（typebox schema：`cmd:string[] / cwd? / run_dir? / timeout_min? / heartbeat_s?`，additionalProperties:false；结果 content 文本 + `details{pid, marker, log}`）。
- worker 可见性走 `activeToolsForType`（worker-mode.ts:167-170），**仅 shell 角色激活**；**不进** `TOOL_ALLOWLISTS`（T-17 parity 锁：该表锁 dispatch.py，加列会破坏 py/ts parity）。read-only 角色不给 spawn 面（守 GC-2 边界 + 不绕 AC-005b）。
- `/mw run-detached` 子命令：ui-bridge.ts 现有 `/mw` 命令的薄扩展（同 `/worker` 共用 `planDispatchFrontmatter` 的先例形态），人/PM 手动入口，与工具共用 `runDetachedMw()`。
- 构建：仅 `mw build`（esbuild 入口图自动收编，D4）；不碰 pi 核心（GC-2）。

### D-006 spawn 站点审计表（AC-002 证据面）

以 spec-spawn-site-survey-20261015.md 的普查为基线，design 交付物 = 该表加 L0 后归属列（**显式 flag / 隐藏控制台继承 / 前台-only**），落 design 同目录 `design-spawn-site-audit-20261015.md`；守卫测试引用其文件名做存在性断言。L0 后归属推演：serve 隐藏控制台 → 全部直接子进程继承兜底（M1），原有显式 flag 站点维持双保险。

## §3 并行性与任务切分（plan 输入）

| 工作束 | 写面 | 依赖 |
|--------|------|------|
| W1: L0 + console_run.py + mw.py 挂接 + 对应测试 | `mw.py`、`console_run.py`(新)、`test_console_storm_guard.py`(新) | 无（D-001/D-002 契约已冻结） |
| W2: guard 包 + guard 单测 | `mw_console_guard/`(新) + 测试段 | 无（D-003 契约已冻结） |
| W3: TS 入口 | `agent-team-loop/shared/run-detached.ts`(新) + 两激活点 + ui-bridge `/mw` + suite 测试 | 无（D-005 契约已冻结；不依赖 W1/W2 落盘） |
| W4: 审计表 + 文档 + 全量 verify | docs + evidence | W1-W3 终态后串行 |

W1 内部 mw.py 是串行面（L0 与 CLI 挂接同 owner）。W2 的测试段并入 W1 的 `test_console_storm_guard.py` 会有同文件冲突 → **W2 的 guard 单测独立文件** `test_mw_console_guard.py`。

## §4 风险与回退

- M4 已证 pytest 链加载 sitecustomize，但极端环境（`-S` / 嵌入式解释器）会跳过——guard 是兜底不是唯一防线（L0/L1 的 flag 契约独立成立），文档明示。
- guard 对 `creationflags` 位置传参不保护（D-003，全仓无此形态）。
- serve 获隐藏控制台后 stdin 不可读——serve 不读 stdin（现状审计），verify 覆盖 start/stop 全链路。
- TS 工具仅 shell 角色可见——PM 需要时 bash 直调 `python mw.py run-detached`（同一 CLI），不产生第二实现面。

## §5 VC 映射

| VC | 断言 | AC |
|----|------|----|
| VC-001 | cmd_start flags={NO_WINDOW,NEW_GROUP} 且无 DETACHED + serve-console.log 重定向 | AC-001 |
| VC-002 | 非测试 .py grep DETACHED=0 + 审计表存在 | AC-002 |
| VC-003 | run-detached win32 flags 契约 + marker rc/时间戳契约 | AC-003 |
| VC-004 | heartbeat 间隔更新 + timeout rc=124 + timed_out=true | AC-004 |
| VC-005 | guard OR 语义 + 显式 flag 不动 | AC-005 |
| VC-006 | 未激活零改写 | AC-006 |
| VC-007 | posix 分支 start_new_session、guard no-op | AC-007 |
| VC-008 | 双激活路径工具注册 + 参数透传 + shell-role 门控 | AC-008 |
| VC-009 | README checklist 三事实 + run-detached 用法 | AC-009 |
| VC-010 | 既有套件零新增失败（对照基线） | AC-010 |
