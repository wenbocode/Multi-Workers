# Spec: mw-console-storm-hardening

> Key: mw-console-storm-hardening
> 创建时间: 2026-10-15T15:30:00+08:00
> 状态: draft

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本 spec 服务于 goal「mw 后台服务（Python）：LLM 代理 + 任务调度器，常驻运行」的可靠性维度——Windows 常驻服务及其编排的后台命令（evidence 收口、全量测试）必须对用户桌面零干扰；agent-team-loop 扩展的 worker 编排入口同步受益。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-2: 不修改 pi 核心——TS 侧暴露仅通过 agent-team-loop 扩展 API（工具/命令注册）。
  - GC-3: Worker 进程级隔离——runner 管理的是单棵子进程树，不引入跨 worker 的共享进程状态。
  - GC-4: 不引入中心化调度器——runner 是无状态工具（heartbeat/marker 落盘由调用方约定路径），不是新调度组件。
- 冲突：无。
- 预期收益（可观察、可验证）：
  1. `mw start` 启动的 serve 树在 Win11 默认终端下运行全程零可见终端窗口（判定：EnumWindows 差分观测 = 0，见 AC-001 verify 任务）。
  2. 框架代码库中 `DETACHED_PROCESS` 出现次数 = 0（判定：守卫测试 0 命中，见 AC-002）。
  3. 项目侧后台/evidence 编排有唯一标准入口，事后可凭 marker 判定 rc/时长（判定：AC-003/004）。
  4. 测试套件裸 spawn `git`/`cmd` 不再弹窗（判定：AC-005 复现脚本对照）。

## §1 功能概述

### 1.1 目标

消除 Multi-Workers 框架在 Windows 上的"控制台窗口风暴"类故障（输入：`H:\MWWorkeSpace\fix\.agenticdoc\incidents\20261015-console-window-storm.md`，调研：`evidence/research/spec-incident-console-storm-20261015.md`）：

- **L0 框架自身除雷**：`mw start` 的 spawn 去除 `DETACHED_PROCESS`（调研：`evidence/research/spec-spawn-site-survey-20261015.md`）——serve 树从"无控制台（每代 spawn 都必须显式打 flag）"变为"隐藏控制台（继承自动兜底全部后代）"，并把 serve stdio 重定向到 serve log。
- **L1 标准 detached-runner**：新模块 + `mw run-detached` CLI 子命令，作为"后台跑证据命令"的唯一入口：win32 固定 `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`（硬禁止 DETACHED_PROCESS），posix 走 `start_new_session`；落盘 heartbeat 与 done marker。
- **L2 子树 console guard**：随框架发布 sitecustomize 风格 guard 模块；runner 以 env 开关（`MW_CONSOLE_GUARD=1` + PYTHONPATH 前置 guard 目录）注入，win32 上给 `subprocess.Popen/run` 在调用方未指定 console 语义（`creationflags=0`）时 OR 上 `CREATE_NO_WINDOW`；显式指定 `CREATE_NEW_CONSOLE`/`DETACHED_PROCESS` 的调用不被改写；env 未设时零行为差异。
- **L3 文档 + 守卫测试**：Win32 detached-run checklist（互斥语义三事实）；守卫测试禁止框架非测试代码出现 `DETACHED_PROCESS`，防回潮。
- **TS 暴露**：agent-team-loop 扩展提供入口（经 GC-2 的扩展 API），PM/Worker 无需手拼 Python 命令即可派发 run-detached。

### 1.2 技术栈 / 语言

- Python 3.10+（`packages/multi-workers/`：mw.py、新 runner 模块、新 guard 模块、pytest 测试）
- TypeScript（`packages/coding-agent/src/extensions/agent-team-loop/`：仅入口暴露层，构建走现有 esbuild bundle 流程）
- 平台：Windows 10/11（conhost 与 Windows Terminal 两种委托）为主；POSIX 兼容分支（runner `start_new_session`、guard no-op）

### 1.3 核心用户场景

1. 场景 A（框架常驻）：用户在 Win11（默认终端 = WT）执行 `python mw.py start --project .`，serve/conductor/proxy/launcher/worker 全树常驻——运行全程桌面零弹窗，即使未来某 spawn 站点漏加 flag。
2. 场景 B（项目侧后台编排）：PM/Worker 需要后台跑长命令（如全量 pytest、UE 构建收口），通过 `mw run-detached`（或 TS 入口）派发——命令树零弹窗，stdout 落 log，结束后 marker JSON（rc/wall_sec）落盘，PM 轮询 marker 判定完成。
3. 场景 C（测试面兜底）：场景 B 的命令是会裸 spawn `git`/`cmd` 的 pytest 套件——runner 注入 guard 后，套件内 `creationflags=0` 的子进程不再弹窗（事故风暴链的测试层被结构性封死）。
4. 场景 D（防回潮）：开发者新写 spawn 站点时，守卫测试在 CI 拦截 `DETACHED_PROCESS`；文档 checklist 说明互斥语义供评审引用。

### 1.4 范围说明（不做什么）

- 不包含：FeatureMigrator 项目侧修复（事故 §8-A，移交该项目）；其 8 个 failed 用例 triage（事故 §9 移交）。
- 不修改用户机器默认终端委托注册表（事故 §8-C）。
- 不在每个测试文件散改 `creationflags`（事故 §8-C，收敛在 guard 一处）。
- 不重构 launcher/serve 现有已正确的 flag 用法（worker spawn、`_git`、conductor/proxy spawn 保持原样）。
- 不修改 pi 核心（GC-2）；不引入新调度组件（GC-4）。
- 不改变 `mw start` 的对外 CLI 语义（参数、输出格式除新增提示行外不变）。

## §2 业务约束

### 2.1 平台 / 环境

- 主平台 Windows 10/11；`cmd_start`、runner、guard 的 win32 分支为本 key 核心；POSIX 分支保持等价语义（`start_new_session=True`，无 creationflags）且不回归。
- Python 兼容面与 `packages/multi-workers` 现状一致（erasable 语法规则不适用 Python；TS 侧遵循根配置 strip-only 约束）。

### 2.2 性能指标

- runner heartbeat 写文件开销可忽略（默认间隔 ≥5s，仅 stat/写小 JSON）；marker 落盘为一次性。
- guard 激活时不改变子进程 stdio/句柄继承行为，对套件耗时无可测影响（<1%）。

### 2.3 安全约束

- guard 仅通过子树 env（PYTHONPATH 前置 + `MW_CONSOLE_GUARD=1`）作用于 runner 的后代进程，不改用户全局 site-packages、不写机器级配置。
- runner 不触碰凭证面（复用调用方 env，不新增读取 auth.json 等行为）。
- guard 不得改写显式指定 console 语义的调用（`CREATE_NEW_CONSOLE`/`DETACHED_PROCESS` 原样保留）。

### 2.4 集成依赖

- `mw.py` CLI 子命令注册（与现有子命令风格一致）。
- agent-team-loop 扩展入口（GC-2：扩展 API，dist bundle 现有构建流程）。
- evidence 落盘惯例与 `mw-ue-toolchain` 的 run_dir 风格（cmd/log/exit 同目录）保持一致（可复用资产，见 §5）。

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-10-15T15:30:00+08:00，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 win32 下，`mw.py cmd_start` 构造的 Popen `creationflags` 集合恰为 {CREATE_NO_WINDOW, CREATE_NEW_PROCESS_GROUP} 且不含 DETACHED_PROCESS；serve 的 stdout/stderr 重定向到 serve log 文件（单测断言 + verify 阶段 EnumWindows 差分实测 60s 零新可见窗口） |
| AC-002 | 在 packages/multi-workers 全部非测试 .py 文件中 grep `DETACHED_PROCESS` 命中数 = 0，且该断言由常驻守卫测试执行（CI 防回潮）；serve 树可达 spawn 站点审计表落盘于 design/evidence 且每站点标注 flag 归属（显式 flag / 继承覆盖） |
| AC-003 | 在 win32 下，`python mw.py run-detached -- <cmd...>` 派发的子进程 creationflags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP；命令结束后 marker JSON 落盘，`rc` 字段与子进程真实退出码一致，且含 `started_at`/`ended_at`/`wall_sec` 字段（单测断言 flag 与 marker 契约） |
| AC-004 | 在 runner 运行期（≥2 个心跳间隔）内，heartbeat 文件 mtime 按配置间隔（默认 5s）持续更新；子进程被 timeout 终止时 marker `timed_out=true` 且 `rc` 为超时哨兵值 124（单测，seam 注入短超时） |
| AC-005 | 在 win32 且 guard 激活（MW_CONSOLE_GUARD=1 + PYTHONPATH 前置）下，guard 模块对 `subprocess.Popen/run` 的包装使 `creationflags=0` 的调用被 OR 上 CREATE_NO_WINDOW；显式 `CREATE_NEW_CONSOLE` 调用的 flags 不变（单测以观测入参方式断言；verify 阶段用事故 §7.1 最小复现脚本对照实测：激活时零窗口） |
| AC-006 | 在未设置 MW_CONSOLE_GUARD 的干净 Python 进程中，subprocess.Popen/run 行为与上游完全一致（guard 模块不被加载或加载后零改写，单测断言） |
| AC-007 | 在 POSIX 分支下，run-detached 使用 `start_new_session=True` 且不传 creationflags；guard 在非 win32 平台为 no-op（单测，platform seam 注入） |
| AC-008 | 在 agent-team-loop 扩展中存在 run-detached 入口（经扩展 API 注册的工具或命令），PM/Worker 会话内可发起后台命令派发并获知 marker/log 路径约定；该入口在 win32 生成的调用满足 AC-003 的 flag 契约（suite 测试以 faux provider 断言入口存在与参数透传，不触真 CLI） |
| AC-009 | 框架文档（packages/multi-workers 下 README 或 docs/）含 Win32 detached-run checklist，明确三事实：DETACHED_PROCESS×CREATE_NO_WINDOW 互斥、组合时 DETACHED 静默生效、后代进程窗口外溢 |
| AC-010 | 在完成 L0-L3 改动后，packages/multi-workers 既有 pytest 套件相对基线零新增失败（对照运行记录留盘） |

## §4 风险与未决项

- 风险 RQ-1（待实证）：`CREATE_NO_WINDOW` 在"父进程无控制台"场景下是否如预期给子进程分配**隐藏**控制台、且被孙代继承——事故 §7.1 给出对照修复版结论，但需本机最小复现实证（design 阶段 research 任务）。
- 风险：guard 的 sitecustomize 注入与 pytest/virtualenv 的加载顺序兼容性——须幂等且 fail-open（guard 异常不得弄崩宿主进程）；design 阶段定注入细节。
- 风险：serve 获得隐藏控制台后 stdin 语义变化——serve 不读 stdin，预期无影响，verify 覆盖 `mw start` + `mw stop` 全链路。
- 风险：TS 入口与 pi Extension API 边界——design 阶段对照 pi 扩展文档确定工具 vs 命令形态，不改核心（GC-2）。
- 待确认：无（三项关键决策用户已确认：key 开本仓库；guard 用 sitecustomize 方案；TS 侧要暴露）。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- `launcher.py` `_spawn`（:2007）与 `mw.py` `_git`（:4441）、`_probe_spawn_kwargs`（mw_common.py:1572）——win32 CREATE_NO_WINDOW 隔离的既有先例与测试 seam 模式（mw-console-title-clobber key 产出，test_common.py:740 有 AC 验证范式）。
- `mw-ue-toolchain` 的 run_dir evidence 惯例（cmd.txt / run.log / exit.txt 同目录落盘）——runner 的 marker/log 目录结构直接沿用。
- `mw-worker-tree-kill` 的进程组终止经验（taskkill /T、kill(-pgid)）——runner 的 timeout 终止路径复用同思路。
- guard 的"env 开关 + 可注入 seam"测试模式：`_probe_spawn_kwargs(platform=...)` 已示范 platform seam 写法。

### 需规避坑点

- P-001（PowerShell 管道破坏 BOM UTF-8）：本 key 所有 `.agenticdoc`/代码文件写入一律用 write 工具或 Python 显式 `encoding="utf-8"`，禁止 PS 读-改-写管线。
- P-003（`open(p,"w")` 截断后求值）：runner/guard 写 marker/heartbeat 用 `Path.write_text(..., encoding="utf-8")` 或临时文件 + `os.replace` 原子替换。
- 事故 §8-C（不推荐项）：不改注册表、不散改测试文件——已列入 §1.4 范围排除。
