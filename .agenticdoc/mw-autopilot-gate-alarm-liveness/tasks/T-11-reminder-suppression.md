# T-11 — 提醒抑制改按 key + fail-loud 双通道 + cap 降级为"打断次数"

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-002, AC-004
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/design.md` §2 D2/D4、§5；
      `evidence/research/spec-rq1-reminder-chain-20261013.md`、`design-drq4-auto-approve-20261013.md`

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（无人值守；"看上去在跑、其实什么都不发生"必须被消除）。
- 已核实锚点（自行复核）：
  - `packages/multi-workers/autopilot/conductor.py:2558`（`if any(_is_in_flight(row) for row in rows): return []` —— **全项目级**抑制）。
  - `:2559-2561`（cap 判定）、`:2562-2566`（stage 终止抑制）、`:2511-2524`（`_reminder_count`）、`:2688-2735`（`_remind_pending_gates`：台账行 `:2708`、timeline `:2717`、**函数体内无 stderr**）、`:2594-2660`（`_emit_roadmap_failure`/`_emit_roadmap_warnings` 的 stderr + timeline `config` 封装，可复用）、`:2617`（roadmap 告警的 stderr 对照）。
  - `packages/multi-workers/autopilot/config.py:57/:103/:134`（`gate_reminder_max` 默认 2、闭区间 `[1,2]`）；TS 镜像 `autopilot/status-model.ts:190-191`。
  - `packages/multi-workers/mw_common.py:3279-3291`（`blocked_on_human` 项目级轴）、`.../autopilot/monitor.ts:442` 邻域（同名判定）。
- 关键事实（驱动本卡）：`gate-0024` 的 n=1/n=2 **相隔 4 秒**烧完 cap 后静默 158.3 min；cap 计数**持久化在台账** ⇒ 只改事件面无效；被压制的重复 stage-close 实例静默 **6.78 h**；两条提醒能发出只因 roadmap 恰好不可读触发 fail-open。

## 要求

1. **抑制粒度改按 gate 所属 key**：仅当"该 gate 所属 key 存在在飞工作"时抑制；**key/stage 不可解析一律不抑制**（沿 `:2535-2550` 既有 fail-open 原则）；存量实例 `JCodingAss gate-0007/gate-0008` 是 `kind: stage-close` 且 **key 为空**，必须仍能被提醒。
2. **被抑制也留可见记录**（上游 P0-② 原文要求）：每次因在飞/终止/cap 而抑制时，留下可读记录（台账或 timeline），至少含 gate id、原因、已等时长。
3. **每次发射走 fail-loud 双通道**：stderr + timeline，内容含 gate id/kind/key/已等时长/原因/可执行动作；复用 `:2594-2660` 的封装形态（必要时提升为通用 alarm helper，**不得新造第二条通道**）。
4. **`gate_reminder_max` 语义降级为"打断次数"**：cap 用尽后不发中断，但状态面照旧且标注"已达打断上限，仍待处理"；限频只防刷屏。同步 TS 镜像（`status-model.ts`）与 parity 测试，**不新增 config 键**（AC-011）。
5. **stage 终止抑制必须留痕**：`:2562-2566` 的抑制同样要可见（当前完全静默）。
6. **`blocked_on_human` 三处同批改**：本卡负责 `packages/multi-workers/mw_common.py:3279-3291` 与 TS `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts:442` 邻域两处（T-10 负责 `status-model.ts:1349-1356`）；三处轴语义必须一致（per-key）。

## 写入允许面

- `packages/multi-workers/autopilot/conductor.py`（**仅** `:2500-2740` 区段与 `blocked_on_human` 相关部分；其他区段属 T-12/T-14/T-16）
- `packages/multi-workers/mw_common.py`（仅 `_blocked_on_human`）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`（仅 `blocked_on_human` 相关处；**不得**动渲染段与 `GateView` —— 那属 T-10）
- `packages/multi-workers/test_mwgal_t11_suppression.py`（新增）
- 既有 Python 测试中与抑制语义直接相关的用例（只改**夹具数据**，不改判据）

## 写入禁止面

- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（属 T-10）
- `packages/multi-workers/autopilot/gates.py`（属 T-14）
- `packages/multi-workers/mw.py`（属 T-13）
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/multi-workers` 目录：`python -m pytest test_mwgal_t11_suppression.py test_autopilot_gate_schema_v2.py -q`

## 改动历史

（填写改动文件 + 每处为什么；特别说明"为什么不能用退避曲线"—— 用户裁定 gate 时间不保险，状态面优先。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
