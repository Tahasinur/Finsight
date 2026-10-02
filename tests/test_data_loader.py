"""Unit tests for transaction CSV loading, normalization, CRUD, and atomic writes."""

import pandas as pd
import pytest
from utils.data_loader import (
    TRANSACTION_COLUMNS,
    add_transaction,
    delete_transaction,
    import_transactions,
    load_transactions,
    normalize_transactions,
    save_transactions,
    update_transaction,
)


@pytest.fixture
def valid_df():
    return pd.DataFrame(
        [
            {
                "date": "2026-09-01",
                "type": "income",
                "category": "Salary",
                "amount": 5000.0,
                "description": "Monthly pay",
            },
            {
                "date": "2026-09-05",
                "type": "expense",
                "category": "Food",
                "amount": 85.50,
                "description": "Supermarket",
            },
        ]
    )


@pytest.fixture
def ledger_file(tmp_path, valid_df):
    csv_path = tmp_path / "test_transactions.csv"
    save_transactions(valid_df, csv_path)
    return csv_path


def test_normalize_transactions_schema_and_id_generation(valid_df):
    """Normalize adds transaction_id and returns standard columns."""
    normalized = normalize_transactions(valid_df)

    assert list(normalized.columns) == TRANSACTION_COLUMNS
    assert len(normalized) == 2
    assert normalized["transaction_id"].notna().all()
    assert normalized["transaction_id"].nunique() == 2


def test_category_alias_normalization():
    """Verify common aliases like 'groceries' or 'dining' map to 'Food'."""
    raw = pd.DataFrame(
        [
            {
                "date": "2026-09-02",
                "type": "expense",
                "category": "groceries",
                "amount": 50.0,
                "description": "Weekly grocery",
            },
            {
                "date": "2026-09-03",
                "type": "expense",
                "category": "utilities",
                "amount": 120.0,
                "description": "Power bill",
            },
        ]
    )
    normalized = normalize_transactions(raw)

    assert normalized.loc[0, "category"] == "Food"
    assert normalized.loc[1, "category"] == "Housing"


def test_reject_negative_or_zero_amounts():
    """Amounts must be strictly positive."""
    bad_df = pd.DataFrame(
        [
            {
                "date": "2026-09-01",
                "type": "expense",
                "category": "Food",
                "amount": -20.0,
                "description": "Negative refund",
            }
        ]
    )
    with pytest.raises(ValueError, match="Transaction amounts must be greater than zero."):
        normalize_transactions(bad_df)


def test_reject_invalid_type_or_mismatched_category():
    """Type must be income or expense; category must belong to the specified type."""
    bad_type = pd.DataFrame(
        [
            {
                "date": "2026-09-01",
                "type": "transfer",
                "category": "Salary",
                "amount": 100.0,
                "description": "Bad type",
            }
        ]
    )
    with pytest.raises(ValueError, match="Transaction type must be either 'income' or 'expense'."):
        normalize_transactions(bad_type)

    mismatched = pd.DataFrame(
        [
            {
                "date": "2026-09-01",
                "type": "expense",
                "category": "Salary",  # Salary is income, not expense
                "amount": 100.0,
                "description": "Mismatched",
            }
        ]
    )
    with pytest.raises(ValueError, match="not a valid expense category"):
        normalize_transactions(mismatched)


def test_missing_required_columns():
    """Dataframe lacking required columns raises ValueError."""
    bad_columns = pd.DataFrame([{"date": "2026-09-01", "amount": 100.0}])
    with pytest.raises(ValueError, match="Missing required columns"):
        normalize_transactions(bad_columns)


def test_atomic_persistence_and_load(ledger_file):
    """Saving and loading transactions roundtrips all fields faithfully."""
    loaded = load_transactions(ledger_file)
    assert len(loaded) == 2
    assert loaded.loc[0, "type"] == "income"
    assert loaded.loc[0, "amount"] == 5000.0


def test_crud_add_update_delete(ledger_file):
    """Test add_transaction, update_transaction, and delete_transaction operations."""
    new_id = add_transaction(
        {
            "date": "2026-09-10",
            "type": "expense",
            "category": "Transportation",
            "amount": 45.0,
            "description": "Subway pass",
        },
        path=ledger_file,
    )
    current = load_transactions(ledger_file)
    assert len(current) == 3
    assert new_id in current["transaction_id"].values

    # Update
    update_transaction(
        new_id,
        {
            "date": "2026-09-10",
            "type": "expense",
            "category": "Transportation",
            "amount": 55.0,
            "description": "Metro card reload",
        },
        path=ledger_file,
    )
    updated = load_transactions(ledger_file)
    updated_row = updated.loc[updated["transaction_id"] == new_id].iloc[0]
    assert updated_row["amount"] == 55.0
    assert updated_row["description"] == "Metro card reload"

    # Delete
    delete_transaction(new_id, path=ledger_file)
    after_delete = load_transactions(ledger_file)
    assert len(after_delete) == 2
    assert new_id not in after_delete["transaction_id"].values


def test_import_csv_appends_records(ledger_file):
    """Importing raw 5-column CSV bytes appends records and generates IDs."""
    csv_bytes = b"date,type,category,amount,description\n2026-09-12,expense,Health,120.00,Doctor visit\n"
    count = import_transactions(csv_bytes, path=ledger_file)
    assert count == 1

    current = load_transactions(ledger_file)
    assert len(current) == 3
    assert "Doctor visit" in current["description"].values


def test_flexible_csv_mapping_auto_polarity():
    """Test mapping custom bank export columns with auto polarity (+/- amount)."""
    from pages.transactions import _build_mapped_transactions

    raw_bank_data = pd.DataFrame(
        [
            {"TransDate": "2026-08-01", "TransactionDetail": "ACME Corp Paycheck", "NetValue": "3200.50"},
            {"TransDate": "2026-08-03", "TransactionDetail": "Whole Foods Market", "NetValue": "-85.20"},
        ]
    )
    mapped = _build_mapped_transactions(
        raw_bank_data,
        date_col="TransDate",
        amount_col="NetValue",
        type_col="(Auto: positive = Income, negative = Expense)",
        category_col="(Infer from Description)",
        desc_col="TransactionDetail",
    )
    assert len(mapped) == 2
    assert mapped.loc[0, "type"] == "income"
    assert mapped.loc[0, "category"] == "Salary"
    assert mapped.loc[0, "amount"] == 3200.50

    assert mapped.loc[1, "type"] == "expense"
    assert mapped.loc[1, "category"] == "Food"
    assert mapped.loc[1, "amount"] == 85.20


def test_flexible_csv_mapping_category_inference():
    """Test category inference across multiple common transaction descriptions."""
    from pages.transactions import _infer_category

    assert _infer_category("Monthly Apartment Rent", "expense") == "Housing"
    assert _infer_category("Trader Joe's Groceries", "expense") == "Food"
    assert _infer_category("Chevron Gas Station", "expense") == "Transportation"
    assert _infer_category("CVS Pharmacy Prescription", "expense") == "Health"
    assert _infer_category("Coursera Annual Subscription", "expense") == "Education"
    assert _infer_category("Netflix Monthly", "expense") == "Entertainment"
    assert _infer_category("Client Wire Payment Upwork", "income") == "Freelance"
    assert _infer_category("Vanguard Dividend Distribution", "income") == "Investment"


@pytest.fixture
def sqlite_ledger(tmp_path, valid_df):
    db_file = tmp_path / "test_store.sqlite3"
    from utils.auth import initialize_auth_store
    initialize_auth_store(db_file)
    save_transactions(valid_df, db_file)
    return db_file


def test_sqlite_transaction_crud(sqlite_ledger):
    """Test load, add, update, delete, and import operations directly on SQLite transactions store."""
    loaded = load_transactions(sqlite_ledger)
    assert len(loaded) == 2
    assert list(loaded.columns) == TRANSACTION_COLUMNS
    # Verify date descending sort
    assert loaded.iloc[0]["date"] >= loaded.iloc[1]["date"]

    # Add transaction
    new_id = add_transaction(
        {
            "date": "2026-09-15",
            "type": "expense",
            "category": "Entertainment",
            "amount": 35.0,
            "description": "Cinema tickets",
        },
        path=sqlite_ledger,
    )
    current = load_transactions(sqlite_ledger)
    assert len(current) == 3
    assert new_id in current["transaction_id"].values
    assert current.iloc[0]["transaction_id"] == new_id  # 2026-09-15 is latest date

    # Update transaction
    update_transaction(
        new_id,
        {
            "date": "2026-09-15",
            "type": "expense",
            "category": "Entertainment",
            "amount": 42.50,
            "description": "IMAX tickets",
        },
        path=sqlite_ledger,
    )
    updated = load_transactions(sqlite_ledger)
    updated_row = updated.loc[updated["transaction_id"] == new_id].iloc[0]
    assert updated_row["amount"] == 42.50
    assert updated_row["description"] == "IMAX tickets"

    # Delete transaction
    delete_transaction(new_id, path=sqlite_ledger)
    after_del = load_transactions(sqlite_ledger)
    assert len(after_del) == 2
    assert new_id not in after_del["transaction_id"].values

    # Import transactions
    csv_bytes = b"date,type,category,amount,description\n2026-09-20,income,Freelance,750.00,Website design\n"
    imported_count = import_transactions(csv_bytes, path=sqlite_ledger)
    assert imported_count == 1
    after_import = load_transactions(sqlite_ledger)
    assert len(after_import) == 3
    assert "Website design" in after_import["description"].values


def test_csv_migration(tmp_path):
    """Test automated migration from legacy per-user CSV files into SQLite transactions table."""
    from utils.auth import initialize_auth_store, migrate_existing_csv_ledgers, register_user
    from uuid import uuid4

    test_db = tmp_path / "migration_test.sqlite3"
    initialize_auth_store(test_db)
    user = register_user("migrate@example.com", "Migrate User", "Password12345!", db_path=test_db)
    user_id = user["user_id"]

    # Create user folder and CSV ledger
    user_folder = tmp_path / "user_data" / user_id
    user_folder.mkdir(parents=True, exist_ok=True)
    csv_path = user_folder / "transactions.csv"
    csv_path.write_text(
        "transaction_id,date,type,category,amount,description\n"
        "t1,2026-08-01,income,Salary,4000.0,Paycheck\n"
        "t2,2026-08-05,expense,Food,65.0,Dinner\n",
        encoding="utf-8",
    )

    # Run migration
    migrated_count = migrate_existing_csv_ledgers(test_db)
    assert migrated_count == 2

    # Check database contains migrated rows
    loaded = load_transactions(user_id=user_id, db_path=test_db)
    assert len(loaded) == 2
    assert "Paycheck" in loaded["description"].values
    assert "Dinner" in loaded["description"].values

    # Check original CSV renamed to .migrated
    assert not csv_path.exists()
    assert (user_folder / "transactions.csv.migrated").exists()

    # Re-running migration is idempotent
    second_run = migrate_existing_csv_ledgers(test_db)
    assert second_run == 0


