"""pm-state: D-063 (QG review worker empty run + corrective re-dispatch) + R22 candidate note."""

import pathlib

p = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/pm-state.md")
lines = p.read_text(encoding="utf-8").splitlines()

d62 = next(i for i, l in enumerate(lines) if l.startswith("- D-062（2026-10-10 19:50）"))
lines.insert(
    d62 + 1,
    "- D-063（2026-10-10 20:05）：**QG 复审首派空转（PM 任务书缺陷，非框架缺陷）** ⇒ `mwg-qg-review-20261010` 54s/8 次调用后 settle，"
    "`output.md` 仅是被截断的推理流水、**无 `report.md`**、未做任何审查。**根因（现场取证）**：review 角色工具白名单无 `write`/`edit`，"
    "只由 `worker-mode.ts::activeToolsForType`（`:114-117`）追加 `worker_file`；而 `worker-file-tool.ts::WORKER_FILE_NAME_RE` "
    "只接受 basename（`progress.md` / `report.md` / `report[-.]<slug>.md`）、只写进 worker **自身** task 目录、单次 ≤64 KiB UTF-8，其它路径 fail-closed 拒绝。"
    "**我却在任务书里要求它写 `evidence/quality-gate-report-review-20261010.md`** ⇒ 不可完成 ⇒ 它卡在写面矛盾上空转。"
    "**纠正动作**：该 task_key 按 AC-022 **不再复用**；改派两张**修正写面**的卡 —— `mwg-qg2a-evidence-chain`（QG Step1→5 证据链/覆盖闭合/绑定/achieved 一致性）"
    "与 `mwg-qg2b-code-adversarial`（14 项代码级对抗清单：done-guard 首写顺序、跨 key 拒绝时机、五个写者槽位保留、AC-025 不回溯、短路顺序、有界、`run.json` 身份、提醒上限、帧自证、"
    "对照承重性、两侧镜像、空洞测试抽查、卡片绑定、`achieved` 一致性），任务书已写死“唯一写入 = `report.md`（worker 自身目录），PM 收录”，并要求**先落骨架再逐条填充**以抗 premature settle。"
    "**候选框架改进（R22）**：`dispatch_worker` 对**只读角色**的任务书若出现自身目录之外的写路径（`evidence/`、`../`、绝对路径），应在派发期告警/拒绝——本次框架静默接受。"
    "派发后队列归一化：**273 行 / 全部 8 列 / unparsable=0 / version=1**。",
)

i = next(idx for idx, l in enumerate(lines) if l.startswith("- 10-10 19:50：用户要求"))
lines.insert(
    i + 1,
    "- 10-10 20:05：QG 复审首派 `mwg-qg-review-20261010` **空转未交付**（我要求 read-only 角色写到自身目录之外）⇒ 已 ack + 记录；"
    "改派 `mwg-qg2a-evidence-chain` + `mwg-qg2b-code-adversarial`（写面修正为 `report.md`）；队列 273 行 × 8 列。记 D-063（+ 候选 R22）。",
)

upd = next(i for i, l in enumerate(lines) if l.startswith("- Updated:"))
lines[upd] = "- Updated: 2026-10-10 20:05"

p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("ok")
