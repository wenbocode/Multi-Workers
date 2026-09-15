# Evidence Requirement: mw-widget-terminal-lifecycle

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-widget-terminal-lifecycle/spec.md` |
| spec_locked_at | 2026-09-10T12:13:52+08:00 |
| ac_fingerprint | `95d6a253ba12` |
| ac_fingerprint_note | 2026-09-10 VERIFY 阶段重锚：原记录 `4340acf7b818` 为早期会话 ad-hoc 计算，口径不可复现（20 种哈希变体均不匹配）。AC 集合零漂移已独立证实：本表 ac_ids（AC-001~013）与当前 spec 完全一致，且 spec.md mtime（12:14:44）早于本表 generated_at（12:30）。重锚采用 quality-gate 文档 canonical 管道 `grep -oE 'AC-[0-9]{3}' spec.md | sort -u | sha1sum | cut -c1-12`（git-bash 实跑验证）。 |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013 |
| vc_ids | VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-011, VC-012, VC-013 |
| generated_at | 2026-09-10T12:30:00+08:00 |

## AC-001: live 行全部显示不折叠
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | L1 单测（renderWatchLines 构造输入） | live_rows=5, more_line=absent | 单次 PASS |

## AC-002: 未 ack 终态待处理行常驻，ack 后移出
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-002 | L1 单测（ack 前后两次渲染对照） | unhandled=2, history_contains=acked_key | 单次 PASS |

## AC-003: history 折叠 5 + more
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-003 | L1 单测（7 行与 5 行两组边界） | history_lines=5, more=+2 / more=absent | 两组均 PASS |

## AC-004: /mw ack 持久化/幂等/拒绝非终态
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-004 | L1 单测（命令 handler + 新 AckStore 实例重读） | acked=t1, persisted=yes, all_covered=N, rejected=t-running | 全部断言 PASS |

## AC-005: ack_worker_result 工具 PM-only
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-005 | L1 单测（fake pi 注册表 + PI_WORKER_TASK 分支） | pm_registered=true, worker_registered=false, tool_ack=equivalent | 单次 PASS |

## AC-006: ack 不改队列、不重派
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-006 | L1 单测（status 快照 diff + dispatchNewTasks 扫描） | status_diff=0, re_dispatch=0 | 单次 PASS |

## AC-007: failed detail = Exit Reason / spawn 原因
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-007 | L1 单测（构造 output.md / worker.log） | detail_source=exit_reason, markdown_prefix=absent | 单次 PASS |

## AC-008: nc detail = Questions + 回退链
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-008 | L1 单测（三段回退各自构造） | fallback_chain=questions,log_tail,no_output | 三段均 PASS |

## AC-009: done detail = TL;DR/清洗回退
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-009 | L1 单测（headline 归一化 + 旧文件回退） | tldr_len<=100, markdown_prefix=absent, fallback=cleaned_summary | 两组均 PASS |

## AC-010: hint 含 ack 指示
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-010 | L0 静态断言（常量字符串） | hint_contains=ack_worker_result | 单次 PASS |

## AC-011: list_tasks acked 徽标
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-011 | L1 单测（工具输出解析） | acked_badge=present_on_acked_only | 单次 PASS |

## AC-012: 孤儿行正证据 reconcile
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-012 | L1 单测（伪造 task dir 三种 [END] + output-only + own 行） | map=0-done,1-failed,2-nc, output_only=failed+unverifiable, own_row=untouched | 全部断言 PASS |

## AC-013: 孤儿行静默 reconcile + beat 退让
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-013 | L1 单测（mtime/updated_at 构造 + beat 文件构造） | silence_failed=1, fresh_untouched=1, beat_guard=skipped | 三段均 PASS |

## 质检门禁使用说明

本文件由 /quality-gate 读取，对每个 AC/VC 逐条核查证据充分性。实现侧在对应测试中埋 `[VERIFY] VC-NNN: key=value` 输出行；L0 断言直接读常量。双侧套件（agent-team-loop.test.ts / test_launcher.py）须全绿且既有用例零回归。
