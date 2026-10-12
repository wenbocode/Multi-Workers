"""QG-B 复审后的 PM 更正：质量门报告 §2/§4/§5 + achieved.md + pm-state D-064。"""

import pathlib

KEY = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening")


def edit(path: pathlib.Path, pairs):
    t = path.read_text(encoding="utf-8")
    for old, new in pairs:
        assert t.count(old) == 1, (path.name, t.count(old), old[:70])
        t = t.replace(old, new)
    path.write_text(t, encoding="utf-8", newline="\n")
    print("edited", path.name)


# ── 1. 质量门报告：降级 AC-007 / AC-024，撤回 T-20 不实声称，加 §8 更正 ──────────
qg = KEY / "evidence" / "quality-gate-report-20261010.md"
edit(
    qg,
    [
        (
            "## 2. AC 矩阵（25/25 PASS）",
            "## 2. AC 矩阵（23 PASS + 2 ⚠️ PARTIAL —— 复审后更正，见 §8）",
        ),
        (
            "| **AC-007** | G2 | **PASS** | T-07 只对 `status==pending` 生效（已答/终态 stage/无 gate 均不产事件） | `test_autopilot_gate_reminder.py` 非空洞对照 3 组 |",
            "| **AC-007** | G2 | **⚠️ PARTIAL** | T-07 只对 `status==pending` 生效（**已答 gate 与“无 gate”**不产事件）；**“已终态 stage 的 gate”未实现**：`gates.pending_gates`（`gates.py:770-772`）只按 `status==\"pending\"` 过滤整个 gates 目录、`_remind_pending_gates`（`conductor.py:2564`）不做 stage 范围过滤、`pending_gate_reminders` 三条件（`conductor.py:2541-2551`）无 stage 终态判据 | 复审反证 QG-B #14①（PM 已独立复现）；`test_autopilot_gate_reminder.py` 3 组对照只覆盖已答/无门/在飞行 |",
        ),
        (
            "| **AC-024** | G6 | **PASS** | T-22 `ui-bridge.ts` `foreignLiveClaimRefusal` + `dispatch_worker`（显式 key）/`advance_phase` 先拒后动，返回 `[cross-key-read-only]`；读面零改动 | `t22-controls.ps1` 4 组全红 + 还原；`worker-crosskey-readonly.test.ts` 4 例 |",
            "| **AC-024** | G6 | **⚠️ PARTIAL** | T-22 `ui-bridge.ts` `foreignLiveClaimRefusal` + `dispatch_worker`（显式 key）/`advance_phase` 先拒后动，返回 `[cross-key-read-only]`；读面零改动 —— **AC 字面点名的两个工具成立**；但 `/worker` handler（`ui-bridge.ts:1710`，注册于 `pm-orchestrator.ts:1059`）经 `resolveOwnerKeyWithSync`（`:66-67`）直通后未调用守卫（全仓仅 `:1333`/`:1698` 两处调用），仍可对他人 live key 写 `task.md` + 队列行（`:1813-1819`），而拒绝文案 `:241-242` 自称 `/worker` 已拒 ⇒ 文案与实现不符 | `t22-controls.ps1` 4 组全红 + 还原；`worker-crosskey-readonly.test.ts` 4 例；复审反证 QG-B #2（PM 已独立复现） |",
        ),
        (
            "| T-20 | `t20-controls.ps1` A–G 全红 + 还原（其中控制 B 曾因**不承重**被替换为承重变异） | `t-20-run-identity-report.md` |",
            "| T-20 | `t20-controls.ps1` A–G 全红 + 还原 | `t-20-run-identity-report.md`（**原括号“控制 B 曾因不承重被替换”已撤回：无工件支持，见 §8**） |",
        ),
        (
            "6. **PM 直执的小改已复核**",
            "6. **本次 QG 的判定层级 = 源码 + 证据级**；独立 review 复审（`workers/mwg-qg2b-code-adversarial/report.md`）后 **AC-007 / AC-024 降级为 ⚠️ PARTIAL**、§4 一条不实声称撤回 —— 全部更正见 **§8**。\n"
            "7. **PM 直执的小改已复核**",
        ),
        (
            "**结论：AC 25/25、VC 47/47 PASS（源码+测试级）；新增红 0；唯一交付缺口是运行时切换（R21，待用户批准）。**",
            "**结论（复审更正后）：AC = 23 PASS + 2 ⚠️ PARTIAL（AC-007 已终态 stage 未实现；AC-024 `/worker` 未受守卫且文案不符）、VC 47/47 按其字面成立；新增红 0；交付缺口 = 运行时切换（R21）+ 上述 2 个代码缺口（待新 key 修复）。**",
        ),
    ],
)

# 追加 §8（正文之后）
qg_text = qg.read_text(encoding="utf-8")
qg.write_text(
    qg_text.rstrip("\n")
    + "\n\n"
    + """## 8. 复审更正（2026-10-10 20:40）——独立 review 反证 + PM 独立复现

来源：独立代码级对抗复审 `workers/mwg-qg2b-code-adversarial/report.md`（`[VERIFY] QG-B: items=14 confirmed=12 refuted=2 undecided=0 hollow_controls=0 hollow_tests=0 mirror_mismatch=0 conclusion=conditional`）。
下表每条都由 **PM 亲自复现**（不采信 worker 结论本身）：

| # | 本报告原判定 | 复审反证 | PM 独立复现（坐标） | 处置 |
|---|---|---|---|---|
| 1 | AC-007 = PASS | **“已终态 stage 的 gate”未实现** | `gates.pending_gates`（`gates.py:770-772`）= 整个 gates 目录按 `status=="pending"` 过滤，无 stage 范围；`_remind_pending_gates`（`conductor.py:2564`）直接使用；`pending_gate_reminders` 三条件（`conductor.py:2541-2551`）无 stage 终态判据 ⇒ 人工关闭 roadmap stage 而门未答时仍会提醒 | 本条降级 **⚠️ PARTIAL**；代码缺口 → 遗留（新 key） |
| 2 | AC-024 = PASS | **`/worker` 未受守卫 + 拒绝文案自相矛盾** | `foreignLiveClaimRefusal` 全仓仅 2 个调用点（`ui-bridge.ts:1333`、`:1698`）；`/worker`（`registerWorkerCommands` `:1710`，注册 `pm-orchestrator.ts:1059`）经 `:66-67` 显式 key 直通且无守卫，`fs.mkdirSync`+`writeFileSync` task.md `:1813-1816`、`dispatchTask` `:1819`；拒绝文案 `:241-242` 明写 “Refused: dispatch_worker, **/worker**, advance_phase…” | 本条降级 **⚠️ PARTIAL**；缺口 → 遗留（新 key，含“扩守卫 vs 改文案”口径待裁） |
| 3 | §4 T-20 行括注“控制 B 曾因**不承重**被替换为承重变异” | **无工件支持**：该说法只出现在本报告；被引来源 `t-20-run-identity-report.md` 全文无此句、`tasks/T-20-run-identity-state.md` 对照表也只有当前 B，且无任何工件记录“原控制 B”是什么 ⇒ 违反 AC-014/VC-018 的锚点要求 | `rg` 两个被引文件均无该断言（0 命中） | **撤回该括注**；`t20-controls.ps1` 当前 7 组经复审静态判定全部承重（27 组变异点均落在判据行） |

**复审确认的已声明边界（非新缺陷，无需动作）**：

1. 空队列 + 产物证据守卫位于 per-owner 循环内（`pm-orchestrator.ts:653`，循环起于 `:595`）⇒ 混合场景下“新增行数 = 0”只按 owner 成立；`t-15-t17-t19-report.md:98` 已如实登记该取舍。
2. `readMonitorState` 的 per-section catch（`monitor.ts:362/376/432`）静默给空段，仅整体抛错才降级 —— 与本报告 §5.1 已声明的“widget 写失败静默”同族。
3. `STALL_REASON_CODES`(14) 无 TS 镜像 —— 两侧从未声称镜像，不计不符。

**复审未否证的项**：done-guard 首个 check-before-write（`conductor.py:2244` 严格先于 `:2278/2287/2297/2317/2331/2334` 全部写盘）、五个队列写者槽位保留、AC-025 首见冻锚（仅 design/plan、非空不重写、CLI 默认拒变更块）、AC-020 短路先于配额/候选、AC-021 有界 + `_workers.acked` 参与、`run.json` worker 自写 + launcher 只补 `lost`、G2 上限（30min/2 次/零残留/`seq` 水位）、G4 帧自证与降级帧、事件 27 / 配置 20 / `authorizes` 闭集 2 逐项相等、15 个抽查测试无空洞、23 张卡无空绑定。
""",
    encoding="utf-8",
    newline="\n",
)
print("appended §8 to", qg.name)

# ── 2. achieved.md 更正 ─────────────────────────────────────────────────────
edit(
    KEY / "achieved.md",
    [
        (
            "- 已答门 / 已终态 stage / 无门 ⇒ 零事件（零残留）。",
            "- 已答门 / 无门 ⇒ 零事件（零残留）。**“已终态 stage 的 gate ⇒ 零事件”未实现**（`gates.pending_gates` `gates.py:770-772` 无 stage 范围过滤，`pending_gate_reminders` `conductor.py:2541-2551` 无 stage 终态判据）—— 独立复审发现、PM 已复现，见「遗留」。",
        ),
        (
            "- 每个 worker 在**自身目录**写 `run.json`（`run_id`/`owner_key`/`pid`/心跳/终态）；launcher 只补 `lost` 而不代写终态；同 task_key 声明 `supersedes` 指向已终态旧目录即拒派。",
            "- 每个 worker 在**自身目录**写 `run.json`（`run_id`/`owner_key`/`pid`/心跳/终态）；launcher 只补 `lost` 而不代写终态。派发判据（`run-store.ts:176-205`）：自己的 `run.json` 终态或 active ⇒ 拒（同一 task_key 一律不重跑）；新 task_key 声明 `supersedes: <旧>` 且旧目录**已终态** ⇒ 放行（合法替换），指向**未知/未终态** ⇒ 拒。",
        ),
        (
            "- 触及包：`packages/multi-workers`（`autopilot/{conductor,config,timeline,gates,contract_guard,dispatch,advance}.py`、`launcher.py`、`mw.py`、`mw_common.py`）与 `packages/coding-agent`（`agent-team-loop/{autopilot,pm,shared,worker}` 的 TS 侧 + 控制台/面板）。",
            "- 触及包：`packages/multi-workers`（`autopilot/{conductor,config,dispatch,gates,timeline}.py` 改动 + `autopilot/contract_guard.py` **新增**，`launcher.py`、`mw.py`、`mw_common.py`；`autopilot/advance.py` **未改动** —— 原始登记误列，复审更正）与 `packages/coding-agent`（`agent-team-loop/{autopilot,pm,shared,worker}` 的 TS 侧 + 控制台/面板）。",
        ),
        (
            "| R21 | **dist/bundle 未重建 ⇒ 本轮改动尚未生效**；运行时切换待批准 | 交付缺口（非缺陷） |",
            "| **AC-007 缺口** | “已终态 stage 的 gate ⇒ 零提醒”未实现（复审发现，PM 复现：`gates.py:770-772` 无 stage 范围、`conductor.py:2541-2551` 无 stage 终态判据） | 代码缺口：待新 key 修复（或明确降级该 AC 子句） |\n| **AC-024 缺口** | `/worker --key <他人 live key>` 未受跨 key 守卫（`ui-bridge.ts:1710` 无 `foreignLiveClaimRefusal`），且拒绝文案 `:241-242` 已声称 `/worker` 被拒 ⇒ 文案与实现不符 | 代码缺口：待新 key（扩守卫或改文案，口径待用户裁） |\n| R21 | **dist/bundle 未重建 ⇒ 本轮改动尚未生效**；运行时切换待批准 | 交付缺口（非缺陷） |",
        ),
    ],
)

# ── 3. pm-state D-064 ───────────────────────────────────────────────────────
ps = KEY / "pm-state.md"
lines = ps.read_text(encoding="utf-8").splitlines()
d63 = next(i for i, l in enumerate(lines) if l.startswith("- D-063（2026-10-10 20:05）"))
lines.insert(
    d63 + 1,
    "- D-064（2026-10-10 20:40）：**独立 review QG-B 回执 + PM 全部复现**（`mwg-qg2b-code-adversarial`，152 次调用 / 37 KB / "
    "`[VERIFY] QG-B: items=14 confirmed=12 refuted=2 undecided=0 hollow_controls=0 hollow_tests=0 mirror_mismatch=0 conclusion=conditional`）。"
    "**两条反证成立且 PM 独立复现**：① **AC-007 部分未实现**——“已终态 stage 的 gate 不提醒”在代码中不存在（`gates.pending_gates` `gates.py:770-772` 只按 `status==pending` 过滤整个 gates 目录；`_remind_pending_gates` `conductor.py:2564` 无 stage 范围；`pending_gate_reminders` `conductor.py:2541-2551` 三条件无 stage 终态判据）⇒ 我的质量门报告 AC-007 行由 PASS **降级 ⚠️ PARTIAL**；"
    "② **AC-024 存在同类缺口 + 文案不符**——`foreignLiveClaimRefusal` 全仓仅 2 调用点（`ui-bridge.ts:1333`/`:1698`），而 `/worker` handler（`registerWorkerCommands` `:1710`，注册 `pm-orchestrator.ts:1059`）经 `:66-67` 显式 key 直通、无守卫，仍可 `:1813-1819` 写他人 live key 的 `task.md` + 队列行，且拒绝文案 `:241-242` 自称 “Refused: … **/worker** …” ⇒ 文案与实现不符（AC 字面只点名两个工具，那两处“先拒后动”成立）。"
    "**一条我自己的不实声称已撤回**：§4 T-20 行“控制 B 曾因不承重被替换为承重变异”无任何工件支持（只存在于我的报告，被引 `t-20-run-identity-report.md` 与 `tasks/T-20-*.md` 均无此句、无“原控制 B”记录）⇒ 违反 AC-014/VC-018 锚点要求，**撤回**；`t20-controls.ps1` 7 组经复审静态判定全部承重（27 组变异点均落在判据行）。"
    "**同时更正 achieved.md**：AC-007 子句改为“未实现”、`supersedes` 口径改回实现真值（自己终态/active ⇒ 拒；`supersedes` 指向已终态旧目录 ⇒ **放行**；未知/未终态 ⇒ 拒，`run-store.ts:176-205`）、影响面误列的 `autopilot/advance.py` 更正为“未改动”（`git diff --stat` 实证）+ 补登 `contract_guard.py`（新增）。"
    "**已声明边界（无需动作）**：空队列守卫在 per-owner 循环内（`pm-orchestrator.ts:653`，混合场景“新增=0”按 owner 成立；T-15 报告 §5.1 已登记）；`readMonitorState` per-section catch 静默空段；`STALL_REASON_CODES` 无 TS 镜像（从未声称）。"
    "**处置**：文档级更正 PM 直执（本决策）；**两个代码缺口待用户裁后开新 key**（不夹带回本 key，AC 口径不污染）。`mwg-qg2a-evidence-chain` 仍在跑。",
)
i = next(idx for idx, l in enumerate(lines) if l.startswith("- 10-10 20:05：QG 复审首派"))
lines.insert(
    i + 1,
    "- 10-10 20:40：**QG-B 独立复审回执**（14 项 / 12 成立 / 2 反证 / 0 空洞对照 / 0 空洞测试 / 0 镜像差异）⇒ PM 逐条复现，**确认 2 个代码缺口（AC-007 stage 终态、AC-024 `/worker`）** + 撤回我的 1 条不实声称（T-20 控制 B）⇒ 更正质量门报告（§2 降级 + §8 更正节）、`achieved.md`（3 处）、pm-state 于 D-064。`mwg-qg2a-evidence-chain` 仍在跑。",
)
upd = next(idx for idx, l in enumerate(lines) if l.startswith("- Updated:"))
lines[upd] = "- Updated: 2026-10-10 20:40"
ps.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("pm-state D-064 written")
