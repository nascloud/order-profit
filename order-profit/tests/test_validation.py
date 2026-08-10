from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from order_profit.config import Platform, RunConfig
from order_profit.errors import InputContractError
from order_profit.inputs import LoadedTable
from order_profit.models import InputFileMetadata
from order_profit.normalize import add_source_audit_columns
from order_profit.validation import normalize_costs


def _config(tmp_path: Path) -> RunConfig:
    return RunConfig(
        orders=tmp_path / "orders.xlsx",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        platform=Platform.TMALL,
        output_dir=tmp_path / "output",
    )


def _cost_table(tmp_path: Path, data: pd.DataFrame) -> LoadedTable:
    path = tmp_path / "costs.xlsx"
    audited = add_source_audit_columns(
        data,
        path=path,
        sheet="Sheet1",
        file_sha256="a" * 64,
    )
    metadata = InputFileMetadata(
        role="成本编码表",
        path=path,
        sha256="a" * 64,
        size_bytes=1,
        rows=len(data),
        sheet="Sheet1",
    )
    return LoadedTable(data=audited, metadata=metadata)


def test_costs_drop_identical_duplicate_codes(tmp_path: Path) -> None:
    table = _cost_table(
        tmp_path,
        pd.DataFrame({"编码": ["A", "A"], "成本": ["1.00", "1.00"], "运费": ["2", "2"]}),
    )

    normalized = normalize_costs(table, _config(tmp_path))

    assert len(normalized.data) == 1
    assert normalized.data.iloc[0]["成本_分"] == 100


def test_costs_reject_conflicting_duplicate_codes(tmp_path: Path) -> None:
    table = _cost_table(
        tmp_path,
        pd.DataFrame({"编码": ["A", "A"], "成本": ["1.00", "1.01"], "运费": ["2", "2"]}),
    )

    with pytest.raises(InputContractError, match="冲突"):
        normalize_costs(table, _config(tmp_path))


def test_costs_reject_empty_code(tmp_path: Path) -> None:
    table = _cost_table(
        tmp_path,
        pd.DataFrame({"编码": [""], "成本": ["1.00"], "运费": ["2"]}),
    )

    with pytest.raises(InputContractError, match="编码不能为空"):
        normalize_costs(table, _config(tmp_path))
