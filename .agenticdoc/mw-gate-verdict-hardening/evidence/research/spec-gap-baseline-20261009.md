# Research: 三条 reflect 缺口的框架侧基线（spec）

> Key: mw-gate-verdict-hardening ｜ 角色: PM（只读） ｜ 快照: 2026-10-09
> 决策问题：本 key §1 范围（收哪三条缺口）、§4 风险（写面冲突）、以及派发给 RQ-1/2/3 的边界。
> 说明：本文是 PM 本轮的只读基线；RQ-1/2/3 的深化结论另见同目录 `spec-l3-abort-taxonomy-*` / `spec-pending-gate-alert-surfaces-*` / `spec-gate-authorization-scope-*`。所有事实带 `文件:行号`（工作树 = 2026-10-09，`HEAD=aafaa378b`）。

## 调研方法与出处

- 只读 grep/read：`packages/multi-workers/autopilot/*.py`、`packages/multi-workers/*.py`、`packages/coding-agent/src/extensions/agent-team-loop/**/*.ts`。
- 只读跨项目：`H:\git\E2Feature\.agenticdoc\_autopilot\reflect\`（11 条，README 索引）。
- 只读本仓 key 档案：`.agenticdoc/mw-autopilot-slot-capacity/{plan.md,tasks/**,evidence/research/**}`。
- `git log` / `git status`（判定写面冲突）。

## 发现

### F1 三条缺口对应框架侧的现状

| 缺口 | 现状（可定位） | 缺口本身 |
|---|---|---|
| G1 L3 流中止 | `l3-no-verdict` 事件路径存在（conductor L3 段）；provenance guard 存在（`conductor.py:1508` `_PROVENANCE_FILENAME`、`:1620 _l3_provenance_record`、`:1715 _persist_l3_provenance`）；裁决源回退 `_L3_SOURCE_ORDER`（commit `a0c36fcce`） | 全仓 `l3-aborted` / `stream closed` **零命中**（`Get-ChildItem -Recurse -Include *.py,*.ts … \| Select-String`）⇒ 中止无指纹、无专项重掷 |
| G2 pending gate 静默 | T-08 已做 `expires_at = created_at + 48h` + `review-escalated`（`conductor.py:2863` 读 `gate.expires_at`、`:2909` `review-escalated`）；T-13 已做 doctor gate 段（`mw_common.py:2534+` 段与 I1–I9） | 全仓 `BLOCKED_ON_HUMAN` / `gate_pending` / `remind` / `nudge` 零命中；无"pending 超 N 分钟提醒"；`MonitorGate` 是否带 age 需 RQ-2 定 |
| G3 闸门授权范围 | gate schema v2 已有 `write_scope`/`blast_radius`/`out_of_band_actions`/`answer_source`（`gates.py:29-34,102-126,158-159`）；T-24 已做散文授权机器判定（`mw_common.py:2559 _crosskey_prose_decision`、`:2614 _crosskey_prose_scan`、`:2769` I 类 issue） | 无 `authorizes:` 显式字段（`authorizes` 仅 4 处命中，均为无关文案/测试名）；`advance *->done` 前无 AC/VC 文本变更的机械检查 |

### F2 写面冲突（决定性约束）

- `git status --short` 显示 `packages/multi-workers/autopilot/{conductor.py,gates.py,config.py,dispatch.py,roadmap.py,timeline.py,evidence.py}` 与 `packages/coding-agent/.../autopilot/{status-model.ts,monitor.ts,console.ts}` 均为**未提交改动**（`conductor.py` 工作树 6023 行 vs `HEAD` 3773 行）。
- 这些文件正是 `mw-autopilot-slot-capacity`（`_index.parallel`：EXECUTE，claim `WENBOZHOU-PC4:18200`）的写面（其 `plan.md` §1.1 明确"唯一热点 conductor.py，四段串行"）。
- ⇒ 本 key 的 spec/design（纯文档 + 只读调研）可立即开工；**EXECUTE 必须等该 key 提交**（判据：`git status` 干净 / 相关文件已入 commit）。

### F3 依赖与先例

- `mw-autopilot-slot-capacity` 的 24 张卡已有本 key 三条缺口的"近邻"实现（消费载体 T-05、证据快照 T-06、自决策 T-07、待复核 T-08、doctor T-13、散文授权判定 T-24）；本 key 是在其之上的**补口**，不是重做。
- 现成可复用：timeline 事件 + `_timeline_has_event` 去重、gate 允许集机制、`_l3_provenance_record`（"来源可疑⇒机械降级"先例）、`_crosskey_prose_scan`（"散文不当授权"先例）。

## 结论 → 决策映射

- 支撑 §1 范围：三条缺口各自独立、可单独验收（G1=裁决面、G2=人机交接面、G3=授权面），归入一个 key 的理由是共享同一写面与同一批先例（证据见 F1/F3）。
- 支撑 §4 R1：写面冲突是**硬约束**而非提示（F2）⇒ plan 必须把"等 `mw-autopilot-slot-capacity` 提交"列为 EXECUTE 前置门禁。
- 支撑派发边界：RQ-1/2/3 分别只覆盖 G1/G2/G3，互不重叠；三条都需要 file:line 锚点与真实语料（P-014 正负双穷举）。

## 数据缺口

- 本 key 自身 `EXECUTE` 前无法得到"改后"的端到端数字（需等写面释放）；本文所有数字是"改前基线"。
- E2Feature / FeatureMigrator 的 gate 与 worker 语料为只读引用，冻结时刻见各 RQ note。

`[VERIFY] baseline: gaps=3(l3-aborted=0 hits, gate_reminder=0 hits, authorizes_field=0) worktree_dirty=conductor.py(6023 vs HEAD 3773) conflicting_key=mw-autopilot-slot-capacity(EXECUTE) reusable={timeline_dedup,gates_allowlist,l3_provenance,crosskey_prose} reflect_open=6(of 11)`
