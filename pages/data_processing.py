"""Visualize the reusable transaction preprocessing pipeline."""

import pandas as pd
import streamlit as st

from models.preprocessing import preprocess_transactions
from utils.calculations import format_currency


def render(frame: pd.DataFrame) -> None:
    st.title("Clean My Data")
    st.caption("Check missing values and see how your transactions become ready for analysis.")

    try:
        result = preprocess_transactions(frame)
    except ValueError as error:
        st.error(f"Preprocessing could not continue: {error}")
        return

    stages = [
        "YOUR TRANSACTIONS",
        "Fill missing details",
        "Label categories",
        "Align number scales",
        "Add monthly context",
        "READY TO EXPLORE",
    ]
    flow_items = []
    for position, stage in enumerate(stages):
        if position:
            flow_items.append('<span style="color:#718078;font-size:18px;">→</span>')
        color = "#174f3c" if position in {0, len(stages) - 1} else "#526158"
        flow_items.append(
            f'<span style="flex:0 0 auto;color:{color};font-weight:700;font-size:13px;">{stage}</span>'
        )
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;overflow-x:auto;white-space:nowrap;'
        'padding:10px 0;">' + "".join(flow_items) + "</div>",
        unsafe_allow_html=True,
    )

    st.divider()
    missing_count = int(result.missing_values.sum())
    encoded_count = result.encoded_features.shape[1]
    normalized_count = result.normalized_features.shape[1]
    model_feature_count = result.model_features.shape[1]
    missing_col, encoded_col, normalized_col, feature_col = st.columns(4)
    missing_col.metric("Missing values detected", f"{missing_count:,}")
    encoded_col.metric("Category labels prepared", f"{encoded_count:,}")
    normalized_col.metric("Number fields aligned", f"{normalized_count:,}")
    feature_col.metric("Details ready for analysis", f"{model_feature_count:,}")

    if missing_count:
        st.info("Missing transaction values are imputed for processing only; the shared ledger is unchanged.")
    elif not frame.empty:
        st.success("No missing values were found in the current transaction ledger.")

    st.subheader("Before and after")
    raw_col, cleaned_col = st.columns(2, gap="large")
    with raw_col:
        st.markdown("**Raw transactions**")
        st.dataframe(_display_frame(result.raw_data), width="stretch", hide_index=True)
    with cleaned_col:
        st.markdown("**After missing-value handling**")
        st.dataframe(_display_frame(result.cleaned_data), width="stretch", hide_index=True)

    st.subheader("Transaction and category labels")
    if result.encoded_features.empty:
        st.info("Encoded feature rows will appear when transactions are available.")
    else:
        st.dataframe(result.encoded_features, width="stretch", hide_index=True)

    st.subheader("Numbers aligned to a common scale")
    if result.normalized_features.empty:
        st.info("Normalized feature rows will appear when transactions are available.")
    else:
        st.dataframe(result.normalized_features, width="stretch", hide_index=True)

    st.subheader("Monthly money snapshot")
    if result.monthly_metrics.empty:
        st.info("Add transactions to calculate monthly financial metrics.")
        return

    latest = result.monthly_metrics.iloc[-1]
    savings_ratio = latest["savings_ratio"]
    discretionary_ratio = latest["discretionary_ratio"]
    savings_value = f"{savings_ratio:.1%}" if pd.notna(savings_ratio) else "N/A"
    discretionary_value = (
        f"{discretionary_ratio:.1%}" if pd.notna(discretionary_ratio) else "N/A"
    )
    savings_col, burn_col, discretionary_col = st.columns(3)
    savings_col.metric("Share of income left over", savings_value, help="Monthly income less monthly expenses, divided by monthly income.")
    burn_col.metric("Recent monthly spending pace", format_currency(latest["monthly_burn_rate"]), help="Average spending across the last seven calendar days, extended to a 30-day estimate.")
    discretionary_col.metric("Optional spending share", discretionary_value, help="Optional expenses divided by all recorded expenses.")
    st.caption(f"Latest transaction month: {latest['month']:%B %Y}")
    st.dataframe(result.monthly_metrics, width="stretch", hide_index=True)

    with st.expander("Prepared analysis details"):
        if result.model_features.empty:
            st.info("Model-ready feature rows will appear when transactions are available.")
        else:
            st.dataframe(result.model_features, width="stretch", hide_index=True)
        st.caption("These prepared details can be reused by the analysis tools.")


def _display_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.drop(columns=["transaction_id"], errors="ignore")
