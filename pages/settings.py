import pandas as pd
import streamlit as st

from models.rule_engine import RuleThresholds
from utils.auth import (
    add_custom_category,
    clear_user_financial_data,
    delete_custom_category,
    export_user_data,
    get_user_categories,
    get_user_preferences,
    get_user_thresholds,
    save_user_preferences,
    save_user_thresholds,
    user_transactions_path,
)
from utils.data_loader import DEFAULT_DATA_PATH, EXPENSE_CATEGORIES, INCOME_CATEGORIES, load_transactions, save_transactions


def render(frame: pd.DataFrame) -> None:
    st.title("Settings")
    st.caption("Personal preferences, custom categories, rule thresholds, and data controls.")
    if st.session_state.pop("_reset_clear_confirmation", False):
        st.session_state.pop("confirm_clear_user_data", None)
    if st.session_state.pop("_clear_user_data_notice", False):
        st.success("Your private financial data was cleared. Your account is still active.")
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.error("Sign in to manage your personal workspace settings.")
        return

    preferences = get_user_preferences(user_id)
    with st.form("settings_preferences_form"):
        default_period = st.selectbox(
            "Dashboard default period",
            ["This month", "Last 30 days", "Custom"],
            index=["This month", "Last 30 days", "Custom"].index(preferences["dashboard_period"]),
            help="The dashboard period selected when you first open it in a session.",
        )
        st.caption("Currency display is currently USD throughout the application.")
        preferences_saved = st.form_submit_button("Save preferences", type="primary")
    if preferences_saved:
        try:
            save_user_preferences(user_id, default_period)
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state[f"dashboard_period_{user_id}"] = default_period
            st.success("Your dashboard preference has been saved.")
            st.rerun()

    st.divider()
    _render_custom_categories_section(user_id)

    st.divider()
    _render_thresholds_tuning_section(user_id)

    st.divider()
    data_col, privacy_col = st.columns([1, 1], gap="large")
    with data_col:
        st.subheader("Example data")
        st.write("The bundled sample is illustrative only. It is copied into this account's private ledger only when you choose to load it.")
        if frame.empty:
            if st.button("Load Demo Data", type="primary"):
                try:
                    save_transactions(load_transactions(DEFAULT_DATA_PATH), user_transactions_path(user_id))
                except (OSError, ValueError) as error:
                    st.error(f"Could not load demo data: {error}")
                else:
                    st.success("Demo transactions were copied into your private ledger.")
                    st.rerun()
        else:
            st.info(f"Your ledger currently contains {len(frame):,} transactions. Loading demo data replaces this ledger.")
            confirm_demo = st.checkbox("Replace my current ledger with the bundled demo")
            if st.button("Load Demo Data", disabled=not confirm_demo):
                try:
                    save_transactions(load_transactions(DEFAULT_DATA_PATH), user_transactions_path(user_id))
                except (OSError, ValueError) as error:
                    st.error(f"Could not load demo data: {error}")
                else:
                    st.success("Your private ledger now contains the bundled demo transactions.")
                    st.rerun()
    with privacy_col:
        st.subheader("Privacy")
        st.info("FinWise stores your account, profile, goals, preferences, and transaction CSV locally. It does not connect to banks or send transactions to a cloud service.")
        st.write("Dashboard and purchase checks use your account's ledger. Purchase training labels are synthetic/demo data shared by the local installation.")
        st.download_button(
            "Export My Data",
            data=export_user_data(user_id),
            file_name="finwise_my_data.zip",
            mime="application/zip",
        )
        st.markdown("**Current look**")
        st.write("Teal and mint · light surfaces · USD")

    st.subheader("Module status")
    status = pd.DataFrame(
        [
            {"Module": "Spending Insights", "Status": "Needs 3+ transaction months", "Uses": "This account's monthly ledger"},
            {"Module": "Should I Buy This?", "Status": "Ready · synthetic training", "Uses": "This account plus demo-labeled outcomes"},
            {"Module": "Smart Budget Helper", "Status": "Ready when inputs are entered", "Uses": "Your budget targets"},
            {"Module": "Goal Pathfinder", "Status": "Ready when a goal is saved", "Uses": "Your goals and savings limit"},
        ],
    )
    st.dataframe(status, width="stretch", hide_index=True)

    st.divider()
    st.subheader("Clear all my financial data")
    st.caption("This clears your transaction ledger, goals, saved preferences, and profile picture. It keeps your login account.")
    confirmed = st.checkbox("I understand this cannot be undone", key="confirm_clear_user_data")
    if st.button("Clear all my data", disabled=not confirmed, type="secondary"):
        try:
            clear_user_financial_data(user_id)
        except (OSError, ValueError) as error:
            st.error(f"Could not clear account data: {error}")
        else:
            for key in ["purchase_advisor_run", "budget_optimizer_run", "rule_advisor_run", "goal_planner_run"]:
                st.session_state.pop(key, None)
            st.session_state.pop(f"dashboard_period_{user_id}", None)
            st.session_state["_reset_clear_confirmation"] = True
            st.session_state["_clear_user_data_notice"] = True
            st.rerun()


def _render_custom_categories_section(user_id: str) -> None:
    st.subheader("Custom Categories")
    st.write("Add your own custom categories for categorizing income and expenses in addition to system defaults.")

    user_cats = get_user_categories(user_id)
    custom_incomes = [c for c in user_cats["income"] if c not in INCOME_CATEGORIES]
    custom_expenses = [c for c in user_cats["expense"] if c not in EXPENSE_CATEGORIES]

    col_add, col_list = st.columns([1, 1], gap="large")
    with col_add:
        with st.form("add_custom_category_form", clear_on_submit=True):
            cat_name = st.text_input("New category name", max_chars=50, placeholder="e.g. Pet Care, Freelance Design")
            cat_type = st.radio("Category Type", ["Expense", "Income"], horizontal=True)
            submitted_cat = st.form_submit_button("Add Category", type="primary")

        if submitted_cat:
            if not cat_name.strip():
                st.error("Please enter a category name.")
            else:
                try:
                    add_custom_category(user_id, cat_name.strip(), cat_type)
                except ValueError as err:
                    st.error(str(err))
                else:
                    st.success(f"Added custom {cat_type.lower()} category: '{cat_name.strip()}'.")
                    st.rerun()

    with col_list:
        st.markdown("**Your Custom Categories**")
        all_custom = [(c, "Income") for c in custom_incomes] + [(c, "Expense") for c in custom_expenses]
        if not all_custom:
            st.caption("No custom categories added yet. All system default categories are active.")
        else:
            for name, c_type in all_custom:
                c_col1, c_col2 = st.columns([3, 1])
                c_col1.write(f"• **{name}** ({c_type})")
                if c_col2.button("Delete", key=f"del_cat_{name}_{c_type}"):
                    try:
                        delete_custom_category(user_id, name)
                    except Exception as err:
                        st.error(str(err))
                    else:
                        st.success(f"Deleted '{name}'.")
                        st.rerun()


def _render_thresholds_tuning_section(user_id: str) -> None:
    st.subheader("Financial Rule Thresholds")
    st.write("Tune personal benchmark limits for the Money Rules engine to match your financial situation.")

    current = get_user_thresholds(user_id)
    with st.form("rule_thresholds_tuning_form"):
        r_col1, r_col2 = st.columns(2)
        savings_low = r_col1.slider(
            "Minimum Savings Ratio Alert Threshold (%)",
            min_value=1,
            max_value=30,
            value=int(round(current.savings_low * 100)),
            help="Alerts if monthly savings falls below this percentage of monthly income (Default: 10%).",
        )
        savings_healthy = r_col2.slider(
            "Healthy Savings Ratio Target (%)",
            min_value=10,
            max_value=50,
            value=int(round(current.savings_healthy * 100)),
            help="Positive recommendation triggered when savings meet or exceed this level (Default: 20%).",
        )

        d_col1, d_col2 = st.columns(2)
        discretionary = d_col1.slider(
            "Maximum Discretionary Spending Cap (%)",
            min_value=5,
            max_value=50,
            value=int(round(current.discretionary * 100)),
            help="Alerts if entertainment/flexible spending exceeds this portion of total expenses (Default: 20%).",
        )
        burn_rate = d_col2.slider(
            "Maximum 30-Day Burn Rate of Income (%)",
            min_value=40,
            max_value=120,
            value=int(round(current.burn_rate_income * 100)),
            help="Alerts if 30-day estimated expenses exceed this share of monthly income (Default: 80%).",
        )

        debt_income = st.slider(
            "Maximum Debt-to-Income Payment Ratio (%)",
            min_value=5,
            max_value=50,
            value=int(round(current.debt_income * 100)),
            help="Alerts if monthly debt payments exceed this share of monthly income (Default: 20%).",
        )

        save_btn = st.form_submit_button("Save Thresholds", type="primary")

    if save_btn:
        new_thresholds = RuleThresholds(
            savings_low=savings_low / 100.0,
            savings_healthy=savings_healthy / 100.0,
            discretionary=discretionary / 100.0,
            burn_rate_income=burn_rate / 100.0,
            debt_income=debt_income / 100.0,
        )
        save_user_thresholds(user_id, new_thresholds)
        st.session_state.pop("rule_advisor_run", None)
        st.success("Rule thresholds updated! Money Rules checks will evaluate against your new parameters.")
        st.rerun()