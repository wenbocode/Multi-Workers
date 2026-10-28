# design 阶段 RQ 计划（mw-write-face-guard）

- key: mw-write-face-guard
- phase: DESIGN
- 日期: 2026-10-14
- 上游: `spec.md`（AC-001..AC-014）、三份 spec 证据（`spec-write-face-sources/enforcement/safety-20261014.md`）、`design.md`（D-001..D-009 draft）
- 本文件是 design 阶段的**证据清单 + 派发声明**（dispatch gate 要求的 `design-*` note），不是研究结论。

## 并行性分析

- 两个 RQ 互不重叠：一个只读 glob/算子语义（`shared/read-scope.ts`、`worker/read-scope.ts`、minimatch 用法、`conductor.py` 的 blast_radius 语义），一个只读运行期闸的插入点与 bash 写目标词法（`worker-mode.ts`、`implementation-gate.ts`、`worker-file-tool.ts`）。
- 共享资源：无（各自唯一证据文件；不写生产文件）。
- 串行理由：无。两 RQ 一次并行派发。

## RQ 与唯一证据文件

| RQ | 问题 | 唯一证据文件 | 卡片 |
|---|------|-------------|------|
| RQ-D1 | 写面 glob 的最终归一语义：现有 `read_scope`/`deny_globs` 与 minimatch 的全部差异点、每个差异应取哪一侧、交集算子 `write_faces_overlap` 的规范定义 + 边界向量集（含两侧语言可实现性） | `.agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md` | `tasks/T-W-D1-glob-intersection.md` |
| RQ-D2 | 运行期写面闸扩到全角色的插入点：现有 `research` 分支的形状能否直接推广、bash 写目标的词法从哪来（复用 `implementation-gate` 的 target lexer？）、`write`/`edit`/`worker_file` 三类的判定位置、假阻（引语/文档内容）如何避免 | `.agenticdoc/mw-write-face-guard/evidence/research/design-runtime-guard-20261014.md` | `tasks/T-W-D2-runtime-guard.md` |

## 设计决策的待验项（design.md 中标 RQ 的部分）

- D-006（glob 交集算子语义）→ RQ-D1 定稿后回填 design.md §2/§3.2。
- D-007（运行期范围与插入点）→ RQ-D2 定稿后回填 design.md §1/§5。

## 不派 worker 的部分（PM 串行）

- `design.md` 正文（decision 表、接口、VC 计划）由 PM 写；不派 worker。
- 存量 419 份任务书的迁移脚本设计属 plan 阶段。
