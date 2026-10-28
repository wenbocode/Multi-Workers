# T01: PM serial safe automatic monitor replacement
- type: coding
- executor: PM direct (not dispatched)

## 上下文
Goal .agenticdoc/goal.md; spec.md AC001–008; design.md D001–005 confirmed by user 确认. Source packages/multi-workers/decision_monitor.py:2663 ensure_instance, :416 fingerprint; packages/multi-workers/mw.py:5565 _monitor_open. Both research paths evidence/research/spec-lifecycle-20261024.md and spec-cli-20261024.md read; worker done/acked.

## 要求
RED→minimal GREEN: incompatible authenticated same-project restart inside held lock; strict stopped/detail/refused/absent + literal old PID identity gone before new start, bounded10s and unknown/self refusal. Hash module+3assets. Preserve compatible reuse/low-level default/status/stop; CLI alone opts in and reports replacement truth/no secrets. Recheck identity/token/files/guard/port around transitions; no caller delete/move live instance. Tests private tmp roots/fake probes/fake server only, no user's monitor/shared serve/browser/model. No redispatch after tool's automatic API side effects.

## 写入允许面
- packages/multi-workers/decision_monitor.py
- packages/multi-workers/mw.py
- packages/multi-workers/test_decision_monitor_auto_restart.py
- packages/multi-workers/test_decision_monitor_auto_restart_cli.py
- .agenticdoc/mw-monitor-auto-restart/evidence/
- .agenticdoc/mw-monitor-auto-restart/pm-state.md (machine fields unchanged)

## 写入禁止面
Other source/test files, dashboard assets, registry, any config/framework/global agent settings/locks/deps/generated files, other keys, user's live lifecycle state/history. No build/install/commit/live commands.

## 验收命令
Use evidence/run-verify.py serial runner for named isolated pytest files with scrubbed HOME/secrets/proxy env and full raw output UTC argv cwd rc. Full npm check only protected copied tree. All modified/new tests run; no npm test/build/full pytest/vitest. Existing targeted monitor/CLI and readable contracts safety retained.

## 改动历史
Initial task baseline frozen before source writes: evidence/baseline/. Source implemented in approved two files with two new tests. Three RED/GREEN cycles retained: true incompatibility/asset/CLI omission; partial exit report; secret metadata uncertainty. Postimplementation follow-up integration/timing/spies not retroclaimed test-first. Byte integrity verifier confirms exact3 CLI edits and monitor outside-region equality. Targeted source275P1S, all selected command exits0; full protected check still exit1 outside-card TS diagnostics. Report evidence/implementation-report.md; not whole-key closed or deployed.

## 交付格式
Baseline raw byte/hash/diff evidence, RED/GREEN logs/metadata, final targeted verification/failure report, PM state updates. Explicit current source vs runtime/whole-key scope; partial old-stopped/new-start-failed facts preserved. No DONE without review evidence.
