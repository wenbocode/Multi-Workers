# RQ1: identity, authentication and graceful lifecycle for automatic replacement

Scope: read-only source analysis of `packages/multi-workers/decision_monitor.py` and the
monitor call sites in `packages/multi-workers/mw.py`, answering RQ1 for spec AC001-008.
No source writes, no service/browser/model/provider/build/install/commit run. Every claim
below is source-derived; no live monitor was started or stopped.

## 结论

- Automatic replacement is feasible with the existing primitives and **no new protocol**:
  compatibility (`protocol_version` + `code_fingerprint`) is a separate predicate from
  identity/auth (project id, instance id, pid + start time, port, control token). An
  incompatible instance still reports its *own* recorded identity over authenticated
  `/api/health`, so it can be identity-proven before it is asked to stop
  (`decision_monitor.py:2701-2704`, `:1218-1235`, `:2473-2504`).
- The minimal safe change is one opt-in branch in `ensure_instance` (default off, enabled
  only by `mw decide monitor open`) that runs under the already-held start lock:
  project check -> authenticated health+identity match -> authenticated `/api/shutdown` ->
  accept only an *accepted* request plus confirmed `ECONNREFUSED` plus old state gone ->
  existing `recover_stale` + `start` + `wait_health`.
- `AttachedInstance.stop()`'s `stopped=True` is **not** a sufficient replacement gate:
  `stopped` only proves the port refused, and it can be true with a non-empty `detail`
  (failed/refused request) and with `state="retained"|"foreign"` (`:2551-2610`).
- No force kill or live-state deletion is ever needed: the old instance removes its own
  state/secret before it closes the listener (`:2377-2395`, `:2407-2424`), and stale
  material is only renamed aside by `recover_stale`/`_move_aside` (`:753-766`, `:1063-1190`).
- Two concrete gaps that the current compatibility predicate does not cover: (1) dashboard
  assets are not fingerprinted (`:173-194`, `:416-424`), so a JS/HTML/CSS-only edit reuses a
  stale UI; (2) a non-1 `schema` or malformed state never reaches a replacement decision
  (`:478-495`, `:2689-2696`).
- Concurrency is satisfied by fail-closed locking, not by queueing: `ensure_instance` holds
  the start lock for the whole decision, and acquisition is capped at ~0.248s
  (`:93-95`, `:826-887`, `mw_common.py:2388-2425`), so a second open during a multi-second
  replacement gets `start-lock-conflict` (AC-006 holds; a waiting UX needs a real retry loop,
  not a larger budget).
- Biggest implementation risk: `AttachedInstance.stop()` has no injection seams today
  (hard-coded `_post_json`, `probe_recorded_port`, `time.sleep`, `read_state`), so the
  failure matrix cannot be tested deterministically without a small, behavior-preserving
  seam refactor (`:2539-2610`, `:2613-2646`).

## 证据

### 1. Compatibility vs identity/auth (distinct predicates, distinct failure meanings)

- Compatibility is exactly two fields: `identity.protocol_version == PROTOCOL_VERSION and
  identity.code_fingerprint == CODE_FINGERPRINT` (`decision_monitor.py:2701-2704`).
  `PROTOCOL_VERSION = 1`, `STATE_SCHEMA = 1` (`:84-85`). The CLI duplicates the same
  predicate only for display (`mw.py:5364-5367`).
- `code_fingerprint` is `sha256(decision_monitor.py bytes)[:16]` computed at import
  (`:416-424`). It does **not** cover `decision_dashboard.{html,css,js}`; those are read at
  import into `STATIC_ASSETS` (`:173-194`) and served from memory (`:1588-1590`,
  `_send_static`). Consequence: a running instance keeps serving the old JS after an asset
  edit and `ensure_instance` reuses it (no fingerprint change). This is directly relevant to
  the goal "refresh monitor after source updates" (source-derived, not reproduced live).
- Identity fields are `project_id, instance_id, pid, pid_start_ms, port, protocol_version,
  code_fingerprint, schema` (`:448-471`). `_identity_problem` requires `schema ==
  STATE_SCHEMA`, non-empty text fields and positive ints (`:478-495`); violations become
  `instance-unknown` before any lifecycle decision (`:540-557`, `:2689-2696`). Therefore an
  incompatible-but-parseable instance (protocol or fingerprint drift) is restartable, while a
  schema/malformed state is not; it stays fail-closed.
- Project ownership is checked separately and earlier: `_require_project_match`
  (`:738-752`) calls `decision_wire.project_id_for(root)`. A *foreign project* state raises
  the same `incompatible-instance` kind as a version/fingerprint mismatch
  (`:743-750` vs `:2712-2722`), and `_monitor_read_recorded` repeats that kind for stop/status
  (`mw.py:5325-5337`). Consequence: replacement logic must not branch on `kind` alone; the
  project check must stay before any HTTP/stop and keep its "nothing moved" guarantee
  (existing test `test_foreign_project_state_is_a_conflict_and_is_not_moved`,
  `test_decision_monitor.py:1808`).
- Identity proof is version-independent: `/api/health` returns the *instance's own* identity
  (`:2473-2504`), and `identity_matches` compares against the **recorded** identity, not the
  current build constants (`:1218-1235`). So an old build with `code_fingerprint=old` can be
  proven to be exactly the recorded process/port before stop - the crux for AC-003/AC-004.
  `identity_matches` compares project_id, instance_id, code_fingerprint, protocol_version,
  pid, port and pid_start_ms (5s tolerance, `START_TOLERANCE_MS` at `:97`); it does not
  compare `schema`.

### 2. Authentication boundary for an automatic stop

- Control routes require the control role: `/api/shutdown` is `("control","shutdown")`
  (`:1480`); role resolution is a constant-time compare against the 256-bit control token
  (`TOKEN_BYTES=32` `:91`, `generate_token` `:608-610`, `TokenStore.role_for` `:617-636`).
  Missing/invalid token -> 401 before the handler (`:1603-1619`).
- The token is published per instance in `.mw/decide-monitor.secret` atomically, owner-only
  on POSIX (`:591-598`, `_atomic_write` `:559-581`); it never appears in the state document
  (`publish_state` `:583-589`). A stale token cannot stop a different instance on the same
  port: that instance's `role_for` rejects it (401 -> `health()` returns `None`,
  `:1196-1215`; `_post_json` raises `instance-refused`, `:2634-2638`).
- Origin is *not* required for a control POST (`require_origin = role_required in
  ("public","page") and method == "POST"`, `:1620`), so `AttachedInstance.stop` sends only the
  token header (`:2623-2630`). Host is still pinned to the exact loopback `Host`
  (`:1626-1633`), so an automatic stop cannot be redirected to another host.
- `health()` collapses 401, timeout, connection failure and non-JSON into `None`
  (`:1196-1215`). "Cannot authenticate" and "cannot reach" are therefore indistinguishable
  and must both fail closed (no stop, no move, no start).

### 3. What a graceful stop actually confirms (truth table)

Server side: `_act_shutdown` calls `request_shutdown()` and returns `{"stopping": true}`
immediately (`:1728-1732`); a daemon thread sleeps 50ms then runs `MonitorInstance.stop`
(`:2397-2405`). `stop()` order is: `server.shutdown()` -> `_remove_own_files()` (state, then
secret, only when the state still names this `instance_id`) -> `server_close()` ->
`listener.close()` (`:2377-2395`, `:2407-2424`). The comment at `:2385-2386` states the
intent: "port free implies state gone". Because `listener.close()` is last, a client-observed
`ECONNREFUSED` happens-after the old instance's file removal; the second `stop()` from
`serve()`'s `finally` is a no-op (`_stopped`, `:2378-2379`). So the old process can never
delete a replacement's new state after the refusal is observed.

Client side: `AttachedInstance.stop()` (`:2539-2610`) sends the authenticated POST
(`:2551`), probes the recorded port until it is not "connected" (10s loop, `:2557-2564`;
3s per probe, `:104`), and then polls the state for <=2s (`:2580-2598`). Returns
`{stopped, detail, port, instance_id, port_probe, state}` (`:2603-2610`).

| shutdown request | port probe | state poll | result | replacement-safe? |
|---|---|---|---|---|
| accepted | refused | absent | `stopped=True`, `detail=None`, `state="absent"` | yes |
| accepted | never refused | - | `stopped=False`, `state="unknown"` | no (`:2565-2578`) |
| failed/refused (401/timeout/dead) | refused | absent/retained | `stopped=True`, `detail` non-empty | no: closure was not caused/proven by this caller (`:2599-2602`) |
| accepted | refused | another `instance_id` | `stopped=True`, `state="foreign"` | no: a publisher appeared (`:2592-2594`) |
| accepted | refused | still this instance | `stopped=True`, `state="retained"` | not by itself (`:2595-2602`) |

Consequence for design: accept only `stopped is True and detail is None and
port_probe == "refused" and state == "absent"` (or handle `retained` as a separate,
liveness-gated stale-recovery step). `probe_recorded_port` treats only
`ECONNREFUSED`/Windows `10061` as proof; timeout/ACL/reset are `unknown` (`:916-960`).
`_post_json` has a 5s timeout and maps HTTPError to `instance-refused` without status detail
(`:2613-2646`).

No kill, no delete: `AttachedInstance.stop` docstring `:2542-2547`; the only destructive
lifecycle operation in this area is a rename by `_move_aside` to
`<name>.stale-<instance_id>` (`:753-766`), used by `recover_stale` (`:1015-1190`) and only
after proof of a dead owner + refused port + re-read identity.

### 4. Lock ownership, coverage and acquisition limits

- Start lock: `.mw/decide-monitor.start.lock` (`:86-92`, `:444`), acquired with
  `O_CREAT|O_EXCL` (`mw_common.py:2388-2425`), owner stamped with pid + process start time
  (`mw_common.py:2804-2833`), classification absent/legacy/alive/dead/unknown where only
  `dead` is stealable (`mw_common.py:2836-2915`). `StartLockGuard.verify()` re-checks pid,
  start time and the same file before each destructive step (`:786-824`); release only
  removes a lock that still carries this process identity (`:768-783`); a dead owner's lock
  is moved aside, never deleted (`:826-887`).
- `ensure_instance` holds this lock across read -> liveness -> recovery -> start ->
  health wait (`:2688-2793`). The old instance's `stop`/`_remove_own_files` never take the
  start lock (`:2397-2424`, `:2539-2610`), so performing the stop while holding the lock
  cannot self-deadlock; the parent starter already relies on the same discipline
  (`mw.py:5481-5482`, `:5530-5564`).
- Acquisition is capped: `START_LOCK_RETRIES=5`, `START_LOCK_BASE_DELAY=0.008`,
  `START_LOCK_BUDGET_S=0.25` (`:93-95`); `_acquire_start_lock` passes `retries=5`
  (`:832-840`), i.e. 6 attempts whose sleeps sum to 0.248s. `deadline_s` only shortens the
  sleeps (`mw_common.py:2414-2425`), so increasing `budget_s` alone cannot make a concurrent
  open wait. AC-006 is satisfied by fail-closed `start-lock-conflict`; a waiting UX requires
  an explicit retry loop.
- Crash safety: the lock owner is the CLI process. If it dies mid-replacement, the owner is
  provably dead and the next open moves the lock aside. The old instance either was not
  stopped (state alive -> reuse/refuse) or removed its own state/secret on stop
  (-> normal start). Publication only happens in `MonitorInstance.start` (`:2334-2375`), and
  the parent adopts only a state whose PID equals the child it spawned (`mw.py:5497-5515`),
  so at most one instance owns the state document.

### 5. Races and TOCTOU points to re-check (all under the start lock)

1. State/secret read, then health: if the secret was replaced between `read_secret` and the
   health call, the health call returns `None` (401/other) -> fail closed. If a different
   instance now serves the recorded port, the old token is rejected; no stop.
2. Health/identity verified, then shutdown: a different instance cannot accept the old token
   (401). An instance that died in between yields `detail` non-empty -> refuse (rule in §3).
3. Stop accepted, then start: if a non-cooperating publisher (`serve()` invoked directly,
   outside the lock) writes a state during the stop, `state="foreign"` or a fresh state is
   seen -> fail closed and preserve; `recover_stale` also re-reads state and secret and
   compares file identity before moving (`:1063-1190`).
4. State absent after stop, then `recover_stale`: its state-`None` branch only moves an
   orphan secret (`:1078-1091`). A fresh secret published by a non-locking publisher between
   that read and the move would be moved aside; this is an inherited, documented race
   (precedent: `.agenticdoc/mw-decision-dashboard/workers/dd-review-monitor/report.md:88`),
   not introduced by replacement, and cooperating starters are excluded by the lock.
5. Port re-bind: `bind_listener` tries all candidates in `43170..43269` (`:665-732`), so a
   just-closed port that is not immediately bindable (e.g. Windows TIME_WAIT) falls back to
   another candidate instead of failing the replacement. Not exercised here.

### 6. Existing contracts/tests that constrain the change

- Reuse without rewriting state/secret: `test_decision_monitor.py:1548`.
- Live incompatible instance currently refuses, state unchanged:
  `test_incompatible_protocol_or_code_identity_is_a_conflict` (`:1886`). If replacement were
  enabled by default in `ensure_instance`, this test's expected `incompatible-instance`
  outcome would change; hence the opt-in flag default `False`.
- Foreign project refused, nothing moved (`:1808`); alive-but-unhealthy refused
  (`instance-unresponsive`, `:1829`); malformed/PID-reuse -> `instance-unknown` (`:1858`);
  start-lock conflict (`:1573`).
- Stop contracts: refusal -> `stopped=False` and the live instance keeps serving (`:1775`);
  success -> `stopped=True`, `port_probe=refused`, no state/secret left (`:1792`).
- CLI expectation that a stopped detached child dies within 20s:
  `test_decision_monitor_cli.py:453`; `--no-open` and token redaction contracts at `:394-456`,
  `:530`.
- `status`/`stop` are separate read-only/stop paths and must not inherit replacement
  (`mw.py:5301-5349`, `:5648-5748`; AC-008).

### 7. Minimal viable implementation shape (recommendation, not written)

1. `decision_monitor.ensure_instance(..., replace_incompatible: bool = False)`:
   keep the current refusal when the flag is off; `mw.py:_monitor_open` passes `True`
   (`mw.py:5576-5578`). Leave `serve`, `_monitor_stop`, `_monitor_status`,
   `_monitor_read_recorded` untouched.
2. In the existing `liveness == "alive" and not compatible` branch (`:2710-2722`), replace
   the raise with (all inside the held `StartLockGuard`):
   a. `token = read_secret(root)`; `None` -> `instance-unknown` (no request).
   b. re-read state + secret; require the same `instance_id` and the same token; else
      `instance-unknown`.
   c. `data = health(identity.port, token)`; require `data is not None and
      identity_matches(data, identity)`; else `instance-unresponsive` (zero stop calls).
   d. `stop = AttachedInstance(root, identity, token, deps).stop()`; require
      `stop["stopped"] is True and stop["detail"] is None and stop["port_probe"] ==
      "refused" and stop["state"] == "absent"`; else `stop-failed`/`instance-unknown` with
      `details={"stop": stop}` and no start. Variant: accept `state="retained"` only after
      `_identity_liveness(identity)` returns `dead`, then route through `recover_stale`.
   e. `report = recover_stale(root, guard=guard, ...)` (state absent -> orphan-secret only),
      then the existing `start` + `wait_health` (`:2769-2793`).
   f. attach `replacement = {"instance_id","pid","port","stop": stop}` to the returned
      instance; keep `recovery` for the stale-only report. Never unlink old files here.
3. Error kinds: keep `incompatible-instance` for project mismatch and for the flag-off
   refusal; use the existing `instance-unresponsive`, `stop-failed` (already used by the CLI,
   `mw.py:5717`), `instance-unknown`, `health-failed`; no new kind is required. Update the
   kind list in the module docstring (`:44-46`).
4. Test seam: factor the body of `AttachedInstance.stop` into a module-level
   `stop_instance(identity, token, control_root, *, request=_post_json,
   probe=probe_recorded_port, sleep=time.sleep, clock=time.monotonic,
   read_state_fn=read_state)` and delegate; add pass-through injections on
   `ensure_instance` (`stop_request=`/`stop_probe=`). Defaults must reproduce current
   behavior exactly (call site `mw.py:5713`).
5. Output: `_monitor_open` should report a third mode (`replaced`) plus the replacement
   report, redact nothing new (no tokens in the stop result), and only open the window after
   `ensure_instance` returns (already the case, `mw.py:5598-5619`).
6. Optional and goal-relevant: fold the dashboard asset bytes into `code_fingerprint`
   (`sha256(module bytes + asset names/bytes)[:16]`) so an asset-only edit also triggers one
   replacement. Keep the single existing field so `identity_matches`/state schema stay
   unchanged; expect one restart after deploy.

### 8. Test plan (describe-only; nothing executed)

- Fake-clock/fake-request unit tests around the new seam: success call order
  `health -> shutdown -> probe(refused) -> state read -> start`, exactly one start and one
  shutdown; replacement report fields present; no state/secret unlink by the caller.
- Failure matrix, each asserting zero start and byte-identical state/secret:
  missing secret; health `None`; identity mismatch; secret changed between read and stop;
  shutdown 401/refused; accepted request but probe stays `connected`/`unknown`;
  `stopped=True` with non-empty `detail`; `state="retained"`/`"foreign"`; liveness `unknown`.
- Concurrency: hold the start lock (pattern `test_decision_monitor.py:1573`) and assert the
  second open gets `start-lock-conflict` with no additional start; after release, reuse of the
  single replacement.
- Integration with a *fake old instance* (no production seams needed): a threaded loopback
  HTTP server publishes a state/secret whose identity is this test PID + real
  `process_start_ms` + old `code_fingerprint`/`protocol_version`, implements token-gated
  `GET /api/health` (returns that identity) and `POST /api/shutdown` (200, then closes its
  listener and removes its own state/secret). Then `ensure_instance(..., replace_incompatible
  =True, starter=in-process starter)` must close the old server, start one healthy instance,
  leave no old files, and keep history/submission bytes unchanged; the wrong-token variant
  must leave the fake serving and start nothing.
- CLI-level: `--no-open` replacement opens zero windows; normal replacement opens exactly one
  (stub browser already exists, `test_decision_monitor_cli.py:394-456`); JSON contains
  `replacement`, no token in stdout/stderr/log.
- Preservation: hash the project's history/submission files plus
  `.mw/decide-monitor.{json,secret}` before/after; only lifecycle files may change, and any
  `.stale-*` copy must be byte-identical to the original.
- No-kill assertion: spy `os.kill`/`subprocess.*` on the replacement path and require zero
  calls.

### 9. AC001-008 mapping (what each AC needs from the lifecycle design)

| AC | Lifecycle requirement | Source anchor / plan |
|---|---|---|
| AC-001 no instance | unchanged: state absent -> orphan-secret recovery -> start -> health wait; one starter call | decision_monitor.py:2760-2793 |
| AC-002 compatible reuse | health + identity_matches -> AttachedInstance, zero stop/start | :2723-2732; existing test test_decision_monitor.py:1548 |
| AC-003 incompatible same project | project check -> authenticated health -> stop gate (accepted + refused + absent) -> stale recovery -> exactly one start -> window only after return | :2700, :2701-2722, :2539-2610, :2769-2793; mw.py:5598+ |
| AC-004 identity/auth mismatch | project mismatch raises before any HTTP; health None/identity mismatch raises before shutdown; missing secret raises before shutdown | :2700, :738-752, :2723-2742; test plan T2/T12 |
| AC-005 stop failure/timeout/unresponsive | any non-accepted or unconfirmed stop -> error, no start, files untouched (the caller never unlinks and recover_stale is not reached) | :2565-2610; test plan T3/T4/T5 |
| AC-006 concurrent opens | start lock held across verify/stop/start; acquisition capped ~0.248s -> second open start-lock-conflict; one publisher per state | :2688, :826-887, mw_common.py:2388-2425, :2334-2375; test plan T7 |
| AC-007 --no-open + history bytes | window branch skipped on flag; lifecycle only touches .mw/decide-monitor.{json,secret}/lock/stale renames; history and submissions are read/written by other paths | mw.py:5598+; :440-445, :753-766; test plan T9/T10 |
| AC-008 status/stop unchanged | do not modify _monitor_read_recorded/_monitor_status/_monitor_stop; they stay read-only/stop-only | mw.py:5301-5746; test plan T9 |

AC-003 confirmed exit is implemented as confirmed listener closure plus own-state removal (see section 3); the process-death nuance is a PM decision documented in the residual section.

## 残留与未验证

- No live service, browser, model, build, install or commit was performed. All conclusions
  are source-derived; request/response timing is unmeasured.
- The build actually running on the user's machine is unknown. An older monitor without
  `/api/health` or `/api/shutdown` yields `instance-unresponsive`/`stop-failed` and no
  replacement (safe but inert); no backward-compatibility evidence exists for pre-T08 builds.
- A non-1 `schema` (future bump) or malformed state is `instance-unknown` before the
  replacement decision (`:478-495`); auto-restart across a schema change would need an
  explicit tolerant-parse + authenticate decision.
- Asset-fingerprint staleness (§1) is source-derived, not reproduced against a running
  instance.
- "Confirmed exit" is confirmed *listener closure + own-state removal*; `AttachedInstance.stop`
  does not prove PID death. A mandatory PID-exit gate would break in-process callers
  (`ensure_instance` in tests, e.g. `test_decision_monitor.py:1792`) whose PID is the test
  process. Recommendation: record post-stop liveness in the replacement report; gate on it
  only if the PM requires literal process exit. The CLI test (`test_decision_monitor_cli.py:
  453`) shows expedited death for the detached child, but this was not re-measured.
- Worst-case timing under the lock: stop request 5s + 10s probe loop + 2s state poll ~= 17s,
  plus 5s health wait for the new instance (`:96`, `:2560`, `:2582`, `:2620`). Concurrent
  opens deterministically fail `start-lock-conflict` within ~0.25s; a waiting UX is not
  implemented or measured.
- Windows specifics: immediate re-bind of the just-closed port (TIME_WAIT/exclusive-address)
  and availability of `pid_start_ms` across integrity levels are unverified; the candidate
  fallback and `unknown` liveness are the source-level mitigations
  (`:665-732`, `mw_common.py:2725-2775`).
- `_recover_stale_locked`'s state-`None` branch can move a fresh secret published by a
  non-locking `serve()` caller in a narrow window; inherited from the current recovery
  discipline, not introduced here.
- A file edit between the CLI's import and the child's import could make the new instance
  look incompatible on the next open (fingerprint is import-time); harmless extra restart,
  unobserved.
- Test seam shape (`stop_instance(...)` vs keyword params on `AttachedInstance.stop`) depends
  on PM file ownership; both preserve behavior, but the exact signature is not decided here.

## 上下文来源

- `packages/multi-workers/decision_monitor.py` (full read, 2938 lines): constants `:84-104`,
  assets `:171-194`, fingerprint `:416-424`, identity `:448-519`, state/secret `:540-615`,
  tokens `:617-655`, listeners `:665-732`, project match `:738-752`, move-aside `:753-766`,
  guard/lock `:786-895`, connect classification/probe `:916-960`, liveness `:985-1012`,
  recovery `:1015-1190`, health/identity/wait `:1196-1260`, routes/role/origin `:1480-1660`,
  shutdown handler `:1728-1732`, `MonitorInstance` `:2301-2504`, `AttachedInstance`
  `:2508-2610`, `_post_json` `:2613-2646`, `ensure_instance` `:2663-2793`, `serve` `:2796-2812`,
  window primitives `:2815+`.
- `packages/multi-workers/mw.py`: monitor constants/argv `:5190-5215`, `_SpawnedMonitorInstance`
  `:5218-5255`, error mapping `:5262-5299`, `_monitor_read_recorded` `:5301-5349`,
  identity payload `:5352-5368`, window redaction `:5371-5415`, publication wait
  `:5472-5528`, `_start_monitor_child` `:5530-5564`, `_monitor_open` `:5565-5645`,
  `_monitor_status` `:5648-5705`, `_monitor_stop` `:5708-5746`, starter entry `:5799-5828`.
- `packages/multi-workers/mw_common.py`: `acquire_lock` `:2388-2425`, tri-state liveness
  `:2654-2668`, `process_start_ms` `:2725-2775`, lock owner record/lookup `:2795-2915`.
- Existing tests: `packages/multi-workers/test_decision_monitor.py:73-266` (fixtures),
  `:1548`, `:1573`, `:1738`, `:1775`, `:1792`, `:1808`, `:1829`, `:1858`, `:1886`;
  `packages/multi-workers/test_decision_monitor_cli.py:272-456`.
- Spec/requirements: `.agenticdoc/mw-monitor-auto-restart/spec.md` (§1-§4, AC-001..008);
  `.agenticdoc/goal.md`; task card `tasks/RQ1-lifecycle.md`.
- Prior related notes (not re-derived): `.agenticdoc/mw-decision-dashboard/evidence/runs/
  T10-monitor-service/verify-summary.md:72-104`;
  `.agenticdoc/mw-decision-dashboard/workers/dd-review-monitor/report.md:88`;
  sibling research `.agenticdoc/mw-monitor-auto-restart/evidence/research/
  spec-cli-20261024.md` (CLI starter/publication focus; this file does not duplicate it).
