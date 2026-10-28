"""Append the fourth-round absorption record (W-06) plus the fingerprint
normalization note and the reachability finding for `globs_overlap`."""

import pathlib

PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\plan.md")

ADDENDUM = """
### 7.1 W-06 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核（不采信自述）**：`python -m pytest test_write_face.py -q` = **130 passed**（修复前基线 2 failed / 127 passed）；`wf-v58-probe-20261014.py` 输出 V58 = `Conflict(sample="src/x.ts", rule="src/x.ts", other="src/x.ts")`、V59 = `Unsupported(unsupported-syntax)`、V60 = `Unsupported(glob-product-state-limit)`，与 TS 侧逐条同族。
- **修复形状经 PM 读码确认**（`autopilot/write_face.py:943-977`）：单槽 `deferred`（首个遇到者胜）+ `ga.unsupported or gb.unsupported` 与 `_ConservativeUnknown` 共用该槽 + 冲突对立即 `return Conflict` + 循环耗尽后才 `return deferred`。与 `shared/write-face.ts:844` 的 `writeFacesOverlap` 逐条对应，注释里也写明了对应关系。
- **卡面 129 vs 实测 130 的解释（PM 采信）**：`129 collected` 是开工基线（127 passed + 2 failed），要求 7 强制新增 1 条独立回归测试 ⇒ 修复后 `130 collected` 全绿。卡面数字未计入新增测试，不是测试泄漏。
- **指纹口径修正（W-06 发现，PM 确认并记此）**：本仓 Windows 磁盘上的语料是 **CRLF**（130 行 ⇒ 磁盘 20126 B），而本文件各处记的 `sha256` / `bytes` 均按**LF 归一化后的内容**计（`19996 B`）。两者等价：两侧读者解析的都是同一份 JSON 内容，LF 归一化 sha 恒为 `b39f8925…`。后续引用该指纹时必须带这个口径说明。
- **遗留（本 key 只记录，不单独开卡）**：`globs_overlap`（`write_face.py:858`）仍是旧形状——`except _ConservativeUnknown` 仍包住整轮 `for ga_globs/for gb_globs/...`，混合"不可判定对 + 可证冲突对"时会提前 `return Unsupported`。**可达性实测**：唯一调用点是 `test_write_face.py:318` 的 `_go()`，恒以 1×1 列表调用；其 docstring 自述为 "direct boundary testing" 变体（每元素单个 glob）⇒ 当前**不可达**，且不在任何生产路径（`dispatch.py` 只调 `overlap()`）。触发条件与义务：一旦有卡以**多元素列表**调用它，必须同族化（按对延迟）。
"""

raw = PLAN.read_text(encoding="utf-8")
if "### 7.1 W-06 终态吸收" in raw:
    print("already recorded")
else:
    PLAN.write_text(raw.rstrip() + "\n" + ADDENDUM, encoding="utf-8")
    print("appended")
text = PLAN.read_text(encoding="utf-8")
print("lines", len(text.splitlines()), "bytes", len(text.encode("utf-8")))
print("7.1 present:", "### 7.1 W-06 终态吸收" in text)
