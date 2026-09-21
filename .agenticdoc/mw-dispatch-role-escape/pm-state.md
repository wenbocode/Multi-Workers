# PM State: mw-dispatch-role-escape

## 1. Snapshot
- Key: mw-dispatch-role-escape
- Claim-Id: —
- Phase: DONE
- Next Action: —
- Started: 2026-09-20 20:38
- Updated: 2026-09-20 20:52
- Completed: 2026-09-20 20:52

## 2. Task Status
| Task | 代码 | 验证 | 说明 |
|------|------|------|------|
| T-01 TS 派发门禁 | 完成 | 通过 | dispatch-models + ui-bridge + 10 用例；168/168 |
| T-02 Python launcher 观测行 | 完成 | 通过 | launcher `_model_override_note` + 4 用例；pytest 692 passed |
| T-03 文档 + dist + 冒烟 | 完成 | 通过 | 三份文档 + bundle/dist 重建 + 安装后 bundle live smoke |

## 3. Evidence Ledger
- E-001: 168/168 agent-team-loop.test.ts（新增 10，原 158 零回归）→ AC-001~AC-008/AC-010 PASS
- E-002: pytest 692 passed / 0 failed / 9 deselected → AC-009/AC-010 PASS
- E-003: `npm run check` biome 0 修复 + tsgo 0 错 + shrinkwrap/install-lock 一致 → AC-010/AC-011 PASS
- E-004: 安装后 bundle live smoke（临时项目，BOM 配置）：无理由覆盖被拒（无目录）+ 带理由覆盖落盘 `model-reason` + 无 model 时回显 `dispatch.yml review=timi/gpt-5.6-sol` → AC-001/004/005/006/008 PASS
- E-005: smoke worker trace `type=review` + `[MODEL] model=gpt-5.6-sol` + 仅 read 工具（review 白名单）→ 原缺陷（role 不可达）端到端修复 PASS
- E-006: 临时项目 launcher.log 出现 `model-override task=timi/gpt-5.6-luna config:review=timi/gpt-5.6-sol` → AC-009 PASS
- E-007: 首轮 smoke 暴露 BOM fail-open（TS 未读到配置 / PyYAML 读到）→ 修复 `readRoleModel` 剥 BOM + 双侧用例 VC-013 → PASS
- E-008: 质检报告 24 ✅ / 2 ⚠️ / 0 ❌（欠债：/worker live 路径、CLI 直调 id 校验）→ 有条件通过，待用户确认
- E-009: 清理完成：临时项目 serve 已停（PID 16436）、临时目录与仓库临时脚本已删；框架 serve（115752）未受影响
- 证据归档：evidence/runs/run-2026-09-20.md · evidence/baseline/baseline-defect-state-2026-09-20.md · evidence/quality-gate-report-2026-09-20.md

## 4. Hypothesis Queue
*(empty)*

## 5. Decisions
- 2026-09-20: 用户裁定方案 1（保留 per-task `model` 覆盖，但强制理由 + 显式回显），据此写 spec/design；非目标含「不删除覆盖能力」
- 2026-09-20: 对「dispatch.yml 解析失败不阻断派发」原则做**有意例外**：可解析但模型 id 不存在的 role 值 fail-closed（逃生口＝显式 model + 理由），理由见 spec §2.4 / design D-005
- 2026-09-20: 校验点选 TS 派发期 + pi 窗口 `/mw model set`，不改 Python 解析链（D-004/D-010；Python 无模型表）
- 2026-09-20: 执行期发现 BOM fail-open，在 AC-007 内补 BOM 分支（AC 编号未变，fingerprint 未变）

## 6. Turn End Records
*(empty)*

## 7. Process Log
*(empty)*
