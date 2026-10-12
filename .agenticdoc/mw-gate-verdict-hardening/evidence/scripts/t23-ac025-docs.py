"""AC-025 / T-23 doc updates: spec, design, plan, T-14 follow-up."""

import pathlib

ROOT = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening")


def read(p):
    return pathlib.Path(p).read_text(encoding="utf-8")


def write(p, t):
    pathlib.Path(p).write_text(t, encoding="utf-8", newline="\n")


# ---------------- spec.md : AC-025 ----------------
spec_p = ROOT / "spec.md"
spec = read(spec_p)

ac025 = (
    "| AC-025 | **G3 锚点必须由框架自身建立（否则 AC-011 在生产中永不触发）**："
    "① **自动建立**——key 首次被观测到 `phase == design` 时冻结 AC 块、`phase == plan` 时冻结 VC 块；"
    "**每块最多写一次，已存在的非空块永不重写**（一次 tick 内合并为一次原子写）；"
    "② **建立留痕**——新增 timeline 事件 `contract-frozen`"
    "（`data={block, phase, source, freeze_rel, ids}`，P-009 机读分类）；"
    "③ **显式入口**——`mw autopilot contract-freeze --project <dir> --key <k> [--block ac|vc|all] [--force] [--json]`"
    "（缺块补齐；已存在且未变更的块默认跳过；已**变更**的块必须 `--force` 才重冻，并打印被替换的 id）；"
    "④ **不回溯**——`phase` 已在 `tasks/execute/verify/done` 的历史 key **不自动补锚**"
    "（P-018 口径：无历史可回填），其锚点只能由显式 CLI 建立；"
    "⑤ **缺失/损坏的锚一律视为无锚 ⇒ 放行**（与 T-04 `evaluate` 同口径；"
    "否则等于把所有历史 key 永久锁死，与 AC-013 冲突）。"
    "反向用例：①把临时 key 推进到 design 并跑一次 tick ⇒ 出现 sidecar 且**仅含 AC 块**；"
    "推进到 plan ⇒ VC 块加入且 AC 块**字节不变**；②改写一条 AC 文本 ⇒ `evaluate` 拒绝（G3 真活）；"
    "③再次 tick 不重写（文件 sha 不变、无第二个 `contract-frozen`）；④`--force` 才允许重冻。"
    " `[ADDED @ 2026-10-10]` |"
)
lines = spec.splitlines()
i = next(idx for idx, l in enumerate(lines) if l.startswith("| AC-024 |"))
lines.insert(i + 1, ac025)

note = (
    "> 追加范围 G3-锚点（补齐 AC-011 的可达性）：**AC-025** 于 2026-10-10 顺延追加"
    "（T-11 交接 R1：design D-015 / §4.5 要求 `mw autopilot contract-freeze` 与两处接受边界冻结，"
    "但无卡承载 ⇒ G3 在生产中处于休眠态：无锚 ⇒ `no_anchor` ⇒ 永不拒绝）。旧编号与旧内容未改动。"
)
j = next(idx for idx, l in enumerate(lines) if l.startswith("> 注（2026-10-10，原地追加说明，不改 AC-014 原文）"))
lines.insert(j, note)
spec = "\n".join(lines) + "\n"
write(spec_p, spec)

# ---------------- design.md ----------------
design_p = ROOT / "design.md"
design = read(design_p)

# D-015 row in the decision table
old_d015 = "| D-015 | G3 文本身份锚"
k = design.index(old_d015)
end = design.index("\n", k)
d015_rev = (
    " **REVISED @ 2026-10-10 18:55**："
    "（a）“缺失 ⇒ fail-closed 拒绝”改为“**缺失/损坏 ⇒ 无锚 ⇒ 放行**”，只有“**有锚 + 文本变更 + 无批准记录**”才拒绝"
    "——原字面会让所有历史 key（含本仓全部现存 key，均无 sidecar）的 done 永久被拒，与 AC-013/P-018 直接冲突；"
    "（b）冻结时机按原设计（`spec→design` 冻结 AC 块 / `design→plan` 冻结 VC 块）由 **AC-025/T-23** 落地为"
    "“见 design 即冻 AC、见 plan 即冻 VC”的**幂等一次写**，并新增 `contract-frozen` 留痕；"
    "（c）历史 key 不自动补锚（不回溯），仅显式 CLI 可补。"
)
design = design[:end] + d015_rev + design[end:]

# new section §11.11 appended after the AC/VC traceability table area (end of file)
design += (
    "\n### 11.11 G3 锚点建立（AC-025，T-23；2026-10-10 追加）\n\n"
    "**为何必须有这一节**：T-04 只造了 `contract_guard.py` 的 `freeze_contract`/`write_freeze`，"
    "T-10 的 done 前守卫只调 `evaluate`，T-11 只暴露只读 CLI/doctor；"
    "**没有任何生产调用者创建 sidecar** ⇒ 全仓零 sidecar（PM 实测：`Get-ChildItem -Recurse -Filter contract-freeze.json .agenticdoc` 为空）"
    "⇒ `no_anchor` ⇒ AC-011 永不触发。T-11 拒绝擅自新增第 4 个 CLI 面并把它作为 R1 交回 PM，PM 判定为 G3 完整性缺口，"
    "开 **AC-025 + T-23** 收口。\n\n"
    "| 机制点 | 落点 | 行为 |\n"
    "|---|---|---|\n"
    "| 自动锚（AC 块）| `conductor.py::_freeze_contract_first_sight`（tick 内一步）| `phase == design` 且无 AC 块 ⇒ 读 `spec.md` 摘 AC 文本，构建后与既有块**合并**、**一次** `write_freeze`；留 `contract-frozen`（`block=\"ac\"`, `source=\"conductor-first-sight\"`）|\n"
    "| 自动锚（VC 块）| 同上 | `phase == plan` 且无 VC 块 ⇒ 同上（`block=\"vc\"`）|\n"
    "| 永不重写 | 同上 | 既有块非空即跳过（读 `read_freeze`）；同一 key 同一 tick 只写一次；任何异常吞掉并留 `contract-frozen` 失败留痕（不阻断 tick）|\n"
    "| 不回溯 | 同上 | `phase ∈ {tasks, execute, verify, done}` ⇒ 不自动补锚（P-018：无历史可回填）|\n"
    "| 显式 CLI | `mw.py::_ap_contract_freeze` | `mw autopilot contract-freeze --project --key [--block ac\\|vc\\|all] [--force] [--json]`；缺块补齐；已存在且未变更 ⇒ 跳过；已变更 ⇒ 需 `--force`，打印被替换 id；写路径**只在显式人指令下**发生 |\n"
    "| 事件词汇 | `timeline.py::EVENT_TYPES` += `contract-frozen` | Python 侧 27 项；TS 镜像（`status-model.ts EVENT_TYPES`）由 **T-14** 补齐（跨语言 parity 锁）|\n"
    "| 无锚语义 | `contract_guard.read_freeze`/`evaluate`（不改）| 缺失/损坏 ⇒ `None` ⇒ `no_anchor=True` ⇒ 放行（D-015 `[REVISED]`）|\n\n"
    "- **VC-047**：把临时 key 的 `pm-state` 推进到 `design` 后跑一次 conductor tick ⇒ `<key>/evidence/contract-freeze.json` 出现且 `spec` 块非空、`design` 块为空；"
    "推进到 `plan` 再跑一次 ⇒ `design` 块非空且 **`spec` 块逐字节不变**；再跑一次 ⇒ 文件 sha 不变且 timeline 只有 2 条 `contract-frozen`；"
    "改写一条 AC 文本 ⇒ `contract_guard.evaluate` 返回 `ok=False` 且 `changed_ids` 含该 id（T-10 的 done 守卫据此拒绝）；"
    "`phase == execute` 且无 sidecar 的 key ⇒ tick 后仍无 sidecar（不回溯）。\n"
    "- **F47** | G3 锚点自动建立（AC-025）| 摘掉 `_freeze_contract_first_sight` 调用 ⇒ sidecar 不出现 ⇒ VC-047 红；"
    "把“既有块非空即跳过”改成无条件重写 ⇒ 第二次 tick 的 sha 断言红；删除 `contract-frozen` 事件 ⇒ 留痕断言红 |\n"
    "- **写面**：`packages/multi-workers/autopilot/conductor.py`（串行链末段 T-01→T-07→T-10→**T-23**）、"
    "`packages/multi-workers/mw.py`、`packages/multi-workers/autopilot/timeline.py`（+1 事件名）、"
    "新测试文件 `packages/multi-workers/test_autopilot_contract_freeze.py`。**不碰任何计数锁**（归 T-14）。\n"
)
write(design_p, design)

# ---------------- plan.md ----------------
plan_p = ROOT / "plan.md"
plan = read(plan_p)

old_scale = "- 规模：**24 AC / 46 VC / 49 功能点**"
assert plan.count(old_scale) == 1
plan = plan.replace(
    old_scale,
    "- 规模：**25 AC / 47 VC / 50 功能点**"
    "（AC-025 / VC-047 / F47 于 2026-10-10 追加：G3 锚点建立，补齐 AC-011 的可达性，见 T-23）",
)

# card table row for T-23 (append right after the T-22 row)
t22 = "| T-22 | **AC-024 跨 key 只读（写面守卫）**"
lines = plan.splitlines()
i = next(idx for idx, l in enumerate(lines) if l.startswith(t22[:24]))
lines.insert(
    i + 1,
    "| T-23 | **AC-025 G3 锚点建立（自动 + 显式）** | 3 | AC-025 | VC-047 | "
    "`conductor.py` 见 design 冻 AC / 见 plan 冻 VC（幂等一次写、不回溯）+ `mw autopilot contract-freeze` CLI "
    "+ `timeline.py` 事件 `contract-frozen`；**不碰计数锁**（T-14 补 TS 镜像与 27 事件数） |"
    "+ T-04, T-10, T-11 |",
)

# serial chain extension
old_chain = "最大并行度 = 6（波 0）；**八条串行链**：`conductor.py`（T-01→T-07→T-10）"
plan = "\n".join(lines)
assert plan.count(old_chain) == 1
plan = plan.replace(
    old_chain,
    "最大并行度 = 6（波 0）；**八条串行链**：`conductor.py`（T-01→T-07→T-10→**T-23**）、"
    "`timeline.py`（T-03→**T-23**）、`mw.py`（T-11→**T-23**）",
)

plan += (
    "\n| R19 | **G3 锚点仍未覆盖“错过边界”的 key**（在 conductor 未运行时穿过 design/plan 的 key，"
    "或 feature 上线前已在 execute 的历史 key）⇒ 无锚 ⇒ 不受 G3 保护 | T-23 | "
    "按设计**不回溯**（P-018）：这类 key 的守卫需由人显式 `mw autopilot contract-freeze` 建立；"
    "残余状态在 `mw doctor` 上可见（无 sidecar ⇒ `gates` 无 `contract_guard` 段，`mw autopilot contract-guard --key K` 明确打印 `no freeze sidecar`）|"
)
write(plan_p, plan)

# ---------------- T-14 card follow-up ----------------
t14_p = ROOT / "tasks" / "T-14-count-locks.md"
t14 = read(t14_p)
t14 += (
    "\n\n## PM 追记（2026-10-10 19:00，T-23 落地后必须一并刷新）\n\n"
    "T-23（AC-025，G3 锚点建立）新增了一个 timeline 事件名 **`contract-frozen`**（Python `timeline.py::EVENT_TYPES` 已加）。"
    "因此本卡的计数锁必须按**新数字**刷新，两侧同时：\n\n"
    "| 锁 | 就绪前 | **就绪后（本卡）** | 位置 |\n"
    "|---|---|---|---|\n"
    "| timeline 事件集合 | 23 → 26 | **27**（+`contract-frozen`）| `test_autopilot_timeline.py:48/53/54`（建议改为对 `EVENT_TYPES` 的集合相等断言）|\n"
    "| TS 事件集合 | 集合相等 | **27**，`status-model.ts EVENT_TYPES` += `contract-frozen` | `autopilot-event-parity.test.ts`（两侧集合相等）|\n"
    "| `reason_code` 数量 | 12 | **14**（T-01/T-10 已落，本卡只改锁）| `test_autopilot_auto_decision.py:301/333/338` |\n"
    "| 配置键数 | 17 | **20** | `test_autopilot_config_parity.py` + 冻结语料 + `autopilot-config-sync.test.ts` |\n\n"
    "- **新增事件名的 TS 半边归你**（T-23 不碰 `status-model.ts`，以免与 T-12 的 `authorizes` 镜像同文件冲突）。\n"
    "- 若 `test_autopilot_timeline.py` 已经改成动态读 `EVENT_TYPES`，则本卡只需保证 **两侧集合相等** 且 TS 侧含 `contract-frozen`；"
    "并在回执里说明“集合相等比硬数字更强”的理由（这仍是本卡要求的判据）。\n"
)
write(t14_p, t14)

print("spec/design/plan/T-14 updated")
