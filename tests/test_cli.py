from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from order_profit.__main__ import main
from order_profit.inputs import ORDER_COLUMNS
from order_profit.excel_report import _summary_frame


def test_version_option(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--version"])

    assert raised.value.code == 0
    assert "0.2.0" in capsys.readouterr().out


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "validate-inputs" in capsys.readouterr().out


def test_excel_summary_displays_percentage_points() -> None:
    result = SimpleNamespace(
        analysis=SimpleNamespace(summary={"销售额核算覆盖率": Decimal("0.8972")})
    )
    row = _summary_frame(result).iloc[0]
    assert row.to_dict() == {"指标": "销售额核算覆盖率", "值": 89.72, "单位": "%"}


def test_validate_inputs_writes_manifest(tmp_path: Path) -> None:
    orders = tmp_path / "orders.xlsx"
    output = tmp_path / "output"
    values = {column: [""] for column in sorted(ORDER_COLUMNS)}
    values["主订单编号"] = ["001"]
    values["商品ID"] = ["1001"]
    values["商家备注"] = ["D"]
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
    assert manifest["status"] == "FINAL"
    assert manifest["stage"] == "P1-P9_IN_MEMORY_RECONCILIATION"
    assert manifest["inputs"]["orders"]["rows"] == 1
    assert manifest["order_partitions"]["DELETED_BY_RULE"] == 1
    assert manifest["cost_freight"]["missing_cost_rows"] == 0
    assert manifest["summary"]["有效商品链接"] == 0
    assert all(check["passed"] for check in manifest["reconciliation"])


def test_validate_complete_order_without_source_cost_or_freight_columns(
    tmp_path: Path,
) -> None:
    orders = tmp_path / "orders.xlsx"
    costs = tmp_path / "costs.xlsx"
    freight = tmp_path / "freight.xlsx"
    output = tmp_path / "output"
    values = {column: [""] for column in sorted(ORDER_COLUMNS)}
    values.update(
        {
            "主订单编号": ["001"],
            "商品ID": ["1001"],
            "商品标题": ["测试商品"],
            "商品属性": ["颜色:白色"],
            "购买数量": [2],
            "订单状态": ["交易成功"],
            "商家编码": ["SKU1"],
            "买家应付货款": ["20.00"],
            "退款状态": ["无退款"],
            "订单付款时间": ["2026-08-01 00:00:00"],
            "物流单号": ["W1"],
        }
    )
    order_frame = pd.DataFrame(values)
    assert "货品成本" not in order_frame.columns
    assert "运费" not in order_frame.columns
    order_frame.to_excel(orders, sheet_name="export", index=False)
    pd.DataFrame(
        {"编码": ["SKU1"], "成本": ["1.50"], "运费": ["3.00"]}
    ).to_excel(costs, sheet_name="Sheet1", index=False)
    pd.DataFrame(
        {"运单号": ["W1"], "订单编码": ["001"], "总运费": ["8.00"]}
    ).to_excel(freight, sheet_name="Sheet1", index=False)

    result = main(
        [
            "validate-inputs",
            "--orders",
            str(orders),
            "--costs",
            str(costs),
            "--freight",
            str(freight),
            "--start-date",
            "2026-08-01",
            "--end-date",
            "2026-08-07",
            "--platform",
            "tmall",
            "--output-dir",
            str(output),
            "--require-complete",
        ]
    )

    assert result == 0
    manifest = json.loads((output / "validation-manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FINAL"
    assert manifest["cost_freight"]["missing_cost_rows"] == 0
    assert manifest["cost_freight"]["missing_freight_rows"] == 0
    assert manifest["summary"]["已核算货品成本_分"] == 300
    assert manifest["summary"]["已核算运费_分"] == 800


def test_require_complete_returns_nonzero_for_provisional_result(tmp_path: Path) -> None:
    orders = tmp_path / "orders.xlsx"
    values = {column: [""] for column in sorted(ORDER_COLUMNS)}
    values.update(
        {
            "主订单编号": ["001"],
            "商品ID": ["1001"],
            "商品标题": ["测试商品"],
            "购买数量": [1],
            "订单状态": ["交易成功"],
            "商家编码": ["SKU1"],
            "买家应付货款": ["20.00"],
            "退款状态": ["无退款"],
            "订单付款时间": ["2026-08-01 00:00:00"],
        }
    )
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
            str(tmp_path / "output"),
            "--require-complete",
        ]
    )

    assert result == 4


def test_run_writes_reports_for_complete_empty_result(tmp_path: Path) -> None:
    orders = tmp_path / "orders.xlsx"
    output = tmp_path / "reports"
    values = {column: [""] for column in sorted(ORDER_COLUMNS)}
    values["主订单编号"] = ["001"]
    values["商品ID"] = ["1001"]
    values["商品标题"] = ["<script>alert(1)</script>"]
    values["商家备注"] = ["D"]
    pd.DataFrame(values).to_excel(orders, sheet_name="export", index=False)

    result = main(
        [
            "run",
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
    assert (output / "订单成本利润分析.xlsx").exists()
    assert (output / "店铺经营复盘.html").exists()
    assert (output / "manifest.json").exists()
    page = (output / "店铺经营复盘.html").read_text(encoding="utf-8")
    assert "店铺经营复盘" in page
    assert "FINAL" in page


def test_run_reports_missing_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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

    assert result == 3
    assert "INPUT_FILE_NOT_FOUND" in capsys.readouterr().err
