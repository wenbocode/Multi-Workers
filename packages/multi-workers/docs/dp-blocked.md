# Trace a blocked DP attempt

The control project stores one receipt per recorded block in
`.agenticdoc/_autopilot/dp-blocked/<event_id>.json`. Look up the exact receipt
using `blocked_event_id` from the CLI JSON or the `ask_decision` tool details.
Autopilot gate receipts can be filtered by `gate_id` or `key`.

The receipt includes the UTC time, DP, source, stage, short reason and any
available task, decision or matter identifiers. Repeated blocks have distinct
event IDs. If the tool receives a receipt ID from its MW child, it uses that ID
for the initial call. A later blocked replay gets its own receipt.

From the control project root, list the latest blocks in PowerShell.

```powershell
Get-ChildItem .agenticdoc/_autopilot/dp-blocked -Filter '*.json' |
    ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json } |
    Sort-Object ts -Descending |
    Select-Object -First 20 ts, dp, key, stage, reason, detail, event_id
```
