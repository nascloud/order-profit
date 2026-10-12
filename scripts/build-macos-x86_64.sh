#!/usr/bin/env bash
set -euo pipefail

clean_args=()
if [[ $# -gt 0 ]]; then
    if [[ $# -ne 1 || "$1" != "--clean" ]]; then
        echo "Usage: bash scripts/build-macos-x86_64.sh [--clean]" >&2
        exit 2
    fi
    clean_args=(--clean)
fi

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "x86_64" ]]; then
    echo "Build on macOS with an x86_64 shell and Python; cross-compilation is not supported." >&2
    exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required: https://docs.astral.sh/uv/" >&2
    exit 1
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export PYTHONIOENCODING=utf-8
venv="$root/.venv-macos-x86_64"
if [[ ! -x "$venv/bin/python" ]]; then
    uv venv --python 3.13 "$venv"
fi
python="$venv/bin/python"
"$python" -c 'import platform, sys; sys.exit(0 if sys.platform == "darwin" and platform.machine() == "x86_64" else "Build Python must be macOS x86_64")'
uv pip install --python "$python" -e '.[build]'

version="$("$python" -c 'import order_profit; print(order_profit.__version__)')"
exe_name="order-profit-cli-v${version}-macos-x86_64"
"$python" -m PyInstaller ${clean_args[@]+"${clean_args[@]}"} \
    --noconfirm \
    --onefile \
    --console \
    --target-arch x86_64 \
    --hidden-import openpyxl \
    --hidden-import xlrd \
    --collect-data tzdata \
    --name "$exe_name" \
    --paths src \
    src/order_profit/__main__.py

package_root="$root/dist/order-profit-cli-skill-v${version}-macos-x86_64"
skill_root="$package_root/order-profit-cli"
if [[ -d "$package_root" ]]; then
    rm -rf "$package_root"
fi
mkdir -p "$package_root"
cp -R "$root/skills/order-profit-cli" "$skill_root"
mkdir -p "$skill_root/assets"
cp "$root/dist/$exe_name" "$skill_root/assets/order-profit-cli-macos-x86_64"
chmod +x "$skill_root/assets/order-profit-cli-macos-x86_64" "$skill_root/scripts/order-profit.sh"
archive="${package_root}.zip"
ditto -c -k --keepParent "$skill_root" "$archive"

printf 'CLI: %s\nSkill: %s\nArchive: %s\n' "$root/dist/$exe_name" "$skill_root" "$archive"
