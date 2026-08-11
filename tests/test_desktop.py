from __future__ import annotations

from datetime import date
from pathlib import Path
from tkinter import Tcl

import pytest

from order_profit.config import Platform
from order_profit.desktop import DesktopApp, format_desktop_error
from order_profit.errors import InputContractError
from order_profit.models import Issue, Severity, SourceLocation


def test_desktop_builds_config_without_opening_window(tmp_path: Path) -> None:
    app = object.__new__(DesktopApp)
    interpreter = Tcl()
    from tkinter import BooleanVar, StringVar

    app.paths = {
        "orders": StringVar(interpreter, str(tmp_path / "orders.xlsx")),
        "costs": StringVar(interpreter, ""),
        "freight": StringVar(interpreter, ""),
        "after_sales": StringVar(interpreter, ""),
        "promotion": StringVar(interpreter, ""),
        "supplements": StringVar(interpreter, ""),
        "output_dir": StringVar(interpreter, str(tmp_path / "output")),
    }
    app.start_date = StringVar(interpreter, "2026-08-01")
    app.end_date = StringVar(interpreter, "2026-08-07")
    app.platform = StringVar(interpreter, "tmall")
    app.overwrite = BooleanVar(interpreter, False)
    app.require_complete = BooleanVar(interpreter, True)

    config = app._build_config()

    assert config.start_date == date(2026, 8, 1)
    assert config.end_date == date(2026, 8, 7)
    assert config.platform is Platform.TMALL
    assert config.require_complete is True


def test_desktop_formats_structured_input_error() -> None:
    issue = Issue(
        code="INPUT_KEY_EMPTY",
        severity=Severity.ERROR,
        message="编码是必需匹配键，不能为空",
        location=SourceLocation(
            file=r"C:\data\成本表.xlsx",
            sheet="Sheet1",
            row=173,
            field="编码",
        ),
        suggestion="请补齐匹配键或删除无效行后重试",
    )
    error = InputContractError(
        "成本编码表的编码不能为空，源行：[173]",
        code="INPUT_KEY_EMPTY",
        issues=[issue],
    )

    message = format_desktop_error(error)

    assert "错误代码：INPUT_KEY_EMPTY" in message
    assert "工作表：Sheet1" in message
    assert "Excel 行号：173" in message
    assert "字段：编码" in message
    assert "清空界面中的“成本编码表”" in message


def test_desktop_requires_orders_path(tmp_path: Path) -> None:
    app = object.__new__(DesktopApp)
    interpreter = Tcl()
    from tkinter import BooleanVar, StringVar

    app.paths = {
        key: StringVar(interpreter, str(tmp_path / "output") if key == "output_dir" else "")
        for key in (
            "orders",
            "costs",
            "freight",
            "after_sales",
            "promotion",
            "supplements",
            "output_dir",
        )
    }
    app.start_date = StringVar(interpreter, "2026-08-01")
    app.end_date = StringVar(interpreter, "2026-08-07")
    app.platform = StringVar(interpreter, "tmall")
    app.overwrite = BooleanVar(interpreter, False)
    app.require_complete = BooleanVar(interpreter, False)

    with pytest.raises(ValueError, match="订单表"):
        app._build_config()
