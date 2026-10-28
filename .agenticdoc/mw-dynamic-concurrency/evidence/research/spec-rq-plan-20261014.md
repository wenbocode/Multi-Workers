# 调研声明 — spec（mw-dynamic-concurrency）

- **key**：mw-dynamic-concurrency
- **日期**：2026-10-14
- **类型**：本 key 需要代码事实调研（非零调研声明）

## 目的

把并发上限从"静态常量"改为"依赖前沿 + 配置上界"，spec 关键决策（§1 范围 / §2 约束 / §4 风险）需要现状事实：
派发链在哪些点被串行化、依赖数据今天有什么载体、配置语义与两侧镜像的变更面。三项调研**只读**、互不重叠、各写唯一文件。

| RQ | 问题 | 产出文件（唯一写者） |
|---|---|---|
| **RQ-C1** | 派发链与串行点：conductor 每 tick 派发链、per-key 硬串行点、PM 手工通道入口；两条通道共用队列与唯一消费者的逐行证据；"放开点"清单与各自的并发安全性 | `evidence/research/spec-dispatch-chain-20261014.md` |
| **RQ-C2** | 依赖数据源：key 级 `depends_on`（roadmap）语义与解析；任务级依赖今天有什么机器可读载体（plan.md 顺序 / 任务卡字段 / wave / deps），缺什么；前沿计算所需数据与缺口 | `evidence/research/spec-dependency-sources-20261014.md` |
| **RQ-C3** | 配置与镜像：`max_parallel_keys` 语义/floor/取值域/生效链；`effective_config` 机器层键域；TS `status-model.ts` 镜像与 parity 语料；既有 materialized config 的兼容/迁移面 | `evidence/research/spec-config-mirror-20261014.md` |

## 事实基线（可直接引用，须自行复看确认）

- key 层唯一闸：`packages/multi-workers/autopilot/conductor.py:744`；per-key conductor 串行 = 1（`:742-745`、`:1771`）。
- 配置：`autopilot/config.py:87`（默认 2）、`:122`（`(2, None)` = floor 2 无上限）；TS 镜像 `status-model.ts:136,196`。
- 两条通道共用队列 + 唯一消费者：`packages/multi-workers/launcher.py:819-841`。
- 前置件：`mw-write-face-guard`（本 key 的 `deps`）。

**约束**：三项 RQ 全为**只读**；不得改任何生产文件；结论必须给 `file:line` + 原文片段，未找到写"未找到（命令 + 输出）"，
禁止推测补齐；推算值必须标注。
