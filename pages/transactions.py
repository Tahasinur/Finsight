"""Transaction browser and local CSV transaction management."""

from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from utils.auth import get_user_categories, get_user_preferences
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
    user_id = st.session_state.get("user_id")
    user_prefs = get_user_preferences(user_id) if user_id else {}
    initial_balance = float(user_prefs.get("initial_balance", 0.0))
    current_balance = initial_balance + income - expenses

    income_col, expense_col, balance_col = st.columns(3)
    income_col.metric("Total income", format_currency(income))
    expense_col.metric("Total expenses", format_currency(expenses))
    balance_help = (
        f"Initial balance (${initial_balance:,.2f}) plus cumulative income minus expenses."
        if initial_balance > 0
        else "Cumulative income minus expenses from the start of this ledger. Set your starting balance in My Profile."
    )
    balance_col.metric(
        "Current balance",
        format_currency(current_balance),
        help=balance_help,
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

    valid_dates = frame["date"].dropna()
    default_start = valid_dates.min().date() if not valid_dates.empty else date.today()
    default_end = valid_dates.max().date() if not valid_dates.empty else date.today()
    categories = ["All", *sorted(frame["category"].dropna().unique().tolist())]

    with st.form("transaction_filter_form"):
        search_col, type_col, category_col, date_col = st.columns([1.4, 0.8, 1, 1.4])
        search = search_col.text_input(
            "Search",
            value=st.session_state.get("tx_filter_search", ""),
            placeholder="Description or category",
        )
        type_options = ["All", "Income", "Expense"]
        default_type_idx = (
            type_options.index(st.session_state["tx_filter_type"])
            if st.session_state.get("tx_filter_type") in type_options
            else 0
        )
        selected_type = type_col.selectbox("Type", type_options, index=default_type_idx)

        default_cat_idx = (
            categories.index(st.session_state["tx_filter_category"])
            if st.session_state.get("tx_filter_category") in categories
            else 0
        )
        selected_category = category_col.selectbox("Category", categories, index=default_cat_idx)

        if valid_dates.empty:
            date_range = None
            date_col.caption("No valid transaction dates to filter.")
        else:
            saved_dates = st.session_state.get("tx_filter_dates", (default_start, default_end))
            date_range = date_col.date_input("Date range", value=saved_dates)

        apply_filters = st.form_submit_button("Apply filters", type="primary")

    if apply_filters:
        st.session_state["tx_filter_search"] = search
        st.session_state["tx_filter_type"] = selected_type
        st.session_state["tx_filter_category"] = selected_category
        st.session_state["tx_filter_dates"] = date_range
        st.session_state["tx_current_page"] = 1

    active_search = st.session_state.get("tx_filter_search", search)
    active_type = st.session_state.get("tx_filter_type", selected_type)
    active_category = st.session_state.get("tx_filter_category", selected_category)
    active_dates = st.session_state.get("tx_filter_dates", date_range)

    filtered = frame.copy()
    if active_type != "All":
        filtered = filtered.loc[filtered["type"] == active_type.lower()]
    if active_category != "All":
        filtered = filtered.loc[filtered["category"] == active_category]
    if active_search:
        searchable = filtered[["description", "category", "type"]].astype("string")
        matches = searchable.apply(
            lambda column: column.str.contains(active_search, case=False, regex=False, na=False)
        ).any(axis=1)
        filtered = filtered.loc[matches]
    if isinstance(active_dates, (tuple, list)) and len(active_dates) == 2:
        start_date, end_date = active_dates
        filtered = filtered.loc[
            filtered["date"].dt.date.between(start_date, end_date)
        ]

    total_rows = len(filtered)

    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1.2, 1, 1, 2])
    page_size = ctrl_col1.selectbox("Rows per page", [25, 50, 100], index=0, key="tx_page_size")
    total_pages = max(1, (total_rows + page_size - 1) // page_size)

    current_page = st.session_state.get("tx_current_page", 1)
    if current_page > total_pages:
        current_page = total_pages
        st.session_state["tx_current_page"] = current_page

    prev_clicked = ctrl_col2.button("← Previous", disabled=(current_page <= 1), key="tx_prev_btn")
    next_clicked = ctrl_col3.button("Next →", disabled=(current_page >= total_pages), key="tx_next_btn")

    if prev_clicked and current_page > 1:
        st.session_state["tx_current_page"] = current_page - 1
        st.rerun()
    elif next_clicked and current_page < total_pages:
        st.session_state["tx_current_page"] = current_page + 1
        st.rerun()

    current_page = st.session_state.get("tx_current_page", 1)
    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_rows)

    ctrl_col4.markdown(f"**Page {current_page} of {total_pages}** &nbsp;·&nbsp; {total_rows:,} matches")

    if total_rows > 0:
        st.caption(f"Showing rows {start_idx + 1}–{end_idx} of {total_rows:,} filtered transactions (from {len(frame):,} in ledger)")
        page_slice = filtered.iloc[start_idx:end_idx]
        table = page_slice.drop(columns=["transaction_id"], errors="ignore").rename(
            columns={"date": "Date", "type": "Type", "category": "Category", "amount": "Amount", "description": "Description"}
        )
        st.dataframe(
            table,
            width="stretch",
            hide_index=True,
            column_config={"Amount": st.column_config.NumberColumn(format="$%.2f")},
        )
    else:
        st.info("No transactions match the selected filters.")

    export_csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Export filtered transactions (CSV)",
        data=export_csv,
        file_name="transactions_filtered.csv",
        mime="text/csv",
        help="Export all records matching your active filters to a CSV file.",
    )


def _render_add_form(store_path: str | Path | None = None) -> None:
    st.subheader("Add a transaction")
    selected_type = st.selectbox(
        "Transaction type",
        ["income", "expense"],
        format_func=str.title,
        key="new_transaction_type",
    )
    user_id = st.session_state.get("user_id")
    categories_by_type = get_user_categories(user_id)
    with st.form("add_transaction_form", clear_on_submit=True):
        left, middle, right = st.columns(3)
        transaction_date = left.date_input("Date", value=date.today())
        amount = middle.number_input("Amount", min_value=0.01, value=0.01, step=1.0, format="%.2f")
        category = right.selectbox("Category", categories_by_type[selected_type])
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

    user_id = st.session_state.get("user_id")
    categories_by_type = get_user_categories(user_id)
    transaction_ids = frame["transaction_id"].tolist()
    selected_id = st.selectbox(
        "Select transaction",
        transaction_ids,
        format_func=lambda transaction_id: _transaction_label(frame, transaction_id),
    )
    selected = frame.loc[frame["transaction_id"] == selected_id].iloc[0]
    current_type = selected["type"] if pd.notna(selected["type"]) else "expense"
    if current_type not in categories_by_type:
        current_type = "expense"
    edit_type = st.selectbox(
        "Transaction type",
        ["income", "expense"],
        index=["income", "expense"].index(current_type),
        format_func=str.title,
        key=f"edit_type_{selected_id}",
    )
    categories = categories_by_type[edit_type]
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
    st.write("Upload a CSV to append rows to your ledger. Standard FinWise files or custom bank exports are both supported.")
    st.caption("Standard schema: date, type, category, amount, description")
    upload = st.file_uploader("Choose a CSV file", type=["csv"], key="transaction_csv_upload")
    if upload is not None:
        try:
            raw_bytes = upload.getvalue()
            raw_df = pd.read_csv(BytesIO(raw_bytes))
        except Exception as error:
            st.error(f"Could not parse CSV file: {error}")
            return

        columns = list(raw_df.columns)
        lower_columns = {str(c).strip().casefold(): c for c in columns}
        standard_cols = {"date", "type", "category", "amount", "description"}

        if standard_cols.issubset(lower_columns.keys()):
            st.success(f"Standard FinWise format detected ({len(raw_df):,} rows found).")
            if st.button("Append transactions to ledger", type="primary"):
                try:
                    imported_count = import_transactions(
                        raw_bytes,
                        **_store_path_kwargs(store_path),
                    )
                except (OSError, ValueError, pd.errors.ParserError) as error:
                    st.error(str(error))
                    return
                st.success(f"Added {imported_count:,} transactions to the shared ledger.")
                st.rerun()
        else:
            st.info("Custom CSV format detected. Map your CSV columns to FinWise fields below:")

            def _find_match(candidates: list[str]) -> int:
                for idx, col in enumerate(columns):
                    c_lower = str(col).strip().casefold()
                    if any(cand in c_lower for cand in candidates):
                        return idx
                return 0

            with st.form("csv_column_mapping_form"):
                col_left, col_right = st.columns(2)
                date_idx = _find_match(["date", "time", "day", "posted", "trans"])
                amount_idx = _find_match(["amount", "total", "cost", "sum", "debit", "price", "val"])
                desc_idx = _find_match(["desc", "memo", "payee", "name", "narrative", "merchant", "detail"])

                mapped_date = col_left.selectbox("Date column *", columns, index=date_idx)
                mapped_amount = col_right.selectbox("Amount column *", columns, index=amount_idx)

                type_options = ["(Auto: positive = Income, negative = Expense)", "(All Expenses)", "(All Income)"] + columns
                type_idx = 0
                for idx, col in enumerate(columns):
                    if any(term in str(col).casefold() for term in ["type", "flow", "cr/dr", "transaction_type"]):
                        type_idx = 3 + idx
                        break
                mapped_type = col_left.selectbox("Transaction Type", type_options, index=type_idx)

                cat_options = ["(Infer from Description)", "(Default: Other/Food)"] + columns
                cat_idx = 0
                for idx, col in enumerate(columns):
                    if any(term in str(col).casefold() for term in ["cat", "tag", "label", "group"]):
                        cat_idx = 2 + idx
                        break
                mapped_cat = col_right.selectbox("Category", cat_options, index=cat_idx)
                mapped_desc = col_left.selectbox("Description column", columns, index=desc_idx)

                submitted_mapping = st.form_submit_button("Preview & Import Transactions", type="primary")

            if submitted_mapping:
                try:
                    mapped_df = _build_mapped_transactions(raw_df, mapped_date, mapped_amount, mapped_type, mapped_cat, mapped_desc)
                except Exception as error:
                    st.error(f"Error mapping transactions: {error}")
                    return

                st.subheader("Mapped Preview (Top 5 rows)")
                preview_display = mapped_df.head(5).copy()
                st.dataframe(preview_display, width="stretch", hide_index=True)

                buffer = BytesIO()
                mapped_df.to_csv(buffer, index=False)
                try:
                    imported_count = import_transactions(
                        buffer.getvalue(),
                        **_store_path_kwargs(store_path),
                    )
                except (OSError, ValueError, pd.errors.ParserError) as error:
                    st.error(str(error))
                    return
                st.success(f"Successfully mapped and imported {imported_count:,} transactions!")
                st.rerun()


def _build_mapped_transactions(
    df: pd.DataFrame,
    date_col: str,
    amount_col: str,
    type_col: str,
    category_col: str,
    desc_col: str,
) -> pd.DataFrame:
    result = pd.DataFrame()
    result["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    result["date"] = result["date"].fillna(date.today().strftime("%Y-%m-%d"))

    cleaned_amounts = (
        df[amount_col]
        .astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    numeric_amounts = pd.to_numeric(cleaned_amounts, errors="coerce")

    if type_col == "(Auto: positive = Income, negative = Expense)":
        result["type"] = numeric_amounts.apply(lambda val: "income" if pd.notna(val) and val > 0 else "expense")
        result["amount"] = numeric_amounts.abs()
    elif type_col == "(All Expenses)":
        result["type"] = "expense"
        result["amount"] = numeric_amounts.abs()
    elif type_col == "(All Income)":
        result["type"] = "income"
        result["amount"] = numeric_amounts.abs()
    else:
        raw_types = df[type_col].astype(str).str.strip().str.lower()
        result["type"] = raw_types.apply(
            lambda val: "income" if any(w in val for w in ["in", "cr", "deposit", "salary", "pay"]) else "expense"
        )
        result["amount"] = numeric_amounts.abs()

    result["amount"] = result["amount"].fillna(0.01)
    result.loc[result["amount"] <= 0, "amount"] = 0.01

    raw_descriptions = df[desc_col].astype(str).str.strip().replace("", "Imported transaction")
    result["description"] = raw_descriptions

    if category_col == "(Default: Other/Food)":
        result["category"] = result["type"].apply(lambda t: "Salary" if t == "income" else "Food")
    elif category_col == "(Infer from Description)":
        result["category"] = [
            _infer_category(desc, t)
            for desc, t in zip(result["description"], result["type"])
        ]
    else:
        result["category"] = df[category_col].astype(str).str.strip()

    return result[["date", "type", "category", "amount", "description"]]


def _infer_category(desc: str, transaction_type: str) -> str:
    desc_lower = desc.casefold()
    if transaction_type == "income":
        if any(w in desc_lower for w in ["salary", "payroll", "wage", "paycheck"]):
            return "Salary"
        if any(w in desc_lower for w in ["freelance", "contract", "client", "upwork", "fiverr"]):
            return "Freelance"
        if any(w in desc_lower for w in ["div", "invest", "stock", "interest", "yield"]):
            return "Investment"
        return "Salary"
    else:
        if any(w in desc_lower for w in ["rent", "mortgage", "power", "electric", "water", "utility", "lease"]):
            return "Housing"
        if any(w in desc_lower for w in ["food", "grocer", "market", "cafe", "restaurant", "dining", "uber eats", "doordash"]):
            return "Food"
        if any(w in desc_lower for w in ["transit", "subway", "metro", "gas", "fuel", "uber", "lyft", "parking"]):
            return "Transportation"
        if any(w in desc_lower for w in ["health", "doctor", "pharmacy", "medical", "clinic", "dental"]):
            return "Health"
        if any(w in desc_lower for w in ["tuition", "school", "book", "course", "class", "college", "udemy"]):
            return "Education"
        if any(w in desc_lower for w in ["movie", "game", "netflix", "spotify", "ticket", "cinema", "entertainment"]):
            return "Entertainment"
        return "Food"


def _transaction_label(frame: pd.DataFrame, transaction_id: str) -> str:
    row = frame.loc[frame["transaction_id"] == transaction_id].iloc[0]
    transaction_date = row["date"].strftime("%Y-%m-%d") if pd.notna(row["date"]) else "Date needed"
    transaction_type = row["type"].title() if pd.notna(row["type"]) else "Type needed"
    description = row["description"] if pd.notna(row["description"]) else "No description"
    return f"{transaction_date} · {transaction_type} · {description} · {format_currency(row['amount'])}"


def _store_path_kwargs(store_path: str | Path | None) -> dict:
    return {} if store_path is None else {"path": store_path}
