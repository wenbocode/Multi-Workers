# Evidence Requirement: mw-dispatch-role-escape

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-dispatch-role-escape/spec.md` |
| spec_locked_at | 2026-09-20T20:30:00+08:00 |
| ac_fingerprint | `b944d7646135`（AC-001~AC-011；执行期新增 AC-007 的 BOM 分支见 AC-007 表内标注，AC 编号未变） |
| ac_ids | AC-001 ~ AC-011 |
| vc_ids | VC-001 ~ VC-013 |
| generated_at | 2026-09-20T20:55:00+08:00 |

## AC-001: pi 任务可声明 type，review/research role 可达
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | TS 单测 | type: review 写入 task.md；省略时 pi→coding / codex→codex | 单次 PASS |
| live smoke（print 模式，安装后的 bundle） | worker 产物 | task.md `type: review` + launcher.log `source=config:review` + worker trace `type=review` | 单次 PASS + 产物三处一致 |
| worker trace 工具集 | worker.log/trace.log | review 任务只出现 read/find/grep/ls（无 write/edit/bash） | 单次 PASS |

## AC-002: 非法 type 被拒绝且无半成品
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | TS 单测 | 消息含合法值列表；task 目录不存在；_workers.parallel 无行 | 单次 PASS |

## AC-003: `/worker --type` 与工具同语义
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-002 | TS 单测（命令 handler） | task.md `type: review`；notify 含 `[type: review, role: review`；非法值仅 notify 警告且不建目录 | 单次 PASS |

## AC-004: 偏离 role 默认值必须给理由
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-003 | TS 单测 | 缺 reason → 拒绝，消息含 `review=<默认值>`；无 task 目录 | 单次 PASS |
| [VERIFY] VC-013 | TS 单测（BOM 配置） | BOM 前缀 dispatch.yml 同样触发 reason 门 | 单次 PASS |
| live smoke 拒绝路径 | 工具返回文本 + 文件系统 | `needs model_reason: dispatch.yml review=timi/gpt-5.6-sol, requested=...`；`smoke2-no-reason/` 不存在 | 单次 PASS |

## AC-005: 与配置默认值相同则不 pin
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-004 | TS 单测 | task.md 不含 `model:`；回显含 “matches the configured default” | 单次 PASS |
| live smoke（无 model 参数） | 工具返回 + task.md | `model: dispatch.yml review=timi/gpt-5.6-sol`；task.md 仅 `type: review` | 单次 PASS |

## AC-006: 覆盖理由落盘为单行
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-003 | TS 单测 | `model-reason: <单行>`；多行 reason 折叠为单行 | 单次 PASS |
| live smoke 产物 | task.md | `model: timi/gpt-5.6-luna` + `model-reason: luna chosen for the longer diff` | 单次 PASS |

## AC-007: 模型 id 校验（pi 路由）
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-005 | TS 单测矩阵 | 非法 id/未知 prefix 拒绝；合法/裸 id/CLI 前缀/非 pi/registry 缺失/无该 provider 放行 | 全矩阵 PASS |
| [VERIFY] VC-006 | TS 单测 | 生效的 role 默认值非法（`timi/gpt-5.6.sol`）→ 拒绝；显式 model + reason 为逃生口 | 单次 PASS |
| [VERIFY] VC-008 | TS 单测 | `/mw model set` 非法前缀值不调用 runner | 单次 PASS |
| live smoke | 工具返回文本 | `Model 'timi/gpt-5.6.sol' not found for provider 'timi' ...`；无 task 目录 | 单次 PASS |
| BOM 分支（新增） | TS 单测 + Python 单测 | `readRoleModel` 剥 BOM；PyYAML 同文件同结果（双侧 parity） | 双侧 PASS |

## AC-008: 成功派工回显 type/role/模型层
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001/VC-003/VC-004 | TS 单测 | 结果文本含 `type: <t>, role: <r>` 与三种模型层文案 | 单次 PASS |
| live smoke（三次调用） | 工具返回文本 | `type: review, role: review, model: dispatch.yml review=...` / `model override: role default review=X -> Y (reason: ...)` | 单次 PASS |

## AC-009: launcher override 证据行
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-009 | Python 单测（`_model_override_note` + `_spawn` + capsys） | 偏离 → 打印 `model-override task=X config:<role>=Y`；相等/非 task/无配置 → 无行；spawn 仍用显式值 | 单次 PASS |
| live smoke launcher.log | 运行日志 | 真实 spawn 输出的两行（`source=task` + `model-override ...`） | 单次 PASS |

## AC-010: 零回归
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-010 | TS 单测 | 不传新参数时 task.md == `type: coding\n\nwork\n`（逐字节） | 单次 PASS |
| agent-team-loop.test.ts 全量 | 测试套件 | 168/168 通过 | 全绿 |
| multi-workers pytest 全量 | 测试套件 | 692 passed, 0 failed（9 deselected = e2e） | 全绿 |
| `npm run check` | 静态门禁 | biome 0 修复 + tsgo 0 错 + shrinkwrap/install-lock 一致 | 0/0/0 |

## AC-011: 文档同步
| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| diff 检查 | 三份文档 | coding-agent CHANGELOG Added/Changed、multi-workers CHANGELOG Added/Changed、README「派工类型与模型覆盖门禁」小节 | 存在且与实现一致 |

## 质检门禁使用说明
本文件由 /quality-gate 读取，对每个 AC/VC 逐条核查证据充分性。执行证据归档于 `evidence/runs/`。
