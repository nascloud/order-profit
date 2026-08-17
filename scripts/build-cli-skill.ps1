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
$exeName = "order-profit-cli-v$version"
$arguments = @(
    "--noconfirm"
    "--onefile"
    "--console"
    "--icon", "assets\app-icon.ico"
    "--name", $exeName
    "--paths", "src"
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
Copy-Item -LiteralPath "skills\order-profit-cli" -Destination $skillRoot -Recurse
New-Item -ItemType Directory -Path (Join-Path $skillRoot "assets") -Force | Out-Null
Copy-Item -LiteralPath "dist\$exeName.exe" -Destination (Join-Path $skillRoot "assets\order-profit-cli.exe")

$archive = Join-Path $root "dist\order-profit-cli-skill-v$version.zip"
Compress-Archive -LiteralPath $skillRoot -DestinationPath $archive -Force

Write-Host "CLI: $root\dist\$exeName.exe"
Write-Host "Skill: $skillRoot"
Write-Host "Archive: $archive"
