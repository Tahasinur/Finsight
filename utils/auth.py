"""Local multi-user accounts, password verification, profiles, and isolated stores."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from io import BytesIO as MemoryBuffer
import json
from math import isfinite
from pathlib import Path
from typing import Iterator
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
from PIL import Image, ImageOps


AUTH_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "finwise_users.sqlite3"
PASSWORD_ITERATIONS = 310_000
MAX_AVATAR_BYTES = 5 * 1024 * 1024
SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def initialize_auth_store(db_path: str | Path = AUTH_DB_PATH) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
                avatar_filename TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        user_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        if "role" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"
            )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_goals (
                goal_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                goal_name TEXT NOT NULL,
                target_amount REAL NOT NULL CHECK (target_amount > 0),
                current_savings REAL NOT NULL DEFAULT 0 CHECK (current_savings >= 0),
                monthly_saving_limit REAL NOT NULL CHECK (monthly_saving_limit >= 0),
                deadline_date TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, goal_name)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_goals_user_active ON user_goals(user_id, active, deadline_date)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                dashboard_period TEXT NOT NULL DEFAULT 'Last 30 days',
                initial_balance REAL NOT NULL DEFAULT 0.0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        pref_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(user_preferences)").fetchall()
        }
        if "initial_balance" not in pref_columns:
            connection.execute(
                "ALTER TABLE user_preferences ADD COLUMN initial_balance REAL NOT NULL DEFAULT 0.0"
            )
        if "rule_thresholds" not in pref_columns:
            connection.execute(
                "ALTER TABLE user_preferences ADD COLUMN rule_thresholds TEXT DEFAULT NULL"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                run_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                module_type TEXT NOT NULL,
                ledger_fingerprint TEXT NOT NULL,
                result_payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_analysis_runs_user ON analysis_runs(user_id, module_type, created_at DESC)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                date TEXT NOT NULL,
                type TEXT CHECK(type IN ('Income', 'Expense', 'income', 'expense')) NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_user_category ON transactions(user_id, category)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_categories (
                category_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                category_name TEXT NOT NULL,
                category_type TEXT CHECK(category_type IN ('Income', 'Expense', 'income', 'expense')) NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, category_name)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_custom_categories_user ON custom_categories(user_id)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS login_attempts (
                email TEXT PRIMARY KEY,
                attempt_count INTEGER DEFAULT 1,
                last_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                locked_until TEXT
            )
            """
        )
    migrate_existing_csv_ledgers(path)


MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 300  # 5 minutes


def migrate_existing_csv_ledgers(db_path: str | Path = AUTH_DB_PATH) -> int:
    """Migrate legacy per-user transactions.csv files into SQLite transactions table."""
    path = Path(db_path)
    user_data_dir = path.resolve().parent / "user_data"
    if not user_data_dir.is_dir():
        return 0

    migrated_count = 0
    with _connect(path) as connection:
        user_ids = {row["user_id"] for row in connection.execute("SELECT user_id FROM users").fetchall()}
        for user_folder in user_data_dir.iterdir():
            if not user_folder.is_dir():
                continue
            user_id = user_folder.name
            if user_id not in user_ids:
                continue
            csv_path = user_folder / "transactions.csv"
            if not csv_path.is_file():
                continue

            try:
                df = pd.read_csv(csv_path)
                if not df.empty and "date" in df.columns and "amount" in df.columns:
                    for _, row in df.iterrows():
                        t_id = str(row.get("transaction_id", "")).strip() or str(uuid4())
                        t_date = str(row.get("date", "")).strip()
                        t_type = str(row.get("type", "expense")).strip()
                        t_cat = str(row.get("category", "Other")).strip()
                        try:
                            t_amount = float(row.get("amount", 0))
                        except (ValueError, TypeError):
                            continue
                        if t_amount <= 0 or not t_date:
                            continue
                        t_desc = str(row.get("description", "")).strip() if pd.notna(row.get("description")) else ""
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO transactions
                            (transaction_id, user_id, date, type, category, amount, description, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                            """,
                            (t_id, user_id, t_date, t_type, t_cat, t_amount, t_desc),
                        )
                        migrated_count += 1
                backup_path = user_folder / "transactions.csv.migrated"
                csv_path.replace(backup_path)
            except Exception:
                pass
    return migrated_count


def check_login_lockout(email: str, db_path: str | Path = AUTH_DB_PATH) -> tuple[bool, int]:
    """Check if an email is locked out due to excessive failed attempts. Returns (is_locked, remaining_seconds)."""
    try:
        normalized_email = _normalize_email(email)
    except ValueError:
        return False, 0
    path = Path(db_path)
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT attempt_count, locked_until FROM login_attempts WHERE email = ?",
            (normalized_email,),
        ).fetchone()
    if not row or not row["locked_until"]:
        return False, 0
    try:
        locked_until = datetime.fromisoformat(row["locked_until"])
        now = datetime.now(timezone.utc)
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        remaining = int((locked_until - now).total_seconds())
        if remaining > 0:
            return True, remaining
    except Exception:
        pass
    clear_login_attempts(normalized_email, path)
    return False, 0


def record_login_failure(email: str, db_path: str | Path = AUTH_DB_PATH) -> tuple[int, bool, int]:
    """Record a failed login attempt. Returns (attempt_count, is_locked, lock_seconds)."""
    try:
        normalized_email = _normalize_email(email)
    except ValueError:
        return 1, False, 0
    path = Path(db_path)
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT attempt_count, locked_until FROM login_attempts WHERE email = ?",
            (normalized_email,),
        ).fetchone()
        if not row:
            connection.execute(
                "INSERT INTO login_attempts (email, attempt_count, last_attempt_at, locked_until) "
                "VALUES (?, 1, CURRENT_TIMESTAMP, NULL)",
                (normalized_email,),
            )
            return 1, False, 0
        new_count = row["attempt_count"] + 1
        if new_count >= MAX_LOGIN_ATTEMPTS:
            locked_until = (datetime.now(timezone.utc) + timedelta(seconds=LOCKOUT_DURATION_SECONDS)).isoformat()
            connection.execute(
                "UPDATE login_attempts SET attempt_count = ?, last_attempt_at = CURRENT_TIMESTAMP, locked_until = ? WHERE email = ?",
                (new_count, locked_until, normalized_email),
            )
            return new_count, True, LOCKOUT_DURATION_SECONDS
        else:
            connection.execute(
                "UPDATE login_attempts SET attempt_count = ?, last_attempt_at = CURRENT_TIMESTAMP WHERE email = ?",
                (new_count, normalized_email),
            )
            return new_count, False, 0


def clear_login_attempts(email: str, db_path: str | Path = AUTH_DB_PATH) -> None:
    """Clear failed login attempts after successful authentication or lockout expiration."""
    try:
        normalized_email = _normalize_email(email)
    except ValueError:
        return
    path = Path(db_path)
    with _connect(path) as connection:
        connection.execute("DELETE FROM login_attempts WHERE email = ?", (normalized_email,))


def register_user(
    email: str,
    display_name: str,
    password: str,
    db_path: str | Path = AUTH_DB_PATH,
) -> dict:
    normalized_email = _normalize_email(email)
    clean_name = display_name.strip()
    if not clean_name or len(clean_name) > 80:
        raise ValueError("Enter a display name between 1 and 80 characters.")
    if len(password) < 10 or len(password) > 128:
        raise ValueError("Password must be between 10 and 128 characters.")

    user_id = str(uuid4())
    salt = secrets.token_bytes(16)
    password_hash = _hash_password(password, salt)
    bootstrap_email = os.environ.get("FINWISE_ADMIN_EMAIL", "").strip().casefold()
    role = "admin" if bootstrap_email and normalized_email == bootstrap_email else "user"
    path = Path(db_path)
    initialize_auth_store(path)
    try:
        with _connect(path) as connection:
            connection.execute(
                "INSERT INTO users (user_id, email, display_name, password_salt, password_hash, role) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, normalized_email, clean_name, salt, password_hash, role),
            )
    except sqlite3.IntegrityError as error:
        raise ValueError("An account with that email already exists.") from error

    return get_user_by_id(user_id, path)


def authenticate_user(email: str, password: str, db_path: str | Path = AUTH_DB_PATH) -> dict | None:
    normalized_email = _normalize_email(email)
    path = Path(db_path)
    initialize_auth_store(path)

    # 1. Check lockout status
    is_locked, remaining_seconds = check_login_lockout(normalized_email, path)
    if is_locked:
        minutes = max(1, (remaining_seconds + 59) // 60)
        raise ValueError(f"Account is temporarily locked due to too many failed attempts. Try again in {minutes} minute(s).")

    with _connect(path) as connection:
        row = connection.execute(
            "SELECT user_id, email, display_name, password_salt, password_hash, role, avatar_filename, created_at "
            "FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()

    if row is None:
        count, locked, remaining = record_login_failure(normalized_email, path)
        if locked:
            raise ValueError("Account is temporarily locked due to too many failed attempts. Try again in 5 minutes.")
        return None

    actual_hash = _hash_password(password, row["password_salt"])
    if not hmac.compare_digest(actual_hash, row["password_hash"]):
        count, locked, remaining = record_login_failure(normalized_email, path)
        if locked:
            raise ValueError("Account is temporarily locked due to too many failed attempts. Try again in 5 minutes.")
        return None

    # Clear attempts on successful authentication
    clear_login_attempts(normalized_email, path)

    bootstrap_email = os.environ.get("FINWISE_ADMIN_EMAIL", "").strip().casefold()
    if bootstrap_email and normalized_email == bootstrap_email and row["role"] != "admin":
        with _connect(path) as connection:
            connection.execute("UPDATE users SET role = 'admin' WHERE user_id = ?", (row["user_id"],))
        return get_user_by_id(row["user_id"], path)
    return _row_to_profile(row)


def get_user_by_id(user_id: str, db_path: str | Path = AUTH_DB_PATH) -> dict | None:
    try:
        canonical_id = str(UUID(str(user_id)))
    except (ValueError, TypeError, AttributeError):
        return None

    path = Path(db_path)
    initialize_auth_store(path)
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT user_id, email, display_name, password_salt, password_hash, role, avatar_filename, created_at "
            "FROM users WHERE user_id = ?",
            (canonical_id,),
        ).fetchone()
    return _row_to_profile(row) if row is not None else None


def list_user_summaries(admin_user_id: str, db_path: str | Path = AUTH_DB_PATH) -> list[dict]:
    _require_admin(admin_user_id, db_path)
    path = Path(db_path).resolve()
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT 
                u.user_id, 
                u.email, 
                u.display_name, 
                u.role, 
                u.created_at,
                COUNT(t.transaction_id) AS transaction_count,
                MAX(t.date) AS latest_activity,
                SUM(CASE WHEN t.type = 'income' THEN t.amount ELSE 0 END) AS total_income,
                SUM(CASE WHEN t.type = 'expense' THEN t.amount ELSE 0 END) AS total_expenses
            FROM users u
            LEFT JOIN transactions t ON u.user_id = t.user_id
            GROUP BY u.user_id, u.email, u.display_name, u.role, u.created_at
            ORDER BY u.created_at DESC
            """
        ).fetchall()
        summaries = []
        for row in rows:
            transaction_count = int(row["transaction_count"] or 0)
            if transaction_count == 0:
                ledger = path.parent / "user_data" / row["user_id"] / "transactions.csv"
                if ledger.is_file():
                    with ledger.open("r", encoding="utf-8", newline="") as source:
                        transaction_count = max(0, sum(1 for _ in source) - 1)
            summaries.append(
                {
                    "display_name": row["display_name"],
                    "email": row["email"],
                    "role": row["role"],
                    "created_at": row["created_at"],
                    "transaction_count": transaction_count,
                    "latest_activity": row["latest_activity"] or "N/A",
                    "total_volume": float(row["total_income"] or 0.0) + float(row["total_expenses"] or 0.0),
                }
            )
    return summaries


def get_admin_system_stats(admin_user_id: str, db_path: str | Path = AUTH_DB_PATH) -> dict:
    _require_admin(admin_user_id, db_path)
    path = Path(db_path).resolve()
    with _connect(path) as connection:
        counts_row = connection.execute(
            "SELECT COUNT(*), SUM(CASE WHEN role = 'admin' THEN 1 ELSE 0 END) FROM users"
        ).fetchone()
        user_count = int(counts_row[0]) if counts_row else 0
        admin_count = int(counts_row[1] or 0) if counts_row else 0
        goal_count = int(connection.execute("SELECT COUNT(*) FROM user_goals WHERE active = 1").fetchone()[0])
        db_tx_count = int(connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
    ledgers = list((path.parent / "user_data").glob("*/transactions.csv"))
    csv_tx_count = 0
    for ledger in ledgers:
        with ledger.open("r", encoding="utf-8", newline="") as source:
            csv_tx_count += max(0, sum(1 for _ in source) - 1)
    total_tx_count = db_tx_count if db_tx_count > 0 else csv_tx_count
    return {
        "user_count": user_count,
        "admin_count": admin_count,
        "active_goal_count": goal_count,
        "private_ledger_count": len(ledgers) or user_count,
        "transaction_row_count": total_tx_count,
        "database_path": path.name,
    }


def update_user_profile(
    user_id: str,
    display_name: str,
    avatar_bytes: bytes | None = None,
    db_path: str | Path = AUTH_DB_PATH,
) -> dict:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to edit your profile.")
    clean_name = display_name.strip()
    if not clean_name or len(clean_name) > 80:
        raise ValueError("Enter a display name between 1 and 80 characters.")

    avatar_filename = user["avatar_filename"]
    if avatar_bytes is not None:
        avatar_filename = _save_avatar(user["user_id"], avatar_bytes, db_path)

    path = Path(db_path)
    with _connect(path) as connection:
        connection.execute(
            "UPDATE users SET display_name = ?, avatar_filename = ? WHERE user_id = ?",
            (clean_name, avatar_filename, user["user_id"]),
        )
    return get_user_by_id(user["user_id"], path)


def validate_profile_picture(image_bytes: bytes) -> None:
    """Validate image uploads before a new account is created."""
    _validated_avatar_image(image_bytes)


def get_user_goals(user_id: str, db_path: str | Path = AUTH_DB_PATH, active_only: bool = False) -> list[dict]:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to view goals.")
    with _connect(Path(db_path)) as connection:
        query = (
            "SELECT goal_id, goal_name, target_amount, current_savings, monthly_saving_limit, "
            "deadline_date, active, created_at, updated_at FROM user_goals "
            "WHERE user_id = ?"
        )
        if active_only:
            query += " AND active = 1"
        query += " ORDER BY deadline_date, goal_name"
        rows = connection.execute(query, (user["user_id"],)).fetchall()
    return [dict(row) for row in rows]


def save_user_goal(
    user_id: str,
    goal_name: str,
    target_amount: float,
    current_savings: float,
    monthly_saving_limit: float,
    deadline_date: date | str,
    db_path: str | Path = AUTH_DB_PATH,
) -> dict:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to save a goal.")
    name = goal_name.strip()
    if not name or len(name) > 100:
        raise ValueError("Goal name must be between 1 and 100 characters.")
    values = [float(target_amount), float(current_savings), float(monthly_saving_limit)]
    if not all(isfinite(value) for value in values):
        raise ValueError("Goal amounts must be finite numbers.")
    if values[0] <= 0 or values[1] < 0 or values[2] < 0:
        raise ValueError("Goal target must be positive; savings and monthly limit cannot be negative.")
    try:
        deadline = date.fromisoformat(deadline_date) if isinstance(deadline_date, str) else deadline_date
    except ValueError as error:
        raise ValueError("Enter a valid goal deadline.") from error
    if not isinstance(deadline, date):
        raise ValueError("Enter a valid goal deadline.")
    goal_id = str(uuid4())
    with _connect(Path(db_path)) as connection:
        connection.execute(
            "INSERT INTO user_goals (goal_id, user_id, goal_name, target_amount, current_savings, "
            "monthly_saving_limit, deadline_date) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, goal_name) DO UPDATE SET target_amount=excluded.target_amount, "
            "current_savings=excluded.current_savings, monthly_saving_limit=excluded.monthly_saving_limit, "
            "deadline_date=excluded.deadline_date, active=1, updated_at=CURRENT_TIMESTAMP",
            (goal_id, user["user_id"], name, values[0], values[1], values[2], deadline.isoformat()),
        )
        row = connection.execute(
            "SELECT goal_id, goal_name, target_amount, current_savings, monthly_saving_limit, "
            "deadline_date, active, created_at, updated_at FROM user_goals "
            "WHERE user_id = ? AND goal_name = ?",
            (user["user_id"], name),
        ).fetchone()
    return dict(row)


def deactivate_user_goal(user_id: str, goal_id: str, db_path: str | Path = AUTH_DB_PATH) -> None:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to update goals.")
    with _connect(Path(db_path)) as connection:
        result = connection.execute(
            "UPDATE user_goals SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND goal_id = ?",
            (user["user_id"], goal_id),
        )
        if result.rowcount == 0:
            raise KeyError("Goal not found in this account.")


def change_user_password(
    user_id: str,
    current_password: str,
    new_password: str,
    db_path: str | Path = AUTH_DB_PATH,
) -> None:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again before changing your password.")
    if len(new_password) < 10 or len(new_password) > 128:
        raise ValueError("New password must be between 10 and 128 characters.")
    path = Path(db_path)
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT password_salt, password_hash FROM users WHERE user_id = ?",
            (user["user_id"],),
        ).fetchone()
    if row is None or not hmac.compare_digest(_hash_password(current_password, row["password_salt"]), row["password_hash"]):
        raise ValueError("Current password did not match this account.")
    new_salt = secrets.token_bytes(16)
    new_hash = _hash_password(new_password, new_salt)
    with _connect(path) as connection:
        connection.execute(
            "UPDATE users SET password_salt = ?, password_hash = ? WHERE user_id = ?",
            (new_salt, new_hash, user["user_id"]),
        )


def get_user_preferences(user_id: str, db_path: str | Path = AUTH_DB_PATH) -> dict:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to load preferences.")
    with _connect(Path(db_path)) as connection:
        row = connection.execute(
            "SELECT dashboard_period, initial_balance FROM user_preferences WHERE user_id = ?",
            (user["user_id"],),
        ).fetchone()
    if row:
        balance = 0.0
        try:
            balance = float(row["initial_balance"]) if row["initial_balance"] is not None else 0.0
        except (ValueError, IndexError, KeyError):
            pass
        return {
            "dashboard_period": row["dashboard_period"],
            "initial_balance": balance,
        }
    return {"dashboard_period": "Last 30 days", "initial_balance": 0.0}


def save_user_preferences(
    user_id: str,
    dashboard_period: str | None = None,
    initial_balance: float | None = None,
    db_path: str | Path = AUTH_DB_PATH,
) -> dict:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to save preferences.")
    current_prefs = get_user_preferences(user["user_id"], db_path)
    period = dashboard_period if dashboard_period is not None else current_prefs["dashboard_period"]
    balance = float(initial_balance) if initial_balance is not None else current_prefs["initial_balance"]
    if period not in {"This month", "Last 30 days", "Custom"}:
        raise ValueError("Choose a supported dashboard period.")
    if not isfinite(balance) or balance < 0:
        raise ValueError("Starting balance must be a finite, nonnegative amount.")
    with _connect(Path(db_path)) as connection:
        connection.execute(
            "INSERT INTO user_preferences (user_id, dashboard_period, initial_balance) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET dashboard_period=excluded.dashboard_period, "
            "initial_balance=excluded.initial_balance, updated_at=CURRENT_TIMESTAMP",
            (user["user_id"], period, balance),
        )
    return get_user_preferences(user["user_id"], db_path)


def get_user_thresholds(user_id: str | None, db_path: str | Path = AUTH_DB_PATH):
    """Retrieve personal rule thresholds for user, falling back to system defaults."""
    from models.rule_engine import RuleThresholds

    if not user_id:
        return RuleThresholds()
    user = get_user_by_id(user_id, db_path)
    if user is None:
        return RuleThresholds()
    with _connect(Path(db_path)) as connection:
        row = connection.execute(
            "SELECT rule_thresholds FROM user_preferences WHERE user_id = ?",
            (user["user_id"],),
        ).fetchone()
    if row and row["rule_thresholds"]:
        try:
            return RuleThresholds.from_dict(json.loads(row["rule_thresholds"]))
        except Exception:
            pass
    return RuleThresholds()


def save_user_thresholds(
    user_id: str,
    thresholds,
    db_path: str | Path = AUTH_DB_PATH,
):
    """Save updated rule thresholds in user_preferences."""
    from models.rule_engine import RuleThresholds

    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to save rule thresholds.")

    t_obj = thresholds if isinstance(thresholds, RuleThresholds) else RuleThresholds.from_dict(thresholds)
    for name, val in t_obj.to_dict().items():
        if not isfinite(val) or val < 0 or val > 2.0:
            raise ValueError(f"Threshold for {name} must be between 0% and 200%.")

    payload = json.dumps(t_obj.to_dict())
    with _connect(Path(db_path)) as connection:
        connection.execute(
            """
            INSERT INTO user_preferences (user_id, dashboard_period, initial_balance, rule_thresholds)
            VALUES (?, 'Last 30 days', 0.0, ?)
            ON CONFLICT(user_id) DO UPDATE SET rule_thresholds=excluded.rule_thresholds, updated_at=CURRENT_TIMESTAMP
            """,
            (user["user_id"], payload),
        )
    return t_obj


def get_user_categories(user_id: str | None, db_path: str | Path = AUTH_DB_PATH) -> dict[str, list[str]]:
    """Return default categories combined with user-defined custom categories."""
    from utils.data_loader import EXPENSE_CATEGORIES, INCOME_CATEGORIES

    income = list(INCOME_CATEGORIES)
    expense = list(EXPENSE_CATEGORIES)
    if not user_id:
        return {"income": income, "expense": expense}
    user = get_user_by_id(user_id, db_path)
    if user is None:
        return {"income": income, "expense": expense}
    with _connect(Path(db_path)) as connection:
        rows = connection.execute(
            "SELECT category_name, category_type FROM custom_categories WHERE user_id = ? ORDER BY category_name",
            (user["user_id"],),
        ).fetchall()
    for row in rows:
        name = row["category_name"]
        cat_type = row["category_type"].lower()
        if cat_type == "income" and name not in income:
            income.append(name)
        elif cat_type == "expense" and name not in expense:
            expense.append(name)
    return {"income": income, "expense": expense}


def add_custom_category(
    user_id: str,
    name: str,
    category_type: str,
    db_path: str | Path = AUTH_DB_PATH,
) -> str:
    """Create a new custom category for a user."""
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to add custom categories.")
    clean_name = name.strip()
    if not clean_name or len(clean_name) > 50:
        raise ValueError("Category name must be between 1 and 50 characters.")
    norm_type = category_type.strip().lower()
    if norm_type not in {"income", "expense"}:
        raise ValueError("Category type must be Income or Expense.")

    existing = get_user_categories(user["user_id"], db_path)[norm_type]
    if any(c.casefold() == clean_name.casefold() for c in existing):
        raise ValueError(f"Category '{clean_name}' already exists for {norm_type.title()}.")

    cat_id = str(uuid4())
    stored_type = norm_type.title()
    with _connect(Path(db_path)) as connection:
        connection.execute(
            """
            INSERT INTO custom_categories (category_id, user_id, category_name, category_type, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (cat_id, user["user_id"], clean_name, stored_type),
        )
    return cat_id


def delete_custom_category(
    user_id: str,
    category_id_or_name: str,
    db_path: str | Path = AUTH_DB_PATH,
) -> None:
    """Delete a user's custom category by ID or name."""
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to delete custom categories.")
    identifier = category_id_or_name.strip()
    with _connect(Path(db_path)) as connection:
        cursor = connection.execute(
            "DELETE FROM custom_categories WHERE user_id = ? AND (category_id = ? OR category_name = ?)",
            (user["user_id"], identifier, identifier),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"Custom category '{identifier}' not found.")


class _PayloadEncoder(json.JSONEncoder):
    def default(self, obj):
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return super().default(obj)


def _reconstruct_run_payload(module_type: str, data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    if module_type == "budget_optimizer" and "result" in data and isinstance(data["result"], dict):
        from models.budget_csp import BudgetOptimizationResult, SearchStatistics

        res_data = dict(data["result"])
        stats_data = res_data.get("statistics")
        if isinstance(stats_data, dict):
            res_data["statistics"] = SearchStatistics(**stats_data)
        data["result"] = BudgetOptimizationResult(**res_data)
    elif module_type == "goal_planner" and "result" in data and isinstance(data["result"], dict):
        from models.goal_astar import GoalPlanResult

        res_data = dict(data["result"])
        if isinstance(res_data.get("goal_month"), str):
            res_data["goal_month"] = date.fromisoformat(res_data["goal_month"])
        data["result"] = GoalPlanResult(**res_data)
    return data


def save_analysis_run(
    user_id: str,
    module_type: str,
    ledger_fingerprint: str,
    payload: dict,
    db_path: str | Path = AUTH_DB_PATH,
) -> str:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to save analysis runs.")
    run_id = str(uuid4())
    serialized = json.dumps(payload, cls=_PayloadEncoder)
    with _connect(Path(db_path)) as connection:
        connection.execute(
            "INSERT INTO analysis_runs (run_id, user_id, module_type, ledger_fingerprint, result_payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (run_id, user["user_id"], module_type, ledger_fingerprint, serialized),
        )
    return run_id


def get_latest_analysis_run(
    user_id: str,
    module_type: str,
    db_path: str | Path = AUTH_DB_PATH,
) -> dict | None:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        return None
    with _connect(Path(db_path)) as connection:
        row = connection.execute(
            "SELECT run_id, module_type, ledger_fingerprint, result_payload, created_at "
            "FROM analysis_runs WHERE user_id = ? AND module_type = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (user["user_id"], module_type),
        ).fetchone()
    if row is None:
        return None
    payload = json.loads(row["result_payload"])
    payload = _reconstruct_run_payload(module_type, payload)
    payload["_persisted_run_id"] = row["run_id"]
    payload["_created_at"] = row["created_at"]
    return payload


def export_user_data(user_id: str, db_path: str | Path = AUTH_DB_PATH) -> bytes:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to export your data.")
    goals = get_user_goals(user["user_id"], db_path)
    profile_export = {
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"],
        "created_at": user["created_at"],
    }
    preferences = get_user_preferences(user["user_id"], db_path)
    with _connect(Path(db_path)) as connection:
        tx_rows = connection.execute(
            "SELECT transaction_id, date, type, category, amount, description FROM transactions WHERE user_id = ? ORDER BY date DESC, transaction_id DESC",
            (user["user_id"],),
        ).fetchall()
    if tx_rows:
        tx_df = pd.DataFrame([dict(r) for r in tx_rows])
    else:
        ledger_path = user_transactions_path(user["user_id"], db_path)
        tx_df = pd.read_csv(ledger_path) if ledger_path.is_file() else pd.DataFrame(columns=["transaction_id", "date", "type", "category", "amount", "description"])

    archive_buffer = MemoryBuffer()
    with ZipFile(archive_buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("profile.json", json.dumps(profile_export, indent=2))
        archive.writestr("goals.csv", pd.DataFrame(goals).to_csv(index=False))
        archive.writestr("preferences.json", json.dumps(preferences, indent=2))
        archive.writestr("transactions.csv", tx_df.to_csv(index=False))
    return archive_buffer.getvalue()


def clear_user_financial_data(user_id: str, db_path: str | Path = AUTH_DB_PATH) -> None:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again before clearing data.")
    avatar = user_avatar_path(user, db_path)
    ledger_path = user_transactions_path(user["user_id"], db_path)
    from utils.data_loader import TRANSACTION_COLUMNS, save_transactions

    save_transactions(pd.DataFrame(columns=TRANSACTION_COLUMNS), ledger_path)
    with _connect(Path(db_path)) as connection:
        connection.execute("DELETE FROM transactions WHERE user_id = ?", (user["user_id"],))
        connection.execute("DELETE FROM custom_categories WHERE user_id = ?", (user["user_id"],))
        connection.execute("DELETE FROM user_goals WHERE user_id = ?", (user["user_id"],))
        connection.execute("DELETE FROM user_preferences WHERE user_id = ?", (user["user_id"],))
        connection.execute("DELETE FROM analysis_runs WHERE user_id = ?", (user["user_id"],))
        connection.execute("UPDATE users SET avatar_filename = NULL WHERE user_id = ?", (user["user_id"],))
    if avatar is not None:
        avatar.unlink(missing_ok=True)


def user_avatar_path(user: dict, db_path: str | Path = AUTH_DB_PATH) -> Path | None:
    filename = user.get("avatar_filename")
    if not filename:
        return None
    image_path = Path(db_path).resolve().parent / "profile_images" / filename
    return image_path if image_path.is_file() else None


def user_transactions_path(user_id: str, db_path: str | Path = AUTH_DB_PATH) -> Path:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to access transaction data.")
    try:
        canonical_id = str(UUID(user["user_id"]))
    except (ValueError, TypeError) as error:
        raise ValueError("Invalid account identifier.") from error

    path = Path(db_path).resolve().parent / "user_data" / canonical_id / "transactions.csv"
    if not path.is_file():
        from utils.data_loader import TRANSACTION_COLUMNS

        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=TRANSACTION_COLUMNS).to_csv(path, index=False)
    return path


def _save_avatar(user_id: str, image_bytes: bytes, db_path: str | Path) -> str:
    image = _validated_avatar_image(image_bytes)

    directory = Path(db_path).resolve().parent / "profile_images"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{user_id}.webp"
    destination = directory / filename
    temporary = directory / f"{user_id}.tmp.webp"
    image.save(temporary, format="WEBP", quality=88, method=5)
    temporary.replace(destination)
    return filename


def _validated_avatar_image(image_bytes: bytes) -> Image.Image:
    if not image_bytes or len(image_bytes) > MAX_AVATAR_BYTES:
        raise ValueError("Profile picture must be a nonempty image smaller than 5 MB.")

    try:
        source = Image.open(BytesIO(image_bytes))
        if source.format not in SUPPORTED_IMAGE_FORMATS:
            raise ValueError("Upload a PNG, JPEG, or WebP profile picture.")
        if source.width * source.height > 20_000_000:
            raise ValueError("Profile picture dimensions must be at most 20 megapixels.")
        source.verify()
        source = Image.open(BytesIO(image_bytes))
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((512, 512))
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("The uploaded profile picture could not be read.") from error
    return image


def _normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if len(normalized) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        raise ValueError("Enter a valid email address.")
    return normalized


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
        dklen=32,
    )


@contextmanager
def _connect(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _row_to_profile(row: sqlite3.Row) -> dict:
    return {
        "user_id": row["user_id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "avatar_filename": row["avatar_filename"],
        "created_at": row["created_at"],
    }


def _require_admin(user_id: str, db_path: str | Path) -> dict:
    user = get_user_by_id(user_id, db_path)
    if user is None or user["role"] != "admin":
        raise PermissionError("Administrator access is required.")
    return user
