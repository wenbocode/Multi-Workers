# T06 read-only check sub-steps (no --write, no full `npm run check`).
# Usage: pwsh -File check-steps-readonly.ps1
# Writes one log with command, exit code, stdout+stderr per step.
$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $here "check-steps-readonly.txt"
Set-Location "H:/git/Multi-Workers"
"# T06 read-only check sub-steps" | Out-File -Encoding utf8 $log
"# repo root: $(Get-Location)" | Out-File -Encoding utf8 -Append $log
"# note: full 'npm run check' was NOT run (it invokes 'biome check --write'); these steps are not equivalent to it." | Out-File -Encoding utf8 -Append $log

$steps = @(
    @{ name = "biome check (read-only, no --write)"; cmd = "npx biome check ." },
    @{ name = "npm run check:pinned-deps"; cmd = "npm run check:pinned-deps" },
    @{ name = "npm run check:ts-imports"; cmd = "npm run check:ts-imports" },
    @{ name = "npm run check:shrinkwrap"; cmd = "npm run check:shrinkwrap" },
    @{ name = "npm run check:install-lock:coding-agent"; cmd = "npm run check:install-lock:coding-agent" },
    @{ name = "tsgo --noEmit"; cmd = "npx tsgo --noEmit" },
    @{ name = "npm run check:browser-smoke"; cmd = "npm run check:browser-smoke" }
)

foreach ($step in $steps) {
    "" | Out-File -Encoding utf8 -Append $log
    "=== $($step.name) ===" | Out-File -Encoding utf8 -Append $log
    "CMD: $($step.cmd)" | Out-File -Encoding utf8 -Append $log
    $output = & cmd /c "$($step.cmd) 2>&1" | Out-String
    $code = $LASTEXITCODE
    $output | Out-File -Encoding utf8 -Append $log
    "EXIT: $code" | Out-File -Encoding utf8 -Append $log
}

"" | Out-File -Encoding utf8 -Append $log
"# files changed by this task (hashes):" | Out-File -Encoding utf8 -Append $log
foreach ($path in @("packages/multi-workers/decision_playground.py", "packages/multi-workers/test_decision_playground.py")) {
    $hash = (Get-FileHash -Algorithm SHA256 -Path $path).Hash.ToLower()
    "$path sha256=$hash bytes=$((Get-Item $path).Length)" | Out-File -Encoding utf8 -Append $log
}
"" | Out-File -Encoding utf8 -Append $log
"# git status (own paths only):" | Out-File -Encoding utf8 -Append $log
(git status --short packages/multi-workers/decision_playground.py packages/multi-workers/test_decision_playground.py .agenticdoc/mw-decision-dashboard/evidence/runs/T06-playground .agenticdoc/mw-decision-dashboard/workers/dd-playground 2>&1) | Out-File -Encoding utf8 -Append $log
"# git status (shared dependency files, must show only pre-existing other-session diffs):" | Out-File -Encoding utf8 -Append $log
(git status --short packages/multi-workers/decision_book.py packages/multi-workers/decision_points.py packages/multi-workers/decision_monitor.py packages/multi-workers/decision_wire.py packages/multi-workers/decision.py 2>&1) | Out-File -Encoding utf8 -Append $log
Get-Content $log | Select-Object -Last 20
