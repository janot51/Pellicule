# Installation Pellicule sous Windows (Python 3.11+)
$ErrorActionPreference = "Stop"

function Find-Python {
    foreach ($tag in @("-3.12", "-3.11", "-3")) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $v = & py $tag -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v -and ([version]$v -ge [version]"3.11")) {
                return @("py", $tag)
            }
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $v = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v -and ([version]$v -ge [version]"3.11")) {
            return @("python")
        }
    }
    return $null
}

function Get-VenvPythonVersion {
    param([string]$PythonExe)
    if (-not (Test-Path $PythonExe)) { return $null }
    $v = & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return $v
}

function Apply-PipWindowsWorkaround {
    # pip/platformdirs peut planter si le registre Common AppData est incomplet (WinError 2).
    if (-not $env:PROGRAMDATA) {
        $env:PROGRAMDATA = "C:\ProgramData"
    }
    $env:PIP_CONFIG_FILE = "NUL"
}

function Install-EditablePackage {
    param([string]$PythonExe)
    Apply-PipWindowsWorkaround
    & $PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Avertissement : mise a jour pip ignoree, nouvelle tentative..."
    }
    & $PythonExe -m pip install -e .
    if ($LASTEXITCODE -eq 0) { return $true }

    Write-Host "Nouvelle tentative sans isolation de build (hatchling)..."
    Apply-PipWindowsWorkaround
    & $PythonExe -m pip install hatchling
    if ($LASTEXITCODE -ne 0) { return $false }
    & $PythonExe -m pip install -e . --no-build-isolation
    return ($LASTEXITCODE -eq 0)
}

$py = Find-Python
if (-not $py) {
    Write-Error "Python 3.11 ou plus est requis. Installez-le depuis https://www.python.org/downloads/ (ou py -3.12)."
    exit 1
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$needVenv = $true
if (Test-Path $python) {
    $venvVer = Get-VenvPythonVersion $python
    if ($venvVer -and ([version]$venvVer -ge [version]"3.11")) {
        $needVenv = $false
    } else {
        Write-Host "Suppression du venv existant (Python $venvVer, 3.11+ requis)..."
        Remove-Item -Recurse -Force $venv
    }
}

if ($needVenv) {
    Write-Host "Creation du venv avec $($py -join ' ')..."
    if ($py[0] -eq "py") {
        & py $py[1] -m venv $venv
    } else {
        & $py[0] -m venv $venv
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de creation du venv."
        exit 1
    }
}

Write-Host "Installation du paquet (editable)..."
if (-not (Install-EditablePackage $python)) {
    Write-Error "Echec de pip install -e . Verifiez Python 3.11+ et l'acces au registre Windows (PROGRAMDATA)."
    exit 1
}

$toml = Join-Path $root "pellicule.toml"
$keys = Join-Path $root "pellicule.keys"
if (-not ((Test-Path $toml) -and (Test-Path $keys))) {
    Write-Host "Initialisation des fichiers de configuration..."
    & $python -m pellicule init
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de pellicule init."
        exit 1
    }
}

Write-Host ""
Write-Host "Termine. Prochaines etapes :"
Write-Host "  1. Editez pellicule.keys (voir pellicule.keys.example)"
Write-Host "  2. .\.venv\Scripts\Activate.ps1"
Write-Host "  3. pellicule doctor"
Write-Host "  4. pellicule"
