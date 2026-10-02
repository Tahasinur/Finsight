"""Admin-only operational overview with aggregate-only user visibility."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.metrics import silhouette_score

from models.purchase_classifier import SYNTHETIC_DATASET_PATH, train_purchase_models
from models.spending_clustering import fit_spending_clusters
from utils.auth import get_admin_system_stats, list_user_summaries
from utils.calculations import format_currency
from utils.data_loader import DEFAULT_DATA_PATH, load_transactions, save_transactions


@st.cache_resource(show_spinner="Training the shared synthetic demo classifiers...")
def _global_purchase_models():
    return train_purchase_models()


def render(user: dict, own_frame: pd.DataFrame, own_store_path: str | Path) -> None:
    if user.get("role") != "admin":
        st.error("Administrator access is required.")
        return

    st.title("Admin Console")
    st.caption("Local system health and aggregate account counts. Other users' transaction details are not available here.")
    try:
        stats = get_admin_system_stats(user["user_id"])
        users = list_user_summaries(user["user_id"])
    except PermissionError as error:
        st.error(str(error))
        return

    stat_cols = st.columns(4)
    stat_cols[0].metric("Accounts", f"{stats['user_count']:,}")
    stat_cols[1].metric("Admin accounts", f"{stats['admin_count']:,}")
    stat_cols[2].metric("Private ledgers", f"{stats['private_ledger_count']:,}")
    stat_cols[3].metric("Transaction rows", f"{stats['transaction_row_count']:,}")
    st.caption("Counts only; no other account's transaction descriptions, categories, dates, or amounts are shown.")

    st.subheader("Accounts")
    account_table = pd.DataFrame(users)
    if account_table.empty:
        st.info("No registered accounts.")
    else:
        st.dataframe(account_table, width="stretch", hide_index=True)

    st.subheader("Global demo model evaluation")
    st.caption("Purchase metrics use synthetic/demo labels. The clustering view uses only the bundled example ledger, never other users' private data.")
    models = _global_purchase_models()
    model_metrics = pd.DataFrame(
        [
            {
                "Model": name,
                "Accuracy": result.accuracy,
                "Precision": result.precision,
                "Recall": result.recall,
                "F1": result.f1,
            }
            for name, result in models.evaluation.items()
        ]
    )
    st.dataframe(model_metrics, width="stretch", hide_index=True)
    demo_transactions = load_transactions(DEFAULT_DATA_PATH)
    try:
        clusters = fit_spending_clusters(demo_transactions)
    except ValueError as error:
        st.info(f"Example-ledger consumer profile is unavailable: {error}")
    else:
        distribution = clusters.assignments.groupby("profile").size().rename("Months").reset_index()
        figure = px.bar(
            distribution,
            x="profile",
            y="Months",
            color="profile",
            color_discrete_map={"Heavy Consumer": "#F87171", "Balanced Consumer": "#F59E0B", "Light Consumer": "#10B981"},
        )
        figure.update_layout(
            template="plotly_white",
            height=260,
            margin=dict(l=8, r=8, t=8, b=8),
            showlegend=False,
            font=dict(family="DM Sans, sans-serif", color="#134E4A"),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(figure, width="stretch", theme=None, config={"displayModeBar": False})
        st.metric("Example K-Means inertia", f"{clusters.model.inertia_:.3f}")
        if len(clusters.assignments) > clusters.assignments["cluster"].nunique() > 1:
            st.metric("Example silhouette score", f"{silhouette_score(clusters.scaled_features, clusters.assignments['cluster']):.3f}")

    st.subheader("Sample data management")
    demo_col, model_col = st.columns(2, gap="large")
    with demo_col:
        st.markdown("**Example transactions**")
        st.caption(f"Bundled, illustrative ledger: {len(demo_transactions):,} rows. It is never used as an account's live ledger unless that account chooses to copy it.")
        if st.button("Copy example transactions to my own ledger"):
            try:
                save_transactions(demo_transactions, own_store_path)
            except (OSError, ValueError) as error:
                st.error(f"Could not copy the example data: {error}")
            else:
                st.success("Example transactions copied to your own admin ledger.")
                st.rerun()
        st.download_button(
            "Download example transactions",
            data=DEFAULT_DATA_PATH.read_bytes(),
            file_name="finwise_example_transactions.csv",
            mime="text/csv",
        )
    with model_col:
        st.markdown("**Purchase training set**")
        if SYNTHETIC_DATASET_PATH.is_file():
            demo_rows = sum(1 for _ in SYNTHETIC_DATASET_PATH.open("r", encoding="utf-8")) - 1
            st.caption(f"Synthetic/demo labeled rows: {max(0, demo_rows):,}")
            st.download_button(
                "Download synthetic training data",
                data=SYNTHETIC_DATASET_PATH.read_bytes(),
                file_name="finwise_synthetic_purchase_training.csv",
                mime="text/csv",
            )
        else:
            st.info("Synthetic training data is generated the first time the purchase models load.")

    with st.expander("Admin role setup"):
        st.write("Set FINWISE_ADMIN_EMAIL before registering the bootstrap administrator. Existing accounts can be granted the role by setting this value and signing in with that email. Never expose an admin-creation control to public registration.")
        st.code("$env:FINWISE_ADMIN_EMAIL = 'admin@example.com'", language="powershell")
