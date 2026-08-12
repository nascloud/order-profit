param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$utf8 = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = $utf8
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$env:PYTHONIOENCODING = "utf-8"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required: https://docs.astral.sh/uv/"
}
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    uv venv --python 3.13 .venv
}
uv pip install --python .venv\Scripts\python.exe -e ".[build]"

$version = & .venv\Scripts\python.exe -c "import order_profit; print(order_profit.__version__)"
$name = "order-profit-v$version"
$arguments = @(
    "--noconfirm"
    "--onefile"
    "--windowed"
    "--name", $name
    "--paths", "src"
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
