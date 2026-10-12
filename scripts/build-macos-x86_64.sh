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
"$python" - <<'PY'
from pathlib import Path
import tkinter
from PyInstaller.utils.hooks.tcl_tk import tcltk_info

tkinter.Tcl()
if not tcltk_info.available:
    raise SystemExit("Build Python must provide working Tcl/Tk for the desktop app.")
for directory, script in (
    (tcltk_info.tcl_data_dir, "init.tcl"),
    (tcltk_info.tk_data_dir, "tk.tcl"),
):
    if not directory or not (Path(directory) / script).is_file():
        raise SystemExit(f"Build Python is missing Tcl/Tk runtime resources: {script}")
for library in (tcltk_info.tcl_shared_library, tcltk_info.tk_shared_library):
    if not library or not Path(library).is_file():
        raise SystemExit("Build Python must provide bundleable Tcl and Tk shared libraries.")
PY

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

icon_tmp="$(mktemp -d "${TMPDIR:-/tmp}/order-profit-icon.XXXXXX")"
trap 'rm -rf "$icon_tmp"' EXIT
iconset="$icon_tmp/app.iconset"
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$root/assets/app-icon.png" \
        --out "$iconset/icon_${size}x${size}.png" >/dev/null
    sips -z "$((size * 2))" "$((size * 2))" "$root/assets/app-icon.png" \
        --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$iconset" -o "$icon_tmp/app.icns"

app_name="订单利润核算-v${version}-macos-x86_64"
"$python" -m PyInstaller ${clean_args[@]+"${clean_args[@]}"} \
    --noconfirm \
    --onedir \
    --windowed \
    --target-arch x86_64 \
    --hidden-import openpyxl \
    --hidden-import xlrd \
    --collect-data tzdata \
    --icon "$icon_tmp/app.icns" \
    --osx-bundle-identifier com.nascloud.order-profit \
    --specpath "$root/build/macos-ui" \
    --name "$app_name" \
    --paths src \
    src/order_profit/desktop.py

app="$root/dist/${app_name}.app"
# PyInstaller's CLI does not expose bundle version fields. Update them and
# renew the outer ad-hoc signature without changing nested library signatures.
"$python" - "$app/Contents/Info.plist" "$version" <<'PY'
import plistlib
from pathlib import Path
import sys

path = Path(sys.argv[1])
with path.open("rb") as stream:
    metadata = plistlib.load(stream)
metadata.update(
    CFBundleDisplayName="订单利润核算",
    CFBundleShortVersionString=sys.argv[2],
    CFBundleVersion=sys.argv[2],
)
with path.open("wb") as stream:
    plistlib.dump(metadata, stream)
PY
codesign --force --sign - "$app"
app_archive="${app}.zip"
ditto -c -k --keepParent "$app" "$app_archive"

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

printf 'CLI: %s\nUI: %s\nUI archive: %s\nSkill archive: %s\n' \
    "$root/dist/$exe_name" "$app" "$app_archive" "$archive"
