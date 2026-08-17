$ErrorActionPreference = "Stop"
$utf8 = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = $utf8
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$env:PYTHONIOENCODING = "utf-8"

$exe = Join-Path (Split-Path -Parent $PSScriptRoot) "assets\order-profit-cli.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Missing bundled CLI: $exe"
}

& $exe @args
exit $LASTEXITCODE
