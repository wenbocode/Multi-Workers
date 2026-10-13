# SPEC 阶段研究基线（mw-dispatch-card-gate）

- key：`mw-dispatch-card-gate`｜阶段：SPEC｜日期：2026-10-12
- 状态：**PM 基线声明**（先于 3 个 RQ 落盘，用于满足派发门禁「research note 存在」；不替代 RQ 证据）

## 1. 已确认事实（本会话实测）

| 事实 | 证据 |
|---|---|
| 实现型任务可在**没有卡片**的情况下派发 | T-20：`tasks/T-20-final-ci-and-heredoc-fixes.md` 不存在，worker 在 `workers/mwgf-t20-final-fixes/report.md` 中如实上报 |
| 派发只产出 `workers/<task_key>/task.md`（由 PM 描述生成），不校验卡片 | 同上；卡片是 PM 侧产物，与派发无强制关联 |
| 卡片集合与实际派发集合会漂移 | T-20 未登记进 `plan.md` |
| 同源病症有先例 | 上一 key：守卫「形态」是假设不是事实；本 key：卡片「存在/格式/一致」是假设不是事实 |

## 2. 待取证清单（3 个 RQ，互不重叠）

| RQ | 问题 | 唯一证据文件 |
|---|---|---|
| RQ-1 | 派发路径在哪些点假设了卡存在（调用链 + 坐标 + 两种入口） | `evidence/research/spec-dispatch-path-20261012.md` |
| RQ-2 | 现有 `tasks/*.md` 语料中「上下文/要求/交付物」三段的实况分布与命名变体；最小格式候选 | `evidence/research/spec-card-format-corpus-20261012.md` |
| RQ-3 | 门禁落层（工具层/服务层/校验器）的拦截时机、可观测性、cutover 代价；如何对所有类型一致生效 | `evidence/research/spec-gate-layer-20261012.md` |

## 3. 不可复用前提（必须在 RQ 中实测）

- 不得假设"卡片格式已经统一"（可能有多种命名变体）。
- 不得假设"只有一种派发入口"（交互式工具与服务队列可能各有一套）。
- 不得假设"所有历史卡都合规"（历史卡可能普遍缺段 ⇒ 影响 AC-005 的误拒口径）。
