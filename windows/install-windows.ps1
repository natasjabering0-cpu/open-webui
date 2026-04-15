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

function Get-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{
            FilePath = $py.Source
            Arguments = @('-3')
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{
            FilePath = $python.Source
            Arguments = @()
        }
    }

    throw 'Python 3.11+ was not found in PATH.'
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

$pythonCommand = Get-PythonCommand
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
