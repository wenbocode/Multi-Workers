# Evidence Requirement: agent-team-loop

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/agent-team-loop/spec.md` |
| spec_locked_at | 2026-08-11 |
| ac_fingerprint | AC-001~AC-036 (36 conditions) |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017, AC-018, AC-019, AC-020, AC-021, AC-022, AC-023, AC-024, AC-025, AC-026, AC-027, AC-028, AC-029, AC-030, AC-031, AC-032, AC-033, AC-034, AC-035, AC-036 |
| vc_ids | VC-001 ~ VC-047 |
| generated_at | 2026-08-11 |

---

## AC-001: launcher.py ≤5s 检测 pending

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | L0 静态检查 | DEFAULT_POLL_INTERVAL ≤ 5 | 单次 PASS |

## AC-002: cli=pi env vars（ANTHROPIC_BASE_URL + PI_WORKER_TASK）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-002 | L1 局部测试 | ANTHROPIC_BASE_URL=http://localhost:7001 | 单次 PASS |
| [VERIFY] VC-003 | L1 局部测试 | PI_WORKER_TASK=<绝对路径> | 单次 PASS |

## AC-003: cli=codex env vars（OPENAI_BASE_URL + OPENAI_API_KEY）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-004 | L1 局部测试 | OPENAI_BASE_URL=http://localhost:7002 | 单次 PASS |
| [VERIFY] VC-005 | L1 局部测试 | OPENAI_API_KEY 非空 | 单次 PASS |

## AC-004: cli=claude env vars（ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-006 | L1 局部测试 | ANTHROPIC_BASE_URL=http://localhost:7003 | 单次 PASS |
| [VERIFY] VC-007 | L1 局部测试 | ANTHROPIC_AUTH_TOKEN 非空 | 单次 PASS |

## AC-005: exit 0 → done ≤3s

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-008 | L1 局部测试 | status=done latency ≤ 3000ms | 单次 PASS |

## AC-006: exit code → status 映射

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-009 | L1 局部测试 | exit 1 → status=failed | 单次 PASS |
| [VERIFY] VC-010 | L1 局部测试 | exit 2 → status=needs-clarification | 单次 PASS |
| [VERIFY] VC-011 | L1 局部测试 | exit 99 → status=failed（兜底） | 单次 PASS |

## AC-007: max-workers 队列

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-012 | L1 局部测试 | queued=1 active=N（N=max） | 单次 PASS |

## AC-008: 不重复 spawn 同一 key

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-013 | L1 局部测试 | duplicate_spawn_prevented=true | 单次 PASS |

## AC-009: --dry-run 输出 + 无子进程

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-014 | L1 局部测试 | stdout 含 CLI 命令和 task.md 路径 | 单次 PASS |
| [VERIFY] VC-015 | L1 局部测试 | subprocess_count=0 | 单次 PASS |

## AC-010: tool allowlist 生效

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-016 | L1 局部测试 | pi.state.tools 仅含 allowlist 工具 | 单次 PASS |
| [VERIFY] VC-017 | L1 局部测试 | denied_tools_absent=true | 单次 PASS |

## AC-011: output.md 4 节 + size + exit 0

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-018 | L1 局部测试 | output_sections=4 | 单次 PASS |
| [VERIFY] VC-019 | L1 局部测试 | output_size > 50 bytes, exit=0 | 单次 PASS |

## AC-012: trace.log [FLOW] 记录

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-020 | L1 局部测试 | flow_entries ≥ 1 | 单次 PASS |

## AC-013: proxy 三端口 LISTENING

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-021 | L2 E2E 测试 | netstat 含 7001, 7002, 7003 LISTENING | 单次 PASS |

## AC-014: dispatch-table grep 计数

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-022 | L0 静态检查 | pi≥2, codex≥1, claude≥2 | 单次 PASS |

## AC-015: Windows 含空格路径

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-023 | L1 局部测试 | path_with_spaces=ok（子进程 exit 0） | 单次 PASS |

## AC-016: phases 非空 → progress/phase-N.md

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-024 | L1 局部测试 | progress/phase-1.md size > 20 bytes | 每 phase 一次 |

## AC-017: GOAL_CHECK trace.log 记录

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-025 | L1 局部测试 | [GOAL_CHECK] phase=<N> goal_mtime=<ts> | 每 phase 一次 |

## AC-018: goal.md mtime 感知

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-026 | L1 局部测试 | goal_mtime_match=true（误差 < 1s） | 单次 PASS |

## AC-019: 无 phases → 不创建 progress/

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-027 | L1 局部测试 | progress_dir_absent=true | 单次 PASS |

## AC-020: mw init 目录结构 + exit 0

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-028 | L1 局部测试 | .agenticdoc/_index.md 存在, exit=0 | 单次 PASS |

## AC-021: goal elicitation 产出 3 节

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-029 | L2 E2E 测试 | goal_sections=3 all_nonempty=true | 单次 PASS |

## AC-022: sync + 保留用户文件

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-030 | L1 局部测试 | update_index.py 存在 | 单次 PASS |
| [VERIFY] VC-031 | L1 局部测试 | user_file_preserved=true | 单次 PASS |

## AC-023: --project path 前缀正确

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-032 | L1 局部测试 | task.md 路径前缀为 <project-dir>\.agenticdoc\ | 单次 PASS |

## AC-024: provider → 正确 env var

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-033 | L1 局部测试 | DEEPSEEK_BASE_URL 存在，ANTHROPIC_BASE_URL 缺失 | 单次 PASS |

## AC-025: dry-run provider env 输出

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-034 | L1 局部测试 | dry_run 输出含 DEEPSEEK_BASE_URL，不含 ANTHROPIC_BASE_URL | 单次 PASS |

## AC-026: PM/Worker 互斥加载

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-035 | L1 局部测试 | mode=pm|worker exclusive=true | 单次 PASS |

## AC-027: _index.parallel 格式兼容

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-036 | L1 局部测试 | update_index.py list exit=0, key_found=true | 单次 PASS |

## AC-028: /pm-key TUI 命令

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-037 | L2 E2E 测试 | pi TUI 输出 _index.parallel 全表 | 单次 PASS |

## AC-029: 原子写并发安全

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-038 | L1 局部测试 | concurrent_write_clean=true（无半写行） | 单次 PASS |

## AC-030: done 后 TUI 展示 Summary

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-039 | L2 E2E 测试 | summary_displayed=true（非空） | 单次 PASS |

## AC-031: Phase 枚举校验拒绝非法值

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-040 | L0 静态检查 + L1 局部测试 | invalid_phase_rejected=true, pm-state.md 内容不变 | 单次 PASS |

## AC-032: _workers.parallel 7 列格式

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-041 | L1 局部测试 | 每行 7 列，Status 值域合法，与 _index.parallel 独立 | 单次 PASS |

## AC-033: worker exit code 语义（output.md 要求）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-042 | L1 局部测试 | exit 1 → output.md 含 Exit Reason 节（非空） | 单次 PASS |
| [VERIFY] VC-043 | L1 局部测试 | exit 2 → output.md 含 Questions 节（替代 Verification Steps） | 单次 PASS |
| [VERIFY] VC-044 | L1 局部测试 | exit 130 → output.md 存在（可部分填充） | 单次 PASS |

## AC-034: mw serve PID 文件 + 防重复实例

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-045 | L1 局部测试 | PID 文件存在，第二实例 exit 1，进程退出后 PID 清理 | 单次 PASS |

## AC-035: mw serve 独立于 pi 进程

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-046 | L1 局部测试 | kill pi 后 mw serve PID 仍存活，worker 继续运行到完成 | 单次 PASS |

## AC-036: mw init 安装 Extension bundle

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-028 | L1 局部测试 | .pi/extensions/agent-team-loop.js 存在（已在 AC-020 共用） | 单次 PASS |
| [VERIFY] VC-047 | L1 局部测试 | bundle 缺失时 exit 1，不创建不完整目录 | 单次 PASS |

---

## 质检门禁使用说明

本文件由 `/quality-gate` 读取，对每个 AC/VC 逐条核查证据充分性。
- L0 证据：代码/文件静态检查，不需要运行时
- L1 证据：局部单元/集成测试，不需要完整 E2E 环境
- L2 证据：端到端测试，需要 proxy + pi + launcher 全部启动
