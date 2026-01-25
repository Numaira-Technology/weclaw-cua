# WeChat Removal Workflow Launcher (Desktop Mode)
# Usage: Right-click -> Run with PowerShell
#   or: powershell -ExecutionPolicy Bypass -File start.ps1

$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  WeChat Removal Workflow (Desktop Mode)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check for .env file and load API key
$EnvFile = Join-Path $ScriptDir ".env"
if (Test-Path $EnvFile) {
    Write-Host "[OK] Loading API key from .env file..." -ForegroundColor Green
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            # Remove surrounding quotes if present
            if ($value -match '^["''](.*)["'']$') {
                $value = $matches[1]
            }
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
            Write-Host "   Set $key" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "[!] No .env file found. Checking environment..." -ForegroundColor Yellow
}

# Verify API key is set
if (-not $env:OPENROUTER_API_KEY) {
    Write-Host ""
    Write-Host "[ERROR] OPENROUTER_API_KEY not set!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please either:" -ForegroundColor Yellow
    Write-Host "  1. Create a .env file with: OPENROUTER_API_KEY=sk-or-v1-..." -ForegroundColor Yellow
    Write-Host "  2. Or set the environment variable manually" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[OK] API key configured" -ForegroundColor Green
Write-Host ""

# Check Python
Write-Host "Checking Python..." -ForegroundColor Cyan
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[OK] $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python not found in PATH" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  WARNING: Desktop Mode" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "The agent will control your mouse and keyboard directly." -ForegroundColor Yellow
Write-Host "Please:" -ForegroundColor Yellow
Write-Host "  - Close sensitive applications" -ForegroundColor Yellow
Write-Host "  - Make sure WeChat is open and logged in" -ForegroundColor Yellow
Write-Host "  - Do not use the computer while the agent is running" -ForegroundColor Yellow
Write-Host ""
Write-Host "------------------------------------------------------------" -ForegroundColor Gray
Write-Host ""

# Launch Control Panel
Write-Host "Launching Control Panel..." -ForegroundColor Cyan
Write-Host "Use the Control Panel to:" -ForegroundColor Gray
Write-Host "  - Start/Stop the computer server" -ForegroundColor Gray
Write-Host "  - Start/Stop the workflow backend" -ForegroundColor Gray
Write-Host "  - Run individual workflow steps" -ForegroundColor Gray
Write-Host ""

python control_panel.py

$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "------------------------------------------------------------" -ForegroundColor Gray

if ($exitCode -eq 0) {
    Write-Host "[OK] Control Panel closed." -ForegroundColor Green
} else {
    Write-Host "[!] Control Panel exited with code $exitCode" -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Press Enter to exit"
