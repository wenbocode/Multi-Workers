# T-21 non-hollow controls (A-E): each mutation targets a claim the IN-3 replay
# asserts, and the named test must go red. Byte-safe UTF-8 IO (the TS file
# carries Chinese comments).
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

$store = Join-Path $ca "src/extensions/agent-team-loop/shared/worker-store.ts"
$common = Join-Path $mw "mw_common.py"
$storeBak = "$store.t21bak"
$commonBak = "$common.t21bak"
Copy-Item $store $storeBak -Force
Copy-Item $common $commonBak -Force

try {
	# A: the TS reader goes back to the pre-fix 8-column ceiling.
	Mutate $store 'const WORKER_COLS_MAX = 9;' 'const WORKER_COLS_MAX = 8;' "A"
	RunVitest "CONTROL A (TS reader rejects 9-column rows again)" "test/suite/worker-store.test.ts" "reads every incident row"
	Copy-Item $storeBak $store -Force

	# B: the Python reader goes back to the pre-fix 8-column ceiling.
	Mutate $common 'WORKER_COLS_MAX = 9' 'WORKER_COLS_MAX = 8' "B"
	RunPytest "CONTROL B (Python reader rejects 9-column rows again)" "test_in3_queue_replay.py::test_current_codec_reads_every_incident_row"
	Copy-Item $commonBak $common -Force

	# C: the TS writer rewrites the file from its parsed view (IN-3 amplifier F4).
	Mutate $store '			const raw = this.readRawLines();' '			const raw = this.readRawLines().filter((line) => line.trim() === "" || line.trimStart().startsWith("#") || parseWorkerLine(line).ok);' "C"
	RunVitest "CONTROL C (TS writer drops unreadable rows)" "test/suite/worker-store.test.ts" "counts a 10-column row and keeps its slot across an upsert"
	Copy-Item $storeBak $store -Force

	# D: the TS reader rejects the legacy 8-column writer output.
	Mutate $store 'const WORKER_COLS_MIN = 7;' 'const WORKER_COLS_MIN = 9;' "D"
	RunVitest "CONTROL D (TS reader rejects legacy 8-column rows)" "test/suite/worker-store.test.ts" "also reads the legacy 8-column writer output"
	Copy-Item $storeBak $store -Force

	# E: the Python reader rejects the legacy 8-column writer output.
	Mutate $common 'WORKER_COLS_MIN = 7' 'WORKER_COLS_MIN = 9' "E"
	RunPytest "CONTROL E (Python reader rejects legacy 8-column rows)" "test_in3_queue_replay.py::test_current_codec_also_reads_the_legacy_column_shape"
	Copy-Item $commonBak $common -Force
} finally {
	Copy-Item $storeBak $store -Force
	Copy-Item $commonBak $common -Force
	Remove-Item $storeBak -Force
	Remove-Item $commonBak -Force
	"restored: " + ((ReadText $store).Contains('const WORKER_COLS_MAX = 9;') -and (ReadText $common).Contains('WORKER_COLS_MAX = 9'))
}
