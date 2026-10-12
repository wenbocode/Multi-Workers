"""Rewrite the mw-gate-verdict-hardening CHANGELOG entries in English (file convention)."""

import pathlib

MW = pathlib.Path("packages/multi-workers/CHANGELOG.md")
CA = pathlib.Path("packages/coding-agent/CHANGELOG.md")

MAP = {
    # --- multi-workers ---
    "abort fingerprint": "- Added the `l3-aborted` abort fingerprint (mw-gate-verdict-hardening): an L3 round whose worker stream aborted (an abort marker in `worker.log` with no qualifying verdict source) is no longer conflated with \"no verdict\" — it emits an `l3-aborted` timeline event, retries inside a dedicated bounded budget (`loop=\"l3abort:<key>\"`), and marks the gate stalled with `reason_code=\"l3-aborted\"` once that budget is exhausted.",
    "pending-gate proactive reminder": "- Added the pending-gate proactive reminder (mw-gate-verdict-hardening): the conductor checks answer-pending gates on every tick and reminds at most twice per gate (`gate_reminder_after_min` / `gate_reminder_max`), writing a `phase:\"remind\"` ledger row plus a `gate-reminder` timeline event; the PM side de-duplicates on a `seq` watermark before surfacing it to the human.",
    "G3 gate authorization scope": "- Added the G3 gate authorization scope (mw-gate-verdict-hardening): gate frontmatter accepts an optional `authorizes` field (closed set `{retry, contract-change}`); `advance *->done` runs a mechanical AC/VC text-identity check (`contract_guard.py`, anchored by the content-addressed `<key>/evidence/contract-freeze.json`), and an unauthorized rewrite emits a `contract-refused` event plus a `contract-unauthorized` stall. The conductor establishes the anchor idempotently at the `design`/`plan` acceptance boundaries, `mw autopilot contract-freeze` adds or explicitly force-refreshes it, and `mw autopilot contract-guard` plus `mw doctor` expose the read-only verdict.",
    "queue integrity (G5)": "- Added queue integrity (mw-gate-verdict-hardening): `_workers.parallel` accepts an optional `# mw-queue:v2` header; unknown row widths are no longer dropped silently (7..9 columns are all readable), the read side counts unparsable rows and preserves them verbatim on write-back, every Python and TS queue writer now rewrites only its own row, dispatch is suppressed while unparsable rows exist, and `mw doctor` gained the stateless `queue-rows-unparsable` / `queue-burst-shape` / `run-ledger-conflict` criteria.",
    "launcher bounded spawn": "- Added launcher bounded spawn (mw-gate-verdict-hardening): `launcher_max_workers` (default 8, 1..64) caps concurrent spawns per pass, and queue rebuilds skip already-acked terminal tasks.",
    "dispatch isolation and run identity": "- Added dispatch isolation and run identity (mw-gate-verdict-hardening): PM-side auto-dispatch is scoped to the watching window's key plus `_scratch` (the `mw` CLI stays global) and skipped keys are aggregated into an `out-of-scope` alarm; workers write their own `<task_dir>/run.json` identity (`run_id`/`owner_key`/`pid`/heartbeat/terminal state) and the launcher only adds `lost` instead of writing terminal states; a `task_key` is never re-run (extensions use a new key plus `supersedes`); `dispatch_max_per_scan` (default 3) caps a single scan.",
    "six autopilot config keys": "- Added six autopilot config keys (mw-gate-verdict-hardening): `DEFAULT_CONFIG` 14 -> 20 with `launcher_max_workers`, `dispatch_max_per_scan`, `queue_alarm_delta`, `l3_abort_retry_limit`, `gate_reminder_after_min` and `gate_reminder_max`.",
    "autopilot config key count from 14 to 20": "- Changed the autopilot config key count from 14 to 20 (mw-gate-verdict-hardening): the six keys above, all range-validated and covered by the 73-case frozen corpus.",
    "Fixed 闸门可静默": "- Fixed silent gates (mw-gate-verdict-hardening): an answer-pending gate could sit unanswered for weeks with no reminder.",
    "Fixed L3 流中止": "- Fixed the L3 stream-abort misclassification (mw-gate-verdict-hardening): an aborted stream was treated as a candidate verdict source instead of \"no verdict\".",
    "Fixed gate 自由文本": "- Fixed free-text gate notes being read as authorization (mw-gate-verdict-hardening): a prose `note` can no longer authorize an AC/VC rewrite.",
    "Fixed 队列行被静默丢弃": "- Fixed silent queue-row drops rebuilding the whole project queue (mw-gate-verdict-hardening): the reader dropped 9-column rows and the whole-file rewrite then deleted them, re-dispatching 250 stale rows.",
    # --- coding-agent ---
    "panel frame self-proof and degraded frames": "- Added panel frame self-proof and degraded frames (mw-gate-verdict-hardening): the `/autopilot monitor` panel stamps every frame with an absolute collection time and tick count, warns with `STALE PANEL (...)` after 3 refresh cycles without progress, replaces a read failure with a degraded frame carrying the error summary instead of silently dropping the frame, and follows data-surface changes within 2 refresh cycles.",
    "the panel not lying before a human answers": "- Added the panel not lying before a human answers (mw-gate-verdict-hardening): a pinned `BLOCKED_ON_HUMAN` line (non-terminal worker count plus the oldest gate age) and a coarse `age=` on gate rows.",
    "--authorizes": "- Added `/autopilot gate <id> approve|reject --authorizes <a,b>` (mw-gate-verdict-hardening): records the action types an answer authorizes in the gate file under the closed set `{retry, contract-change}` (out-of-set values fail closed, and a gate file without an `authorizes:` line is refused with a hint).",
    "panel re-arm after": "- Added panel re-arm after `/new` and `/resume` (mw-gate-verdict-hardening): `autoStartMonitor` stops and restarts the monitor when its context changes, fixing a panel that never came back.",
    "cross-key read-only": "- Added cross-key read-only enforcement (mw-gate-verdict-hardening): `dispatch_worker` (explicit `key`) and `advance_phase` refuse another window's live-held key with `[cross-key-read-only]` before any side effect, while the read surface (`list_tasks` with `scope:\"all\"/\"key\"`, `mw_status`, `mw doctor`, the monitor panel) stays globally readable.",
    "row-shape recognition": "- Added `worker-store` row-shape recognition (mw-gate-verdict-hardening): 7..9 columns are all readable, unparsable rows are counted and alarmed instead of dropped, write-back preserves them, and new queues carry a `# mw-queue:v2` header.",
    "extension-side config key count from 14 to 20": "- Changed the extension-side config key count from 14 to 20 (mw-gate-verdict-hardening): the six keys above, all range-validated and covered by the 73-case frozen corpus.",
    "Fixed `/mw restart`": "- Fixed the monitor panel freezing on a stale frame after `/mw restart` (mw-gate-verdict-hardening): it showed the new PID, reported no error, and never attested its own staleness.",
    "Fixed `/new`": "- Fixed the `/autopilot monitor` panel disappearing for good after `/new` and `/resume` (mw-gate-verdict-hardening).",
    "Fixed 队列行被静默丢弃": "- Fixed silent queue-row drops rebuilding the whole project queue (mw-gate-verdict-hardening): the reader dropped 9-column rows and the whole-file rewrite then deleted them, re-dispatching 250 stale rows.",
}


def rewrite(path, label):
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    hits = [i for i, l in enumerate(lines) if "mw-gate-verdict-hardening" in l]
    used = set()
    for i in hits:
        line = lines[i]
        for key, replacement in MAP.items():
            if key in line:
                newline = "\n" if line.endswith("\n") else ""
                lines[i] = replacement + newline
                used.add(key)
                break
        else:
            print(f"  !! UNMATCHED in {label}: {line[:90]}")
    path.write_text("".join(lines), encoding="utf-8", newline="\n")
    print(f"{label}: {len(hits)} lines, {len(used)} mappings used")


rewrite(MW, "multi-workers")
rewrite(CA, "coding-agent")
