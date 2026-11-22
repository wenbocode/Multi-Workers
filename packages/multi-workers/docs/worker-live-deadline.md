# Worker deadline extensions

An operator can authorize a PM to extend a running Worker within a preallocated time and execution budget. The Worker reads the authorization at startup. The original `timeout` remains the initial deadline, bounded by the authorization and any fixed allocation.

## Provision the allowance

Use the same user account and control project as the PM and launcher. Inside that project's private MW PM channel directory, place an operator-authored file at `worker-deadlines/<key>/<task_key>.json`. The channel directory is `~/.mw-pm-channel/<project-hash>`. Its hash is SHA-256 of the real absolute control project path, lowercased on Windows. Keep it outside Worker write access.

For example, a Worker with a ten-minute initial timeout can use the following allowance. Set the card pin to the dispatched card's EOL-normalized SHA-256 and set `expires_at` to the intended future authorization expiry in Unix milliseconds.

```json
{
  "card_sha256": "<64 lowercase hexadecimal characters>",
  "expires_at": 1795331700000,
  "review_after_ms": 480000,
  "max_run_ms": 960000,
  "max_extension_ms": 180000,
  "max_total_extension_ms": 360000,
  "max_approvals": 2,
  "max_steps": 20,
  "max_cost": 20,
  "no_progress_limit": 6
}
```

One admitted tool call uses one step and one cost unit. The no-progress count tracks tool completions without new verified milestone evidence. A fixed allocation can further reduce the deadline and execution allowance. An approval spends only the available extension time.

## Review and approve

The owning PM gets a reminder at the configured review time when the run is still eligible. Use `read_worker_progress` for the current deadline version, reported milestones, measured tool activity and remaining allowance. Use `extend_worker_deadline` with the exact run ID and version, a unique request ID, a bounded new deadline, the next review time, the reason and the remaining work. The time fields take Unix milliseconds.

The host verifies a current PM claim and fresh evidence with at least one verifiable completed acceptance item. Additional approvals require new evidence. Approved extensions apply to the same run. The hard cutoff stops new work and ends in-flight managed tools.

Replace the active policy atomically with the same fields plus `"cancelled": true` to explicitly cancel the run. Removing or changing the active policy revokes its authorization. An already effective cancellation, an exhausted allowance or the hard cutoff blocks additional work. The recorder retains the approval history for audit.
