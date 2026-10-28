param(
    [string]$Label = "run",
    [string]$Target = "test_decision_context_workbench.py",
    [string]$Selection = ""
)

$ErrorActionPreference = "Continue"
$Evidence = "H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\evidence\implementation\dpc-t05-eight-cases"
$Pkg = "H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers"
$RunDir = Join-Path $Evidence ("logs\" + $Label)
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
$HomeDir = Join-Path $RunDir "home"
$TmpDir = Join-Path $RunDir "tmp"
$ProjectDir = Join-Path $RunDir "project"
New-Item -ItemType Directory -Force -Path $HomeDir, $TmpDir, $ProjectDir | Out-Null

$names = @(
    "ANTHROPIC_API_KEY","OPENAI_API_KEY","TIMI_API_KEY","TIMI_BASE_URL","MW_DECIDE_API_KEY",
    "MW_DECISION_API_KEY","PI_API_KEY","PI_WORKER_TASK","PI_AGENT_TEAM_ROLE","HTTP_PROXY","HTTPS_PROXY",
    "http_proxy","https_proxy","ALL_PROXY","all_proxy"
)
foreach ($name in $names) { Remove-Item -Path ("Env:" + $name) -ErrorAction SilentlyContinue }
$env:HOME = $HomeDir
$env:USERPROFILE = $HomeDir
$env:TEMP = $TmpDir
$env:TMP = $TmpDir
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPYCACHEPREFIX = $TmpDir
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:MW_PROJECT_DIR = $ProjectDir
$env:PI_CODING_AGENT_DIR = Join-Path $HomeDir "pi-agent"

$deps = @(
    "decision_lifecycle.py",
    "decision_task_state.py",
    "decision_wire.py",
    "decision_book.py",
    "decision_points.py"
)

function Capture-Deps([string]$Path) {
    $rows = @()
    foreach ($dep in $deps) {
        $file = Join-Path $Pkg $dep
        $sha = (Get-FileHash -Algorithm SHA256 -Path $file).Hash.ToLower()
        $item = Get-Item $file
        $rows += [ordered]@{ file = $dep; sha256 = $sha; bytes = $item.Length; mtime = $item.LastWriteTimeUtc.ToString("o") }
    }
    $rows | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 $Path
}

Capture-Deps (Join-Path $RunDir "deps-before.json")
Push-Location $Pkg
$stamp = (Get-Date).ToUniversalTime().ToString("o")
$argv = @("python", "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q")
if ($Selection -ne "") { $argv += @("-k", $Selection) }
$argv += @($Target)
python -B -m pytest -p no:cacheprovider -q $(if ($Selection -ne "") { @("-k", $Selection) } else { @() }) $Target 2>&1 | Tee-Object -FilePath (Join-Path $RunDir "stdout.txt")
$rc = $LASTEXITCODE
Pop-Location
Capture-Deps (Join-Path $RunDir "deps-after.json")

# The imported module identity in exactly this environment (read back).
$probeScript = Join-Path $RunDir "import_probe.py"
@'
import hashlib, importlib.util, json, pathlib, sys
sys.path.insert(0, sys.argv[1])
out = {}
for name in ("decision_lifecycle", "decision_task_state", "decision_wire", "decision_book", "decision_points"):
    spec = importlib.util.find_spec(name)
    origin = pathlib.Path(spec.origin).resolve()
    out[name] = {
        "imported_from": str(origin),
        "sha256": hashlib.sha256(origin.read_bytes()).hexdigest(),
    }
print(json.dumps(out, indent=2))
'@ | Set-Content -Encoding utf8 $probeScript
python -B $probeScript $Pkg | Set-Content -Encoding utf8 (Join-Path $RunDir "imported-modules.json")

$meta = [ordered]@{
    label = $Label
    started_at = $stamp
    finished_at = (Get-Date).ToUniversalTime().ToString("o")
    cwd = $Pkg
    target = $Target
    selection = $Selection
    argv = $argv
    rc = $rc
    home = $HomeDir
    temp = $TmpDir
    project = $ProjectDir
    env = [ordered]@{
        HOME = $env:HOME; USERPROFILE = $env:USERPROFILE; TEMP = $env:TEMP
        PYTHONDONTWRITEBYTECODE = $env:PYTHONDONTWRITEBYTECODE
        PYTHONPYCACHEPREFIX = $env:PYTHONPYCACHEPREFIX
        PYTEST_DISABLE_PLUGIN_AUTOLOAD = $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD
        PYTHONUTF8 = $env:PYTHONUTF8; MW_PROJECT_DIR = $env:MW_PROJECT_DIR
    }
}
$meta | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $RunDir "meta.json")
Write-Output ("rc=" + $rc)
