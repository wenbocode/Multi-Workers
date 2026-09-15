# Plan: goal-autopilot

## 概览
- Key: goal-autopilot
- Spec: .agenticdoc/goal-autopilot/spec.md（AC-001~025，locked 2026-09-08T20:31:02Z）
- Design: .agenticdoc/goal-autopilot/design.md（v2，D-101~D-116，VC-001~027，指纹 475a2958a5ca）
- 预计阶段数: 5（S0 基线冻结 → S1 Python 基础设施 → S2 conductor 核心 → S3 TS console/worker → S4 验证收口）
- 拆解顺序依据: pm-state 2026-09-08 处置轮第 7 条建议（Python 基础设施含 stale-lock/act-first/origin → conductor 核心 → TS console/worker-mode 含 D-115/116 修复 → L2 计时/E2E → 奇偶与静态门禁）
- 创建时间: 2026-09-09

## 阶段列表

### Stage 0: 基线冻结
**目标**: 在任何实现改动前固化现有手动工作流套件基线（AC-012 的对照锚点，evidence-requirement 落盘约定）
**依赖**: 无
**产出**:
- `.agenticdoc/goal-autopilot/evidence/baseline/baseline-manual-suites.md`（套件清单 + 期望通过数 + 原样输出，首 commit 固化）
**Tasks**: T-01

---

### Stage 1: Python 基础设施（autopilot/ 无状态模块）
**目标**: conductor 的全部支撑模块先行——配置/roadmap/时间线/gate/派发/状态推导/L1 审计，每个模块自带 L1 单测（test_autopilot_*.py，[VERIFY] 行输出）
**依赖**: Stage 0（基线已冻结）
**产出**:
- `packages/multi-workers/autopilot/config.py`（D-110）
- `packages/multi-workers/autopilot/advance.py`
- `packages/multi-workers/autopilot/roadmap.py` + `roadmap_check.py`（D-105 schema）
- `packages/multi-workers/autopilot/timeline.py`（D-109）
- `packages/multi-workers/autopilot/gates.py`（D-105）
- `packages/multi-workers/autopilot/dispatch.py`（D-107/D-111/D-104 origin 标记）
- `packages/multi-workers/autopilot/state.py`（D-102/D-111/D-115）
- `packages/multi-workers/autopilot/audit_evidence.py`
- `packages/multi-workers/test_autopilot_{config,roadmap,timeline,gates,dispatch,state,audit}.py`
**Tasks**: T-02, T-03, T-04, T-05, T-06, T-07, T-08

---

### Stage 2: conductor 核心（状态机与集成）
**目标**: conductor.py 主循环 + per-key phase 机 + stage 机 + EXECUTE/L3 回路，mw serve 挂载监护；全部推进经 advance_phase.py 子进程（AC-005）
**依赖**: Stage 1（全部基础设施模块）
**产出**:
- `packages/multi-workers/autopilot/conductor.py`（§5.1/5.2/5.3 全流程）
- `packages/multi-workers/mw.py` 改（serve 监护 respawn / finally 终止集合 / status·doctor 增 conductor 行）
- `packages/multi-workers/test_autopilot_conductor{,_stage,_exec}.py`
**Tasks**: T-09, T-10, T-11, T-12

---

### Stage 3: TS console / worker-mode 协议增量
**目标**: worker 侧 read_scope 拦截（containment）+ 协议增量（origin 跳过/fail-closed/[START]/agenticdocRoot 修复）+ /autopilot 命令集；vitest 单测随任务
**依赖**: Stage 1（task.md frontmatter 协议定义）；Stage 2 非硬依赖但联调需要
**产出**:
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` 改（D-106/D-107/D-115/D-116）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` 改（dispatchNewTasks origin 跳过，D-104）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts` / `status-model.ts` / `gate-writer.ts`
- `packages/coding-agent/test/suite/autopilot-*.test.ts`（vitest）
**Tasks**: T-13, T-14, T-15

---

### Stage 4: 验证收口（L2 E2E / L0 静态 / 全量回归）
**目标**: L2 计时·隔离·并发 E2E（stub worker 完成器）+ L0 静态门禁与双侧奇偶 + 手动套件对照基线 + bundle 重建安装 + [VERIFY] 汇总供 QG
**依赖**: Stage 1~3 全部完成
**产出**:
- `packages/multi-workers/test_autopilot_e2e.py`
- `packages/multi-workers/test_autopilot_l0.py`（静态扫描 + 奇偶）
- `evidence/runs/` 验证记录
- bundle 重建安装（mw build --install）
**Tasks**: T-16, T-17, T-18

---

## 状态总览

| Task | Stage | 内容 | AC | VC | 状态 |
|------|-------|------|----|----|------|
| T-01: 基线冻结 | 0 | 按 mw-dispatch-reliability L0/L1/L2 矩阵运行现有 test_*.py + smoke_test.sh，固化 evidence/baseline/baseline-manual-suites.md（首 commit） | AC-012 | VC-014 前置 | ⬜ pending |
| T-02: config.py + advance.py | 1 | config.json 读写/默认值/校验（D-110 字段全集）；advance_phase.py 定位 + 子进程封装，框架缺失 → 拒绝启动 | AC-025 | VC-027 前置 | ⬜ pending |
| T-03: roadmap.py + roadmap_check.py | 1 | _roadmap.md 解析（D-105 schema：stage 三要素/key-status/status 行）+ 独立校验 CLI（exit 0/1 + stderr 缺失项） | AC-001 | VC-001 | ⬜ pending |
| T-04: timeline.py | 1 | jsonl 追加 + seq 单调恢复 + beat 事件 + 10MB 轮转保 2 代 + watermark 查询（旧→新回放） | AC-017 | VC-019（格式） | ⬜ pending |
| T-05: gates.py | 1 | gate 创建/解析/枚举 + seq = max(id)+1 + 5 kind + frontmatter schema 全字段 | AC-003, AC-024 | VC-005, VC-026（前置） | ⬜ pending |
| T-06: dispatch.py | 1 | typed 注册表（5 类型→工具集→cli/provider，D-107）+ 未知 type 拒绝（0 行 + 时间线）+ task.md 模板（origin/loop/attempt/read_scope）+ ap-{key}-{stem} 队列行（workers.lock 内） | AC-021 | VC-023（conductor 侧） | ⬜ pending |
| T-07: state.py | 1 | 零私有状态全推导：phase 读 index、claim 存活（parseClaim 复刻 + _is_alive）、loop 回合计数（task 目录标签）、[START] pid 观测 | AC-013, AC-014, AC-018, AC-022 | VC-015, VC-016, VC-020, VC-024（推导源） | ⬜ pending |
| T-08: audit_evidence.py | 1 | L1 审计 CLI → JSON dossier（ac_list/decision_map/gaps），齐全 exit 0 / 缺口 exit 1 | AC-007 | VC-009 | ⬜ pending |
| T-09: conductor 骨架 + serve 集成 | 2 | 主循环 tick（act-then-sleep D-114）/ beat 追加 / enabled+paused / goal mtime 检测 → goal-change gate 一次 / tick 级异常捕获；conductor 侧锁包装 stale 窃取（D-113，age>30s）；mw.py serve 1s 监护 + respawn + finally 终止 + status/doctor 行；--once/--poll-interval 可测入口 | AC-005, AC-019, AC-025 | VC-021（beat）, VC-027 | ⬜ pending |
| T-10: per-key phase 机 | 2 | pick ready key（依赖满足 + 未 live-claim）→ live foreign claim skip + timeline / phase artifact 映射 / L1 干净 → advance / 缺口 → L1↔L2 回路（verifier 派发 + phase-writer 补证同回合）/ 回合预算升级人工 gate / stalled 四产物（标记+gate+achieved 草稿+pattern）+ 依赖阻塞传播 / EXECUTE 中途接手（mtime 不变）/ budget=1 三回路一致 | AC-004, AC-005, AC-008, AC-011, AC-013, AC-014 | VC-006（L2）, VC-010, VC-013, VC-015, VC-016, VC-019（转移矩阵） | ⬜ pending |
| T-11: stage 机 + gate 生命周期 | 2 | stage-confirm 未答 0 派发 / 答后放行 / 全 key 终态 → 闭环 dossier + 下一 stage gate（1 tick 内）/ reject → roadmap-writer 重提案恰 1 次（roadmap 回路预算）/ 二拒停止自动提案 / stalled reject → 遗留关闭不阻塞闭环 / goal-change halt 语义 / 回答消费（gate-answered 事件） | AC-001, AC-002, AC-003, AC-006, AC-024 | VC-003, VC-005, VC-008, VC-026 | ⬜ pending |
| T-12: EXECUTE 循环 + L3 收敛 + done 三件套 | 2 | task 身份 = stem、每 key 串行、exec loop 标签、失败（exit/看门狗/spawn）入 retry 预算、孤儿和解、不阻塞他 key；L3 裁决解析（meets/below/缺节=below）→ below 走 repair:{key} 回路复评 ≤2 / meets → QG 报告 + achieved.md 机械落盘 + ≥200B 后验 + pm-state §3 PASS 行（key lock 下）+ advance done + index 后验；杀重启 2 tick 恢复不变量（[START]=1/预算不变/mtime 不变） | AC-004, AC-010, AC-022, AC-023 | VC-012, VC-024, VC-025 | ⬜ pending |
| T-13: worker read_scope 拦截 | 3 | tool_call block（read/ls/find/grep 同构）+ containment 算法（resolve → realpath 含不存在祖先回退 → 段边界前缀 → win32 lower）+ 文件/字节 cap 累计 + 拒绝记录双落盘（output.md 节 + trace.log [READ_SCOPE]）+ vitest 单测 | AC-009 | VC-011 | ⬜ pending |
| T-14: worker/TS 协议增量 | 3 | dispatchNewTasks 跳过 origin: conductor（D-104）；TOOL_ALLOWLISTS 增 5 类型显式条目（verifier 强制 read_scope 提示）；origin=conductor 且未注册 type → fail-closed exit 1（output.md 写明）；[START] pid 行（D-115）；agenticdocRoot 语义拆分修 goalMtime bug（D-116）；vitest | AC-021 | VC-023（worker 侧） | ⬜ pending |
| T-15: /autopilot console | 3 | status-model（roadmap+gates+timeline+workers → 视图模型 + status --json schema autopilot-status/1 版本化 + rounds 与 conductor 同源）+ gate-writer（gates.lock 下重写 frontmatter）+ console 命令集全量注册（status/gates/gate/timeline/enable/disable/pause/resume/roadmap）+ pmActivate 挂载 + session watermark（autopilot-seen）+ vitest（json 三字段/重建/parity） | AC-015, AC-016, AC-018 | VC-017, VC-018（L2 计时在 T-16）, VC-020 | ⬜ pending |
| T-16: L2 E2E（计时/隔离/并发） | 4 | test_autopilot_e2e.py（stub worker 完成器）：stage 门禁时延（delay ≤ 2×interval）/ gate 消费时延（≤ interval）/ 双 key 并行 <10s / roadmap-writer 产物全 stage 过 roadmap_check / 60s 窗 beat ≥12 / enable 链路（serve 检测+spawn+首 tick ≤ interval）/ 未启用零足迹 / 并发写 60s 压测（_workers 7\|8 列容错 + _index 7 列 + 并集无丢失） | AC-002, AC-004, AC-012, AC-016, AC-019, AC-020, AC-025 | VC-002, VC-004, VC-006, VC-014, VC-018, VC-021, VC-022, VC-027 | ⬜ pending |
| T-17: L0 静态门禁 + 奇偶 | 4 | 静态扫描（conductor 源码 Phase 直写 0 + goal.md 写调用 0 + advance 全走脚本留痕）；双侧注册表奇偶（每类型工具集精确相等，含 verifier）+ 未知 type conductor 0 行 + worker fail-closed 动态 | AC-005, AC-021 | VC-007, VC-023 | ⬜ pending |
| T-18: 全量收口 | 4 | L1 conductor 套件全绿 + 现有手动套件对照 baseline（AC-012 零回归）+ npm run check + vitest 全量 + bundle 重建安装（mw build --install）+ [VERIFY] 行汇总至 evidence/runs/ 供 QG 机械提取 | 全部 | 全部 | ⬜ pending |

## 执行约定

- **task 身份与顺序**：EXECUTE 期权威源是 `tasks/T-NN-slug.md` 文件（D-111）；plan 列出但 tasks/ 缺失 → L1 审计捕为缺口；同 key 一次一个在飞 exec 任务
- **验证分层**：L1 = Python 单测（[VERIFY] VC-NNN 行统一 emit）；vitest = 测试名含 VC 编号；L2 = test_autopilot_e2e.py stub 完成器；L0 = 静态扫描 + 奇偶
- **[VERIFY] 埋点**：Python harness 统一 emit `[VERIFY] VC-NNN: key=value`（evidence-requirement 落盘约定），供 QG 机械提取
- **零回归红线**：任何 task 不得改动未启用项目可见行为；手动路径 fallback 全集行为保持（GC-8）；TS 侧锁协议不动（D-113 仅 conductor 侧）
- **推进通道**：conductor 全部 phase 推进经 advance_phase.py 子进程（AC-005），本 plan 各 task 自测亦复用 advance.py 封装
