# 研究声明（spec 相位，零既有证据起步）

- key: mw-decision-substitution · 相位: SPEC · 日期: 2026-10-16

## 声明

本 key 是新立项（`deps: mw-jev-provider-integration`，DONE），spec 相位**没有**可继承的同 key 调研证据；本文件用于满足门禁的"至少一份 research note"要求，并登记调研在飞状态与预期落点。

## 在飞调研（并行，互不重叠，各自唯一证据文件）

| RQ | 问题 | 唯一证据文件 | 落点 |
| --- | --- | --- | --- |
| RQ-1 | 全仓"会停下来等人"的位置普查与分级 | `spec-decision-inventory-20261016.md` | `spec.md` §4 决策点表定稿 |
| RQ-2 | pi 扩展能介入哪些交互面（能否替代提问/确认） | `spec-pi-interaction-surface-20261016.md` | `spec.md` §5 binding 执行位置 |
| RQ-3 | 授权状态机 + 决策档案 schema + review 判据 | `spec-authority-audit-model-20261016.md` | `spec.md` §6/§7 |
| RQ-4 | 决策输入的结构化契约与脱敏分层 | `spec-structured-input-contract-20261016.md` | `spec.md` §5 input schema |
| RQ-5 | 人工轮次/阻塞墙钟/各类比率的可测性与算法 | `spec-decision-metrics-20261016.md` | `spec.md` §7 与 AC-010 |

## 已存在的可复用证据（不属于本 key 的调研，但被直接引用）

- `.agenticdoc/mw-jev-provider-integration/docs/jev-integration-flow-and-usage.md`：决策底座全链路（契约 / 三后端 / 失败分类 / 证据行 / 凭据复用 pi auth.json）
- `.agenticdoc/mw-jev-provider-integration/evidence/quality-gate-report-20261016-recheck.md`：底座的两轮 QG 结论（PASS，0 blockers）
- `packages/multi-workers/decision.py:74`（`EVIDENCE_RELATIVE_PATH`）、`:945-960`（证据行 11 字段）、`:88-99`（`REASON_CODES` 8 类）

## 待定事实（由 RQ 回答，不在本声明中假设）

1. pi 扩展能否在工具执行前接管确认（决定 DS-3 的未来与 P2 binding 的部分执行位置）。
2. 决策结果能否自动关联（决定 AC-006 是"自动"还是"人工标注"）。
3. 人工轮次/阻塞时长能否不改代码测出（决定 AC-010 是否需要新埋点）。
