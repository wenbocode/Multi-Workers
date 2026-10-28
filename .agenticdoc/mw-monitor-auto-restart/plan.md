# Plan: mw-monitor-auto-restart

## Context and parallel analysis
Spec AC001–008 / design D001–005 approved. Goal .agenticdoc/goal.md. Research RQ1 worker and PM RQ2 complete, disjoint unique evidence. Further dispatch paused because tool automatically invokes real dp1 API; confirmed no-new-API boundary outweighs worker parallelism. PM sole source writer, serial implementation; no other source worker in flight. Preserve current dirty work and baseline raw bytes/diffs. Docs serial PM only; code surface two files plus new targeted tests, not dashboard/registry/framework/config.

## Task DAG
T01 freeze baseline / regression RED → T02 lifecycle and asset fingerprint GREEN → T03 actual CLI opt-in/report wiring GREEN → T04 isolated matrix verification, protected full npm check and source-report. T02/T03 different file boundaries could parallelize in theory; cannot safely dispatch now, and CLI interface depends on T02. Verification waits stable files.

## T01 baseline / tests
Full decision_monitor read completed; mw monitor region inspected, only local _monitor_open changes. Freeze exact decision_monitor.py/mw.py bytes and git status/diffs. New test_decision_monitor_auto_restart.py and test_decision_monitor_auto_restart_cli.py; fake probes/monotonic clock/stop and tmp roots, real orchestration / mocked unavoidable OS/network. Fingerprint synthetic module/assets temp, no repository mutation. Observe true incompatibility refusal and actual CLI no opt-in RED before code, not merely absent API TypeError.

## T02 implementation
Opt-in keyword, lock-held strict identity rechecks+auth+shutdown result validation+post-stop old-process death (bounded10s, self/unknown refusal)+guard/files/port reread; no recovery/moves on successful restart, require absent files. Reuse existing stale recovery only before nonreplacement starts. Add replacement metadata to healthy instance and partial failure errors. Include ordered length-framed module/asset raw bytes fingerprint, unreadable source explicit error.

## T03 CLI
_only _monitor_open opts in_; output previous-identity/stop/exit report and mode=replaced. Window only after healthy instance, no-open no browser. Status/stop and child startup unchanged. New tests exercise actual _monitor_open and _decide_monitor routing, no provider/start/browser real calls.

## T04 verification
Run new test files then selected existing monitor/CLI/contract/assets/playground tests serial isolated. Synthetic private-loopback old detached child integration if safe fixture can authenticate shutdown with no credential reads; no shared monitor/PID/ports. Protected root npm check via existing snapshot pattern under this key, no install/build, don't repair outside write-face diagnostics. Raw logs/metadata baseline/final hash manifests report limitations. No whole-key acceptance/DONE/deployment without later quality review.
