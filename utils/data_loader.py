"""Canonical local transaction store and CSV import helpers."""

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pandas as pd


DEFAULT_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "transactions.csv"
TRANSACTION_COLUMNS = ["transaction_id", "date", "type", "category", "amount", "description"]
UPLOAD_COLUMNS = {"date", "type", "category", "amount", "description"}

INCOME_CATEGORIES = ["Salary", "Freelance", "Investment", "Gift", "Loan", "Debt Repaid"]
EXPENSE_CATEGORIES = ["Housing", "Food", "Transportation", "Entertainment", "Health", "Education"]
CATEGORIES_BY_TYPE = {"income": INCOME_CATEGORIES, "expense": EXPENSE_CATEGORIES}

_CATEGORY_ALIASES = {
    "groceries": "Food",
    "dining": "Food",
    "utilities": "Housing",
    "household": "Housing",
    "subscriptions": "Entertainment",
    "healthcare": "Health",
    **{category.casefold(): category for category in INCOME_CATEGORIES + EXPENSE_CATEGORIES},
}


def normalize_transactions(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate transactions and return the common in-memory schema."""
    missing_columns = UPLOAD_COLUMNS.difference(frame.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required columns: {missing}")

    normalized = frame.copy()
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    normalized["type"] = (
        normalized["type"].astype("string").str.strip().str.lower().replace("", pd.NA)
    )
    normalized["amount"] = pd.to_numeric(normalized["amount"], errors="coerce")
    normalized["category"] = (
        normalized["category"].astype("string").str.strip().replace("", pd.NA)
    )
    normalized["description"] = (
        normalized["description"].astype("string").str.strip().replace("", pd.NA)
    )

    if normalized.empty:
        normalized["transaction_id"] = pd.Series(dtype="string")
        return normalized.reindex(columns=TRANSACTION_COLUMNS)

    if normalized["amount"].dropna().le(0).any():
        raise ValueError("Transaction amounts must be greater than zero.")

    invalid_types = set(normalized["type"].dropna().unique()).difference(CATEGORIES_BY_TYPE)
    if invalid_types:
        raise ValueError("Transaction type must be either 'income' or 'expense'.")

    normalized["category"] = normalized["category"].map(
        lambda value: pd.NA if pd.isna(value) else _CATEGORY_ALIASES.get(value.casefold(), value)
    )
    valid_categories = {
        category for categories in CATEGORIES_BY_TYPE.values() for category in categories
    }
    invalid_categories = [
        (transaction_type, category)
        for transaction_type, category in zip(normalized["type"], normalized["category"])
        if pd.notna(category)
        and (
            category not in valid_categories
            or (
                pd.notna(transaction_type)
                and category not in CATEGORIES_BY_TYPE[transaction_type]
            )
        )
    ]
    if invalid_categories:
        transaction_type, category = invalid_categories[0]
        options = ", ".join(CATEGORIES_BY_TYPE[transaction_type])
        raise ValueError(f"'{category}' is not a valid {transaction_type} category. Choose from: {options}.")

    if "transaction_id" not in normalized.columns:
        normalized["transaction_id"] = pd.Series(pd.NA, index=normalized.index, dtype="string")
    else:
        normalized["transaction_id"] = (
            normalized["transaction_id"].astype("string").str.strip().replace("", pd.NA)
        )

    for row_position, row_index in enumerate(normalized.index):
        if pd.isna(normalized.at[row_index, "transaction_id"]):
            normalized.at[row_index, "transaction_id"] = f"legacy-{row_position:08d}"
    normalized["transaction_id"] = normalized["transaction_id"].astype("string")
    if normalized["transaction_id"].duplicated().any():
        raise ValueError("Transaction IDs must be unique.")

    return (
        normalized.reindex(columns=TRANSACTION_COLUMNS)
        .sort_values(["date", "transaction_id"])
        .reset_index(drop=True)
    )


def load_transactions(path: str | Path = DEFAULT_DATA_PATH) -> pd.DataFrame:
    """Read the single local CSV store and normalize legacy rows if needed."""
    source = Path(path)
    if not source.is_file():
        raise OSError(f"File not found: {source}")
    return normalize_transactions(pd.read_csv(source))


def save_transactions(frame: pd.DataFrame, path: str | Path = DEFAULT_DATA_PATH) -> None:
    """Validate and atomically persist the shared transaction dataset."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_transactions(frame)
    temporary = target.with_suffix(target.suffix + ".tmp")
    normalized.to_csv(temporary, index=False, date_format="%Y-%m-%d")
    temporary.replace(target)


def add_transaction(transaction: dict, path: str | Path = DEFAULT_DATA_PATH) -> str:
    _validate_complete_transaction(transaction)
    current = load_transactions(path)
    new_row = dict(transaction, transaction_id=str(uuid4()))
    updated = normalize_transactions(pd.concat([current, pd.DataFrame([new_row])], ignore_index=True))
    save_transactions(updated, path)
    return new_row["transaction_id"]


def update_transaction(
    transaction_id: str,
    transaction: dict,
    path: str | Path = DEFAULT_DATA_PATH,
) -> None:
    _validate_complete_transaction(transaction)
    current = load_transactions(path)
    matches = current["transaction_id"] == transaction_id
    if not matches.any():
        raise KeyError(f"Transaction not found: {transaction_id}")
    for column in UPLOAD_COLUMNS:
        value = pd.Timestamp(transaction[column]) if column == "date" else transaction[column]
        current.loc[matches, column] = value
    save_transactions(current, path)


def delete_transaction(transaction_id: str, path: str | Path = DEFAULT_DATA_PATH) -> None:
    current = load_transactions(path)
    updated = current.loc[current["transaction_id"] != transaction_id]
    if len(updated) == len(current):
        raise KeyError(f"Transaction not found: {transaction_id}")
    save_transactions(updated, path)


def import_transactions(
    csv_content: bytes,
    path: str | Path = DEFAULT_DATA_PATH,
) -> int:
    """Append a five-column CSV upload to the shared store and return row count."""
    uploaded = pd.read_csv(BytesIO(csv_content))
    missing_columns = UPLOAD_COLUMNS.difference(uploaded.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"CSV is missing required columns: {missing}")

    uploaded = uploaded.drop(columns=["transaction_id"], errors="ignore")
    uploaded["transaction_id"] = [str(uuid4()) for _ in range(len(uploaded))]
    current = load_transactions(path)
    combined = pd.concat([current, uploaded], ignore_index=True)
    normalized = normalize_transactions(combined)
    save_transactions(normalized, path)
    return len(uploaded)


def _validate_complete_transaction(transaction: dict) -> None:
    missing_values = [
        column
        for column in UPLOAD_COLUMNS
        if column not in transaction
        or pd.isna(transaction[column])
        or (isinstance(transaction[column], str) and not transaction[column].strip())
    ]
    if missing_values:
        missing = ", ".join(sorted(missing_values))
        raise ValueError(f"Transaction fields cannot be empty: {missing}.")
