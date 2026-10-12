"""QG-A 复审后的 PM 更正：质量门报告（锚点重锚 + 基线纠错 + AC-008 降级 + §9）+ achieved.md + pm-state D-065。"""

import pathlib

KEY = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening")


def edit(path, pairs):
    t = path.read_text(encoding="utf-8")
    for old, new in pairs:
        assert t.count(old) == 1, (path.name, t.count(old), old[:80])
        t = t.replace(old, new)
    path.write_text(t, encoding="utf-8", newline="\n")
    print("edited", path.name)


qg = KEY / "evidence" / "quality-gate-report-20261010.md"
edit(
    qg,
    [
        # 1. 基线纠错
        (
            "| 基线 `verify-baseline.md` = 2 failed / 1431 passed；",
            "| 基线 `verify-baseline.md` **实录 2 failed / 655 passed / 8 deselected**（该文件是早期子集跑，早于本 key 新增/扩展测试落地；全量终跑 = 2 failed / 1523 passed，与 `verify-closure.md` §2 同数）；",
        ),
        # 2. AC-001 锚点重锚
        (
            "| **AC-001** | G1 | **PASS** | T-01 `conductor.py:1649` 指纹分支在状态门 `:1651` **之前**",
            "| **AC-001** | G1 | **PASS** | T-01 `conductor.py:1662`（`_l3_stream_aborted` 指纹分支）在状态门 `:1664` **之前**（复审重锚；原文 `:1649/:1651` 系 T-10/T-23 插入后漂移）",
        ),
        # 3. AC-005 锚点重锚
        (
            "| **AC-005** | G2 | **PASS** | T-07 `conductor.py:2475` `pending_gate_reminders` 纯判定 + `:2508` `_remind_pending_gates`，`tick` 第 2b 步 `:2577`",
            "| **AC-005** | G2 | **PASS** | T-07 `conductor.py:2522` `pending_gate_reminders` 纯判定 + `:2555` `_remind_pending_gates`，`tick` 第 2b 步调用 `:2764`（复审重锚；原文 `:2475/:2508/:2577` 漂移）",
        ),
        # 4. AC-008 降级
        (
            "| **AC-008** | G2 | **PASS** | T-08 `monitor.ts` snapshot 级 `blockedOnHuman`（`:184`，采集 `:364-369`，用 T-05 共享 `blockedOnHuman()`）+ 置顶 `BLOCKED_ON_HUMAN` 行（`:745-753`，受 `!tickStale` 门控） | PM 复跑 73 passed，`VC-011: age_shown=true blocked_marker=true` |",
            "| **AC-008** | G2 | **⚠️ PARTIAL** | **面板半边已交付**：T-08 `monitor.ts` snapshot 级 `blockedOnHuman`（`:184`，采集 `:364-369`）+ 置顶 `BLOCKED_ON_HUMAN` 行（`:745-753`，受 `!tickStale` 门控）；**`mw doctor` 半边未交付**：design D-009 第三面（`design.md:147`/`:386`/`:432`）要求在 `mw_common.py` 的 `_doctor_gates` 加 `blocked_on_human` 字段 + `_gates_text_alerted` 触发 + `format_doctor_text` 条件后缀，实测 `mw_common.py` grep `blocked_on_human|BLOCKED_ON_HUMAN` = **0 命中**，且无卡承接 | PM 复跑 73 passed（面板侧）；doctor 侧反证 QG-A #1（PM 已 grep 复现） |",
        ),
        # 5. AC-014 边界备注
        (
            "| **AC-014** | 全部 | **PASS** | 每条机器判据附非空洞对照（见 §4 索引：7 个 `*-controls.ps1` 脚本 + 各卡 CF 组，全部实测转红并逐字节还原） | 本报告 §4 |",
            "| **AC-014** | 全部 | **PASS（边界）** | 每条机器判据附非空洞对照（见 §4 索引：7 个 `*-controls.ps1` 脚本 + 各卡 CF 组）。**边界**：① 对照“实际跑红并逐字节还原”这一层只有各卡回执记录，本次两个独立复审均无 bash 不能复跑（运行层欠债）；② 独立复审静态核查 27 组变异点**全部落在判据行**（无空洞对照）；③ 本报告 §4 曾据不实转述标注 T-20“控制 B 不承重”——已撤回（§8） | 本报告 §4/§8；`verify-g5g6-tests.md` §3；各卡 `*-controls.ps1` |",
        ),
        # 6. AC-022 边界备注
        (
            "| **AC-022** | G6 | **PASS** | T-20 `run-store.ts` + `worker-mode.ts` 自写 `run.json`（running/终态/心跳）+ launcher 只补 `lost` + 同 `task_key` 不再重跑（`supersedes` 指已终态旧目录） | T-20 report（15+6+9+7 例）；PM 复跑 340 passed |",
            "| **AC-022** | G6 | **PASS（边界）** | T-20 `run-store.ts` + `worker-mode.ts` 自写 `run.json`（running/终态/心跳）+ launcher 只补 `lost`；派发判据：自己终态/active ⇒ 拒、`supersedes` 指向未知/未终态 ⇒ 拒、指向已终态 ⇒ 放行（`run-store.ts:176-205`）。**边界（D-038）**：Python 侧 `autopilot/dispatch.py:621-633` 派发判据**不读** `run.json`（AC 字面“派发/重派判据首先读产物终态”未限定路径） | T-20 report（15+6+9+7 例）；PM 复跑 340 passed；反证 QG-A #3（PM 已 grep 复现 0 命中） |",
        ),
        # 7. 标题与引用口径
        (
            "## 2. AC 矩阵（23 PASS + 2 ⚠️ PARTIAL —— 复审后更正，见 §8）",
            "## 2. AC 矩阵（**post-复审**：22 PASS + 3 ⚠️ PARTIAL（AC-007/AC-008/AC-024）；另 AC-014/AC-022 标 PASS 但附边界 —— 更正见 §8、§9）",
        ),
        (
            "## 3. VC 矩阵（47/47 PASS；判据全文见 `design.md`）",
            "## 3. VC 矩阵（复审后：VC 按其字面 47/47 成立；VC-011/017/018 因下述欠债标 ⚠️ —— 见 §9）",
        ),
        (
            "> VC 的完整判据文本在 `design.md` §6 / §11.7 / §11.11；本表给出各自摘要与归属证据通道。",
            "> VC 的完整判据文本在 `design.md` §6 / §11.7 / §11.11；本表的**证据通道**列是分组引用（非逐条锚点），逐条 VC→用例锚点在 `evidence/runs/verify-g5g6-tests.md` §1（47 行映射，含用例名）。**复审指出：本表 24 行同组引用属模板化，使用时请以映射表为准**（QG-A §7 #8）。",
        ),
        # 8. 结论行
        (
            "**结论（复审更正后）：AC = 23 PASS + 2 ⚠️ PARTIAL（AC-007 已终态 stage 未实现；AC-024 `/worker` 未受守卫且文案不符）、VC 47/47 按其字面成立；新增红 0；交付缺口 = 运行时切换（R21）+ 上述 2 个代码缺口（待新 key 修复）。**",
            "**结论（两次复审更正后）：AC = 22 PASS + 3 ⚠️ PARTIAL（AC-007 已终态 stage 未实现；AC-008 `mw doctor` 半边未交付；AC-024 `/worker` 未受守卫且文案不符）、AC-014/AC-022 带边界备注；VC 47/47 按其字面成立（VC-011/017/018 因欠债标 ⚠️）；新增红 0。交付缺口 = 运行时切换（R21）+ 3 个代码缺口 + 文档勘误（待新 key），详见 §8/§9。**",
        ),
    ],
)

qg.write_text(
    qg.read_text(encoding="utf-8").rstrip("\n")
    + "\n\n"
    + """## 9. 第二次复审更正（QG-A 证据链审查，2026-10-10 21:00）

来源：独立证据链审查 `workers/mwg-qg2a-evidence-chain/report.md`（131 问 = 114 ✅ / 17 ⚠️ / 0 ❌；`[VERIFY] QG-A: questions=131 sufficient=114 insufficient=17 missing=0 conclusion=conditional`）。同样由 PM 逐条复现：

| # | 本报告原判定 | 复审反证 | PM 独立复现 | 处置 |
|---|---|---|---|---|
| 1 | AC-008 = PASS（只引 `monitor.ts` 锚点） | **`mw doctor` 半边未交付**：AC-008 字面要求“monitor 面板**与 `mw doctor`**”两个监视面；design D-009 第三面（`design.md:147`/`:386`/`:432`）要求在 `mw_common.py` 加 `blocked_on_human` + `_gates_text_alerted` 触发 + `format_document_text` 条件后缀，且该面**从未进任何任务卡**（plan 把 `mw_common.py` 只分给 T-11/T-18） | `rg 'blocked_on_human|BLOCKED_ON_HUMAN' packages/multi-workers/mw_common.py` = **0 命中**（monitor.ts 侧 = 10 命中）；`t-08` 回执全文无 “doctor” | AC-008 降级 **⚠️ PARTIAL**；缺口中 `mw_common.py` G2 面 → 遗留（新 key） |
| 2 | §1 “基线 `verify-baseline.md` = 2 failed / **1431** passed” | **引用失准** | `verify-baseline.md` 原文 = “2 failed, **655** passed, 8 deselected”（早期子集跑）；1431 是 T-21 期全量数 | **已更正 §1**（并保留“新增红 = 0”结论：两条红同名同集合） |
| 3 | AC-001 / AC-005 行 conductor 锚点 | **锚点漂移**（报告由脚本组装时复用早期行号） | 实测：AC-001 → `:1662`/`:1664`（原 `:1649`/`:1651`）；AC-005 → `:2522`/`:2555`/`:2764`（原 `:2475`/`:2508`/`:2577`） | **已重锚 §2 两行** |
| 4 | AC-022 = PASS | **D-038 边界未在行内披露** | `rg 'run\\.json' packages/multi-workers/autopilot/dispatch.py` = **0 命中** ⇒ Python 派发判据不读产物终态 | AC-022 标 **PASS（边界）**；缺口 → 遗留（新 key） |
| 5 | §3 VC 证据通道列 | **模板化引用**（24 行同组 6 文件），非逐条锚定 | 属实（报告由 `t23-quality-gate-report.py` 生成） | §3 加口径说明并指向 `verify-g5g6-tests.md` §1 的 47 行映射 |
| 6 | AC-014 = PASS | 对照“跑红 + 还原”只能由运行证实 | 属实（两次复审均无 bash）；静态层 27 组变异点全部承重 | AC-014 标 **PASS（边界）** |

**复审认同（非差异）**：25 条 AC 的**实现存在性**经独立重锚后**无一证伪**；收口数字（2 failed / 1523 passed、13 suite / 340 tests、`check` exit 0）与 `verify-closure.md` 逐字一致；R21 为已诚实声明的全局欠债。

**仍未处置（归入新 key，避免污染本 key 已冻口径）**：

1. 代码缺口：**AC-008 doctor 面**、**AC-007 stage 终态**、**AC-024 `/worker` 守卫/文案**、**D-038 `dispatch.py` 接 `run.json`**。
2. spec/plan/design 勘误：AC-021 标题与反向用例措辞冲突；spec §2.3 与 AC-025⑤ 字面冲突；plan §2.5 值域（1..50 应为 1..64）；design §0 `ac_count: 24` 陈旧、§8 映射表止于 AC-018。
3. 工作流前置物：`evidence-requirement.md` / `evidence/baseline/` 缺失（本 key 以 design §7 + `verify-baseline.md` 替代）——需登记偏离或补页。
4. 卡片卡头 VC 少报（T-18/T-19/T-20）——plan §3 为准，卡头补登记。
5. 运行层欠债：6 份 `*-controls.ps1` 与全量 pytest/vitest 需在有 bash 的会话独立复跑。
""",
    encoding="utf-8",
    newline="\n",
)
print("appended §9")

# ── achieved.md ─────────────────────────────────────────────────────────────
edit(
    KEY / "achieved.md",
    [
        (
            "- 面板顶置 `BLOCKED_ON_HUMAN` 行（非终态 worker 计数 + 最旧 pending gate 年龄），gate 行附粗粒度 `age=`；数据面变化 ≤2 个刷新周期（8 s）内跟随。",
            "- 面板顶置 `BLOCKED_ON_HUMAN` 行（非终态 worker 计数 + 最旧 pending gate 年龄），gate 行附粗粒度 `age=`；数据面变化 ≤2 个刷新周期（8 s）内跟随。"
            "**但 AC-008 的 `mw doctor` 半边未交付**（design D-009 第三面要求在 `mw_common.py` 加 `blocked_on_human` + 条件文本；实测 0 命中，且无卡承接）—— 独立复审发现、PM 已复现，见「遗留」。",
        ),
        (
            "| R21 | **dist/bundle 未重建 ⇒ 本轮改动尚未生效**；运行时切换待批准 | 交付缺口（非缺陷） |",
            "| **AC-008 缺口** | `mw doctor` 的 G2 可见面未交付（`mw_common.py` grep `blocked_on_human|BLOCKED_ON_HUMAN` = 0 命中；design `:147`/`:386`/`:432` 要求；AC-008 字面含“与 `mw doctor`”） | 代码缺口：待新 key 落地或正式 descope |\n"
            "| **D-038 确认（AC-022 边界）** | Python 侧 `autopilot/dispatch.py:621-633` 派发判据不读 `run.json` ⇒ “派发/重派判据首先读产物终态”只在 TS 路径 + launcher 收敛成立 | 代码缺口：待新 key 接 `read_run_status`（或 AC 行内明确边界） |\n"
            "| **文档勘误（待新 key）** | spec AC-021 措辞冲突、spec §2.3 vs AC-025⑤、plan §2.5 值域、design §0 `ac_count`/§8 映射表陈旧；`evidence-requirement.md` 缺失；T-18/19/20 卡头 VC 少报 | 文档：随新 key 的 spec/design 阶段一并修 |\n"
            "| R21 | **dist/bundle 未重建 ⇒ 本轮改动尚未生效**；运行时切换待批准 | 交付缺口（非缺陷） |",
        ),
        (
            "- 验收结论：AC 25/25、VC 47/47 **PASS（源码 + 测试级）**；全量回归**新增红 = 0**",
            "- 验收结论（**两次独立复审更正后**）：AC = **22 PASS + 3 ⚠️ PARTIAL**（AC-007 已终态 stage 未实现 / AC-008 `mw doctor` 半边未交付 / AC-024 `/worker` 未受守卫）+ AC-014/AC-022 带边界；VC 47 项按其字面成立；全量回归**新增红 = 0**。判定层级 = **源码 + 证据级**（除运行时切换外）；复审报告见 `workers/mwg-qg2a-evidence-chain/report.md`、`workers/mwg-qg2b-code-adversarial/report.md`",
        ),
    ],
)

# ── pm-state D-065 ──────────────────────────────────────────────────────────
ps = KEY / "pm-state.md"
lines = ps.read_text(encoding="utf-8").splitlines()
d64 = next(i for i, l in enumerate(lines) if l.startswith("- D-064（2026-10-10 20:40）"))
lines.insert(
    d64 + 1,
    "- D-065（2026-10-10 21:00）：**独立 review QG-A 回执 + PM 复现**（`mwg-qg2a-evidence-chain`，121 次调用 / 57 KB / "
    "`[VERIFY] QG-A: questions=131 sufficient=114 insufficient=17 missing=0 conclusion=conditional`）。**实质发现（PM 已 grep 复现）**："
    "① **AC-008 只交付了面板半边**——AC-008 字面要求“monitor 面板**与 `mw doctor`**”两个监视面，design D-009 第三面（`design.md:147`/`:386`/`:432`）要求在 `mw_common.py` 加 `blocked_on_human` 字段 + `_gates_text_alerted` 触发 + `format_doctor_text` 条件后缀，实测 **0 命中**，plan 把 `mw_common.py` 只分给 T-11/T-18 ⇒ **该面从未进任何卡**（掉单）⇒ AC-008 降级 ⚠️ PARTIAL；"
    "② **AC-022 边界确认（D-038）**：`autopilot/dispatch.py` grep `run.json` = 0 ⇒ Python 派发判据不读产物终态；"
    "③ **我的报告两处硬伤（自证）**：基线引用失准（`verify-baseline.md` 实录 2 failed/**655** passed，我写 1431）与 conductor 锚点漂移（AC-001 `:1649/:1651`→`:1662/:1664`；AC-005 `:2475/:2508/:2577`→`:2522/:2555/:2764`）⇒ 已在 §1/§2 就地更正并加 **§9 更正节**（含 6 行差异表：AC-008 降级、基线、锚点、AC-022 边界、§3 模板化引用、AC-014 运行层欠债）；"
    "④ 17 条 ⚠️ 的构成 = 1 项功能缺口（doctor 面）+ 2 项运行复证欠债（对照脚本/[VERIFY] 实测）+ 6 项报告/文档质量 + 4 项 spec/plan 措辞 + 3 项已登记残留（R21/R18/D-038）。"
    "**两次复审的合并结论**：AC = **22 PASS + 3 ⚠️ PARTIAL**（AC-007/AC-008/AC-024）+ AC-014/AC-022 带边界；VC 字面成立；**新增红 = 0**；判定层级 = 源码+证据级。"
    "**待处置（新 key，需用户裁）**：4 个代码缺口（AC-008 doctor 面 / AC-007 stage 终态 / AC-024 `/worker` / D-038）+ 文档勘误（spec AC-021、spec §2.3、plan §2.5、design §0/§8、`evidence-requirement.md`、卡头 VC 少报）+ 运行层复跑欠债。",
)
i = next(idx for idx, l in enumerate(lines) if l.startswith("- 10-10 20:40：**QG-B 独立复审回执**"))
lines.insert(
    i + 1,
    "- 10-10 21:00：**QG-A 独立复审回执**（131 问 / 114 ✅ / 17 ⚠️ / 0 ❌）⇒ PM 复现：**AC-008 `mw doctor` 半边从未进卡**（0 命中）、AC-022/D-038 边界确认、我的报告基线引用与锚点各一处硬伤 ⇒ 就地更正质量门报告（§1/§2 重锚 + §9 更正节）、achieved.md（AC-008 缺口 + 3 项新遗留 + 验收口径改 22 PASS/3 PARTIAL）。两次复审合并：**无一项“声称实现而源码不存在”**，功能缺口 = 3（AC-007/AC-008/AC-024）+ 1 边界（D-038）。**下一步待用户裁：开新 key 修 4 个缺口 + 文档勘误**。",
)
upd = next(idx for idx, l in enumerate(lines) if l.startswith("- Updated:"))
lines[upd] = "- Updated: 2026-10-10 21:00"
na = next(idx for idx, l in enumerate(lines) if l.startswith("- Next Action:"))
lines[na] = (
    "- Next Action: 本 key **done 但结论已按两次独立复审更正**：AC = 22 PASS + 3 ⚠️ PARTIAL（AC-007 / AC-008 / AC-024）+ AC-014/AC-022 带边界；"
    "VC 字面成立；新增红 0（`evidence/quality-gate-report-20261010.md` §8/§9 为更正节）。**待用户裁**：① 是否开新 key 修 4 个代码缺口"
    "（AC-008 `mw doctor` 面 / AC-007 stage 终态 / AC-024 `/worker` 守卫或文案 / D-038 `dispatch.py` 接 `run.json`）+ 文档勘误（spec AC-021、spec §2.3、plan §2.5、design §0/§8、`evidence-requirement.md`、卡头 VC 少报）；"
    "② 运行时切换（R21，runbook 已就绪，待批准）；③ R18 是否单开卡；④ 运行层欠债（6 份 `*-controls.ps1` + 全量 pytest/vitest 需有 bash 的会话复跑）。"
)
ps.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("pm-state D-065 written")
