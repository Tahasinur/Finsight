"""Structured report combining current metrics and completed module runs."""

import pandas as pd
import streamlit as st

from models.preprocessing import preprocess_transactions
from models.spending_clustering import fit_spending_clusters
from utils.auth import get_latest_analysis_run
from utils.calculations import format_currency, monthly_financial_metrics, transaction_fingerprint


PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2, "Positive": 3}


def render(frame: pd.DataFrame) -> None:
    st.title("Your Money Snapshot")
    st.caption("A plain-language summary of your finances and completed planning tools.")

    user_id = st.session_state.get("user_id")
    signature = transaction_fingerprint(frame)
    runs = {}
    for key, module_type, label in [
        ("purchase_advisor_run", "purchase_advisor", "Should I Buy This?"),
        ("budget_optimizer_run", "budget_optimizer", "Smart Budget Helper"),
        ("rule_advisor_run", "rule_advisor", "Money Rules"),
        ("goal_planner_run", "goal_planner", "Goal Pathfinder"),
    ]:
        saved = st.session_state.get(key)
        if saved is None and user_id:
            persisted = get_latest_analysis_run(user_id, module_type)
            if persisted:
                saved = persisted
                st.session_state[key] = saved

        if saved is not None and saved.get("transaction_fingerprint") == signature:
            runs[key] = saved
        elif saved is not None:
            st.warning(f"{label} output is stale because the transaction ledger changed. Re-run that module to include its result.")

    try:
        processed = preprocess_transactions(frame)
    except ValueError as error:
        processed = None
        st.warning(f"Data Processing could not produce model features: {error}")
    monthly = monthly_financial_metrics(frame)
    latest = monthly.iloc[-1] if not monthly.empty else None

    st.header("FINANCIAL SUMMARY")
    if latest is None:
        st.info("No dated transactions are available for a financial summary.")
    else:
        summary_cols = st.columns(4)
        summary_cols[0].metric("Monthly income", format_currency(latest["income"]))
        summary_cols[1].metric("Monthly expenses", format_currency(latest["expenses"]))
        summary_cols[2].metric("Remaining balance", format_currency(latest["remaining_balance"]))
        summary_cols[3].metric(
            "Savings ratio",
            f"{latest['savings_ratio']:.1%}" if pd.notna(latest["savings_ratio"]) else "N/A",
        )
        detail_cols = st.columns(3)
        detail_cols[0].metric("Monthly burn rate", format_currency(latest["monthly_burn_rate"]))
        detail_cols[1].metric(
            "Discretionary ratio",
            f"{latest['discretionary_ratio']:.1%}" if pd.notna(latest["discretionary_ratio"]) else "N/A",
        )
        if processed is not None:
            detail_cols[2].metric("Missing source values", int(processed.missing_values.sum()))
        else:
            detail_cols[2].metric("Processed features", "Unavailable")
        st.caption(
            f"Latest transaction month: {latest['month']:%B %Y} · "
            f"{len(frame):,} ledger rows"
            + (
                f" · {processed.model_features.shape[1]:,} processed features"
                if processed is not None
                else " · processed features unavailable"
            )
        )

    st.header("SPENDING PATTERN")
    try:
        signature = transaction_fingerprint(frame) if not frame.empty else None
        with st.spinner("Synthesizing spending behavior profile..."):
            profile = fit_spending_clusters(frame, fingerprint=signature) if not frame.empty else None
    except ValueError as error:
        profile = None
        st.info(f"A consumer type is not available yet: {error}")
    if profile is not None:
        st.markdown(
            f"**Latest-month profile:** {profile.latest_profile} · "
            f"cluster {profile.latest_cluster + 1} of 3"
        )
        latest_features = profile.monthly_features.iloc[-1]
        st.write(
            f"Based on {len(profile.monthly_features)} monthly observations. "
            f"Savings ratio {latest_features['savings_ratio']:.1%}, "
            f"discretionary ratio {latest_features['discretionary_ratio']:.1%}, "
            f"and monthly burn rate {format_currency(latest_features['monthly_burn_rate'])}."
        )
        st.caption("This type summarizes the account's recorded history; it is not a diagnosis or financial-risk rating.")

    st.header("BUDGET SUGGESTIONS")
    budget_run = runs.get("budget_optimizer_run")
    if budget_run is None:
        st.info("Run Smart Budget Helper to add a current allocation to this report.")
    else:
        budget = budget_run["result"]
        st.markdown(f"**Plan status:** {budget.status}")
        if budget.feasible:
            allocation_table = pd.DataFrame(
                [
                    {"Allocation": name.replace("_", " ").title(), "Amount": amount}
                    for name, amount in budget.allocations.items()
                ]
            )
            st.dataframe(allocation_table, width="stretch", hide_index=True)
            st.caption(budget.explanation)
        else:
            st.warning(budget.explanation)

    st.header("SHOULD I BUY THIS?")
    purchase_run = runs.get("purchase_advisor_run")
    if purchase_run is None:
        st.info("Check a purchase to include its main estimate, second opinion, and goal impact.")
    else:
        prediction = purchase_run["prediction"]
        primary = prediction["logistic_regression"]
        comparison = prediction["knn"]
        purchase_cols = st.columns(3)
        purchase_cols[0].metric("Product", purchase_run["item_name"])
        purchase_cols[1].metric("Main estimate", primary["predicted_class"])
        purchase_cols[2].metric("Second opinion", comparison["predicted_class"])
        probabilities = pd.DataFrame(
            [
                {
                    "Class": class_name,
                    "Main estimate": f"{primary['probabilities'][class_name]:.2%}",
                    "Second opinion": f"{comparison['probabilities'][class_name]:.2%}",
                }
                for class_name in ["Strong Yes", "Cautious Yes", "Better Wait", "No"]
            ]
        )
        st.dataframe(probabilities, width="stretch", hide_index=True)
        st.caption("These estimates use synthetic/demo examples, not observed purchases; they are not real-world financial advice.")

    st.header("SAVING RECOMMENDATIONS")
    rule_run = runs.get("rule_advisor_run")
    triggered_rules = []
    if rule_run is None:
        st.info("Run Money Rules to include your reserve and debt inputs alongside this ledger's totals.")
    else:
        for rule in rule_run["rules"]:
            if rule["result"] == "Triggered":
                triggered_rules.append(rule)
                st.markdown(f"**{rule['rule_id']} · {rule['priority']} · {rule['condition']}**")
                st.write(rule["recommendation"])
                st.caption(f"Current: {rule['current_value']} · Threshold: {rule['threshold']} · {rule['details']}")
        if not triggered_rules:
            st.success("No configured rules triggered on the saved evaluation.")

    st.header("GOAL ROADMAP")
    goal_run = runs.get("goal_planner_run")
    if goal_run is None:
        st.info("Plan a goal in Goal Pathfinder to include its monthly route.")
    else:
        goal = goal_run["result"]
        st.markdown(f"**{goal.goal_name}:** {goal.status}")
        if goal.feasible:
            st.write(
                f"Target {format_currency(goal.target_amount)} in {goal.path_length} months, "
                f"estimated for {goal.goal_month:%B %Y}."
            )
            st.dataframe(pd.DataFrame(goal.selected_path), width="stretch", hide_index=True)
        else:
            st.warning(goal.explanation)

    st.header("TOP 3 ACTIONS")
    actions = _build_actions(triggered_rules, purchase_run, budget_run, goal_run)
    if not actions:
        st.info("No evidence-backed actions are available from the completed module runs yet.")
    else:
        for position, action in enumerate(actions[:3], start=1):
            st.markdown(f"**{position}. {action['source']} · {action['priority']}**")
            st.write(action["text"])

    with st.expander("How to read this report"):
        st.write("Purchase estimates compare your inputs with synthetic examples. Spending types are learned from your own monthly transaction history.")
        st.write("Budget allocations are searched against your selected minimums and limits. Goal routes compare month-by-month savings choices.")
        st.write("The same figures appear on each module page. Saved outputs are included only if they still match the current ledger.")


def _build_actions(triggered_rules, purchase_run, budget_run, goal_run) -> list[dict]:
    actions = [
        {
            "priority": rule["priority"],
            "source": f"Money Rule {rule['rule_id']}",
            "text": rule["recommendation"],
        }
        for rule in triggered_rules
    if rule["priority"] != "Positive"
    ]

    if purchase_run is not None:
        prediction = purchase_run["prediction"]["logistic_regression"]["predicted_class"]
        if prediction in {"Better Wait", "No"}:
            actions.append(
                {
                    "priority": "High" if prediction == "No" else "Medium",
                    "source": "Purchase estimate",
                    "text": f"Review {purchase_run['item_name']} before proceeding; the demo-trained estimate returned {prediction}.",
                }
            )

    if budget_run is not None and budget_run["result"].feasible:
        result = budget_run["result"]
        for variable, label in [("emergency_reserve", "emergency reserve"), ("savings", "savings")]:
            amount = result.allocations.get(variable, 0.0)
            if amount > 0:
                actions.append(
                    {
                        "priority": "Medium",
                        "source": "Smart Budget Helper",
                        "text": f"Use the searched allocation of {format_currency(amount)} for {label} within the feasible monthly budget.",
                    }
                )

    if goal_run is not None and goal_run["result"].feasible and goal_run["result"].path_length:
        goal = goal_run["result"]
        first_contribution = goal.selected_path[1]["monthly_saving"]
        actions.append(
            {
                "priority": "Medium",
                "source": "Goal Pathfinder",
                "text": f"Follow the first planned contribution of {format_currency(first_contribution)} toward {goal.goal_name}.",
            }
        )

    actions.sort(key=lambda action: (PRIORITY_ORDER.get(action["priority"], 4), action["source"]))
    return actions
