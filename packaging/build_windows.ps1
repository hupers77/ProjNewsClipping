# Build the Windows installer on a Windows PC (no GitHub Actions needed).
#
#   Double-click packaging\build_windows.bat   (or run this script in PowerShell)
#
# Output: dist\NewsClipping-Setup-<version>.exe
# What it does: installs uv / Inno Setup if missing (via winget), builds the app with PyInstaller,
# smoke-tests it, then compiles the installer. Internet access is required.
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 reads BOM-less files as ANSI).

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host "== Project folder: $(Get-Location)"

function Step($msg) { Write-Host ""; Write-Host "== $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }

# ---- 1. uv (Python package manager; it also downloads Python itself) ----
Step "1/6 Checking uv"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found - installing"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id astral-sh.uv -e --silent --accept-package-agreements --accept-source-agreements
    } else {
        powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
    }
    # make the fresh install visible in this session
    $env:Path = "$env:USERPROFILE\.local\bin;$env:LOCALAPPDATA\Microsoft\WinGet\Links;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Fail "uv was installed but is not on PATH. Close this window, open a new one and run the script again."
    }
}
uv --version

# ---- 2. Inno Setup (installer compiler) ----
Step "2/6 Checking Inno Setup"
function Find-Iscc {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}
$iscc = Find-Iscc
if (-not $iscc) {
    Write-Host "Inno Setup not found - installing with winget"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "winget is not available. Install Inno Setup 6 manually from https://jrsoftware.org/isdl.php and run again."
    }
    winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements
    $iscc = Find-Iscc
    if (-not $iscc) { Fail "Inno Setup installation not found. Install it manually from https://jrsoftware.org/isdl.php" }
}
Write-Host "ISCC: $iscc"

# ---- 3. Dependencies ----
Step "3/6 Installing build dependencies (uv sync)"
uv sync --group build
if ($LASTEXITCODE -ne 0) { Fail "uv sync failed" }

# ---- 4. PyInstaller ----
Step "4/6 Building the app (PyInstaller) - takes a few minutes"
uv run python packaging/write_build_info.py
if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist\NewsClipping) { Remove-Item dist\NewsClipping -Recurse -Force }
uv run pyinstaller packaging/newsclipping.spec --noconfirm
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed" }

# ---- 5. Smoke test (runs every screen script inside the bundle) ----
Step "5/6 Smoke test"
$log = Join-Path $env:TEMP "newsclip-smoke.log"
if (Test-Path $log) { Remove-Item $log -Force }
$p = Start-Process -FilePath "dist\NewsClipping\NewsClipping.exe" -ArgumentList "--smoke" -Wait -PassThru
if (Test-Path $log) { Get-Content $log }
if ($p.ExitCode -ne 0) { Fail "Smoke test failed (see lines above; app log: $env:LOCALAPPDATA\ProjNewsClipping\app.log)" }

# ---- 6. Installer ----
Step "6/6 Creating the installer (Inno Setup)"
$korean = "packaging\Korean.isl"
if (-not (Test-Path $korean)) {
    try {
        Invoke-WebRequest "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/Unofficial/Korean.isl" -OutFile $korean
    } catch {
        Write-Host "Could not download Korean.isl - the installer wizard will be in English."
    }
}
$version = (uv run python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
& $iscc "/DAppVersion=$version" "packaging\installer.iss"
if ($LASTEXITCODE -ne 0) { Fail "Inno Setup compile failed" }

$out = Get-ChildItem dist\NewsClipping-Setup-*.exe | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host ""
Write-Host "DONE: $($out.FullName)" -ForegroundColor Green
Start-Process explorer.exe "/select,`"$($out.FullName)`""
