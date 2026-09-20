# Evidence Requirement: mw-partition-parent-extended

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-partition-parent-extended/spec.md` |
| spec_locked_at | 2026-09-20T15:05:00+08:00 |
| ac_fingerprint | `6a9e7040d5d2`（sorted AC-ids sha1 前 12 位，质检门禁公式；初版 b28ae1d8b531 为 spec 全文 sha1，同日公式对齐重算，AC 零变更） |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006 |
| vc_ids | VC-001 ~ VC-009 |
| generated_at | 2026-09-20T15:40:00+08:00 |

## AC-001: Py 展开并入 parent（VC-001）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-001 | `test_partition_dispatch.py` 展开断言（翻转后）+ 新增判重 case | expanded=[条目, control, parent] 逐项相等；已列根不重复；dual/single 同输入零变化 | 全部 PASS |

## AC-002: worker union（VC-002/003/004）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-002 | `autopilot-read-scope.test.ts` 纯函数矩阵（新 describe） | parentRootFromTaskContent：新旧标签→P；无模式行/无行→null | 全部 PASS |
| [VERIFY] VC-003 | 同上 | applyParentRootUnion：非空 scope 追加；undefined/null/空 scope 原样返回 | 全部 PASS |
| [VERIFY] VC-004 | 同文件 wiring 用例（startScopedWorker 变体带 profile body） | parent 路径 read 不 block；scope 外路径 block（rule=scope） | 单次 PASS |

## AC-003: deny 先于 union（VC-005）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-005 | wiring/纯函数用例（deny glob + union 并存） | parent 下 deny 匹配路径 block，reason 含 rule=deny-glob | 单次 PASS |

## AC-004: 写路径零拦截回归锁定（VC-006）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-006 | wiring 用例 + 既有 non-read 用例 | parent 路径 write/edit/bash 不 block、无 rejection；gate 工具集={read,ls,find,grep} | 全部 PASS |

## AC-005: 措辞/标签/golden 同步（VC-007/008）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-007 | 双侧 golden parity 用例（标签更新后） | 两实现 Parent root 行= `Parent root (extended workspace, writable):`，输出逐字节一致；golden/断言同步 | 双侧 PASS |
| [VERIFY] VC-008 | CLI 文案断言（`test_mw_partition.py` 或 grep 审计） | mw.py 两处不含 "read-only"、含 "extended writable workspace" | 单次 PASS |

## AC-006: 零回归与修改面限定（VC-009）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| [VERIFY] VC-009 | 全量两侧测试 + diff 审计 + `npm run check` | dual/single 既有用例零修改全绿；partition 用例修改限于 AC-001/005 触点；check 0/0/0 | 全部 PASS |

## 质检门禁使用说明
本文件由 /quality-gate 读取，对每个 AC/VC 逐条核查证据充分性。
