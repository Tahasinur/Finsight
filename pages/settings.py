"""Per-account preferences, sample data controls, and local privacy details."""

import pandas as pd
import streamlit as st

from utils.auth import (
    clear_user_financial_data,
    export_user_data,
    get_user_preferences,
    save_user_preferences,
    user_transactions_path,
)
from utils.data_loader import DEFAULT_DATA_PATH, load_transactions, save_transactions


def render(frame: pd.DataFrame) -> None:
    st.title("Settings")
    st.caption("Personal preferences and data controls for this local account.")
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