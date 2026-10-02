"""Plan and save a goal with a month-by-month savings route."""

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from models.goal_astar import GoalPlanResult, plan_savings_goal
from utils.auth import save_user_goal
from utils.calculations import format_currency, monthly_financial_metrics, transaction_fingerprint


def render(frame: pd.DataFrame) -> None:
    st.title("Goal Pathfinder")
    st.caption("Choose a goal and see a monthly saving route that fits your limit and target date.")

    monthly = monthly_financial_metrics(frame)
    baseline = max(0.0, float(monthly.iloc[-1]["remaining_balance"])) if not monthly.empty else 0.0
    st.caption(
        f"Observed monthly surplus baseline from the latest ledger month: {format_currency(baseline)}. "
        "Current goal savings must be entered by you."
    )
    limit_lifestyle = st.checkbox(
        "Apply an optional monthly lifestyle restriction",
        help="Caps contributions at observed monthly surplus plus the extra monthly spending cut you allow.",
    )

    with st.form("goal_planner_form"):
        goal_name = st.text_input("Goal name", max_chars=100)
        target_col, current_col = st.columns(2)
        target_amount = target_col.number_input("Target price", min_value=0.0, value=0.0, step=100.0, format="%.2f")
        current_savings = current_col.number_input("Current savings", min_value=0.0, value=0.0, step=100.0, format="%.2f")
        max_col, lifestyle_col = st.columns(2)
        max_monthly_saving = max_col.number_input(
            "Maximum monthly saving",
            min_value=0.0,
            value=baseline,
            step=50.0,
            format="%.2f",
        )
        if limit_lifestyle:
            lifestyle_cut = lifestyle_col.number_input(
                "Maximum extra lifestyle cut per month",
                min_value=0.0,
                value=0.0,
                step=25.0,
                format="%.2f",
            )
        else:
            lifestyle_cut = None
            lifestyle_col.caption("No additional lifestyle-cut cap")
        deadline = st.date_input(
            "Target deadline",
            value=date.today() + timedelta(days=180),
            min_value=date.today(),
        )
        submitted = st.form_submit_button("Find my route", type="primary")

    if submitted:
        try:
            result = plan_savings_goal(
                goal_name,
                target_amount,
                current_savings,
                max_monthly_saving,
                baseline_monthly_savings=baseline,
                maximum_lifestyle_cut=lifestyle_cut,
            )
            saved_goal = None
            user_id = st.session_state.get("user_id")
            if user_id:
                saved_goal = save_user_goal(
                    user_id,
                    goal_name,
                    target_amount,
                    current_savings,
                    max_monthly_saving,
                    deadline,
                )
        except ValueError as error:
            st.session_state.pop("goal_planner_run", None)
            st.error(str(error))
        else:
            st.session_state["goal_planner_run"] = {
                "goal_name": goal_name.strip(),
                "target_amount": float(target_amount),
                "current_savings": float(current_savings),
                "maximum_monthly_saving": float(max_monthly_saving),
                "baseline_monthly_savings": baseline,
                "maximum_lifestyle_cut": lifestyle_cut,
                "deadline": deadline.isoformat(),
                "saved_goal_id": saved_goal["goal_id"] if saved_goal else None,
                "result": result,
                "transaction_fingerprint": transaction_fingerprint(frame),
            }

    run = st.session_state.get("goal_planner_run")
    if run is not None:
        _render_result(run["result"])
        if run.get("saved_goal_id"):
            st.caption(f"This goal and deadline are saved to your account and are available to the dashboard and purchase check.")
        if run.get("deadline") and run["result"].goal_month:
            target_date = date.fromisoformat(run["deadline"])
            if run["result"].goal_month > target_date.replace(day=1):
                st.warning(f"The A* path reaches this goal after your selected deadline of {target_date:%B %d, %Y}.")


def _render_result(result: GoalPlanResult) -> None:
    st.subheader(f"Roadmap · {result.goal_name}")
    st.markdown(f"**Route status:** {'A route fits your saving limit' if result.feasible else 'No route fits these inputs'}")
    if not result.feasible:
        st.error(result.explanation)
        st.metric("Monthly options checked", f"{result.nodes_explored:,}")
        if result.explored_states:
            st.dataframe(pd.DataFrame(result.explored_states[:30]), width="stretch", hide_index=True)
        return

    months_col, date_col, cost_col, nodes_col = st.columns(4)
    months_col.metric("Months to goal", f"{result.path_length}")
    date_col.metric("Goal achievement month", result.goal_month.strftime("%B %Y"))
    cost_col.metric("Lifestyle adjustment", f"{result.final_cost:.2f}")
    nodes_col.metric("Monthly options checked", f"{result.nodes_explored:,}")

    st.subheader("Selected monthly path")
    path_frame = pd.DataFrame(result.selected_path)
    path_frame["month"] = pd.to_datetime(path_frame["month"])
    path_display = path_frame[
        ["month", "monthly_saving", "savings", "remaining_target", "disruption_penalty"]
    ].rename(
        columns={
            "month": "Month",
            "monthly_saving": "Monthly saving",
            "savings": "Cumulative savings",
            "remaining_target": "Remaining target",
            "disruption_penalty": "Lifestyle adjustment",
        }
    )
    st.dataframe(
        path_display,
        width="stretch",
        hide_index=True,
        column_config={
            "Monthly saving": st.column_config.NumberColumn(format="$%.2f"),
            "Cumulative savings": st.column_config.NumberColumn(format="$%.2f"),
            "Remaining target": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    chart = px.line(
        path_frame,
        x="month",
        y="savings",
        markers=True,
        labels={"month": "Month", "savings": "Cumulative savings (USD)"},
        color_discrete_sequence=["#0F766E"],
    )
    chart.add_hline(y=result.target_amount, line_dash="dash", line_color="#F59E0B")
    chart.update_layout(
        template="plotly_white",
        height=340,
        margin=dict(l=12, r=12, t=16, b=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, sans-serif", color="#134E4A"),
        xaxis=dict(showgrid=False, tickfont=dict(color="#134E4A")),
        yaxis=dict(gridcolor="#E2E8F0", tickfont=dict(color="#134E4A")),
    )
    st.plotly_chart(chart, width="stretch", theme=None, config={"displayModeBar": False})

    st.subheader("Why this route was selected")
    st.write("The route reaches your goal using the monthly contributions shown below. It favors steady saving and adds a small adjustment when a step exceeds your usual monthly surplus.")
    st.markdown("**Initial state**")
    st.dataframe(pd.DataFrame([result.initial_state]), width="stretch", hide_index=True)
    with st.expander(f"Other monthly options considered · {len(result.explored_states):,} total"):
        explored = pd.DataFrame(result.explored_states[:50]).rename(
            columns={
                "month": "Month",
                "savings": "Savings so far",
                "remaining_target": "Still needed",
                "month_index": "Months from now",
            }
        )
        display_columns = [column for column in ["Month", "Months from now", "Savings so far", "Still needed"] if column in explored]
        st.dataframe(explored[display_columns], width="stretch", hide_index=True)