"""pm-state D-058/D-059 + process log 19:15 + T-14 card record + plan T-16 row note."""

import pathlib

ROOT = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening")


def read(p):
    return pathlib.Path(p).read_text(encoding="utf-8")


def write(p, t):
    pathlib.Path(p).write_text(t, encoding="utf-8", newline="\n")


# ---- pm-state ----
p = ROOT / "pm-state.md"
lines = read(p).splitlines()
d57 = next(i for i, l in enumerate(lines) if l.startswith("- D-057（2026-10-10 19:05）"))
lines.insert(
    d57 + 1,
    "- D-058（2026-10-10 19:12）：**T-14 完成（本 key 最后一张改测试的卡）**。PM 亲跑："
    "`test_autopilot_auto_decision.py + test_autopilot_timeline.py + test_autopilot_config_parity.py` = **47 passed**（开工前 4 红全消）；"
    "TS 4 文件（event-parity / console / config-sync / config-parity）= **47 passed**，`[VERIFY] P6: effective_view_20=true fields_covered=20`。"
    "实际落法：`reason_code` 锁 12→**14**（含测试名/注释的 `twelve` 陈旧字样一并更名）；"
    "timeline 锁由硬数字 23 改为**对照 27 名 `LOCKED_EVENT_TYPES` 字面量**的集合相等（既有 3 个 + `contract-frozen`）+ 派生 seq 区间——"
    "PM 认可这是**比硬数字更强**的锁（增删都需人改动字面量）；配置语料 64→**73**（3 单键 accept + 6 越界 reject，两侧 sha 同步 `4921…`→`1e27…`）；"
    "`status-model.ts EVENT_TYPES` += `contract-frozen`（T-23 欠的 TS 半边已补）；"
    "`autopilot-console.test.ts:374-378` 经核实**已是** T-05/T-12 后的形状（`authorizes` 不进 `GateView`）⇒ 未改。"
    "`test_autopilot_readcap_injection.py` 无需再重冻（`test_autopilot_config.py` 未动）。四组对照 A~D 均转红并逐字节还原。",
)
lines.insert(
    d57 + 2,
    "- D-059（2026-10-10 19:12）：**T-16 范围按用户待决项收窄（deviation，已记 plan）**。原卡含「重建 `packages/coding-agent/dist/**`」；"
    "PM 决定**拆出**：① AGENTS.md 规定 `npm run build` 需用户明确要求，而运行时切换（`mw build --install --allow-dirty` + 重启 launcher/serve + 重启 9 个 pre-10:53 旧窗口）"
    "仍在等用户拍板（D-043 残留）；② `dist/**` 是版本控制产物，多会话同 cwd 重建会夹带别的会话改动；③ 切换会让 9 个旧窗口的 pre-`b8bc115ff` 解析器与新产物共存 = IN-3 复现条件。"
    "⇒ T-16 改为 **CHANGELOG×2 + 全量回归/基线对照（`verify-closure.md`）+ 必要 README 同步 + 运行时切换 runbook（只写不执行）**；"
    "dist/bundle 重建与切换 = **用户批准后 PM 直执**（新增残留 R21）。",
)

i = next(idx for idx, l in enumerate(lines) if l.startswith("- 10-10 19:05：**T-23 done + acked**"))
lines.insert(
    i + 1,
    "- 10-10 19:15：**T-14 done + acked**（计数锁收口：reason_code 12→14、timeline 改 27 名字面量集合相等、配置 17→20 + 语料 64→73 双侧重冻、"
    "TS `EVENT_TYPES` += `contract-frozen`；PM 亲跑 Python 47 passed / TS 47 passed，四组对照转红还原）。"
    "⇒ 派 **T-16**（**范围已收窄**：CHANGELOG×2 + `verify-closure.md` + 运行时切换 runbook；**不重建 dist、不跑 build、不重启**）。"
    "记 D-058/D-059。在跑 = **T-16**（本 key 最后一张卡）。",
)

na = next(i for i, l in enumerate(lines) if l.startswith("- Next Action:"))
lines[na] = (
    "- Next Action: **本 key 的实现卡只剩 T-16（本次收窄后的文档+回归+runbook 卡）**，T-01~T-15、T-17~T-23 全部 done+acked。"
    "**当前在跑 = T-16**（CHANGELOG×2 + `verify-closure.md` 全量回归与基线对照 + 运行时切换 runbook；**明确不重建 dist、不跑 `npm run build`、不重启**）。"
    "**T-16 done 后 PM 动作**：① 自己独立跑一遍全量收口验证（Python 全量 + TS 全集 + `npm run check`）；"
    "② 核销剩余 AC/VC 矩阵（`evidence/runs/verify-g5g6-tests.md` + 各卡 [VERIFY]）；③ 评估 `advance_phase(verify)`。"
    "**待用户决定（阻塞收尾的最后一项）**：运行时切换（`mw build --install --allow-dirty` + 重启 launcher/serve + 重启 9 个 pre-10:53 旧窗口）"
    "—— 在此之前本轮全部 TS/扩展改动**尚未生效**，且每次派发都会把队列翻成 9 列（PM 每次已归一回 8 列）；"
    "runbook 由 T-16 产出，批准后 PM 直执。"
    "**次待决定**：残留 R18 是否单独开卡；T-23 的 `--force` 语义是否认可。"
    "**已知残留**：R18（spawn 竞态不得静默判终态）、R19（错过 design/plan 边界的 key 无锚）、R20（`monitorCtx` 只由 `autoStartMonitor` 写）、"
    "R21（dist/bundle 重建 + 运行时切换待批准）、D-038（`autopilot/dispatch.py` 未接 `run.json`）。"
)
upd = next(i for i, l in enumerate(lines) if l.startswith("- Updated:"))
lines[upd] = "- Updated: 2026-10-10 19:15"
write(p, "\n".join(lines) + "\n")

# ---- T-14 card: implementation record ----
t14 = ROOT / "tasks" / "T-14-count-locks.md"
t14t = read(t14)
assert "## 实施记录（PM 核销 2026-10-10 19:12）" not in t14t
t14t += (
    "\n\n## 实施记录（PM 核销 2026-10-10 19:12）\n\n"
    "| 锁 | 旧 → 新 | 落点（实测行号） |\n|---|---|---|\n"
    "| `reason_code` | 12 → **14** | `test_autopilot_auto_decision.py:301`（`len(STALL_REASON_CODES)`）、`:333`（`len(calls)`）；`:338` 集合相等在计数修正后自洽（调用点 14 = 源码 14）；陈旧测试名/注释里的 `twelve` 字样已更名 |\n"
    "| timeline 事件集合 | 23 → **27** | `test_autopilot_timeline.py`：硬数字改为**对照 `LOCKED_EVENT_TYPES`（27 名字面量）的集合相等** + 派生 seq 区间；PM 认可其强于硬数字（增删都逼人改字面量）|\n"
    "| 配置键数 | 17 → **20** | `test_autopilot_config_parity.py:60-61`（sha `4921…`→`1e27…`、例数 64→73）+ `:422-426` 计数/注释；`autopilot-config-sync.test.ts` sha/计数；`autopilot-config-parity.test.ts` 17→20（×2）|\n"
    "| 冻结语料 | 64 → **73** 例 | `autopilot-config-corpus.json` **只追加**：3 条单键 accept（T-02 三键）+ 6 条越界 reject（两界/键）|\n"
    "| TS 事件集合 | +`contract-frozen` | `status-model.ts EVENT_TYPES`（T-23 欠的 TS 半边）；`autopilot-event-parity.test.ts` 本就是集合相等 ⇒ 无数字改动，`count=27` 绿 |\n"
    "| TS gates 行形状 | 无需改 | `autopilot-console.test.ts:374-378` 经核实已是 T-05/T-12 后的 `{id,kind,status,ageMs}`（`authorizes` 不进 `GateView`）|\n\n"
    "- `test_autopilot_readcap_injection.py`：**无需**再重冻（`test_autopilot_config.py` 未被本卡改动，T-02 的 golden 保持）。\n"
    "- PM 亲跑：Python 三文件 **47 passed**（开工前 4 红全消）；TS 四文件 **47 passed**；"
    "`[VERIFY] P6: partial_single_key=35 raw_view_partial=true effective_view_20=true fields_covered=20`。\n"
    "- 四组非空洞对照 A~D（`STALL_REASON_CODES` 回 12 / 摘一条语料 accept 例 / 摘 `timeline.EVENT_TYPES` 的 `contract-frozen` / 摘 TS 侧同名）均转红并逐字节还原。\n"
    "- 回执：`evidence/runs/t-14-count-locks-report.md`。\n"
)
write(t14, t14t)

# ---- plan: T-16 row note + R21 ----
plan_p = ROOT / "plan.md"
plan = read(plan_p)
old = "| T-16 | 文档 + dist + 全量回归 | 5 | 全部 | 全部 | `CHANGELOG.md`×2（两包）+ `dist/**` 重建 + 基线对照 |"
assert plan.count(old) == 1
plan = plan.replace(
    old,
    "| T-16 | **文档收口 + 全量回归 + 切换 runbook** | 5 | 全部 | 全部 | `CHANGELOG.md`×2（两包）+ `verify-closure.md`（基线对照，新增红=0）+ 运行时切换 runbook（**只写不执行**）；"
    "**`dist/**` 重建已按 D-059 拆出**（需用户批准后 PM 直执）|",
)
plan += (
    "\n| R21 | **`dist`/bundle 未重建 ⇒ 本轮全部 TS/扩展改动尚未生效**"
    "（运行时仍是 10-10 10:53 的 `b8bc115ff` 时代 bundle + 常驻 launcher 的进程内旧代码）| T-16 收窄（D-059）| "
    "T-16 产出 `runtime-cutover-runbook.md`（命令/前置/验证/回滚）；用户批准后 PM 直执 `mw build --install --allow-dirty` + 重启 launcher/serve + "
    "重启 9 个 pre-10:53 旧窗口；在那之前每次 dispatch 都会把队列翻成 9 列（PM 每次归一回 8 列，脚本 `evidence/scripts/t23-normalize-whole-queue.py`）|\n"
)
write(plan_p, plan)
print("ok")
