# design 阶段 RQ 计划（mw-dynamic-concurrency）

- key: mw-dynamic-concurrency
- phase: DESIGN
- 日期: 2026-10-14
- 上游: `spec.md`（AC-001..AC-013）、三份 spec 证据（`spec-dispatch-chain/dependency-sources/config-mirror-20261014.md`）、`design.md`（D-101..D-109 draft）
- 本文件是 design 阶段的**证据清单 + 派发声明**（dispatch gate 要求的 `design-*` note），不是研究结论。

## 并行性分析

- 三个 RQ 的读取面互不重叠：RQ-D3 只读队列/锁/两条通道的入队路径；RQ-D4 只读任务卡头解析、plan 排序、任务图校验；RQ-D5 只读配置双镜像、parity 语料、面板口径与 `advance` 调用点。
- 共享资源：无（各自唯一证据文件；不写生产文件）。
- 串行理由：无。三个 RQ 一次并行派发。

## RQ 与唯一证据文件

| RQ | 问题 | 唯一证据文件 | 卡片 |
|---|------|-------------|------|
| RQ-D3 | 在飞判定进锁的可行设计：`.mw/workers.lock` 临界区内要读/判/写什么、两条通道各自的最小改动、`task.md` 先于锁创建如何改、如何用双进程对拍证明"同 task_key 只 append 一次"，以及锁粒度对吞吐的影响 | `.agenticdoc/mw-dynamic-concurrency/evidence/research/design-lock-critical-section-20261014.md` | `tasks/T-C-D3-lock-critical-section.md` |
| RQ-D4 | 任务级依赖载体的落地设计：`deps:` 卡头语法与解析落点、派发头回显、V1–V7 校验（含环/悬空/跨 key/重试代数归一）的实现位置、`_plan_task_order` 的替换与 fail-closed 回退、任务前沿的计算与"在飞卡身份"的比较 | `.agenticdoc/mw-dynamic-concurrency/evidence/research/design-task-deps-20261014.md` | `tasks/T-C-D4-task-deps.md` |
| RQ-D5 | 配置与呈现的改动集：`max_parallel_keys` 默认/floor 变更 + 新键 `max_workers_per_key` 的完整落点、parity 语料重冻步骤与计数锁清单、面板三量（上界/effective/前沿）的口径统一 + `advance` 阻塞量化方案 | `.agenticdoc/mw-dynamic-concurrency/evidence/research/design-cap-and-status-20261014.md` | `tasks/T-C-D5-cap-and-status.md` |

## 决策的待验项

- D-105（锁临界区）→ RQ-D3 定稿后回填 design.md §3.3。
- D-103/D-104（任务级依赖与校验）→ RQ-D4 定稿后回填 §3.2。
- D-101/D-102/D-107/D-109（配置、呈现、阻塞）→ RQ-D5 定稿后回填 §2/§3.1/§4。

## 不派 worker 的部分（PM 串行）

- `design.md` 正文（决策表、接口、VC）由 PM 写。
- 前置 `mw-write-face-guard` 的机制不在此 key 内重做；此处只引用其 AC-005 作为 VC-105 的判定依据。
