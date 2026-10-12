#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "x86_64" ]]; then
    echo "This bundled CLI requires macOS x86_64 (Intel)." >&2
    exit 1
fi

skill_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exe="$skill_root/assets/order-profit-cli-macos-x86_64"
if [[ ! -x "$exe" ]]; then
    echo "Missing or non-executable bundled CLI: $exe" >&2
    exit 1
fi

export PYTHONIOENCODING=utf-8
exec "$exe" "$@"
