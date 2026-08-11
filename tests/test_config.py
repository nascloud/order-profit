from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from order_profit.config import Platform, RunConfig
from order_profit.errors import ConfigurationError


def test_run_config_exposes_platform_rates(tmp_path: Path) -> None:
    config = RunConfig(
        orders=tmp_path / "orders.xlsx",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        platform=Platform.TMALL,
        output_dir=tmp_path / "output",
    )

    assert str(config.platform_fee_rate) == "0.06"
    assert str(config.tax_rate) == "0.023"
    assert config.to_dict()["platform"] == "tmall"


def test_run_config_rejects_reversed_dates(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="开始日期"):
        RunConfig(
            orders=tmp_path / "orders.xlsx",
            start_date=date(2026, 8, 8),
            end_date=date(2026, 8, 7),
            platform=Platform.TAOBAO,
            output_dir=tmp_path / "output",
        )


def test_run_config_rejects_unknown_timezone(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="未知时区"):
        RunConfig(
            orders=tmp_path / "orders.xlsx",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 7),
            platform=Platform.TAOBAO,
            output_dir=tmp_path / "output",
            timezone="Mars/Olympus",
        )


def test_sabc_config_is_strict_and_traceable(tmp_path: Path) -> None:
    path = tmp_path / "sabc.json"
    path.write_text('{"s_profit_share":0.4,"a_profit_share":0.75}', encoding="utf-8")
    config = RunConfig(
        orders=tmp_path / "orders.xlsx", start_date=date(2026, 8, 1), end_date=date(2026, 8, 7),
        platform=Platform.TMALL, output_dir=tmp_path / "output", sabc_config=path,
    )
    assert config.s_profit_share == Decimal("0.4")
    assert config.a_profit_share == Decimal("0.75")
    assert config.to_dict()["sabc_config"] == str(path.resolve())

    path.write_text('{"s_profit_share":0.8,"a_profit_share":0.5}', encoding="utf-8")
    with pytest.raises(ConfigurationError, match="0 < s_profit_share"):
        RunConfig(
            orders=tmp_path / "orders.xlsx", start_date=date(2026, 8, 1), end_date=date(2026, 8, 7),
            platform=Platform.TMALL, output_dir=tmp_path / "output", sabc_config=path,
        )

    path.write_text('{"s_profit_share":NaN,"a_profit_share":0.8}', encoding="utf-8")
    with pytest.raises(ConfigurationError, match="有限数字"):
        RunConfig(
            orders=tmp_path / "orders.xlsx", start_date=date(2026, 8, 1), end_date=date(2026, 8, 7),
            platform=Platform.TMALL, output_dir=tmp_path / "output", sabc_config=path,
        )
