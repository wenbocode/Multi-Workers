# T-17 / T-19 non-hollow controls (A-E): mutate each guard, prove the named tests go red.
# Byte-safe UTF-8 IO (the file contains Chinese comments).
$ErrorActionPreference = "Continue"
$repo = "H:/git/Multi-Workers"
$file = Join-Path $repo "packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts"
$bak = "$file.t17bak"
Copy-Item $file $bak -Force

$utf8 = New-Object System.Text.UTF8Encoding($false)
function ReadText([string] $p) { [System.IO.File]::ReadAllText($p, $utf8) }
function WriteText([string] $p, [string] $t) { [System.IO.File]::WriteAllText($p, $t, $utf8) }

function RunTest([string] $label) {
	Push-Location (Join-Path $repo "packages/coding-agent")
	try {
		$out = (node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-dispatch-guard.test.ts 2>&1 | Out-String)
		$tests = ([regex]::Match($out, "Tests\s+(\d+ failed \| \d+ passed|\d+ passed)[^\r\n]*")).Value
		"$label -> [$tests]"
	} finally { Pop-Location }
}

function Swap([string] $needle, [string] $replacement, [string] $label) {
	$t = ReadText $file
	if (-not $t.Contains($needle)) { throw "needle not found: $label" }
	WriteText $file $t.Replace($needle, $replacement)
}

try {
	Swap 'if (scope === "pm" && owner.name !== SCRATCH_WORKERS_KEY && owner.name !== opts.watchedKey) continue;' 'if (false) continue;' "A"
	RunTest "CONTROL A (pm scope filter removed)"
	Copy-Item $bak $file -Force

	Swap 'if (queued >= maxPerScan) {' 'if (false) {' "B"
	RunTest "CONTROL B (quota removed)"
	Copy-Item $bak $file -Force

	Swap 'if (queue.unparsable.length > 0) {' 'if (false) {' "C"
	RunTest "CONTROL C (unparsable rows no longer abort)"
	Copy-Item $bak $file -Force

	Swap 'if (queueIsEmpty && undispatched.some((t) => hasProductEvidence(path.dirname(t.taskMdPath)))) {' 'if (false) {' "D"
	RunTest "CONTROL D (empty-queue evidence guard removed)"
	Copy-Item $bak $file -Force

	Swap 'recordDispatchAlarm(agenticdocRoot, alarm);' 'void alarm;' "E"
	RunTest "CONTROL E (alarm ledger write removed)"
} finally {
	Copy-Item $bak $file -Force
	Remove-Item $bak -Force
	"restored: " + ((ReadText $file).Contains('if (queue.unparsable.length > 0) {'))
}
