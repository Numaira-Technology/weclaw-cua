# WeChat Removal Skill — Windows Launcher
# Called by OpenClaw when the wechat-removal skill is dispatched.
#
# Usage:
#   .\scripts\run_wechat_removal.ps1
#   .\scripts\run_wechat_removal.ps1 --dry-run
#   .\scripts\run_wechat_removal.ps1 --tool-root "C:\path\to\tool"
#   .\scripts\run_wechat_removal.ps1 --model "openrouter/anthropic/claude-sonnet-4"

param(
    [string]$ToolRoot   = "",
    [string]$Model      = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# -----------------------------------------------------------------------
# 1. Resolve tool root
# -----------------------------------------------------------------------
if ($ToolRoot -eq "") {
    # Default: two levels up from this script (OpenClaw_WeChatRemoval_skill/scripts/ -> tool root)
    $ScriptPath = $MyInvocation.MyCommand.Path
    if (-not $ScriptPath) {
        Write-Host "[ERROR] Cannot auto-detect tool root: script path is unavailable." -ForegroundColor Red
        Write-Host "        Run with: .\scripts\run_wechat_removal.ps1 --tool-root <path>" -ForegroundColor Yellow
        exit 1
    }
    $ToolRoot = Split-Path -Parent (Split-Path -Parent $ScriptPath)
}

if (-not (Test-Path $ToolRoot)) {
    Write-Host "[ERROR] Tool root not found: $ToolRoot" -ForegroundColor Red
    Write-Host "        Use --tool-root to specify the installation directory." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  WeChat Removal Tool  (OpenClaw Skill Launcher)" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  Tool root : $ToolRoot" -ForegroundColor Gray
Write-Host ""

# -----------------------------------------------------------------------
# 2. Load .env from tool root
# -----------------------------------------------------------------------
$EnvFile = Join-Path $ToolRoot ".env"
if (Test-Path $EnvFile) {
    Write-Host "[OK] Loading environment from .env ..." -ForegroundColor Green
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
            $key   = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($value -match '^["''](.*)["'']$') { $value = $matches[1] }
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
} else {
    Write-Host "[!] No .env file found — relying on system environment." -ForegroundColor Yellow
}

# -----------------------------------------------------------------------
# 3. Pre-flight checks
# -----------------------------------------------------------------------
$Errors = @()

# 3a. API key
if (-not $env:OPENROUTER_API_KEY) {
    $Errors += "OPENROUTER_API_KEY is not set. Add it to .env or set it as an environment variable."
}

# 3b. Python version (requires 3.11+)
try {
    $pyVer = python --version 2>&1
    if ($pyVer -match "Python (\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
            $Errors += "Python 3.11+ required. Found: $pyVer. Download from https://www.python.org/downloads/"
        } else {
            Write-Host "[OK] $pyVer" -ForegroundColor Green
        }
    } else {
        $Errors += "Could not parse Python version from: $pyVer"
    }
} catch {
    $Errors += "Python not found on PATH. Install Python 3.11+ and ensure it is on PATH."
}

# 3c. Control panel entry point
$ControlPanel = Join-Path $ToolRoot "control_panel.py"
if (-not (Test-Path $ControlPanel)) {
    $Errors += "control_panel.py not found at: $ControlPanel"
}

# 3d. Config files
$ModelConfig   = Join-Path $ToolRoot "config\model.yaml"
$ComputerConfig = Join-Path $ToolRoot "config\computer_windows.yaml"
foreach ($cfg in @($ModelConfig, $ComputerConfig)) {
    if (-not (Test-Path $cfg)) {
        $Errors += "Config file missing: $cfg"
    }
}

if ($Errors.Count -gt 0) {
    Write-Host ""
    Write-Host "[PREFLIGHT FAILED]" -ForegroundColor Red
    foreach ($err in $Errors) {
        Write-Host "  - $err" -ForegroundColor Red
    }
    Write-Host ""
    exit 1
}

Write-Host "[OK] All pre-flight checks passed." -ForegroundColor Green

# -----------------------------------------------------------------------
# 4. Dry-run exit
# -----------------------------------------------------------------------
if ($DryRun) {
    Write-Host ""
    Write-Host "[DRY-RUN] Setup is valid. Skipping launch." -ForegroundColor Yellow
    Write-Host ""
    exit 0
}

# -----------------------------------------------------------------------
# 5. Apply optional model override
# -----------------------------------------------------------------------
if ($Model -ne "") {
    Write-Host "[INFO] Model override: $Model" -ForegroundColor Cyan
    [Environment]::SetEnvironmentVariable("WECHAT_REMOVAL_MODEL_OVERRIDE", $Model, "Process")
}

# -----------------------------------------------------------------------
# 6. Launch Control Panel
# -----------------------------------------------------------------------
Write-Host ""
Write-Host "[INFO] Launching Control Panel..." -ForegroundColor Cyan
Write-Host "       WeChat must be open and logged in." -ForegroundColor Yellow
Write-Host ""

Set-Location $ToolRoot
python $ControlPanel

$exitCode = $LASTEXITCODE
Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "[OK] Control Panel closed cleanly." -ForegroundColor Green
} else {
    Write-Host "[!] Control Panel exited with code $exitCode" -ForegroundColor Yellow
}
Write-Host ""
