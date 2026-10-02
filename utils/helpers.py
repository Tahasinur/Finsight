"""Small shared presentation and formatting helpers."""

import pandas as pd


def format_currency(amount: float | int | None) -> str:
    """Format numeric value as USD currency."""
    if amount is None or pd.isna(amount):
        return "N/A"
    return f"-${abs(amount):,.2f}" if amount < 0 else f"${amount:,.2f}"


def format_percentage(value: float | int | None, decimals: int = 1) -> str:
    """Format numeric ratio as percentage string."""
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def format_delta_currency(amount: float | int | None, suffix: str = "vs previous") -> str:
    """Format delta value with directional indicator and label."""
    if amount is None or pd.isna(amount):
        return "N/A"
    formatted = format_currency(amount)
    return f"{formatted} {suffix}"
