# T14 screenshot default-log removal

Vision worker dc-t14-vision-log-blocks used gpt-6.1-sol (vision role, images=yes), read both PNGs; trace explicitly records image reads. Complete evidence/output absorbed and acked. Findings: screenshot1 is #pg-meta configuration metadata; screenshot2 is renderSubmissionDetail's pre-DAG audit/answer/outcome list, not the operation feedback list or submit output. Evidence: research/vision-log-blocks-20261023.md.

Cause: existing metadata renderer remained expanded; T13 renderLocalTest reused full submission detail even without a backend submission. User explicitly requested removal from default display.

Changed only dashboard HTML/JS/readable UI test:
- DP technical metadata contained in closed explicit `pg-config-details`.
- Actual submission technical definition list, answer/projection summary/outcome/attempts contained in closed `pg-submission-log`, after graph.
- Local initial/scaffold/preview render no submission log, no missing-persistence/answer/outcome boilerplate.
- Nonempty issues stay visible; DAG/node detail/status/errors/polling preserved. No registry/backend/data removal, no model/service/browser/build/install/commit/framework operations.

Baseline original bytes/hashes: t14-baseline/.
RED initial two failures included absent speculative details selector for one case; corrected test selector dependence, second RED two real default-field failures (t14-red2). GREEN readable UI29P. Neighboring assets9/workbench17/contracts119/playground13 all exit0; distinct fresh five files187P. Raw logs/metadata: ui-recovery/t14-green-*, t14-adjacent-*.
Protected full npm run check current snapshot exit1, same outside-scope three mwoc files3warnings2infos, later chain not run. t14-check/ metadata:11713 copied files, formatter_changes=[], original_changed_during_check=[]. No foreign formatter results applied.

No live browser/screenshot-after or deployment acceptance performed. Source-only removal; whole-key EXECUTE remains, review/24AC/global-check/deployment/separate auto-restart still pending.
