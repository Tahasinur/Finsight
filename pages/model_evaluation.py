"""Evaluation views for classifiers, clustering, CSP, and A* runs."""

import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.metrics import silhouette_score

from models.purchase_classifier import CLASS_NAMES, train_purchase_models
from models.spending_clustering import fit_spending_clusters
from utils.calculations import transaction_fingerprint


@st.cache_resource(show_spinner="Evaluating purchase demo models...")
def _purchase_models():
    return train_purchase_models()


def render(frame: pd.DataFrame) -> None:
    st.title("How Accurate Are the Tools?")
    st.caption("Inspect the methods, test results, and limits behind the analysis tools.")
    signature = transaction_fingerprint(frame)

    st.header("Logistic Regression and KNN")
    purchase_models = _purchase_models()
    st.warning("These classifier metrics use synthetic/demo labels and do not measure real-world financial accuracy.")
    st.caption(
        f"Holdout: {purchase_models.test_rows:,} rows from the deterministic synthetic dataset; "
        "precision, recall, and F1 are macro-averaged."
    )
    evaluation_table = pd.DataFrame(
        [
            {
                "Model": name,
                "Accuracy": metrics.accuracy,
                "Precision (macro)": metrics.precision,
                "Recall (macro)": metrics.recall,
                "F1 (macro)": metrics.f1,
            }
            for name, metrics in purchase_models.evaluation.items()
        ]
    )
    st.dataframe(evaluation_table, width="stretch", hide_index=True)
    with st.expander("View Confusion Matrices & Model Breakdown", expanded=False):
        confusion_columns = st.columns(2)
        for column, model_name in zip(confusion_columns, purchase_models.evaluation):
            with column:
                metrics = purchase_models.evaluation[model_name]
                st.markdown(f"**{model_name} · confusion matrix**")
                matrix = pd.DataFrame(metrics.confusion_matrix, index=CLASS_NAMES, columns=CLASS_NAMES)
                matrix.index.name = "Actual"
                st.dataframe(matrix, width="stretch")

    st.header("K-Means spending clusters")
    try:
        clustering = fit_spending_clusters(frame, fingerprint=signature) if not frame.empty else None
    except ValueError as error:
        clustering = None
        st.warning(f"Insufficient data for reliable evaluation. {error}")
    if clustering is not None:
        metrics_col, silhouette_col, points_col = st.columns(3)
        metrics_col.metric("Inertia", f"{clustering.model.inertia_:.3f}")
        if len(clustering.assignments) >= 6 and clustering.assignments["cluster"].nunique() > 1:
            silhouette = silhouette_score(clustering.scaled_features, clustering.assignments["cluster"])
            silhouette_col.metric("Silhouette score", f"{silhouette:.3f}")
        elif len(clustering.assignments) > clustering.assignments["cluster"].nunique() > 1:
            silhouette = silhouette_score(clustering.scaled_features, clustering.assignments["cluster"])
            silhouette_col.metric("Silhouette score · exploratory", f"{silhouette:.3f}")
            st.info("Insufficient data for reliable evaluation. Fewer than six monthly observations are available.")
        else:
            silhouette_col.metric("Silhouette score", "N/A")
            st.info("Insufficient data for reliable evaluation.")
        points_col.metric("Monthly observations", f"{len(clustering.assignments):,}")

        st.markdown("**Cluster distribution**")
        distribution = (
            clustering.assignments.groupby(["cluster", "profile"], as_index=False)
            .size()
            .rename(columns={"size": "Monthly observations"})
        )
        st.dataframe(distribution, width="stretch", hide_index=True)

        points = clustering.assignments.copy()
        points["month_label"] = points["month"].dt.strftime("%b %Y")
        figure = px.scatter(
            points,
            x="savings_ratio",
            y="discretionary_ratio",
            color="profile",
            text="month_label",
            labels={"savings_ratio": "Savings ratio", "discretionary_ratio": "Discretionary ratio"},
            color_discrete_map={"Heavy Consumer": "#F87171", "Balanced Consumer": "#F59E0B", "Light Consumer": "#10B981"},
        )
        figure.update_layout(
            template="plotly_white",
            height=350,
            margin=dict(l=12, r=12, t=12, b=12),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="DM Sans, sans-serif", color="#134E4A"),
            xaxis=dict(tickformat=".0%", gridcolor="#E2E8F0"),
            yaxis=dict(tickformat=".0%", gridcolor="#E2E8F0"),
        )
        with st.expander("View Cluster Visualization Scatter Plot", expanded=True):
            st.plotly_chart(figure, width="stretch", theme=None, config={"displayModeBar": False})
    else:
        st.info("Insufficient data for reliable evaluation.")

    st.header("Constraint Satisfaction Problem")
    budget_run = st.session_state.get("budget_optimizer_run")
    if budget_run is None or budget_run.get("transaction_fingerprint") != signature:
        st.info("Insufficient data for reliable evaluation. Run Budget Optimizer with the current ledger first.")
    else:
        budget = budget_run["result"]
        csp_cols = st.columns(4)
        csp_cols[0].metric("Hard constraints", f"{len(budget.constraints)}")
        csp_cols[1].metric("Feasible", "Yes" if budget.feasible else "No")
        csp_cols[2].metric("Search nodes", f"{budget.statistics.nodes_explored:,}")
        csp_cols[3].metric("Solution found", "Yes" if budget.feasible else "No")
        st.write(f"Search status: {budget.status}")
        st.caption(
            f"Forward-check prunes: {budget.statistics.forward_check_prunes:,} · "
            f"Backtracks: {budget.statistics.backtracks:,} · "
            f"Feasible solutions: {budget.statistics.feasible_solutions:,}"
        )

    st.header("A* goal planning")
    goal_run = st.session_state.get("goal_planner_run")
    if goal_run is None or goal_run.get("transaction_fingerprint") != signature:
        st.info("Insufficient data for reliable evaluation. Run Goal Planner with a goal first.")
    else:
        goal = goal_run["result"]
        astar_cols = st.columns(4)
        astar_cols[0].metric("States explored", f"{goal.nodes_explored:,}")
        astar_cols[1].metric("Path length", f"{goal.path_length}")
        astar_cols[2].metric("Final cost", f"{goal.final_cost:.2f}" if goal.final_cost is not None else "N/A")
        astar_cols[3].metric("Solution found", "Yes" if goal.feasible else "No")
        if goal.selected_path:
            heuristic_values = pd.DataFrame(
                [
                    {"Month": state["month"], "g(n)": state["g"], "h(n)": state["h"], "f(n)": state["f"]}
                    for state in goal.selected_path
                ]
            )
            st.dataframe(heuristic_values, width="stretch", hide_index=True)

    st.header("Rule engine")
    rule_run = st.session_state.get("rule_advisor_run")
    if rule_run is None or rule_run.get("transaction_fingerprint") != signature:
        st.info("Run Rule-Based Advisor to evaluate configured reserve and debt rules against the current ledger.")
    else:
        rule_results = pd.DataFrame(rule_run["rules"])
        st.metric("Rules evaluated", f"{len(rule_results):,}")
        st.metric("Rules triggered", f"{int(rule_results['result'].eq('Triggered').sum()):,}")
        st.dataframe(rule_results[["rule_id", "condition", "result", "priority"]], width="stretch", hide_index=True)