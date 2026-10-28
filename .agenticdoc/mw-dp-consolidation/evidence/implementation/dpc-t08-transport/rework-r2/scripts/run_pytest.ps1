# T08 R2 assigned-suite runner (isolated fixture env, no live objects).
# Usage: run_pytest.ps1 -Label <name> [-Extra @('-k','expr')]
param(
    [Parameter(Mandatory = $true)][string]$Label,
    [string[]]$Extra = @()
)

$ErrorActionPreference = 'Stop'
# Keep the captured stdout/stderr readable UTF-8 (PS 5.1 `>` defaults to UTF-16LE).
$PSDefaultParameterValues = @{ 'Out-File:Encoding' = 'utf8' }
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$pkg = 'H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers'
$ev = 'H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\evidence\implementation\dpc-t08-transport\rework-r2'
$fix = Join-Path $ev 'fixture'
$run = Join-Path $ev ("runs\" + $Label)

foreach ($d in @($fix, (Join-Path $fix 'home'), (Join-Path $fix 'temp'), (Join-Path $fix 'project'), (Join-Path $fix 'basetemp'), $run)) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

# --- minimal, private, UTF-8 environment (no ambient provider/worker config) ---
$drop = @(
    'TIMI_API_KEY', 'TIMI_BASE_URL', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY',
    'PI_WORKER_TASK', 'PI_WORKER_IDLE_MS', 'PI_WORKER_TIMEOUT_MS', 'PI_AGENTIC_KEY',
    'PYTHONPATH', 'PYTHONSTARTUP', 'PYTEST_ADDOPTS', 'PYTEST_PLUGINS'
)
foreach ($name in $drop) { Remove-Item -Path ("Env:" + $name) -ErrorAction SilentlyContinue }

$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONNOUSERSITE = '1'
$env:HOME = (Join-Path $fix 'home')
$env:USERPROFILE = (Join-Path $fix 'home')
$env:TEMP = (Join-Path $fix 'temp')
$env:TMP = (Join-Path $fix 'temp')
$env:XDG_CACHE_HOME = (Join-Path $fix 'temp')
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'

$basetemp = Join-Path $fix 'basetemp'
$argv = @(
    '-B', '-m', 'pytest', '-p', 'no:cacheprovider', '-q',
    '--basetemp', $basetemp, 'test_dp_consolidation_materials.py'
) + $Extra

Push-Location $pkg
try {
    $started = (Get-Date).ToUniversalTime().ToString('o')
    $out = Join-Path $run 'pytest.stdout'
    $err = Join-Path $run 'pytest.stderr'
    & python @argv 1> $out 2> $err
    $rc = $LASTEXITCODE
    $finished = (Get-Date).ToUniversalTime().ToString('o')
} finally {
    Pop-Location
}

$meta = [ordered]@{
    label = $Label
    cwd = $pkg
    argv = $argv
    started_utc = $started
    finished_utc = $finished
    rc = $rc
    env = [ordered]@{
        PYTHONDONTWRITEBYTECODE = $env:PYTHONDONTWRITEBYTECODE
        PYTHONUTF8 = $env:PYTHONUTF8
        PYTHONIOENCODING = $env:PYTHONIOENCODING
        PYTHONNOUSERSITE = $env:PYTHONNOUSERSITE
        HOME = $env:HOME
        USERPROFILE = $env:USERPROFILE
        TEMP = $env:TEMP
        PYTEST_DISABLE_PLUGIN_AUTOLOAD = $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD
    }
}
$meta | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $run 'rc.json')
Write-Output ("label={0} rc={1} stdout={2}" -f $Label, $rc, $out)
Get-Content $out -Tail 6
