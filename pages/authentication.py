"""Public landing, registration, and sign-in screens."""

import textwrap

import streamlit as st

from utils.auth import authenticate_user, register_user, update_user_profile, validate_profile_picture


def render_landing(on_authenticated, on_open_login, on_open_register) -> None:
    # Query parameter handling for instant navigation
    query_auth = st.query_params.get("auth")
    if query_auth == "login":
        on_open_login()
        st.rerun()
    elif query_auth == "register":
        on_open_register()
        st.rerun()

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400..700;1,9..40,400..700&family=Manrope:wght@500;600;700;800&display=swap');

        /* Hide native Streamlit chrome and force 100% full bleed */
        header[data-testid="stHeader"] {
            display: none !important;
        }
        footer[data-testid="stFooter"] {
            display: none !important;
        }
        #MainMenu {
            visibility: hidden !important;
        }
        .stAppDeployButton {
            display: none !important;
        }
        .stApp {
            background-color: #0C1017 !important;
        }
        .stApp [data-testid="stAppViewContainer"] {
            background-color: #0C1017 !important;
        }
        .stApp [data-testid="stMain"] {
            padding: 0 !important;
            margin: 0 !important;
        }
        .stApp .block-container,
        .stApp [data-testid="stMain"] .block-container,
        .stApp .stMainBlockContainer {
            max-width: 100% !important;
            padding-top: 0 !important;
            padding-right: 0 !important;
            padding-bottom: 0 !important;
            padding-left: 0 !important;
            margin: 0 !important;
        }
        .stApp [data-testid="stVerticalBlock"] {
            gap: 0 !important;
        }
        .stApp [data-testid="stElementContainer"] {
            margin: 0 !important;
            padding: 0 !important;
        }

        /* Top Navigation Bar */
        .fw-nav {
            background: #FFFFFF;
            border-bottom: 1px solid #E2E8F0;
            width: 100%;
            padding: 14px 0;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .fw-nav-inner {
            max-width: 1140px;
            margin: 0 auto;
            padding: 0 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .fw-brand {
            display: flex;
            align-items: center;
            gap: 10px;
            text-decoration: none;
        }
        .fw-brand-icon {
            width: 32px;
            height: 32px;
            background: #0F766E;
            border-radius: 8px;
            color: #FFFFFF !important;
            font-family: 'Manrope', sans-serif;
            font-weight: 800;
            font-size: 16px;
            display: grid;
            place-items: center;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-brand-name,
        .fw-brand-name {
            font-family: 'Manrope', sans-serif !important;
            font-weight: 800 !important;
            font-size: 18px !important;
            color: #0F172A !important;
            letter-spacing: -0.2px !important;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-brand-name span,
        .fw-brand-name span {
            color: #0D9488 !important;
        }
        .fw-nav-actions {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .fw-btn-deploy {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 999px !important;
            color: #475569 !important;
            font-family: 'DM Sans', sans-serif !important;
            font-weight: 500 !important;
            font-size: 13px !important;
            padding: 6px 18px !important;
            text-decoration: none !important;
            transition: all 0.15s ease;
        }
        .fw-btn-deploy:hover {
            background: #F8FAFC !important;
            border-color: #CBD5E1 !important;
            color: #1E293B !important;
        }
        .fw-btn-signin {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #0F766E !important;
            border: none !important;
            border-radius: 999px !important;
            color: #FFFFFF !important;
            font-family: 'DM Sans', sans-serif !important;
            font-weight: 600 !important;
            font-size: 13px !important;
            padding: 7px 22px !important;
            text-decoration: none !important;
            transition: background 0.15s ease;
        }
        .fw-btn-signin:hover {
            background: #115E59 !important;
            color: #FFFFFF !important;
        }
        .fw-btn-dots {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 999px !important;
            color: #64748B !important;
            width: 34px !important;
            height: 34px !important;
            padding: 0 !important;
            cursor: pointer;
        }

        /* Hero Section */
        .fw-hero {
            background-color: #0C1017;
            width: 100%;
            padding: 64px 0 76px;
        }
        .fw-hero-inner {
            max-width: 1140px;
            margin: 0 auto;
            padding: 0 24px;
            display: grid;
            grid-template-columns: 1.15fr 0.85fr;
            gap: 48px;
            align-items: center;
        }
        .fw-hero-left {
            max-width: 520px;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-eyebrow,
        .fw-eyebrow {
            color: #14B8A6 !important;
            font-family: 'DM Sans', sans-serif !important;
            font-weight: 700 !important;
            font-size: 11px !important;
            letter-spacing: 1.2px !important;
            text-transform: uppercase !important;
            margin-bottom: 16px !important;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-hero-title,
        .stApp h1.fw-hero-title,
        h1.fw-hero-title {
            color: #0D9488 !important;
            font-family: 'Manrope', sans-serif !important;
            font-weight: 800 !important;
            font-size: 52px !important;
            line-height: 1.05 !important;
            margin: 0 0 16px 0 !important;
            letter-spacing: -0.5px !important;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-hero-subtitle,
        .stApp h2.fw-hero-subtitle,
        h2.fw-hero-subtitle {
            color: #FFFFFF !important;
            font-family: 'Manrope', sans-serif !important;
            font-weight: 700 !important;
            font-size: 28px !important;
            line-height: 1.22 !important;
            margin: 0 0 18px 0 !important;
            max-width: 460px !important;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-hero-desc,
        .stApp p.fw-hero-desc,
        p.fw-hero-desc {
            color: #94A3B8 !important;
            font-family: 'DM Sans', sans-serif !important;
            font-weight: 400 !important;
            font-size: 15px !important;
            line-height: 1.6 !important;
            margin: 0 0 28px 0 !important;
            max-width: 450px !important;
        }
        .fw-btn-create {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background-color: #0F766E !important;
            color: #FFFFFF !important;
            font-family: 'DM Sans', sans-serif !important;
            font-weight: 600 !important;
            font-size: 14px !important;
            padding: 11px 24px !important;
            border-radius: 8px !important;
            text-decoration: none !important;
            box-shadow: 0 4px 14px rgba(15, 118, 110, 0.25) !important;
            transition: background-color 0.15s ease, transform 0.1s ease;
        }
        .fw-btn-create:hover {
            background-color: #115E59 !important;
            color: #FFFFFF !important;
            transform: translateY(-1px);
        }

        /* White Workspace Flow Card */
        .fw-card-white {
            background: #FFFFFF !important;
            border-radius: 18px !important;
            padding: 34px 38px !important;
            box-shadow: 0 20px 45px rgba(0, 0, 0, 0.25) !important;
            max-width: 440px !important;
            margin-left: auto !important;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-card-eyebrow,
        .fw-card-eyebrow {
            color: #0F766E !important;
            font-family: 'DM Sans', sans-serif !important;
            font-weight: 700 !important;
            font-size: 11px !important;
            letter-spacing: 1.1px !important;
            text-transform: uppercase !important;
            margin-bottom: 4px !important;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-card-tagline,
        .fw-card-tagline {
            color: #64748B !important;
            font-family: 'DM Sans', sans-serif !important;
            font-size: 13px !important;
            margin-bottom: 24px !important;
        }
        .fw-flow-list {
            display: flex;
            flex-direction: column;
        }
        .fw-flow-item {
            display: flex;
            align-items: flex-start;
            gap: 16px;
            padding: 4px 0;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-flow-num,
        .fw-flow-num {
            color: #0F766E !important;
            font-family: 'Manrope', sans-serif !important;
            font-weight: 800 !important;
            font-size: 16px !important;
            min-width: 22px !important;
            line-height: 1.2 !important;
        }
        .fw-flow-text {
            display: flex;
            flex-direction: column;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-flow-text strong,
        .fw-flow-text strong {
            color: #0F172A !important;
            font-family: 'Manrope', sans-serif !important;
            font-weight: 700 !important;
            font-size: 15px !important;
            line-height: 1.25 !important;
            margin-bottom: 2px !important;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-flow-text small,
        .fw-flow-text small {
            color: #64748B !important;
            font-family: 'DM Sans', sans-serif !important;
            font-size: 12px !important;
            line-height: 1.35 !important;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-flow-arrow,
        .fw-flow-arrow {
            color: #0D9488 !important;
            font-size: 14px !important;
            font-weight: 700 !important;
            text-align: left !important;
            padding-left: 130px !important;
            margin: 10px 0 !important;
            display: block !important;
        }

        /* Feature Cards Section */
        .fw-features {
            background-color: #FFFFFF !important;
            width: 100% !important;
            padding: 48px 0 54px !important;
        }
        .fw-features-inner {
            max-width: 1140px !important;
            margin: 0 auto !important;
            padding: 0 24px !important;
            display: grid !important;
            grid-template-columns: repeat(3, 1fr) !important;
            gap: 24px !important;
        }
        .fw-feature-card {
            background: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 12px !important;
            padding: 24px 28px !important;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.03) !important;
            min-height: 124px !important;
            transition: transform 0.15s ease, box-shadow 0.15s ease !important;
        }
        .fw-feature-card:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06) !important;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-feature-num,
        .fw-feature-num {
            color: #0D9488 !important;
            font-family: 'Manrope', sans-serif !important;
            font-weight: 700 !important;
            font-size: 13px !important;
            margin-bottom: 8px !important;
        }
        .stApp [data-testid="stMarkdownContainer"] .fw-feature-body,
        .fw-feature-body {
            color: #475569 !important;
            font-family: 'DM Sans', sans-serif !important;
            font-size: 14px !important;
            line-height: 1.5 !important;
        }

        /* Footer Section */
        .fw-footer {
            background-color: #0C1017 !important;
            width: 100% !important;
            padding: 36px 0 44px !important;
            border-top: 1px solid rgba(255, 255, 255, 0.05) !important;
            display: block !important;
            box-sizing: border-box !important;
        }
        .fw-footer-inner {
            max-width: 1140px !important;
            margin: 0 auto !important;
            padding: 0 24px !important;
            color: #64748B !important;
            font-family: 'DM Sans', sans-serif !important;
            font-size: 12px !important;
            text-align: center !important;
            line-height: 1.5 !important;
        }

        @media (max-width: 768px) {
            .fw-hero-inner {
                grid-template-columns: 1fr;
                gap: 32px;
            }
            .fw-features-inner {
                grid-template-columns: 1fr;
            }
            .fw-hero-title {
                font-size: 38px !important;
            }
            .fw-hero-subtitle {
                font-size: 22px !important;
            }
            .fw-card-white {
                margin-left: 0;
            }
        }
        </style>

        <nav class="fw-nav">
          <div class="fw-nav-inner">
            <div class="fw-brand">
              <div class="fw-brand-icon">F</div>
              <div class="fw-brand-name">FinWise <span>AI</span></div>
            </div>
            <div class="fw-nav-actions">
              <a href="#" class="fw-btn-deploy">Deploy</a>
              <a href="?auth=login" class="fw-btn-signin" target="_self">Sign in</a>
              <button class="fw-btn-dots" aria-label="Menu">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                  <circle cx="8" cy="3" r="1.5"/>
                  <circle cx="8" cy="8" r="1.5"/>
                  <circle cx="8" cy="13" r="1.5"/>
                </svg>
              </button>
            </div>
          </div>
        </nav>

        <section class="fw-hero">
          <div class="fw-hero-inner">
            <div class="fw-hero-left">
              <div class="fw-eyebrow">PERSONAL FINANCE, MADE EXPLAINABLE</div>
              <h1 class="fw-hero-title">FinWise AI</h1>
              <h2 class="fw-hero-subtitle">Make your next money decision with more context.</h2>
              <p class="fw-hero-desc">Bring your own transactions. Explore spending patterns, compare purchase-risk models, and plan budgets with algorithms you can inspect.</p>
              <a href="?auth=register" class="fw-btn-create" target="_self">Create your account</a>
            </div>
            <div class="fw-hero-right">
              <div class="fw-card-white">
                <div class="fw-card-eyebrow">YOUR PRIVATE WORKSPACE</div>
                <div class="fw-card-tagline">A guided flow from transactions to explainable guidance.</div>
                <div class="fw-flow-list">
                  <div class="fw-flow-item">
                    <span class="fw-flow-num">01</span>
                    <div class="fw-flow-text">
                      <strong>Transactions</strong>
                      <small>Your account, your ledger</small>
                    </div>
                  </div>
                  <div class="fw-flow-arrow">↓</div>
                  <div class="fw-flow-item">
                    <span class="fw-flow-num">02</span>
                    <div class="fw-flow-text">
                      <strong>Models &amp; algorithms</strong>
                      <small>K-Means · Logistic Regression · A*</small>
                    </div>
                  </div>
                  <div class="fw-flow-arrow">↓</div>
                  <div class="fw-flow-item">
                    <span class="fw-flow-num">03</span>
                    <div class="fw-flow-text">
                      <strong>Traceable guidance</strong>
                      <small>Inputs, methods, and limits shown</small>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="fw-features">
          <div class="fw-features-inner">
            <div class="fw-feature-card">
              <div class="fw-feature-num">01 / Understand</div>
              <div class="fw-feature-body">A live dashboard and preprocessing view follow the transactions in your own ledger.</div>
            </div>
            <div class="fw-feature-card">
              <div class="fw-feature-num">02 / Explore</div>
              <div class="fw-feature-body">Compare supervised purchase-risk demos with unsupervised spending clusters.</div>
            </div>
            <div class="fw-feature-card">
              <div class="fw-feature-num">03 / Plan</div>
              <div class="fw-feature-body">Search budget allocations and savings paths, then inspect why each result was selected.</div>
            </div>
          </div>
        </section>

        <footer class="fw-footer">
          <div class="fw-footer-inner">
            Accounts are isolated locally. Purchase classifiers use labeled synthetic/demo examples and are not financial advice.
          </div>
        </footer>
        """,
        unsafe_allow_html=True,
    )


def render_login(on_authenticated, on_open_register, on_open_home) -> None:
    query_auth = st.query_params.get("auth")
    if query_auth == "register":
        on_open_register()
        st.rerun()
    elif query_auth == "welcome":
        on_open_home()
        st.rerun()

    st.markdown(
        textwrap.dedent(
            """<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400..700;1,9..40,400..700&family=Manrope:wght@500;600;700;800&display=swap');

/* Force clean white background and hide default Streamlit UI chrome */
header[data-testid="stHeader"] {
    display: none !important;
}
footer[data-testid="stFooter"] {
    display: none !important;
}
#MainMenu {
    visibility: hidden !important;
}
.stAppDeployButton {
    display: none !important;
}
.stApp {
    background-color: #FFFFFF !important;
}
.stApp [data-testid="stAppViewContainer"] {
    background-color: #FFFFFF !important;
}
.stApp .block-container,
.stApp [data-testid="stMain"] .block-container,
.stApp .stMainBlockContainer {
    max-width: 1240px !important;
    padding-top: 24px !important;
    padding-bottom: 24px !important;
    padding-left: 48px !important;
    padding-right: 48px !important;
    margin: 0 auto !important;
}

/* Outer two-column layout */
.stApp .block-container > div[data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] {
    align-items: stretch !important;
    gap: 56px !important;
}

/* Form styling */
div[data-testid="stForm"] {
    border: none !important;
    padding: 0 !important;
    background: transparent !important;
}

/* Form Labels */
.stApp [data-testid="stTextInput"] label p {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    color: #1E293B !important;
    margin-bottom: 4px !important;
}

/* Form Inputs */
.stApp [data-testid="stTextInput"] input {
    border-radius: 8px !important;
    border: 1px solid #E2E8F0 !important;
    height: 48px !important;
    font-size: 14.5px !important;
    font-family: 'DM Sans', sans-serif !important;
    color: #0F172A !important;
    background-color: #FFFFFF !important;
    padding: 0 14px !important;
    box-shadow: none !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}
.stApp [data-testid="stTextInput"] input:focus {
    border-color: #0F766E !important;
    box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12) !important;
}

/* Checkbox & Options Row Inside Form */
div[data-testid="stForm"] [data-testid="stHorizontalBlock"] {
    align-items: center !important;
    gap: 12px !important;
    margin-top: 2px !important;
    margin-bottom: 6px !important;
}
div[data-testid="stForm"] [data-testid="stHorizontalBlock"] [data-testid="column"] {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
}
div[data-testid="stForm"] [data-testid="stHorizontalBlock"] [data-testid="column"]:last-child {
    justify-content: flex-end !important;
}
div[data-testid="stForm"] [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-end !important;
    width: 100% !important;
}
div[data-testid="stForm"] [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p {
    margin: 0 !important;
    line-height: normal !important;
}
.stApp div[data-testid="stCheckbox"] {
    margin: 0 !important;
    padding: 0 !important;
}
.stApp div[data-testid="stCheckbox"] > label {
    margin: 0 !important;
    padding: 0 !important;
    min-height: auto !important;
    display: flex !important;
    align-items: center !important;
}
.stApp div[data-testid="stCheckbox"] label p {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 13px !important;
    color: #475569 !important;
    font-weight: 500 !important;
    margin: 0 !important;
}
.fw-forgot-container {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    width: 100%;
}
.fw-forgot-link {
    color: #0F766E !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    text-decoration: none !important;
    white-space: nowrap !important;
}
.fw-forgot-link:hover {
    text-decoration: underline !important;
}

/* Form Submit Button */
.stApp [data-testid="stFormSubmitButton"] button {
    background: #EF4444 !important;
    background: linear-gradient(135deg, #F87171 0%, #EF4444 100%) !important;
    border: none !important;
    border-radius: 10px !important;
    color: #FFFFFF !important;
    height: 48px !important;
    box-shadow: 0 8px 24px rgba(239, 68, 68, 0.35) !important;
    margin-top: 16px !important;
    transition: all 0.15s ease !important;
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    padding-left: 20px !important;
    padding-right: 20px !important;
    box-sizing: border-box !important;
}
.stApp [data-testid="stFormSubmitButton"] button:hover {
    background: linear-gradient(135deg, #EF4444 0%, #DC2626 100%) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 10px 28px rgba(239, 68, 68, 0.42) !important;
}
.stApp [data-testid="stFormSubmitButton"] button p {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 15px !important;
    font-weight: 700 !important;
    color: #FFFFFF !important;
    margin: 0 !important;
}
.stApp [data-testid="stFormSubmitButton"] button::after {
    content: '→' !important;
    font-size: 18px !important;
    font-weight: 700 !important;
    color: #FFFFFF !important;
    display: inline-block !important;
    transition: transform 0.15s ease !important;
}
.stApp [data-testid="stFormSubmitButton"] button:hover::after {
    transform: translateX(3px) !important;
}

/* Brand Lockup */
.fw-login-brand {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    text-decoration: none !important;
    margin-bottom: 26px;
}
.fw-brand-icon-bars {
    width: 36px;
    height: 36px;
    background: #062820;
    border-radius: 9px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 3.5px;
    box-shadow: 0 4px 12px rgba(6, 40, 32, 0.15);
}
.fw-brand-icon-bars span {
    width: 3.5px;
    background: #34D399;
    border-radius: 2px;
    display: inline-block;
}
.stApp [data-testid="stMarkdownContainer"] .fw-brand-text,
.fw-brand-text {
    font-family: 'Manrope', sans-serif !important;
    font-weight: 800 !important;
    font-size: 19px !important;
    color: #0F172A !important;
    letter-spacing: -0.3px !important;
}

/* Left Column Text */
.stApp [data-testid="stMarkdownContainer"] .fw-login-eyebrow,
.fw-login-eyebrow {
    color: #0F766E !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 700 !important;
    font-size: 11px !important;
    letter-spacing: 1.2px !important;
    text-transform: uppercase !important;
    margin-bottom: 8px !important;
}
.stApp [data-testid="stMarkdownContainer"] .fw-login-title,
.fw-login-title {
    font-family: 'Manrope', sans-serif !important;
    font-weight: 800 !important;
    font-size: 40px !important;
    letter-spacing: -1px !important;
    color: #0A251E !important;
    line-height: 1.1 !important;
    margin: 0 0 8px 0 !important;
}
.stApp [data-testid="stMarkdownContainer"] .fw-login-subtitle,
.fw-login-subtitle {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 14.5px !important;
    color: #64748B !important;
    margin: 0 0 20px 0 !important;
    line-height: 1.5 !important;
}

/* Switch & Legal Footer */
.fw-login-switch {
    font-family: 'DM Sans', sans-serif;
    font-size: 14px;
    color: #64748B;
    text-align: center;
    margin-top: 18px;
    margin-bottom: 22px;
}
.fw-login-switch a {
    color: #0A251E !important;
    font-weight: 700 !important;
    text-decoration: none !important;
}
.fw-login-switch a:hover {
    text-decoration: underline !important;
}
.fw-login-legal-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: 'DM Sans', sans-serif;
    font-size: 12px;
    color: #94A3B8;
    padding-top: 16px;
    border-top: 1px solid #F1F5F9;
}
.fw-legal-links {
    display: flex;
    gap: 18px;
}
.fw-legal-links a {
    color: #94A3B8 !important;
    text-decoration: none !important;
    font-size: 12px !important;
}
.fw-legal-links a:hover {
    color: #64748B !important;
}

/* Right Column (Mint Card Showcase) */
.fw-login-promo-card {
    background: linear-gradient(145deg, #BFF6E3 0%, #A4EED4 50%, #90E7C9 100%);
    border-radius: 36px;
    padding: 32px 38px 28px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: 590px;
    position: relative;
    overflow: hidden;
    box-sizing: border-box;
}
.fw-promo-glow-1 {
    position: absolute;
    right: -40px;
    top: -40px;
    width: 260px;
    height: 260px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(255, 255, 255, 0.45) 0%, transparent 70%);
    pointer-events: none;
}
.fw-promo-glow-2 {
    position: absolute;
    right: -80px;
    top: 160px;
    width: 300px;
    height: 300px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(52, 211, 153, 0.3) 0%, transparent 70%);
    pointer-events: none;
}
.fw-floating-balance-card {
    background: #FFFFFF;
    border-radius: 18px;
    padding: 18px 24px 22px;
    box-shadow: 0 24px 48px rgba(10, 60, 48, 0.12), 0 4px 12px rgba(0, 0, 0, 0.03);
    margin-bottom: 24px;
    position: relative;
    z-index: 2;
}
.fw-card-window-bar {
    display: flex;
    align-items: center;
    gap: 6px;
    padding-bottom: 12px;
    border-bottom: 1px solid #F1F5F9;
    margin-bottom: 16px;
}
.fw-window-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #94D3BE;
    display: inline-block;
}
.fw-card-window-content {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 20px;
}
.fw-card-skeleton-col {
    padding-top: 8px;
}
.fw-skeleton-bar-1 {
    width: 70px;
    height: 8px;
    background: #D1EAE2;
    border-radius: 4px;
    margin-bottom: 6px;
}
.fw-skeleton-bar-2 {
    width: 44px;
    height: 8px;
    background: #D1EAE2;
    border-radius: 4px;
}
.fw-card-balance-col {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
}
.fw-balance-label {
    color: #64748B;
    font-size: 11.5px;
    font-family: 'DM Sans', sans-serif;
    font-weight: 500;
    margin-bottom: 2px;
}
.fw-balance-amount {
    color: #0F172A;
    font-size: 28px;
    font-weight: 800;
    font-family: 'Manrope', sans-serif;
    letter-spacing: -0.5px;
    line-height: 1.1;
    margin-bottom: 16px;
}
.fw-balance-chart {
    display: flex;
    align-items: flex-end;
    gap: 7px;
    height: 68px;
}
.fw-chart-bar {
    width: 22px;
    background: #3B957B;
    border-radius: 4px;
}
.fw-promo-bottom-content {
    position: relative;
    z-index: 2;
}
.fw-promo-badge {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    background: rgba(255, 255, 255, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.7);
    border-radius: 999px;
    padding: 5px 14px;
    margin-bottom: 18px;
}
.fw-promo-badge span {
    font-family: 'DM Sans', sans-serif;
    font-weight: 800;
    font-size: 10.5px;
    letter-spacing: 1.2px;
    color: #0D5C4E;
}
.stApp [data-testid="stMarkdownContainer"] .fw-promo-quote,
.fw-promo-quote {
    font-family: 'Manrope', sans-serif !important;
    font-weight: 800 !important;
    font-size: 38px !important;
    line-height: 1.14 !important;
    letter-spacing: -0.8px !important;
    color: #082921 !important;
    margin: 0 0 14px 0 !important;
}
.stApp [data-testid="stMarkdownContainer"] .fw-promo-subtext,
.fw-promo-subtext {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 14.5px !important;
    line-height: 1.5 !important;
    color: #234E44 !important;
    margin: 0 0 28px 0 !important;
    max-width: 460px !important;
}
.fw-promo-footer {
    border-top: 1px solid rgba(13, 92, 78, 0.16);
    padding-top: 18px;
}
.fw-promo-footer span {
    font-family: 'DM Sans', sans-serif;
    font-weight: 700;
    font-size: 10.5px;
    letter-spacing: 1.2px;
    color: #1E4D43;
    text-transform: uppercase;
}

@media (max-width: 860px) {
    .stApp .block-container {
        padding-left: 20px !important;
        padding-right: 20px !important;
    }
    .fw-login-promo-card {
        margin-top: 32px;
        min-height: auto;
    }
    .fw-promo-quote {
        font-size: 28px !important;
    }
    .fw-login-title {
        font-size: 32px !important;
    }
}
</style>
<div class="fw-login-root"></div>
"""
        ),
        unsafe_allow_html=True,
    )

    form_col, promo_col = st.columns([1, 1.15], gap="large")

    with form_col:
        st.markdown(
            textwrap.dedent(
                """\
                <a href="?auth=welcome" target="_self" class="fw-login-brand">
                  <div class="fw-brand-icon-bars">
                    <span style="height: 10px;"></span>
                    <span style="height: 18px;"></span>
                    <span style="height: 14px;"></span>
                  </div>
                  <span class="fw-brand-text">FinWise</span>
                </a>
                <div class="fw-login-eyebrow">ACCOUNT ACCESS</div>
                <h1 class="fw-login-title">Welcome back</h1>
                <p class="fw-login-subtitle">Sign in to continue to your private financial workspace.</p>
                """
            ),
            unsafe_allow_html=True,
        )

        with st.form("finwise_login_form"):
            email = st.text_input("Email address", autocomplete="email")
            password = st.text_input("Password", type="password", autocomplete="current-password")

            opt_left, opt_right = st.columns([1.1, 1], vertical_alignment="center")
            with opt_left:
                st.checkbox("Keep me signed in", value=True, key="login_keep_signed_in")
            with opt_right:
                st.markdown(
                    textwrap.dedent(
                        """\
                        <div class="fw-forgot-container">
                          <a href="#" onclick="alert('Password recovery: FinWise accounts are isolated locally. If you need credentials reset, check your local user database or contact your workspace admin.'); return false;" class="fw-forgot-link">Forgot password?</a>
                        </div>
                        """
                    ),
                    unsafe_allow_html=True,
                )

            submitted = st.form_submit_button("Sign in securely", type="primary", use_container_width=True)

        if submitted:
            if not email or not password:
                st.error("Please enter both email and password.")
            else:
                try:
                    profile = authenticate_user(email, password)
                except ValueError as error:
                    st.error(f"🔒 {error}")
                else:
                    if profile is None:
                        st.error("Email or password was not recognized.")
                    else:
                        on_authenticated(profile)

        st.markdown(
            textwrap.dedent(
                """\
                <div class="fw-login-switch">
                  New to FinWise? <a href="?auth=register" target="_self">Create an account</a>
                </div>
                <div class="fw-login-legal-footer">
                  <span>© 2025 FinWise</span>
                  <div class="fw-legal-links">
                    <a href="#">Privacy</a>
                    <a href="#">Security</a>
                  </div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

    with promo_col:
        st.markdown(
            textwrap.dedent(
                """\
                <div class="fw-login-promo-card">
                  <div class="fw-promo-glow-1"></div>
                  <div class="fw-promo-glow-2"></div>
                  <div class="fw-floating-balance-card">
                    <div class="fw-card-window-bar">
                      <span class="fw-window-dot"></span>
                      <span class="fw-window-dot"></span>
                      <span class="fw-window-dot"></span>
                    </div>
                    <div class="fw-card-window-content">
                      <div class="fw-card-skeleton-col">
                        <div class="fw-skeleton-bar-1"></div>
                        <div class="fw-skeleton-bar-2"></div>
                      </div>
                      <div class="fw-card-balance-col">
                        <div class="fw-balance-label">Available balance</div>
                        <div class="fw-balance-amount">$24,860.40</div>
                        <div class="fw-balance-chart">
                          <div class="fw-chart-bar" style="height: 26px;"></div>
                          <div class="fw-chart-bar" style="height: 44px;"></div>
                          <div class="fw-chart-bar" style="height: 34px;"></div>
                          <div class="fw-chart-bar" style="height: 52px;"></div>
                          <div class="fw-chart-bar" style="height: 46px;"></div>
                          <div class="fw-chart-bar" style="height: 68px;"></div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="fw-promo-bottom-content">
                    <div class="fw-promo-badge">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0D5C4E" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                        <polyline points="9 12 11 14 15 10"/>
                      </svg>
                      <span>PRIVATE BY DESIGN</span>
                    </div>
                    <h2 class="fw-promo-quote">&ldquo;A calmer way to understand your money and plan what comes next.&rdquo;</h2>
                    <p class="fw-promo-subtext">Your profile and transactions stay securely separated from every other account.</p>
                    <div class="fw-promo-footer">
                      <span>BANK-LEVEL ENCRYPTION &nbsp;&bull;&nbsp; YOUR DATA, YOUR CONTROL</span>
                    </div>
                  </div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )



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
