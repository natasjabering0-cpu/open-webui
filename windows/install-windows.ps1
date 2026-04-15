[CmdletBinding()]
param(
    [ValidateSet('cpu', 'cuda')]
    [string]$LlamaBackend = 'cpu',
    [switch]$LaunchAfterInstall,
    [switch]$RegisterStartup
)

$ErrorActionPreference = 'Stop'

$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $Root

function Invoke-WingetInstall {
    param(
        [string]$Id,
        [string]$Name,
        [string]$Scope = 'user',
        [string]$Override
    )

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "$Name is missing and winget was not found. Install $Name manually, then rerun this installer."
    }

    $arguments = @(
        'install',
        '--id', $Id,
        '-e',
        '--source', 'winget',
        '--silent',
        '--accept-package-agreements',
        '--accept-source-agreements'
    )

    if ($Scope) {
        $arguments += @('--scope', $Scope)
    }

    if ($Override) {
        $arguments += @('--override', $Override)
    }

    Invoke-CommandLine -FilePath $winget.Source -Arguments $arguments -WorkingDirectory $Root
}

function Test-PythonVersion {
    param(
        [hashtable]$PythonCommand
    )

    try {
        $versionOutput = & $PythonCommand.FilePath @($PythonCommand.Arguments + @('--version')) 2>&1
        if ($versionOutput -match 'Python (\d+)\.(\d+)') {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            return ($major -gt 3) -or ($major -eq 3 -and $minor -ge 11)
        }
        return $false
    } catch {
        return $false
    }
}

function Get-PythonCommand {
    $candidates = @()

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $candidates += @{
            FilePath = $py.Source
            Arguments = @('-3')
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $candidates += @{
            FilePath = $python.Source
            Arguments = @()
        }
    }

    foreach ($root in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python'),
        (Join-Path $env:ProgramFiles 'Python'),
        (Join-Path ${env:ProgramFiles(x86)} 'Python')
    )) {
        if (-not $root -or -not (Test-Path $root)) {
            continue
        }

        $pythonExe = Get-ChildItem -Path $root -Filter python.exe -Recurse -File -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($pythonExe) {
            $candidates += @{
                FilePath = $pythonExe.FullName
                Arguments = @()
            }
        }
    }

    foreach ($candidate in $candidates) {
        if (Test-PythonVersion $candidate) {
            return $candidate
        }
    }

    return $null
}

function Ensure-Python {
    $python = Get-PythonCommand
    if ($python) {
        return $python
    }

    Write-Host 'Python 3.11+ not found. Installing Python 3.11 via winget...'
    Invoke-WingetInstall -Id 'Python.Python.3.11' -Name 'Python'
    Start-Sleep -Seconds 5

    $python = Get-PythonCommand
    if (-not $python) {
        throw 'Python was installed, but the installer still cannot find a Python 3.11+ executable.'
    }

    return $python
}

function Get-NodeCommand {
    $candidates = @(
        (Get-Command npm.cmd -ErrorAction SilentlyContinue),
        (Get-Command npm -ErrorAction SilentlyContinue)
    ) | Where-Object { $_ }

    foreach ($root in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\nodejs'),
        (Join-Path $env:ProgramFiles 'nodejs'),
        (Join-Path ${env:ProgramFiles(x86)} 'nodejs')
    )) {
        if (-not $root -or -not (Test-Path $root)) {
            continue
        }

        $npmCmd = Get-ChildItem -Path $root -Filter npm.cmd -Recurse -File -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($npmCmd) {
            $candidates += @{
                Source = $npmCmd.FullName
            }
        }
    }

    foreach ($candidate in $candidates) {
        $path = $candidate.Source
        if ($path -and (Test-Path $path)) {
            return $path
        }
    }

    return $null
}

function Ensure-Node {
    $npm = Get-NodeCommand
    if ($npm) {
        return $npm
    }

    Write-Host 'Node.js not found. Installing Node.js LTS via winget...'
    Invoke-WingetInstall -Id 'OpenJS.NodeJS.LTS' -Name 'Node.js'
    Start-Sleep -Seconds 5

    $npm = Get-NodeCommand
    if (-not $npm) {
        throw 'Node.js was installed, but the installer still cannot find npm.cmd.'
    }

    return $npm
}

function Ensure-CudaToolkit {
    $nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $nvidiaSmi) {
        Write-Warning 'No NVIDIA driver was detected. The CUDA Toolkit can still install, but CUDA acceleration also needs a compatible NVIDIA driver from NVIDIA.'
    }

    Write-Host 'Installing NVIDIA CUDA Toolkit via winget...'
    Invoke-WingetInstall -Id 'Nvidia.CUDA' -Name 'NVIDIA CUDA Toolkit'
    Start-Sleep -Seconds 5
}

function Get-CMakePath {
    $cmake = Get-Command cmake -ErrorAction SilentlyContinue
    if ($cmake) {
        return $cmake.Source
    }

    foreach ($candidate in @(
        (Join-Path $env:ProgramFiles 'CMake\bin\cmake.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'CMake\bin\cmake.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\CMake\bin\cmake.exe')
    )) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Ensure-CMake {
    $cmakePath = Get-CMakePath
    if ($cmakePath) {
        $env:PATH = "$(Split-Path $cmakePath -Parent);$env:PATH"
        return
    }

    Write-Host 'CMake not found. Installing Kitware CMake via winget...'
    Invoke-WingetInstall -Id 'Kitware.CMake' -Name 'CMake'
    Start-Sleep -Seconds 5

    $cmakePath = Get-CMakePath
    if (-not $cmakePath) {
        throw 'CMake was installed, but the installer still cannot find cmake.exe.'
    }

    $env:PATH = "$(Split-Path $cmakePath -Parent);$env:PATH"
}

function Test-BuildToolsInstalled {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path $vswhere) {
        $installationPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
        if ($installationPath) {
            return $true
        }
    }

    foreach ($candidate in @(
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\2022\BuildTools'),
        (Join-Path $env:ProgramFiles 'Microsoft Visual Studio\2022\BuildTools')
    )) {
        if ($candidate -and (Test-Path $candidate)) {
            return $true
        }
    }

    return $false
}

function Ensure-BuildTools {
    if (Test-BuildToolsInstalled) {
        return
    }

    Write-Host 'Visual C++ build tools not found. Installing Visual Studio Build Tools...'
    Invoke-WingetInstall -Id 'Microsoft.VisualStudio.2022.BuildTools' -Name 'Visual Studio Build Tools' -Scope '' -Override '--wait --quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --norestart'
    Start-Sleep -Seconds 10
}

function Invoke-CommandLine {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )

    $display = @($FilePath) + $Arguments
    Write-Host ('+ ' + ($display -join ' '))

    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Command failed with exit code $($process.ExitCode): $($display -join ' ')"
    }
}

function Invoke-PythonScript {
    param(
        [string[]]$PythonCommand,
        [string[]]$ScriptArguments,
        [string]$WorkingDirectory
    )

    $filePath = $PythonCommand[0]
    $arguments = @()
    if ($PythonCommand.Count -gt 1) {
        $arguments += $PythonCommand[1..($PythonCommand.Count - 1)]
    }
    $arguments += $ScriptArguments
    Invoke-CommandLine -FilePath $filePath -Arguments $arguments -WorkingDirectory $WorkingDirectory
}

function New-Shortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [string]$Description,
        [string]$IconLocation
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    if ($Arguments) {
        $shortcut.Arguments = $Arguments
    }
    if ($WorkingDirectory) {
        $shortcut.WorkingDirectory = $WorkingDirectory
    }
    if ($Description) {
        $shortcut.Description = $Description
    }
    if ($IconLocation) {
        $shortcut.IconLocation = $IconLocation
    }
    $shortcut.Save()
}

function Get-VenvPython {
    $python = Join-Path $Root 'venv\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        throw "Virtualenv python not found at $python"
    }
    return $python
}

$pythonCommand = Ensure-Python
$npmCommand = Ensure-Node
$env:NPM_COMMAND = $npmCommand

if ($LlamaBackend -eq 'cuda') {
    Ensure-CudaToolkit
    Ensure-CMake
    Ensure-BuildTools
}

$pythonCommandArray = @($pythonCommand.FilePath) + $pythonCommand.Arguments
Invoke-PythonScript -PythonCommand $pythonCommandArray -ScriptArguments @('install-local.py', '--llama-backend', $LlamaBackend) -WorkingDirectory $Root

$venvPython = Get-VenvPython
$venvPythonw = Join-Path $Root 'venv\Scripts\pythonw.exe'

$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Legend AI'
$startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'

foreach ($folder in @($startMenu)) {
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
}

$trayShortcut = Join-Path $desktop 'Legend Tray.lnk'
$serverShortcut = Join-Path $desktop 'Open WebUI Server.lnk'
$trayStartMenuShortcut = Join-Path $startMenu 'Legend Tray.lnk'
$serverStartMenuShortcut = Join-Path $startMenu 'Open WebUI Server.lnk'

New-Shortcut -ShortcutPath $trayShortcut -TargetPath $venvPythonw -Arguments 'tray_assistant.py' -WorkingDirectory $Root -Description 'Start the tray app and Open WebUI' -IconLocation "$venvPythonw,0"
New-Shortcut -ShortcutPath $serverShortcut -TargetPath $venvPython -Arguments 'run-local.py' -WorkingDirectory $Root -Description 'Start Open WebUI directly' -IconLocation "$venvPython,0"
New-Shortcut -ShortcutPath $trayStartMenuShortcut -TargetPath $venvPythonw -Arguments 'tray_assistant.py' -WorkingDirectory $Root -Description 'Start the tray app and Open WebUI' -IconLocation "$venvPythonw,0"
New-Shortcut -ShortcutPath $serverStartMenuShortcut -TargetPath $venvPython -Arguments 'run-local.py' -WorkingDirectory $Root -Description 'Start Open WebUI directly' -IconLocation "$venvPython,0"

if ($RegisterStartup) {
    $startupShortcut = Join-Path $startup 'Legend Tray.lnk'
    New-Shortcut -ShortcutPath $startupShortcut -TargetPath $venvPythonw -Arguments 'tray_assistant.py' -WorkingDirectory $Root -Description 'Start the tray app and Open WebUI on login' -IconLocation "$venvPythonw,0"
}

if ($LaunchAfterInstall) {
    Start-Process -FilePath $venvPythonw -ArgumentList 'tray_assistant.py' -WorkingDirectory $Root
}

Write-Host ''
Write-Host 'Windows installation complete.'
Write-Host "Desktop shortcuts created for: $trayShortcut and $serverShortcut"
Write-Host "Start Menu folder: $startMenu"
