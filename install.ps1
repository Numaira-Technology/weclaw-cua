# WeChat Removal Tool — Installer
#
# Downloads (or copies from a local source) the tool and wires it up for
# first-time use. Creates a desktop shortcut and optionally installs
# Python dependencies.
#
# Usage:
#   # From a local repo clone — install in-place
#   .\install.ps1
#
#   # Install to a custom directory
#   .\install.ps1 --install-dir "C:\Tools\WeChatRemoval"
#
#   # Skip dependency installation (manage venv yourself)
#   .\install.ps1 --skip-deps
#
#   # Non-interactive (CI / scripted)
#   .\install.ps1 --no-prompt

param(
    [string]$InstallDir  = "",
    [switch]$SkipDeps,
    [switch]$NoPrompt
)

$ErrorActionPreference = "Stop"

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------
function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "  >> $msg" -ForegroundColor Cyan
}

function Write-Ok([string]$msg)    { Write-Host "     [OK] $msg" -ForegroundColor Green  }
function Write-Warn([string]$msg)  { Write-Host "     [!]  $msg" -ForegroundColor Yellow }
function Write-Err([string]$msg)   { Write-Host "     [X]  $msg" -ForegroundColor Red    }

function Confirm-Step([string]$prompt) {
    if ($NoPrompt) { return $true }
    $ans = Read-Host "$prompt [Y/n]"
    return ($ans -eq "" -or $ans -match "^[Yy]")
}

# -----------------------------------------------------------------------
# Banner
# -----------------------------------------------------------------------
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  WeChat Removal Tool — Installer" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# -----------------------------------------------------------------------
# 1. Determine source and install directories
# -----------------------------------------------------------------------
$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($InstallDir -eq "") {
    $InstallDir = $SourceDir
    Write-Ok "Using source directory as install root: $InstallDir"
} else {
    Write-Step "Copying files to $InstallDir ..."
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    # Exclude .env so secrets are never copied to a new location
    Copy-Item -Path "$SourceDir\*" -Destination $InstallDir -Recurse -Force -Exclude ".env"
    Write-Ok "Files copied."
}

Set-Location $InstallDir

# -----------------------------------------------------------------------
# 2. Python version check
# -----------------------------------------------------------------------
Write-Step "Checking Python ..."
try {
    $pyVer = python --version 2>&1
    if ($pyVer -match "Python (\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
            Write-Err "Python 3.11+ required. Found: $pyVer"
            Write-Host "  Download from https://www.python.org/downloads/" -ForegroundColor Yellow
            if (-not $NoPrompt) { Read-Host "Press Enter to exit" }
            exit 1
        }
        Write-Ok "$pyVer"
    }
} catch {
    Write-Err "Python not found on PATH."
    Write-Host "  Download from https://www.python.org/downloads/" -ForegroundColor Yellow
    if (-not $NoPrompt) { Read-Host "Press Enter to exit" }
    exit 1
}

# -----------------------------------------------------------------------
# 3. Create virtual environment and install dependencies
# -----------------------------------------------------------------------
$VenvDir = Join-Path $InstallDir ".venv"

if (-not $SkipDeps) {
    Write-Step "Setting up Python virtual environment ..."

    if (-not (Test-Path $VenvDir)) {
        python -m venv $VenvDir
        Write-Ok "Virtual environment created at $VenvDir"
    } else {
        Write-Ok "Virtual environment already exists — reusing."
    }

    $PipExe = Join-Path $VenvDir "Scripts\pip.exe"

    Write-Step "Installing Python dependencies into venv ..."
    $ReqFile = Join-Path $InstallDir "requirements.txt"
    if (Test-Path $ReqFile) {
        Write-Host "     Using requirements.txt ..." -ForegroundColor Gray
        & $PipExe install -r $ReqFile --quiet
    } else {
        # Fallback: individual packages (keep in sync with requirements.txt)
        $Deps = @(
            "httpx", "aiohttp", "pydantic", "litellm", "pillow",
            "typing-extensions", "uvicorn", "fastapi", "pynput", "anyio", "pyyaml"
        )
        Write-Host "     requirements.txt not found — installing individual packages ..." -ForegroundColor Gray
        & $PipExe install @Deps --quiet
    }

    Write-Ok "Dependencies installed."
} else {
    Write-Warn "Skipping dependency installation (--skip-deps)."
    if (-not (Test-Path $VenvDir)) {
        Write-Warn "No .venv found. The tool may fail to launch without dependencies."
    }
}

# -----------------------------------------------------------------------
# 4. API key setup
# -----------------------------------------------------------------------
Write-Step "API key configuration ..."
$EnvFile = Join-Path $InstallDir ".env"

if (Test-Path $EnvFile) {
    Write-Ok ".env file already exists — skipping."
} else {
    if ($NoPrompt) {
        Write-Warn "No .env file found. Create $EnvFile with your OPENROUTER_API_KEY."
    } else {
        Write-Host ""
        Write-Host "     An OpenRouter API key is required to run the tool." -ForegroundColor White
        Write-Host "     Get one at https://openrouter.ai" -ForegroundColor Gray
        Write-Host ""
        $apiKey = Read-Host "     Paste your OPENROUTER_API_KEY (leave blank to skip)"
        if ($apiKey -ne "") {
            "OPENROUTER_API_KEY=$apiKey" | Set-Content $EnvFile -Encoding UTF8
            # Restrict .env to the current user only
            $acl = Get-Acl $EnvFile
            $acl.SetAccessRuleProtection($true, $false)
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
                [System.Security.Principal.WindowsIdentity]::GetCurrent().Name,
                "FullControl", "Allow"
            )
            $acl.SetAccessRule($rule)
            Set-Acl $EnvFile $acl
            Write-Ok ".env file created (restricted to current user)."
        } else {
            Write-Warn "Skipped. Create $EnvFile manually before running the tool."
        }
    }
}

# -----------------------------------------------------------------------
# 5. Create desktop shortcut
# -----------------------------------------------------------------------
Write-Step "Creating desktop shortcut ..."

try {
    $Desktop     = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "WeChat Removal Tool.lnk"
    $LauncherBat  = Join-Path $InstallDir "start.bat"

    if (-not (Test-Path $LauncherBat)) {
        Write-Warn "start.bat not found — skipping shortcut creation."
    } else {
        $WshShell  = New-Object -ComObject WScript.Shell
        $Shortcut  = $WshShell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath       = $LauncherBat
        $Shortcut.WorkingDirectory = $InstallDir
        $Shortcut.Description      = "WeChat Removal Tool"
        $Shortcut.Save()
        Write-Ok "Shortcut created: $ShortcutPath"
    }
} catch {
    Write-Warn "Could not create desktop shortcut: $_"
}

# -----------------------------------------------------------------------
# 6. Summary
# -----------------------------------------------------------------------
Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Install directory : $InstallDir" -ForegroundColor White
Write-Host "  Virtual env       : $VenvDir" -ForegroundColor White
Write-Host ""
Write-Host "  To start the tool:" -ForegroundColor White
Write-Host "    Double-click 'WeChat Removal Tool' on your desktop" -ForegroundColor Gray
Write-Host "    — or —" -ForegroundColor Gray
Write-Host "    Run: .\start.bat  (or .\start.ps1)" -ForegroundColor Gray
Write-Host ""
Write-Host "  Before first run:" -ForegroundColor White
Write-Host "    1. Open WeChat and log in" -ForegroundColor Gray
Write-Host "    2. Make sure OPENROUTER_API_KEY is set in .env" -ForegroundColor Gray
Write-Host "    3. Adjust config\computer_windows.yaml if your screen" -ForegroundColor Gray
Write-Host "       resolution differs from 2560x1440" -ForegroundColor Gray
Write-Host ""

if (-not $NoPrompt) {
    Read-Host "Press Enter to exit"
}
