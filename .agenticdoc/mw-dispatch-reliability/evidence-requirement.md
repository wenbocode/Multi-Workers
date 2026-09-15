# Evidence Requirement: mw-dispatch-reliability

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-dispatch-reliability/spec.md` |
| spec_locked_at | 2026-08-28T16:30:00+08:00 |
| ac_fingerprint | `102172138524` |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017 |
| vc_ids | VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-011, VC-012, VC-013, VC-014, VC-015, VC-016, VC-017, VC-018 |
| generated_at | 2026-08-28T17:05:00+08:00 |

## AC-001: 缺凭证任务隔离 failed，服务存活
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | L1 集成测试输出 | claude_task.status=failed | 单次 PASS |
| [VERIFY] VC-002 | L1 集成测试输出 | worker_log.contains=ANTHROPIC_AUTH_TOKEN; sibling.status=done | 单次 PASS |

## AC-002: 全路由缺凭证 fail fast 退出
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-003 | L1 单元/集成输出 | serve_exit!=0; mw_log.contains=missing（含每路由清单） | 单次 PASS |

## AC-003: 部分可用时预检逐路由记录
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-004 | L1 输出 | mw_log.route_lines==len(providers) | 单次 PASS |

## AC-004: stale 条目 ≤10s 归档
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-005 | L1 集成测试输出 | archived_lines=1; queue_lines_stale=0（≤10s） | 单次 PASS |

## AC-005: 启动即死不播报假成功
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-006 | L1 vitest 输出 | waitForMwStart=false（PID 出现后 3s 内死亡场景） | 单次 PASS |

## AC-006: doctor CLI ≥7 节 <5s 退出码语义
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-007 | L1 输出 | sections>=7; exit_code∈{0,1}; duration_s<5 | 单次 PASS |

## AC-007: /mw doctor 同源播报
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-008 | L0 代码检查/单测 | ui_bridge.calls=mw.py_doctor_json | 单次 PASS |

## AC-008: doctor --fix 自动修复清单
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-009 | L1 输出 | fixed=[stale_archive, pid_clear]; suggested=[bundle, proxy] | 单次 PASS |

## AC-009: 测试密封全绿零真实调用
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-010 | L1 pytest 输出 | pytest_pass=all; real_calls=0（真实 config.toml 存在的机器） | 单次 PASS |

## AC-010: 假 CLI exit 0/1 状态机
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-011 | L1 集成测试输出 | t1=done; t2=failed; worker_logs=2 | 单次 PASS |

## AC-011: max_workers=1 串行
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-012 | L1 集成测试输出 | t2_running_at > t1_terminal_at | 单次 PASS |

## AC-012: 8 并发写不丢行
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-013 | L1 集成测试输出 | lines_written==lines_read | 单次 PASS |

## AC-013: L2 真实任务全链 done
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-014 | L2 E2E 输出 | status=done; output_md.contains=## Summary; size>50（≤120s） | 单次 PASS（需真实 timi 凭证） |

## AC-014: smoke T5 去假阳性
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-015 | L0 静态断言 | false_positive_branch=absent | 单次 PASS |

## AC-015: vitest 收编游离脚本
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-016 | L1 test.sh 输出 | vitest=pass; loose_script=deleted | 单次 PASS |

## AC-016: file 凭证源可用
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-017 | L1 单元输出 | resolved_from=file; precheck.available=true | 单次 PASS |

## AC-017: 配置扩展零代码改动
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-018 | L1 集成测试输出 | new_route.in_precheck=true; code_diff=0 | 单次 PASS |

## 质检门禁使用说明

本文件由 /quality-gate 读取，对每个 AC/VC 逐条核查证据充分性。
L2（VC-014）依赖真实 timi 凭证与上游可用性；上游故障时标注"环境不可用"而非判 FAIL，待重跑。
