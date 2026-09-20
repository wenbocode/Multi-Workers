# Evidence Requirement: mw-provider-routing

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-provider-routing/spec.md` |
| spec_locked_at | 2026-09-16T16:30:00+08:00 |
| ac_fingerprint | `1f3b42bb09a9` |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008 |
| vc_ids | VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010 |
| generated_at | 2026-09-17T10:30:00+08:00（D-001 改选 C 后同步） |

## AC-001: 无 port 路由直连注入（env 无 localhost、含 PI_WORKER_TASK）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | pytest（hermetic pi_providers 配置） | zai env 注入 + localhost 缺席 + PI_WORKER_TASK 存在 | 单次 PASS |

## AC-002: 直连凭证缺失 → RuntimeError 含路由名与缺失描述

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-002 | pytest | 异常消息含 provider 名 + describe_missing 片段 | 单次 PASS |

## AC-003: zai worker env 不含其他 provider 凭证

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-003 | pytest | ANTHROPIC/DEEPSEEK/TIMI 凭证与 TIMI_BASE_URL 全部缺席 | 单次 PASS |

## AC-004: route_precheck 列出 zai-coding-cn 可用性

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-004 | pytest | route 条目存在 + available 随凭证翻转 | 双态各一次 PASS |

## AC-005: 真实端到端派发（glm-5.3 往返、退出码 0）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-005 | e2e_real（真实派发冒烟，预算 ≥1024） | --provider zai-coding-cn 启动 + 真实往返 + exit 0 | 单次 PASS |
| [VERIFY] VC-010 | 静态双侧 map 断言（pytest + vitest） | zai ↔ zai-coding-cn 互逆存在 | 单次 PASS |

## AC-006: 默认路由保持 timi

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-006 | pytest（window-model=timi/glm-5.3） | provider=timi + TIMI_API_KEY 存在 + ZAI env 缺席 | 单次 PASS |
| [VERIFY] VC-009 | pytest（_build_command） | zai 无 model → RuntimeError；timi 无 model → --model glm-5.3（回归守护） | 双分支各一次 PASS |

## AC-007: 全量 pytest 0 failed

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-007 | 全量 pytest 运行记录 | failed=0, deselected=8 | 单次 PASS |

## AC-008: pi_providers-only 凭证不 spawn proxy

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-008 | pytest（cmd_serve + fake Popen，仅无 port 路由有凭证） | spawn 列表不含 proxy_multi.py | 单次 PASS |

## 质检门禁使用说明

本文件由 /quality-gate 读取，对每个 AC/VC 逐条核查证据充分性。VC-005 为 e2e_real 标记（默认 deselect），质检时需显式 `-m e2e_real` 运行或以真实派发运行记录替代。
