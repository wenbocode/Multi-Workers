# Plan: mw-widget-terminal-lifecycle

## 概览
- Key: mw-widget-terminal-lifecycle
- Spec: .agenticdoc/mw-widget-terminal-lifecycle/spec.md（AC-001~013，locked 2026-09-10T12:13:52+08:00）
- Design: .agenticdoc/mw-widget-terminal-lifecycle/design.md（D-001~D-009，VC-001~013，指纹 95d6a253ba12，2026-09-10 重锚，原 4340acf7b818 口径不可复现已废弃）
- 预计阶段数: 5（S1 双侧基础协议 → S2 终态摘要源头 → S3 PM 展示与 ack 通道 → S4 launcher reconcile → S5 回归收口）
- 拆解顺序依据: design §3 模块划分与依赖方向（协议层 → 源头 → 消费方 → 集成 → 收口）；S1 与 S2 无交叉可并行
- 创建时间: 2026-09-10

## 阶段列表

### Stage 1: 双侧基础协议（sidecar 与证据解析）
**目标**: ack 持久化（D-001）与 Python 终态证据/beat 协议（D-007/D-008 支撑函数）先行，均为无 UI 依赖的独立模块，各带 L1 单测。
**依赖**: 无（可与 Stage 2 并行）
**产出**:
- `packages/coding-agent/src/extensions/agent-team-loop/shared/ack-store.ts`（AckStore：readAll/ack，workers.lock + tmp/rename）
- `packages/multi-workers/mw_common.py` 增量：`parse_end_exit(task_dir)`、`launcher_beat_write/other_live_launcher`、`ORPHAN_DEAD_AFTER`（env `PI_WORKER_ORPHAN_DEAD_MIN`，默认 90）
- 对应单测（agent-team-loop.test.ts 扩展 + test_launcher.py/test_common.py 扩展）
**Tasks**: T-01, T-02

---

### Stage 2: 终态摘要源头（worker / launcher 侧）
**目标**: done 行单行结论的源头质量（D-005）：worker 侧 TL;DR 归一化写入 + 跨 CLI starter 引导。不依赖 Stage 1。
**依赖**: 无（可与 Stage 1 并行）
**产出**:
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`：writeOutput 增 `## TL;DR` 首节 + `headline()` 导出（首非空行/剥标记/折叠空白/截断 100）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`：deadline steer 文案补首行结论要求（微调）
- `packages/multi-workers/launcher.py`：`_starter_prompt` 追加首行结论指令
**Tasks**: T-03, T-04

---

### Stage 3: PM 展示与 ack 通道（消费方）
**目标**: widget 分区渲染（D-003）、终态 detail 取源（D-004）、ack 双通道与提示链路（D-002）。
**依赖**: Stage 1（AckStore）+ Stage 2（TL;DR 节格式）
**产出**:
- `ui-bridge.ts`：readOutputSection / readTerminalDetail / readWorkerLogTail；renderWatchLines 分区重构（live/unhandled 不折叠，history 5+more，header `N unhandled`）；/mw ack 子命令；ack_worker_result 工具；list_tasks acked 徽标
- `pm-orchestrator.ts`：PM_CONTINUE_HINT 追加 ack 指示；poll loop 构造 AckStore 传入 render
- agent-team-loop.test.ts 扩展（VC-001~007/009~011 埋点）
**Tasks**: T-05, T-06, T-07

---

### Stage 4: launcher reconcile（集成）
**目标**: 孤儿 running 行收敛（D-006/D-007/D-008）：正证据映射 + 静默窗口 + beat 退让，接入 _poll_once。
**依赖**: Stage 1（mw_common 助手）
**产出**:
- `packages/multi-workers/launcher.py`：`_reconcile_orphans(project_dir, running_procs)` + poll 接入 + beat 刷新
- test_launcher.py 扩展（VC-012/013 埋点）
**Tasks**: T-08

---

### Stage 5: 回归与收口
**目标**: 双侧全量回归零基线漂移 + bundle 重建 + [VERIFY] 证据汇总（QG 输入）。
**依赖**: Stage 1~4 全部完成
**产出**:
- TS 全量（既有 90 用例 + 新增）+ Python 全量 + `npm run check` 全绿记录
- `/mw build` 重建全局 bundle + 冒烟（widget 渲染 + ack 手动路径）
- `evidence/runs/` 汇总记录
**Tasks**: T-09

---

## 状态总览

| Task | Stage | 内容 | AC | VC | 状态 |
|------|-------|------|----|----|------|
| T-01: AckStore | 1 | sidecar `_workers.acked` 读写：readAll/ack（lock+tmp/rename，幂等）；单测往返/幂等/坏行容忍 | AC-004 | VC-004（存储半） | pending |
| T-02: mw_common 证据与 beat | 1 | parse_end_exit（镜像 TS END_LINE_RE）+ launcher_beat_write/other_live_launcher（30s 新鲜阈）+ ORPHAN_DEAD_AFTER env 解析；单测 | AC-012, AC-013 | VC-012, VC-013（支撑半） | pending |
| T-03: TL;DR 归一化 | 2 | writeOutput 增 `## TL;DR` 首节 + headline()（首非空行/剥 `#`/`**`/`[-*] `/`> `/折叠空白/截断 100）+ deadline steer 文案；单测含样本回测 | AC-009 | VC-009（写入半） | pending |
| T-04: starter 引导 | 2 | launcher `_starter_prompt` 追加「最终回复第一行 = 单行结论（状态+关键产出/卡点）」指令（ASCII，跨 CLI） | AC-009 | VC-009（源头半） | pending |
| T-05: 终态 detail 取源 | 3 | readOutputSection 泛化 + readTerminalDetail（failed→spawnFailure??Exit Reason；nc→Questions??log 尾行(≤256KB)??no-output；done→TL;DR??清洗 Summary）+ readWorkerLogTail；单测回退链 | AC-007, AC-008, AC-009 | VC-007, VC-008, VC-009（展示半） | pending |
| T-06: widget 分区 | 3 | renderWatchLines 三区重构 + WATCH_HISTORY_MAX=5 + more 行 + header `N unhandled`；签名增 ackStore；单测 5/6 折叠边界 | AC-001, AC-002, AC-003 | VC-001, VC-002, VC-003 | pending |
| T-07: ack 通道与提示 | 3 | /mw ack 子命令 + ack_worker_result 工具（PM-only）+ list_tasks 徽标 + PM_CONTINUE_HINT + 防重派发验证；单测 | AC-004, AC-005, AC-006, AC-010, AC-011 | VC-004（通道半）, VC-005, VC-006, VC-010, VC-011 | pending |
| T-08: reconcile 集成 | 4 | _reconcile_orphans：正证据三映射（0/2/else）+ output.md-only→failed+unverifiable + 静默 90m + beat 退让 + own 行不动 + worker.log 原因行；接入 _poll_once；单测 | AC-012, AC-013 | VC-012, VC-013 | pending |
| T-09: 回归收口 | 5 | TS/Python 全量 + npm run check + /mw build 重建 + 冒烟 + evidence/runs/ 汇总 | 全部 | 全部（汇总） | pending |

## 依赖图

```
T-01 ──┬──> T-06 ──┐
T-02 ──────> T-08 ─┤
T-03 ──> T-05 ──> T-06 ──> T-09
T-04 ──────────────┤
T-01 ──> T-07 ─────┘
```

- T-01/T-02/T-03/T-04 相互独立（可 4 并行派发）
- T-05 依赖 T-03（TL;DR 节格式）；T-06 依赖 T-01+T-05；T-07 依赖 T-01；T-08 依赖 T-02
- T-09 依赖全部

## 派发建议（沿用 goal-autopilot D-009/D-010 模式，执行时定案）

- 自包含、零文件交叉（T-01/T-02/T-03/T-04）→ 适合并行 worker
- 语义最重、跨文件集成（T-06/T-07/T-08）→ 建议 PM 直执或派发时带严格约束
- T-09 收口 → PM 直执
