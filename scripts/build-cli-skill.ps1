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
$exeName = "order-profit-cli-v$version"
$arguments = @(
    "--noconfirm"
    "--onefile"
    "--console"
    "--icon", "assets\app-icon.ico"
    "--name", $exeName
    "--paths", "src"
    "--hidden-import", "openpyxl"
    "--hidden-import", "xlrd"
    "--collect-data", "tzdata"
    "src\order_profit\__main__.py"
)
if ($Clean) {
    $arguments = @("--clean") + $arguments
}

& .venv\Scripts\python.exe -m PyInstaller @arguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$packageRoot = Join-Path $root "dist\order-profit-cli-skill-v$version"
$skillRoot = Join-Path $packageRoot "order-profit-cli"
if (Test-Path -LiteralPath $packageRoot) {
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
Copy-Item -LiteralPath "skills\order-profit-cli" -Destination $skillRoot -Recurse
New-Item -ItemType Directory -Path (Join-Path $skillRoot "assets") -Force | Out-Null
Copy-Item -LiteralPath "dist\$exeName.exe" -Destination (Join-Path $skillRoot "assets\order-profit-cli.exe")

$archive = Join-Path $root "dist\order-profit-cli-skill-v$version.zip"
Compress-Archive -LiteralPath $skillRoot -DestinationPath $archive -Force

Write-Host "CLI: $root\dist\$exeName.exe"
Write-Host "Skill: $skillRoot"
Write-Host "Archive: $archive"
