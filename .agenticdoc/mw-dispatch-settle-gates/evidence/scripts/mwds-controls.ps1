# T-12 (mw-dispatch-settle-gates) consolidated non-hollow controls (A/B/C).
#
# Merges the A (remove the criterion) / B (invert the default) / C (remove the
# whitelist or guardrail) controls each of T-01…T-10 documented in its report,
# plus two cross-card seam controls: every group must drive at least one NAMED
# test red, then restore the file byte-identically and re-run it green.
#
# Protocol per control: baseline sha256 -> backup -> minimal inverse edit ->
# named test must be RED -> restore from the backup -> sha256 must equal the
# baseline -> the same named test must be GREEN. Byte-safe UTF-8 IO (the TS
# sources carry Chinese text; the Python sources carry Chinese comments).
#
# Usage:  pwsh -NoProfile -File .agenticdoc/mw-dispatch-settle-gates/evidence/scripts/mwds-controls.ps1
# No build, no commit, no process restart; every mutation is restored.
#
# Optional regression comparison (reverse case c):
#   ... -RegressionFinal <log> -RegressionBaseline <log>
# Compares the `FAILED <nodeid>` set of the final Python log against a baseline
# log and asserts the final set is a subset (new_reds = 0). When no baseline log
# is given, the two reds recorded by the previous key/T-10 are used.

param(
	[string] $RegressionFinal = "",
	[string] $RegressionBaseline = ""
)

$ErrorActionPreference = "Continue"
$repo = "H:/git/Multi-Workers"
$mw = Join-Path $repo "packages/multi-workers"
$ca = Join-Path $repo "packages/coding-agent"
$utf8 = New-Object System.Text.UTF8Encoding($false)

function ReadText([string] $p) { [System.IO.File]::ReadAllText($p, $utf8) }
function WriteText([string] $p, [string] $t) { [System.IO.File]::WriteAllText($p, $t, $utf8) }
function Sha([string] $p) { (Get-FileHash -Algorithm SHA256 $p).Hash.ToLower() }

function RunTs([string] $file, [string] $name) {
	Push-Location $ca
	try {
		$out = (node ../../node_modules/vitest/dist/cli.js --run $file -t $name 2>&1 | Out-String)
		$code = $LASTEXITCODE
	} finally { Pop-Location }
	$m = [regex]::Match($out, "Tests +\d+ (failed|passed)[^\r\n]*")
	return @{ code = $code; summary = $(if ($m.Success) { $m.Value.Trim() } else { "no summary" }) }
}

function RunPy([string] $nodeId) {
	Push-Location $mw
	try {
		$out = (python -X utf8 -m pytest $nodeId -q -p no:randomly 2>&1 | Out-String)
		$code = $LASTEXITCODE
	} finally { Pop-Location }
	$m = [regex]::Match($out, "\d+ (failed|passed|error)[^\r\n]*")
	return @{ code = $code; summary = $(if ($m.Success) { $m.Value.Trim() } else { "no summary" }) }
}

# Runs one control. `$Patterns`/`$Replacements` are applied in order with a
# match evaluator, so replacement strings are literal (no `$` escaping).
function Control {
	param(
		[string] $Id,
		[string] $Kind,
		[string] $File,
		[string[]] $Patterns,
		[string[]] $Replacements,
		[scriptblock] $Runner
	)
	$bak = "$File.t12bak"
	$base = Sha $File
	Copy-Item $File $bak -Force
	$red = $null; $green = $null; $shaOk = $false; $note = ""
	try {
		$t = ReadText $File
		for ($i = 0; $i -lt $Patterns.Count; $i++) {
			$rep = $Replacements[$i]
			$new = [regex]::Replace($t, $Patterns[$i], { param($m) $rep })
			if ($new -eq $t) { throw "mutation $Id/$i matched nothing" }
			$t = $new
		}
		WriteText $File $t
		$red = & $Runner
		Copy-Item $bak $File -Force
		$shaOk = ((Sha $File) -eq $base)
		$green = & $Runner
	} catch {
		$note = "ERROR: $_"
	} finally {
		Copy-Item $bak $File -Force -ErrorAction SilentlyContinue
		Remove-Item $bak -Force -ErrorAction SilentlyContinue
	}
	$pass = ($red -ne $null) -and ($red.code -ne 0) -and ($green -ne $null) -and ($green.code -eq 0) -and $shaOk
	if ($note -ne "") { $pass = $false }
	$verdict = $(if ($pass) { "PASS" } else { "FAIL" })
	$redText = $(if ($red) { "RED [$($red.summary)]" } else { "RED [n/a]" })
	$greenText = $(if ($green) { "GREEN [$($green.summary)]" } else { "GREEN [n/a]" })
	[Console]::WriteLine("[$Id/$Kind] $([System.IO.Path]::GetFileName($File)) -> $redText ; restore_sha=$shaOk ; $greenText ; $verdict $note")
	return [pscustomobject]@{ Id = $Id; Kind = $Kind; Pass = $pass }
}

$uiBridge = Join-Path $ca "src/extensions/agent-team-loop/pm/ui-bridge.ts"
$pmOrch = Join-Path $ca "src/extensions/agent-team-loop/pm/pm-orchestrator.ts"
$deliverable = Join-Path $ca "src/extensions/agent-team-loop/shared/deliverable-evidence.ts"
$outputSections = Join-Path $ca "src/extensions/agent-team-loop/shared/output-sections.ts"
$workerMode = Join-Path $ca "src/extensions/agent-team-loop/worker/worker-mode.ts"
$outputWriter = Join-Path $ca "src/extensions/agent-team-loop/worker/output-writer.ts"
$launcher = Join-Path $mw "launcher.py"
$common = Join-Path $mw "mw_common.py"
$conductor = Join-Path $mw "autopilot/conductor.py"
$dispatchPy = Join-Path $mw "autopilot/dispatch.py"

$results = @()

# ── T-01 AC-003 /worker cross-key guard ──────────────────────────────────────
$results += Control "T-01" "A" $uiBridge @(
	'const crossKeyRefusal = foreignLiveClaimRefusal\(indexStore, ownerKey\);[\s\S]*?ctx\.ui\.notify\(crossKeyRefusal, "warning"\);\s*\n\s*return;\s*\n\s*\}'
) @('// T-01/A: /worker guard removed') { RunTs "test/suite/mwds-t01-worker-guard.test.ts" "refuses another window's live key" }

$results += Control "T-01" "B" $uiBridge @(
	'const claim = indexStore\.findByKey\(trimmed\)\?\.claimId\.trim\(\) \?\? "";'
) @('const claim = "";') { RunTs "test/suite/mwds-t01-worker-guard.test.ts" "refuses another window's live key" }

$results += Control "T-01" "C" $uiBridge @(
	'export const CROSS_KEY_READ_ONLY_SURFACES = \["dispatch_worker", "/worker", "advance_phase"\] as const;'
) @('export const CROSS_KEY_READ_ONLY_SURFACES = ["dispatch_worker", "advance_phase"] as const;') {
	RunTs "test/suite/mwds-t01-worker-guard.test.ts" "every declared surface maps to a real foreignLiveClaimRefusal call site"
}

# ── T-02 AC-005a dispatch-time write-intent ──────────────────────────────────
$results += Control "T-02" "A" $uiBridge @(
	'export function collectWriteIntentHits\(text: string\): WriteIntentHit\[\] \{\s*\n\s*const body = text'
) @("export function collectWriteIntentHits(text: string): WriteIntentHit[] {`n`treturn [];`n`tconst body = text") { RunTs "test/suite/mwds-t02-write-intent.test.ts" "the same text without the guard is refused" }

$results += Control "T-02" "B" $uiBridge @(
	'if \(!isWritelessRole\(input\.type\) \|\| isShellRole\(input\.type\)\) return \{ ok: true, hits: \[\], violations: \[\] \};'
) @('return { ok: true, hits: [], violations: [] };') { RunTs "test/suite/mwds-t02-write-intent.test.ts" "the same text without the guard is refused" }

$results += Control "T-02" "C" $uiBridge @(
	'if \(WRITE_INTENT_NEGATIONS\.some\(\(n\) => before\.includes\(n\)\)\) continue;'
) @('if (false) continue;') { RunTs "test/suite/mwds-t02-write-intent.test.ts" "each guard turns its hit into an allowed mention" }

# ── T-03 AC-005b bash write-scope guard ──────────────────────────────────────
$results += Control "T-03" "A" $workerMode @(
	'\tif \(bashWriteScopeConfig\) \{'
) @("`tif (false && bashWriteScopeConfig) {") { RunTs "test/suite/mwds-t03-bash-write-scope.test.ts" "VC-020: five deny categories block" }

$results += Control "T-03" "B" $workerMode @(
	'for \(const candidate of extractBashWriteCandidates\(command\)\) \{'
) @('const __controlB = extractBashWriteCandidates(command); if (__controlB.length === 0) return { block: true, reason: "write-scope: control B" }; for (const candidate of __controlB) {') {
	RunTs "test/suite/mwds-t03-bash-write-scope.test.ts" "own taskDir/evidence allowed"
}

$results += Control "T-03" "C" $workerMode @(
	'if \(samePath\(target, path\.join\(config\.keyDir, "pm-state\.md"\)\)\) return "pm-state\.md";'
) @('if (false) return "pm-state.md";') { RunTs "test/suite/mwds-t03-bash-write-scope.test.ts" "VC-020: five deny categories block" }

# ── T-04 AC-006 three-channel deliverable predicate ──────────────────────────
$results += Control "T-04" "A" $deliverable @(
	'export function hasDeliverableEvidence\(taskDir: string, outputText = ""\): DeliverableEvidence \{\s*\n\s*// Channel 1'
) @("export function hasDeliverableEvidence(taskDir: string, outputText = `"`"): DeliverableEvidence {`n`treturn { delivered: true, channel: `"report`", detail: `"control A`" };`n`t// Channel 1") {
	RunTs "test/suite/mwds-t04-deliverable.test.ts" "undelivered read-only settle"
}

$results += Control "T-04" "B" $deliverable @(
	'export function hasDeliverableEvidence\(taskDir: string, outputText = ""\): DeliverableEvidence \{\s*\n\s*// Channel 1'
) @("export function hasDeliverableEvidence(taskDir: string, outputText = `"`"): DeliverableEvidence {`n`treturn { delivered: false, channel: `"none`", detail: `"control B`" };`n`t// Channel 1") {
	RunTs "test/suite/mwds-t04-deliverable.test.ts" "delivered read-only settle"
}

$results += Control "T-04" "C" $pmOrch @(
	'for \(const name of \["output\.md", "report\.md", "run\.json", "trace\.log"\]\) \{'
) @('for (const name of ["report.md"]) {') { RunTs "test/suite/mwds-t04-deliverable.test.ts" "trace.log-only dir still refuses" }

# ── T-05 AC-010 read side + settle idempotence ───────────────────────────────
$results += Control "T-05" "A" $outputSections @(
	'for \(let i = blocks\.length - 1; i >= 0; i--\) \{\s*const block = blocks\[i\];\s*if \(title !== undefined && block\.title !== title\) continue;\s*if \(!isPlaceholderSection\(block\.title, block\.body\)\) return block;\s*\}'
) @('for (let i = 0; i < blocks.length; i++) { const block = blocks[i]; if (title !== undefined && block.title !== title) continue; return block; }') {
	RunTs "test/suite/mwds-t05-output-sections.test.ts" "VC-043a"
}

$results += Control "T-05" "B" $outputSections @(
	'return isPlaceholderBody\(body\);'
) @('return !isPlaceholderBody(body);') { RunTs "test/suite/mwds-t05-output-sections.test.ts" "VC-043a" }

$results += Control "T-05" "C" $workerMode @(
	'if \(taskDone\) return;\s*\n\s*taskDone = true;',
	'if \(taskDone\) return;\s*\n\t\t\tif \(!initialSettled\) \{'
) @('taskDone = true;', 'if (!initialSettled) {') { RunTs "test/suite/mwds-t05-output-sections.test.ts" "VC-045a" }

# ── T-06 AC-007 output informativeness ───────────────────────────────────────
$results += Control "T-06" "A" $outputWriter @(
	'if \(deliverables\.length > 0\) sections\.push\(',
	'\$\{deliverables\.join\("\\n"\)\}'
) @('sections.push(', '${deliverables.join("\n") || "(none)"}') { RunTs "test/suite/mwds-t06-output-informativeness.test.ts" "no artifacts has neither section" }

$results += Control "T-06" "B" $outputWriter @(
	'if \(deliverables\.length > 0\) sections\.push\('
) @('sections.push(') { RunTs "test/suite/mwds-t06-output-informativeness.test.ts" "no artifacts has neither section" }

$results += Control "T-06" "C" $workerMode @(
	'const effort = `writes=\$\{writesLabel\(\)\}`;'
) @('const effort = "";') { RunTs "test/suite/mwds-t06-output-informativeness.test.ts" "tool count and writes=" }

# ── T-07 AC-006 launcher reap product-first (python) ─────────────────────────
$results += Control "T-07" "A" $launcher @(
	'    run_status = mw_common\.read_run_status\(task_dir\)'
) @('    run_status = None') {
	RunPy "test_mwds_t07_reap_productfirst.py::TestReapStatusProductFirst::test_a_run_needs_clarification_outranks_exit_zero"
}

$results += Control "T-07" "B" $launcher @(
	'    run_status = mw_common\.read_run_status\(task_dir\)\n'
) @("    run_status = mw_common.read_run_status(task_dir)`n    if run_status is None:`n        return `"done`"`n") {
	RunPy "test_mwds_t07_reap_productfirst.py::TestReapStatusProductFirst::test_c_missing_run_json_falls_back_to_exit_code"
}

$results += Control "T-07" "C" $launcher @(
	'    if run_status != from_exit:'
) @('    if False:') {
	RunPy "test_mwds_t07_reap_productfirst.py::TestReapProductFirstEndToEnd::test_e_conflict_line_lands_in_launcher_log"
}

# ── T-08 AC-001 doctor blocked_on_human (python) ─────────────────────────────
$results += Control "T-08" "A" $common @(
	'    if int\(_doctor_queue\(project_dir\)\.get\("non_terminal_count"\) or 0\) > 0:\s*\n\s*return False\s*\n\s*return _conductor_tick_fresh\(project_dir\)'
) @('    return True') { RunPy "test_mwds_t08_doctor_blocked.py::test_c_non_terminal_row_forces_false" }

$results += Control "T-08" "B" $common @(
	'def _blocked_on_human\(project_dir: pathlib\.Path, pending_count: int\) -> bool:'
) @("def _blocked_on_human(project_dir: pathlib.Path, pending_count: int) -> bool:`n    return True") {
	RunPy "test_mwds_t08_doctor_blocked.py::test_b_false_has_no_suffix"
}

$results += Control "T-08" "C" $common @(
	'def _blocked_on_human\(project_dir: pathlib\.Path, pending_count: int\) -> bool:'
) @("def _blocked_on_human(project_dir: pathlib.Path, pending_count: int) -> bool:`n    pathlib.Path(project_dir, '.agenticdoc', '_autopilot', 'doctor-blocked-snapshot.json').write_text('{}')") {
	RunPy "test_mwds_t08_doctor_blocked.py::test_f_doctor_is_zero_write"
}

# ── T-09 AC-002 stage-terminal reminder suppression (python) ─────────────────
$results += Control "T-09" "A" $conductor @(
	'        if stage_status is not None and stage_number is not None:\s*\n\s*rank = _STAGE_STATUS_RANK\.get\(stage_status\.get\(stage_number, ""\)\)\s*\n\s*if rank is not None and rank >= _STAGE_TERMINAL_RANK:\s*\n\s*continue\s*\n'
) @('') { RunPy "test_mwds_t09_gate_stage_terminal.py::test_gate_stage_terminal_suppresses_reminder" }

$results += Control "T-09" "B" $conductor @(
	'        if stage_status is not None and stage_number is not None:\s*\n\s*rank = _STAGE_STATUS_RANK\.get\(stage_status\.get\(stage_number, ""\)\)\s*\n\s*if rank is not None and rank >= _STAGE_TERMINAL_RANK:\s*\n\s*continue'
) @("        if True:`n            continue") {
	RunPy "test_mwds_t09_gate_stage_terminal.py::test_no_roadmap_fails_open_and_reminds"
}

$results += Control "T-09" "C" $conductor @(
	'if rank is not None and rank >= _STAGE_TERMINAL_RANK:\s*\n\s*continue'
) @('if rank is not None and rank >= _STAGE_TERMINAL_RANK and stage_status.get(stage_number, "") != "halted": continue') {
	RunPy "test_mwds_t09_gate_stage_terminal.py::test_gate_stage_terminal_suppresses_reminder"
}

# ── T-10 AC-004 dispatch first-checks run.json (python) ──────────────────────
$results += Control "T-10" "A" $dispatchPy @(
	'    if run_status in mw_common\.RUN_TERMINAL_STATUSES:'
) @('    if False:') { RunPy "test_mwds_t10_dispatch_run_state.py::test_terminal_run_status_refuses_dispatch" }

$results += Control "T-10" "B" $dispatchPy @(
	'    run_status = mw_common\.read_run_status\(task_dir\)\n'
) @("    run_status = mw_common.read_run_status(task_dir)`n    if run_status is None:`n        return reject(`"run-missing`", `"control B`")`n") {
	RunPy "test_mwds_t10_dispatch_run_state.py::test_missing_run_json_dispatches_byte_identically"
}

# ── seam controls: either end reverted reds the T-12 seam case ───────────────
$results += Control "T-12" "C" $workerMode @(
	'if \(\s*config\.writeScope !== undefined &&\s*\n\s*!config\.writeScope\.some\(\(entry\) => matchesWriteScopeEntry\(config, entry, target\)\)\s*\n\s*\) \{'
) @('if (false) {') { RunTs "test/suite/mwds-t12-regression.test.ts" "the producer's one-line header is parsed" }

$results += Control "T-12" "A" $outputSections @(
	'for \(let i = blocks\.length - 1; i >= 0; i--\) \{\s*const block = blocks\[i\];\s*if \(title !== undefined && block\.title !== title\) continue;\s*if \(!isPlaceholderSection\(block\.title, block\.body\)\) return block;\s*\}'
) @('for (let i = 0; i < blocks.length; i++) { const block = blocks[i]; if (title !== undefined && block.title !== title) continue; return block; }') {
	RunTs "test/suite/mwds-t12-regression.test.ts" "a T-06-written output.md reads back"
}

# ── summary ──────────────────────────────────────────────────────────────────
""
"===== SUMMARY ====="
$byKind = $results | Group-Object Kind
foreach ($g in $byKind) {
	$reds = ($g.Group | Where-Object { $_.Pass }).Count
	"kind=$($g.Name) controls=$($g.Count) red=$reds"
}
$fails = $results | Where-Object { -not $_.Pass }
"total_controls=$($results.Count) pass=$($results.Count - $fails.Count) fail=$($fails.Count)"
if ($fails.Count -gt 0) { "FAILED: " + (($fails | ForEach-Object { "$($_.Id)/$($_.Kind)" }) -join ", ") }
$abCovered = ($byKind | ForEach-Object { $_.Name }) -contains "A" -and ($byKind | ForEach-Object { $_.Name }) -contains "B" -and ($byKind | ForEach-Object { $_.Name }) -contains "C"
$perGroup = ($byKind | ForEach-Object { "$($_.Name)=$(($_.Group | Where-Object { $_.Pass }).Count)" }) -join ','
"[VERIFY] VC-042: control_groups=A/B/C per_group_red=$perGroup"

# ── optional regression comparison (reverse case c) ──────────────────────────
function RegId([string] $line) {
	$m = [regex]::Match($line, 'test_[^\\/]+\.py::[^ ]+')
	if ($m.Success) { return $m.Value }
	return ($line -replace '^FAILED ','')
}
if ($RegressionFinal -ne "") {
	$baselineReds = $(if ($RegressionBaseline -ne "") {
		@(Select-String -Path $RegressionBaseline -Pattern '^FAILED ' | ForEach-Object { RegId $_.Line })
	} else {
		@(
			'test_autopilot_readcap_injection.py::test_baseline_left_end_bound',
			'test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below'
		)
	})
	$finalReds = @(Select-String -Path $RegressionFinal -Pattern '^FAILED ' | ForEach-Object { RegId $_.Line })
	$newReds = @($finalReds | Where-Object { $baselineReds -notcontains $_ })
	""
	"===== REGRESSION COMPARISON ====="
	"baseline_reds=$($baselineReds.Count) final_reds=$($finalReds.Count) new_reds=$($newReds.Count)"
	foreach ($r in $finalReds) { "  final red: $r" }
	if ($newReds.Count -gt 0) { "NEW REDS: " + ($newReds -join ', ') }
}
