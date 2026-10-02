"""Transaction-backed overview dashboard."""

import plotly.express as px
import pandas as pd
import streamlit as st
from pathlib import Path
from datetime import date, timedelta

from models.preprocessing import preprocess_transactions
from models.spending_clustering import PROFILE_NAMES, fit_spending_clusters
from utils.calculations import (
    DISCRETIONARY_CATEGORIES,
    format_currency,
    monthly_cash_flow,
    monthly_financial_metrics,
    spending_by_category,
    transaction_fingerprint,
)
from utils.auth import get_user_goals, get_user_preferences
from utils.data_loader import DEFAULT_DATA_PATH, load_transactions, save_transactions


GREEN = "#0F766E"
CORAL = "#F59E0B"


def render(frame: pd.DataFrame, store_path: str | Path | None = None) -> None:
    st.title("Your Money Snapshot")
    st.caption("A calm overview of your recorded cash flow, spending pattern, and active goals.")
    user_id = st.session_state.get("user_id")
    period_key = f"dashboard_period_{user_id or 'guest'}"
    default_period = get_user_preferences(user_id)["dashboard_period"] if user_id else "Last 30 days"
    if period_key not in st.session_state:
        st.session_state[period_key] = default_period
    period = st.radio(
        "View period",
        ["This month", "Last 30 days", "Custom"],
        horizontal=True,
        key=period_key,
    )
    bounds = _period_bounds(period, frame)
    if bounds is None:
        current_start, current_end = date.today(), date.today()
        previous_start, previous_end = current_start - timedelta(days=29), current_start - timedelta(days=1)
    else:
        current_start, current_end, previous_start, previous_end = bounds

    current = _filter_dates(frame, current_start, current_end)
    previous = _filter_dates(frame, previous_start, previous_end)
    current_income, current_expenses = _cash_totals(current)
    previous_income, previous_expenses = _cash_totals(previous)
    current_net = current_income - current_expenses
    previous_net = previous_income - previous_expenses
    current_savings_rate = (current_net / current_income) if current_income else None
    previous_savings_rate = ((previous_income - previous_expenses) / previous_income) if previous_income else None
    user_prefs = get_user_preferences(user_id) if user_id else {}
    initial_balance = float(user_prefs.get("initial_balance", 0.0))
    lifetime_income, lifetime_expenses = _cash_totals(frame)
    current_balance = initial_balance + lifetime_income - lifetime_expenses

    if frame.empty:
        st.info("Your private ledger is empty. Add transactions or import a CSV to start your snapshot.")
    elif current.empty:
        st.warning("There are no dated transactions in this period. Try Last 30 days or adjust the dates.")

    balance_help = (
        f"Initial balance (${initial_balance:,.2f}) plus cumulative ledger net flow."
        if initial_balance > 0
        else "Cumulative ledger net flow from a zero opening balance; set your starting balance in My Profile."
    )

    metrics = st.columns(4)
    metrics[0].metric(
        "Current balance",
        format_currency(current_balance),
        delta=_currency_delta(current_net - previous_net, "net this period") if not previous.empty else None,
        help=balance_help,
    )
    metrics[1].metric("Income", format_currency(current_income), delta=_currency_delta(current_income - previous_income) if not previous.empty else None)
    metrics[2].metric("Expenses", format_currency(current_expenses), delta=_currency_delta(previous_expenses - current_expenses, "less spending") if not previous.empty else None, delta_color="normal")
    savings_display = f"{current_savings_rate:.1%}" if current_savings_rate is not None else "N/A"
    savings_delta = (current_savings_rate - previous_savings_rate) * 100 if current_savings_rate is not None and previous_savings_rate is not None else None
    metrics[3].metric("Savings rate", savings_display, delta=f"{savings_delta:+.1f} pp" if savings_delta is not None else None)
    st.caption(f"{current_start:%b %d} – {current_end:%b %d, %Y} · Compared with {previous_start:%b %d} – {previous_end:%b %d}")

    profile_name, profile_error = _consumer_profile(frame)
    profile_style = {
        "Heavy Consumer": ("#FEE2E2", "#991B1B", "Your recent monthly activity is closer to the higher-spend clusters."),
        "Balanced Consumer": ("#FEF3C7", "#92400E", "Your recent activity sits between the lighter and heavier clusters."),
        "Light Consumer": ("#D1FAE5", "#065F46", "Your recent monthly activity is closer to the lower-spend clusters."),
    }
    profile_bg, profile_ink, profile_copy = profile_style.get(profile_name, ("#E2E8F0", "#334155", "Add at least three months of transactions to find a pattern."))
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:16px;padding:18px 22px;margin:12px 0 24px;border-radius:14px;background:{profile_bg};'>"
        f"<span style='padding:8px 13px;border-radius:99px;background:white;color:{profile_ink};font:700 13px Manrope,sans-serif;'>{profile_name}</span>"
        f"<span style='color:{profile_ink};font-size:14px;'>{profile_copy}</span></div>",
        unsafe_allow_html=True,
    )
    if profile_error:
        st.caption(profile_error)

    if frame.empty:
        st.markdown("**Explore with example data**")
        st.caption("This four-month sample is illustrative only. It is copied into this account only if you choose to use it.")
        if store_path is not None and st.button("Explore the example ledger", type="primary"):
            try:
                save_transactions(load_transactions(DEFAULT_DATA_PATH), store_path)
            except (OSError, ValueError) as error:
                st.error(f"Could not copy the example data: {error}")
            else:
                st.rerun()
        return

    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        st.subheader("Cash flow")
        flow = monthly_cash_flow(frame)
        if flow.empty:
            st.info("Cash flow will appear after dated transactions are added.")
        else:
            flow_long = flow.melt(id_vars="month", value_vars=["income", "expense"], var_name="type", value_name="amount")
            chart = px.bar(
                flow_long,
                x="month",
                y="amount",
                color="type",
                barmode="group",
                color_discrete_map={"income": "#10B981", "expense": "#F59E0B"},
                labels={"month": "Month", "amount": "Amount", "type": "Cash flow"},
            )
            _style_figure(chart)
            st.plotly_chart(chart, width="stretch", theme=None, config={"displayModeBar": False})
    with right:
        st.subheader("Where spending goes")
        categories = spending_by_category(current)
        if categories.empty:
            st.info("No expenses in this period yet.")
        else:
            chart = px.pie(categories, names="category", values="amount", hole=0.68, color_discrete_sequence=["#0F766E", "#2DD4BF", "#F59E0B", "#F87171", "#6366F1", "#84CC16"])
            chart.update_traces(textposition="inside", textinfo="percent", hovertemplate="%{label}<br>$%{value:,.2f}<extra></extra>")
            _style_figure(chart, height=280)
            chart.update_layout(showlegend=False)
            st.plotly_chart(chart, width="stretch", theme=None, config={"displayModeBar": False})
            st.dataframe(categories.head(5).rename(columns={"category": "Category", "amount": "Spent"}), width="stretch", hide_index=True, column_config={"Spent": st.column_config.NumberColumn(format="$%.2f")})

    st.subheader("A closer look")
    anomaly_col, goals_col = st.columns([1, 1], gap="large")
    with anomaly_col:
        st.markdown("**Unusual repeat costs**")
        anomalies = _repeat_cost_anomalies(frame, current)
        if anomalies.empty:
            st.success("No unusually high repeat costs found in this period.")
        else:
            for _, anomaly in anomalies.iterrows():
                st.warning(f"{anomaly['description']}: {format_currency(anomaly['amount'])}, above your recorded typical {format_currency(anomaly['median'])}.")
        st.caption("Compares repeated descriptions with at least three earlier records; new expenses are not labeled anomalies.")
    with goals_col:
        st.markdown("**Active goals**")
        goals = _active_goals()
        if not goals:
            st.info("No active goals saved yet. Add a goal in Goal Pathfinder to track progress here.")
        for goal in goals[:4]:
            target = float(goal["target_amount"])
            progress = min(1.0, float(goal["current_savings"]) / target)
            st.markdown(f"**{goal['goal_name']}** · {format_currency(goal['current_savings'])} / {format_currency(target)} · due {goal['deadline_date']}")
            st.progress(progress)

    st.subheader("Recent transactions")
    recent = frame.sort_values("date", ascending=False, na_position="last").head(5)
    if recent.empty:
        st.info("Your recent transactions will appear here.")
    else:
        recent_table = recent[["date", "description", "category", "type", "amount"]].rename(columns={"date": "Date", "description": "What", "category": "Category", "type": "Type", "amount": "Amount"})
        st.dataframe(recent_table, width="stretch", hide_index=True, column_config={"Amount": st.column_config.NumberColumn(format="$%.2f")})

    st.subheader("Insight from your activity")
    st.info(_activity_insight(current_income, current_expenses, current_savings_rate, profile_name, anomalies))

    next_action = _next_action(current_savings_rate, profile_name, goals, anomalies)
    action_col, button_col = st.columns([3, 1])
    with action_col:
        st.markdown("**Recommended next action**")
        st.write(next_action)
    with button_col:
        if st.button("Should I buy this?", type="primary", use_container_width=True):
            st.session_state["finwise_workspace_page"] = "Should I Buy This?"
            st.rerun()

    saved_check = st.session_state.get("purchase_advisor_run")
    if saved_check and saved_check.get("transaction_fingerprint") != transaction_fingerprint(frame):
        st.warning("Your last purchase check is based on older transactions. Re-run it for an up-to-date result.")


def _period_bounds(period: str, frame: pd.DataFrame):
    today = date.today()
    if period == "This month":
        start, end = today.replace(day=1), today
    elif period == "Last 30 days":
        start, end = today - timedelta(days=29), today
    else:
        valid_dates = frame["date"].dropna() if not frame.empty else pd.Series(dtype="datetime64[ns]")
        default_end = valid_dates.max().date() if not valid_dates.empty else today
        date_range = st.date_input("Choose date range", value=(default_end - timedelta(days=29), default_end), key="dashboard_custom_period")
        if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
            return None
        start, end = date_range
    if end < start:
        start, end = end, start
    length = (end - start).days + 1
    return start, end, start - timedelta(days=length), start - timedelta(days=1)


def _filter_dates(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if frame.empty or "date" not in frame:
        return frame.iloc[:0].copy()
    return frame.loc[frame["date"].notna() & frame["date"].dt.date.between(start, end)].copy()


def _cash_totals(frame: pd.DataFrame) -> tuple[float, float]:
    income = float(frame.loc[frame["type"] == "income", "amount"].sum()) if not frame.empty else 0.0
    expenses = float(frame.loc[frame["type"] == "expense", "amount"].sum()) if not frame.empty else 0.0
    return income, expenses


def _currency_delta(value: float, suffix: str = "vs previous period") -> str:
    return f"{format_currency(value)} {suffix}"


def _consumer_profile(frame: pd.DataFrame) -> tuple[str, str | None]:
    try:
        profile = fit_spending_clusters(frame)
        return profile.latest_profile, None
    except ValueError as error:
        return "Building pattern", f"Add at least three distinct months for a K-Means consumer type. {error}"


def _active_goals() -> list[dict]:
    user_id = st.session_state.get("user_id")
    if not user_id:
        return []
    return [goal for goal in get_user_goals(user_id) if goal["active"]]


def _repeat_cost_anomalies(all_transactions: pd.DataFrame, period_transactions: pd.DataFrame) -> pd.DataFrame:
    if all_transactions.empty or period_transactions.empty:
        return pd.DataFrame(columns=["description", "amount", "median"])
    period_ids = set(period_transactions["transaction_id"])
    history = all_transactions.loc[
        (all_transactions["type"] == "expense") & ~all_transactions["transaction_id"].isin(period_ids)
    ]
    current_expenses = period_transactions.loc[period_transactions["type"] == "expense"]
    anomalies = []
    for _, transaction in current_expenses.iterrows():
        prior = history.loc[
            (history["description"].str.casefold() == str(transaction["description"]).casefold())
            & (history["category"] == transaction["category"]),
            "amount",
        ]
        if len(prior) < 3:
            continue
        median = float(prior.median())
        if median > 0 and float(transaction["amount"]) > median * 1.5:
            anomalies.append({"description": transaction["description"], "amount": float(transaction["amount"]), "median": median})
    return pd.DataFrame(anomalies, columns=["description", "amount", "median"])


def _next_action(savings_rate, consumer_type: str, goals: list[dict], anomalies: pd.DataFrame) -> str:
    if not goals:
        return "Save one concrete goal in Goal Pathfinder so your purchase checks and dashboard can show deadline impact."
    if not anomalies.empty:
        return "Review an unusually high repeated cost before making another discretionary purchase."
    if savings_rate is not None and savings_rate < 0.10:
        return "Keep the next discretionary purchase small while you rebuild this period's savings buffer."
    if consumer_type == "Heavy Consumer":
        return "Compare the largest recurring expense against a recent month before adding a new commitment."
    return "Review the progress bar for your nearest goal and confirm its monthly saving limit is current."


def _activity_insight(income: float, expenses: float, savings_rate, consumer_type: str, anomalies: pd.DataFrame) -> str:
    if income <= 0:
        return "There is not enough income in this period to calculate a savings pattern yet. Add or import income transactions to personalize this view."
    if not anomalies.empty:
        return f"One repeated expense is higher than its earlier recorded amount. Monthly spending is {format_currency(expenses)} against {format_currency(income)} in income."
    if savings_rate is not None:
        return f"You kept {savings_rate:.1%} of recorded income this period. Your recent monthly pattern is {consumer_type.lower()} based on transaction history."
    return f"Recorded expenses are {format_currency(expenses)} for this period. Add income records to calculate a savings rate."


def _style_figure(figure, height: int = 320) -> None:
    figure.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=12, r=12, t=16, b=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, sans-serif", color="#134E4A"),
        legend=dict(font=dict(color="#134E4A")),
        xaxis=dict(showgrid=False, tickfont=dict(color="#134E4A")),
        yaxis=dict(gridcolor="#E2E8F0", tickfont=dict(color="#134E4A")),
    )
