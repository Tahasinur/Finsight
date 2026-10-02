"""Interactive constraint satisfaction budget optimizer."""

import pandas as pd
import plotly.express as px
import streamlit as st

from models.budget_csp import (
    BudgetOptimizationResult,
    optimize_budget_csp,
)
from utils.auth import get_latest_analysis_run, get_user_categories, save_analysis_run
from utils.calculations import format_currency, monthly_financial_metrics, transaction_fingerprint


def render(frame: pd.DataFrame) -> None:
    st.title("Smart Budget Helper")
    st.caption("Search for a monthly plan that covers your minimums and makes room for priorities.")
    st.info(
        "Enter net spendable monthly income. Existing category targets are prefilled from the latest transaction month; debt and reserve targets require your input if they are not recorded in the ledger."
    )

    user_id = st.session_state.get("user_id")
    user_categories = get_user_categories(user_id)
    expense_categories = user_categories.get("expense", [])

    with st.expander("Inspect category spend & calibrate targets"):
        cat_col1, cat_col2 = st.columns([1.5, 1])
        selected_cat = cat_col1.selectbox(
            "Category",
            expense_categories,
            help="Review recent monthly spend across standard and custom categories to calibrate your budget targets.",
        )
        if not frame.empty and "category" in frame.columns and "amount" in frame.columns:
            recent_month_mask = frame["date"].dt.to_period("M") == frame["date"].max().to_period("M")
            recent_spend = float(
                frame.loc[recent_month_mask & (frame["category"] == selected_cat) & (frame["type"] == "expense"), "amount"].sum()
            )
            cat_col2.metric(f"{selected_cat} (Latest Month)", format_currency(recent_spend))
        else:
            cat_col2.caption("No transaction records found.")

    defaults = _transaction_defaults(frame, expense_categories)
    with st.form("budget_optimizer_form"):
        income = st.number_input(
            "Net monthly income",
            min_value=0.0,
            value=defaults["monthly_income"],
            step=100.0,
            format="%.2f",
        )
        first_row = st.columns(2)
        housing = first_row[0].number_input("Minimum housing", min_value=0.0, value=defaults["housing"], step=25.0, format="%.2f")
        food = first_row[1].number_input("Food target", min_value=0.0, value=defaults["food"], step=25.0, format="%.2f")
        second_row = st.columns(2)
        transportation = second_row[0].number_input("Transportation target", min_value=0.0, value=defaults["transportation"], step=25.0, format="%.2f")
        health = second_row[1].number_input("Health target", min_value=0.0, value=defaults["health"], step=25.0, format="%.2f")
        third_row = st.columns(2)
        education = third_row[0].number_input("Education target", min_value=0.0, value=defaults["education"], step=25.0, format="%.2f")
        debt_payment = third_row[1].number_input("Minimum debt payment", min_value=0.0, value=defaults["debt_payment"], step=25.0, format="%.2f")
        fourth_row = st.columns(2)
        emergency_reserve = fourth_row[0].number_input("Emergency reserve target", min_value=0.0, value=defaults["emergency_reserve"], step=25.0, format="%.2f")
        discretionary = fourth_row[1].number_input("Discretionary spending target", min_value=0.0, value=defaults["discretionary"], step=25.0, format="%.2f")
        savings = st.number_input("Savings target", min_value=0.0, value=defaults["savings"], step=25.0, format="%.2f")
        submitted = st.form_submit_button("Search for an allocation", type="primary")

    user_id = st.session_state.get("user_id")
    if submitted:
        targets = {
            "housing": housing,
            "food": food,
            "transportation": transportation,
            "health": health,
            "education": education,
            "debt_payment": debt_payment,
            "emergency_reserve": emergency_reserve,
            "discretionary": discretionary,
            "savings": savings,
        }
        try:
            with st.spinner("Solving budget allocation CSP..."):
                result = optimize_budget_csp(income, targets)
        except ValueError as error:
            st.session_state.pop("budget_optimizer_run", None)
            st.error(str(error))
        else:
            run_data = {
                "monthly_income": float(income),
                "targets": targets,
                "result": result,
                "transaction_fingerprint": transaction_fingerprint(frame),
            }
            st.session_state["budget_optimizer_run"] = run_data
            if user_id:
                try:
                    save_analysis_run(user_id, "budget_optimizer", run_data["transaction_fingerprint"], run_data)
                except Exception as save_err:
                    st.caption(f"Could not persist run to database: {save_err}")

    if user_id and "budget_optimizer_run" not in st.session_state:
        persisted = get_latest_analysis_run(user_id, "budget_optimizer")
        if persisted:
            st.session_state["budget_optimizer_run"] = persisted

    run = st.session_state.get("budget_optimizer_run")
    if run is not None:
        if run.get("transaction_fingerprint") != transaction_fingerprint(frame):
            st.warning("Your transaction ledger changed since this allocation search was run. Search again for an up-to-date result.")
        _render_result(run["monthly_income"], run["targets"], run["result"])


def _transaction_defaults(frame: pd.DataFrame, expense_categories: list[str] | None = None) -> dict[str, float]:
    defaults = {
        "monthly_income": 0.0,
        "housing": 0.0,
        "food": 0.0,
        "transportation": 0.0,
        "health": 0.0,
        "education": 0.0,
        "debt_payment": 0.0,
        "emergency_reserve": 0.0,
        "discretionary": 0.0,
        "savings": 0.0,
    }
    metrics = monthly_financial_metrics(frame)
    if metrics.empty:
        return defaults

    latest = metrics.iloc[-1]
    defaults["monthly_income"] = float(latest["income"])
    defaults["savings"] = max(0.0, float(latest["remaining_balance"]))
    month_frame = frame.loc[frame["date"].dt.to_period("M").dt.to_timestamp() == latest["month"]]
    expenses = month_frame.loc[month_frame["type"] == "expense"]

    standard_map = {
        "Housing": "housing",
        "Food": "food",
        "Transportation": "transportation",
        "Health": "health",
        "Education": "education",
    }
    for category, key in standard_map.items():
        amount = expenses.loc[expenses["category"] == category, "amount"].sum()
        defaults[key] = float(amount)

    all_cats = expense_categories if expense_categories else expenses["category"].dropna().unique().tolist()
    discretionary_amount = 0.0
    for cat in all_cats:
        if cat not in standard_map:
            discretionary_amount += float(expenses.loc[expenses["category"] == cat, "amount"].sum())
    defaults["discretionary"] = discretionary_amount

    debt_mask = expenses["description"].astype("string").str.contains("debt payment", case=False, na=False)
    defaults["debt_payment"] = float(expenses.loc[debt_mask, "amount"].sum())
    return defaults


def _render_result(
    monthly_income: float,
    targets: dict[str, float],
    result: BudgetOptimizationResult,
) -> None:
    st.subheader("Suggested plan")
    st.markdown(f"**Plan status:** {'A plan fits your limits' if result.feasible else 'No plan fits these inputs'}")
    if not result.feasible:
        st.error(result.explanation)
        _render_search_statistics(result)
        return

    st.caption("Flexible spending was compared at several levels while your housing and debt minimums stayed protected.")
    input_col, constraint_col = st.columns([1, 1.2], gap="large")
    with input_col:
        st.markdown("**Your requested amounts**")
        input_table = pd.DataFrame(
            [{"Allocation": name.replace("_", " ").title(), "Requested amount": value} for name, value in targets.items()]
        )
        st.dataframe(input_table, width="stretch", hide_index=True)
    with constraint_col:
        st.markdown("**Required minimums**")
        constraints = pd.DataFrame(
            [{"Constraint": name, "Satisfied": satisfied} for name, satisfied in result.constraints.items()]
        )
        st.dataframe(constraints, width="stretch", hide_index=True)

    st.markdown("**Suggested monthly amounts**")
    allocations = pd.DataFrame(
        [
            {
                "Category": name.replace("_", " ").title(),
                "Requested": targets.get(name, 0.0),
                "Allocated": amount,
            }
            for name, amount in result.allocations.items()
        ]
    )
    st.dataframe(
        allocations,
        width="stretch",
        hide_index=True,
        column_config={
            "Requested": st.column_config.NumberColumn(format="$%.2f"),
            "Allocated": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    total_col, remaining_col, cap_col = st.columns(3)
    total_col.metric("Total allocation", format_currency(result.total_allocation))
    remaining_col.metric("Unallocated amount", format_currency(result.remaining_amount))
    cap_col.metric("Suggested optional-spending limit", format_currency(result.discretionary_cap))

    chart = px.bar(
        allocations,
        x="Category",
        y="Allocated",
        color="Category",
        color_discrete_sequence=["#0F766E", "#2DD4BF", "#F59E0B", "#F87171", "#6366F1", "#84CC16", "#115E59", "#64D2C5", "#FBBF24"],
        labels={"Allocated": "Amount (USD)"},
    )
    chart.update_layout(
        template="plotly_white",
        height=310,
        margin=dict(l=12, r=12, t=12, b=12),
        showlegend=False,
        font=dict(family="DM Sans, sans-serif", color="#134E4A"),
        xaxis=dict(showgrid=False, tickfont=dict(color="#134E4A")),
        yaxis=dict(gridcolor="#E2E8F0", tickfont=dict(color="#134E4A")),
    )
    st.plotly_chart(chart, width="stretch", theme=None, config={"displayModeBar": False})

    st.subheader("Why this solution was selected")
    st.write("The plan protects your housing and debt minimums first, stays within entered income, then gives your emergency reserve and savings more room when the other requests do not all fit.")
    st.caption(f"Optional spending is encouraged to stay near {format_currency(monthly_income * 0.20)} when the rest of the budget allows it.")
    with st.expander("How the plan was compared"):
        st.write("The helper checks combinations of your requested amounts, drops options that go over income, and keeps the best-fitting plan it finds.")
        st.write("Emergency savings and long-term savings are given more priority than optional purchases. Your selected housing and debt minimums are never reduced.")
    _render_search_statistics(result)


def _render_search_statistics(result: BudgetOptimizationResult) -> None:
    st.markdown("**Plan search**")
    statistics = result.statistics
    first, second = st.columns(2)
    first.metric("Plans checked", f"{statistics.nodes_explored:,}")
    second.metric("Plans that fit", f"{statistics.feasible_solutions:,}")