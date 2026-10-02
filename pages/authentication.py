"""Public landing, registration, and sign-in screens."""

import streamlit as st

from utils.auth import authenticate_user, register_user, update_user_profile, validate_profile_picture


def render_landing(on_authenticated, on_open_login, on_open_register) -> None:
    left_nav, right_nav = st.columns([3, 1])
    with left_nav:
        st.markdown(
            "<div class='brand-lockup'><span class='brand-mark'>F</span>FinWise <span>AI</span></div>",
            unsafe_allow_html=True,
        )
    with right_nav:
        st.button("Sign in", on_click=on_open_login, use_container_width=True)

    st.markdown(
        """
        <section class="landing-hero">
          <div class="hero-copy">
            <p class="eyebrow">PERSONAL FINANCE, MADE EXPLAINABLE</p>
            <h1>FinWise AI</h1>
            <h2>Make your next money decision with more context.</h2>
            <p class="hero-description">Bring your own transactions. Explore spending patterns, compare purchase-risk models, and plan budgets with algorithms you can inspect.</p>
          </div>
          <div class="hero-visual" aria-label="FinWise analysis flow">
            <div class="flow-label">YOUR PRIVATE WORKSPACE</div>
            <div class="flow-step"><span class="flow-index">01</span><strong>Transactions</strong><small>Your account, your ledger</small></div>
            <div class="flow-arrow">↓</div>
            <div class="flow-step flow-step-accent"><span class="flow-index">02</span><strong>Models &amp; algorithms</strong><small>K-Means · Logistic Regression · A*</small></div>
            <div class="flow-arrow">↓</div>
            <div class="flow-step"><span class="flow-index">03</span><strong>Traceable guidance</strong><small>Inputs, methods, and limits shown</small></div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    _, create_col, _ = st.columns([1, 1, 1])
    with create_col:
        st.button("Create your account", type="primary", on_click=on_open_register, use_container_width=True)

    st.markdown("<div class='section-rule'></div>", unsafe_allow_html=True)
    feature_cols = st.columns(3, gap="large")
    features = [
        ("01 / Understand", "A live dashboard and preprocessing view follow the transactions in your own ledger."),
        ("02 / Explore", "Compare supervised purchase-risk demos with unsupervised spending clusters."),
        ("03 / Plan", "Search budget allocations and savings paths, then inspect why each result was selected."),
    ]
    for column, (label, description) in zip(feature_cols, features):
        with column:
            st.markdown(
                f"<div class='feature-card'><p class='feature-index'>{label}</p>"
                f"<p class='feature-copy'>{description}</p></div>",
                unsafe_allow_html=True,
            )
    st.caption("Accounts are isolated locally. Purchase classifiers use labeled synthetic/demo examples and are not financial advice.")


def render_login(on_authenticated, on_open_register, on_open_home) -> None:
    _render_auth_header("Welcome back", "Sign in to your private FinWise workspace.", on_open_home)
    form_col, detail_col = st.columns([1.2, 0.8], gap="large")
    with form_col:
        with st.form("finwise_login_form"):
            email = st.text_input("Email address", autocomplete="email")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            try:
                profile = authenticate_user(email, password)
            except ValueError as error:
                st.error(str(error))
            else:
                if profile is None:
                    st.error("Email or password was not recognized.")
                else:
                    on_authenticated(profile)
    with detail_col:
        st.markdown(
            "<div class='auth-note'><p class='eyebrow'>YOUR WORKSPACE</p><h3>Private by account</h3>"
            "<p>Your profile and transaction file are stored separately from other local accounts.</p></div>",
            unsafe_allow_html=True,
        )
        st.button("New to FinWise? Create account", on_click=on_open_register, use_container_width=True)


def render_register(on_authenticated, on_open_login, on_open_home) -> None:
    _render_auth_header("Create your account", "Set up a profile and a private transaction workspace.", on_open_home)
    form_col, detail_col = st.columns([1.2, 0.8], gap="large")
    with form_col:
        with st.form("finwise_register_form"):
            display_name = st.text_input("Name", max_chars=80, autocomplete="name")
            email = st.text_input("Email address", autocomplete="email")
            password = st.text_input("Password", type="password", autocomplete="new-password")
            password_confirmation = st.text_input("Confirm password", type="password", autocomplete="new-password")
            submitted = st.form_submit_button("Create account", type="primary", use_container_width=True)
        avatar = st.file_uploader("Profile picture (optional)", type=["png", "jpg", "jpeg", "webp"], key="register_avatar")
        if submitted:
            if password != password_confirmation:
                st.error("The passwords do not match.")
                return
            try:
                avatar_bytes = avatar.getvalue() if avatar is not None else None
                if avatar_bytes is not None:
                    validate_profile_picture(avatar_bytes)
                profile = register_user(email, display_name, password)
                if avatar_bytes is not None:
                    profile = update_user_profile(profile["user_id"], display_name, avatar_bytes)
            except ValueError as error:
                st.error(str(error))
            else:
                on_authenticated(profile)
    with detail_col:
        st.markdown(
            "<div class='auth-note'><p class='eyebrow'>START WITH YOUR DATA</p><h3>An empty account is intentional.</h3>"
            "<p>Import your own CSV after sign-up, or choose the clearly labeled demo ledger to explore the algorithms.</p></div>",
            unsafe_allow_html=True,
        )
        st.button("Already have an account? Sign in", on_click=on_open_login, use_container_width=True)
        st.caption("Passwords are stored as salted PBKDF2 hashes. Profile images are resized and stored locally.")


def _render_auth_header(title: str, subtitle: str, on_open_home) -> None:
    nav_col, _ = st.columns([1, 3])
    with nav_col:
        st.button("← FinWise AI", on_click=on_open_home)
    st.markdown(f"<p class='eyebrow'>ACCOUNT ACCESS</p><h1 class='auth-title'>{title}</h1>", unsafe_allow_html=True)
    st.caption(subtitle)
