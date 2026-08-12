[CmdletBinding()]
param(
    [string]$InstallDir,
    [switch]$NoPath
)

$ErrorActionPreference = 'Stop'

if (-not $InstallDir) {
    $base = $env:LOCALAPPDATA
    if (-not $base) {
        $base = Join-Path $HOME 'AppData\Local'
    }
    $InstallDir = Join-Path $base 'Programs\codex-usage'
}

$pythonExe = $null
$pythonArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = 'py'
    $pythonArgs = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = 'python'
} else {
    throw 'Python 3.9+ was not found. Install Python first and ensure py.exe or python.exe is on PATH.'
}

& $pythonExe @pythonArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw 'codex-usage requires Python 3.9 or newer.'
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot 'codex-usage') (Join-Path $InstallDir 'codex-usage')
Copy-Item -Force (Join-Path $PSScriptRoot 'codex-usage.cmd') (Join-Path $InstallDir 'codex-usage.cmd')

if (-not $NoPath) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @()
    if ($userPath) {
        $parts = $userPath -split ';' | Where-Object { $_ }
    }
    $alreadyPresent = $false
    foreach ($part in $parts) {
        if ($part.TrimEnd('\') -ieq $InstallDir.TrimEnd('\')) {
            $alreadyPresent = $true
            break
        }
    }
    if (-not $alreadyPresent) {
        if ($userPath) {
            $newPath = "$userPath;$InstallDir"
        } else {
            $newPath = $InstallDir
        }
        [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    }
    if (-not (($env:Path -split ';') | Where-Object { $_.TrimEnd('\') -ieq $InstallDir.TrimEnd('\') })) {
        $env:Path = "$InstallDir;$env:Path"
    }
}

Write-Host "Installed codex-usage to $InstallDir"
if (-not $NoPath) {
    Write-Host 'The install directory is on your user PATH. New terminals will pick it up automatically.'
}
& (Join-Path $InstallDir 'codex-usage.cmd') --version
