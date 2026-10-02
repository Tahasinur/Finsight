"""Unit tests for SQLite authentication, PBKDF2 hashing, and isolated user stores."""

import hmac
import os
import sqlite3
import pytest
from utils.auth import (
    _connect,
    _hash_password,
    add_custom_category,
    authenticate_user,
    change_user_password,
    check_login_lockout,
    clear_login_attempts,
    clear_user_financial_data,
    deactivate_user_goal,
    delete_custom_category,
    export_user_data,
    get_user_by_id,
    get_user_categories,
    get_user_goals,
    get_user_preferences,
    get_user_thresholds,
    initialize_auth_store,
    record_login_failure,
    register_user,
    save_user_goal,
    save_user_preferences,
    save_user_thresholds,
)


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_users.sqlite3"
    initialize_auth_store(db_file)
    return db_file


def test_pbkdf2_hashing_and_timing_safe_comparison():
    """Verify PBKDF2 creates 32-byte hashes and hmac.compare_digest operates correctly."""
    salt = b"\x01" * 16
    hash1 = _hash_password("SuperSecret123!", salt)
    hash2 = _hash_password("SuperSecret123!", salt)
    hash3 = _hash_password("DifferentPassword123!", salt)

    assert len(hash1) == 32
    assert hmac.compare_digest(hash1, hash2) is True
    assert hmac.compare_digest(hash1, hash3) is False


def test_user_registration_and_authentication(test_db):
    """Register a user, verify record in database, and authenticate."""
    email = "jane.doe@example.com"
    name = "Jane Doe"
    password = "StrongPassword456!"

    user = register_user(email, name, password, db_path=test_db)
    assert user["email"] == email
    assert user["display_name"] == name
    assert user["role"] == "user"
    assert user["user_id"] is not None

    # Authenticate with correct credentials
    auth_user = authenticate_user(email, password, db_path=test_db)
    assert auth_user is not None
    assert auth_user["user_id"] == user["user_id"]

    # Authenticate with wrong password
    bad_auth = authenticate_user(email, "WrongPassword!", db_path=test_db)
    assert bad_auth is None

    # Authenticate nonexistent email
    no_auth = authenticate_user("nonexistent@example.com", password, db_path=test_db)
    assert no_auth is None


def test_duplicate_email_rejected(test_db):
    """Attempting to register with an existing email raises ValueError."""
    email = "duplicate@example.com"
    register_user(email, "First User", "Password12345!", db_path=test_db)

    with pytest.raises(ValueError, match="An account with that email already exists."):
        register_user(email, "Second User", "AnotherPassword123!", db_path=test_db)

    # Case-insensitive duplicate check
    with pytest.raises(ValueError, match="An account with that email already exists."):
        register_user(email.upper(), "Third User", "AnotherPassword123!", db_path=test_db)


def test_admin_bootstrapping_via_env(test_db, monkeypatch):
    """When FINWISE_ADMIN_EMAIL matches, registered user gets role='admin'."""
    admin_email = "boss@example.com"
    monkeypatch.setenv("FINWISE_ADMIN_EMAIL", admin_email)

    admin_user = register_user(admin_email, "Admin Boss", "AdminPassword123!", db_path=test_db)
    assert admin_user["role"] == "admin"


def test_password_change_flow(test_db):
    """Test updating user password with current password verification."""
    user = register_user("pwdtest@example.com", "Pwd User", "OldPassword123!", db_path=test_db)

    # Wrong current password fails
    with pytest.raises(ValueError, match="Current password did not match this account."):
        change_user_password(user["user_id"], "IncorrectOld!", "NewPassword123!", db_path=test_db)

    # Correct current password succeeds
    change_user_password(user["user_id"], "OldPassword123!", "NewPassword123!", db_path=test_db)

    # Can now login with new password
    assert authenticate_user("pwdtest@example.com", "NewPassword123!", db_path=test_db) is not None
    assert authenticate_user("pwdtest@example.com", "OldPassword123!", db_path=test_db) is None


def test_user_goals_crud_and_cascading(test_db):
    """Test creating, fetching, deactivating goals, and verifying foreign key cascade."""
    user = register_user("goals@example.com", "Goal Tracker", "Password12345!", db_path=test_db)
    user_id = user["user_id"]

    # Save a goal
    goal = save_user_goal(
        user_id=user_id,
        goal_name="Emergency Fund",
        target_amount=5000.0,
        current_savings=1000.0,
        monthly_saving_limit=400.0,
        deadline_date="2027-01-01",
        db_path=test_db,
    )
    assert goal["goal_name"] == "Emergency Fund"
    assert goal["target_amount"] == 5000.0
    assert goal["active"] == 1

    # Fetch goals
    goals = get_user_goals(user_id, db_path=test_db)
    assert len(goals) == 1
    assert goals[0]["goal_id"] == goal["goal_id"]

    # Deactivate goal
    deactivate_user_goal(user_id, goal["goal_id"], db_path=test_db)
    updated_goals = get_user_goals(user_id, db_path=test_db)
    assert updated_goals[0]["active"] == 0

    # Foreign key cascade: deleting the user deletes user_goals
    with _connect(test_db) as conn:
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        remaining_goals = conn.execute("SELECT * FROM user_goals WHERE user_id = ?", (user_id,)).fetchall()
        assert len(remaining_goals) == 0


def test_user_preferences(test_db):
    """Test saving and retrieving user preferences."""
    user = register_user("prefs@example.com", "Pref User", "Password12345!", db_path=test_db)
    user_id = user["user_id"]

    # Default preference
    prefs = get_user_preferences(user_id, db_path=test_db)
    assert prefs["dashboard_period"] == "Last 30 days"

    # Update preference
    save_user_preferences(user_id, "This month", db_path=test_db)
    updated = get_user_preferences(user_id, db_path=test_db)
    assert updated["dashboard_period"] == "This month"

    # Invalid preference option rejected
    with pytest.raises(ValueError, match="Choose a supported dashboard period."):
        save_user_preferences(user_id, "InvalidPeriod", db_path=test_db)


def test_initial_balance_preference(test_db):
    """Test saving and retrieving initial balance in preferences."""
    user = register_user("balance@example.com", "Balance User", "Password12345!", db_path=test_db)
    user_id = user["user_id"]

    # Initial balance defaults to 0.0
    prefs = get_user_preferences(user_id, db_path=test_db)
    assert prefs["initial_balance"] == 0.0

    # Save custom initial balance
    save_user_preferences(user_id, initial_balance=2500.50, db_path=test_db)
    updated = get_user_preferences(user_id, db_path=test_db)
    assert updated["initial_balance"] == 2500.50
    assert updated["dashboard_period"] == "Last 30 days"

    # Negative balance rejected
    with pytest.raises(ValueError, match="nonnegative"):
        save_user_preferences(user_id, initial_balance=-500.0, db_path=test_db)


def test_analysis_run_persistence(test_db):
    """Test saving and loading analysis runs with JSON serialization and reconstruction."""
    from utils.auth import get_latest_analysis_run, save_analysis_run

    user = register_user("runs@example.com", "Run User", "Password12345!", db_path=test_db)
    user_id = user["user_id"]

    # No runs initially
    assert get_latest_analysis_run(user_id, "budget_optimizer", db_path=test_db) is None

    # Save a run with BudgetOptimizationResult
    from models.budget_csp import BudgetOptimizationResult, SearchStatistics
    from models.goal_astar import GoalPlanResult
    from datetime import date
    from utils.auth import clear_user_financial_data

    sample_budget_result = BudgetOptimizationResult(
        feasible=True,
        optimal=True,
        status="Optimal",
        allocations={"housing": 1200.0, "food": 500.0},
        total_allocation=1700.0,
        remaining_amount=2300.0,
        discretionary_cap=800.0,
        objective_score=0.0,
        constraints={"housing_preserved": True},
        requested_targets={"housing": 1200.0, "food": 500.0},
        statistics=SearchStatistics(nodes_explored=42, forward_check_prunes=10, bound_prunes=5),
        resolution_note="",
        explanation="Feasible plan found.",
    )
    sample_payload = {
        "monthly_income": 4000.0,
        "targets": {"housing": 1200.0, "food": 500.0},
        "result": sample_budget_result,
        "transaction_fingerprint": "hash123456",
    }
    run_id = save_analysis_run(user_id, "budget_optimizer", "hash123456", sample_payload, db_path=test_db)
    assert run_id is not None

    # Retrieve and verify dataclass reconstruction
    restored = get_latest_analysis_run(user_id, "budget_optimizer", db_path=test_db)
    assert restored is not None
    assert restored["monthly_income"] == 4000.0
    assert isinstance(restored["result"], BudgetOptimizationResult)
    assert restored["result"].feasible is True
    assert isinstance(restored["result"].statistics, SearchStatistics)
    assert restored["result"].statistics.nodes_explored == 42
    assert restored["_persisted_run_id"] == run_id

    # Test GoalPlanResult reconstruction
    sample_goal_result = GoalPlanResult(
        feasible=True,
        status="Optimal",
        goal_name="Emergency Fund",
        target_amount=3000.0,
        initial_savings=500.0,
        maximum_monthly_saving=500.0,
        effective_monthly_limit=500.0,
        initial_state={"savings": 500.0, "month": "2026-10-01"},
        path_length=6,
        goal_month=date(2027, 3, 1),
        final_cost=15.5,
        nodes_explored=150,
        selected_path=[{"month": "2026-10-01", "monthly_saving": 500.0}],
        explored_states=[],
        explanation="Route found.",
    )
    goal_payload = {
        "goal_name": "Emergency Fund",
        "result": sample_goal_result,
        "transaction_fingerprint": "hash_goal",
    }
    save_analysis_run(user_id, "goal_planner", "hash_goal", goal_payload, db_path=test_db)
    restored_goal = get_latest_analysis_run(user_id, "goal_planner", db_path=test_db)
    assert restored_goal is not None
    assert isinstance(restored_goal["result"], GoalPlanResult)
    assert restored_goal["result"].goal_month == date(2027, 3, 1)

    # Test clear_user_financial_data cascades to analysis_runs
    clear_user_financial_data(user_id, db_path=test_db)
    assert get_latest_analysis_run(user_id, "budget_optimizer", db_path=test_db) is None
    assert get_latest_analysis_run(user_id, "goal_planner", db_path=test_db) is None


def test_custom_categories(test_db):
    """Test custom categories CRUD, uniqueness, defaults merging, and cascade on delete."""
    from utils.data_loader import EXPENSE_CATEGORIES, INCOME_CATEGORIES

    user = register_user("cats@example.com", "Cat User", "Password12345!", db_path=test_db)
    user_id = user["user_id"]

    # Initially defaults only
    cats = get_user_categories(user_id, db_path=test_db)
    assert cats["income"] == list(INCOME_CATEGORIES)
    assert cats["expense"] == list(EXPENSE_CATEGORIES)

    # Add custom expense and income category
    gym_id = add_custom_category(user_id, "Gym & Fitness", "Expense", db_path=test_db)
    consult_id = add_custom_category(user_id, "Consulting", "Income", db_path=test_db)
    assert gym_id is not None
    assert consult_id is not None

    updated = get_user_categories(user_id, db_path=test_db)
    assert "Gym & Fitness" in updated["expense"]
    assert "Consulting" in updated["income"]

    # Duplicate rejected (case-insensitive)
    with pytest.raises(ValueError, match="already exists"):
        add_custom_category(user_id, "gym & fitness", "Expense", db_path=test_db)

    # Empty name or invalid type rejected
    with pytest.raises(ValueError, match="between 1 and 50 characters"):
        add_custom_category(user_id, "   ", "Expense", db_path=test_db)
    with pytest.raises(ValueError, match="Category type must be Income or Expense"):
        add_custom_category(user_id, "Crypto", "OtherType", db_path=test_db)

    # Delete custom category by name
    delete_custom_category(user_id, "Gym & Fitness", db_path=test_db)
    after_del = get_user_categories(user_id, db_path=test_db)
    assert "Gym & Fitness" not in after_del["expense"]

    # Delete custom category by ID
    delete_custom_category(user_id, consult_id, db_path=test_db)
    after_del2 = get_user_categories(user_id, db_path=test_db)
    assert "Consulting" not in after_del2["income"]

    # Delete nonexistent raises KeyError
    with pytest.raises(KeyError):
        delete_custom_category(user_id, "NonexistentCategory", db_path=test_db)

    # Foreign key cascade on delete user
    add_custom_category(user_id, "TempCat", "Expense", db_path=test_db)
    with _connect(test_db) as conn:
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        remaining = conn.execute("SELECT * FROM custom_categories WHERE user_id = ?", (user_id,)).fetchall()
        assert len(remaining) == 0


def test_configurable_rule_thresholds(test_db):
    """Test retrieving, updating, and evaluating financial rules with custom thresholds."""
    from models.rule_engine import RuleThresholds, evaluate_financial_rules

    user = register_user("rules@example.com", "Rule User", "Password12345!", db_path=test_db)
    user_id = user["user_id"]

    # Default thresholds
    defaults = get_user_thresholds(user_id, db_path=test_db)
    assert isinstance(defaults, RuleThresholds)
    assert defaults.savings_low == 0.10
    assert defaults.savings_healthy == 0.20
    assert defaults.discretionary == 0.20
    assert defaults.burn_rate_income == 0.80
    assert defaults.debt_income == 0.20

    # Custom thresholds
    custom = RuleThresholds(
        savings_low=0.15,
        savings_healthy=0.30,
        discretionary=0.15,
        burn_rate_income=0.75,
        debt_income=0.15,
    )
    saved = save_user_thresholds(user_id, custom, db_path=test_db)
    assert saved.savings_low == 0.15

    retrieved = get_user_thresholds(user_id, db_path=test_db)
    assert retrieved.savings_low == 0.15
    assert retrieved.savings_healthy == 0.30
    assert retrieved.discretionary == 0.15

    # Out of range threshold rejected
    with pytest.raises(ValueError, match="between 0% and 200%"):
        save_user_thresholds(user_id, RuleThresholds(savings_low=-0.05), db_path=test_db)

    # Evaluation behaves differently with custom threshold
    metrics = {
        "income": 5000.0,
        "savings_ratio": 0.12,  # 12% savings rate
        "discretionary_ratio": 0.10,
        "monthly_burn_rate": 4400.0,
    }
    # With default threshold (savings_low = 10%), 12% is NOT < 10%, so R01 is "Not triggered"
    default_rules = evaluate_financial_rules(metrics, 1000.0, 3000.0, 0.0, thresholds=defaults)
    r01_default = next(r for r in default_rules if r.rule_id == "R01")
    assert r01_default.result == "Not triggered"
    assert "10%" in r01_default.condition

    # With tuned threshold (savings_low = 15%), 12% IS < 15%, so R01 is "Triggered"
    custom_rules = evaluate_financial_rules(metrics, 1000.0, 3000.0, 0.0, thresholds=custom)
    r01_custom = next(r for r in custom_rules if r.rule_id == "R01")
    assert r01_custom.result == "Triggered"
    assert "15%" in r01_custom.condition


def test_login_rate_limiting_lockout(test_db):
    """Test brute-force protection: 5 failed attempts trigger lockout, success clears counter."""
    user = register_user("lockout@example.com", "Lockout User", "CorrectPassword123!", db_path=test_db)
    email = user["email"]

    # Attempts 1 to 4 record failures but do not lock
    for attempt in range(1, 5):
        result = authenticate_user(email, "WrongPassword!", db_path=test_db)
        assert result is None
        is_locked, remaining = check_login_lockout(email, db_path=test_db)
        assert is_locked is False
        assert remaining == 0

    # 5th failed attempt triggers lockout
    with pytest.raises(ValueError, match="temporarily locked"):
        authenticate_user(email, "WrongPassword!", db_path=test_db)

    is_locked, remaining = check_login_lockout(email, db_path=test_db)
    assert is_locked is True
    assert remaining > 0

    # While locked, even correct credentials raise ValueError
    with pytest.raises(ValueError, match="temporarily locked"):
        authenticate_user(email, "CorrectPassword123!", db_path=test_db)

    # Clearing attempts removes lockout and allows login
    clear_login_attempts(email, db_path=test_db)
    is_locked, remaining = check_login_lockout(email, db_path=test_db)
    assert is_locked is False

    auth_success = authenticate_user(email, "CorrectPassword123!", db_path=test_db)
    assert auth_success is not None
    assert auth_success["email"] == email


def test_export_and_clear_user_data_with_sqlite_transactions(test_db):
    """Test export and clear operations cascade across transactions, categories, and preferences."""
    import io
    import zipfile
    from utils.data_loader import add_transaction, load_transactions

    user = register_user("fulluser@example.com", "Full User", "Password12345!", db_path=test_db)
    user_id = user["user_id"]

    # Add custom category
    add_custom_category(user_id, "Freelance Dev", "Income", db_path=test_db)

    # Add transaction in SQLite
    tx_id = add_transaction(
        {
            "date": "2026-09-25",
            "type": "income",
            "category": "Freelance Dev",
            "amount": 1500.0,
            "description": "App build",
        },
        path=test_db,
        user_id=user_id,
    )
    assert tx_id is not None

    # Save a goal
    save_user_goal(user_id, "Vacation", 2000.0, 500.0, 300.0, "2027-06-01", db_path=test_db)

    # Export user data
    zip_bytes = export_user_data(user_id, db_path=test_db)
    assert len(zip_bytes) > 0

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = z.namelist()
        assert "profile.json" in names
        assert "goals.csv" in names
        assert "transactions.csv" in names
        assert "preferences.json" in names
        tx_csv = z.read("transactions.csv").decode("utf-8")
        assert "App build" in tx_csv

    # Clear financial data
    clear_user_financial_data(user_id, db_path=test_db)

    # Check transactions table is empty for user
    loaded = load_transactions(user_id=user_id, db_path=test_db)
    assert len(loaded) == 0

    # Custom categories cleared
    user_cats = get_user_categories(user_id, db_path=test_db)
    assert "Freelance Dev" not in user_cats["income"]

    # Goals cleared
    goals = get_user_goals(user_id, db_path=test_db)
    assert len(goals) == 0


