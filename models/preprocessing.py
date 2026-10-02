"""Reusable transaction preprocessing and financial feature engineering."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder

from utils.calculations import MONTHLY_METRIC_COLUMNS, monthly_financial_metrics


CATEGORICAL_FEATURES = ["type", "category"]
NUMERICAL_FEATURES = [
	"amount",
	"signed_amount",
	"day_of_month",
	"day_of_week",
	"is_weekend",
	"savings_ratio",
	"monthly_burn_rate",
	"discretionary_ratio",
	"transaction_frequency",
	"average_transaction_amount",
	"spending_variance",
]
BASE_TRANSACTION_COLUMNS = ["date", "type", "category", "amount", "description"]


@dataclass
class ProcessingResult:
	raw_data: pd.DataFrame
	cleaned_data: pd.DataFrame
	engineered_data: pd.DataFrame
	encoded_features: pd.DataFrame
	normalized_features: pd.DataFrame
	model_features: pd.DataFrame
	missing_values: pd.Series
	monthly_metrics: pd.DataFrame
	pipeline: Pipeline


def build_preprocessing_pipeline() -> Pipeline:
	"""Build an unfitted imputation, encoding, and MinMax scaling pipeline."""
	categorical_pipeline = Pipeline(
		steps=[
			("imputer", SimpleImputer(strategy="constant", fill_value="Unknown")),
			("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
		]
	)
	numerical_pipeline = Pipeline(
		steps=[
			("imputer", SimpleImputer(strategy="median")),
			("scaler", MinMaxScaler()),
		]
	)
	features = ColumnTransformer(
		transformers=[
			("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
			("numerical", numerical_pipeline, NUMERICAL_FEATURES),
		],
		verbose_feature_names_out=False,
	)
	return Pipeline(steps=[("features", features)])


def preprocess_transactions(frame: pd.DataFrame) -> ProcessingResult:
	"""Clean, engineer, encode, and normalize transaction features."""
	missing_columns = set(BASE_TRANSACTION_COLUMNS).difference(frame.columns)
	if missing_columns:
		missing = ", ".join(sorted(missing_columns))
		raise ValueError(f"Missing required transaction columns: {missing}")

	raw = frame.copy()
	missing_values = raw[BASE_TRANSACTION_COLUMNS].isna().sum().astype(int)
	cleaned = raw.copy()

	cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce")
	if cleaned["date"].notna().any():
		median_date = cleaned["date"].dropna().median()
		cleaned["date"] = cleaned["date"].fillna(median_date)
	elif not cleaned.empty:
		raise ValueError("Cannot extract date features because every transaction date is missing.")

	cleaned["amount"] = pd.to_numeric(cleaned["amount"], errors="coerce")
	if cleaned["amount"].notna().any():
		median_amount = cleaned["amount"].median()
		cleaned["amount"] = cleaned["amount"].fillna(median_amount)
	elif not cleaned.empty:
		raise ValueError("Cannot calculate financial metrics because every transaction amount is missing.")

	for column in ["type", "category"]:
		cleaned[column] = (
			cleaned[column]
			.astype("string")
			.str.strip()
			.replace("", pd.NA)
			.fillna("Unknown")
			.astype(str)
		)
	cleaned["description"] = (
		cleaned["description"]
		.astype("string")
		.str.strip()
		.replace("", pd.NA)
		.fillna("No description")
	)

	financial_data = raw[BASE_TRANSACTION_COLUMNS].copy()
	financial_data["date"] = pd.to_datetime(financial_data["date"], errors="coerce")
	financial_data["type"] = (
		financial_data["type"].astype("string").str.strip().str.lower()
	)
	financial_data["category"] = financial_data["category"].astype("string").str.strip()
	financial_data["amount"] = pd.to_numeric(financial_data["amount"], errors="coerce")
	monthly_metrics = monthly_financial_metrics(financial_data)
	if cleaned.empty:
		engineered = pd.DataFrame(columns=CATEGORICAL_FEATURES + NUMERICAL_FEATURES)
		encoded = pd.DataFrame()
		normalized = pd.DataFrame(columns=NUMERICAL_FEATURES)
		model_features = pd.DataFrame()
		pipeline = build_preprocessing_pipeline()
	else:
		dates = cleaned["date"]
		months = dates.dt.to_period("M").dt.to_timestamp()
		metric_lookup = monthly_metrics.set_index("month")
		engineered = pd.DataFrame(index=cleaned.index)
		engineered["type"] = cleaned["type"]
		engineered["category"] = cleaned["category"]
		engineered["amount"] = cleaned["amount"].astype(float)
		engineered["signed_amount"] = np.select(
			[cleaned["type"].eq("income"), cleaned["type"].eq("expense")],
			[cleaned["amount"], -cleaned["amount"]],
			default=np.nan,
		)
		engineered["day_of_month"] = dates.dt.day.astype(float)
		engineered["day_of_week"] = dates.dt.dayofweek.astype(float)
		engineered["is_weekend"] = dates.dt.dayofweek.ge(5).astype(float)
		for metric in MONTHLY_METRIC_COLUMNS[1:]:
			engineered[metric] = months.map(metric_lookup[metric])

		encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
		encoded_values = encoder.fit_transform(engineered[CATEGORICAL_FEATURES])
		encoded = pd.DataFrame(
			encoded_values,
			index=engineered.index,
			columns=encoder.get_feature_names_out(CATEGORICAL_FEATURES),
		)

		scaler = MinMaxScaler()
		normalized_values = scaler.fit_transform(engineered[NUMERICAL_FEATURES])
		normalized = pd.DataFrame(
			normalized_values,
			index=engineered.index,
			columns=NUMERICAL_FEATURES,
		)

		pipeline = build_preprocessing_pipeline()
		model_values = pipeline.fit_transform(engineered)
		feature_names = pipeline.named_steps["features"].get_feature_names_out()
		model_features = pd.DataFrame(model_values, index=engineered.index, columns=feature_names)

	return ProcessingResult(
		raw_data=raw,
		cleaned_data=cleaned,
		engineered_data=engineered,
		encoded_features=encoded,
		normalized_features=normalized,
		model_features=model_features,
		missing_values=missing_values,
		monthly_metrics=monthly_metrics,
		pipeline=pipeline,
	)
