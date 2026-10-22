# pm-state — mw-signoff-per-key

- Phase: DONE
- Updated: 2026-10-22 01:02
- Completed: 2026-10-22 01:02

## Snapshot

- Next Action: 等 QG review 回读后签收（`mw decide sign --key mw-signoff-per-key --project . --allow-empty`，本 key 无决策档案行，预期 jev 答 `narrow`），再 `advance_phase done`。
- 卡片：`mini-spec.md`（trivial-fix fast path，无 tasks/）
- 证据：`achieved.md`、`evidence/quality-gate-report-*.md`（QG worker 产出）

## 验证记录（ledger）

| 阶段 | 命令 | 结果 | 判定 |
| --- | --- | --- | --- |
| EXECUTE | `python -m pytest -q test_decide.py test_decide_cli.py test_decide_sign_auto.py test_decide_signoff.py test_decide_dp_cli.py test_decision_points.py test_decide_registry_contract.py test_decide_registry_export.py test_decision_book.py test_decision_context.py test_decide_policy.py test_decide_archive.py test_decide_report.py` | 647 passed | **PASS** |
| EXECUTE | `npx vitest --run test/suite/decision-signoff.test.ts test/suite/xkey-gate-guard-coverage.test.ts` | 25 passed | **PASS** |
| EXECUTE | `python mw.py decide dp check --project ../..` | 0 error / 0 warning，rc=0 | **PASS** |
| EXECUTE | `python scripts/gen_decide_registry_ts.py --check` | rc=0（无漂移） | **PASS** |
| EXECUTE | `npx tsgo --noEmit`（packages/coding-agent） | rc=0 | **PASS** |
| EXECUTE | `npm run check`（repo root） | rc=1：3 warnings 全在他人会话未提交的 `mwoc-matrix-t07.test.ts`；本次 3 个文件 biome 干净 | **PASS（非本 key 面）** |
| EXECUTE | `python mw.py decide dp show --project . dp25-signoff-conclusion` | `P2 enabled=true mode=auto source=config`，`layer=OK` | **PASS** |
| EXECUTE | `.mw/decide-points.json` 行数断言 | 25 行，dp25 `{tier: P2, enabled: true, mode: auto}`，`updated_by=refresh` | **PASS** |
| EXECUTE | `mw decide sign --key mw-decision-substitution --project . --dry-run` | 2 rows，sha 与既有签收一致（签收不受表更新影响） | **PASS** |
| EXECUTE | mw decide sign --key mw-signoff-per-key --project . --allow-empty | jev 答 
arrow（confidence=1.0 api），signed_via: auto-decide，无 fallback；第二个 key 现场验证通用性 | **PASS** |
| QG | psk-qg-review（独立复核） | Verdict: PASS，6 项全过，0 BLOCKER / 0 MAJOR / 3 MINOR | **PASS** |
| FIX | QG MINOR-1/2/3 处置 | ①decide_signoff.py:93-97 注释改 P2/wired-echo；②docs/decision-points.md 必填字段表补 dp25（3→4 个）；③_dp_refresh/_dp_set 补写 updated_at + 	est_decide_dp_cli.py 断言 | **FIXED** |
| EXECUTE | 处置后复跑 | 647 passed；vitest 48 passed；dp check 0 error/0 warning | **PASS** |
