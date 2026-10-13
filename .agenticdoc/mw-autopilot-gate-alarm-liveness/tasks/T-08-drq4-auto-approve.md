# T-08 — DRQ-4｜阻塞-派发因果链与「小 gate 自动收证 approve」

type: research
phase: design
key: mw-autopilot-gate-alarm-liveness
唯一证据文件: .agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/research/design-drq4-auto-approve-20261013.md

## 上下文（种子，不是上界）

- 项目目标锚点：`.agenticdoc/goal.md`（无人值守并行开发）。
- **用户 2026-10-13 重述的三个第一性目标**（本卡要把它落成可实现的判据）：
  1. **阻塞无感知 ⇒ 派发被卡住**（最核心，"看上去在跑，其实什么都不发生"）；
  2. **窗口并不显式 watch 某个 key** ⇒ 派发不得以"有人 watch"为前置；
  3. **autopilot = 自动驾驶，gate 越少越好** ⇒ 小 gate（stage-close / 文书型完成）应能**自动收集证据并 approved**。
- 已核实事实（可直接复核）：
  - 提醒侧四杀手：`conductor.py:2688-2735 _remind_pending_gates`（无 stderr）；`:2559-2561` cap（`config.py:57` 默认 2 且闭区间 `[1,2]`）；**`:2558` 全项目级在飞抑制**；`:2562-2566` stage 终止抑制。
  - `stalled` 出口 3 个：approve→`running`（`:3289`）、reject→`closed-legacy`（`:3340`，全历史 1 例）、延后→`pending-review`（`:3701`/`:3667`，仅 `auto_gate_mode` 开）。
  - 既有自动裁决机器：`auto_gate_mode`（`status-model.ts:101-129` 镜像）、`auto_decision_for_rule`（`conductor.py:5831`）、`gate_facts` stalled 分支（`:6083-6091`）、`_apply_stalled_approvals/rejections`（`:3313/:3319`）、文书型确定性钩子 `.mw-achieved-baddraft.json` 的 `NO MATCH: achieved.md missing pattern` + 幂等 `splice_achieved`。
  - push 消费面要求窗口正在 watch（`pm-orchestrator.ts:1466-1513`，`:1489`），丢弃点 3 处（`:1489/:1490/:1511`）；面板 `blocked_on_human` 是项目级轴、三处实现（`monitor.ts:442` 邻域 / `status-model.ts:1349-1356` / `mw_common.py:3279-3291`）。
  - 存量 gate **56**（E2Feature 26 `H:\git\E2Feature` / JCodingAss 8 `H:\git\JCodingAss` / FeatureMigrator 22 `E:\CLI_workspace\FeatureMigrator` / MW 0），v1 51 / v2 5，`blocker_class` 100% 缺；真实 pending 3（JCodingAss `gate-0007`/`gate-0008` 均 `kind: stage-close` 且 **key 为空**、年龄 25.6/17.0 天；`FeatureMigrator/gate-0022`）。
- 允许自行扩大取证（含读 `_roadmap.md` 与 gates 目录的真实分布）。

## 要求

1. **阻塞-派发因果链（第一性目标 ①②）**：从"某 key 被门禁阻塞"到"派发停止"的**完整因果路径**，逐跳 `path:line`：谁在读 gate 状态、谁据此决定不派发、哪些判断**显式要求"有人 watch/有人响应"**（列出全部此类前置点）。必须回答：**无人 watch 时，哪些动作今天会静默不发生？**（这是 AC-014 的靶子清单）
2. **gate 种类普查与"可自动收证"分级（目标 ③）**：用真实的 56 个 gate 统计 `kind` 分布；对每种 kind 给出：① 判定它需要哪些证据；② 这些证据能否**确定性机器收集**（给具体命令/判据）；③ 是否 destructive；④ 结论（可自动 approve / 只能 auto-classify / 必须人工）。**特别回答 stage-close**（存量里有 key 为空、静置 25 天的实例）。
3. **复用面**：既有 `auto_gate_mode` / `auto_decision_for_rule` / `_apply_stalled_approvals` / `splice_achieved` / `gate_facts` 各自现在能自动决定什么、缺口在哪（哪些只需接线、哪些需新写）。
4. **自动 approve 的安全边界与留痕**：`answered_by` 取值、依据字段（零新字段是否可行）、幂等性、审计面（timeline 事件名是否复用）、**失败回落**判据（收集失败 ⇒ 人工 gate，且状态面显示为何回落）。
5. **可度量**：「必须等人响应」的 gate 数/占比在改动前后的期望变化，以及**运行期可观测的验收数字**（如自动批准占比、平均等待时长）。
6. 只读；唯一允许写的是本卡声明的证据文件。

## 交付格式

证据文件必须含以下**四个 H2 段**（逐字）：
`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。
