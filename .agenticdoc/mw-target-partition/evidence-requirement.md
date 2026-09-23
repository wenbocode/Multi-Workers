# Evidence Requirement: mw-target-partition

> 2026-09-19 v2：随单文件方案需求转向重新生成（v1 清单作废）

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-target-partition/spec.md` |
| spec_locked_at | 2026-09-19T00:54:29+08:00（v2 修订同日） |
| ac_fingerprint | `7b09f3e5e571`（2026-09-19 AC-007 标记版本修订后） |
| ac_ids | AC-001~AC-013（REVISED）、AC-014/015（OBSOLETE）、AC-016（REVISED）、AC-017~AC-020、AC-022、AC-023（新增；021 未分配） |
| vc_ids | VC-001~VC-013、VC-016~VC-020、VC-022、VC-023 |
| generated_at | 2026-09-19T02:10:00+08:00 |

## AC-001: v2 partition 解析 13 字段 parity（VC-001）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | parity 夹具 case（target-config-cases 续号 v2 case，双跑） | mode=partition、13 项逐字段相等、相对路径锚定控制根 | 单次 PASS |

## AC-002: 缺字段/缺块（VC-002）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-002 | parity 夹具 error case | kind=invalid-config，消息含 "parent"/"partition"（字段名或块名） | 双侧各一次 PASS |

## AC-003: 结构层 7 类校验（VC-003）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-003 | parity 夹具 error case ×7（混格式/非法 active/顶层白名单/块白名单/块间错放/roots 键名/根关系） | kind=invalid-config，消息含对应要素 | 每变体双侧 PASS |

## AC-004: 占位符 mode 分派（VC-004）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-004 | parity 夹具 render/render_error | partition token 渲染归一；未知 token → missing-field 含 token 名与原命令；dual 渲染零变化 | 双侧 PASS |

## AC-005: env 覆盖与 source（VC-005）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-005 | 夹具 env case + Py 单测 | EP 子集覆盖、source=env/target-yml、空白串=未设置、枚举 3 值 | 双侧 PASS |

## AC-006: worker cwd 与写回（VC-006）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-006 | test_mw_partition.py（_worker_cwd + spawn 断言） | cwd=partition root；trace/output 在控制根 | 单次 PASS |

## AC-007: profile 注入幂等（VC-007）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-007 | agent-team-loop-profile-injection.test.ts | PROFILE_MARK v2 块（v2 标记仅 partition；dual 维持 v1 零变化；模式行+内容段），同配置重派字节不变 | 单次 PASS |

## AC-008: read_scope 锚定（VC-008）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-008 | dispatch 层单测 | 锚定 partition root + control 追加；无 parent 追加 | 单次 PASS |

## AC-009: doctor 探测与指纹缓存（VC-009）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-009 | test_mw_partition.py | checks=[parent_root,partition_root,root:*]，uproject/engine=0；指纹变化重探测 | 单次 PASS |

## AC-010: CLI set（迁移/校验/落盘）（VC-010）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-010 | test_mw_partition.py（正常/v1 迁移/拒绝三路） | exit 0 落盘（--partition 默认、--root 语法）；迁移 .bak+提示；拒绝路径文件不变 | 每路 PASS |

## AC-011: CLI 缺参/clear（VC-011）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-011 | test_mw_partition.py | 缺 --parent exit 1 不变无 .bak；clear 删块 single/删文件；块缺失 exit 0 | 单次 PASS |

## AC-012: /mw partition 透传（VC-012）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-012 | agent-team-loop.test.ts（fake runner）+ test_mw_partition.py（字节确定性） | 参数序列与 yml 字节与 CLI 一致；show/on/off/clear 转发一致 | 双侧 PASS |

## AC-013: 零回归（VC-013）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-013 | 全量测试 + npm run check + `git diff --exit-code` 既有测试文件 + reviewer 签署 target 路径 diff | 全绿零修改；v1 行为零变化；check 0/0/0 | 四类证据齐 PASS |

## AC-014 / AC-015: [OBSOLETE]
无需证据（废弃项，由 AC-017/AC-018 取代）

## AC-016: 升级基线（VC-016）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-016 | 基线用例（main 先行录制，独立文件不导入 partition 符号） | v1 dual 与 single 样例 legacy 投影/输出六类逐字节一致 | 单次 PASS |

## AC-017: 规则表全枚举（VC-017）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-017 | _decide_active_mode 参数化测试（TS/Py 同表全枚举 F×A×EP/ET） | 12 行全符合、双侧 kind/消息一致、行 5 不解析、行 8 零变化 | 表全行 PASS |

## AC-018: active 模式感知（VC-018）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-018 | test_mw_partition.py + 注入用例 | 守卫互斥 exit 1；模式行存在；partition-only 键条件出现；指纹随切换失效 | 四子项各 PASS |

## AC-019: profile 切换替换（VC-019）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-019 | agent-team-loop-profile-injection.test.ts | 切换后标记到 EOF 整体替换；同配置字节不变 | 单次 PASS |

## AC-020: 撕裂校验（VC-020）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-020 | test_mw_partition.py（launcher 撕裂场景） | 任务 failed、原因含 config torn 与两侧模式名、未 spawn | 单次 PASS |

## AC-022: set 写盘安全（VC-022）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-022 | test_mw_partition.py | 同参幂等；手维护段/注释保留；原子替换完整可解析；.bak 完整含 v1 字段 | 四子项各 PASS |

## AC-023: on/off 切换（VC-023）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-023 | test_mw_partition.py + agent-team-loop.test.ts | on 翻转/块缺失 exit 1；off 置 single 块保留；v1 报错提示；转发一致 | 各子项 PASS |

## 质检门禁使用说明
本文件由 /quality-gate 读取，对每个 AC/VC 逐条核查证据充分性。ac_fingerprint 变更（spec AC 表修改）须重新生成本清单。
