from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest

from order_profit.errors import NormalizationError
from order_profit.normalize import (
    money_to_cents,
    normalize_count,
    normalize_datetime,
    normalize_id,
    normalize_merchant_code,
    normalize_quantity,
)


def test_id_normalization_only_removes_numeric_decimal_suffix() -> None:
    assert normalize_id(123.0) == "123"
    assert normalize_id(" 123.0 ") == "123.0"
    assert normalize_id(pd.NA) == ""


def test_id_rejects_scientific_notation_and_unsafe_float() -> None:
    with pytest.raises(NormalizationError, match="科学计数法"):
        normalize_id("1.23E+15")
    with pytest.raises(NormalizationError, match="安全表示范围"):
        normalize_id(9.1e15)


def test_merchant_code_preserves_decimal_suffix() -> None:
    assert normalize_merchant_code(123.0) == "123.0"
    assert normalize_merchant_code(" AbC ") == "AbC"


def test_money_uses_round_half_up_and_integer_cents() -> None:
    assert money_to_cents("1.005") == 101
    assert money_to_cents(Decimal("-1.005")) == -101
    assert money_to_cents("", allow_missing=True) is None


def test_nonnegative_money_rejects_negative_values() -> None:
    with pytest.raises(NormalizationError, match="不能为负数"):
        money_to_cents("-0.01", nonnegative=True)


def test_count_allows_zero_but_rejects_negative_or_fractional() -> None:
    assert normalize_count(0) == 0
    assert normalize_count("", allow_missing=True) is None
    with pytest.raises(NormalizationError, match="不能为负数"):
        normalize_count(-1)
    with pytest.raises(NormalizationError, match="必须是整数"):
        normalize_count("1.5")


def test_quantity_requires_positive_integer() -> None:
    assert normalize_quantity("2.0") == 2
    with pytest.raises(NormalizationError, match="必须是整数"):
        normalize_quantity("1.5")
    with pytest.raises(NormalizationError, match="必须大于 0"):
        normalize_quantity(0)


def test_datetime_accepts_strict_iso_and_converts_timezone() -> None:
    local = normalize_datetime("2026-08-07 23:59:59.123456")
    assert local == datetime.fromisoformat("2026-08-07T23:59:59.123456+08:00")

    converted = normalize_datetime("2026-08-07 16:00:00+00:00")
    assert converted == datetime.fromisoformat("2026-08-08T00:00:00+08:00")


def test_datetime_rejects_loose_formats() -> None:
    with pytest.raises(NormalizationError, match="严格 ISO"):
        normalize_datetime("2026/08/07")
