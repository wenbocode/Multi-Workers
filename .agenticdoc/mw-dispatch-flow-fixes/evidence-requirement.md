# Evidence Requirement: mw-dispatch-flow-fixes

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-dispatch-flow-fixes/spec.md` |
| spec_locked_at | 2026-09-07T20:43:55+08:00（AC-012/013 追加 @ 2026-09-08 设计审核轮） |
| ac_fingerprint | `9c90fbb3e171` |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013 |
| vc_ids | VC-001..VC-019 |
| generated_at | 2026-09-08T10:45:00+08:00；指纹重算 @ 2026-09-08 15:00 为 quality-gate 规范口径
| fingerprint_formula | `grep -oE 'AC-[0-9]{3}' spec.md \| sort -u \| sha1sum`（sorted-unique AC ID 行流；AC 集合演进：AC-001~011 锁定 + AC-012/013 追加 + AC-001/AC-008 措辞修订 + AC-014 追加（2026-09-08 评审后用户决策），当前编号集合 14 个） |

## AC-001: owner = 激活 key（task.md 落 {K}/workers/）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | L1 单测输出 | 双 active 行（旧前新后）→ owner=goal-autopilot | 单次 PASS |
| [VERIFY] VC-002 | L1 单测输出 | _index.parallel 无 active + _index.md active=K → owner=K | 单次 PASS |
| [VERIFY] VC-017 | L1 脚本级验证 | update_index.py claim 后 active 行唯一 | 单次 PASS |

## AC-002: watch 不一致同步 + 一次告警
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-003 | L1 单测输出 | warn_count=1（含两 key 名）；owner=Y 不变 | 单次 PASS |

## AC-003: 心跳 ≤60s 结构化条目
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-004 | L0 静态断言 | interval ≤60000；行格式 ^\[HEARTBEAT\] \S+ task=\S+ | 单次 PASS |
| [FLOW] 心跳流 | L2 实跑 trace.log | 相邻 [HEARTBEAT] 间隔 ≤60s（并入 VC-012） | 完整序列 |

## AC-004: 活性判定机制（阈值可配）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-006 | L1 pytest | verdicts={alive,stale,no-heartbeat}；--stale-after 覆盖 | 单次 PASS |
| [VERIFY] VC-007 | L1 单测 | /mw doctor 摘要含活性行，stale 任务名列出 | 单次 PASS |

## AC-005: 既有协议 additive
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-005 | L1 单测 | [FLOW]/[GOAL_CHECK] 格式不变；[HEARTBEAT] 独立 | 单次 PASS |
| [VERIFY] VC-008 | L1 回归 | 既有 vitest 全绿 | 全量 PASS |

## AC-006: 无凭证环境 review 默认 pi 完成
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-009 | L1 单测 | type: review 扫描派发 → cli=pi provider=timi | 单次 PASS |
| [FLOW] L2 | L2 实跑 | 无凭证环境 review 任务经 pi/timi 完成（并入 VC-012） | 完整链路 |

## AC-007: 显式 claude 保留；type 不触发
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-010 | L1 单测 | 显式 cli=claude → 队列行 claude；research 内容路由 pi/timi | 单次 PASS |

## AC-008: ga-spec-review-1 同规格回归
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-012 | L2 实跑证据 | owner=派发窗口认领 key（mw-dispatch-flow-fixes，REVISED @ 2026-09-08 用户决策 9）；hb 间隔≤60s；pi/timi 完成；零人工干预 | 单次全项 PASS |

## AC-009: 显式 claude 缺凭证隔离不降级
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-011 | L1 回归（mw-dispatch-reliability 既有用例） | claude_task=failed；worker.log 含凭证名；sibling=done | 既有用例 PASS |

## AC-010: gate 仅评有未入队任务的 key
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-013 | L1 单测 | 全入队 undoc key → gate_events=0 | 单次 PASS |
| [VERIFY] VC-014 | L1 单测（既有用例回归） | 有未入队 → gate_events=1 且不入队 | 单次 PASS |

## AC-011: 播报按窗口认领 key 过滤
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-015 | L1 单测 | K→1、J→0、无 watch→0 | 单次 PASS |
| [VERIFY] VC-016 | L1 单测 | 终态摘要仅 watch key 名下任务 | 单次 PASS |

## AC-012: widget 心跳进度 monitor
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-018 | L1 单测 | running 行含 ph+hb；>90s STALE；无 hb 占位 | 单次 PASS |
| [FLOW] L2 | L2 实跑 | widget 活进度可见（并入 VC-012 观察项） | 观察记录 |

## AC-013: 终态摘要附心跳统计
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-019 | L1 单测 | ≥2 hb → 统计附注；<2 hb → 现状格式 | 单次 PASS |
| [VERIFY] VC-020 | L1 单测输出 | 终态消息含 output.md 全文；>20k 截断+指路；无 output 走 fallback | 单次 PASS |

## 质检门禁使用说明
本文件由 /quality-gate 读取，对每个 AC/VC 逐条核查证据充分性。L2 证据（VC-012）留存于 `evidence/runs/`。
