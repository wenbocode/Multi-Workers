# 事件：派发卡片型任务时未落卡片文件（2026-10-12）

- 类型：**流程缺陷（框架侧可加固）**｜状态：**待修（后续 key）**
- 发现者：worker `mwgf-t20-final-fixes`（key `mw-guard-form-hardening`），在回读中如实上报
- 上报原文要点：「the card named as sole authority (`tasks/T-20-final-ci-and-heredoc-fixes.md`) does not exist」——它按 dispatch 描述执行，并明确声明而不是静默假设范围

## 1. 事实经过

PM（主窗口）在 `mw-guard-form-hardening` 的 verify 阶段连续派发两类 worker：

| worker | 派发方式 | 卡片文件 | 结果 |
|---|---|---|---|
| `mwgf-t15-python-claim` | 先写卡 `tasks/T-15-*.md` 再派 | 存在 | 正常 |
| `mwgf-t16-claim-family-gate` | 先写卡再派 | 存在 | 正常 |
| `mwgf-t17-repair-reanchor` | 先写卡再派 | 存在 | 正常 |
| `mwgf-t18-exe-wrapper-vc-labels` | 先写卡再派 | 存在 | 正常 |
| `mwgf-t19-residual-fixes` | 先写卡再派 | 存在 | 正常 |
| **`mwgf-t20-final-fixes`** | **只写 dispatch 描述，未落卡** | **不存在** | 结果正确，但**违反流程**（worker 只能以描述为权威，且如实上报了缺口） |
| `mwgf-qga*` / `mwgf-qgb*`（6 次 QC 派发） | 描述式派发（QC 无需卡片，由 dispatch 文本承载完整指令） | — | 符合既有惯例 |

**关键区别**：T-20 是**实现型**任务（要改 `worker-mode.ts` 与测试、有明确写入面与禁令），必须落卡；QC/审计型 worker 的指令可全部由 dispatch 文本承载（但即便如此也应尽量落卡以便追溯）。

## 2. 危害

1. **权威缺失**：卡是 worker 的「唯一权威」载体（含写入面白名单、禁令、验收命令、判定纪律）。无卡时 worker 只能依赖 dispatch 描述 ⇒ 描述若与相位文档冲突，冲突不可仲裁。
2. **不可追溯**：`tasks/` 目录是「本 key 做过哪些实现」的账本；漏卡会让 `plan.md` 的卡片总表与实际派发不一致（本次 T-20 就未登记进 `plan.md`）。
3. **宽度不可控**：卡的写入面白名单是防止 worker 扩面的主要机制；无卡时扩面风险显著上升（本次侥幸未扩面）。
4. **门禁口径漂移**：PM 自检清单（「派发前卡片存在」）在这次的多轮高压派发中被跳过，说明该检查目前**只依赖 PM 自律**，没有工具强制。

## 3. 建议修法（按优先级）

### F-1（推荐，工具侧强制）：`dispatch_worker` 对实现型任务要求卡片存在
- 当 `type = coding`（或任何会改 `packages/**` / `.agents/**` 的任务）时，`dispatch_worker` 应：
  - 要么要求显式传入卡片路径参数（如 `card_path`）并**校验文件存在**，不存在则拒绝派发并给出明确错误；
  - 要么按约定自动生成卡片骨架（`tasks/<task_key>.md`）并在派发前落盘，把 dispatch 描述中的指令写入该文件，然后要求 worker 以该文件为唯一权威。
- 错误信息应指名缺失路径 + 建议动作，避免 PM 自行「描述式派发」蒙过去。

### F-2（弱保证，PM 侧清单）：派发前自检
- 在 PM 工作流中加入一条硬检查：「实现型任务派发前，`tasks/` 内必须存在同任务卡片；未落卡不得派发」。
- 该检查写入 PM 的 dispatch 纪律文档（与 D-037「不得转述卡片内部细节」并列），作为派发前 checklist 一项。

### F-3（可观测）：`plan.md` 卡片总表与实际派发的一致性校验
- 在 verify/quality 阶段增加一条机器检查：`tasks/*.md` 的卡片集合与 `_workers.parallel` 中本 key 的实现型 task_key 集合应可对齐；不对齐时告警（本次 T-20 会让该检查报红）。

## 4. 复现与证据

- 缺失路径：`.agenticdoc/mw-guard-form-hardening/tasks/T-20-final-ci-and-heredoc-fixes.md`（实测不存在）
- 存在同批其他卡片：`T-15`…`T-19`（均在 `tasks/` 内）
- worker 上报位置：`.agenticdoc/mw-guard-form-hardening/workers/mwgf-t20-final-fixes/report.md`（TL;DR 与 Summary 均声明「the card named as sole authority ... does not exist」）
- 派发记录：`_workers.parallel` 中 `mwgf-t20-final-fixes` 一行（其 task.md 由 dispatch 描述生成，非卡片）

## 5. 归属

- **框架侧修法**（F-1/F-3）：`mw` 后台服务与 `dispatch_worker` 工具实现（`packages/multi-workers/**`、`packages/coding-agent/src/extensions/agent-team-loop/**`）
- **流程文本修法**（F-2）：PM 纪律文档（`.agents/skills/agentic-task/` 下的 PM 参考/工作流文档）
- **建议**：随下一个「框架硬化」key 一并处理，不要在本 key（`mw-guard-form-hardening`，已完成其守卫硬化范围）内扩面。
