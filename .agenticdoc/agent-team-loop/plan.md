# Plan: agent-team-loop

## 概览
- Key: agent-team-loop
- Spec: .agenticdoc/agent-team-loop/spec.md（AC-001~036）
- Design: .agenticdoc/agent-team-loop/design.md（VC-001~047）
- 预计阶段数: 7
- 创建时间: 2026-08-11

## 阶段列表

### Stage 1: 基础文件层
**目标**: 实现 `_workers.parallel` 和 `_index.parallel` 的 TypeScript 读写模块，含跨平台文件锁
**依赖**: 无
**产出**:
- `packages/coding-agent/src/extensions/agent-team-loop/shared/file-lock.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts`
**Tasks**: T-01, T-02

---

### Stage 2: launcher.py
**目标**: Python launcher 完整实现——轮询 `_workers.parallel`、从 providers.json 路由、spawn worker 进程、回写 status（含 .lock 文件锁）
**依赖**: Stage 1（`_workers.parallel` 格式已定义）
**产出**:
- `packages/multi-workers/launcher.py`
- `packages/multi-workers/providers.json`
**Tasks**: T-03, T-04

---

### Stage 3: proxy_multi.py + mw serve
**目标**: 三端口 LLM proxy + mw serve/start/stop/status 生命周期管理（PID 文件防重复）
**依赖**: Stage 2（launcher.py 已可被 mw serve 管理）
**产出**:
- `packages/multi-workers/proxy_multi.py`
- `mw.py`（serve/start/stop/status 子命令）
**Tasks**: T-05, T-06

---

### Stage 4: worker-mode Extension
**目标**: Pi worker-mode Extension：读 task.md、setActiveTools、agent_settled 监听、output.md 四节写入、全 exit code（0/1/2/130）
**依赖**: Stage 1（worker-store.ts 格式定义）
**产出**:
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/phase-runner.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`
**Tasks**: T-07, T-08, T-09

---

### Stage 5: pm-orchestrator Extension
**目标**: Pi PM-mode Extension：goal elicitation、task dispatch 到 `_workers.parallel`、轮询 done/failed、/pm-key TUI 命令、_index.parallel AgenticTask 格式兼容
**依赖**: Stage 1（worker-store.ts + index-store.ts）、Stage 4（Extension index.ts 两 mode 均可 import）
**产出**:
- `packages/coding-agent/src/extensions/agent-team-loop/index.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/state-manager.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/goal-reader.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
**Tasks**: T-10, T-11, T-12, T-13

---

### Stage 6: mw init + Extension bundle
**目标**: mw init 子命令完整实现（目录结构 + bundle 安装到 `.pi/extensions/`）；build 配置产出预编译 `dist/extensions/agent-team-loop.js`
**依赖**: Stage 3（mw.py 框架）、Stage 5（Extension 源码完整，可构建）
**产出**:
- `mw.py`（init 子命令完整实现）
- Extension build 配置（esbuild/tsup）
- `dist/extensions/agent-team-loop.js`（构建产物占位 or 构建脚本）
**Tasks**: T-14, T-15

---

### Stage 7: 集成验证
**目标**: smoke_test.sh E2E 验证全链路（L2 VCs）；dispatch-table.md 补全路由条目；全部 L0/L1 VC 通过
**依赖**: Stage 1~6 全部完成
**产出**:
- `smoke_test.sh`
- `dispatch-table.md`
- `evidence/runs/` 验证记录
**Tasks**: T-16, T-17

---

## 状态总览

| Task | Stage | 状态 | 负责 Agent |
|------|-------|------|-----------|
| T-01: file-lock.ts | 1 | ⬜ pending | - |
| T-02: worker-store.ts + index-store.ts | 1 | ⬜ pending | - |
| T-03: launcher.py 核心（轮询 + spawn） | 2 | ⬜ pending | - |
| T-04: launcher.py 进阶（providers.json + dry-run + max-workers） | 2 | ⬜ pending | - |
| T-05: proxy_multi.py | 3 | ⬜ pending | - |
| T-06: mw.py serve/start/stop/status | 3 | ⬜ pending | - |
| T-07: worker-mode.ts 主协调 | 4 | ⬜ pending | - |
| T-08: phase-runner.ts（Goal-Anchored） | 4 | ⬜ pending | - |
| T-09: output-writer.ts（全 exit code） | 4 | ⬜ pending | - |
| T-10: index.ts Extension 入口 | 5 | ⬜ pending | - |
| T-11: state-manager.ts + task-dispatcher.ts | 5 | ⬜ pending | - |
| T-12: goal-reader.ts（goal elicitation） | 5 | ⬜ pending | - |
| T-13: pm-orchestrator.ts + ui-bridge.ts | 5 | ⬜ pending | - |
| T-14: mw.py init 子命令 | 6 | ⬜ pending | - |
| T-15: Extension build 配置 | 6 | ⬜ pending | - |
| T-16: smoke_test.sh E2E | 7 | ⬜ pending | - |
| T-17: dispatch-table.md + L0/L1 验证汇总 | 7 | ⬜ pending | - |
