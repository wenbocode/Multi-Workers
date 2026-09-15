# Evidence Requirement: autopilot-monitor

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/autopilot-monitor/spec.md` |
| spec_locked_at | 2026-09-11T17:30:00+08:00 |
| ac_fingerprint | `77e45dafd9cb` |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009 |
| vc_ids | VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-011 |
| generated_at | 2026-09-11T18:05:00+08:00 |

指纹算法：sha1("AC-001=描述;AC-002=…;…") 前 12 位（spec §3 表格行拼接）。

## AC-001: 开启 ≤1 轮询周期出面板，serve 行含 PID + fresh/stale
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | L1 单测输出 | serve_line_contains=<pid,fresh\|stale>, first_frame_ticks=0 | 单次 PASS |
| [VERIFY] VC-010 | L2 实机/RPC 输出 | distinct_widget_ids=2 | 单次 PASS |

## AC-002: conductor 死亡 ≤2 周期变 dead
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-002 | L1 单测输出 | conductor_line_contains=dead, ticks<=2 | 单次 PASS |

## AC-003: running workers 行 + 分钟数
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-003 | L1 单测输出 | worker_rows=2, elapsed_min=2, nonrunning_shown=0 | 单次 PASS |

## AC-004: pending gates 行 + 归零
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-004 | L1 单测输出 | pending_shown=1, after_approve_pending=0 | 单次 PASS |

## AC-005: off 清面板不重建
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-005 | L1 单测输出 | cleared=true, post_off_ticks=0 | 单次 PASS |

## AC-006: print 模式降级
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-006 | L1 单测输出 | notice_contains=no visual UI, started=false, thrown=0 | 单次 PASS |

## AC-007: serve down 显示指引
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-007 | L1 单测输出 | serve_line_contains=not running\|/mw restart, other_lines_present=true | 单次 PASS |

## AC-008: 纯只读无副作用
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-008 | L1 单测输出 | content_hash_changed=0, ticks=3 | 单次 PASS |
| [VERIFY] VC-009 | L0 静态扫描输出 | write_api_calls=0, persist_writes=0 | 单次 PASS |

## AC-009: 单窗口内存态
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-009 | L0 静态扫描输出 | write_api_calls=0, persist_writes=0 | 单次 PASS |
| [VERIFY] VC-010 | L2 实机/RPC 输出 | distinct_widget_ids=2 | 单次 PASS |
| [VERIFY] VC-011 | L0+L1 输出 | cross_window_leak=0 | 单次 PASS |

## 质检门禁使用说明

本文件由 /quality-gate 读取，对每个 AC/VC 逐条核查证据充分性。L0 = 静态扫描（rg 无写 API 调用 + 双 fake pi 实例隔离单测）；L1 = vitest（agent-team-loop.test.ts 新 describe 或独立 monitor.test.ts，fake timers 驱动 tick）；L2 = 实机（repo 自身 serve + JCodingAss conductor 会话，RPC 或 TUI 窗口双 widget 并存验证）。
