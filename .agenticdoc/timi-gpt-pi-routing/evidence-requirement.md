# Evidence Requirement: timi-gpt-pi-routing

## Locked fingerprint

| Field | Value |
|---|---|
| spec_path | `.agenticdoc/timi-gpt-pi-routing/spec.md` |
| spec_locked_at | `2026-08-14` |
| ac_fingerprint | `7923ef691e85` |
| ac_ids | AC-001 through AC-015 |
| vc_ids | VC-001 through VC-015 |
| generated_at | `2026-08-14` |

## Per-AC evidence and sufficiency

| AC | Required evidence | Exact sufficiency rule |
|---|---|---|
| AC-001 | VC-001 direct generated-catalog test | Every catalog ID checked; zero protocol mismatches; three GPT-5.6 reasoning matches |
| AC-002 | VC-002 provider dispatch test | Public stream dispatch succeeds for one model per family without inspecting private construction state |
| AC-003 | VC-003 model resolver test | Resolved provider/model equals `timi/gpt-5.6-sol` |
| AC-004 | VC-004 payload matrix | Every named normalization/hook/immutability case passes |
| AC-005 | VC-005 retry/stream matrix | Every listed status, cancellation, boundary, and post-start case passes |
| AC-006 | VC-006 converter matrix | Both cross-directions plus both same-API signature cases pass |
| AC-007 | VC-007 compatibility deep equality | Every non-Claude model matches all seven exact fields |
| AC-008 | VC-008 launcher command/environment assertions | Exact argv and all environment presence/absence assertions pass |
| AC-009 | VC-009 launcher command/environment assertions | Exact argv, URL, key, and isolation assertions pass |
| AC-010 | VC-010 Codex launcher matrix | Empty/codex accepted, other rejected, exact argv, OpenAI variables absent |
| AC-011 | VC-011 named-surface scan/tests | Zero obsolete port-7002 behavior across all six files |
| AC-012 | VC-012 lifecycle matrix | All startup/runtime/simultaneous/stop-file/KeyboardInterrupt/POSIX-SIGTERM/child-kill/PID/Win32-read-only/stop-timeout cases pass |
| AC-013 | VC-013 generated-dist plus offline CLI output | Dist checks pass and exactly three GPT-5.6 rows report thinking `yes` |
| AC-014 | VC-014 command logs | Every direct test, `npm run check`, and approved `npm run build` exits 0 |
| AC-015 | VC-015 leak checks | Zero secret-value matches and zero credential fields in generated metadata |

## Required command evidence

- Modified TypeScript test files run directly with package-local Vitest commands.
- Modified Python tests run directly without network access.
- `npm run check` full output is retained and exits zero.
- User-approved `npm run build` full output is retained and exits zero.
- `pi --list-models timi --offline` is parsed without making a provider request.

No real provider API call or credential value may appear in evidence.
