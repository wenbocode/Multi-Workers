# T11b interpretation and deviation notes

Delivered source never modified by the RED plugin; all four RED runs patch the
pre-card behaviour in memory for that single pytest run.

## 1. Tab switch reads nothing (explicit load click)

The card says "切页加载仅元数据和记录". The pre-existing T11a asset contract
(which this card may not edit: write face forbids existing tests) asserts that
switching to the DP tab performs **zero** fetches and has no form/input/submit
button. Both cannot hold literally.

Resolution: switching the tab only shows the panel; a labelled
`加载 DP 契约与测试记录（只读元数据）` button performs the two read-only GETs
(`/api/dps`, `/api/test/history`). The load reads metadata + records only: no
validate, no credential use, no model call. The panel contains no `<form>`, no
`<input>` and no `type="submit"` button (all controls are `<select>`,
`<textarea>` and `type="button"`), so the T11a scenario stays truthful and its
9 history scenarios keep passing.

The phrase "待接入" that T11a asserted is kept only where it is factually true:
the boundary note says real-browser visible acceptance and real-Jev end-to-end
acceptance are still 待接入 (not authorized) - the DP submit path itself is
delivered.

## 2. Where the default provider is installed

`MonitorDeps.resolve_playground(control_root)` is the lazy, per-root,
create-once resolver; `resolve_redactor(control_root)` does the same for the
response redactor (a playground response that cannot be made safe is never
served). `default_monitor_deps()` installs both factories and is used by
the **command entry points** `serve()` (the detached child) and
`ensure_instance()` (the CLI's attach/start path). A bare `MonitorDeps()` or a
directly constructed `MonitorInstance(deps=None)` keeps `playground=None` (503),
because the pre-existing T10 monitor tests
(`test_playground_routes_are_unavailable_without_a_provider` and the health
test) lock that contract and this card may not edit them. The real
`mw decide monitor` path therefore has a working DP provider; the test surface
that constructs an instance directly keeps the explicit-injection contract.

First-use cost: the redactor factory resolves the root's credential once
(`credential_snapshot` + `credential_redactor`); nothing is read at import, on
`/api/health`, on `/api/dps`, or on production history reads. The production
history fold keeps its pre-existing fail-closed behaviour (`deps.redactor` is
still the caller's obligation there; wiring history redaction through the CLI is
T08a/T10 debt, not changed by this card).

## 3. Credential discovery budget unchanged (T05l)

Each explicit `validate`/`submit` is one credential unit. With a cfg/extras key
the frozen known set pays exactly one legacy-leg read (T05l, `decision.py`, off
this card's write face). No discovery happens at import, on `/api/dps`, on
`/api/health`, on production history reads, or on opening/switching the page. The
command-path default redactor is built on the **first** DP-test route only (one
read per control root, then cached). The new tests lock this: 0 discoveries for
registry/scaffold/history, 1 per explicit validate unit, 1 for the lazy default
redactor.

## 4. Answer persistence boundary

The wire `submission-end` schema is closed (`decision_wire.py` is off-face) and
has no answer field. The result projection is therefore written by the
playground at the same point as `submission-end`, one file per submission:
`.mw/decide-test/submission-results/<submit_id>.json`, containing only the safe
projection (redacted with the submission's frozen known-secret + capture
redactors, then hash-sealed). No raw request/response body, no credential, no
book text is copied. Reading it back is hash-verified; a mismatch is treated as
missing, never guessed.

Raw request/response bodies are shown in the submission detail by *reading* the
existing test wire ledger (attempt-start/attempt-end captures) - the same
single-writer store, no duplicate index. The history list view omits the bodies
(`output_omitted:true`) so one page stays bounded.

## 5. Not claimed

- Real visible browser acceptance and a real Jev call were NOT executed (not
  authorized). The DOM run is a Node shim replay of real monitor JSON; the model
  endpoint is a local loopback HTTP fixture driven by the real
  `TimiDecisionsBackend` (not a scripted provider).
- No full `npm run check` (it would rewrite other sessions' files); only the
  read-only substeps in `readonly-checks.log`.
- No commit was made.
