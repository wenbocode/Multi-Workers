"""Append MDC plan §7.2 (M-02 absorption) and note the 2nd duplicate-activation
instance in the existing RF evidence doc."""

import pathlib

REPO = pathlib.Path(r"H:\git\Multi-Workers")
PLAN = REPO / ".agenticdoc/mw-dynamic-concurrency/plan.md"
RF = REPO / ".agenticdoc/_scratch/evidence/wfg-i03-duplicate-activation-20261014.md"

PLAN_ADD = """
### 7.2 M-02 终态吸收（conductor tick 前沿消费 / roadmap 校验 / advance 打点；PM 独立复核，2026-10-14）

- **卡**：`tasks/T-C-M02-conductor-frontier.md`；写面 `autopilot/conductor.py` **唯一写者**；diff = **+364 / -31，单文件**（`git diff --stat` 实测），无遗留临时文件（`_m02_probe*.py/txt`、`_m02_body.md` 均已自行清理）。
- **回读异常（非本卡质量）**：`output.md` 主报告之后混入 **4 条 `status=failed` 的短命 `mw-run` 块**（09:01–09:05，"exited without writing output"）⇒ 这是 WFG 已定性的**重复激活缺陷 RF-1..RF-4 的第二个实例**（同一 `task_key` 多个 worker-mode 实例共写一份 `output.md`）。已追加到 `_scratch/evidence/wfg-i03-duplicate-activation-20261014.md`。主报告完整、结论有效。
- **PM 亲跑（不采信自述）**：
  - **全量 pytest 我自跑**：`6 failed, 2206 passed, 10 deselected in 317s` —— 与自报**逐字一致**。
  - **6 条红的归因（PM 逐条做完）**：① `test_autopilot_readcap_injection::test_baseline_left_end_bound` = 外部仓库冻结基线（见 §7.1）；② `test_autopilot_verdict_freshness::test_true_below_without_resume_stays_below` = **PM 用 A/B 隔离证明既有**：把包复制到 TEMP、只把 `conductor.py` 换回 `git show HEAD:` 版本，同一测试**同样失败且报错逐字相同**（`AssertionError: latest report is not from the last round; assert 3 in [2]`）⇒ 与 M-02 无因果；③④ `test_launcher::…test_bom_historical_books…` + `test_task_type_parity::test_bom_historical_books` = 别的 key 的任务书缺失（`mw-dispatch-reliability/workers/mw-dr-glm53/task.md` 不存在，语料漂移）；⑤⑥ `test_mwds_t27_service_envelope` + `test_mwds_t29_producer_signal` 的 TS 对拍 = `proc` 为 **None**（TS 子进程 runner 起不来）⇒ 即已知的 `dist/**` 未重建（本 key 遗留 #1 的同源）。**本卡新增失败 = 0（PM 判定）**。
  - **探针亲跑**：附录 A（前沿恒等/V-problem/写面/roadmap/kill-switch/advance 打点）与附录 B（写面前沿预筛）**都在原位置复跑通过**：附录 B = 全声明互不重叠 3 / 全未声明 1 / 混合 1；附录 A = `cap=4,|F|=3→3`、`cap=1→1`、链 `|F|=1→1`、`cap=2,|F|=5→2`、`|F|=0→0 且只 advance`、key 层 `mpk=2→2 / 1→1 / 8→3`、V-problem 串行回退 + 去重（tick2 累计仍 1 条）+ 下一 tick 正常推进、AC-006 `bounds 8/4→2 keys/3 rows` 与 `1/1→1 key/1 row`（同进程改配置即生效）。
  - **AC-013 量化独立复现**：PM 在原位置跑同一探针得 `ms=[243, 561, 230] median=243`、idle tick `3ms`、`window_share=0.991371`、`81.00x`、`advance event data={'ms': 243}`，落在 worker 两轮记录区间内（`[835,772,232]/0.995130/257x`、`[224,217,230]/0.986765/74.67x`）⇒ **量化成立，D-107 的执行器决定按原计划留待一周实测**。
    - **PM 的一次自我纠错（记录）**：我最初把附录 A 抽到 `_scratch/evidence/` 跑，得到 `exit=1 ms=0`（`AgenticTask framework not installed`）——原因是探针用 `HERE = __file__` 推导 `FRAMEWORK` 并写进临时根的 `.agentic-framework` 标记，抽错目录就找不到 framework。**在原位置重跑即复现**。这不是 worker 的问题，是 PM 抽取位置造成的假阴性。
  - **代码面 PM 逐点读证**（`_scratch/evidence/mdc-m02-code-audit-20261014.txt`）：`_timed_advance` 墙钟包 `advance.advance()` 并原样传递异常；`_record_advance_result(..., ms=None)` 关键字默认 ⇒ 旧调用不破；`_declared_write_face` 用 `getattr(dispatch, "_card_write_face_entries", None)` + `dispatch_card`（**纯读**，无副作用，`dispatch.py:569-599` 实测）⇒ 缺失即 fail-closed 串行，重叠判定仍归 `dispatch._write_face_verdict`；`_audit_task_graph_problems` 去重键 `(tasks dir, key)`、经 `_emit_alarm` 复用既有 `config` 事件；`_emit_roadmap_validation` **只观察**（注释与实现一致），去重键 `(path, problem)` 且修复后允许复发再报；`_stable_dependency_order` Kahn + plan 序 tie-break，环 ⇒ 回 plan 序；写面拒绝路径 `_write_face_wait_reason ⇒ return dispatched_any`（**等待而非 stall**），其它拒绝仍 `mark_stalled`；`cap = max(1, int(cfg.get("max_workers_per_key", 4)))`（防御默认 4）；`_is_in_flight`（`:3872`）与 key 层 `in_flight_keys`（`:706`）/`:752` 未被触碰（AC-012）；**新增 diff 里只出现 `advance` 一个事件名**（无新事件类型）。
- **残留（PM 判定 → 去向）**：① **跨 tick 顶配（top-up）未开**：任一在飞 key 仍跳过 `_advance_key` ⇒ 同 tick 批次内 `min(cap,|F|)` 成立，但批内 N 个 worker 全部完成前不补派；这是 AC-002 的**同 tick 语义**边界，**由 M-06 的 N≥4 端到端反证量化"批完成→下一批启动"的空窗**，不在本卡扩范围；② 未声明写面的卡会改变到达顺序（预筛把它移出并行前沿）——plan §6 直接结果，进度不丢；③ 探针 F 节不自带 framework 装配 ⇒ 复跑须在原位置（已记录方法）；④ `advance` 仍为同步 `subprocess.run`（D-107 留待一周实测）。
"""

text = PLAN.read_text(encoding="utf-8")
if "### 7.2" not in text:
    PLAN.write_text(text.rstrip() + "\n" + PLAN_ADD, encoding="utf-8")
    print("plan: appended §7.2")
else:
    print("plan: §7.2 already present")

RF_ADD = """

## 追加实例 2（2026-10-14，key `mw-dynamic-concurrency`，任务 `mdc-m02-conductor-frontier`）

同一签名再现，佐证 RF-1..RF-4 是框架级缺陷而非 `wfg-i03` 的一次性偶发：

- 主激活完整写出 `output.md`（M-02 报告 + 证据落盘）；
- 之后在 **09:01:00 / 09:03:38 / 09:04:58 / 09:05:01** 出现 **4 条** `<!-- mw-run: … status=failed -->` 块，内容均为
  "worker exited before output.md was written (crash or unexpected exit)"（即"未写 output 就退出"的短命激活）；
- 另有 1 条 **08:26:50 `status=done`** 的块（"已追加 CKPT 40m"，`writes=none`）出现在文件**末尾**，与时间序不一致 ⇒ 说明这些块由**不同激活各自 append**，顺序即竞态顺序；
- 与 `wfg-i03` 一致：多次激活共享同一個 `output.md`，每个激活各自写自己的运行块；本任务的 `task_key` 全生命周期只 dispatch 过一次（PM 侧 `list_tasks` 单一 terminal 行）。
"""

rf = RF.read_text(encoding="utf-8")
if "追加实例 2" not in rf:
    RF.write_text(rf.rstrip() + RF_ADD, encoding="utf-8")
    print("RF doc: appended instance 2")
else:
    print("RF doc: already has instance 2")
