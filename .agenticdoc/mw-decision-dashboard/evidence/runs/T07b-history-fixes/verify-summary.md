# T07b verify summary (dd-history-fixes)

| item | command / evidence | result |
|---|---|---|
| acceptance | `python -m pytest test_decision_history.py test_decide_archive.py test_decide_signoff.py test_decision_wire_store.py -q` (`pytest-green-acceptance.txt`) | 237 passed, exit 0 |
| history suite repeat | `python -m pytest test_decision_history.py -q` (`pytest-green-history-repeat.txt`) | 39 passed, exit 0 |
| test inventory | `pytest --collect-only` (`test-names.txt`, `test-names-list.txt`) | 23 pre-existing (1 rewritten) + 16 new |
| RED mutants | `python red_mutants.py` (`red-*.txt`) | mutants=10 survived=0, all assertion failures |
| fixture isolation | `python isolation_check.py` (`fixture-bytes-isolation.txt`) | 5 carriers unchanged, inventory unchanged, secret_echoed=False |
| production carrier isolation | `python isolation_check.py` (`carrier-bytes-isolation.txt`) | 5/5 real carriers unchanged, pytest exit 0 |
| real production history probe | `python real_history_probe.py` (`real-history-probe.txt`) | 38 records, dropped=0 invalid=0 invalid_keys=0 |
| neighbour consumers | `python -m pytest test_decision_monitor.py test_decide_sign_auto.py -q` | 68 passed, 1 skipped |
| biome (read-only) | `npx biome check .` (`check-biome-readonly.txt`) | exit 0; 3 warnings/2 infos only in foreign `mwoc-*.test.ts` |
| pinned deps / ts imports / shrinkwrap / install lock / tsgo | `npm run check:*`, `npx tsgo --noEmit` (`check-*.txt`) | all exit 0 |
| `npm run check` (full) | not run | would `biome check --write` foreign TS files (write-face) |

Mutation matrix (each mutant reverts one fix to its pre-fix behaviour):

| mutant | target test(s) | log |
|---|---|---|
| p1-1-raw-free-text | redaction/withhold/clip/boundary (5) | `red-p1-1-raw-free-text.txt` |
| p1-2-key-as-path | key validation + symlink refusal (3) | `red-p1-2-key-as-path.txt` |
| p2-1-engine-echo-without-answer | source claim (2) | `red-p2-1-engine-echo-without-answer.txt` |
| p2-2-usage-merge-without-semantics | usage semantics (1) | `red-p2-2-usage-merge-without-semantics.txt` |
| p2-3-first-settled-status | settled/status agreement (1) | `red-p2-3-first-settled-status.txt` |
| p2-4-silent-gate-drop | gate visibility (1) | `red-p2-4-silent-gate-drop.txt` |
| p2-5-auto-signoff-as-human | auto sign-off provenance (1) | `red-p2-5-auto-signoff-as-human.txt` |
| p2-5-no-dp-level-broadcast | dp-level authority (1) | `red-p2-5-no-dp-level-broadcast.txt` |
| p2-5-refresh-actor-human | refresh authority actor (1) | `red-p2-5-refresh-actor-human.txt` |
| isolation-reader-writes | no-write/no-mkdir isolation (1) | `red-isolation-reader-writes.txt` |

Known foreign failure (not this card): `test_mwds_t10_dispatch_run_state.py::
test_missing_run_json_dispatches_byte_identically` compares the PM dispatch card text and
fails on the newly added "交付段契约（本角色）" section; it does not touch history.
