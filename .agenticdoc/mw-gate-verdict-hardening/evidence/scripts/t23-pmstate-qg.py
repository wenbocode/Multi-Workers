"""pm-state: post-done independent QG review note (D-062) + process log."""

import pathlib

p = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/pm-state.md")
lines = p.read_text(encoding="utf-8").splitlines()

d61 = next(i for i, l in enumerate(lines) if l.startswith("- D-061（2026-10-10 19:40）"))
lines.insert(
    d61 + 1,
    "- D-062（2026-10-10 19:50）：**用户要求独立 review worker 做 QG（post-done 复审）** ⇒ 派 `mwg-qg-review-20261010`"
    "（type=review、role=review、默认模型 `timi/glm-5.3`、工具白名单只读 read/find/grep/ls ⇒ **无 bash，不能跑测试/构建/git**）。"
    "任务口径：**不采信 PM 自写的 `evidence/quality-gate-report-20261010.md`**，从 spec 25 AC / design 47 VC / Coverage Matrix 机械推导问题清单"
    "（+≥8 条自推交叉问题），回源码与 `evidence/runs/*` 逐条三态判定（✅充分 / ⚠️不足 / ❌无证据），并执行 14 条**重点对抗清单**"
    "（done-guard 是否真为第一个 check-before-write、跨 key 拒绝时机、四个写者槽位保留、AC-025 不回溯、fail-closed 短路顺序、配额/有界、`run.json` 身份与 `lost`、"
    "提醒上限、帧自证/降级帧、对照脚本是否承重、两侧镜像逐项相等、空洞测试、卡片 vc_refs 空绑定、`achieved.md` 与实际改动一致性）。"
    "唯一写入 = `evidence/quality-gate-report-review-20261010.md`。**本复审不改变 key 的 done 状态**：若发现实质缺口，按 AC-022 另开新 key/新卡（不重跑已终态 task_key）。"
    "派发后已按 D-050 纪律归一化队列：**271 行 / 全部 8 列 / unparsable=0 / version=1**。",
)

i = next(idx for idx, l in enumerate(lines) if l.startswith("- 10-10 19:40：**verify 阶段质量门"))
lines.insert(
    i + 1,
    "- 10-10 19:50：用户要求**独立 review worker 做 QG** ⇒ 派 `mwg-qg-review-20261010`（只读对抗审查，产出 `evidence/quality-gate-report-review-20261010.md`）；"
    "队列归一化 271 行 × 8 列。记 D-062。key 保持 done（复审发现缺口即另开 key）。",
)

upd = next(i for i, l in enumerate(lines) if l.startswith("- Updated:"))
lines[upd] = "- Updated: 2026-10-10 19:50"

p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("ok")
