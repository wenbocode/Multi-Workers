# AC-024 (T-22) non-hollow controls: mutate each guard, prove the named tests go red.
# Byte-safe UTF-8 IO (the file has Chinese comments and em dashes).
$ErrorActionPreference = "Continue"
$repo = "H:/git/Multi-Workers"
$file = Join-Path $repo "packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts"
$bak = "$file.t22bak"
Copy-Item $file $bak -Force

$utf8 = New-Object System.Text.UTF8Encoding($false)
function ReadText([string] $p) { [System.IO.File]::ReadAllText($p, $utf8) }
function WriteText([string] $p, [string] $t) { [System.IO.File]::WriteAllText($p, $t, $utf8) }

function RunTest([string] $label) {
	Push-Location (Join-Path $repo "packages/coding-agent")
	try {
		$out = (node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-crosskey-readonly.test.ts 2>&1 | Out-String)
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
	Swap 'if ((key ?? "").trim()) {' 'if (false) {' "A"
	RunTest "CONTROL A (dispatch_worker cross-key guard removed)"
	Copy-Item $bak $file -Force

	Swap 'const crossKeyRefusal = foreignLiveClaimRefusal(indexStore, trimmedKey);' 'const crossKeyRefusal = null;' "B"
	RunTest "CONTROL B (advance_phase cross-key guard removed)"
	Copy-Item $bak $file -Force

	Swap 'if (claimState(claim, windowClaimId()) !== "held-live") return null;' 'return null;' "C"
	RunTest "CONTROL C (foreign-live predicate always allows)"
	Copy-Item $bak $file -Force

	Swap 'if (scope === "all") {' 'if (false) {' "D"
	RunTest "CONTROL D (global read path broken -> reverse case catches it)"
} finally {
	Copy-Item $bak $file -Force
	Remove-Item $bak -Force
	"restored: " + ((ReadText $file).Contains('if ((key ?? "").trim()) {'))
}
