# Research: 问题背景与根因语料（spec）

## 决策问题

回答 spec 的 §1.1（问题背景与根因）与 §1.4（范围取舍）：这条治理通道的需求依据是什么、根因在哪一层、为什么现在机制化。

## 调研方法与出处

- **语料（逐字）**：`E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\evidence\cross-key-repair-request-20260925-n1.md`（全文已读，76 行；本会话直接读取）
  - `:6` `request_id : XKEY-2026-09-25-01`
  - `:7` `status : pending-human-authorization（未授权前不动任何文件）`
  - `:8` `affected_keys : cli-run-state-and-events（红之来源）· cli-hitl-channel（守卫所在 key）`
  - `:9` `memory_refs : reflect/plan-writeface-gap.md（A-06 同族：红无 owner）`
  - `:14-20` 复现事实：`[COUNT] cli_groups=13`，groups 列表含 `runs`；`tests/test_hitl_channel.py:268` 期望 12 组
  - `:24-28` A 侧 L3 原文：`[VERIFY] REPAIR-R1-F1: cross_key_test=tests/test_hitl_channel.py::test_top_level_command_groups_unchanged`、`rc=1 cli_groups=13 frozen_groups=12 owner=cli-hitl-channel handoff=registered not_fixed_by_this_key=True`；"F-1（跨 key 红）未闭合（按设计）…… owner=cli-hitl-channel，挂账交接、本 key 写面外不修，纪律正确"
  - `:29` B 侧 L3 原文：`K-1 兄弟 key 新增顶层命令 runs 下本 key PG-2 断言（12 组）红，owner 在跨 key 修复轮（不在本 key 写面内）`
  - `:31` 归纳："**同一处红被两边都正确登记，但没有任何 key 的写面覆盖它**（A-06 的跨 key 版本）"
  - `:35-39` 候选处置 R1/R2/R3（PM 建议 R1：只改冻结期望、不改断言逻辑，附 sha256+reason+复跑绿证+全量对照）
  - `:43-47` 拟授权精确边界：唯一可写路径 `tests/test_hitl_channel.py`；禁止改断言主体/`ANSWER_OK_KEYS`/负例探针/`migrator/**`/放宽判据
  - `:56` 追认入口："在本文末追加一行：`decision: <approved|rejected> by <who> at <ts>`"
- **框架时序证据**（本会话直接读取）：`E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\timeline.jsonl` 尾部——重启后新 conductor `goal-snapshot`（本地 10:30:43）→ `gui-live-monitor` / `gui-run-control-hitl` 依次 `design->plan->tasks`（至本地 10:46），说明任务链在跑、且该红不在当前活跃 key 的推进路径上。
- **既有项目记忆**：`.agenticdoc/_arch_snapshot.md`（§1.3 文件驱动协调 GC-1；§2 资产清单）、`.agenticdoc/_pitfalls.md`（P-001…P-015 标题全列已读）。
- **本会话已核实的代码事实**（供 RQ-1 深化，非最终）：
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts` `startMw()`：`spawn(PYTHON_EXE, [mwPy, "start", "--project=..."])`，不传 `env` → **继承执行窗口的 process.env**（与本次 P-015 相关）
  - `packages/multi-workers/mw.py` `cmd_start()`：`[sys.executable, mw.py, "serve", ...]`，未带 `-X utf8`（与 P-015 相关）
  - `packages/multi-workers/mw.py:214-222`：`mw.log` / `launcher.log`（每 session 截断）/ `conductor.log`（每 session 截断）的落点

## 发现

1. **跨 key 红的"无 owner"是结构性的，不是纪律失误**。两侧 L3 都按写面纪律正确拒修（`:24-29`），红的 owner 字段指向一个**已 DONE 的 key**（`:8` `cli-hitl-channel`），框架状态机里没有"治理级修复"通道，于是红在机制层面无处可去。
2. **检测已存在、授权已存在，缺的只是传导通道**：L3 全量扫描发现了红并登记了交接（`:24-28`），人也具备解冻能力（`:7` pending-human-authorization、`:56` 追认入口），但两者之间没有机器通道——**人手工写了一份申请文件来代替通道**。
3. **该申请文件本身就是一个被散文写出来的状态机**：`request_id / affected_keys / 候选处置 / 拟授权边界 / 追认入口 / decision:` —— pending → 授权 → 受限修复 → 证据包 → 闭合，除"授权"外每步可机械判定/执行/验证。这是机制化的直接证据。
4. **复发信号**：`:9` 明写 `A-06 同族：红无 owner`——同类问题此前出现过（A-06），本次是第二次。第二次出现即"停止手搓协议"的信号。
5. **二阶根因（聚合缺失）**：同一处红被两个 key 各自登记（`:24-29`），但没有任何跨 key 的聚合视图——信息局部记录、全局孤立，红只能停在各自报告里靠人眼对上。
6. **边界收窄是可能的**（设计可行性证据）：因为耦合边精确指名了那一个断言与那一个冻结常量（`:14-20` 精确到 `:268` 与 `TOP_LEVEL_GROUPS`），`拟授权边界` 可以精确到"file + 冻结常量块"（`:43-45`），从而最小改动的机械强制是可行的。

## 结论 → 决策映射

| 结论 | 支撑的 spec 决策 |
|---|---|
| 1 + 2（检测/授权都在、缺通道） | §1.1 根因第 3 层；§1.1 "本 key 做什么"= 补通道，而非补检测或补授权 |
| 1（owner 指向终态 key；写面分区 vs 非分区耦合图） | §1.1 根因第 2 层；§1.4 不改写面模型（不把 B 的文件划给 A） |
| 2 + 3（冻结快照的权威被钉在关闭点） | §1.1 根因第 4 层；§2.3 解冻权只给人 |
| 3 + 6（边界可精确收窄） | §2.3 边界机械强制；AC-005 精确到冻结常量块行集合 |
| 4（A-06 同族、复发第二次） | 本 key 立项理由（§1.1 "为什么机制化"）；§4 R-1 要求机器可读化交接登记，避免再次靠散文 |
| 5（聚合缺失） | §1.1 二阶根因；AC-001 账本聚合与幂等去重 |
| 6（边界可精确） | §2.2 增量扫描；AC-003 工单含精确边界 |

**待深化（已派 RQ-1/RQ-2/RQ-3）**：交接登记现状是否为机器字段（R-1 风险）；A-06 原始记录的逐字内容与闭合方式；仓内可复用件的精确落点。
