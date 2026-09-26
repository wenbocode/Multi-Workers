# T-06 conductor 应用/验证/证据/闭合段（W 单写者，conductor.py）

key: `xkey-repair-mechanism` · 依赖: T-01（`autopilot/xkey.py` 已落地）+ T-03（挂载已落地） · 覆盖: VC-005,006,007（+AC-005/006/007）

## 背景

T-03 只交付了 `detected → ticketed → gate → approved`。**apply / verify / evidence / close 段缺失**（已核实 `conductor.py` 中零处 `check_boundary` / `apply_block_replace` / `run_verification` / `evidence_bundle_write` 调用）。本卡补齐。

## 入口与阶段（逐段实现，每步失败都不覆盖、不静默）

**入口**：工单状态为 `approved`（T-03 的 `_consume_xkey_gate:2657` 置位）**且**存在提案文件 `.agenticdoc/_autopilot/xkey/evidence/<request_id>/proposal.md`。

- **S1 提案解析**：frontmatter `file` / `line_range` / `old_block_sha256` + 围栏代码块承载新块内容（逐字保留换行，D-012 字节精确）。三项元数据必须与工单 `frozen_block` **逐字一致**，不一致 ⇒ 按 S2 的违规处理（不尝试修复）。
- **S2 边界前置校验（AC-005）**：调 `xkey.check_boundary(proposal, ticket)`。`"violation"` ⇒ 状态置 `boundary_violation`、**零写盘**、账本 `history` 追加、写 escalation；被涉及文件 sha256 必然等于工单创建时值（由构造保证）。
- **S3 应用（D-005 前置校验 + 快照兜底）**：应用**前**把目标文件按字节复制到 `evidence/<request_id>/runs/<ts>/pre-apply.bak`；再调 `xkey.apply_block_replace(root, ticket, new_bytes)`（其内部会重算块 sha，漂移即 raise ⇒ 捕获后置 `boundary_violation`，**不写盘**）；记录新块 sha 与新文件 sha256。
- **S4 验证执行（D-007）**：`xkey.run_verification(list(cfg["xkey_verify_cmd"]), cwd=str(project_root), run_dir=<evidence/<request_id>/runs/<ts>>, timeout=cfg["xkey_verify_timeout_s"])`。红数对比：before = 工单记录的红数，after = 返回的 `red_counts`。
  - **未转绿（红数上升或持平由你按 run_verification 的 `red_counts` 语义判定）⇒ 从 `pre-apply.bak` 按字节还原目标文件（还原后必须校验 sha256 == 工单创建时值）**，状态置 `verify_failed`，写 escalation，**不得闭合**（fail 方向永远不覆盖）。
- **S5 证据包（AC-006）**：调 `xkey.evidence_bundle_write`，五项语义齐备：`old_sha256`/`new_sha256`（文件级）、`reason`、`relaxed_assertion=False`、定向复跑命令 + 原始 stdout 路径、红数 before→after。`closed` 由模块返回（缺项 ⇒ False ⇒ 不得闭合）。
- **S6 闭合（AC-007）**：仅当 S4 转绿 **且** S5 `closed=True` ⇒ 账本行置 `closed`；**两个受影响 key 的闭合标注写进账本行本身**（`source` 的交接登记 + `owner` 的遗留登记，账本内两处标注），**不得写任何受影响 key 的文件**（D-004：DONE key 不可写、跨 key 无单 owner）。重复闭合必须幂等（无新增行、无重复标注）。

## 挂载与不变量

- 挂在 `_xkey_aggregate`（`conductor.py:224` 处的 `if cfg.get("xkey_repair", False):` 门控内）之后——同一门控内新增调用 `_xkey_apply_stage(project_root, st, status_of, cfg)` 即可；必须在 gate 消费（step F）之后，使本 tick 的 approve 立即可见。
- **零私有状态**：不得在 `ConductorState` 加内存游标；所有阶段从盘重派生（读工单状态 + 提案/证据文件是否存在 + 账本 history）。
- **异常隔离**：本段任何异常不得打断 tick（捕获 + timeline 事件 + 工单留在上一个良好状态）。
- 惰性 import 继续（`_xkey()` 已有），开关关闭时零 import、零行为变化（AC-008）。

## 验收（必须给真实输出）

- 自建 scratch fixture（写 `.tmp/`，跑完删；**不要**读 FM 树、不要改 FM）：一个含"冻结常量 + 断言"的小项目，先红；构造提案文件 ⇒ 走完 S1→S6 ⇒ 断言：文件 sha 变化、验证转绿、证据包 `closed=True`、账本 `status == closed`、两处闭合标注存在、**重复跑一遍 tick 后账本行数与标注数不变**（幂等）。
- 违规路径：提案 `line_range` 越界 / 改断言主体 ⇒ 状态 `boundary_violation` 且目标文件 sha256 **等于工单创建时值**（零残留）。
- 验证失败路径：构造"验证后仍红" ⇒ 状态 `verify_failed` **且文件字节已还原**（sha256 等于创建时值）。
- 焦点回归：`python -m pytest -q test_autopilot_xkey_registration.py test_autopilot_gates.py test_autopilot_fail_marker_forms.py`（加 `-s`）无新增失败（既有 2 条外域先在红见 T-03 报告）。

## 纪律

- **只写 `autopilot/conductor.py`**（+ 报告 + `.tmp/` scratch）。不改 `xkey.py`（T-01 的公开面只调用）、不改 config.py、不改任何测试文件、不改 TS。
- `_parse_l3_output` / `_md_section` 区域禁改（sha 锁）；`test_frozen_anchors_and_criteria_unchanged` 冻结的 4-tuple arity 保持不变。
- 不跑全量套件（PM 在 T-06 之后统一跑）；不 commit。
