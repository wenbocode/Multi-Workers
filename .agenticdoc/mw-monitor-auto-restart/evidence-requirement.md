# Evidence Requirement: mw-monitor-auto-restart

## 锁定指纹
- spec_path: .agenticdoc/mw-monitor-auto-restart/spec.md
- ac_ids: AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008
- vc_ids: VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008
- design approved by user 确认 this turn; exact user UTC not supplied.
- Document snapshot hashes: evidence/design-draft-verification.md. Scope unchanged, design approval recorded separately, no fabricated timestamp/fingerprint.

## Evidence expected (not yet satisfied)
| AC | VC | Sufficient evidence |
|---|---|---|
| AC-001 | VC-001 | actual open writer using synthetic starter, one healthy start; no-open zero windows |
| AC-002 | VC-002 | reuse same identity/bytes, zero shutdown/start |
| AC-003 | VC-003 | RED then GREEN order verifies auth→stop→port/files→old PID death→start→health; covered asset hash changes; synthetic old detached process |
| AC-004 | VC-004 | identity/project/secret/state mutation failures before shutdown and no start; raw-byte preservation |
| AC-005 | VC-005 | shutdown failure/detail/retained/foreign/process alive/unknown/timeout, zero replacement/kill/caller delete; truthful partial failures |
| AC-006 | VC-006 | held lock during stop/death/start; second open fails lock conflict with no start; later reuse |
| AC-007 | VC-007 | actual open no-open passes opt-in with zero browser; history/submission original-byte equality; tokens absent from report |
| AC-008 | VC-008 | original status/stop unchanged, existing monitor/CLI targeted tests and new entry-boundary probes |

## Verification boundaries
Serial isolated test files, scrubbed HOME/USERPROFILE/agentDir/secret/proxy env, private temp roots/random loopback; no shared monitor/service/browser/model. Capture full UTF8 stdout/stderr UTC/argv/cwd/rc. Targeted tests are source verification, not installed runtime/real-browser acceptance. Full npm check protected copied source only (no foreign formatter application); retain blocker if unrelated diagnostics remain. No whole-key DONE/signoff until independent quality review and complete evidence.
