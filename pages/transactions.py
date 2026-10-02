"""Transaction browser and local CSV transaction management."""

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from utils.calculations import format_currency
from utils.data_loader import (
    CATEGORIES_BY_TYPE,
    add_transaction,
    delete_transaction,
    import_transactions,
    update_transaction,
)


def render(frame: pd.DataFrame, store_path: str | Path | None = None) -> None:
    st.title("Income & Expenses")
    st.caption("One local transaction ledger shared by every FinWise module.")

    income = float(frame.loc[frame["type"] == "income", "amount"].sum())
    expenses = float(frame.loc[frame["type"] == "expense", "amount"].sum())
    income_col, expense_col, balance_col = st.columns(3)
    income_col.metric("Total income", format_currency(income))
    expense_col.metric("Total expenses", format_currency(expenses))
    balance_col.metric(
        "Current balance",
        format_currency(income - expenses),
        help="Cumulative income minus expenses from the start of this ledger. Opening bank balances are not tracked.",
    )

    list_tab, add_tab, manage_tab, import_tab = st.tabs(
        ["Transactions", "Add transaction", "Edit or delete", "Import CSV"]
    )
    with list_tab:
        _render_transaction_table(frame)
    with add_tab:
        _render_add_form(store_path)
    with manage_tab:
        _render_edit_delete(frame, store_path)
    with import_tab:
        _render_import(store_path)


def _render_transaction_table(frame: pd.DataFrame) -> None:
    st.subheader("Transaction history")
    search_col, type_col, category_col, date_col = st.columns([1.4, 0.8, 1, 1.4])
    search = search_col.text_input("Search", placeholder="Description or category")
    selected_type = type_col.selectbox("Type", ["All", "Income", "Expense"])
    categories = ["All", *sorted(frame["category"].dropna().unique().tolist())]
    selected_category = category_col.selectbox("Category", categories)

    valid_dates = frame["date"].dropna()
    if valid_dates.empty:
        date_range = None
        date_col.caption("No valid transaction dates to filter.")
    else:
        start = valid_dates.min().date()
        end = valid_dates.max().date()
        date_range = date_col.date_input("Date range", value=(start, end))

    filtered = frame.copy()
    if selected_type != "All":
        filtered = filtered.loc[filtered["type"] == selected_type.lower()]
    if selected_category != "All":
        filtered = filtered.loc[filtered["category"] == selected_category]
    if search:
        searchable = filtered[["description", "category", "type"]].astype("string")
        matches = searchable.apply(
            lambda column: column.str.contains(search, case=False, regex=False, na=False)
        ).any(axis=1)
        filtered = filtered.loc[matches]
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        start_date, end_date = date_range
        filtered = filtered.loc[
            filtered["date"].dt.date.between(start_date, end_date)
        ]

    st.caption(f"Showing {len(filtered):,} of {len(frame):,} transactions")
    table = filtered.drop(columns=["transaction_id"], errors="ignore").rename(
        columns={"date": "Date", "type": "Type", "category": "Category", "amount": "Amount", "description": "Description"}
    )
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={"Amount": st.column_config.NumberColumn(format="$%.2f")},
    )


def _render_add_form(store_path: str | Path | None = None) -> None:
    st.subheader("Add a transaction")
    selected_type = st.selectbox(
        "Transaction type",
        ["income", "expense"],
        format_func=str.title,
        key="new_transaction_type",
    )
    with st.form("add_transaction_form", clear_on_submit=True):
        left, middle, right = st.columns(3)
        transaction_date = left.date_input("Date", value=date.today())
        amount = middle.number_input("Amount", min_value=0.01, value=0.01, step=1.0, format="%.2f")
        category = right.selectbox("Category", CATEGORIES_BY_TYPE[selected_type])
        description = st.text_input("Description", max_chars=120)
        submitted = st.form_submit_button("Add transaction", type="primary")

    if submitted:
        if not description.strip():
            st.error("Enter a description before adding the transaction.")
            return
        try:
            add_transaction(
                {
                    "date": transaction_date,
                    "type": selected_type,
                    "category": category,
                    "amount": amount,
                    "description": description.strip(),
                },
                **_store_path_kwargs(store_path),
            )
        except (OSError, ValueError) as error:
            st.error(str(error))
            return
        st.success("Transaction added to the shared ledger.")
        st.rerun()


def _render_edit_delete(frame: pd.DataFrame, store_path: str | Path | None = None) -> None:
    st.subheader("Edit or delete a transaction")
    if frame.empty:
        st.info("Add or import a transaction before editing the ledger.")
        return

    transaction_ids = frame["transaction_id"].tolist()
    selected_id = st.selectbox(
        "Select transaction",
        transaction_ids,
        format_func=lambda transaction_id: _transaction_label(frame, transaction_id),
    )
    selected = frame.loc[frame["transaction_id"] == selected_id].iloc[0]
    current_type = selected["type"] if pd.notna(selected["type"]) else "expense"
    if current_type not in CATEGORIES_BY_TYPE:
        current_type = "expense"
    edit_type = st.selectbox(
        "Transaction type",
        ["income", "expense"],
        index=["income", "expense"].index(current_type),
        format_func=str.title,
        key=f"edit_type_{selected_id}",
    )
    categories = CATEGORIES_BY_TYPE[edit_type]
    selected_category = selected["category"]
    current_category = (
        selected_category
        if pd.notna(selected_category) and selected_category in categories
        else categories[0]
    )

    with st.form(f"edit_transaction_form_{selected_id}"):
        left, middle, right = st.columns(3)
        transaction_date = left.date_input(
            "Date" if pd.notna(selected["date"]) else "Date (missing; choose a value)",
            value=selected["date"].date() if pd.notna(selected["date"]) else date.today(),
        )
        amount = middle.number_input(
            "Amount" if pd.notna(selected["amount"]) else "Amount (missing; enter a value)",
            min_value=0.01,
            value=float(selected["amount"]) if pd.notna(selected["amount"]) else 0.01,
            step=1.0,
            format="%.2f",
        )
        category = right.selectbox(
            "Category",
            categories,
            index=categories.index(current_category),
            key=f"edit_category_{selected_id}_{edit_type}",
        )
        selected_description = selected["description"]
        description = st.text_input(
            "Description",
            value=selected_description if pd.notna(selected_description) else "",
            max_chars=120,
        )
        submitted = st.form_submit_button("Save changes", type="primary")

    if submitted:
        if not description.strip():
            st.error("Description cannot be empty.")
            return
        try:
            update_transaction(
                selected_id,
                {
                    "date": transaction_date,
                    "type": edit_type,
                    "category": category,
                    "amount": amount,
                    "description": description.strip(),
                },
                **_store_path_kwargs(store_path),
            )
        except (OSError, ValueError, KeyError) as error:
            st.error(str(error))
            return
        st.success("Transaction updated in the shared ledger.")
        st.rerun()

    st.divider()
    confirm_delete = st.checkbox(
        "Confirm deletion of this transaction",
        key=f"confirm_delete_{selected_id}",
    )
    if st.button("Delete transaction", disabled=not confirm_delete, key=f"delete_{selected_id}"):
        try:
            delete_transaction(selected_id, **_store_path_kwargs(store_path))
        except (OSError, KeyError) as error:
            st.error(str(error))
            return
        st.success("Transaction deleted from the shared ledger.")
        st.rerun()


def _render_import(store_path: str | Path | None = None) -> None:
    st.subheader("Import transactions")
    st.write("Upload a CSV to append rows to the shared ledger.")
    st.code("date,type,category,amount,description", language="text")
    upload = st.file_uploader("Choose a CSV file", type=["csv"], key="transaction_csv_upload")
    if upload is not None:
        if st.button("Append transactions", type="primary"):
            try:
                imported_count = import_transactions(
                    upload.getvalue(),
                    **_store_path_kwargs(store_path),
                )
            except (OSError, ValueError, pd.errors.ParserError) as error:
                st.error(str(error))
                return
            st.success(f"Added {imported_count:,} transactions to the shared ledger.")
            st.rerun()


def _transaction_label(frame: pd.DataFrame, transaction_id: str) -> str:
    row = frame.loc[frame["transaction_id"] == transaction_id].iloc[0]
    transaction_date = row["date"].strftime("%Y-%m-%d") if pd.notna(row["date"]) else "Date needed"
    transaction_type = row["type"].title() if pd.notna(row["type"]) else "Type needed"
    description = row["description"] if pd.notna(row["description"]) else "No description"
    return f"{transaction_date} · {transaction_type} · {description} · {format_currency(row['amount'])}"


def _store_path_kwargs(store_path: str | Path | None) -> dict:
    return {} if store_path is None else {"path": store_path}
