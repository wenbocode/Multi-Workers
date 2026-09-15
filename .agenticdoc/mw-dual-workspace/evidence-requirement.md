# Evidence Requirement: mw-dual-workspace

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-dual-workspace/spec.md` |
| spec_locked_at | 2026-09-11T15:01:58+08:00（AC-007 于 2026-09-11 修订：profile 载体改 target.yml 配置节） |
| ac_fingerprint | `e9719d9067b2` |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009 |
| vc_ids | VC-001..VC-016 |
| generated_at | 2026-09-11T16:20:00+08:00 |

## AC-001: 单目录缺省零回归
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | 单测输出 | mode=single roots-equal=true | 单次 PASS |
| [VERIFY] VC-002 | check/test 运行输出 | check-clean=true new-failures=0（对照 89 例基线） | 单次 PASS |

## AC-002: 目标树零污染（跨盘）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-003 | L2 集成测试输出（MW_TEST_CROSS_DRIVE_ROOTS 门控） | target-tree-hits=0 control-files=complete；env 缺失时 skip 原因可见 | 单次 PASS（跨盘 fixture） |

## AC-003: worker cwd=game + 协调文件落控制根
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-004 | 单测断言 | spawn-cwd=game 绝对路径 | 单次 PASS |
| [VERIFY] VC-005 | 单测断言 | write-prefix=control-root | 单次 PASS |

## AC-004: Game+Engine 双目录渲染 + fail-closed
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-006 | 单测输出 | rendered-contains-engine=true unresolved-placeholders=0 | 单次 PASS |
| [VERIFY] VC-007 | 单测输出 | exit-nonzero=true fallback=false | 单次 PASS |
| [VERIFY] VC-008 | 单测输出 | uproject-resolved=true ambiguous-fail=true | 单次 PASS |
| [VERIFY] VC-009 | 单测输出 | game-allow=true engine-allow=true outside-block=true | 单次 PASS |

## AC-005: 配置/指令切换模式
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-010 | 单测输出 | dual-root=game single-root=control rebuild=false | 单次 PASS |

## AC-006: deny globs 防火墙
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-011 | 单测输出 | deny-block-rate=100 trace-has-reason=true（*.uasset 与 DerivedDataCache/** 两形态） | 单次 PASS |
| [VERIFY] VC-012 | 单测输出 | precedence=deny | 单次 PASS |

## AC-007: target.yml 三节注入
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-013 | 单测输出 | toolchain-mark=true ignore-mark=true contract-mark=true | 单次 PASS |

## AC-008: goal mtime 双根不变
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-014 | 既有用例双根 fixture 运行输出 | goal-check-pass=true trace-has-goalcheck=true | 单次 PASS |

## AC-009: serve 根绑定控制工作区
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-015 | 单测输出 | serve-meta-prefix=control-mw | 单次 PASS |
| [VERIFY] VC-016 | 既有 staleness 用例双根 fixture 输出 | staleness-detect=true | 单次 PASS |

## 质检门禁使用说明

本文件由 /quality-gate 读取，对每个 AC/VC 逐条核查证据充分性。VC-003 为跨盘门控用例：质检时若 `MW_TEST_CROSS_DRIVE_ROOTS` 未设置，该条按 skip 记录（不判 FAIL），其余 VC 均须可复现。
