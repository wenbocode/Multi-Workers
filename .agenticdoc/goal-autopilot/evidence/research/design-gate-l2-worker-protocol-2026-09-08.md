# Research: gate 协议、L2 定点读取与 typed 派发（design）

## 决策问题

人工门禁文件协议、L2 worker 定点读取的机械强制（AC-009）、autopilot 派发路径的工具白名单显式化与未知 type 拒绝（GC-8/AC-021）、L3 review 级与 done 门禁的产物落地方式（AC-010）。

## 调研方法与出处

- `packages/coding-agent/src/core/extensions/types.ts` L1025-1060（ToolCallEvent）+ L1330-1340（ToolCallEventResult）：`tool_call` 事件在工具执行前触发，`event.input` 可原地改写，handler 返回 `{block: true, reason}` 即拒绝执行——扩展可机械拦截工具调用，无需改 pi 核心
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` L10-18：TOOL_ALLOWLISTS 现有 coding/review/research/fallback 四条目；`toolsForType` 未知 type 回退 fallback 全集（含 write/edit/bash）——spec B2 代码事实验证一致；`parseTaskMd`（L23-67）已按行解析 `type:` frontmatter，扩展 `read_scope:`/`loop:`/`attempt:` 为同构增量
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`（接口）+ worker-mode.ts L170-230：output.md 由 worker-mode 在退出路径统一写入（writeOutput），exit hook 兜底——拒绝记录可在内存收集后随 output.md 落盘
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` L289-296（pickWorkerRoute）：`type: codex` 路由 claude 外全部 pi/timi——新 type 无需路由改动
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` registerMwCommands/registerWorkerCommands（L700-900 区段）：命令注册模式（subcommand 分发 + ctx.ui.notify）与 `pi.appendEntry` 会话持久化——/autopilot 命令集与 last-seen 水位直接复用该模式
- `.agents/skills/agentic-task/scripts/advance_phase.py` GATES["done"]：需要 achieved.md ≥200B、pm-state 含 PASS、evidence/quality-gate-report-*.md ≥1——done 门禁的三项产物清单
- `packages/multi-workers/launcher.py` L60-104（_build_env）：pi worker 经 PI_WORKER_TASK 环境变量定位任务文件；worker 进程 env 由 launcher 构造——conductor 派发行无需新增 env 通道
- `packages/coding-agent/src/extensions/agent-team-loop/shared/phase-docs.ts`（dispatchDocGaps 被 pm-orchestrator/ui-bridge 引用）：TS 手动路径的 docs gate 只拦 TS 侧自动派发；launcher 对队列行不做 docs gate——conductor 自行执行等价前置检查（L1 审计即此职能的强化版）

## 发现

1. **AC-009 无需新进程沙箱**：worker-mode 订阅 `tool_call`，按 task.md `read_scope:` 前缀列表核对 read/grep/find/ls 的路径参数，越界返回 `{block, reason}`，拒绝项（路径+命中规则）内存累积，退出时写入 output.md 附加节——纯扩展层实现，跨平台无差异
2. **AC-021 双侧注册表可行**：conductor 侧（Python）持 type→工具集→cli 路由表，派发前查表，未注册 type → 0 行 + 时间线事件；worker 侧 TOOL_ALLOWLISTS 增加同名显式条目；双侧表由一个 L0 奇偶校验测试锁定（TS/Python 无法共享模块，测试是防漂移的唯一手段）
3. **未知 type 的 fallback 语义保留**：GC-8 明确 fallback 全集行为仅限手动模式；autopilot 派发的 task.md 一律带 conductor 可识别 type，worker 侧无需区分来源（conductor 侧已拒绝未知 type，到达 worker 的必然是注册过的）
4. **L3 review 级与 done 门禁冲突的解法**：L3 reviewer 无 write 权限（AC-021 锁定），但 done 门禁需要 quality-gate-report + achieved.md；裁决 = L3 在 output.md 输出结构化报告节，conductor 机械落盘两文件（文件写入非判断，不违反 AC-005——其只禁 Phase 直写与 goal.md 写）
5. **gate 文件协议选 per-gate md 文件**：frontmatter（id/kind/status/answered_by）+ 正文问题与上下文指针；人工经 `/autopilot gate <id> approve` 由 TS 重写字段（O_CREAT|O_EXCL 锁 `.mw/gates.lock`），conductor 每 tick 扫描 gates/ 目录——人可读可手改、锁粒度小、无单文件争用
6. **AC-016 时延可达**：conductor tick 读取已回答 gate 并在同一 tick 内继续推进，时延 = 1 个轮询间隔

## 结论 → 决策映射

- D-105 gate = `.agenticdoc/_autopilot/gates/gate-{seq:04d}.md` frontmatter 协议，回答走 TS 重写、创建走 conductor、消费走 tick 扫描 → AC-002/003/016/024
- D-106 L2 定点读取 = task.md `read_scope:` + worker-mode `tool_call` block + output.md 拒绝记录 → AC-009
- D-107 typed 派发 = conductor 注册表 + worker TOOL_ALLOWLISTS 显式条目 + 奇偶测试 → GC-8/AC-021
- D-108 L3 产物 = reviewer 输出结构化节 + conductor 机械落盘 QG 报告与 achieved.md 草稿 → AC-010、done 门禁
