"""Account profile details and profile-picture management."""

import streamlit as st

from utils.auth import (
    change_user_password,
    export_user_data,
    get_user_by_id,
    get_user_preferences,
    save_user_preferences,
    update_user_profile,
    user_avatar_path,
)


def render(frame) -> None:
    st.title("My Profile")
    user_id = st.session_state.get("user_id")
    profile = get_user_by_id(user_id) if user_id else None
    if profile is None:
        st.error("Your account session could not be found. Sign in again.")
        return

    avatar_path = user_avatar_path(profile)
    avatar_col, account_col = st.columns([1, 3], gap="large")
    with avatar_col:
        if avatar_path is not None:
            st.image(str(avatar_path), width=112)
        else:
            initial = profile["display_name"][:1].upper()
            st.markdown(
                f"<div class='profile-initial'>{initial}</div>",
                unsafe_allow_html=True,
            )
    with account_col:
        st.subheader(profile["display_name"])
        st.write(profile["email"])
        role_color = "#115E59" if profile["role"] == "admin" else "#0F766E"
        st.markdown(
            f"<span style='display:inline-block;padding:5px 10px;border-radius:999px;background:#CCFBF1;color:{role_color};font:700 12px Manrope,sans-serif;'>"
            f"{profile['role'].title()}</span>",
            unsafe_allow_html=True,
        )
        st.caption(f"Member since {profile['created_at'][:10]}")
        st.caption(f"{len(frame):,} transaction records in your private ledger")

    st.subheader("Update profile")
    with st.form("profile_update_form"):
        display_name = st.text_input("Display name", value=profile["display_name"], max_chars=80)
        submitted = st.form_submit_button("Save profile", type="primary")
    avatar = st.file_uploader(
        "Change profile picture",
        type=["png", "jpg", "jpeg", "webp"],
        key="profile_avatar_upload",
    )
    if submitted:
        try:
            update_user_profile(
                profile["user_id"],
                display_name,
                avatar.getvalue() if avatar is not None else None,
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state["profile_notice"] = "Profile updated."
            st.rerun()

    notice = st.session_state.pop("profile_notice", None)
    if notice:
        st.success(notice)

    st.divider()
    preferences = get_user_preferences(profile["user_id"])
    st.subheader("Financial Starting Capital")
    st.caption("Configure your opening liquid bank balance to reflect true available capital across the app.")
    with st.form("starting_balance_form"):
        initial_balance = st.number_input(
            "Starting / Opening Balance ($)",
            value=float(preferences.get("initial_balance", 0.0)),
            min_value=0.0,
            step=100.0,
            format="%.2f",
            help="Starting cash amount in your bank accounts before ledger transactions.",
        )
        balance_submitted = st.form_submit_button("Save starting balance", type="primary")
    if balance_submitted:
        try:
            save_user_preferences(profile["user_id"], initial_balance=initial_balance)
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Starting balance updated successfully.")
            st.rerun()

    st.divider()
    st.subheader("Change password")
    with st.form("change_password_form"):
        current_password = st.text_input("Current password", type="password", autocomplete="current-password")
        new_password = st.text_input("New password", type="password", autocomplete="new-password")
        confirm_password = st.text_input("Confirm new password", type="password", autocomplete="new-password")
        password_submitted = st.form_submit_button("Update password")
    if password_submitted:
        if new_password != confirm_password:
            st.error("The new passwords do not match.")
        else:
            try:
                change_user_password(profile["user_id"], current_password, new_password)
            except ValueError as error:
                st.error(str(error))
            else:
                st.success("Password updated. Use the new password the next time you sign in.")

    st.divider()
    st.subheader("Export my data")
    st.caption("Download your profile details, saved goals, preferences, and private transaction ledger.")
    try:
        archive = export_user_data(profile["user_id"])
    except ValueError as error:
        st.error(str(error))
    else:
        st.download_button(
            "Download my data",
            data=archive,
            file_name="finwise_my_data.zip",
            mime="application/zip",
            type="primary",
        )

    st.caption("Your account data remains local to this FinWise installation.")
