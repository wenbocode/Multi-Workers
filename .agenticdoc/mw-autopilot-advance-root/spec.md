# Spec: mw-autopilot-advance-root（autopilot phase-advance 通道跨项目根定位修复）

> Key: mw-autopilot-advance-root
> 创建时间: 2026-09-22
> 状态: locked

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（已确立，非 draft）

- 对齐：goal 的核心交付之一是「mw 后台服务（Python）：LLM 代理 + 任务调度器，常驻运行」，以及「一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目」。autopilot conductor 的 phase-advance 通道是无人值守推进的唯一执行路径；本 key 修的是该通道在「framework 装在项目之外」（mw 仓库一份 clone + 各项目内一份副本）时整体不可用——conductor 每 tick `advance exit=1`，并把 `mkdir` 落到错误项目（mw 仓库自己的 `.agenticdoc`）。修复后 conductor 能在目标项目（E2Feature 等）真正推进 key phase，PM 不必常驻当 manual bridge。
- 继承约束（GC 编号）：
  - GC-1: 不修改 pi 核心——改动限于 AgenticTask framework skill（跨仓 `wenbocode/AgenticTask`）+ `packages/multi-workers/autopilot/advance.py` + agent-team-loop 扩展内既有脚本运行器（`agent-scripts.ts`），走既有接口，不 fork pi。
  - GC-2: 文件驱动协调——root 判定仍以文件系统事实（`.agenticdoc` 目录）为准，不引入中心化服务。
- 冲突：无（不触及 timi-proxy / 派发路由 / target partition 语义）。
- 预期收益：autopilot 的 phase 自动推进从「整条通道 exit=1、只能人工 bridge」恢复为可无人值守；同时 fail-loud 保证任何「根定位不一致」不再静默写到别的项目目录。判定：conductor 路径（mw `advance()`）在目标项目上 spec→design 成功，且跨项目 `.agenticdoc` 无新建目录。

## §1 功能概述

### 1.1 目标

修掉 autopilot phase-advance 通道的跨项目根错位（三跳根因链），并把中文诊断编码修回可读。

根因（2026-09-22 实测确认）：

1. `<project>/.agentic-framework` 的 `repo=` 指向 mw 仓库里的 framework clone；mw `autopilot/advance.py::locate_platform_dir()` 把 marker repo 排在候选第一位，只取 `detect_root.py` 的 `PLATFORM_DIR`，丢掉 `PROJECT_ROOT`，于是错误无法被发现。
2. framework `advance_phase.py::find_root()` 用 `Path(__file__)` 向上找 `.agenticdoc`，与 cwd 无关；framework 装在项目外时命中的是 clone 所在仓库（Multi-Workers）自己的 `.agenticdoc`。
3. 错误 key_dir 被 `mkdir` 出来，门禁按「Current phase: init + MISSING: spec.md」报错；`locate_platform_dir`/`advance` 的子进程没加 `-X utf8`，cp936 中文诊断被按 utf-8 解码成 `?`，故障信息不可读。

### 1.2 技术栈 / 语言

Python（framework skill scripts + `packages/multi-workers`）；TypeScript（agent-team-loop 扩展既有运行器）。

### 1.3 核心用户场景

1. E2Feature（framework 装在 mw 仓库）autopilot conductor 每 tick 调 `advance(key, design, E2Feature)` → exit 0，`E2Feature/.agenticdoc/<key>/pm-state.md` 推进。
2. 修复前副作用（在 `H:\git\Multi-Workers\.agenticdoc` 下 `mkdir` 空的 key 目录）不再发生。
3. 若某候选 framework 的 `detect_root` 报出的 `PROJECT_ROOT` 与目标项目不一致 → mw 直接 `AdvanceError`（fail-loud），绝不静默写错项目。
4. 中文门禁诊断（缺 spec.md / 记忆前馈 / 编号 AC 等）在 mw 与 pi 扩展两侧都可读（不再 `?`）。

### 1.4 范围说明（不做什么）

- 不改 `detect_root.py` 的 `PLATFORM_DIR` 推导（脚本自身位置仍是它的正确来源）。
- 不引入「候选优先级重排」（项目内副本优先）：实测项目内副本可能更旧（E2Feature `.agents` 副本 a06b4a2 vs marker clone e9360db），重排等于跑旧框架。
- 不做 mw 侧根路径缓存/lock 改造。
- 不改 autopilot 调度语义（tick、budget、门禁业务规则不动）。

## §2 业务约束

### 2.1 平台 / 环境

Windows（cp936 控制台）+ 三份 framework 副本：`<mw>/.agents/skills/agentic-task`（marker repo 指向的 clone）、`<project>/.agents/skills/agentic-task`（codex clone）、`<project>/.claude/scripts`（install.py 镜像）。canonical 源为 framework repo 根的 `scripts/`，`claude/scripts`、`core/scripts` 是镜像。

### 2.2 性能指标

root 判定只读文件系统，单次 advance 增开销 < 10ms（不引入额外子进程；`detect_root.py` 调用已存在）。

### 2.3 安全约束

- 失败必须 fail-loud：候选 framework 与目标项目不一致时抛 `AdvanceError`，不得回退到「猜一个」。
- 不得写坏其它项目/仓库的 `.agenticdoc`（本 key 的验收核心）。
- 跨仓改动需 commit + push 到 `wenbocode/AgenticTask`，并同步项目内副本。

### 2.4 集成依赖

- `.agentic-framework` marker（`repo=`）语义：由 install.py 写。
- `detect_root.py --json` 输出契约：`PLATFORM_DIR` / `PROJECT_ROOT` / `AGENTICDOC_ROOT`。
- mw `autopilot/advance.py` 调用契约：`advance(key, phase, project_root) -> (exit, stdout, stderr)`；conductor 依赖 exit code。

## §3 验收标准（AC）

> AC Locked at 2026-09-22（编号永不回改）

| AC 编号 | 描述 |
|--------|------|
| AC-001 | framework 的 root 定位统一改为「cwd 向上专扫 `.agenticdoc` 优先，`__file__` 仅回退」：`advance_phase.py`、`update_index.py`、`migrate_patterns.py`、`verify_project_memory.py` 四处在 framework 位于项目外、cwd=项目根时解析到项目自身 `.agenticdoc`；framework repo 自身即项目时仍解析正确。 |
| AC-002 | `detect_root.py` 的 `PROJECT_ROOT`/`AGENTICDOC_ROOT` 在 framework 位于项目外、cwd=项目根时返回该 cwd 所属项目（`method` 反映 cwd 专扫），不再锚到 framework clone 所在仓库。 |
| AC-003 | mw `locate_platform_dir()` 逐个候选执行 `detect_root.py --json`，只采用 `PROJECT_ROOT == project_root`（resolve 归一）的候选；全部不一致时 raise `AdvanceError`（消息含每个候选的实测 PROJECT_ROOT）。不再出现「静默 `mkdir` 到别的 `.agenticdoc`」。 |
| AC-004 | mw `advance()` 与 `locate_platform_dir()` 的子进程 argv 均含 `-X utf8`；相应单测断言 argv（中文诊断不再变 `?`）。 |
| AC-005 | 端到端（hermetic）：在 framework 之外的临时项目目录建 `.agenticdoc/<key>/{spec.md（过 design 门禁）,_index.parallel}`，调 mw `advance(key, "design", tmp_project)` → exit 0 且临时项目 `pm-state.md` 推进；同时断言 framework clone 所在仓库的 `.agenticdoc` 无新建目录。 |
| AC-006 | 负路径：候选 framework 的 `PROJECT_ROOT` 与 project_root 不一致时 `locate_platform_dir` raise `AdvanceError`；`advance()` 返回 `(1, "", "[advance] ...")` 且消息可读（非 `?`）。 |
| AC-007 | framework clone 改动 commit + push 到 `wenbocode/AgenticTask`；`diff-installed.py`（对本仓）clean；E2Feature 的两份项目内副本（`.agents/skills/agentic-task` clone + `.claude/scripts`）同步到含该修复的 commit。 |
| AC-008 | 回归：`packages/multi-workers` pytest（framework/autopilot 相关用例）全绿；`npm run check` 0 error/0 warning/0 info；无新增失败。 |

## §4 风险与未决项

- 风险：`-X utf8` 依赖 CPython（mw 用 `sys.executable`，成立）；若将来换非 CPython 解释器需改为 `PYTHONUTF8=1` 环境变量。
- 风险：cwd 优先在「cwd 落在别的 AgenticTask 项目子目录」时可能选错——但相比现状（`__file__` 恒选中 clone 所在仓库）是严格改善，且工具链恒以 `cwd=项目根` 调用。
- 风险：其它未同步的项目在 AC-003 fail-loud 上线后会拒绝 advance——需在同一批次同步其项目内副本（或先发 framework 再发 mw）。
- 待确认：pi 扩展 `agent-scripts.ts` 是否也纳入 `-X utf8`（同型缺陷）——design 定案。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- `detect_root.py --json`（PLATFORM_DIR/PROJECT_ROOT/AGENTICDOC_ROOT 契约，install.py 已依赖）——AC-003 直接复用其输出做一致性校验。
- `.agentic-framework` marker（`repo=`）+ `install.py`（mirror 同步 + clone `pull --ff-only` + 写 marker）——AC-007 同步路径。
- framework 自带测试 `scripts/test_detect_root.py` / `test_advance_phase.py` / `test_update_index.py`——AC-001/002 先例。
- `packages/multi-workers/test_autopilot_conductor.py` 的 fake-framework harness——AC-003/004/005/006 复用。
- `_arch_snapshot.md` §advance_phase / audit_phase 门禁脚本条目（`.agents/skills/agentic-task/scripts`）。

### 需规避坑点

- P-001（PS 管道损坏无 BOM UTF-8）：所有 `.agenticdoc/` 与 framework 脚本改写用 write/edit 或 Python `encoding="utf-8"`，禁止 PS Get-Content/Set-Content 往返。
- P-003（`open(p,"w")` 先截断后求值）：脚本改动先算后写；测试断言文件非空 + 关键内容锚点，不看退出码。
- P-003 附则：本次改动脚本多，复验必须 grep 关键行（如 `Path.cwd()` 出现在 find_root）。
- P-004（POSIX 词法在 Windows 路径丢反斜杠）：AC-003/005 的路径一致性比较用 `Path.resolve()` / `os.path.realpath`，不手写字符串切分。
- 野生实施教训（mw-ue-toolchain）：本 key 先建 key 再动手；framework 改动同步走 install.py，不手工贴副本。
