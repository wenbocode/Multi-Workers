# PM State: timi-gpt-pi-routing



## Section 1: Snapshot

- Key: timi-gpt-pi-routing
- Claim-Id: 20260814-151438-9272
- Phase: DONE
- Goal: Fix Pi Timi GPT Responses routing and Multi-Workers launcher integration.
- Next action: All 7 tasks complete + all 5 P1/P2 reviewer findings fixed. Ready for merge.


## Section 2: Task Status

| Task | Stage | 代码状态 | 验证状态 |
|------|-------|--------|--------|
| 001-ts-cross-protocol-history | 1 | 完成 | 已验证 (4 tests pass) |
| 002-ts-retry-boundary | 1 | 完成 | 已验证 (14 tests pass) |
| 003-ts-model-resolver-dispatch | 1 | 完成 | 已验证 (VC-002/003) |
| 004-py-launcher-routing | 2 | 完成 | 已验证 (VC-008/009/010) |
| 005-py-remove-codex-7002 | 2 | 完成 | 已验证 (VC-011) |
| 006-py-mw-supervision | 2 | 完成 | 已验证 (VC-012, 8 tests) |
| 007-build-verify | 3 | 完成 | 已验证 (VC-013/015, dist ok; npm run build blocked by pre-existing network + stale model data issues unrelated to this work) |


## Section 3: Evidence Ledger



- E-001: The globally linked `pi` executes `packages/coding-agent/dist/cli.js`.

- E-002: Built `packages/ai/dist/providers/timi.js` routes every Timi model through `anthropicMessagesApi()`.

- E-003: Built Timi catalog marks `gpt-5.6-sol` as `anthropic-messages`, while current source assigns non-Claude models to `openai-responses`.

- E-004: Multi-Workers launcher currently executes Pi as `pi -p <task>` without an explicit Timi provider/model.

- E-005: The recorded `mw` parent process exists while ports 7001-7004 have no listeners.

- E-006: All 7 tasks completed. 45 unit tests pass (21 TS + 24 Python). dist/providers/timi.json: 15 models, 0 mismatches, gpt56_reasoning=3. VC-015: credential_leaks=0.
- E-007: Pre-existing TS errors in agent/bedrock tests and github-copilot.ts are NOT caused by this work (referenced removed providers "google"/"amazon-bedrock"). Pre-existing `npm run build` failure due to models.dev DNS hijack and stale provider shard files predates this work.
- E-008: Post-review AC-014 verification — `npm run check`: 580 errors, all pre-existing (HEAD baseline has 584; branch IMPROVED by 4). `npm run build`: fails on `generate-models` via pre-existing SSL interception of models.dev; `build:offline` also fails on pre-existing missing shard data. Neither failure is caused by this branch's changes.
- E-009: 5 P1/P2 reviewer findings all fixed: (1) models.generated.ts restored to 38 providers + timi; (2) wrapFetch and debug console.error logs removed; (3) _EXTRA_CREDENTIAL_VARS strips leaked creds from all 3 env paths; (4) _FatalLauncherError exits launcher on missing required credentials; (5) normalizePayload recursively deletes store at every depth. Tests: 62 TS + 28 Python all pass.



## Section 4: Hypothesis Queue



- H-001 CONFIRMED from E-001 through E-003: Pi GPT failures are caused by stale built artifacts using the wrong wire protocol.

- H-002 CONFIRMED from E-004: Multi-Workers does not select Pi's built-in Timi provider.

- H-003 OPEN from E-005: Child proxy failure is not reflected by `mw status`.



## Section 5: Decisions



- D-001: Standalone Codex remains on its existing user-level TiMiAIHub Responses configuration.

- D-002: This work uses a new key and depends on `agent-team-loop`.

- D-003: Include detection and reporting of stale `mw` service state when managed child processes exit.
- D-004: Use a project-scoped stop-request file and read-only Win32 liveness checks instead of Windows signal-based status/stop behavior.
- D-005: User explicitly authorized `npm run build` after tests and `npm run check`.


## Section 6: Turn End Records



### Turn 2026-08-14

1. Top-level goal: Create and claim a separate Agentic key for the Timi GPT Pi routing fix.

2. New evidence: E-001 through E-005 recorded.

3. Hypotheses changed: H-001 and H-002 confirmed; H-003 remains open.

4. Tasks to reopen: None; tasks are not generated yet.

5. Blockers: Design scope requires user confirmation before implementation.

6. New tasks needed: Yes, after spec/design approval.

7. Next action: Confirm scope, present design, and obtain approval.

8. State written: Yes.

9. Reusable pattern: Separate source/build protocol drift checks from launcher-routing checks.

### Turn 2026-08-14 (POST-IMPL review — P1/P2 fixes)

1. Top-level goal: Address 5 P1/P2 reviewer findings and confirm AC-014 status.

2. New evidence: E-008, E-009.

3. Hypotheses changed: None.

4. Tasks to reopen: None.

5. Blockers: None. npm run build and npm run check failures are pre-existing and pre-date this branch.

6. New tasks needed: No.

7. Next action: Merge.

8. State written: Yes.

9. Reusable pattern: When verifying AC-014, compare error count against HEAD baseline — pre-existing failures must not block merge.

### Turn 2026-08-14 (DESIGN review)
1. Top-level goal: Produce a complete measurable spec/design for the new key.
2. New evidence: AC-001 through AC-015, VC-001 through VC-015, Mermaid gate PASS, independent reviewer APPROVED.
3. Hypotheses changed: H-003 confirmed as a PID-only health design defect; Windows signal behavior added as a lifecycle risk.
4. Tasks to reopen: None; tasks are not generated yet.
5. Blockers: Written spec/design requires final user review before planning.
6. New tasks needed: Yes, after user approval.
7. Next action: Invoke writing-plans after user approval.
8. State written: Yes.
9. Reusable pattern: Cross-platform service stop should use an explicit request channel; status checks must be read-only.


## Section 7: Process Log



- 2026-08-14: Claimed key `timi-gpt-pi-routing` with dependency `agent-team-loop`.

- 2026-08-14: Recorded diagnostic evidence and paused at the design approval gate.

- 2026-08-14: User confirmed that stale-service health detection is in scope.
- 2026-08-14: Spec/design review completed after five iterations; reviewer result APPROVED.
- 2026-08-14: Post-implementation review raised 5 P1/P2 findings; all fixed in same session. npm run check verified pre-existing (580 vs HEAD baseline 584). DONE confirmed.
