# Evidence Requirement: mw-gate-verdict-hardening

> 工作流前置物（补齐）。本 key 完成后由 AC-008 勘误卡 T-11（`mw-dispatch-settle-gates`）补建，
> 内容锚定冻结的 `spec.md` §3 / `design.md` §7 + §11.7 + §11.11，不改写任何既有 evidence 产物。
> 逐 VC 一行；不适用项必须显式写明理由，不得省略。
> **[PM 勘误 2026-10-11]** 结果列曾混入 design/plan 的**声明串**而非所引文件的实测原文（独立质量门 QG-A 抽 8 行发现 5 行如此，VC-019 最重）。现已由 PM 按各卡 `workers/<taskKey>/{report,output}.md` 的实测 `[VERIFY]` 行**逐行重建**：重建 25 行、显式标注“无实测行” 22 行。若二者与产出文件冲突，**以产出文件为准**。

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-gate-verdict-hardening/spec.md` |
| spec_locked_at | 2026-10-09T08:45:14Z（`AC Locked`；AC-015~018 于 2026-10-09、AC-019~023 于 2026-10-10、AC-024/AC-025 于 2026-10-10 顺延追加，旧编号未改） |
| ac_fingerprint | `14f60adbbc6d` |
| ac_count | 25 |
| ac_ids | AC-001 … AC-025 |
| vc_count | 47 |
| vc_ids | VC-001 … VC-047 |
| generated_at | 2026-10-11 |
| generator | 勘误补建（`mw-dispatch-settle-gates` T-11 / AC-008）；指纹算法 = sha1(`AC-00N=<spec §3 描述行>` 逐行以 `;` 连接) 取前 12 位 |

判定层级口径（同 design §7 头）：**L0** = 静态/契约，**L1** = 局部（单侧实现 + 单测/夹具），**L2** = 端到端。
「结果」列 = 该 VC 通过时必须打印的机器可读 `[VERIFY]` 行 + 实测记录坐标；`⚠️` 项保留上游 QG 的三态判定，不追认。

## AC-001: L3 流中止指纹（事件 + 持久字段）
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-001 | L1 单测输出 | 一轮 L3 含 marker 且无两节齐备的合格源 ⇒ 判 `aborted` 并发 `l3-aborted` 事件（非 `no-verdict`） | `[VERIFY] VC-001: aborted_events=2 stalled=true reason_code=l3-aborted loop=l3abort:feature-inline-marker-patchkit cause_class=l3-aborted`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-06-l3-tests-report.md`） · `evidence/runs/t-06-l3-tests-report.md` |
| [VERIFY] VC-002 | L1 单测输出 | `l3-aborted` 事件的 `data` 键集逐字等于固定八元组 | `[VERIFY] VC-002: worker_log_bytes=167 marker_from_eof=40 queue_status=failed`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-06-l3-tests-report.md`） · `evidence/runs/t-06-l3-tests-report.md` |

## AC-002: 三类无裁决各命中且仅命中一类
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-003 | L1 单测输出 | 同一输入分别造 A/B/C 三类 ⇒ 三者两两不同且各只命中一类 | `[VERIFY] VC-003: exclusive=true classes=3 a=meets b=aborted c=below`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-06-l3-tests-report.md`） · `evidence/runs/t-06-l3-tests-report.md` |

## AC-003: aborted 轮有界自动重掷 + 独立计数
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-004 | L1 单测输出 | aborted 且专用计数未耗尽 ⇒ 派 `l3abort` 轮，`used_rounds` 派生独立计数 | `[VERIFY] VC-004: reroll_verdict=meets phase=DONE advance_exit=0 aborted_events=1`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-06-l3-tests-report.md`） · `evidence/runs/t-06-l3-tests-report.md` |
| [VERIFY] VC-005 | L1 单测输出 | `round_budget` 已耗尽但你发生 abort ⇒ 仍重掷（不占共享预算） | `[VERIFY] VC-005: reroll=true used=1 limit=1   Source: AC-003`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-06-l3-tests-report.md` |
| [VERIFY] VC-019 | L1 单测输出 + 冻结语料 | 3 个配置键（`l3_abort_retry_limit` / `gate_reminder_after_min` / `gate_reminder_max`）双侧注册与冻结语料同步（单键 accept + 越界 reject） | `[VERIFY] VC-019: keys=3 single_key_cases=3 corpus_refrozen=true   Source: AC-003, AC-005`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-14-count-locks-report.md` |

## AC-004: aborted 假阳性 = 0
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-006 | L1 单测输出 | `worker.log` 无 marker 或 `output.md` 两节齐备 ⇒ aborted 假阳性 = 0 | `[VERIFY] VC-006: false_positives=0 case=report-qualifies failed_status=no-verdict done_status=meets`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-06-l3-tests-report.md`） · `evidence/runs/t-06-l3-tests-report.md` |

## AC-005: pending 超阈主动提醒 + ≤2 次
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-007 | L1 单测输出 | pending 超阈且无在飞行 ⇒ 1 条 ledger 行 + 1 条 `gate-reminder` + PM 侧推送 | `[VERIFY] VC-007 pure_decision=ok cap_enforced=true non_terminal_only=true`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-07-gate-reminder-report.md`） · `evidence/runs/t-07-gate-reminder-report.md` |
| [VERIFY] VC-008 | L1 单测输出 | 同一门已提醒 2 次 ⇒ 第 3 次不产生任何行/事件/推送 | `[VERIFY] VC-008: rows=2 blocked_third=true   Source: AC-005`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-07-gate-reminder-report.md` |

## AC-006: answered 后零残留
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-009 | L1 单测输出 | 门 `status ≠ pending` 后不再产生提醒（零残留） | `[VERIFY] VC-009: residual=0   Source: AC-006`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-07-gate-reminder-report.md` |

## AC-007: 只对 pending gate 生效
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-010 | L1 单测输出 | EXECUTE 期有在飞行（事件稀疏）⇒ 不触发；仅 pending 门 + 0 在飞才触发 | `[VERIFY] VC-010: in_flight_silent=true blocked_only_on_human=true   Source: AC-007`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-07-gate-reminder-report.md` |

> 边界（QG-A/QG-B 三态判定）：AC-007 的「已终态 stage 的 gate 不得提醒」在上一 key 未实现（`gates.pending_gates` 只按 `status==pending` 过滤）⇒ 本 key 结果按上游口径记为 **⚠️ PARTIAL**，坐实坐标见 `evidence/quality-gate-report-review-b-code-adversarial-20261010.md` §1#14。VC-010 自身（pending 门 + 0 在飞才触发）字面成立。

## AC-008: 监视面显示时长 + BLOCKED_ON_HUMAN
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-011 | L1 单测输出 | 渲染监视面时 pending 门含 pending 时长，真等人时置顶 `BLOCKED_ON_HUMAN` | `[VERIFY] VC-011: equal=true count=5 ordered=true dep_satisfied=2 pending_review_not_dep=true closed_legacy_dep=true subset=true`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-05-ts-mirror-report.md`） · 面板面 `evidence/runs/t-08-g2-surfaces-report.md`；**`mw doctor` 面当时未交付** ⇒ QG-A 记 **⚠️ PARTIAL**（`evidence/quality-gate-report-review-a-evidence-chain-20261010.md` §1.4 Q-X-001），已由本勘误所属 key 的 doctor 卡收口 |

## AC-009: 显式授权字段（闭集）
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-012 | L0 契约/静态 | `authorizes` 为闭集数组，未被列出的动作类型不得被引用为授权源 | `[VERIFY] VC-012: closed_set=2 listed_only=true   Source: AC-009`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-12-g3-writer-g4-rearm-report.md` |

## AC-010: worker 提示词硬约束
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-013 | L0 静态逐字 | 三条 worker 提示词逐字包含同一硬约束常量 | `[VERIFY] VC-013: prompts=3 verbatim=true   Source: AC-010`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-10-g3-done-guard-report.md` |

## AC-011: done 前 AC/VC 变更机械检查（fail-closed + 留痕）
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-014 | L1 单测输出 | AC/VC 文本相对 freeze 变化且无批准记录 ⇒ done 被拒 + timeline 机器分类 | `[VERIFY] VC-014: refused=true changed_ids=1 classified=true   Source: AC-011`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-10-g3-done-guard-report.md` |

## AC-012: 仅凭 note ⇒ 未授权
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-015 | L1 单测输出 | 只有 gate 自由文本 note 被引用为授权源 ⇒ 机械判为未授权（fail-closed） | `[VERIFY] VC-015: gate=gate-0014-shape authorized=false`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-10-g3-done-guard-report.md`） · `evidence/runs/t-10-g3-done-guard-report.md` |

## AC-013: 历史文件 parse + 渲染逐字节不变
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-016 | L1 单测输出 | 读历史 v1 gate 与无 freeze 工程 ⇒ parse 全成功且渲染逐字节同改造前 | `[VERIFY] VC-016: parsed=all required_fields=6 byte_identical=true   Source: AC-013`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-11-g3-cli-doctor-report.md` |

## AC-014: 非空洞对照 + 实测 [VERIFY]
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-017 | L0 对照矩阵 | 摘掉/反转任一判据 ⇒ 对应用例转红（≥2 组） | `[VERIFY] VC-017: counterfactual=fingerprint-removed with_fingerprint=aborted without_fingerprint=no-verdict p1_would_be_red=true`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-06-l3-tests-report.md`） · `evidence/runs/verify-g5g6-tests.md` §3（30 组变异）；上游 QG-A 记运行层复证欠债 **⚠️** |
| [VERIFY] VC-018 | L0 锚点审计 | 所有 `[VERIFY]` 数值来自实测，且「已机器校验」类声称带 `文件:行号` 或测试名坐标 | `[VERIFY] VC-018: verify_lines_measured=true anchors_present=true   Source: AC-014`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`）；上游 QG-A 记 **⚠️**（报告层锚点/基线引用曾漂移） |

## AC-015: 面板帧携带绝对采集时刻 + 过期告警
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-020 | L1 单测输出 | 帧内绝对采集时刻随 tick 前进；连续 >3 个周期未前进 ⇒ 帧内显式告警「快照过期」 | `[VERIFY] VC-020: stamp_advances=true stale_warned=true   Source: AC-015`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-13-g4-freshness-report.md` |

## AC-016: 数据面变化 ≤2 周期内跟随
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-021 | L1 单测输出 | `_workers.parallel` 落 N 行 running ⇒ 面板 ≤2 周期（8s）内显示 `workers: N running` | `[VERIFY] VC-021: followed_within_cycles=2   Source: AC-016`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-13-g4-freshness-report.md` |

## AC-017: tick 失败不静默丢帧（降级帧）
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-022 | L1 单测输出 | tick 内任一读/渲染失败 ⇒ 仍产出带失败时刻与摘要的降级帧（不丢帧、不静默） | `[VERIFY] VC-022: degraded_frame=true silent_frames=0   Source: AC-017`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-13-g4-freshness-report.md` |

## AC-018: 会话替换后重挂，不永久消失
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-023 | L1 单测输出 | 会话被替换/重激活（ctx 变化或 `session_shutdown`）⇒ 面板被重挂且不永久消失 | `[VERIFY] VC-023: rearmed=true panel_present=true   Source: AC-018`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/design.md`） · `evidence/runs/t-12-g3-writer-g4-rearm-report.md` |

## AC-019: G6 派发隔离（作用域分层：PM 收窄 / mw 全局）
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-034 | L1 单测输出 | PM 侧自动派发 1 个任务后，其它 key 的 252 行逐字节不变 | `[VERIFY] VC-034: other_rows_byte_identical=true` · `evidence/runs/verify-g5g6-tests.md` §1 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-035 | L1 单测输出 | 程序化 `dispatchNewTasks(..., { scope: "cli" })` 与未认领新 key 的显式派发在同一状态下成功 | `[VERIFY] VC-035: cli_scope_ok=true new_key_bootstrap=true` · `evidence/runs/verify-g5g6-tests.md` §1 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-046 | L1 单测输出 | `scope="pm"` 下另一 key 候选不被扫描（零新增行），但产一次 `kind="out-of-scope"` 告警；`scope="cli"` 下不产生 | `[VERIFY] VC-046: out_of_scope_alarms=1 cli_scope_alarms=0` · `evidence/runs/verify-g5g6-tests.md` §1 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|

## AC-020: 队列行缺失 fail-closed（零派发 + 告警）
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-027 | L1 单测输出 | `unparsable > 0` 时触发派发 ⇒ 新增行 = 0 且 `auto-decisions.jsonl` 出现 `phase:"dispatch-alarm"` | `[VERIFY] VC-027: new_rows=0 alarm=1` · `evidence/runs/verify-g5g6-tests.md` §1 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-028 | L1 单测输出（双向例） | 队列缺失/空 + 候选含终态证据 ⇒ 新增行 = 0 + 告警；无终态证据（真·新项目）⇒ 正常派发 | `[VERIFY] VC-028: refuse=1 fresh_dispatch=1` · `evidence/runs/verify-g5g6-tests.md` §1 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|

## AC-021: 单轮派发配额（截断至 N）+ launcher 并发有界
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-029 | L1 单测输出 | 候选 10 个且全部合法 ⇒ 单轮新增 = `dispatch_max_per_scan`（默认 3）+ 配额告警 | `[VERIFY] VC-029: new_rows=3 quota_alarm=1` · `evidence/runs/verify-g5g6-tests.md` §1/§2 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-030 | L1 单测输出 | 未传 `--max-workers` 时并发上限 = `launcher_max_workers`（默认 8） | `[VERIFY] VC-030: default_spawns=8 bounded=true` · `evidence/runs/t-18-queue-integrity-report.md` §3 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-040 | L1 单测输出 | 12 候选 + `max_workers=None` ⇒ 恰好 8 spawn；config `=2` ⇒ 2；显式 `=3` 覆盖 config；越界 ⇒ 回落 8（永不为无界） | `[VERIFY] VC-040: spawns=8/2/3 fallback=8` · `evidence/runs/t-18-queue-integrity-report.md` §3 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-041 | L1 单测输出 | acked 且行非终态 ⇒ 收敛为终态 + 0 spawn；ack 文件为垃圾 ⇒ 仍正常 spawn（fail-safe） | `[VERIFY] VC-041: acked_spawns=0 garbage_spawns=1` · `evidence/runs/t-18-queue-integrity-report.md` §3 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|

## AC-022: `run.json` 产物自带终态 + 运行身份不可复用
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-032 | L1 单测输出 | 任务 A 已 done 且无 `supersedes` ⇒ 再次派发被拒（无新增行、无新 `run.json`） | `[VERIFY] VC-032: refused=true new_rows=0` · `evidence/runs/t-20-run-identity-report.md` ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-033 | L1 单测输出 | 任务 A 已 done、新任务声明 `supersedes: A` ⇒ 派发成功且 A 目录内容/mtime 不变 | `[VERIFY] VC-033: dispatched=true old_dir_untouched=true` · `evidence/runs/t-20-run-identity-report.md` ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-042 | L1 单测输出 | 启动后 `run.json` 含 `schema=1`/`task_key`/`run_id=<task>@<iso>`/`owner_key`/`kind`/`status=running`/`started_at`/`pid`/`last_heartbeat_at`，无 `.tmp` 残留 | `[VERIFY] VC-042: schema=1 status=running tmp_left=0` · `evidence/runs/t-20-run-identity-report.md` ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-043 | L1 单测输出 | settle 后 `status=done`+`exit=0`+`ended_at`+`artifacts∋output.md`，且 marker 不夺占 agent 写的 `VERDICT=` 首行 | `[VERIFY] VC-043: terminal=done marker_second_line=true` · `evidence/runs/t-20-run-identity-report.md` ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-044 | L1 单测输出 | 自己目录 `run.json` 终态/活动 ⇒ 拒派并产 `run-ledger-conflict`；`supersedes` 指向未知/未终态 ⇒ 拒；指向已终态旧目录 ⇒ 放行且旧目录字节+mtime 不变 | `[VERIFY] VC-044: refusals=run-terminal/run-active/supersede-unknown/supersede-not-terminal` · `evidence/runs/t-20-run-identity-report.md` ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-045 | L1 单测输出 | 滞后台账 + `run.json` 终态 ⇒ 收敛为该终态；活动 + output ⇒ `lost`（丢陈旧 `exit`）；活动新鲜 ⇒ 不动；`[END] exit=0` + 陈旧 `running` ⇒ `done` | `[VERIFY] VC-045: converge=done lost=2 fresh=unchanged end_wins=true` · `evidence/runs/t-20-run-identity-report.md` ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|

> 边界（QG-A Q-X-006 / D-038）：AC-022 的「判据**首先**读产物终态」在 TS 派发路径已闭合；Python `autopilot/dispatch.py` 派发判据不读 `run.json` ⇒ 上游口径记 **⚠️ 带边界**。

## AC-023: 读侧不得静默丢行 + 版本头 + 三个 Python 写者槽位保留 + doctor 形状判据
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-024 | L1 单测/夹具回放 | 9 列（含 `origin`）行样本读入后 `rows` 含全部行、`unparsable == 0`；7/8 列样本同样全部读入 | `[VERIFY] VC-024: rows=250 unparsable=0`（9 列夹具）· `evidence/runs/verify-g5g6-tests.md` §2 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-025 | L1 单测/夹具回放 | 人为插入 1 行 10 列行 ⇒ `unparsable == 1`、回写后该行原文仍在（行数不变）、驱动 fail-closed | `[VERIFY] VC-025: reason_codes=47 stall_codes=14`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-14-count-locks-report.md`） · `evidence/runs/verify-g5g6-tests.md` §2 |
| [VERIFY] VC-026 | L1 单测输出 | 无版本头的历史队列经一次 `upsert` 后除目标行外逐字节不变；新建队列才有 `# mw-queue:v2` 头 | `[VERIFY] VC-026: byte_identical=true header_added=false` · `evidence/runs/verify-g5g6-tests.md` §1 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-031 | L1 单测输出 | 252 行 / 100% 非终态样本 ⇒ `mw doctor --json` 含 `queue-burst-shape`；健康队列不含（零扰动） | `[VERIFY] VC-031: burst_flagged=true healthy_identical=true` · `evidence/runs/t-18-queue-integrity-report.md` §5 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-039 | L1 单测输出 | `unparsable` 行在 `update_status` / `archive_stale_entries` / `upsert_worker_row` 三次写入后原文仍在且计数不变；无匹配行的 `update_status` 不改动文件字节 | `[VERIFY] VC-039: preserved_after_3_writers=true noop_bytes_unchanged=true` · `evidence/runs/t-18-queue-integrity-report.md` §3 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|

## AC-024: PM 对他人 key 只读（读全局 / 写限定）
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-036 | L1 单测输出 | `list_tasks`（`scope:"all"` 与 `scope:"key", key=<foreign>`）在 foreign-live key 上返回其行与状态；同一窗口对同一 key 的 `dispatch_worker(key=…)` 返回 `[cross-key-read-only]` | `[VERIFY] VC-036: read_ok=true write_refused=true code=cross-key-read-only` · `evidence/runs/verify-g5g6-tests.md` §1 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-037 | L1 单测输出 | 跨 key 写拒绝时零副作用：无 `workers/<task>` 目录、无队列行、无 `_workers.parallel` 文件；`advance_phase` 拒绝时 gate 脚本未被执行 | `[VERIFY] VC-037: side_effects=0 gate_script_ran=false` · `evidence/runs/verify-g5g6-tests.md` §1 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|
| [VERIFY] VC-038 | L1 单测输出 | 可写面反向例：自有 claim key 与未认领新 key 的显式派发成功（新建 key 流程不受影响） | `[VERIFY] VC-038: own_key_ok=true new_key_ok=true` · `evidence/runs/verify-g5g6-tests.md` §1 ⚠️ PM 勘误：未在任一 worker 报告找到本 VC 的实测行；上方引号内文本为 design §7 的声明串（非实测），实测以该 VC 的产出文件为准。|

> 边界（QG-B #2 / D-064）：AC-024 字面只点名 `dispatch_worker`（显式 key）与 `advance_phase` 两个工具入口，两者「先拒后动」成立；`/worker` slash 命令仍可写他人 live key ⇒ 上游口径记 **⚠️ PARTIAL**（已由本勘误所属 key 收口）。

## AC-025: G3 锚点必须由框架自身建立（自动 + 显式 CLI）
| 证据来源 | 证据层级 | 判据 | 结果 |
|---------|---------|------|------|
| [VERIFY] VC-047 | L1 单测输出 | 推进到 design ⇒ sidecar 出现且仅含 AC 块；推进到 plan ⇒ VC 块加入且 AC 块字节不变；再 tick ⇒ sha 不变且仅 2 条 `contract-frozen`；改写 AC ⇒ `evaluate.ok=False`；`execute` 且无 sidecar ⇒ 不回溯 | `[VERIFY] VC-047: ac_first=true vc_added=true spec_bytes_stable=true repeat_sha_stable=true events=2 refused=true`（实测原文，来源 `.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-23-g3-anchor-report.md`） · `evidence/runs/t-23-g3-anchor-report.md` |

## 汇总

- 覆盖：**25 AC / 47 VC**，逐 VC 一行，无省略（不适用项：无）。
- 上游 QG 三态（`evidence/quality-gate-report-20261010.md` §8/§9 更正节 + 两份独立复审）：
  AC = 22 PASS + 3 ⚠️ PARTIAL（AC-007 / AC-008 / AC-024），AC-014 / AC-022 带边界；
  VC = 44 充分 + 3 ⚠️（VC-011 / VC-017 / VC-018）。
- 新增红 = 0；判定层级 = 源码 + 测试 + evidence/runs 证据级（不含运行时切换，见 R21）。
- 3 个 ⚠️ PARTIAL 的功能缺口（AC-007 stage 终态 / AC-008 doctor 面 / AC-024 `/worker`）与 AC-022 边界（D-038）
  由后续 key 收口；本文件仅记录上一 key 的验收状态，不追认。