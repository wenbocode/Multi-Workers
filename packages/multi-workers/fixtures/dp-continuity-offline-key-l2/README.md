# dp-continuity-offline-key-l2 fixture (T15-B / AC-015)

Offline, finite-budget, sign-required DP-continuity evidence fixture for the
"accepted-local runtime L2" path. This directory holds only test *input*
material (cards, fake provider/transport/CLI stand-ins). It never replaces the
production host / budget / store / validator / sign-off writer.

## Purpose

Prove, in one NEW isolated key + one run, that an OFFLINE decision-service
configuration (real transport + config + activity counters, no paid provider
and no external network) still **preserves the sign-off requirement**, and that
a real production dispatch produces a worker delivery that is consumed by an
independent reviewer (recomputed, content-based check, not a hardcoded pass),
with same-run QG / follow-up / native sign / isolated phase-Done evidence where
the production entrypoints permit.

The parent key `mw-pm-dp-continuity` is NEVER advanced (no phase/sign/Done).
Only an isolated key created under this run's dynamic root may reach Done, via
the real production writer / official phase interface.

## Files

- `worker-card.md`   - task card given to the fake worker (its declared goal).
- `fake-worker.cjs`  - offline stand-in for the worker provider/transport/CLI.
                       Produces a deterministic worker deliverable file.
- `review-card.md`   - task card for the independent reviewer.
- `fake-reviewer.cjs`- offline stand-in for the reviewer provider/transport/CLI.
                       MUST read the worker deliverable and recompute a
                       content-based check; it must not hardcode a pass.
- `README.md`        - this file (first business write of T15-B).

`test_dp_continuity_offline_key_l2.py` (in `packages/multi-workers/`) is the
collectable pytest entry that drives the run. `dp-continuity-runtime-l2.test.ts`
(in `packages/coding-agent/test/suite/`) is the E257 accepted-local runtime
test, preserved byte-for-byte (SHA-256
`e932e4129fc5de2aa07d38cfececf9e1118584d16ca6dc4dfc1646c9a825cc04`).

## Isolation

All persistent dynamic state for a run lives under
`runs/t15-b-20261117T054654Z/**` (control workspace, key, outputs, CLI,
pycache / pytest basetemp). Subprocess cwd / env / roots are set explicitly;
pytest and the native CLI must not write the real parent index or global home.
A distinct reviewer consumes the persisted artifacts read-only after PM
release, using a same-run legal resume entrypoint (no new run, no replay).

## Declaration contract (T15-B correction)

The dispatch card declares five exact fixture file paths (no trailing slash),
the exact Python and TS file paths, and recursive `/**` only for the run
dynamic dir and the own-worker dir. The shared write-face pure parser
(`packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts`)
confirms: trailing `/` is an exact node, `/**` is recursive; sibling files such
as `outside.txt` and other-run neighbours are outside the face. See
`preflight-raw.json` in the own-worker dir for the positive/negative verdict.
