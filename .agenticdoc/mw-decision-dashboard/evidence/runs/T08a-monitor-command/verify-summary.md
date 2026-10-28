# T08a monitor command — verification summary

UTC run window: 2026-10-22T11:04Z..11:07Z (cli-lifecycle.txt), same session as RED/GREEN.
Python 3.14.3 on win32, repo HEAD 54f194d69caea6675285345df57fb0765f769b0c.

## RED -> GREEN

| Step | Command (cwd = packages/multi-workers) | Exit | Result / log |
|---|---|---:|---|
| RED | `python -m pytest test_decision_monitor_cli.py -q --tb=line` | 1 | 9 failed, every failure `argument decide_action: invalid choice: 'monitor'` (`red-pytest.txt`); reproduces T12a `python-monitor-absent.txt` |
| GREEN | `python -m pytest test_decision_monitor_cli.py -q` | 0 | 12 passed in 37.82s (`green-pytest-final.txt`); earlier 12-test run 36.42s (`green-pytest.txt`) |
| GREEN repeat | same (11-test revision) | 0 | 11 passed in 35.25s / 35.06s / 34.94s |
| Narrow regression | `python -m pytest test_decision_monitor.py test_decide_cli.py test_decide_sign_auto.py test_decide_signoff.py test_decide_dp_cli.py test_decision_cli_config_snapshot.py test_decide_run_authority.py test_decision_dashboard_contracts.py -q` | 0 | 352 passed, 1 skipped in 34.71s (`green-narrow-final.txt`; earlier identical run `green-narrow-regression.txt`) |
| Compile | `python -m py_compile mw.py test_decision_monitor_cli.py` | 0 | `py_compile OK` (`py-compile.txt`) |
| Repo check (read-only substep) | `npx biome check --error-on-warnings .` | 1 | 3 warnings + 2 infos, all in pre-existing `packages/coding-agent/test/suite/mwoc-*.test.ts` (other sessions); no finding in this card's files (`check-biome-readonly.txt`). Full `npm run check` not run: its first step is `biome check --write`, which would rewrite other sessions' files. |
| Repo check (read-only substeps) | `check:pinned-deps` / `check:ts-imports` / `check:shrinkwrap` / `check:install-lock:coding-agent` / `npx tsgo --noEmit` | 0 / 0 / 0 / 0 / 0 | all pass (`check-readonly-substeps.txt`, `check-tsgo-readonly.txt`) |
| Isolation | `netstat` LISTENING scan after tests/demo | 0 | 0 LISTENING sockets in 43170..43269 (`isolation-check.txt`) |

## Live CLI transcript (`cli-lifecycle.txt`)

- Private starter argv: `[<python>, <repo>/packages/multi-workers/mw.py, _decide_monitor_starter, --project, <tmp root>]`, cwd = that tmp control root.
- Real child: state pid == starter pid, port 43243 in 43170..43269, listen addresses `['127.0.0.1']`, health identity matches, authenticated shutdown HTTP 200, exit 0, state+secret gone, probe refused (10061).
- `mw decide monitor --json --no-open`: exit 0 in 0.63s, `reused=false`, full starter argv/cwd/log in JSON, state+secret created, no token/boot in stdout/stderr.
- Reuse: exit 0, `reused=true`, same instance/port, state+secret bytes unchanged.
- `status --json`: exit 0, `healthy=true`, state bytes unchanged; no start lock.
- `stop --json`: exit 0, `stopped=true`, `port_probe=refused`, `state=absent`, files gone, listener gone.
- Window attempt with a missing Chromium: exit 0, `spawned=false`, `visibility=not-opened`, explicit reason+guide, `#boot=<redacted>` in argv, no boot code and no control token in output, `url` has no fragment.
- CLI help (`cli-help.txt`): `decide --help` lists `monitor`; `decide monitor --help` lists `{open,status,stop}`, `--project`, `--no-open`, `--json`.
- Unit runs: 12 tests, each starting/stopping at most one temp-root monitor; no shared `mw serve`, no user browser, no real credentials/auth records; HOME/USERPROFILE/LOCALAPPDATA/TMP isolated per test.

## Dependency hashes at GREEN (`cli-lifecycle.txt`)

```
mw.py                          2505c20371ff63b51ffdec751c0ab8c61537557a3db635a04eb36b70ba3a846e
test_decision_monitor_cli.py   b22d472b1d51302a620d7878cfadf971335edcab6e50ad186434115e9a1b5451
decision_monitor.py            c6e8e11f8a72049dda81e0c164b7a6cf7bfea7f0f78dbe0b4f57727f1a87550b
decision_wire.py               47ef6322ccdffb0dae677c009a86d6eafdd7a7842bb7796acbb23b912c684253
decision_history.py            bf1619d1280f02a2631a8da2a76273c812ff8acf844d3d8d6fc1f2408d6ed2c3
decision_points.py             d299f67ea6e97f35d5765dd4428f58893a50431e3db22dcbb5f65535a1b22fef
decision_book.py               fc6d74a31abbddfa2c4a246f7a55cc23ba4c4844a41ed10d6547b2fc006b129f
mw_common.py                   80af680d21efed0dbb51182c3b693a81efe2368fc0fc1114465fdb259ff7daf0
decision_dashboard.html        1e268500e6905789f5e9894767ea9349f795b9e7e65cbf04b0064b6f983b59a0
decision_dashboard.js          5cbac255af16a9a4abda5eb2648a4ee69aa3fa8d5ebc8e1d23fe473fae3761bb
decision_dashboard.css         540497bd17a7ea24ba22ab57a66700af2a0f846639a054001235252af083c4cb
```

Hashes were identical before/after the run (`dependency_hashes_stable=True`).
`decision_monitor.py` was not modified (it is untracked from T10 in this worktree).

## Shutdown-race note

T10 `MonitorInstance.request_shutdown()` answers `/api/shutdown` and then removes
state/secret from a daemon thread named `decide-monitor-stop`; `serve()` returns
on the main thread as soon as `stop()` flips its flag. Without a join the child
can exit between those steps and leave state/secret behind (reproduced in
`debug_shutdown*.py`). `mw.py` waits for that thread after `serve()` returns
(`_join_monitor_stop_threads`); no monitor-file change was needed.
