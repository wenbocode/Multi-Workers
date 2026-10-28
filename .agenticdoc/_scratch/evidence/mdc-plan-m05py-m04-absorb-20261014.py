"""Append MDC plan §7.4 (M-05 Python half) and §7.5 (M-04 dispatch dedup) + note
the two record-keeping lessons found while verifying them."""

import pathlib

PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-dynamic-concurrency\plan.md")

ADD = """
### 7.4 M-05 Python 半边吸收（VC-101/102/103/104；PM 独立复核，2026-10-14）

- **卡**：`tasks/T-C-M05-tests-python.md`；**只新增一个测试文件**、零生产改动：`packages/multi-workers/test_mdc_concurrency.py`（523 行 / 10 条具名测试：VC-101 ×4、VC-102 ×1、VC-103 ×1、VC-104 ×4）。
- **PM 亲跑**：`python -m pytest -q test_mdc_concurrency.py` 由 worker 报 10 passed；我复核其**归因错误**（见下）并跑相邻套件：`test_task_graph.py` + `test_write_face.py` + `test/test_write_face_dispatch.py` **231 passed**、conductor/dispatch 组（`test_autopilot_conductor_exec`/`_conductor`/`_conductor_stage`/`_autopilot_dispatch`/`_dispatch_models`/`_partition_dispatch`/`_mwds_t10`）**186 passed**。
- **worker 的归因错误（PM 修正，记录以免污染基线）**：它把全量 `7 failed/2215 passed` 相对基线的"第 7 条红"归给 `test_autopilot_readcap_injection::test_baseline_left_end_bound`——但那条**本来就在基线的 6 条里**。真正的算术是：10 条新测试全过（2216 期望），有**一条既有绿测变红**。PM 用 `-rf` 全量定位到真凶：`test_rag_launcher.py::TestDispatchRagBlock::test_dispatch_end_to_end_is_stable`（属 M-04 面，见 §7.5），另有 `test_rag_init.py::RagInitTest::test_vc204_zero_interaction` 一条**假红**。
- **假红的根因（新记录）**：`test_rag_init` 那条**单独跑绿**（`12 passed`）；它出现在我的全量跑里是因为**两个全量套件（我的 + M-04 的）同时在跑**，共享临时状态/锁 ⇒ 幻影红。教训：**全量套件必须串行跑**，并行 worker 的全量 pytest 与我自己的全量 pytest 不得重叠。
- **测试诚实性（PM 读码判定）**：期望值取自语料构造规模（未用 `task_graph.frontier` 自证）；VC-104 的写面重叠被拒时断 `stalled_events=0` 且 key 仍 `running`（正是等待类语义）；队列口径为真实 `.agenticdoc/_workers.parallel`（`mw_common.parse_workers_file`）。
- **残留**：① 本卡用注入缝替 `advance.advance`（no-op），未 spawn 真实 phase 子进程（AC-013 的真实量化由 M-02 §6 + PM 复现承担）；② 队列路径口径以 `mw_common.workers_path` 为准（卡文写的 `<key>/workers/_workers.parallel` 不准确，PM 记责）；③ 对 M-04 的并行改动免疫（不断言旧行为/不断言 `duplicate-dispatch`），但若 M-04 语义再变需重跑本文件。

### 7.5 M-04 吸收（派发层 identity 级去重；PM 独立复核，2026-10-14）

- **卡**：`tasks/T-C-M04-dispatch-identity-dedup.md`；写面 `autopilot/dispatch.py` + `conductor.py` 一处有界改动 + `test/test_write_face_dispatch.py`（卡内允许）。
- **PM 亲跑其附录 A 探针（原位置）= 完全复现**：direct-entry 与 conductor-entry 各 5 连跑均 `grants=1 refusals=1 rows=1 dispatch_events=1`，reason `duplicate-dispatch: ap-k1-T-01-x already in flight (pending)`；conductor-entry 附 `stalled_events=0 roadmap_key_status=running`（**我 3b 要求的等待类语义成立**）；正常 `conductor.tick` 路径 `refusals=0`（**无误拒**）；终态重派 `first_ok=true second_ok=true rows=1 dispatch_events=2`。
- **代码面 PM 逐点读证**（`dispatch.py:1463-1505`）：守卫**在已持锁临界区内**（`_write_face_verdict` 之后、`mkdir` 之前）；**零副作用**（先于任何 mkdir/write/事件返回）；identity 判据（`task_key` 相等 ∧ `status not in mw_common._TERMINAL_STATUSES`，**单一终态来源**、未自建）；**未再 `acquire_lock`**（RQ-D3 的 14.6h 退避风险规避）；终态旧行走 upsert（重试路径不被封）；**无新事件名**（拒绝以"缺少 `dispatch` 事件 + reason"可观测）；reason 逐字符合卡文钉死的格式。`conductor.py` 仅 `_WRITE_FACE_WAIT_REFUSALS` 元组 + 注释（常量名/函数名/调用点零改动），`_write_face_wait_reason` 仍只此一处谓词。
- **测试改动是收紧而非放宽（PM 逐行读证）**：`test_same_task_key_is_not_self_refused_by_the_write_face_gate` 现断言第二次被拒为 `duplicate-dispatch:` + `task_md is None` + 恰好 1 行；`test_race_same_task_key_exactly_one_grant` 现断言**恰好 1 grant / 1 refusal（`duplicate-dispatch:`）/ 1 个 `dispatch` 事件 / 1 行，且明确不是 `write-face-overlap`**；新增 `test_duplicate_dispatch_refusal_is_a_wait_class_refusal` 钉住等待类元组 + 共享谓词 + 作者错误仍走 stall。`test/test_write_face_dispatch.py` 因是 untracked 文件，`git diff` 看不出改动（PM 直接读内容核对）。
- **`test_rag_launcher.py` 的既有断言由 PM 机械重修（本 key 合法作废，未删/未跳/未放宽）**：原断言"同 identity 连续派发两次、第二次仍 `ok` 且 task.md 逐字节相同"直接编码了 M-04 要修的"在飞行被覆盖重派"行为。PM 在两次派发之间插入 `mc.update_status(self.root, first.task_key, "done")`（自带锁的既有 API），使其走**合法重派路径**并保留全部原断言（含逐字节相等）；注释指明守卫自身的拒绝由 `test/test_write_face_dispatch.py` 钉住。改后 `test_rag_launcher.py` **19 passed**、`test_rag_init.py` **12 passed**、M-04 套件 **160 passed**。
- **RF 关联（重要）**：守卫的注释与本 key 的 `_scratch/evidence/wfg-i03-duplicate-activation-20261014.md` 互指——`upsert_worker_row` 按 `task_key` **无条件替换**（不区分旧行是否在飞）正是 RF-1..RF-4 重复激活的机制面，M-04 的 identity 守卫是**根修候选**。后续新 key 追查 spawner 时应先验证该守卫是否已覆盖观测到的重复激活路径。
- **残留**：① 其它 dispatch 调用点（L3/repair/roadmap/phase-writer）未逐个接入"等待"分支，按卡片 3b 只改了元组，其处理与既有写面拒绝同形；② `parse_workers_file` 会丢弃不可解析行，故不可解析行无法参与 identity 判定（与上方 `_write_face_verdict` 同口径，非新增面）；③ PM 全量跑与 worker 全量跑重叠导致的幻影红（已记 §7.4）。
"""

text = PLAN.read_text(encoding="utf-8")
if "### 7.4" not in text:
    PLAN.write_text(text.rstrip() + "\n" + ADD, encoding="utf-8")
    print("plan: appended §7.4 + §7.5")
else:
    print("plan: §7.4 already present")
print("plan.md lines =", len(PLAN.read_text(encoding='utf-8').splitlines()))
