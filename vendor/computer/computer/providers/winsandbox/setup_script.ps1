# Setup script for Windows Sandbox Cua Computer provider
# This script runs when the sandbox starts

Write-Host "Starting Cua Computer setup in Windows Sandbox..."

# Step 0: Configure DNS, Firewall, and Proxy settings
Write-Host "Step 0: Configuring network settings..."

# 0a. Configure DNS
Write-Host "  Configuring DNS servers..."
try {
    $adapters = Get-NetAdapter | Where-Object { $_.Status -eq "Up" }
    foreach ($adapter in $adapters) {
        Write-Host "    Setting DNS for adapter: $($adapter.Name)"
        Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses ("8.8.8.8", "8.8.4.4")
    }
    Clear-DnsClientCache
    Write-Host "  DNS configured successfully"
}
catch {
    Write-Host "  WARNING: Failed to configure DNS: $_"
}

# 0b. Disable Windows Firewall inside sandbox (sandbox is already isolated)
Write-Host "  Disabling Windows Firewall inside sandbox..."
try {
    Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False -ErrorAction Stop
    Write-Host "  Firewall disabled successfully"
}
catch {
    Write-Host "  WARNING: Failed to disable firewall: $_"
}

# 0c. Clear any proxy settings that might interfere
Write-Host "  Clearing proxy settings..."
try {
    # Disable proxy in Internet Settings
    Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -Name ProxyEnable -Value 0 -ErrorAction SilentlyContinue
    Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -Name ProxyServer -Value "" -ErrorAction SilentlyContinue
    
    # Clear WinHTTP proxy
    netsh winhttp reset proxy 2>$null
    
    Write-Host "  Proxy settings cleared"
}
catch {
    Write-Host "  WARNING: Failed to clear proxy: $_"
}

# 0d. Reset WinSock and IP stack (can help with connectivity issues)
Write-Host "  Resetting network stack..."
try {
    netsh winsock reset 2>$null
    netsh int ip reset 2>$null
    Write-Host "  Network stack reset complete"
}
catch {
    Write-Host "  WARNING: Network stack reset failed: $_"
}

# Quick network connectivity test
Write-Host "Testing network connectivity..."
$networkOk = $false
try {
    # Test 1: Can we ping the gateway?
    $gateway = (Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue | Select-Object -First 1).NextHop
    if ($gateway) {
        Write-Host "  Gateway: $gateway"
        $gatewayPing = Test-Connection -ComputerName $gateway -Count 1 -ErrorAction SilentlyContinue
        if ($gatewayPing) {
            Write-Host "  Gateway ping: OK" -ForegroundColor Green
        } else {
            Write-Host "  Gateway ping: FAILED" -ForegroundColor Red
        }
    }
    
    # Test 2: Can we reach external IPs?
    $externalPing = Test-Connection -ComputerName "8.8.8.8" -Count 1 -ErrorAction SilentlyContinue
    if ($externalPing) {
        Write-Host "  External IP (8.8.8.8): OK" -ForegroundColor Green
        $networkOk = $true
    } else {
        Write-Host "  External IP (8.8.8.8): FAILED" -ForegroundColor Red
    }
    
    # Test 3: Can we resolve DNS?
    try {
        $dnsTest = Resolve-DnsName -Name "google.com" -Type A -ErrorAction Stop -DnsOnly
        Write-Host "  DNS resolution: OK" -ForegroundColor Green
    } catch {
        Write-Host "  DNS resolution: FAILED" -ForegroundColor Red
    }
    
    # Test 4: Can we make HTTP requests?
    try {
        $httpTest = Invoke-WebRequest -Uri "http://www.msftconnecttest.com/connecttest.txt" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
        Write-Host "  HTTP connectivity: OK" -ForegroundColor Green
    } catch {
        Write-Host "  HTTP connectivity: FAILED - $($_.Exception.Message)" -ForegroundColor Red
    }
} catch {
    Write-Host "  Network test error: $_" -ForegroundColor Red
}

if (-not $networkOk) {
    Write-Host ""
    Write-Host "WARNING: Network connectivity issues detected!" -ForegroundColor Yellow
    Write-Host "The sandbox may not have proper internet access." -ForegroundColor Yellow
    Write-Host "Check: Host firewall, VPN, Hyper-V virtual switch settings" -ForegroundColor Yellow
    Write-Host ""
}

# Function to download and install Python if not available
function Install-Python {
    Write-Host "Python not found. Downloading and installing Python 3.12..."
    
    $pythonUrl = "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe"
    $installerPath = "$env:TEMP\python-installer.exe"
    
    Write-Host "Downloading Python from $pythonUrl..."
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $pythonUrl -OutFile $installerPath -UseBasicParsing
    }
    catch {
        Write-Error "Failed to download Python: $_"
        throw
    }
    
    Write-Host "Installing Python (this may take a minute)..."
    $installArgs = "/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1"
    Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait -NoNewWindow
    
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    
    # Verify installation
    $pythonPath = "C:\Program Files\Python312\python.exe"
    if (Test-Path $pythonPath) {
        Write-Host "Python installed successfully at: $pythonPath"
        return $pythonPath
    }
    
    # Try alternate location
    $pythonPath = "C:\Python312\python.exe"
    if (Test-Path $pythonPath) {
        Write-Host "Python installed successfully at: $pythonPath"
        return $pythonPath
    }
    
    throw "Python installation failed - executable not found"
}

# Function to find the mapped Python installation from pywinsandbox
function Find-MappedPython {
    Write-Host "Looking for Python installation..."
    
    # First check if Python is already installed system-wide
    $systemPaths = @(
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe"
    )
    foreach ($pythonPath in $systemPaths) {
        if (Test-Path $pythonPath) {
            try {
                $version = & $pythonPath --version 2>&1
                if ($version -match "Python") {
                    Write-Host "Found system Python: $pythonPath - $version"
                    return $pythonPath
                }
            }
            catch {
                continue
            }
        }
    }
    
    # Check PATH
    $pythonCommands = @("python", "py", "python3")
    foreach ($cmd in $pythonCommands) {
        try {
            $version = & $cmd --version 2>&1
            if ($version -match "Python") {
                Write-Host "Found Python via command '$cmd': $version"
                return $cmd
            }
        }
        catch {
            continue
        }
    }
    
    # Look for mapped shared folders on the desktop (pywinsandbox pattern)
    $desktopPath = "C:\Users\WDAGUtilityAccount\Desktop"
    $sharedFolders = Get-ChildItem -Path $desktopPath -Directory -ErrorAction SilentlyContinue
    
    foreach ($folder in $sharedFolders) {
        # Look for Python executables in shared folders
        $pythonPaths = @(
            "$($folder.FullName)\python.exe",
            "$($folder.FullName)\Scripts\python.exe",
            "$($folder.FullName)\bin\python.exe"
        )
        
        foreach ($pythonPath in $pythonPaths) {
            if (Test-Path $pythonPath) {
                try {
                    $version = & $pythonPath --version 2>&1
                    if ($version -match "Python") {
                        Write-Host "Found mapped Python: $pythonPath - $version"
                        return $pythonPath
                    }
                }
                catch {
                    continue
                }
            }
        }
        
        # Also check subdirectories that might contain Python
        $subDirs = Get-ChildItem -Path $folder.FullName -Directory -ErrorAction SilentlyContinue
        foreach ($subDir in $subDirs) {
            $pythonPath = "$($subDir.FullName)\python.exe"
            if (Test-Path $pythonPath) {
                try {
                    $version = & $pythonPath --version 2>&1
                    if ($version -match "Python") {
                        Write-Host "Found mapped Python in subdirectory: $pythonPath - $version"
                        return $pythonPath
                    }
                }
                catch {
                    continue
                }
            }
        }
    }
    
    # No Python found - need to install it
    return $null
}

try {
    # Step 1: Find or install Python
    Write-Host "Step 1: Finding or installing Python..."
    $pythonExe = Find-MappedPython
    
    if ($null -eq $pythonExe) {
        Write-Host "No Python found. Installing Python..."
        $pythonExe = Install-Python
    }
    
    Write-Host "Using Python: $pythonExe"
    
    # Verify Python works and show version
    $pythonVersion = & $pythonExe --version 2>&1
    Write-Host "Python version: $pythonVersion"

    # Step 2: Create a dedicated virtual environment in mapped Desktop folder (persistent)
    Write-Host "Step 2: Creating virtual environment (if needed)..."
    $cachePath = "C:\Users\WDAGUtilityAccount\Desktop\wsb_cache"
    $venvPath = "C:\Users\WDAGUtilityAccount\Desktop\wsb_cache\venv"
    if (!(Test-Path $venvPath)) {
        Write-Host "Creating venv at: $venvPath"
        & $pythonExe -m venv $venvPath
    }
    else {
        Write-Host "Venv already exists at: $venvPath"
    }
    # Hide the folder to keep Desktop clean
    try {
        $item = Get-Item $cachePath -ErrorAction SilentlyContinue
        if ($item) {
            if (-not ($item.Attributes -band [IO.FileAttributes]::Hidden)) {
                $item.Attributes = $item.Attributes -bor [IO.FileAttributes]::Hidden
            }
        }
    }
    catch { }
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    if (!(Test-Path $venvPython)) {
        throw "Virtual environment Python not found at $venvPython"
    }
    Write-Host "Using venv Python: $venvPython"

    # Step 3: Check if cua-computer-server is already installed (pre-installed from host)
    Write-Host "Step 3: Checking for cua-computer-server..."
    
    $computerServerInstalled = $false
    try {
        $result = & $venvPython -c "import computer_server; print('OK')" 2>&1
        if ($result -eq "OK") {
            Write-Host "cua-computer-server is already installed (pre-installed from host)"
            $computerServerInstalled = $true
        }
    }
    catch { }
    
    if (-not $computerServerInstalled) {
        Write-Host "cua-computer-server not found, attempting to install..."
        try {
            Write-Host "Upgrading pip..."
            & $venvPython -m pip install --upgrade pip --quiet 2>&1
            
            Write-Host "Installing cua-computer-server..."
            & $venvPython -m pip install cua-computer-server 2>&1
            
            Write-Host "Installing pystray and Pillow for tray launcher..."
            & $venvPython -m pip install pystray Pillow --quiet 2>&1
        }
        catch {
            Write-Host "WARNING: Package installation failed (no network?). Continuing anyway..."
        }
    }
    
    Write-Host "Package check completed."

    # Step 4: Start computer server in background using the venv Python
    Write-Host "Step 4: Starting computer server in background..."
    Write-Host "Starting computer server with: $venvPython"
    
    # Start the computer server in the background
    $serverProcess = Start-Process -FilePath $venvPython -ArgumentList "-m", "computer_server.main" -WindowStyle Hidden -PassThru
    Write-Host "Computer server started in background with PID: $($serverProcess.Id)"
    
    # Give it a moment to start
    Start-Sleep -Seconds 3
    
    # Check if the process is still running
    if (Get-Process -Id $serverProcess.Id -ErrorAction SilentlyContinue) {
        Write-Host "Computer server is running successfully in background"
    }
    else {
        throw "Computer server failed to start or exited immediately"
    }

    # Step 5: Start tray launcher for workflow control
    Write-Host "Step 5: Starting tray launcher..."
    $desktopPath = "C:\Users\WDAGUtilityAccount\Desktop"
    $sharedFolders = Get-ChildItem -Path $desktopPath -Directory -ErrorAction SilentlyContinue
    Write-Host "Found folders on desktop: $($sharedFolders.Name -join ', ')"
    $trayLauncherPath = $null
    foreach ($folder in $sharedFolders) {
        $candidate = Join-Path $folder.FullName "sandbox\tray_launcher.pyw"
        Write-Host "Checking: $candidate"
        if (Test-Path $candidate) {
            $trayLauncherPath = $candidate
            Write-Host "Found tray launcher!"
            break
        }
    }
    if ($trayLauncherPath) {
        Write-Host "Found tray launcher at: $trayLauncherPath"
        $venvPythonw = Join-Path $venvPath "Scripts\pythonw.exe"
        Write-Host "Using pythonw: $venvPythonw"
        if (Test-Path $venvPythonw) {
            Start-Process -FilePath $venvPythonw -ArgumentList $trayLauncherPath -WindowStyle Hidden
            Write-Host "Tray launcher started - look for green icon in system tray"
        }
        else {
            Write-Host "pythonw.exe not found at $venvPythonw"
        }
    }
    else {
        Write-Host "Tray launcher not found in shared folders"
        Write-Host "You can manually run: sandbox\Start_Tray_Launcher.bat from the cua folder"
    }

}
catch {
    Write-Error "Setup failed: $_"
    Write-Host "Error details: $($_.Exception.Message)"
    Write-Host "Stack trace: $($_.ScriptStackTrace)"
    Write-Host ""
    Write-Host "Press any key to close this window..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host ""
Write-Host "Setup completed successfully!"
Write-Host "Press any key to close this window..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
