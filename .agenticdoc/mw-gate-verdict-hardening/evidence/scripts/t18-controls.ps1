# T-18 non-hollow controls (A-F): mutate each guarantee and prove the named test
# goes red. Byte-safe UTF-8 IO (the Python sources carry Chinese comments).
$ErrorActionPreference = "Continue"
$repo = "H:/git/Multi-Workers"
$pkg = Join-Path $repo "packages/multi-workers"
$utf8 = New-Object System.Text.UTF8Encoding($false)

function ReadText([string] $p) { [System.IO.File]::ReadAllText($p, $utf8) }
function WriteText([string] $p, [string] $t) { [System.IO.File]::WriteAllText($p, $t, $utf8) }

function RunTest([string] $label, [string] $nodeId) {
	Push-Location $pkg
	try {
		$out = (python -X utf8 -m pytest $nodeId -q -p no:randomly 2>&1 | Out-String)
		$line = ([regex]::Match($out, "\d+ (failed|passed|error)[^\r\n]*")).Value
		if (-not $line) { $line = ($out -split "`n" | Select-Object -Last 3) -join " " }
		"$label -> [$($line.Trim())]"
	} finally { Pop-Location }
}

function Mutate([string] $file, [string] $needle, [string] $replacement, [string] $label) {
	$t = ReadText $file
	if (-not $t.Contains($needle)) { throw "needle not found for $label" }
	WriteText $file $t.Replace($needle, $replacement)
}

$launcher = Join-Path $pkg "launcher.py"
$common = Join-Path $pkg "mw_common.py"
$launcherBak = "$launcher.t18bak"
$commonBak = "$common.t18bak"
Copy-Item $launcher $launcherBak -Force
Copy-Item $common $commonBak -Force

try {
	# A: the cap resolution falls back to "effectively unbounded" (the IN-3 shape).
	Mutate $launcher 'limit = max_workers if max_workers is not None else mw_common.launcher_max_workers(project_dir)' 'limit = max_workers or 10**9' "A"
	RunTest "CONTROL A (max_workers=None unbounded again)" "test_launcher.py::TestLauncherMaxWorkersBound::test_default_max_workers_is_eight_not_unbounded"
	Copy-Item $launcherBak $launcher -Force

	# B: the burst-shape criterion disappears.
	Mutate $common 'if rows_total > alarm_delta and non_terminal_count / rows_total > 0.9:' 'if False:' "B"
	RunTest "CONTROL B (queue-burst-shape criterion removed)" "test_worker_queue_python_integrity.py::test_doctor_burst_shape_flags_the_in3_fingerprint"
	Copy-Item $commonBak $common -Force

	# C: an unreadable ack row is treated as an acknowledgement (skip everything).
	$cNeedle = "if len(parts) != 2:`n            continue"
	$cReplacement = "if len(parts) != 2:`n            acked[raw.strip()] = `"`"`n            continue"
	Mutate $common $cNeedle $cReplacement "C"
	RunTest "CONTROL C (acked parse failure treated as acked)" "test_launcher.py::TestLauncherAckConvergence::test_acked_parse_failure_does_not_skip"
	Copy-Item $commonBak $common -Force

	# D: update_status rewrites from the parsed view again (the IN-3 amplifier F4).
	$dNeedle = "            if row is not None and row[`"task_key`"] == task_key:`n                row[`"status`"] = status`n                row[`"updated_at`"] = updated_at`n                out.append(serialize_entry(row))`n                found = True`n            else:`n                out.append(line)"
	$dReplacement = "            if row is None:`n                continue`n            if row[`"task_key`"] == task_key:`n                row[`"status`"] = status`n                row[`"updated_at`"] = updated_at`n                found = True`n            out.append(serialize_entry(row))"
	Mutate $common $dNeedle $dReplacement "D"
	RunTest "CONTROL D (update_status drops unparsable rows)" "test_worker_queue_python_integrity.py::test_update_status_preserves_unparsable_rows"
	Copy-Item $commonBak $common -Force

	# E: the width check becomes an equality test, so 8-column rows stop parsing.
	Mutate $common 'if len(parts) < WORKER_COLS_MIN or len(parts) > WORKER_COLS_MAX:' 'if len(parts) not in (WORKER_COLS_MIN, WORKER_COLS_MAX):' "E"
	RunTest "CONTROL E (8-column rows unreadable)" "test_worker_queue_python_integrity.py::test_parse_workers_queue_counts_rows_and_unparsable_slots"
	Copy-Item $commonBak $common -Force

	# F: the unparsable-row doctor criterion disappears.
	Mutate $common 'if unparsable_count:' 'if False:' "F"
	RunTest "CONTROL F (queue-rows-unparsable criterion removed)" "test_worker_queue_python_integrity.py::test_doctor_flags_unparsable_rows"
} finally {
	Copy-Item $launcherBak $launcher -Force
	Copy-Item $commonBak $common -Force
	Remove-Item $launcherBak -Force
	Remove-Item $commonBak -Force
	"restored: " + ((ReadText $common).Contains('if rows_total > alarm_delta and non_terminal_count / rows_total > 0.9:'))
}
