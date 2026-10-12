# T-20 non-hollow controls (A-G): mutate each guarantee and prove the named test
# goes red. Byte-safe UTF-8 IO (pm-orchestrator.ts carries Chinese text).
$ErrorActionPreference = "Continue"
$repo = "H:/git/Multi-Workers"
$mw = Join-Path $repo "packages/multi-workers"
$ca = Join-Path $repo "packages/coding-agent"
$utf8 = New-Object System.Text.UTF8Encoding($false)

function ReadText([string] $p) { [System.IO.File]::ReadAllText($p, $utf8) }
function WriteText([string] $p, [string] $t) { [System.IO.File]::WriteAllText($p, $t, $utf8) }

function RunVitest([string] $label, [string] $file, [string] $testName) {
	Push-Location $ca
	try {
		$out = (node ../../node_modules/vitest/dist/cli.js --run $file -t $testName 2>&1 | Out-String)
		$line = ([regex]::Match($out, "Tests +\d+ (failed|passed)[^\r\n]*")).Value
		if (-not $line) { $line = ($out -split "`n" | Select-Object -Last 3) -join " " }
		"$label -> [$($line.Trim())]"
	} finally { Pop-Location }
}

function RunPytest([string] $label, [string] $nodeId) {
	Push-Location $mw
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

$runStore = Join-Path $ca "src/extensions/agent-team-loop/shared/run-store.ts"
$pmOrch = Join-Path $ca "src/extensions/agent-team-loop/pm/pm-orchestrator.ts"
$launcher = Join-Path $mw "launcher.py"
$common = Join-Path $mw "mw_common.py"
$runStoreBak = "$runStore.t20bak"
$pmOrchBak = "$pmOrch.t20bak"
$launcherBak = "$launcher.t20bak"
$commonBak = "$common.t20bak"
Copy-Item $runStore $runStoreBak -Force
Copy-Item $pmOrch $pmOrchBak -Force
Copy-Item $launcher $launcherBak -Force
Copy-Item $common $commonBak -Force

try {
	# A: the ledger beats the product again (a done task becomes re-queueable).
	Mutate $runStore '	if (kind === "terminal") {' '	if (false && kind === "terminal") {' "A"
	RunVitest "CONTROL A (terminal run record no longer refused)" "test/suite/worker-dispatch-guard.test.ts" "never re-queues a task whose own run already ended"
	Copy-Item $runStoreBak $runStore -Force

	# B: the supersedes replacement path is removed (a legitimate replacement
	# is refused, i.e. the escape hatch from the identity rule is gone).
	Mutate $runStore '	const targetKind = runStateKind(read(targetDir));' '	const targetKind: "terminal" | "active" | "unknown" = "unknown";' "B"
	RunVitest "CONTROL B (supersede replacement path removed)" "test/suite/worker-dispatch-guard.test.ts" "dispatches a replacement run that declares supersedes"
	Copy-Item $runStoreBak $runStore -Force

	# C: the superseded run's own state is no longer validated.
	Mutate $runStore '	if (targetKind !== "terminal") {' '	if (false && targetKind !== "terminal") {' "C"
	RunVitest "CONTROL C (superseding a live run allowed)" "test/suite/worker-dispatch-guard.test.ts" "refuses to supersede a run that is not finished"
	Copy-Item $runStoreBak $runStore -Force

	# D: the run record write throws instead of degrading (output.md must still land).
	$dNeedle = '	} catch (err) {' + "`n" + '		const message = err instanceof Error ? err.message : String(err);' + "`n" + '		appendRunNote(taskDir, `[RUN] run.json write failed (${state.status}): ${message}`);' + "`n" + '		return { ok: false, error: message };' + "`n" + '	}'
	$dReplacement = '	} catch (err) {' + "`n" + '		throw err;' + "`n" + '	}'
	Mutate $runStore $dNeedle $dReplacement "D"
	RunVitest "CONTROL D (run record write throws -> output.md blocked)" "test/suite/worker-run-identity.test.ts" "still writes output.md when the run record cannot be written"
	Copy-Item $runStoreBak $runStore -Force

	# E: the out-of-scope visibility disappears (silent skip).
	Mutate $pmOrch '			outOfScope.push(owner.name);' '			// mutation: candidate keys are skipped silently' "E"
	RunVitest "CONTROL E (skipped keys no longer reported)" "test/suite/worker-dispatch-guard.test.ts" "reports the keys it did not scan"
	Copy-Item $pmOrchBak $pmOrch -Force

	# F: the launcher ignores the product-carried terminal state.
	Mutate $launcher '        elif run_status in mw_common.RUN_TERMINAL_STATUSES:' '        elif False and run_status in mw_common.RUN_TERMINAL_STATUSES:' "F"
	RunPytest "CONTROL F (launcher ignores run.json terminal state)" "test_launcher.py::TestReconcileRunState::test_run_json_terminal_converges_stuck_row"
	Copy-Item $launcherBak $launcher -Force

	# G: the launcher fabricates a terminal state instead of `lost`.
	Mutate $common '    data["status"] = "lost"' '    data["status"] = "done"' "G"
	RunPytest "CONTROL G (launcher writes done instead of lost)" "test_launcher.py::TestReconcileRunState::test_run_json_running_with_output_md_becomes_lost"
	Copy-Item $commonBak $common -Force
} finally {
	Copy-Item $runStoreBak $runStore -Force
	Copy-Item $pmOrchBak $pmOrch -Force
	Copy-Item $launcherBak $launcher -Force
	Copy-Item $commonBak $common -Force
	Remove-Item $runStoreBak -Force
	Remove-Item $pmOrchBak -Force
	Remove-Item $launcherBak -Force
	Remove-Item $commonBak -Force
	"restored: " + ((ReadText $runStore).Contains('	if (kind === "terminal") {') -and (ReadText $common).Contains('    data["status"] = "lost"'))
}
