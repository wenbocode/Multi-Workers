# Research: 现有能力盘点——B+C 架构可行性（spec）

## 决策问题

B+C 架构（conductor + typed 判断-worker + console 监控台）是否可行；哪些能力已存在可直接复用，哪些是纯新增（支撑 spec §1 范围 / §5 复用清单 / §4 风险）。

## 调研方法与出处

- 通读 `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（363 行，全文）
- 通读 `.agents/skills/agentic-task/claude/scripts/update_index.py`（全文）与 `advance_phase.py` 门禁规则（dispatch-table.md「Phase 推进」节引用）
- 读 `.agenticdoc/agent-team-loop/design.md`（模块结构 §2 / 接口 §4 / 数据流 §5）与 `pm-state.md`（17 task 状态、VC 证据）
- 读 `.agenticdoc/_workers.parallel` 现状（9 行历史条目，7 列格式）
- 读 pm-mind.md（Turn Start / Hook 2 / Hook 3 / Phase 4.5 分层降级验证 / U9 pattern）与 dispatch-table.md（路由规则）

## 发现

已存在、可直接复用：

1. **派发通道**：PM 会话 `dispatchNewTasks()` 扫 `{key}/workers/*/task.md` 自动派发（pm-orchestrator.ts）；launcher.py 轮询 `_workers.parallel` spawn worker，exit code→status 映射（0=done / 1=failed / 2=needs-clarification / 130=cancelled）
2. **worker 协议**：task.md + phases + `progress/phase-N.md` + output.md 四节 + trace.log `[GOAL_CHECK]` goal mtime 追踪
3. **phase 门禁**：advance_phase.py 强制所有 phase 转换过 gate-check（spec≥500B / design≥500B / plan≥300B / tasks≥1 / done 需 PASS 证据 + memory feedforward + achieved.md）；guard_pm_state.py 拦截直写
4. **claim 体系**：_index.parallel 7 列格式 + ClaimId（时间戳-PID），`claimState()` 支持 held-live 判定，restoreWatch 从 session entries 恢复 watch
5. **console 基础**：startWorkerPollLoop（4s 轮询）+ watch widget + 终态摘要展示 + readSpawnFailure 失败归因
6. **判断-worker 的路由雏形**：pickWorkerRoute 已按 `type:` 字段路由（codex/review→claude，默认→pi/timi）
7. **U9 pattern 机制与 achieved.md Hook 3**：L3 失败出口（遗留问题必须有去向）已有框架约定

纯新增（本 key 交付）：

- `_roadmap.md`（stage 批次：key 作用/依赖/阶段目标/闭环判定）
- conductor 状态机（mw 服务内，选 key、派 phase worker、收 artifact、调 advance_phase.py）
- L1 证据审计脚本（audit_evidence.py：AC/决策点→证据映射、缺口清单、结构化 dossier）
- gate 文件协议（stage 级 + key 级 stalled + L1↔L2 升级）与 `/autopilot` 命令集
- 事件时间线文件与 console 的离线回放
- 全局回合预算配置（单处定义）

## 结论 → 决策映射

- conductor 不需要新调度基础设施：派发走既有 `_workers.parallel`，推进走既有 advance_phase.py，所有权走既有 ClaimId——B+C 架构成立且与「文件驱动协调」约束一致（spec §1.1、§2.4）
- console 是现有 PM 会话的增量增强（watch widget → stage 视图），非新进程类型（spec §1.1）
- 判断-worker 复用现有 worker 协议 + type 路由，仅扩 task type 语义（spec §1.3 场景 1）
- 风险对应：conductor 与框架语义漂移 → 只调脚本不重写（spec §4）
