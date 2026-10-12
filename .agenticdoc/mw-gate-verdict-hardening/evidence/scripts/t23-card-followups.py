"""Append PM follow-up records to the T-04 and T-12 cards (T-04 R1 deviation)."""

import pathlib

root = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/tasks")

t04 = root / "T-04-contract-guard.md"
t12 = root / "T-12-g3-writer-g4-rearm.md"

t04_block = """

## PM 追记（2026-10-10 20:35，派发后）

- worker 报备 **R1**：design D-011 原写“`authorizes` 追加到 `FRONTMATTER_FIELDS`（索引 40）”，但这会同时打红两处**无人认领**的锁（`test_autopilot_gates.py:224` == 40；TS 跨语言 parity `autopilot-gate-presentation.test.ts:206-235`）。
- **PM 裁决：接受偏离**（判据：解析面成员校验 `gates.py:507` 已接受 `_JSON_LIST_FIELDS` 名；渲染路径 `_gate_file_content`（`gates.py:283`）是手写字面量、不遍历该名单 ⇒ 无“重渲染丢字段”路径；40 名顺序保持冻结反而免掉了 T-14 的两处锁刷新）。design D-011 已打 `[REVISED @ 2026-10-10 20:35]` 并附完整理由。
- **连带硬要求（已写入 T-12 卡）**：TS 侧必须镜像同一形状（`GATE_JSON_LIST_FIELDS` 加 `authorizes` + 未知字段检查放宽 + 闭集校验），否则出现“Python 可解析、TS 面板跳过”的新双语言分叉。
- PM 独立复核：`authorizes ∈ gates._JSON_LIST_FIELDS` ✓、`len(_REQUIRED_FIELDS) == 6` ✓、`AUTHORIZES_ACTIONS == {contract-change, retry}` ✓、`test_autopilot_gates.py + test_autopilot_gate_schema_v2.py + test_autopilot_contract_guard.py` = **80 passed** ✓、`contract_guard.py` 37 个公开符号。
"""

t12_block = """

## PM 追记（2026-10-10 20:35，T-04 R1 的连带要求）

T-04 把 `authorizes` 落成“**冻结 40 名单之外的已识别扩展字段**”（`_JSON_LIST_FIELDS` 成员；design D-011 `[REVISED @ 2026-10-10 20:35]` 有完整理由）。TS 侧**必须**镜像同一形状，否则 `authorizes` 会在 TS 面板被当未知字段跳过（Python 可解析 / TS 不可见的新分叉）：

- `autopilot/status-model.ts` 的 `GATE_JSON_LIST_FIELDS`（单行 JSON 数组字段集）加入 `"authorizes"`；
- 未知/未识别字段检查（T-04 报告定位在约 `:811-812`）相应放宽到“`GATE_FRONTMATTER_FIELDS` **或** `GATE_JSON_LIST_FIELDS`”；
- 值校验加闭集 `{retry, contract-change}`（越界 fail-closed，与 Python `AUTHORIZES_ACTIONS` 逐字同集）；
- `GATE_FRONTMATTER_FIELDS` 的 **40 名顺序一行不改**（跨语言 parity 锁 `autopilot-gate-presentation.test.ts:206-235` 依赖它）。
- 非空洞对照：造一个带 `authorizes: [\"contract-change\"]` 的门文件 ⇒ TS 侧必须能解析并保留该字段；摘掉 `GATE_JSON_LIST_FIELDS` 那一项 ⇒ 对应用例必须转红。
"""

for path, block in ((t04, t04_block), (t12, t12_block)):
    text = path.read_text(encoding="utf-8")
    if "PM 追记（2026-10-10 20:35" in text:
        print(f"skip (already appended): {path.name}")
        continue
    path.write_text(text.rstrip() + "\n" + block, encoding="utf-8", newline="\n")
    print(f"appended {len(block)} chars to {path.name}")
