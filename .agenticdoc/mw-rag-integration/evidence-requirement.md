# Evidence Requirement: mw-rag-integration

- generated_at: 2026-09-22
- ac_fingerprint: ce271f032d25
- ac_ids: AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017, AC-018
- 充分性判定通则：VC 的 `Layer` 决定所需证据等级 —— L0 = 静态结构断言（注册表/文件形态/字节相等）；
  L1 = 单元或进程内集成测试的 `[VERIFY]` 行（fixture 服务，不依赖真实网络）；L2 = 真实时序/长调用/看门狗
  观察（`MW_RAG_SLOW=1` 的 180s 慢调用、撕裂拒 spawn 的真实 spawn 路径）。多等级（如 L0+L1、L1+L2）需齐备。
- 采集点：`evidence/verify-run-2026-09-22.md`（命令 1~9 的原始输出汇总）。

| AC | 关联 VC | 充分性判定标准 |
|---|---|---|
| AC-001 | VC-001 | VC-001 需 L1 证据 |
| AC-002 | VC-002, VC-024, VC-027 | VC-002 需 L1 证据；VC-024 需 L0+L1 证据；VC-027 需 L0+L1 证据 |
| AC-003 | VC-003, VC-022 | VC-003 需 L1 证据；VC-022 需 L2 证据 |
| AC-004 | VC-004, VC-005 | VC-004 需 L1 证据；VC-005 需 L1 证据 |
| AC-005 | VC-006, VC-007, VC-026 | VC-006 需 L1 证据；VC-007 需 L1 证据；VC-026 需 L0 证据 |
| AC-006 | VC-008 | VC-008 需 L1 证据 |
| AC-007 | VC-009, VC-010 | VC-009 需 L1 证据；VC-010 需 L1 证据 |
| AC-008 | VC-011, VC-012 | VC-011 需 L1 证据；VC-012 需 L1 证据 |
| AC-009 | VC-013 | VC-013 需 L2 证据 |
| AC-010 | VC-014 | VC-014 需 L2 证据 |
| AC-011 | VC-015 | VC-015 需 L0+L1 证据 |
| AC-012 | VC-016 | VC-016 需 L1 证据 |
| AC-013 | VC-017, VC-025 | VC-017 需 L1+L2 证据；VC-025 需 L1 证据 |
| AC-014 | VC-018 | VC-018 需 L2 证据 —— **REVISED @ 2026-09-22 → L1**：独立复核（`mw-rag-integration-fix` T-18，`[REVISED @ 2026-09-22 → L1, superseded by mw-rag-integration-fix T-18]`）裁定实际证据是假 pi + 合成 `agent_settled` 的进程内集成测试（L1），L2 的「真实时序/长调用」证据需真实 RAG 服务，未做 → 记入 fix key 的「遗留」 |
| AC-015 | VC-019, VC-020 | VC-019 需 L1 证据；VC-020 需 L1 证据 |
| AC-016 | VC-021 | VC-021 需 L1 证据 |
| AC-017 | VC-023 | VC-023 需 L1 证据 |
| AC-018 | VC-028 | VC-028 需 L1 证据 |
