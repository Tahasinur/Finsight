"""Unit tests verifying performance optimizations, caching signatures, pagination, and batch SQL."""

from pathlib import Path
import pandas as pd
import pytest

from models.purchase_classifier import train_purchase_models
from models.spending_clustering import fit_spending_clusters
from utils.auth import (
    authenticate_user,
    get_admin_system_stats,
    initialize_auth_store,
    list_user_summaries,
    register_user,
)
from utils.calculations import (
    get_financial_summary,
    monthly_cash_flow,
    monthly_financial_metrics,
    spending_by_category,
    transaction_fingerprint,
)
from utils.data_loader import DEFAULT_DATA_PATH, load_transactions, save_transactions


@pytest.fixture
def auth_db(tmp_path: Path):
    db_file = tmp_path / "test_perf.sqlite3"
    initialize_auth_store(db_file)
    return db_file


def test_transaction_fingerprint_deterministic_and_sensitive():
    df1 = pd.DataFrame(
        [
            {"transaction_id": "tx-1", "date": "2026-09-01", "type": "income", "category": "Salary", "amount": 1000.0, "description": "Pay"},
            {"transaction_id": "tx-2", "date": "2026-09-02", "type": "expense", "category": "Food", "amount": 50.0, "description": "Lunch"},
        ]
    )
    df2 = pd.DataFrame(
        [
            {"transaction_id": "tx-2", "date": "2026-09-02", "type": "expense", "category": "Food", "amount": 50.0, "description": "Lunch"},
            {"transaction_id": "tx-1", "date": "2026-09-01", "type": "income", "category": "Salary", "amount": 1000.0, "description": "Pay"},
        ]
    )
    df3 = pd.DataFrame(
        [
            {"transaction_id": "tx-1", "date": "2026-09-01", "type": "income", "category": "Salary", "amount": 1000.0, "description": "Pay"},
            {"transaction_id": "tx-2", "date": "2026-09-02", "type": "expense", "category": "Food", "amount": 55.0, "description": "Lunch"},
        ]
    )
    fp1 = transaction_fingerprint(df1)
    fp2 = transaction_fingerprint(df2)
    fp3 = transaction_fingerprint(df3)

    assert fp1 == fp2, "Stable sort ensures row reordering yields identical fingerprint"
    assert fp1 != fp3, "Altered transaction amount changes fingerprint"


def test_data_loader_pagination_sqlite_and_csv(auth_db):
    user = register_user("paginated@example.com", "SecretPass123!", "Paginated User", db_path=auth_db)
    records = []
    for i in range(10):
        records.append(
            {
                "date": f"2026-08-{i+1:02d}",
                "type": "expense",
                "category": "Food",
                "amount": 10.0 + i,
                "description": f"Meal {i+1}",
            }
        )
    df = pd.DataFrame(records)
    save_transactions(df, user_id=user["user_id"], db_path=auth_db)

    # Full load
    all_rows = load_transactions(user_id=user["user_id"], db_path=auth_db)
    assert len(all_rows) == 10

    # Paginated load: page 1 of size 3
    page1 = load_transactions(user_id=user["user_id"], db_path=auth_db, limit=3, offset=0)
    assert len(page1) == 3

    # Paginated load: page 2 of size 3
    page2 = load_transactions(user_id=user["user_id"], db_path=auth_db, limit=3, offset=3)
    assert len(page2) == 3
    assert set(page1["transaction_id"]).isdisjoint(set(page2["transaction_id"]))

    # CSV pagination
    csv_page = load_transactions(DEFAULT_DATA_PATH, limit=5, offset=0)
    assert len(csv_page) == 5


def test_batch_sql_user_summaries_and_stats(auth_db, monkeypatch):
    monkeypatch.setenv("FINWISE_ADMIN_EMAIL", "admin@example.com")
    admin = register_user("admin@example.com", "Admin", "AdminPass123!", db_path=auth_db)
    user1 = register_user("user1@example.com", "User 1", "UserPass123!", db_path=auth_db)
    user2 = register_user("user2@example.com", "User 2", "UserPass123!", db_path=auth_db)

    # Add transactions for user1
    txs = pd.DataFrame(
        [
            {"date": "2026-08-01", "type": "income", "category": "Salary", "amount": 3000.0, "description": "Pay"},
            {"date": "2026-08-02", "type": "expense", "category": "Food", "amount": 100.0, "description": "Groceries"},
        ]
    )
    save_transactions(txs, user_id=user1["user_id"], db_path=auth_db)

    summaries = list_user_summaries(admin["user_id"], db_path=auth_db)
    assert len(summaries) == 3
    summary_by_email = {s["email"]: s for s in summaries}

    assert summary_by_email["user1@example.com"]["transaction_count"] == 2
    assert summary_by_email["user1@example.com"]["total_volume"] == 3100.0
    assert summary_by_email["user2@example.com"]["transaction_count"] == 0

    stats = get_admin_system_stats(admin["user_id"], db_path=auth_db)
    assert stats["user_count"] == 3
    assert stats["admin_count"] == 1
    assert stats["transaction_row_count"] == 2


def test_deterministic_calculation_functions_with_fingerprint():
    demo_df = load_transactions(DEFAULT_DATA_PATH)
    sig = transaction_fingerprint(demo_df)

    summary = get_financial_summary(demo_df, initial_balance=500.0, fingerprint=sig)
    assert summary["income"] > 0
    assert summary["expenses"] > 0

    flow = monthly_cash_flow(demo_df, fingerprint=sig)
    assert not flow.empty
    assert "net_cash_flow" in flow.columns

    metrics = monthly_financial_metrics(demo_df, fingerprint=sig)
    assert not metrics.empty
    assert "monthly_burn_rate" in metrics.columns

    by_cat = spending_by_category(demo_df, fingerprint=sig)
    assert not by_cat.empty
    assert "amount" in by_cat.columns


def test_spending_clustering_cache_with_fingerprint():
    demo_df = load_transactions(DEFAULT_DATA_PATH)
    sig = transaction_fingerprint(demo_df)
    result = fit_spending_clusters(demo_df, fingerprint=sig)
    assert result.latest_profile in ["Light Consumer", "Balanced Consumer", "Heavy Consumer"]
    assert len(result.assignments) >= 3


def test_model_singleton_training_cached():
    models1 = train_purchase_models(sample_count=100, random_seed=42)
    models2 = train_purchase_models(sample_count=100, random_seed=42)
    assert models1 is models2, "train_purchase_models returns singleton instance when cached"
