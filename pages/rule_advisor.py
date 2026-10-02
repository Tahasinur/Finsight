"""Present explainable financial rules against the current ledger metrics."""

from dataclasses import asdict

import pandas as pd
import streamlit as st

from models.rule_engine import RuleResult, evaluate_financial_rules
from utils.calculations import monthly_financial_metrics, transaction_fingerprint


def render(frame: pd.DataFrame) -> None:
    st.title("Money Rules")
    st.caption("See which simple money checks were met and what each result means.")

    monthly = monthly_financial_metrics(frame)
    if monthly.empty:
        metrics = {}
        inferred_debt_payment = 0.0
        st.warning("No dated transactions are available; ledger-based rules will be marked not evaluated.")
    else:
        latest = monthly.iloc[-1]
        metrics = {
            "income": float(latest["income"]),
            "savings_ratio": float(latest["savings_ratio"]),
            "discretionary_ratio": float(latest["discretionary_ratio"]),
            "monthly_burn_rate": float(latest["monthly_burn_rate"]),
        }
        latest_month = frame.loc[
            frame["date"].dt.to_period("M").dt.to_timestamp() == latest["month"]
        ]
        expenses = latest_month.loc[latest_month["type"] == "expense"]
        debt_mask = expenses["description"].astype("string").str.contains(
            "debt payment", case=False, na=False
        )
        inferred_debt_payment = float(expenses.loc[debt_mask, "amount"].sum())
        st.caption(f"Rules use {latest['month']:%B %Y} metrics from the shared transaction ledger.")

    with st.form("rule_advisor_form"):
        reserve_col, target_col, debt_col = st.columns(3)
        reserve_current = reserve_col.number_input(
            "Current emergency reserve",
            min_value=0.0,
            value=0.0,
            step=100.0,
            format="%.2f",
            help="Not inferred from transactions; enter the current amount you have set aside.",
        )
        reserve_target = target_col.number_input(
            "Configured emergency reserve target",
            min_value=0.0,
            value=0.0,
            step=100.0,
            format="%.2f",
        )
        debt_payment = debt_col.number_input(
            "Monthly debt payment",
            min_value=0.0,
            value=inferred_debt_payment,
            step=50.0,
            format="%.2f",
            help="Prefilled only from expenses whose description contains 'debt payment'. Verify or adjust it.",
        )
        submitted = st.form_submit_button("Evaluate rules", type="primary")

    if submitted:
        try:
            rules = evaluate_financial_rules(
                metrics,
                emergency_reserve_current=reserve_current,
                emergency_reserve_target=reserve_target,
                monthly_debt_payment=debt_payment,
            )
        except ValueError as error:
            st.session_state.pop("rule_advisor_run", None)
            st.error(str(error))
            return
        st.session_state["rule_advisor_run"] = {
            "metrics": metrics,
            "reserve_current": float(reserve_current),
            "reserve_target": float(reserve_target),
            "debt_payment": float(debt_payment),
            "rules": [asdict(rule) for rule in rules],
            "transaction_fingerprint": transaction_fingerprint(frame),
        }

    run = st.session_state.get("rule_advisor_run")
    if run is not None:
        rules = [RuleResult(**record) for record in run["rules"]]
        _render_rules(rules)


def _render_rules(rules: list[RuleResult]) -> None:
    st.subheader("Rule results")
    results_table = pd.DataFrame(
        [
            {
                "Rule ID": rule.rule_id,
                "Condition": rule.condition,
                "Current value": _display_value(rule.rule_id, rule.current_value),
                "Threshold": _display_value(rule.rule_id, rule.threshold),
                "Result": rule.result,
                "Priority": rule.priority,
                "Recommendation": rule.recommendation if rule.result == "Triggered" else "—",
            }
            for rule in rules
        ]
    )
    st.dataframe(results_table, width="stretch", hide_index=True)

    st.subheader("Rule details")
    for rule in rules:
        with st.expander(f"{rule.rule_id} · {rule.result} · {rule.priority} priority"):
            st.markdown(f"**Condition:** {rule.condition}")
            st.write(f"Current value: {_display_value(rule.rule_id, rule.current_value)}")
            st.write(f"Threshold: {_display_value(rule.rule_id, rule.threshold)}")
            st.write(f"Result: {rule.result}")
            st.write(f"Priority: {rule.priority}")
            st.write(f"Recommendation: {rule.recommendation}")
            st.caption(rule.details)


def _display_value(rule_id: str, value: float | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if rule_id in {"R01", "R02", "R03", "R05", "R06"}:
        return f"{value:.1%}"
    return f"${value:,.2f}"