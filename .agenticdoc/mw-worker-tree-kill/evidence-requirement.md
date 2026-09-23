# Evidence Requirement: mw-worker-tree-kill

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-worker-tree-kill/spec.md` |
| spec_locked_at | 2026-09-19T17:11:39+08:00 |
| ac_fingerprint | `264ea1756fc7`（2026-09-19 执行期修订后重算；初版 27c05268f828，AC-001~004 量化/语义 REVISED 见 spec §3 标注） |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006 |
| vc_ids | VC-001, VC-002, VC-003, VC-004, VC-005, VC-006 |
| generated_at | 2026-09-19T17:20:00+08:00 |

## AC-001: idle watchdog 退出前杀全部 tracked 树（杀树先于 exit、写盘先于杀树）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | 单测断言输出 | tree_kill_before_exit=true, killed_pids=N（mock killProcessTree 按 tracked pid 逐个命中，invocationCallOrder 全部小于 exit 调用） | 单次 PASS |
| trace.log/output.md 内容 | 单测文件断言 | [TIMEOUT]/[END] 与 output.md 先于杀树已写入 | 完整序列 |

## AC-002: wall budget 退出路径行为与 AC-001 一致
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-002 | 单测断言输出 | tree_kill_before_exit=true, killed_pids=N（timeout: 2 头触发 wall 分支） | 单次 PASS |

## AC-003: settled-catch 退出前杀全部 tracked 树
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-003 | 单测断言输出 | tree_kill_before_exit=true, killed_pids=N（注入 agent_settled 处理异常） | 单次 PASS |

## AC-004: 'exit' 安全网兜底（硬崩溃路径）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-004 | 单测断言输出 | hook_tree_kill_called=true, killed_pids=N（直接调用注册的 exit listener） | 单次 PASS |

## AC-005: 成功路径零回归
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-005 | 单测断言输出 | success_zero_kill=true, exit_code=0（killProcessTree 零调用、process.exit 零调用、[END] exit=0） | 单次 PASS |
| 既有 watchdog 用例回归 | 测试套件 | agent-team-loop.test.ts 原有用例全绿 | 全绿 |

## AC-006: 真实进程树在 worker 退出后消亡
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-006 | live 测试断言输出 | orphan_count=0, within=60s（真实孙进程树 + 真实 taskkill/kill，探活轮询） | 单次 PASS |
| mw 全链派发 smoke（可选加验） | live smoke | 经 dispatch 的真实 worker wall-timeout 后无孤儿进程 | 分层降级标注 |

## 质检门禁使用说明
本文件由 /quality-gate 读取，对每个 AC/VC 逐条核查证据充分性。执行证据归档于 `evidence/runs/`，diff 归档于 `evidence/diff/`。
