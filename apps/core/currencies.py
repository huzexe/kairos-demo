"""
Currencies an agency can bill a client in.

Each client is dealt with in one currency, chosen by the user. Amounts are
never converted between currencies; totals that mix currencies are shown
side by side instead (for example "PKR 450,000 · USD 2,000").
"""

from decimal import Decimal, ROUND_HALF_UP

# code: (name, decimal places)
CURRENCIES = {
    "PKR": ("Pakistani Rupee", 2),
    "USD": ("US Dollar", 2),
    "EUR": ("Euro", 2),
    "GBP": ("British Pound", 2),
    "AED": ("UAE Dirham", 2),
    "SAR": ("Saudi Riyal", 2),
    "QAR": ("Qatari Riyal", 2),
    "KWD": ("Kuwaiti Dinar", 3),
    "BHD": ("Bahraini Dinar", 3),
    "OMR": ("Omani Rial", 3),
    "INR": ("Indian Rupee", 2),
    "BDT": ("Bangladeshi Taka", 2),
    "LKR": ("Sri Lankan Rupee", 2),
    "CAD": ("Canadian Dollar", 2),
    "AUD": ("Australian Dollar", 2),
    "NZD": ("New Zealand Dollar", 2),
    "CHF": ("Swiss Franc", 2),
    "SEK": ("Swedish Krona", 2),
    "NOK": ("Norwegian Krone", 2),
    "DKK": ("Danish Krone", 2),
    "PLN": ("Polish Zloty", 2),
    "TRY": ("Turkish Lira", 2),
    "EGP": ("Egyptian Pound", 2),
    "NGN": ("Nigerian Naira", 2),
    "KES": ("Kenyan Shilling", 2),
    "ZAR": ("South African Rand", 2),
    "MYR": ("Malaysian Ringgit", 2),
    "SGD": ("Singapore Dollar", 2),
    "IDR": ("Indonesian Rupiah", 2),
    "PHP": ("Philippine Peso", 2),
    "THB": ("Thai Baht", 2),
    "CNY": ("Chinese Yuan", 2),
    "HKD": ("Hong Kong Dollar", 2),
    "JPY": ("Japanese Yen", 0),
    "KRW": ("South Korean Won", 0),
    "BRL": ("Brazilian Real", 2),
    "MXN": ("Mexican Peso", 2),
}

CURRENCY_CHOICES = [(code, f"{code} — {name}") for code, (name, _) in CURRENCIES.items()]
DEFAULT_CURRENCY = "PKR"


def decimal_places(code: str) -> int:
    return CURRENCIES.get(code, ("", 2))[1]


def format_money(amount, code: str) -> str:
    """'PKR 450,000' for whole amounts, 'USD 1,250.50' otherwise."""
    if amount is None:
        return ""
    places = decimal_places(code)
    quant = Decimal(1).scaleb(-places)
    value = Decimal(amount).quantize(quant, rounding=ROUND_HALF_UP)
    if value == value.to_integral_value():
        text = f"{value:,.0f}"
    else:
        text = f"{value:,.{places}f}"
    return f"{code} {text}"


def format_totals(totals: dict) -> str:
    """Format a {currency: amount} dict as 'PKR 450,000 · USD 2,000'."""
    parts = [format_money(amount, code) for code, amount in sorted(totals.items()) if amount]
    return " · ".join(parts)
