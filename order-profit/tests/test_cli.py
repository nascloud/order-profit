from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from order_profit.__main__ import main
from order_profit.inputs import ORDER_COLUMNS


def test_version_option(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--version"])

    assert raised.value.code == 0
    assert "0.1.0" in capsys.readouterr().out


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "validate-inputs" in capsys.readouterr().out


def test_validate_inputs_writes_manifest(tmp_path: Path) -> None:
    orders = tmp_path / "orders.xlsx"
    output = tmp_path / "output"
    values = {column: [""] for column in sorted(ORDER_COLUMNS)}
    values["主订单编号"] = ["001"]
    values["商品ID"] = ["1001"]
    pd.DataFrame(values).to_excel(orders, sheet_name="export", index=False)

    result = main(
        [
            "validate-inputs",
            "--orders",
            str(orders),
            "--start-date",
            "2026-08-01",
            "--end-date",
            "2026-08-07",
            "--platform",
            "tmall",
            "--output-dir",
            str(output),
        ]
    )

    assert result == 0
    manifest = json.loads((output / "validation-manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PROVISIONAL"
    assert manifest["stage"] == "P1-P3_INPUT_VALIDATION"
    assert manifest["inputs"]["orders"]["rows"] == 1


def test_run_command_refuses_incomplete_pipeline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = main(
        [
            "run",
            "--orders",
            str(tmp_path / "orders.xlsx"),
            "--start-date",
            "2026-08-01",
            "--end-date",
            "2026-08-07",
            "--platform",
            "taobao",
            "--output-dir",
            str(tmp_path / "output"),
        ]
    )

    assert result == 10
    assert "PIPELINE_NOT_READY" in capsys.readouterr().err
