"""Canonical local transaction store and CSV import helpers."""

from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd


AUTH_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "finwise_users.sqlite3"
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


def _resolve_target(
    path: str | Path = DEFAULT_DATA_PATH,
    user_id: str | None = None,
    db_path: str | Path = AUTH_DB_PATH,
) -> tuple[str | None, Path | None, Path | None]:
    """
    Determine whether the target is an SQLite transactions store or a standalone CSV file.
    Returns (user_id, db_path, csv_path).
    """
    path_obj = Path(path)
    if path_obj.suffix in {".sqlite3", ".db"}:
        return str(user_id) if user_id else None, path_obj, None

    if user_id:
        return str(user_id), Path(db_path), None

    path_str = str(path)
    try:
        uuid_str = str(UUID(path_str))
        return uuid_str, Path(db_path), None
    except (ValueError, TypeError):
        pass

    try:
        parent_uuid = str(UUID(path_obj.parent.name))
        return parent_uuid, Path(db_path), None
    except (ValueError, TypeError):
        pass

    return None, None, path_obj


def normalize_transactions(
    frame: pd.DataFrame,
    custom_categories: list[str] | dict[str, list[str]] | None = None,
) -> pd.DataFrame:
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
    category_map = {k: list(v) for k, v in CATEGORIES_BY_TYPE.items()}
    if custom_categories:
        if isinstance(custom_categories, dict):
            for t_key, cat_list in custom_categories.items():
                low_k = t_key.lower()
                if low_k in category_map:
                    category_map[low_k].extend(cat_list)
                valid_categories.update(cat_list)
        elif isinstance(custom_categories, list):
            valid_categories.update(custom_categories)
            category_map["income"].extend(custom_categories)
            category_map["expense"].extend(custom_categories)

    invalid_categories = [
        (transaction_type, category)
        for transaction_type, category in zip(normalized["type"], normalized["category"])
        if pd.notna(category)
        and (
            category not in valid_categories
            or (
                pd.notna(transaction_type)
                and category not in category_map.get(transaction_type, [])
            )
        )
    ]
    if invalid_categories:
        transaction_type, category = invalid_categories[0]
        options = ", ".join(category_map.get(transaction_type, []))
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


def load_transactions(
    path: str | Path = DEFAULT_DATA_PATH,
    user_id: str | None = None,
    db_path: str | Path = AUTH_DB_PATH,
) -> pd.DataFrame:
    """Read transactions from SQLite user store or standalone CSV file."""
    target_user, target_db, csv_path = _resolve_target(path, user_id, db_path)
    if target_db is not None:
        from utils.auth import _connect, initialize_auth_store

        initialize_auth_store(target_db)
        with _connect(target_db) as connection:
            if target_user:
                rows = connection.execute(
                    "SELECT transaction_id, date, type, category, amount, description "
                    "FROM transactions WHERE user_id = ? ORDER BY date DESC, transaction_id DESC",
                    (target_user,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT transaction_id, date, type, category, amount, description "
                    "FROM transactions ORDER BY date DESC, transaction_id DESC"
                ).fetchall()
        if not rows:
            empty = pd.DataFrame(columns=TRANSACTION_COLUMNS)
            empty["date"] = pd.to_datetime(empty["date"])
            return empty.reindex(columns=TRANSACTION_COLUMNS)

        df = pd.DataFrame([dict(r) for r in rows])
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["type"] = df["type"].astype("string").str.strip().str.lower()
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        df["transaction_id"] = df["transaction_id"].astype("string")
        df["category"] = df["category"].astype("string")
        df["description"] = df["description"].astype("string").fillna("")
        return (
            df.reindex(columns=TRANSACTION_COLUMNS)
            .sort_values(["date", "transaction_id"], ascending=[False, False])
            .reset_index(drop=True)
        )

    # Standalone CSV file
    if not csv_path.is_file():
        raise OSError(f"File not found: {csv_path}")
    loaded = normalize_transactions(pd.read_csv(csv_path))
    return loaded


def save_transactions(
    frame: pd.DataFrame,
    path: str | Path = DEFAULT_DATA_PATH,
    user_id: str | None = None,
    db_path: str | Path = AUTH_DB_PATH,
) -> None:
    """Validate and atomically persist the transaction dataset to SQLite or CSV."""
    target_user, target_db, csv_path = _resolve_target(path, user_id, db_path)
    normalized = normalize_transactions(frame)

    if target_db is not None:
        from utils.auth import _connect, initialize_auth_store

        initialize_auth_store(target_db)
        with _connect(target_db) as connection:
            if target_user is None:
                user_row = connection.execute("SELECT user_id FROM users LIMIT 1").fetchone()
                target_user = user_row["user_id"] if user_row else "default-user"
                connection.execute(
                    "INSERT OR IGNORE INTO users (user_id, email, display_name, password_salt, password_hash) "
                    "VALUES (?, 'test@finwise.local', 'Test User', X'00', X'00')",
                    (target_user,),
                )
            connection.execute("DELETE FROM transactions WHERE user_id = ?", (target_user,))
            for _, row in normalized.iterrows():
                t_date = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])
                connection.execute(
                    """
                    INSERT INTO transactions (transaction_id, user_id, date, type, category, amount, description, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        str(row["transaction_id"]),
                        target_user,
                        t_date,
                        str(row["type"]).lower(),
                        str(row["category"]),
                        float(row["amount"]),
                        str(row["description"]) if pd.notna(row["description"]) else "",
                    ),
                )
        return

    target = Path(csv_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    normalized.to_csv(temporary, index=False, date_format="%Y-%m-%d")
    temporary.replace(target)


def add_transaction(
    transaction: dict,
    path: str | Path = DEFAULT_DATA_PATH,
    user_id: str | None = None,
    db_path: str | Path = AUTH_DB_PATH,
) -> str:
    _validate_complete_transaction(transaction)
    target_user, target_db, csv_path = _resolve_target(path, user_id, db_path)
    new_id = str(uuid4())
    t_date = transaction["date"].strftime("%Y-%m-%d") if hasattr(transaction["date"], "strftime") else str(transaction["date"])
    t_type = str(transaction["type"]).strip().lower()
    t_cat = str(transaction["category"]).strip()
    t_amount = float(transaction["amount"])
    t_desc = str(transaction.get("description", "")).strip()

    if target_db is not None:
        from utils.auth import _connect, initialize_auth_store

        initialize_auth_store(target_db)
        with _connect(target_db) as connection:
            if target_user is None:
                user_row = connection.execute("SELECT user_id FROM users LIMIT 1").fetchone()
                target_user = user_row["user_id"] if user_row else "default-user"
                connection.execute(
                    "INSERT OR IGNORE INTO users (user_id, email, display_name, password_salt, password_hash) "
                    "VALUES (?, 'test@finwise.local', 'Test User', X'00', X'00')",
                    (target_user,),
                )
            connection.execute(
                """
                INSERT INTO transactions (transaction_id, user_id, date, type, category, amount, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (new_id, target_user, t_date, t_type, t_cat, t_amount, t_desc),
            )
        return new_id

    current = load_transactions(csv_path)
    new_row = dict(transaction, transaction_id=new_id)
    updated = normalize_transactions(pd.concat([current, pd.DataFrame([new_row])], ignore_index=True))
    save_transactions(updated, csv_path)
    return new_id


def update_transaction(
    transaction_id: str,
    transaction: dict,
    path: str | Path = DEFAULT_DATA_PATH,
    user_id: str | None = None,
    db_path: str | Path = AUTH_DB_PATH,
) -> None:
    _validate_complete_transaction(transaction)
    target_user, target_db, csv_path = _resolve_target(path, user_id, db_path)
    t_date = transaction["date"].strftime("%Y-%m-%d") if hasattr(transaction["date"], "strftime") else str(transaction["date"])
    t_type = str(transaction["type"]).strip().lower()
    t_cat = str(transaction["category"]).strip()
    t_amount = float(transaction["amount"])
    t_desc = str(transaction.get("description", "")).strip()

    if target_db is not None:
        from utils.auth import _connect, initialize_auth_store

        initialize_auth_store(target_db)
        with _connect(target_db) as connection:
            if target_user:
                cursor = connection.execute(
                    """
                    UPDATE transactions
                    SET date = ?, type = ?, category = ?, amount = ?, description = ?
                    WHERE transaction_id = ? AND user_id = ?
                    """,
                    (t_date, t_type, t_cat, t_amount, t_desc, transaction_id, target_user),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE transactions
                    SET date = ?, type = ?, category = ?, amount = ?, description = ?
                    WHERE transaction_id = ?
                    """,
                    (t_date, t_type, t_cat, t_amount, t_desc, transaction_id),
                )
            if cursor.rowcount == 0:
                raise KeyError(f"Transaction not found: {transaction_id}")
        return

    current = load_transactions(csv_path)
    matches = current["transaction_id"] == transaction_id
    if not matches.any():
        raise KeyError(f"Transaction not found: {transaction_id}")
    for column in UPLOAD_COLUMNS:
        value = pd.Timestamp(transaction[column]) if column == "date" else transaction[column]
        current.loc[matches, column] = value
    save_transactions(current, csv_path)


def delete_transaction(
    transaction_id: str,
    path: str | Path = DEFAULT_DATA_PATH,
    user_id: str | None = None,
    db_path: str | Path = AUTH_DB_PATH,
) -> None:
    target_user, target_db, csv_path = _resolve_target(path, user_id, db_path)
    if target_db is not None:
        from utils.auth import _connect, initialize_auth_store

        initialize_auth_store(target_db)
        with _connect(target_db) as connection:
            if target_user:
                cursor = connection.execute(
                    "DELETE FROM transactions WHERE transaction_id = ? AND user_id = ?",
                    (transaction_id, target_user),
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM transactions WHERE transaction_id = ?",
                    (transaction_id,),
                )
            if cursor.rowcount == 0:
                raise KeyError(f"Transaction not found: {transaction_id}")
        return

    current = load_transactions(csv_path)
    updated = current.loc[current["transaction_id"] != transaction_id]
    if len(updated) == len(current):
        raise KeyError(f"Transaction not found: {transaction_id}")
    save_transactions(updated, csv_path)


def import_transactions(
    csv_content: bytes,
    path: str | Path = DEFAULT_DATA_PATH,
    user_id: str | None = None,
    db_path: str | Path = AUTH_DB_PATH,
) -> int:
    """Append a CSV upload to the SQLite or CSV store and return row count."""
    uploaded = pd.read_csv(BytesIO(csv_content))
    missing_columns = UPLOAD_COLUMNS.difference(uploaded.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"CSV is missing required columns: {missing}")

    target_user, target_db, csv_path = _resolve_target(path, user_id, db_path)
    uploaded = uploaded.drop(columns=["transaction_id"], errors="ignore")
    uploaded["transaction_id"] = [str(uuid4()) for _ in range(len(uploaded))]
    normalized = normalize_transactions(uploaded)

    if target_db is not None:
        from utils.auth import _connect, initialize_auth_store

        initialize_auth_store(target_db)
        with _connect(target_db) as connection:
            if target_user is None:
                user_row = connection.execute("SELECT user_id FROM users LIMIT 1").fetchone()
                target_user = user_row["user_id"] if user_row else "default-user"
                connection.execute(
                    "INSERT OR IGNORE INTO users (user_id, email, display_name, password_salt, password_hash) "
                    "VALUES (?, 'test@finwise.local', 'Test User', X'00', X'00')",
                    (target_user,),
                )
            for _, row in normalized.iterrows():
                t_date = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])
                connection.execute(
                    """
                    INSERT INTO transactions (transaction_id, user_id, date, type, category, amount, description, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        str(row["transaction_id"]),
                        target_user,
                        t_date,
                        str(row["type"]).lower(),
                        str(row["category"]),
                        float(row["amount"]),
                        str(row["description"]) if pd.notna(row["description"]) else "",
                    ),
                )
        return len(uploaded)

    current = load_transactions(csv_path)
    combined = pd.concat([current, uploaded], ignore_index=True)
    normalized = normalize_transactions(combined)
    save_transactions(normalized, csv_path)
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
