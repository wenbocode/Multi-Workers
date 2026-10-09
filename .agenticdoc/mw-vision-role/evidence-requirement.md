# Evidence Requirement: mw-vision-role

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-vision-role/spec.md` |
| spec_locked_at | 2026-09-26T17:00:00Z |
| ac_fingerprint | `918de4e2b149`（workflow-quality-gate.md 的 id-set 算法：`grep -oE 'AC-[0-9]{3}' spec.md \| sort -u \| sha1 \| cut -c1-12`；2026-09-26 QG 阶段校正） |
| ac_fingerprint_section (旧口径) | `6857a77db10f` → 现为 `0cdc159d3d10`。旧口径 = spec §3 区块文本归一化后 sha1，**对文本编辑敏感**：AC-010 追加 `[REVISED @ 2026-09-26]` 注后该值即漂移，而 AC **集合**未变（19 个 id，含 OBSOLETE 的 AC-018）。故 QG 门禁用 id-set 口径为准，此处保留旧值仅供追溯。 |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017, AC-018(OBSOLETE), AC-019 |
| vc_ids | VC-001 … VC-019（VC-018 不适用） |
| generated_at | 2026-09-26T17:11:01Z |
| design_path | `.agenticdoc/mw-vision-role/design.md` |
| ac_revisions | AC-010 `[REVISED @ 2026-09-26]` issue→suggestion；spec §4 auto-route 边界注 `[REVISED @ 2026-09-26]` 只换模型 |

## 测试入口（本 key 触达面）

```bash
# Python（根 = packages/multi-workers/，不是 test/）
cd packages/multi-workers; python -m pytest test_dispatch_models.py test_autopilot_l0.py test_autopilot_dispatch.py test_mwpp_collection_parity.py test_serve_doctor.py test_rag_phase.py test_autopilot_readcap_injection.py -q -s

# TypeScript（包根）
cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-image-cap.test.ts

# 静态检查（无 --write，避免 P-017 全仓写）
npx biome check --error-on-warnings packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test
npx tsgo --noEmit
```

## AC-001: set vision 成功写入（正常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | 单测输出 | `vision=timi/deepseek-v4-flash-vision-exp rc=0` | 单次 PASS |
| `load_dispatch_config()` 回读 | 单测断言 | `models["vision"] == "timi/deepseek-v4-flash-vision-exp"` | 单次 PASS |

## AC-002: 未知角色拒绝（异常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-002 | CLI 子进程输出 | `rc=nonzero roles=5` | 单次 PASS |
| stderr 原文 | CLI 输出 | 恰好枚举 `main, coding, review, research, vision` | 单次 PASS |

## AC-003: 解析链命中 `config:vision`（正常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-003 | 单测输出 | `source=config:vision task_override=task` | 单次 PASS |

## AC-004: 类型/角色映射两侧一致（正常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-004 | 双端单测输出 | `role_for_vision=vision mirror_ok=true` | 单次 PASS |
| TS 半边断言 | 单测 | `roleForTaskType("vision") === "vision"`（现无 parity 测试，必须新增） | 单次 PASS |

## AC-005: 白名单两侧逐元素相等（正常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-005 | L0 单测输出 | `allowlist_vision=read,write,edit,bash,find,grep,ls parity=true` | 单次 PASS |
| 重冻语料 diff | 人工 review | `test_mwpp_collection_parity.py` 键集更新有据（仅新增键，不放宽断言） | 人工判定 |

## AC-006: 门禁拒绝且零副作用（异常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-006 | 单测输出 | `refused=true queue_delta=0 dir_exists=false` | 单次 PASS |
| 拒绝消息原文 | 单测断言 | 同时含 `images` / `mw model set vision` / `images: no` | 单次 PASS |

## AC-007: 放行 + `images: yes` + 头部顺序（正常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-007 | 单测输出 | `queue_delta=1 images_line=yes order_ok=true` | 单次 PASS |

## AC-008: 不可判定 → fail-open（边界）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-008 | 单测输出 | `failopen_ok=true queue_delta=1` | 三次（registry undefined / `cli!=pi` / CLI 前缀） |

## AC-009: 未声明时逐字节零变化（边界）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-009 | 单测输出 | `zero_byte=true frozen_copy=true` | 单次 PASS |
| 4 处既有 golden | 单测 | 不重冻且保持绿（`test_rag_phase.py` / `test_autopilot_dispatch.py` / `test_autopilot_conductor_exec.py` / readcap VC-007/008） | 全套 PASS |

## AC-010: doctor 三态（正常 + 异常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-010 | in-process 单测输出 | `doctor_rc=0 states=suggestion,ok,skip` | 单次 PASS（三支各一次） |
| 子进程 CLI | CLI 输出 | 仅覆盖 skip 支（`which→None`），rc=0 | 单次 PASS |

## AC-011: worker 兜底 `[IMAGE-CAP]`（异常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-011 | L1 行为单测输出 | `image_cap_line=true exit=1 control_ok=true` | 单次 PASS |
| worker.log 原文 | 真进程（人工 1 次） | 含 `[IMAGE-CAP]` 与模型 id，且退出码非零 | 人工判定（无真进程基建） |

## AC-012: 测试与 check 全绿（流程）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-012 | 命令原始输出 | `scoped_tests=green check=green` | 完整输出留存 |
| 基线对比 | 命令输出 | 全量时 `failed <= 76` 且无 `agent-team-loop*`/`worker-mode*`/`dispatch-models*` 失败 | 人工对比 |

## AC-013: 配置期拒绝 + `--force`（正常 + 异常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-013 | 单测输出 | `no_rc=1 yml_unchanged=true force_rc=0` | 单次 PASS（含 unknown/force/非 vision force 四支） |
| dispatch.yml 字节比对 | 单测断言 | 拒绝路径前后 `read_bytes()` 相等 | 单次 PASS |

## AC-014: PM 知情面四处文本（正常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-014 | L0 单测输出 | `surfaces=4 token_set_ok=true` | 单次 PASS |

## AC-015: 能力可见（show/doctor 列）（正常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-015 | 单测输出 | `show_images=yes/no/unknown rc=0` | 单次 PASS |
| TS 渲染 | 单测 | doctor 派发行含 `images=`；`agent-team-loop.test.ts:5029-5031` 语料按 D-011 重冻 | 单次 PASS |

## AC-016: auto-route 只换模型（正常 + 边界）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-016 | 单测输出 | `auto_route=true type_unchanged=true explicit_model_untouched=true` | 单次 PASS |
| task.md 原文 | 单测断言 | `model:` == vision 值；`model-reason:` 含 `auto-route`；`type:` 保持原类型 | 单次 PASS |

## AC-017: auto-route 按能力参数化（正常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-017 | 单测输出 | `types=vision,review type_unchanged=true effective_vision=2 auto_route_fired=1`（[REVISED @ 2026-09-26] 原 `routed=2` 逻辑不可满足，见 `design.md` §7 VC-017 注） | 参数化两例 |

## AC-018: （OBSOLETE）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-018 | — | `n/a obsolete=true` | 不适用 |

## AC-019: conductor 允许派发（正常 + 异常）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-019 | 单测输出 | `conductor_dispatchable=true unknown_type_refused=true` | 单次 PASS |
| REGISTRY 键集重冻 diff | 人工 review | 仅新增 `vision` 键，不放宽断言 | 人工判定 |

## 已知基线噪声（不得归因本 key）

- `test_autopilot_readcap_injection.py:885 test_baseline_left_end_bound`：本机现状即红（冻结副本 sha256 ≠ git HEAD），与 `images:` 无关。
- Windows 环境基线 89 例（`packages/agent` 13 + `packages/coding-agent` 76），权威分类见 `AGENTS.md` 与 `.agenticdoc/mw-worker-tree-kill/evidence/baseline/known-windows-env-baseline-2026-09-19.md`。

## 质检门禁使用说明

本文件由 `/quality-gate` 读取，对每个 AC/VC 逐条核查证据充分性。判定顺序：先跑"测试入口"段命令取原始输出 → 按本表逐 AC 比对 `[VERIFY]` 行 → 标注"单次PASS/全套PASS/人工判定"的项必须有对应原始输出或人工记录，禁止以退出码代替输出内容（P-006/P-016）。
