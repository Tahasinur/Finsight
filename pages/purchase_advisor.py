"""Plain-language purchase verdicts with model output and goal impact."""

from calendar import monthrange
from datetime import date

import pandas as pd
import streamlit as st

from models.purchase_classifier import (
    CLASS_NAMES,
    CATEGORY_IMPACT_WEIGHTS,
    simulate_goal_impact,
    train_purchase_models,
    predict_purchase,
)
from models.spending_clustering import fit_spending_clusters
from utils.auth import get_user_goals
from utils.calculations import format_currency, monthly_financial_metrics, transaction_fingerprint


@st.cache_resource(show_spinner="Preparing the demo-trained models...")
def _trained_models():
    return train_purchase_models()


def render(frame: pd.DataFrame) -> None:
    st.title("Should I Buy This?")
    st.caption("Check how a purchase may affect your monthly budget and the goals you have saved.")
    st.warning(
        "This estimate learns from labeled synthetic examples, not real purchase outcomes. Use it as a thinking aid, not financial advice."
    )

    models = _trained_models()
    monthly = monthly_financial_metrics(frame)
    latest = monthly.iloc[-1] if not monthly.empty else None
    monthly_income = float(latest["income"]) if latest is not None else 0.0
    monthly_expenses = float(latest["expenses"]) if latest is not None else 0.0
    savings_rate = float(latest["savings_ratio"]) if latest is not None and pd.notna(latest["savings_ratio"]) else 0.0
    discretionary_share = float(latest["discretionary_ratio"]) if latest is not None and pd.notna(latest["discretionary_ratio"]) else 0.0
    ledger_balance = max(0.0, float(frame.loc[frame["type"] == "income", "amount"].sum() - frame.loc[frame["type"] == "expense", "amount"].sum()))
    consumer_type, consumer_error = _consumer_type(frame)
    context_cols = st.columns(4)
    context_cols[0].metric("Recorded monthly income", format_currency(monthly_income))
    context_cols[1].metric("Recorded monthly spending", format_currency(monthly_expenses))
    context_cols[2].metric("Recorded savings rate", f"{savings_rate:.1%}")
    context_cols[3].metric("Spending pattern", consumer_type)
    if consumer_error:
        st.caption(consumer_error)
    today = date.today()
    active_goals = [
        goal
        for goal in _active_goals()
        if date.fromisoformat(goal["deadline_date"]) >= today
        and float(goal["current_savings"]) < float(goal["target_amount"])
    ]
    goal_by_id = {goal["goal_id"]: goal for goal in active_goals}
    nearest_goal = min(active_goals, key=lambda goal: goal["deadline_date"]) if active_goals else None
    nearest_goal_days = _days_until_goal(nearest_goal) if nearest_goal else 3650
    nearest_goal_gap = _goal_gap(nearest_goal) if nearest_goal else 0.0
    month_days = monthrange(date.today().year, date.today().month)[1]
    days_left_default = max(0, month_days - date.today().day)

    with st.form("should_i_buy_form"):
        name_col, category_col = st.columns([1.4, 1])
        item_name = name_col.text_input("What are you thinking of buying?", max_chars=100)
        category = category_col.selectbox("Category (optional)", list(CATEGORY_IMPACT_WEIGHTS))
        price_col, balance_col = st.columns(2)
        price = price_col.number_input("Price", min_value=0.0, value=0.0, step=10.0, format="%.2f")
        balance = balance_col.number_input(
            "Your current available balance",
            min_value=0.0,
            value=round(ledger_balance, 2),
            step=100.0,
            format="%.2f",
            help="Prefilled from recorded ledger net flow. Replace this with your actual available cash; no bank API is connected.",
        )
        days_col, urgency_col = st.columns(2)
        days_left = days_col.number_input("Days left this month", min_value=0, max_value=31, value=days_left_default)
        urgency = urgency_col.select_slider("How important is this purchase?", options=[1, 2, 3, 4, 5], value=3)
        goal_options = ["none", *goal_by_id]
        goal_id = st.selectbox(
            "Goal this purchase could affect (optional)",
            goal_options,
            format_func=lambda value: _goal_option_label(value, goal_by_id),
        )
        submitted = st.form_submit_button("Check this purchase", type="primary", use_container_width=True)

    if submitted:
        if not item_name.strip():
            st.error("Add an item name so the result is easy to review.")
            st.session_state.pop("purchase_advisor_run", None)
        elif price <= 0:
            st.error("Enter a price greater than zero.")
            st.session_state.pop("purchase_advisor_run", None)
        elif balance <= 0:
            st.error("Enter a positive available balance before evaluating affordability.")
            st.session_state.pop("purchase_advisor_run", None)
        else:
            selected_goal = goal_by_id.get(goal_id)
            selected_goal_days = _days_until_goal(selected_goal) if selected_goal else 3650
            try:
                prediction = predict_purchase(
                    models,
                    item_cost=price,
                    current_balance=balance,
                    days_left_in_month=days_left,
                    goal_urgency=urgency,
                    category=category,
                    monthly_income=monthly_income,
                    monthly_expenses=monthly_expenses,
                    savings_rate=savings_rate,
                    discretionary_spending_share=discretionary_share,
                    nearest_goal_days_left=nearest_goal_days,
                    goal_gap_ratio=nearest_goal_gap,
                    consumer_type=consumer_type,
                )
                goal_impact = None
                if selected_goal:
                    goal_impact = simulate_goal_impact(
                        price,
                        float(selected_goal["target_amount"]),
                        float(selected_goal["current_savings"]),
                        selected_goal_days,
                        float(selected_goal["monthly_saving_limit"]),
                    )
                alternative = _alternative_suggestion(
                    models,
                    prediction["verdict"],
                    price,
                    balance,
                    days_left,
                    urgency,
                    category,
                    monthly_income,
                    monthly_expenses,
                    savings_rate,
                    discretionary_share,
                    nearest_goal_days,
                    nearest_goal_gap,
                    consumer_type,
                )
            except ValueError as error:
                st.error(str(error))
                st.session_state.pop("purchase_advisor_run", None)
            else:
                st.session_state["purchase_advisor_run"] = {
                    "item_name": item_name.strip(),
                    "price": float(price),
                    "balance": float(balance),
                    "prediction": prediction,
                    "consumer_type": consumer_type,
                    "goal": selected_goal,
                    "goal_impact": goal_impact,
                    "alternative": alternative,
                    "transaction_fingerprint": transaction_fingerprint(frame),
                }

    run = st.session_state.get("purchase_advisor_run")
    if run is not None:
        if run.get("transaction_fingerprint") != transaction_fingerprint(frame):
            st.warning("Your transaction ledger changed since this check. Run it again for an up-to-date result.")
        else:
            _render_prediction(run, models)

    with st.expander("Why this is only a guide"):
        st.write("The two estimates learn from synthetic/demo examples because no real labeled purchase outcomes are available.")
        st.write("Confidence describes how strongly the tools favor a verdict for these inputs. It is not the chance that buying will work out in real life.")
        st.write("The check combines your entered balance with recorded income and spending, saved goal deadlines, purchase importance, category, and the spending pattern found in your history.")


def _consumer_type(frame: pd.DataFrame) -> tuple[str, str | None]:
    try:
        result = fit_spending_clusters(frame)
        return result.latest_profile, None
    except ValueError as error:
        return "Unknown", f"Consumer type needs at least three distinct months of transactions. Purchase check will not assume a profile. {error}"


def _active_goals() -> list[dict]:
    user_id = st.session_state.get("user_id")
    if not user_id:
        return []
    return [goal for goal in get_user_goals(user_id) if goal["active"]]


def _goal_option_label(goal_id: str, goals: dict[str, dict]) -> str:
    if goal_id == "none":
        return "No goal selected"
    goal = goals[goal_id]
    return f"{goal['goal_name']} · {goal['deadline_date']} · {format_currency(goal['target_amount'])}"


def _days_until_goal(goal: dict) -> int:
    deadline = date.fromisoformat(goal["deadline_date"])
    return max(0, (deadline - date.today()).days)


def _goal_gap(goal: dict) -> float:
    target = float(goal["target_amount"])
    return max(0.0, min(1.0, (target - float(goal["current_savings"])) / target))


def _render_prediction(run: dict, models) -> None:
    prediction = run["prediction"]
    verdict = prediction["verdict"]
    verdict_colors = {
        "Strong Yes": ("#D1FAE5", "#065F46"),
        "Cautious Yes": ("#FEF3C7", "#92400E"),
        "Better Wait": ("#FFEDD5", "#9A3412"),
        "No": ("#FEE2E2", "#991B1B"),
    }
    background, text = verdict_colors[verdict]
    st.markdown(
        f"<div style='padding:22px 24px;margin:16px 0;border-radius:14px;background:{background};color:{text};'>"
        f"<div style='font:700 12px Manrope,sans-serif;text-transform:uppercase;'>Purchase check</div>"
        f"<div style='font:800 30px Manrope,sans-serif;margin:5px 0;'>{verdict}</div>"
        f"<div style='font:600 14px DM Sans,sans-serif;'>{run['item_name']} · {format_currency(run['price'])}</div></div>",
        unsafe_allow_html=True,
    )
    primary_col, confidence_col, profile_col = st.columns(3)
    primary_col.metric("Main estimate", verdict)
    confidence_col.metric("Estimate confidence", f"{prediction['confidence']:.1%}", help="Computed from this tool's synthetic/demo training examples, not real purchase outcomes.")
    profile_col.metric("Your spending style", run["consumer_type"])

    st.markdown("**The estimate and a second opinion**")
    probability_cols = st.columns(2)
    for column, model_name, model_prediction in [
        (probability_cols[0], "Main estimate", prediction["logistic_regression"]),
        (probability_cols[1], "Second opinion", prediction["knn"]),
    ]:
        with column:
            st.markdown(f"**{model_name}: {model_prediction['predicted_class']}**")
            st.dataframe(_probability_table(model_prediction["probabilities"]), width="stretch", hide_index=True)

    st.markdown("**Why this result**")
    for reason in _plain_reasons(run, prediction):
        st.markdown(f"- {reason}")

    st.subheader("Goal impact")
    goal = run.get("goal")
    impact = run.get("goal_impact")
    if goal is None or impact is None:
        st.info("Select one of your saved goals during the next check to estimate deadline impact.")
    else:
        st.markdown(f"**{goal['goal_name']}** · target {format_currency(goal['target_amount'])} by {goal['deadline_date']}")
        impact_cols = st.columns(2)
        if impact["extra_months"] is not None:
            impact_cols[0].metric("Extra time at current saving pace", f"{impact['extra_months']} months")
        else:
            impact_cols[0].metric("Extra time at current saving pace", "Saving pace not set")
        impact_cols[1].metric("Extra monthly saving to offset purchase", format_currency(impact["extra_monthly_savings"]))
        st.caption(
            f"Simulation assumes the purchase amount would otherwise go toward this goal, "
            f"using a {impact['months_to_deadline']}-month deadline window and the goal's saved monthly limit."
        )

    if verdict in {"Better Wait", "No"}:
        st.info(f"**Alternative:** {run['alternative']}")
    st.caption("This is an educational model using synthetic labels, not a guarantee or personalized financial advice.")

    with st.expander("Details used in this check"):
        labels = {
            "item_cost_balance_ratio": "Price / available balance",
            "item_cost_monthly_income_ratio": "Price / monthly income",
            "days_left_in_month": "Days left this month",
            "goal_urgency": "Purchase urgency (1-5)",
            "category_impact_weight": "Category effect on spending",
            "monthly_expense_ratio": "Monthly expenses / income",
            "savings_rate": "Recorded savings rate",
            "discretionary_spending_share": "Discretionary spending share",
            "nearest_goal_days_left": "Days to selected goal",
            "goal_gap_ratio": "Selected goal still unfunded",
            "consumer_heavy_flag": "Heavy Consumer profile flag",
            "consumer_light_flag": "Light Consumer profile flag",
            "consumer_balanced_flag": "Balanced Consumer profile flag",
        }
        features = prediction["features"]
        st.dataframe(
            pd.DataFrame([{"Input": labels[key], "Value": value} for key, value in features.items()]),
            width="stretch",
            hide_index=True,
        )
        st.caption(f"Training set: {models.training_rows:,} synthetic examples; holdout: {models.test_rows:,}. No real purchase outcome dataset is available.")


def _plain_reasons(run: dict, prediction: dict) -> list[str]:
    features = prediction["features"]
    reasons = [
        f"This purchase is {features['item_cost_balance_ratio']:.0%} of the available balance you entered.",
        f"Recorded monthly expenses are {features['monthly_expense_ratio']:.0%} of income and the recorded savings rate is {features['savings_rate']:.0%}.",
    ]
    consumer_flags = [
        (name, features[field])
        for name, field in [
            ("Heavy Consumer", "consumer_heavy_flag"),
            ("Light Consumer", "consumer_light_flag"),
            ("Balanced Consumer", "consumer_balanced_flag"),
        ]
        if features[field] == 1
    ]
    if consumer_flags:
        reasons.append(f"Your recent monthly spending patterns cluster as {consumer_flags[0][0]}.")
    else:
        reasons.append("There is not enough monthly history to assign a consumer profile; the model received no profile flag.")
    if run.get("goal") and run.get("goal_impact"):
        impact = run["goal_impact"]
        if impact["extra_months"] is not None:
            reasons.append(f"At the goal's saved monthly pace, this could add about {impact['extra_months']} month(s) to {run['goal']['goal_name']}.")
        else:
            reasons.append(f"The selected goal has no monthly saving pace, so the deadline effect for {run['goal']['goal_name']} cannot be timed yet.")
    return reasons


def _alternative_suggestion(models, verdict, price, balance, days_left, urgency, category, income, expenses, savings, discretionary, goal_days, goal_gap, consumer_type) -> str:
    order = {name: position for position, name in enumerate(CLASS_NAMES)}
    for discount in [0.85, 0.70, 0.55, 0.40, 0.25]:
        alternative_price = round(price * discount, 2)
        alternative = predict_purchase(
            models,
            item_cost=alternative_price,
            current_balance=balance,
            days_left_in_month=days_left,
            goal_urgency=urgency,
            category=category,
            monthly_income=income,
            monthly_expenses=expenses,
            savings_rate=savings,
            discretionary_spending_share=discretionary,
            nearest_goal_days_left=goal_days,
            goal_gap_ratio=goal_gap,
            consumer_type=consumer_type,
        )
        if order[alternative["verdict"]] < order[verdict]:
            return f"A lower-cost option near {format_currency(alternative_price)} shifts the demo model's verdict to {alternative['verdict']}. Compare the real price and your priorities before deciding."
    return "Consider waiting until your available balance or monthly savings capacity is stronger, then run the check again."


def _probability_table(probabilities: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Verdict": name, "Model probability": f"{probabilities.get(name, 0.0):.1%}"} for name in CLASS_NAMES]
    )