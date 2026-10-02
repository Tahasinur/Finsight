"""Deterministic financial metrics derived from the shared transaction ledger."""

import hashlib

import pandas as pd


DISCRETIONARY_CATEGORIES = {"entertainment"}
MONTHLY_METRIC_COLUMNS = [
    "month",
    "income",
    "expenses",
    "remaining_balance",
    "savings_ratio",
    "monthly_burn_rate",
    "discretionary_expenses",
    "discretionary_ratio",
    "transaction_frequency",
    "average_transaction_amount",
    "spending_variance",
]


def format_currency(amount: float) -> str:
    if pd.isna(amount):
        return "N/A"
    return f"-${abs(amount):,.2f}" if amount < 0 else f"${amount:,.2f}"


def transaction_fingerprint(frame: pd.DataFrame) -> str:
    """Return a stable signature for detecting stale session-level model runs."""
    ordered = frame.copy()
    if "transaction_id" in ordered.columns:
        ordered = ordered.sort_values("transaction_id", kind="stable")
    hashed_rows = pd.util.hash_pandas_object(ordered, index=False, categorize=True)
    return hashlib.sha256(hashed_rows.to_numpy(dtype="uint64").tobytes()).hexdigest()


def get_financial_summary(frame: pd.DataFrame) -> dict[str, float | str]:
    income = float(frame.loc[frame["type"] == "income", "amount"].sum())
    expenses = float(frame.loc[frame["type"] == "expense", "amount"].sum())
    savings_rate = ((income - expenses) / income * 100) if income else 0.0
    if frame.empty:
        period = "No transactions"
    else:
        period = f"{frame['date'].min():%b %Y} - {frame['date'].max():%b %Y}"
    return {
        "income": income,
        "expenses": expenses,
        "net_cash_flow": income - expenses,
        "savings_rate": savings_rate,
        "period": period,
    }


def monthly_cash_flow(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["month", "income", "expense", "net_cash_flow"])
    monthly = frame.assign(month=frame["date"].dt.to_period("M").dt.to_timestamp())
    summary = monthly.pivot_table(
        index="month",
        columns="type",
        values="amount",
        aggfunc="sum",
        fill_value=0,
    )
    summary = summary.reindex(columns=["income", "expense"], fill_value=0).reset_index()
    summary["net_cash_flow"] = summary["income"] - summary["expense"]
    return summary


def monthly_financial_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """Calculate monthly cash-flow ratios and activity features from transactions."""
    if frame.empty:
        return pd.DataFrame(columns=MONTHLY_METRIC_COLUMNS)

    dated = frame.assign(month=frame["date"].dt.to_period("M").dt.to_timestamp())
    records = []
    for month, month_frame in dated.groupby("month", sort=True):
        income_rows = month_frame.loc[month_frame["type"] == "income"]
        expense_rows = month_frame.loc[month_frame["type"] == "expense"]
        income = float(income_rows["amount"].sum())
        expenses = float(expense_rows["amount"].sum())
        discretionary_expenses = float(
            expense_rows.loc[
                expense_rows["category"].str.casefold().isin(DISCRETIONARY_CATEGORIES),
                "amount",
            ].sum()
        )

        as_of = month_frame["date"].max().normalize()
        trailing_days = pd.date_range(end=as_of, periods=7, freq="D")
        daily_expenses = expense_rows.groupby(expense_rows["date"].dt.normalize())["amount"].sum()
        trailing_spend = daily_expenses.reindex(trailing_days, fill_value=0.0)

        month_start = month
        calendar_days = pd.date_range(start=month_start, end=as_of, freq="D")
        daily_month_spend = daily_expenses.reindex(calendar_days, fill_value=0.0)
        records.append(
            {
                "month": month,
                "income": income,
                "expenses": expenses,
                "remaining_balance": income - expenses,
                "savings_ratio": (income - expenses) / income if income else float("nan"),
                "monthly_burn_rate": float(trailing_spend.mean() * 30),
                "discretionary_expenses": discretionary_expenses,
                "discretionary_ratio": (
                    discretionary_expenses / expenses if expenses else float("nan")
                ),
                "transaction_frequency": int(len(month_frame)),
                "average_transaction_amount": (
                    float(expense_rows["amount"].mean()) if not expense_rows.empty else 0.0
                ),
                "spending_variance": float(daily_month_spend.var(ddof=0)),
            }
        )
    return pd.DataFrame.from_records(records, columns=MONTHLY_METRIC_COLUMNS)


def spending_by_category(frame: pd.DataFrame) -> pd.DataFrame:
    expenses = frame.loc[frame["type"] == "expense"]
    if expenses.empty:
        return pd.DataFrame(columns=["category", "amount"])
    return (
        expenses.groupby("category", as_index=False)["amount"]
        .sum()
        .sort_values("amount", ascending=False)
    )
