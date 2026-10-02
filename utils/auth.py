"""Local multi-user accounts, password verification, profiles, and isolated stores."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
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
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


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
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT user_id, email, display_name, password_salt, password_hash, role, avatar_filename, created_at "
            "FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()
    if row is None:
        return None

    actual_hash = _hash_password(password, row["password_salt"])
    if not hmac.compare_digest(actual_hash, row["password_hash"]):
        return None
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
            "SELECT user_id, email, display_name, role, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
    summaries = []
    for row in rows:
        ledger = path.parent / "user_data" / row["user_id"] / "transactions.csv"
        transaction_count = 0
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
            }
        )
    return summaries


def get_admin_system_stats(admin_user_id: str, db_path: str | Path = AUTH_DB_PATH) -> dict:
    _require_admin(admin_user_id, db_path)
    path = Path(db_path).resolve()
    with _connect(path) as connection:
        user_count = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        admin_count = int(connection.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0])
        goal_count = int(connection.execute("SELECT COUNT(*) FROM user_goals WHERE active = 1").fetchone()[0])
    ledgers = list((path.parent / "user_data").glob("*/transactions.csv"))
    transaction_count = 0
    for ledger in ledgers:
        with ledger.open("r", encoding="utf-8", newline="") as source:
            transaction_count += max(0, sum(1 for _ in source) - 1)
    return {
        "user_count": user_count,
        "admin_count": admin_count,
        "active_goal_count": goal_count,
        "private_ledger_count": len(ledgers),
        "transaction_row_count": transaction_count,
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


def get_user_goals(user_id: str, db_path: str | Path = AUTH_DB_PATH) -> list[dict]:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to view goals.")
    with _connect(Path(db_path)) as connection:
        rows = connection.execute(
            "SELECT goal_id, goal_name, target_amount, current_savings, monthly_saving_limit, "
            "deadline_date, active, created_at, updated_at FROM user_goals "
            "WHERE user_id = ? ORDER BY deadline_date, goal_name",
            (user["user_id"],),
        ).fetchall()
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
            "SELECT dashboard_period FROM user_preferences WHERE user_id = ?",
            (user["user_id"],),
        ).fetchone()
    return {"dashboard_period": row["dashboard_period"] if row else "Last 30 days"}


def save_user_preferences(
    user_id: str,
    dashboard_period: str,
    db_path: str | Path = AUTH_DB_PATH,
) -> dict:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to save preferences.")
    if dashboard_period not in {"This month", "Last 30 days", "Custom"}:
        raise ValueError("Choose a supported dashboard period.")
    with _connect(Path(db_path)) as connection:
        connection.execute(
            "INSERT INTO user_preferences (user_id, dashboard_period) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET dashboard_period=excluded.dashboard_period, updated_at=CURRENT_TIMESTAMP",
            (user["user_id"], dashboard_period),
        )
    return get_user_preferences(user["user_id"], db_path)


def export_user_data(user_id: str, db_path: str | Path = AUTH_DB_PATH) -> bytes:
    user = get_user_by_id(user_id, db_path)
    if user is None:
        raise ValueError("Account not found. Sign in again to export your data.")
    ledger_path = user_transactions_path(user["user_id"], db_path)
    goals = get_user_goals(user["user_id"], db_path)
    profile_export = {
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"],
        "created_at": user["created_at"],
    }
    preferences = get_user_preferences(user["user_id"], db_path)
    archive_buffer = MemoryBuffer()
    with ZipFile(archive_buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("profile.json", json.dumps(profile_export, indent=2))
        archive.writestr("goals.csv", pd.DataFrame(goals).to_csv(index=False))
        archive.writestr("preferences.json", json.dumps(preferences, indent=2))
        archive.writestr("transactions.csv", ledger_path.read_bytes())
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
        connection.execute("DELETE FROM user_goals WHERE user_id = ?", (user["user_id"],))
        connection.execute("DELETE FROM user_preferences WHERE user_id = ?", (user["user_id"],))
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
        from utils.data_loader import TRANSACTION_COLUMNS, save_transactions

        save_transactions(pd.DataFrame(columns=TRANSACTION_COLUMNS), path)
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
