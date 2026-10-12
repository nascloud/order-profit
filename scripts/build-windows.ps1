param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$utf8 = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = $utf8
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$env:PYTHONIOENCODING = "utf-8"

if ($env:OS -ne "Windows_NT" -or -not [Environment]::Is64BitOperatingSystem) {
    throw "Build on native 64-bit Windows; cross-compilation is not supported."
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required: https://docs.astral.sh/uv/"
}
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    uv venv --python 3.13 .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
uv pip install --python .venv\Scripts\python.exe -e ".[build]"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .venv\Scripts\python.exe -c "import platform, struct; assert platform.system() == 'Windows' and platform.machine().upper() in ('AMD64', 'X86_64') and struct.calcsize('P') == 8, 'Windows x64 Python required'"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$version = & .venv\Scripts\python.exe -c "import order_profit; print(order_profit.__version__)"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$name = "订单利润核算-v$version"
$arguments = @(
    "--noconfirm"
    "--onefile"
    "--windowed"
    "--icon", "assets\app-icon.ico"
    "--name", $name
    "--paths", "src"
    "--hidden-import", "openpyxl"
    "--hidden-import", "xlrd"
    "--collect-data", "tzdata"
    "src\order_profit\desktop.py"
)
if ($Clean) {
    $arguments = @("--clean") + $arguments
}

& .venv\Scripts\python.exe -m PyInstaller @arguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Built: $root\dist\$name.exe"

& "$PSScriptRoot\build-cli-skill.ps1" -Clean:$Clean
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
