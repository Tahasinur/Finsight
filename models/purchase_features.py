"""Shared feature schema for synthetic training and live purchase predictions."""

from dataclasses import dataclass

import pandas as pd


CONSUMER_TYPES = ["Heavy Consumer", "Light Consumer", "Balanced Consumer"]
CATEGORY_IMPACT_WEIGHTS = {
    "Housing": 1.0,
    "Food": 0.9,
    "Transportation": 0.75,
    "Entertainment": 0.35,
    "Health": 1.0,
    "Education": 0.7,
    "Other": 0.5,
}
PURCHASE_FEATURE_COLUMNS = [
    "item_cost_balance_ratio",
    "item_cost_monthly_income_ratio",
    "days_left_in_month",
    "goal_urgency",
    "category_impact_weight",
    "monthly_expense_ratio",
    "savings_rate",
    "discretionary_spending_share",
    "nearest_goal_days_left",
    "goal_gap_ratio",
    "consumer_heavy_flag",
    "consumer_light_flag",
    "consumer_balanced_flag",
]


@dataclass(frozen=True)
class PurchaseContext:
    item_cost: float
    current_balance: float
    monthly_income: float
    monthly_expenses: float
    savings_rate: float
    discretionary_spending_share: float
    days_left_in_month: int
    goal_urgency: int
    category: str = "Other"
    nearest_goal_days_left: int = 3650
    goal_gap_ratio: float = 0.0
    consumer_type: str = "Unknown"


def build_purchase_feature_row(context: PurchaseContext) -> dict[str, float]:
    """Validate one user context and produce model-ready numeric features."""
    if context.item_cost <= 0:
        raise ValueError("Price must be greater than zero.")
    if context.current_balance <= 0:
        raise ValueError("Enter a positive current liquid balance.")
    if context.monthly_income < 0 or context.monthly_expenses < 0:
        raise ValueError("Monthly income and expenses cannot be negative.")
    if not 0 <= context.days_left_in_month <= 31:
        raise ValueError("Days remaining in the month must be between 0 and 31.")
    if not 1 <= context.goal_urgency <= 5:
        raise ValueError("Goal urgency must be between 1 and 5.")
    if context.nearest_goal_days_left < 0:
        raise ValueError("Days remaining to a goal cannot be negative.")
    if not 0 <= context.goal_gap_ratio <= 1:
        raise ValueError("Goal gap ratio must be between 0 and 1.")
    if context.category not in CATEGORY_IMPACT_WEIGHTS:
        raise ValueError(f"Unsupported category: {context.category}")

    expense_ratio = context.monthly_expenses / context.monthly_income if context.monthly_income else 1.5
    consumer_type = context.consumer_type if context.consumer_type in CONSUMER_TYPES else "Unknown"
    return {
        "item_cost_balance_ratio": context.item_cost / context.current_balance,
        "item_cost_monthly_income_ratio": context.item_cost / max(context.monthly_income, 1.0),
        "days_left_in_month": float(context.days_left_in_month),
        "goal_urgency": float(context.goal_urgency),
        "category_impact_weight": CATEGORY_IMPACT_WEIGHTS[context.category],
        "monthly_expense_ratio": min(expense_ratio, 3.0),
        "savings_rate": max(-1.0, min(float(context.savings_rate), 1.0)),
        "discretionary_spending_share": max(0.0, min(float(context.discretionary_spending_share), 1.0)),
        "nearest_goal_days_left": float(min(context.nearest_goal_days_left, 3650)),
        "goal_gap_ratio": float(context.goal_gap_ratio),
        "consumer_heavy_flag": float(consumer_type == "Heavy Consumer"),
        "consumer_light_flag": float(consumer_type == "Light Consumer"),
        "consumer_balanced_flag": float(consumer_type == "Balanced Consumer"),
    }


def feature_frame(context: PurchaseContext) -> pd.DataFrame:
    return pd.DataFrame(
        [build_purchase_feature_row(context)],
        columns=PURCHASE_FEATURE_COLUMNS,
    )
