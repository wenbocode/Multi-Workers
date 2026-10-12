"""AC-025 / T-23 doc updates, part 2: plan.md + T-14 card (part 1 wrote spec/design)."""

import pathlib

ROOT = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening")


def read(p):
    return pathlib.Path(p).read_text(encoding="utf-8")


def write(p, t):
    pathlib.Path(p).write_text(t, encoding="utf-8", newline="\n")


plan_p = ROOT / "plan.md"
plan = read(plan_p)
assert "T-23" not in plan, "part 1 already applied?"

old_scale = "- 规模：**24 AC / 46 VC / 49 功能点**"
assert plan.count(old_scale) == 1
plan = plan.replace(
    old_scale,
    "- 规模：**25 AC / 47 VC / 50 功能点**"
    "（AC-025 / VC-047 / F47 于 2026-10-10 追加：G3 锚点建立，补齐 AC-011 的可达性，见 T-23）",
)

lines = plan.splitlines()
i = next(idx for idx, l in enumerate(lines) if l.startswith("| T-22 |"))
lines.insert(
    i + 1,
    "| T-23 | **AC-025 G3 锚点建立（自动 + 显式）** | 3 | AC-025 | VC-047 | "
    "`conductor.py` 见 design 冻 AC / 见 plan 冻 VC（幂等一次写、不回溯）+ `mw autopilot contract-freeze` CLI "
    "+ `timeline.py` 事件 `contract-frozen`；**不碰计数锁**（T-14 补 TS 镜像与 27 事件数） | + T-04, T-10, T-11 |",
)
plan = "\n".join(lines)

old_chain = "`conductor.py`（T-01→T-07→T-10）、"
assert plan.count(old_chain) == 1
plan = plan.replace(old_chain, "`conductor.py`（T-01→T-07→T-10→**T-23**）、")

plan += (
    "\n| R19 | **G3 锚点仍未覆盖“错过边界”的 key**（conductor 未运行时穿过 design/plan 的 key，"
    "或 feature 上线前已在 execute 的历史 key）⇒ 无锚 ⇒ 不受 G3 保护 | T-23 | "
    "按设计**不回溯**（P-018）：这类 key 的守卫需由人显式 `mw autopilot contract-freeze` 建立；"
    "残余状态在 `mw doctor` / `mw autopilot contract-guard --key K` 上可见（后者明确打印 `no freeze sidecar`）|"
)
write(plan_p, plan)

t14_p = ROOT / "tasks" / "T-14-count-locks.md"
t14 = read(t14_p)
assert "PM 追记（2026-10-10 19:00" not in t14
t14 += (
    "\n\n## PM 追记（2026-10-10 19:00，T-23 落地后必须一并刷新）\n\n"
    "T-23（AC-025，G3 锚点建立）新增了一个 timeline 事件名 **`contract-frozen`**"
    "（Python `timeline.py::EVENT_TYPES` 已加）。因此本卡的计数锁必须按**新数字**刷新，两侧同时：\n\n"
    "| 锁 | 就绪前 | **就绪后（本卡）** | 位置 |\n"
    "|---|---|---|---|\n"
    "| timeline 事件集合 | 23 → 26 | **27**（+`contract-frozen`）| `test_autopilot_timeline.py:48/53/54`"
    "（建议改为对 `EVENT_TYPES` 的集合相等断言）|\n"
    "| TS 事件集合 | 集合相等 | **27**，`status-model.ts EVENT_TYPES` += `contract-frozen` | "
    "`autopilot-event-parity.test.ts`（两侧集合相等）|\n"
    "| `reason_code` 数量 | 12 | **14**（T-01/T-10 已落，本卡只改锁）| "
    "`test_autopilot_auto_decision.py:301/333/338` |\n"
    "| 配置键数 | 17 | **20** | `test_autopilot_config_parity.py` + 冻结语料 + `autopilot-config-sync.test.ts` |\n\n"
    "- **新增事件名的 TS 半边归你**（T-23 不碰 `status-model.ts`，以免与 T-12 的 `authorizes` 镜像同文件冲突）。\n"
    "- 若 `test_autopilot_timeline.py` 已改成动态读 `EVENT_TYPES`，则本卡只需保证**两侧集合相等**且 TS 侧含 "
    "`contract-frozen`，并在回执里说明“集合相等比硬数字更强”的理由。\n"
)
write(t14_p, t14)
print("plan + T-14 updated")
