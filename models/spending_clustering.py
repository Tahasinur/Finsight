"""K-Means behavioral clustering over monthly financial features."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler
import streamlit as st

from models.preprocessing import preprocess_transactions


CLUSTER_FEATURES = [
	"transaction_frequency",
	"average_transaction_amount",
	"savings_ratio",
	"discretionary_ratio",
	"spending_variance",
	"monthly_burn_rate",
]
PROFILE_NAMES = [
	"Light Consumer",
	"Balanced Consumer",
	"Heavy Consumer",
]
MINIMUM_MONTHS = 3


@dataclass
class SpendingClusteringResult:
	monthly_features: pd.DataFrame
	scaled_features: pd.DataFrame
	assignments: pd.DataFrame
	cluster_characteristics: pd.DataFrame
	latest_profile: str
	latest_cluster: int
	risk_drift: float | None
	model: KMeans
	pipeline: Pipeline
	profile_order: list[str]


@st.cache_data(show_spinner=False)
def fit_spending_clusters(
	frame: pd.DataFrame,
	fingerprint: str | None = None,
) -> SpendingClusteringResult:
	"""Fit three K-Means clusters using engineered monthly spending features."""
	processed = preprocess_transactions(frame)
	monthly_features = processed.monthly_metrics[["month", *CLUSTER_FEATURES]].copy()
	monthly_features = monthly_features.sort_values("month").reset_index(drop=True)

	if len(monthly_features) < MINIMUM_MONTHS:
		raise ValueError(
			f"At least {MINIMUM_MONTHS} distinct transaction months are needed; "
			f"the ledger contains {len(monthly_features)}."
		)

	source_features = monthly_features[CLUSTER_FEATURES]
	imputed = source_features.fillna(source_features.median()).fillna(0.0)
	if len(np.unique(imputed.to_numpy(), axis=0)) < 3:
		raise ValueError("At least three distinct monthly feature profiles are needed to fit K-Means.")

	model = KMeans(n_clusters=3, random_state=42, n_init=20)
	pipeline = Pipeline(
		steps=[
			("imputer", SimpleImputer(strategy="median")),
			("scaler", MinMaxScaler()),
			("kmeans", model),
		]
	)
	labels = pipeline.fit_predict(source_features)
	scaled = pipeline.named_steps["scaler"].transform(
		pipeline.named_steps["imputer"].transform(source_features)
	)
	scaled_features = pd.DataFrame(scaled, columns=CLUSTER_FEATURES)

	if len(np.unique(labels)) != 3:
		raise ValueError("The monthly data did not form three distinct K-Means clusters.")

	consumer_scores = _rank_cluster_centers(model.cluster_centers_, CLUSTER_FEATURES)
	ordered_clusters = sorted(consumer_scores, key=consumer_scores.get)
	profile_by_cluster = dict(zip(ordered_clusters, PROFILE_NAMES))
	consumer_score_by_cluster = {cluster: consumer_scores[cluster] for cluster in consumer_scores}

	assignments = monthly_features.copy()
	assignments["cluster"] = labels
	assignments["profile"] = assignments["cluster"].map(profile_by_cluster)
	assignments["consumer_score"] = assignments["cluster"].map(consumer_score_by_cluster)

	characteristics = (
		assignments.groupby(["cluster", "profile"], as_index=False)[CLUSTER_FEATURES]
		.mean()
		.sort_values("cluster")
	)
	latest = assignments.iloc[-1]
	risk_drift = (
		float(latest["consumer_score"] - assignments.iloc[0]["consumer_score"])
		if len(assignments) >= MINIMUM_MONTHS
		else None
	)

	return SpendingClusteringResult(
		monthly_features=monthly_features,
		scaled_features=scaled_features,
		assignments=assignments,
		cluster_characteristics=characteristics,
		latest_profile=str(latest["profile"]),
		latest_cluster=int(latest["cluster"]),
		risk_drift=risk_drift,
		model=model,
		pipeline=pipeline,
		profile_order=PROFILE_NAMES.copy(),
	)


def _rank_cluster_centers(centers: np.ndarray, feature_names: list[str]) -> dict[int, float]:
	"""Order normalized K-Means centers by observed monthly consumption intensity."""
	center_frame = pd.DataFrame(centers, columns=feature_names)
	scores = (
		0.17 * center_frame["transaction_frequency"]
		+ 0.15 * center_frame["average_transaction_amount"]
		+ 0.20 * (1 - center_frame["savings_ratio"])
		+ 0.16 * center_frame["discretionary_ratio"]
		+ 0.16 * center_frame["spending_variance"]
		+ 0.16 * center_frame["monthly_burn_rate"]
	)
	return {int(cluster): float(score) for cluster, score in scores.items()}
