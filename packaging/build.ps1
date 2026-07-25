<#
.SYNOPSIS
  Build Mouser on Windows: C++ core (deskflow-core.exe) + PyInstaller onedir.

.DESCRIPTION
  Source: plan/mouser 阶段 6 step 34
  Prerequisites:
    - Visual Studio 2022 Build Tools (MSVC)
    - Qt 6.7 installed (via jurplel/install-qt-action or CMAKE_PREFIX_PATH env)
    - CMake + Ninja on PATH
    - Python 3.10+ with: pip install -r requirements-build.txt

  Output:
    build\bin\deskflow-core.exe   (C++ binary)
    dist\Mouser\Mouser.exe        (onedir, portable)

.PARAMETER QtPath
  Path to Qt installation (e.g. C:\Qt\6.7.3\msvc2022_64). If omitted, uses
  $env:CMAKE_PREFIX_PATH.

.EXAMPLE
  .\packaging\build.ps1
  .\packaging\build.ps1 -QtPath 'C:\Qt\6.7.3\msvc2022_64'
#>

[CmdletBinding()]
param(
  [string]$QtPath
)

$ErrorActionPreference = 'Stop'

# Resolve repo root (parent of packaging\).
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir '..')
Set-Location $RepoRoot

# Resolve Qt path: explicit param > $env:CMAKE_PREFIX_PATH.
if (-not $QtPath -and $env:CMAKE_PREFIX_PATH) { $QtPath = $env:CMAKE_PREFIX_PATH }
if (-not $QtPath) {
  throw "Qt not found. Pass -QtPath or set CMAKE_PREFIX_PATH. Example: -QtPath 'C:\Qt\6.7.3\msvc2022_64'"
}
$CmakePrefix = (Resolve-Path $QtPath).Path

Write-Host "==> Mouser Windows build"
Write-Host "    repo:   $RepoRoot"
Write-Host "    qt:     $CmakePrefix"

# Step 1: Configure & build C++ core (deskflow-core.exe only).
$BuildDir = Join-Path $RepoRoot 'build'
Write-Host "==> [1/3] cmake configure deskflow-core"
& cmake -S vendor/deskflow -B "$BuildDir" `
  -G Ninja `
  -DCMAKE_BUILD_TYPE=Release `
  -DCMAKE_PREFIX_PATH="$CmakePrefix" `
  -DBUILD_X11_SUPPORT=OFF
if ($LASTEXITCODE -ne 0) { throw "cmake configure failed" }

Write-Host "==> [2/3] cmake build deskflow-core"
$Jobs = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
& cmake --build "$BuildDir" --target deskflow-core -j $Jobs
if ($LASTEXITCODE -ne 0) { throw "cmake build failed" }

$Binary = Join-Path $BuildDir 'bin\deskflow-core.exe'
if (-not (Test-Path $Binary)) {
  throw "deskflow-core.exe not found at $Binary"
}
Write-Host "    built:  $Binary"

# Step 2: PyInstaller.
Write-Host "==> [3/3] pyinstaller mouser-win.spec"
& pyinstaller packaging/mouser-win.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

$OutDir = Join-Path $RepoRoot 'dist\Mouser'
if (-not (Test-Path $OutDir)) {
  throw "Mouser output directory not produced at $OutDir"
}

Write-Host "==> done: $OutDir"
