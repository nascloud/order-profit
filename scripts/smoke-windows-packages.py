"""Exercise real Windows packages with synthetic data and an interactive desktop.

Run with the build venv: python scripts/smoke-windows-packages.py --dist dist
Driver-only dependencies: openpyxl, pyautogui, Pillow, psutil. No source imports.
Child packages receive a system-only PATH, with Python/venv variables removed.
Screenshots, command logs, manifests and acceptance JSON remain in dist; generated
inputs, extracted skill and reports are removed when the run finishes.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import platform
import runpy
import shutil
import subprocess
import tempfile
import time
import traceback
import zipfile

from openpyxl import Workbook, load_workbook

from order_profit import __version__ as VERSION
from order_profit.config import SPEC_VERSION
TITLE = "订单利润核算｜店铺经营复盘"
EXPECTED_FREIGHT = {
    "1001": 1508, "2001": 0, "2002": 1000, "3001": 0,
    "3002": 1000, "4001": 0, "4002": 0,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_xlsx(path: Path, sheet: str, columns: list[str], rows: list[list]) -> None:
    book = Workbook()
    page = book.active
    page.title = sheet
    page.append(columns)
    for row in rows:
        page.append(row)
    book.save(path)
    book.close()


def fixtures(root: Path) -> dict[str, Path]:
    paths = {name: root / f"{name}.xlsx" for name in ("orders", "costs", "freight")}
    columns = [
        "主订单编号", "商品ID", "商品标题", "商品属性", "购买数量", "订单状态",
        "商家编码", "买家应付货款", "退款状态", "退款金额", "订单付款时间",
        "商家备注", "物流单号",
    ]
    rows = []
    for order, product, marker, closed, waybill in [
        ("O100", "1001", "", False, "CHILD"),
        ("O200", "2001", "D", False, "MIX-BRUSH"),
        ("O200", "2002", "", False, "MIX-NORMAL"),
        ("O300", "3001", "S", False, "CLOSE-BRUSH"),
        ("O300", "3002", "D", True, "CLOSED"),
        ("O400", "4001", "D", False, "PURE-D"),
        ("O400", "4002", "s", False, "PURE-S"),
    ]:
        rows.append([
            order, product, "合成验收商品", "白色", 1,
            "交易关闭" if closed else "交易成功", "SKU1", "20.00", "无退款", "0.00",
            "2026-08-01 12:00:00", marker, waybill,
        ])
    write_xlsx(paths["orders"], "export", columns, rows)
    write_xlsx(paths["costs"], "Sheet1", ["编码", "成本", "运费"], [["SKU1", "1.50", "99.00"]])
    write_xlsx(paths["freight"], "Sheet1", ["运单号", "订单编码", "总运费"], [
        ["CHILD", "O100_CHILD", "0.00"],
        ["MOTHER", "O100_MOTHER_suffix", "12.01"],
        ["SECOND", "O100_SECOND", "3.07"],
        ["MIX", "O200_MIX", "10.00"],
        ["CLOSE", "O300_CLOSE", "10.00"],
        ["PURE", "O400_PURE", "10.00"],
        ["ORPHAN", "", "90.00"],
    ])
    return paths


def cents(value: object) -> int:
    number = Decimal(str(value)) * 100
    require(number == number.to_integral_value(), f"Non-integer cents: {value}")
    return int(number)


def check_report(output: Path, freight: Path, dist: Path, label: str) -> dict:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    # Preserve the actual program output before checking it, including on failure.
    shutil.copy2(output / "manifest.json", dist / f"{label}-manifest.json")
    for key, expected in (("program_version", VERSION), ("spec_version", SPEC_VERSION),
                          ("status", "FINAL")):
        require(manifest[key] == expected, f"{label}: {key} != {expected}")
    checks = manifest["reconciliation"]
    require(bool(checks) and all(item["passed"] is True for item in checks),
            f"{label}: reconciliation failed: {checks}")
    warnings = [issue for issue in manifest["issues"]
                if issue["code"] == "FREIGHT_ORDER_ID_MISSING"]
    require(len(warnings) == 1, f"{label}: expected one orphan freight warning")
    warning = warnings[0]
    location = warning["location"]
    require(warning["severity"] == "warning" and location["row"] == 8
            and location["field"] == "订单编码" and location["sheet"] == "Sheet1"
            and Path(location["file"]).resolve() == freight.resolve(),
            f"{label}: incorrect warning location: {warning}")
    summary = manifest["summary"]
    expected_summary = {
        "已核算运费_分": 2508, "已核算货品成本_分": 300, "关闭已发货损失_分": 1150,
    }
    for key, expected in expected_summary.items():
        require(summary[key] == expected, f"{label}: {key}: {summary[key]} != {expected}")
    book = load_workbook(output / "订单成本利润分析.xlsx", read_only=True, data_only=True)
    try:
        actual = {}
        closed_products = []
        for name in ("正常订单明细", "关闭已发货"):
            records = iter(book[name].values)
            columns = next(records)
            for values in records:
                row = dict(zip(columns, values, strict=True))
                product = str(row["商品ID"])
                require(product not in actual, f"Duplicate report product: {product}")
                actual[product] = cents(row["核算运费"])
                expected_cost = 150 if product in {"1001", "2002", "3002"} else 0
                require(cents(row["核算成本"]) == expected_cost,
                        f"{label}: product {product} cost mismatch")
                if name == "关闭已发货":
                    closed_products.append(product)
        require(actual == EXPECTED_FREIGHT, f"{label}: freight allocation mismatch: {actual}")
        require(closed_products == ["3002"], f"{label}: wrong closed partition")
        require(sum(actual.values()) == 3508, f"{label}: detail freight does not reconcile")
        overview = {row[0]: row[1] for row in list(book["01_经营总览"].values)[1:]}
        for key, expected in summary.items():
            if key.endswith("_分"):
                require(cents(overview[key.removesuffix("_分")]) == expected,
                        f"{label}: Excel/manifest money mismatch for {key}")
    finally:
        book.close()
    html = (output / "店铺经营复盘.html").read_text(encoding="utf-8")
    require("FINAL" in html and "店铺经营复盘" in html, f"{label}: missing HTML report")
    browser_check = runpy.run_path(str(Path(__file__).with_name("check-report-browser.py")))[
        "check_report_browser"
    ](output / "店铺经营复盘.html", dist / f"{label}-report-browser.png")
    shutil.copy2(output / "店铺经营复盘.html", dist / f"{label}-report.html")
    return {"status": "passed", "freight_cents_by_product": actual,
             "expected_summary": expected_summary, "warning": warning,
             "reconciliation": checks, "browser": browser_check}


def packaged_environment() -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith(("PYTHON", "VIRTUAL_ENV", "CONDA", "UV_"))
    }
    system = Path(os.environ["SystemRoot"])
    environment["PATH"] = os.pathsep.join(map(str, [
        system / "System32", system / "System32" / "WindowsPowerShell" / "v1.0",
    ]))
    for executable in ("python", "python3", "py"):
        require(shutil.which(executable, path=environment["PATH"]) is None,
                f"Unexpected Python on package PATH: {executable}")
    return environment


def run_cli(command: list[str], paths: dict[str, Path], output: Path,
            environment: dict[str, str], dist: Path, label: str) -> dict:
    args = command + ["run"]
    for role, path in paths.items():
        args += [f"--{role}", str(path)]
    args += ["--start-date", "2026-08-01", "--end-date", "2026-08-07",
             "--platform", "tmall", "--output-dir", str(output), "--require-complete"]
    log = dist / f"{label}.log"
    with log.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(args, ensure_ascii=False) + "\n")
        stream.flush()
        completed = subprocess.run(args, cwd=output.parent, env=environment, stdout=stream,
                                   stderr=subprocess.STDOUT, timeout=180, check=False)
    require(completed.returncode == 0, f"{label}: exit {completed.returncode}; see {log}")
    return check_report(output, paths["freight"], dist, label)


def screenshot(dist: Path, name: str) -> None:
    import pyautogui
    from PIL import ImageStat

    image = pyautogui.screenshot()
    image.save(dist / f"{name}.png")
    require(max(ImageStat.Stat(image).stddev) > 5, "Desktop capture is blank/locked")


def run_ui(exe: Path, paths: dict[str, Path], output: Path,
           environment: dict[str, str], dist: Path) -> dict:
    import psutil
    import pyautogui

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SetProcessDPIAware()
    pyautogui.PAUSE = 0.15
    process = subprocess.Popen([str(exe)], cwd=output.parent, env=environment)
    owned = psutil.Process(process.pid)
    observed = []
    root_handle = None

    def windows() -> list[tuple[int, str]]:
        pids = {process.pid}
        try:
            pids.update(child.pid for child in owned.children(recursive=True))
        except psutil.NoSuchProcess:
            pass
        found = []

        @callback_type
        def visit(handle, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            if pid.value in pids and user32.IsWindowVisible(handle):
                text = ctypes.create_unicode_buffer(1024)
                user32.GetWindowTextW(handle, text, len(text))
                found.append((handle, text.value))
            return True

        user32.EnumWindows(visit, 0)
        return found

    def wait_window(title: str, timeout: int = 90) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for handle, text in windows():
                if text not in observed:
                    observed.append(text)
                if text == title:
                    return handle
                if text in {"生成失败", "无法开始"}:
                    raise RuntimeError(f"UI reported error dialog: {text}")
            require(process.poll() is None, f"UI exited before {title}: {process.returncode}")
            time.sleep(0.25)
        raise RuntimeError(f"UI window not observed: {title}; observed={observed}")

    def fill(value: str) -> None:
        # Synthetic fixture paths intentionally use an ASCII temp directory.
        require(value.isascii(), f"GUI keyboard input requires ASCII path: {value}")
        pyautogui.hotkey("ctrl", "a")
        pyautogui.write(value, interval=0.01)

    try:
        root_handle = wait_window(TITLE)
        user32.ShowWindow(root_handle, 3)  # Maximize so all controls remain on screen.
        user32.SetForegroundWindow(root_handle)
        time.sleep(1)
        rect = wintypes.RECT()
        require(bool(user32.GetWindowRect(root_handle, ctypes.byref(rect))), "No UI geometry")
        require(rect.right - rect.left >= 760 and rect.bottom - rect.top >= 680,
                "Runner desktop is too small for the complete application")
        screenshot(dist, "ui-open")
        # Tk's initial focus is the toplevel. Tab enters the first input; the
        # existing desktop form has one Entry and one browse Button per file.
        pyautogui.press("tab")
        fill(str(paths["orders"]))
        pyautogui.press("tab", presses=2)
        fill(str(paths["costs"]))
        pyautogui.press("tab", presses=2)
        fill(str(paths["freight"]))
        pyautogui.press("tab", presses=8)
        fill("2026-08-01")
        pyautogui.press("tab")
        fill("2026-08-07")
        pyautogui.press("tab", presses=4)
        fill(str(output))
        pyautogui.press("tab", presses=2)
        screenshot(dist, "ui-filled")
        pyautogui.press("space")
        wait_window("经营复盘已生成", timeout=180)
        time.sleep(0.5)
        screenshot(dist, "ui-generated-dialog")
        pyautogui.press("enter")
        time.sleep(0.5)
        screenshot(dist, "ui-generated")
        result = check_report(output, paths["freight"], dist, "ui")
        result.update({"observed_window_titles": observed,
                       "window_rect": [rect.left, rect.top, rect.right, rect.bottom],
                       "interaction": "native HWND observation and real keyboard input"})
        return result
    except Exception:
        screenshot(dist, "ui-failed")
        raise
    finally:
        (dist / "ui-windows.json").write_text(
            json.dumps(observed, ensure_ascii=False, indent=2), encoding="utf-8")
        if root_handle:
            user32.PostMessageW(root_handle, 0x0010, 0, 0)  # WM_CLOSE
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Only terminate this invocation's process tree, including the
            # PyInstaller onefile child; do not touch unrelated desktop apps.
            subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"),
                            "/PID", str(process.pid), "/T", "/F"], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            process.wait(timeout=15)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    dist = args.dist.resolve()
    dist.mkdir(parents=True, exist_ok=True)
    evidence = {"status": "failed", "program_version": VERSION, "spec_version": SPEC_VERSION,
                "platform": platform.platform(), "checks": {}}
    try:
        require(platform.system() == "Windows" and platform.machine().upper() in
                {"AMD64", "X86_64"}, "Run acceptance on native Windows x64")
        packages = {"ui": dist / f"订单利润核算-v{VERSION}.exe",
                    "cli": dist / f"order-profit-cli-v{VERSION}.exe",
                    "skill": dist / f"order-profit-cli-skill-v{VERSION}.zip"}
        evidence["packages"] = {}
        for role, path in packages.items():
            require(path.is_file(), f"Missing {role}: {path}")
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            evidence["packages"][role] = {"name": path.name, "sha256": digest,
                                           "bytes": path.stat().st_size}
        environment = packaged_environment()
        evidence["package_path"] = environment["PATH"]
        with tempfile.TemporaryDirectory(prefix="order-profit-packages-") as temporary:
            root = Path(temporary)
            paths = fixtures(root)
            evidence["checks"]["cli"] = run_cli(
                [str(packages["cli"])], paths, root / "cli-output", environment, dist, "cli")
            extracted = root / "skill"
            with zipfile.ZipFile(packages["skill"]) as archive:
                for name in archive.namelist():
                    require((extracted / name).resolve().is_relative_to(extracted.resolve()),
                            f"Unsafe skill archive member: {name}")
                archive.extractall(extracted)
            launcher = extracted / "order-profit-cli" / "scripts" / "order-profit.ps1"
            require(launcher.is_file(), f"Missing skill launcher: {launcher}")
            bundled = extracted / "order-profit-cli" / "assets" / "order-profit-cli.exe"
            with bundled.open("rb") as stream:
                require(hashlib.file_digest(stream, "sha256").hexdigest() ==
                        evidence["packages"]["cli"]["sha256"], "Skill CLI differs from standalone")
            powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            evidence["checks"]["skill"] = run_cli(
                [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(launcher)], paths, root / "skill-output", environment, dist, "skill")
            evidence["checks"]["ui"] = run_ui(
                packages["ui"], paths, root / "ui-output", environment, dist)
        evidence["status"] = "passed"
        return 0
    except Exception:
        evidence["error"] = traceback.format_exc()
        print(evidence["error"], flush=True)
        return 1
    finally:
        (dist / "windows-package-acceptance.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Windows package acceptance: {evidence['status']}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
