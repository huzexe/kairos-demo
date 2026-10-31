from decimal import Decimal

from apps.core.currencies import format_money, format_totals


def test_whole_amounts_have_no_decimals():
    assert format_money(Decimal("450000"), "PKR") == "PKR 450,000"


def test_fractional_amounts_keep_decimals():
    assert format_money(Decimal("1250.5"), "USD") == "USD 1,250.50"


def test_three_decimal_currency():
    assert format_money(Decimal("12.3456"), "KWD") == "KWD 12.346"


def test_zero_decimal_currency_rounds():
    assert format_money(Decimal("1999.6"), "JPY") == "JPY 2,000"


def test_none_is_blank():
    assert format_money(None, "USD") == ""


def test_totals_sorted_and_skip_zero():
    assert format_totals({"USD": Decimal("2000"), "PKR": Decimal("450000"), "EUR": 0}) == "PKR 450,000 · USD 2,000"
