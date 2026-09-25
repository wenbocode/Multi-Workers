# Evidence Requirement: mw-done-closure-repair

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-done-closure-repair/spec.md` |
| spec_locked_at | 2026-09-25T11:16:40+08:00（AC-002 二次/AC-003/AC-004/AC-005 [REVISED @ 2026-09-25，依 dcr-review-spec-design]） |
| ac_fingerprint | `b944d7646135`（门禁口径：sorted-unique AC ID 集 sha1 前 12 位） |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011 |
| vc_ids | VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-011, VC-012, VC-013 |
| generated_at | 2026-09-25T14:05:00+08:00 |

## AC-001: 标准词表零人工达 done
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | L2 tick 驱动测试（标准模板 fixture + stderr 忠实 advance fake） | phase=DONE, stalled_gates=0, gate_answered=0 | 单次 PASS |
| [VERIFY] VC-010 | L2 第二套词表 fixture | 同上（「行为影响」「未了事项」） | 单次 PASS |
| [FLOW] 失败→marker→reprompt→覆盖→exit=0 完整事件序列 | L2 timeline 断言 | l3-reprompt + dispatch + advance exit=0 序列 | 完整序列 |

## AC-002: 失败原文进 prompt + 零硬编码
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-002 | L2 读 ap-{key}-l3-a{N+1}/task.md prompt 正文 | 逐字含失败行；全文逐字节 = reprompt 固定基底（_l3_prompt + REPROMPT_INSTRUCTION 常量）+ 失败行列表 | 单次 PASS |
| [VERIFY] VC-003 | L0 静态扫描 | rg「系统行为变化\|行为影响\|未了事项」于 autopilot/ = 0 命中 | 单次 PASS |

## AC-003: 三条件覆盖授权
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-004 | L1 真值表单元（closure.overwrite_authorized 4 否定例） | 各否定条件下 False 且文件字节不变 | 4/4 PASS |
| [VERIFY] VC-005 | L1 全真例 | tmp+os.replace 覆盖 + 同锁删 marker | 单次 PASS |

## AC-004: 人工修稿保护
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-006 | L2 失败后外部改稿场景 | 此后字节不变（含 reprompt 在飞期间）+ reprompt 轮收敛后 advance exit=0 | 单次 PASS |

## AC-005: 预算封顶 + verdict 保真
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-007 | L2 round_budget=1 耗尽场景 | stalled=True, l3 dispatch ≤ l3_limit（含首轮）, verdict=meets | 单次 PASS |

## AC-006: 非结案类分流
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-008 | L2 非 achieved.md 失败场景（如 pm-state/QG 行） | l3 dispatch 增量=0 + streak stall 四件套 | 单次 PASS |

## AC-007: in-flight 零 advance
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-009 | L2 在飞场景事件计数 | advance 事件增量 = 0 | 单次 PASS |

## AC-008: 词表可移植
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-010 | L2 合成词表 fixture | 0 stalled, 0 gate-answered, phase=DONE | 单次 PASS |

## AC-009: 幂等 + 不洪泛
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-011 | L2 30 tick 混合场景 | gate-answered ≤1/gate id + gates 增量 ≤ key 数 | 单次 PASS |

## AC-010: 逐字转写
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-012 | L2 字节比对 | achieved.md == l3-a{N}/output.md ## Achieved 节（尾部换行 ≤1） | 单次 PASS |

## AC-011: marker 生命周期
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-013 | L1/L2 覆盖后与 advance 成功后 | marker 不存在；重复失败单文件 | 单次 PASS |

## 附：e2e_l2 全链回归（D-007）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] e2e_l2 test_full_chain_single_key | L2-e2e（真实框架拷贝） | 修复前证伪（词表缺口复现，plan 阶段先跑一次）；修复后 stub 合规词表或经 reprompt 修正后全链绿 | 修复前红/修复后绿 |

## 质检门禁使用说明
本文件由 /quality-gate 读取，对每个 AC/VC 逐条核查证据充分性。
