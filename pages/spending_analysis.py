"""Explain monthly spending patterns in everyday language."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from models.spending_clustering import CLUSTER_FEATURES, fit_spending_clusters
from models.preprocessing import preprocess_transactions


PROFILE_COLORS = {
    "Heavy Consumer": "#F87171",
    "Balanced Consumer": "#F59E0B",
    "Light Consumer": "#10B981",
}


def render(frame: pd.DataFrame) -> None:
    st.title("Spending Insights")
    st.caption("Compare how your spending, saving, and purchase activity changes from month to month.")

    if frame.empty:
        st.info("Add transactions across at least three months to discover a spending pattern.")
        return

    try:
        result = fit_spending_clusters(frame)
    except ValueError as error:
        st.info("There is not enough varied monthly activity to compare spending patterns yet.")
        try:
            monthly = preprocess_transactions(frame).monthly_metrics
        except ValueError as processing_error:
            st.caption(f"Monthly features are unavailable until missing dates or amounts are repaired: {processing_error}")
            return
        if not monthly.empty:
            st.subheader("Available monthly features")
            st.dataframe(monthly, width="stretch", hide_index=True)
        return

    latest = result.assignments.iloc[-1]
    profile_col, position_col, drift_col = st.columns([1.25, 1, 1])
    with profile_col:
        st.markdown("**Current spending profile**")
        st.markdown(
            f"<div style='font:700 21px Manrope,sans-serif;color:#182721;padding:8px 0;'>"
            f"{result.latest_profile}</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Latest observed month: {latest['month']:%B %Y} · pattern {result.latest_cluster + 1} of 3")
    position_col.metric("Monthly observations", f"{len(result.assignments):,}")
    drift_col.metric(
        "Pattern shift",
        f"{result.risk_drift:+.2f}" if result.risk_drift is not None else "N/A",
        help="Change in the relative monthly spending-pattern score. Positive means recent months look closer to the heavier-spending pattern; it is not a diagnosis.",
    )
    if len(result.assignments) < 6:
        st.warning("This is an exploratory profile: fewer than six monthly observations are available.")

    st.subheader("Your month-by-month pattern")
    points = result.assignments.copy()
    points["month_label"] = points["month"].dt.strftime("%b %Y")
    figure = px.scatter(
        points,
        x="savings_ratio",
        y="discretionary_ratio",
        color="profile",
        text="month_label",
        color_discrete_map=PROFILE_COLORS,
        labels={
            "savings_ratio": "Savings ratio",
            "discretionary_ratio": "Discretionary ratio",
            "profile": "Cluster profile",
        },
    )
    figure.update_traces(textposition="top center", marker=dict(size=12, line=dict(width=1, color="#ffffff")))
    figure.add_trace(
        go.Scatter(
            x=[latest["savings_ratio"]],
            y=[latest["discretionary_ratio"]],
            mode="markers+text",
            name="Latest month",
            text=["You"],
            textposition="bottom right",
            marker=dict(symbol="star", size=19, color="#115E59", line=dict(width=1, color="#ffffff")),
        )
    )
    figure.update_layout(
        template="plotly_white",
        height=410,
        margin=dict(l=16, r=16, t=18, b=18),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, sans-serif", color="#134E4A"),
        legend=dict(font=dict(color="#134E4A")),
        xaxis=dict(tickformat=".0%", gridcolor="#E2E8F0", tickfont=dict(color="#134E4A")),
        yaxis=dict(tickformat=".0%", gridcolor="#E2E8F0", tickfont=dict(color="#134E4A")),
    )
    st.plotly_chart(figure, width="stretch", theme=None, config={"displayModeBar": False})

    st.subheader("What each pattern looks like")
    characteristics = result.cluster_characteristics.rename(
        columns={
            "cluster": "Pattern",
            "profile": "Consumer type",
            "transaction_frequency": "Transactions per month",
            "average_transaction_amount": "Typical purchase amount",
            "savings_ratio": "Share of income left over",
            "discretionary_ratio": "Optional spending share",
            "spending_variance": "Day-to-day spending variation",
            "monthly_burn_rate": "Recent monthly spending pace",
        }
    )
    st.dataframe(characteristics, width="stretch", hide_index=True)

    st.subheader("Month-by-month details")
    profile_table = result.assignments[
        ["month", "profile", "transaction_frequency", "average_transaction_amount", "savings_ratio", "discretionary_ratio", "spending_variance", "monthly_burn_rate"]
    ].copy().rename(
        columns={
            "month": "Month",
            "profile": "Consumer type",
            "transaction_frequency": "Transactions",
            "average_transaction_amount": "Typical purchase amount",
            "savings_ratio": "Share of income left over",
            "discretionary_ratio": "Optional spending share",
            "spending_variance": "Day-to-day spending variation",
            "monthly_burn_rate": "Recent monthly spending pace",
        }
    )
    st.dataframe(profile_table, width="stretch", hide_index=True)

    with st.expander("How to read your spending type"):
        st.write("The label compares your monthly transaction count, usual purchase size, amount saved, optional spending, changes in daily costs, and recent spending pace.")
        st.write("Heavy, Balanced, and Light are relative descriptions of this account's recorded history, not personal judgments or financial-risk diagnoses.")
