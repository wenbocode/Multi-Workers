"""Byte-safe edit of design.md: mark D-011 as revised (T-04 R1) and add the rationale block."""

import pathlib

p = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/design.md")
lines = p.read_text(encoding="utf-8").splitlines()

assert lines[162].startswith("- **选择**"), repr(lines[162])
assert lines[163].lstrip().startswith("`_JSON_LIST_FIELDS`"), repr(lines[163])
assert lines[164].lstrip().startswith("解析期成员校验"), repr(lines[164])

lines[162] = (
    "- **选择**：~~`authorizes` 加入 `FRONTMATTER_FIELDS`（**追加到末尾，索引 40**，绝不插中间）~~ "
    "**[REVISED @ 2026-10-10 20:35（T-04 报备 R1）]** 落点改为 `_JSON_LIST_FIELDS`（单行 JSON 数组）+ "
    "`Gate` dataclass + 新闭集常量 `AUTHORIZES_ACTIONS = {\"retry\", \"contract-change\"}`，**不**进 40 名单："
)
del lines[163]  # the now-redundant `_JSON_LIST_FIELDS` continuation line

bullets = [
    "  - **40 名单保持冻结（已落地事实）**：解析面成员校验 `gates.py:507` 现为“`FRONTMATTER_FIELDS` **或** `_JSON_LIST_FIELDS`” ⇒ `authorizes` 是冻结 40 名之外的**已识别扩展字段**（值解析走 `gates.py:577`）。T-04 在代码内留注释（`gates.py:40/:168-169/:503-504`）并以 `test_autopilot_contract_guard.py:187-188` 锁住“40 名不变 + `authorizes` 不在其中”。",
    "  - **为何不追加第 41 项（接受偏离的判据）**：`FRONTMATTER_FIELDS` 是**跨语言冻结顺序**（TS 镜像 `GATE_FRONTMATTER_FIELDS`），加一项会连带打红两个锁（`test_autopilot_gates.py:224` == 40；`autopilot-gate-presentation.test.ts:206-235` 跨语言 parity）而**无功能收益**：回读路径已由 `_JSON_LIST_FIELDS` 接住；渲染路径 `_gate_file_content`（`gates.py:283`）是手写字面量、**不遍历**该名单 ⇒ **不存在“重渲染丢字段”路径**。",
    "  - **对 T-12 的硬要求**：TS 侧必须镜像同一形状（`status-model.ts` 的 `GATE_JSON_LIST_FIELDS` 加 `authorizes` + 未知字段检查放宽（约 `:811-812`）+ 闭集校验），否则会出现“`authorizes: []` 的门 Python 可解析、TS 面板跳过”的新双语言分叉（AC-015 家族）。",
    "  - **附带收益**：40 名顺序一行不改 ⇒ T-14 **无需**为本次偏离刷新那两处计数锁。",
]
lines[164:164] = bullets

for i, line in enumerate(lines):
    if line.startswith("| D-011 |"):
        lines[i] = line.replace(
            "不升 v3 |",
            "不升 v3；**冻结 40 名单之外**（`[REVISED @ 20:35]`，见上文 D-011 块）|",
        )
        break
else:
    raise SystemExit("table row for D-011 not found")

p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("choice line:", lines[162])
print()
print("\n".join(lines[163:170]))
