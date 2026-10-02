"""Synthetic-demo Logistic Regression and KNN purchase classifiers."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
	accuracy_score,
	confusion_matrix,
	f1_score,
	precision_score,
	recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from models.purchase_features import (
	CATEGORY_IMPACT_WEIGHTS,
	PURCHASE_FEATURE_COLUMNS,
	PurchaseContext,
	feature_frame,
)


CLASS_NAMES = ["Strong Yes", "Cautious Yes", "Better Wait", "No"]
RISK_LEVELS = {
	"Strong Yes": "Low",
	"Cautious Yes": "Moderate",
	"Better Wait": "Elevated",
	"No": "High",
}
SYNTHETIC_SAMPLE_COUNT = 6000
SYNTHETIC_DATASET_PATH = Path(__file__).resolve().parents[1] / "data" / "synthetic_purchase_training.csv"


@dataclass
class ClassifierEvaluation:
	accuracy: float
	precision: float
	recall: float
	f1: float
	confusion_matrix: np.ndarray


@dataclass
class TrainedPurchaseModels:
	logistic_regression: Pipeline
	knn: Pipeline
	evaluation: dict[str, ClassifierEvaluation]
	training_rows: int
	test_rows: int
	demo_training_data: pd.DataFrame
	labels: pd.Series


def generate_synthetic_training_data(
	sample_count: int = SYNTHETIC_SAMPLE_COUNT,
	random_seed: int = 42,
) -> tuple[pd.DataFrame, pd.Series]:
	"""Generate realistic synthetic cases; their outcomes are illustrative labels, not observed behavior."""
	if sample_count < 80:
		raise ValueError("At least 80 synthetic examples are needed for a stratified evaluation split.")

	random = np.random.default_rng(random_seed)
	balance_ratio = np.clip(random.lognormal(-1.85, 0.95, sample_count), 0.01, 4.0)
	income_ratio = np.clip(random.lognormal(-2.7, 0.9, sample_count), 0.005, 2.5)
	expense_ratio = np.clip(random.normal(0.73, 0.30, sample_count), 0.12, 1.8)
	savings_rate = np.clip(1 - expense_ratio + random.normal(0, 0.15, sample_count), -0.65, 0.75)
	discretionary_share = random.beta(2.1, 8.5, sample_count)
	days_left = random.integers(0, 32, sample_count)
	urgency = random.integers(1, 6, sample_count)
	category_weight = random.choice(
		np.array(list(CATEGORY_IMPACT_WEIGHTS.values())),
		size=sample_count,
	)
	goal_days = random.integers(7, 731, sample_count)
	no_goal = random.random(sample_count) < 0.18
	goal_days = np.where(no_goal, 3650, goal_days)
	goal_gap = np.where(no_goal, 0.0, random.beta(2.2, 4.5, sample_count))
	behavior_score = 0.52 * expense_ratio + 0.72 * discretionary_share - 0.48 * savings_rate
	heavy = behavior_score > 0.62
	light = behavior_score < 0.20
	balanced = ~(heavy | light)

	demo_data = pd.DataFrame(
		{
			"item_cost_balance_ratio": balance_ratio,
			"item_cost_monthly_income_ratio": income_ratio,
			"days_left_in_month": days_left.astype(float),
			"goal_urgency": urgency.astype(float),
			"category_impact_weight": category_weight,
			"monthly_expense_ratio": expense_ratio,
			"savings_rate": savings_rate,
			"discretionary_spending_share": discretionary_share,
			"nearest_goal_days_left": goal_days.astype(float),
			"goal_gap_ratio": goal_gap,
			"consumer_heavy_flag": heavy.astype(float),
			"consumer_light_flag": light.astype(float),
			"consumer_balanced_flag": balanced.astype(float),
		},
		columns=PURCHASE_FEATURE_COLUMNS,
	)

	goal_pressure = goal_gap * np.exp(-goal_days / 240)
	risk_score = (
		2.0 * balance_ratio
		+ 1.35 * income_ratio
		+ 0.48 * expense_ratio
		+ 0.90 * discretionary_share
		- 0.82 * savings_rate
		+ 0.30 * (31 - days_left) / 31
		+ 0.055 * (urgency - 1)
		+ 0.20 * category_weight
		+ 0.62 * goal_pressure
		+ 0.34 * heavy
		- 0.15 * light
		+ random.normal(0, 0.18, sample_count)
	)
	labels = pd.Series(
		np.select(
			[risk_score < 0.48, risk_score < 0.98, risk_score < 1.72],
			["Strong Yes", "Cautious Yes", "Better Wait"],
			default="No",
		),
		name="verdict",
	)
	return demo_data, labels


def load_or_create_synthetic_dataset(
	path: str | Path = SYNTHETIC_DATASET_PATH,
	sample_count: int = SYNTHETIC_SAMPLE_COUNT,
	random_seed: int = 42,
) -> tuple[pd.DataFrame, pd.Series]:
	"""Load the labeled demo CSV or persist a deterministic synthetic training set."""
	dataset_path = Path(path)
	if dataset_path.is_file():
		stored = pd.read_csv(dataset_path)
		if set(PURCHASE_FEATURE_COLUMNS + ["verdict"]).issubset(stored.columns):
			features = stored[PURCHASE_FEATURE_COLUMNS].astype(float)
			labels = stored["verdict"].astype(str)
			if labels.isin(CLASS_NAMES).all() and labels.nunique() == len(CLASS_NAMES):
				return features, labels

	features, labels = generate_synthetic_training_data(sample_count, random_seed)
	dataset_path.parent.mkdir(parents=True, exist_ok=True)
	stored = features.copy()
	stored["verdict"] = labels
	stored["dataset_source"] = "synthetic_demo"
	stored.to_csv(dataset_path, index=False)
	return features, labels


def train_purchase_models(
	sample_count: int = SYNTHETIC_SAMPLE_COUNT,
	random_seed: int = 42,
) -> TrainedPurchaseModels:
	if sample_count == SYNTHETIC_SAMPLE_COUNT and random_seed == 42:
		demo_data, labels = load_or_create_synthetic_dataset()
	else:
		demo_data, labels = generate_synthetic_training_data(sample_count, random_seed)
	if labels.value_counts().reindex(CLASS_NAMES, fill_value=0).min() < 2:
		raise ValueError("Synthetic dataset needs at least two samples for every purchase verdict.")

	train_features, test_features, train_labels, test_labels = train_test_split(
		demo_data,
		labels,
		test_size=0.25,
		random_state=random_seed,
		stratify=labels,
	)
	logistic = Pipeline(
		steps=[
			("scaler", StandardScaler()),
			("classifier", LogisticRegression(max_iter=1800, class_weight="balanced", random_state=random_seed)),
		]
	)
	logistic.fit(train_features, train_labels)
	knn = Pipeline(
		steps=[
			("scaler", StandardScaler()),
			("classifier", KNeighborsClassifier(n_neighbors=min(11, len(train_features)), weights="distance")),
		]
	)
	knn.fit(train_features, train_labels)
	evaluation = {
		"Logistic Regression · Primary": _evaluate_classifier(logistic, test_features, test_labels),
		"K-Nearest Neighbors · Comparison": _evaluate_classifier(knn, test_features, test_labels),
	}
	return TrainedPurchaseModels(
		logistic_regression=logistic,
		knn=knn,
		evaluation=evaluation,
		training_rows=len(train_features),
		test_rows=len(test_features),
		demo_training_data=demo_data,
		labels=labels,
	)


def predict_purchase(
	models: TrainedPurchaseModels,
	item_cost: float,
	current_balance: float,
	days_left_in_month: int,
	goal_urgency: int,
	category: str = "Other",
	monthly_income: float = 0.0,
	monthly_expenses: float = 0.0,
	savings_rate: float = 0.0,
	discretionary_spending_share: float = 0.0,
	nearest_goal_days_left: int = 3650,
	goal_gap_ratio: float = 0.0,
	consumer_type: str = "Unknown",
) -> dict:
	context = PurchaseContext(
		item_cost=item_cost,
		current_balance=current_balance,
		monthly_income=monthly_income,
		monthly_expenses=monthly_expenses,
		savings_rate=savings_rate,
		discretionary_spending_share=discretionary_spending_share,
		days_left_in_month=days_left_in_month,
		goal_urgency=goal_urgency,
		category=category,
		nearest_goal_days_left=nearest_goal_days_left,
		goal_gap_ratio=goal_gap_ratio,
		consumer_type=consumer_type,
	)
	features = feature_frame(context)
	primary = _predict_with_probabilities(models.logistic_regression, features)
	comparison = _predict_with_probabilities(models.knn, features)
	confidence = primary["probabilities"][primary["predicted_class"]]
	return {
		"features": features.iloc[0].to_dict(),
		"logistic_regression": primary,
		"knn": comparison,
		"verdict": primary["predicted_class"],
		"risk_level": RISK_LEVELS[primary["predicted_class"]],
		"confidence": confidence,
	}


def simulate_goal_impact(
	price: float,
	goal_target: float,
	goal_current_savings: float,
	goal_days_left: int,
	monthly_savings_capacity: float,
) -> dict:
	"""Compare a goal plan with and without the purchase under an explicit assumption."""
	if price <= 0 or goal_target <= 0 or goal_current_savings < 0 or goal_days_left <= 0:
		raise ValueError("Purchase price, goal target, and deadline must be positive; savings cannot be negative.")
	months_left = max(1, int(np.ceil(goal_days_left / 30)))
	remaining = max(0.0, goal_target - goal_current_savings)
	if monthly_savings_capacity <= 0:
		return {
			"available": True,
			"baseline_months": None,
			"after_purchase_months": None,
			"extra_months": None,
			"extra_monthly_savings": price / months_left,
			"months_to_deadline": months_left,
		}
	baseline_months = int(np.ceil(remaining / monthly_savings_capacity))
	after_purchase_months = int(np.ceil((remaining + price) / monthly_savings_capacity))
	return {
		"available": True,
		"baseline_months": baseline_months,
		"after_purchase_months": after_purchase_months,
		"extra_months": max(0, after_purchase_months - baseline_months),
		"extra_monthly_savings": price / months_left,
		"months_to_deadline": months_left,
	}


def _predict_with_probabilities(model: Pipeline, features: pd.DataFrame) -> dict:
	probabilities = model.predict_proba(features)[0]
	probability_by_class = {
		str(class_name): float(probability)
		for class_name, probability in zip(model.classes_, probabilities)
	}
	predicted = str(model.predict(features)[0])
	return {"predicted_class": predicted, "probabilities": probability_by_class}


def _evaluate_classifier(model: Pipeline, features: pd.DataFrame, labels: pd.Series) -> ClassifierEvaluation:
	predictions = model.predict(features)
	return ClassifierEvaluation(
		accuracy=float(accuracy_score(labels, predictions)),
		precision=float(precision_score(labels, predictions, labels=CLASS_NAMES, average="macro", zero_division=0)),
		recall=float(recall_score(labels, predictions, labels=CLASS_NAMES, average="macro", zero_division=0)),
		f1=float(f1_score(labels, predictions, labels=CLASS_NAMES, average="macro", zero_division=0)),
		confusion_matrix=confusion_matrix(labels, predictions, labels=CLASS_NAMES),
	)
