# T-15 non-hollow controls: mutate the judgement, prove the named tests go red.
# Each control is applied to a backup copy and always restored.
$ErrorActionPreference = "Continue"
$repo = "H:/git/Multi-Workers"
$file = Join-Path $repo "packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts"
$bak = "$file.t15bak"
Copy-Item $file $bak -Force

function RunTest([string] $label) {
	Push-Location (Join-Path $repo "packages/coding-agent")
	try {
		$out = (node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-store.test.ts 2>&1 | Out-String)
		$line = ($out | Select-String -Pattern 'Tests\s+' | Select-Object -Last 1)
		$failed = ($out | Select-String -Pattern 'FAIL' | Measure-Object).Count
		"$label -> $line | FAIL lines: $failed"
	} finally { Pop-Location }
}

try {
	# Control A: narrow the column window back to the pre-origin era (8).
	(Get-Content $file -Raw) -replace 'WORKER_COLS_MAX = 9;', 'WORKER_COLS_MAX = 8;' | Set-Content $file -NoNewline -Encoding UTF8
	RunTest "CONTROL A (WORKER_COLS_MAX=8)"
	Copy-Item $bak $file -Force

	# Control B: make upsert rewrite from the parsed rows only (the IN-3 delete).
	$raw = Get-Content $file -Raw
	$needle = 'lines = raw.map((line, i) => (i === idx ? replacement : line));'
	$repl = 'lines = [...this.readAll().filter((e) => e.taskKey !== entry.taskKey).map(serializeWorkerLine), replacement];'
	if ($raw -notmatch [regex]::Escape($needle)) { throw "control B needle not found" }
	($raw -replace [regex]::Escape($needle), $repl) | Set-Content $file -NoNewline -Encoding UTF8
	RunTest "CONTROL B (upsert drops unreadable rows)"
	Copy-Item $bak $file -Force

	# Control C: stop reading the declared header.
	$raw = Get-Content $file -Raw
	$needleC = 'const QUEUE_HEADER_RE = /^#\s*mw-queue:v(\d+)\s*$/;'
	if ($raw -notmatch [regex]::Escape($needleC)) { throw "control C needle not found" }
	($raw -replace [regex]::Escape($needleC), 'const QUEUE_HEADER_RE = /^#\s*never:(\d+)$/;') | Set-Content $file -NoNewline -Encoding UTF8
	RunTest "CONTROL C (header ignored)"
} finally {
	Copy-Item $bak $file -Force
	Remove-Item $bak -Force
	"restored: " + ((Get-FileHash $file).Hash -ne $null)
}
