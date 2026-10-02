"""FinWise AI Streamlit application entry point."""

import streamlit as st

from pages import (
	admin,
	authentication,
	budget_optimizer,
	dashboard,
	data_processing,
	goal_planner,
	integrated_guidance,
	model_evaluation,
	profile,
	purchase_advisor,
	rule_advisor,
	settings,
	spending_analysis,
	transactions,
)
from utils.auth import get_user_by_id, user_avatar_path, user_transactions_path
from utils.data_loader import load_transactions


st.set_page_config(
	page_title="FinWise AI | Personal Finance",
	page_icon="F",
	layout="wide",
	initial_sidebar_state="expanded",
)

NAVIGATION = {
	"Dashboard": dashboard,
	"Your Money Snapshot": integrated_guidance,
	"Income & Expenses": transactions,
	"Clean My Data": data_processing,
	"Spending Insights": spending_analysis,
	"Should I Buy This?": purchase_advisor,
	"Smart Budget Helper": budget_optimizer,
	"Money Rules": rule_advisor,
	"Goal Pathfinder": goal_planner,
	"Settings": settings,
	"My Profile": profile,
}


def add_global_styles() -> None:
	st.markdown(
		"""
		<style>
		@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');

		:root {
			--primary: #0F766E;
			--primary-dark: #115E59;
			--primary-light: #CCFBF1;
			--background: #F0FDFA;
			--card: #FFFFFF;
			--border: #E2E8F0;
			--ink: #134E4A;
			--muted: #64748B;
			--success: #10B981;
			--warning: #F59E0B;
			--danger: #F87171;
			--accent: #2DD4BF;
		}
		html, body, [class*="css"] {
			font-family: 'DM Sans', sans-serif;
			color: var(--ink);
		}
		.stApp { background: var(--background); }
		.stApp h1, .stApp h2, .stApp h3, .stApp [data-testid="stMarkdownContainer"] { color: var(--ink) !important; }
		.stApp .landing-hero h1, .stApp .landing-hero h2 { color: #FFFFFF !important; }
		.stApp .landing-hero p.hero-description { color: #E6FFFA !important; }
		.stApp [data-testid="stCaptionContainer"] p { color: var(--muted) !important; }
		[data-testid="stHeader"] { background: transparent; }
		[data-testid="stSidebar"] {
			background: #FFFFFF;
			border-right: 1px solid var(--border);
		}
		[data-testid="stSidebar"] > div:first-child { padding-top: 1rem; }
		[data-testid="stSidebar"] a { border-radius: 8px; color: var(--ink) !important; }
		[data-testid="stSidebar"] a:hover { background: var(--primary-light); }
		[data-testid="stSidebar"] [aria-current="page"] { background: #E6FFFA; color: var(--primary-dark) !important; font-weight: 700; }
		[data-testid="stMetric"] {
			background: var(--card);
			border: 1px solid var(--border);
			border-radius: 12px;
			padding: 1.1rem;
			min-height: 124px;
			box-shadow: 0 5px 18px rgba(19, 78, 74, 0.045);
		}
		[data-testid="stMetricLabel"] p {
			color: var(--muted);
			font-size: 0.82rem;
			font-weight: 600;
		}
		[data-testid="stMetricValue"] {
			font-family: 'Manrope', sans-serif;
			color: var(--ink);
			font-size: 1.4rem;
		}
		h1, h2, h3 { font-family: 'Manrope', sans-serif; letter-spacing: 0; }
		h1 { font-size: 2rem; }
		[data-testid="stButton"] button { border-radius: 9px; font-weight: 650; border-color: var(--border); }
		[data-testid="stButton"] button[kind="primary"] { background: var(--primary); border-color: var(--primary); color: white; box-shadow: 0 6px 14px rgba(15, 118, 110, 0.16); }
		[data-testid="stButton"] button[kind="primary"]:hover { background: var(--primary-dark); border-color: var(--primary-dark); }
		.brand-lockup { display:flex; align-items:center; gap:9px; font:800 18px Manrope,sans-serif; color:var(--ink); }
		.brand-lockup > span:last-child { color:var(--primary); }
		.brand-mark { width:34px; height:34px; display:grid; place-items:center; border-radius:10px; color:white; background:var(--primary-dark); }
		.landing-hero { display:grid; grid-template-columns:1.1fr .9fr; gap:52px; align-items:center; padding:54px 5vw 52px; margin:26px 0 20px; color:white; border:1px solid rgba(255,255,255,.32); border-radius:14px; background-image:linear-gradient(108deg, rgba(17,94,89,.97) 0%, rgba(15,118,110,.92) 57%, rgba(45,212,191,.78) 100%), repeating-linear-gradient(135deg, rgba(255,255,255,.10) 0 1px, transparent 1px 24px); box-shadow:0 20px 50px rgba(17,94,89,.17); }
		.hero-copy { max-width:650px; }
		.eyebrow, .flow-label { color:var(--accent); font:700 11px 'DM Sans',sans-serif; letter-spacing:1.1px; }
		.landing-hero h1 { color:white; font:800 52px/1.05 Manrope,sans-serif; margin:10px 0 14px; }
		.landing-hero h2 { color:white; font:700 27px/1.2 Manrope,sans-serif; max-width:520px; margin:0 0 14px; }
		.hero-description { color:#E6FFFA; font-size:16px; line-height:1.65; max-width:560px; }
		.hero-visual { max-width:500px; width:100%; justify-self:end; padding:18px 24px; border:1px solid rgba(255,255,255,.38); border-radius:12px; background:rgba(255,255,255,.12); box-shadow:inset 0 1px 0 rgba(255,255,255,.25); backdrop-filter:blur(10px); }
		.flow-label { margin-bottom:13px; color:#CCFBF1; }
		.flow-step { display:grid; grid-template-columns:38px 1fr; column-gap:12px; padding:12px 0; border-bottom:1px solid rgba(255,255,255,.2); }
		.flow-index { grid-row:span 2; color:#FDE68A; font:800 14px Manrope,sans-serif; }
		.flow-step strong { color:white; font:700 16px Manrope,sans-serif; }
		.flow-step small { color:#CCFBF1; font-size:12px; }
		.flow-step-accent strong { color:white; }
		.flow-arrow { color:#99F6E4; padding:3px 0 3px 48px; }
		.section-rule { border-top:1px solid var(--border); margin:24px 0; }
		.feature-card { min-height:142px; padding:20px; border:1px solid var(--border); border-radius:12px; background:var(--card); box-shadow:0 10px 24px rgba(19,78,74,.055); }
		.feature-index { color:var(--primary) !important; font:700 12px Manrope,sans-serif; }
		.feature-copy { color:var(--muted) !important; line-height:1.55; max-width:340px; }
		.auth-title { margin:8px 0 4px; }
		.auth-note { border-left:3px solid var(--accent); border-radius:0 12px 12px 0; padding:18px 22px; background:var(--primary-light); line-height:1.6; }
		.auth-note h3 { margin:8px 0; }
		.profile-initial { width:112px; height:112px; display:grid; place-items:center; border-radius:50%; color:#fff; background:var(--primary-dark); font:800 42px Manrope,sans-serif; }
		.user-name { font:700 14px Manrope,sans-serif; color:var(--ink); }
		.user-email { font-size:11px; color:var(--muted); overflow-wrap:anywhere; }
		div[data-testid="stPlotlyChart"] {
			background: var(--card);
			border: 1px solid var(--border);
			border-radius: 12px;
			padding: 0.45rem;
			box-shadow: 0 8px 22px rgba(19,78,74,.045);
		}
		@media (max-width: 720px) {
			.landing-hero { grid-template-columns:1fr; gap:24px; padding:32px 6vw; border-radius:12px; }
			.landing-hero h1 { font-size:40px; }
			.landing-hero h2 { font-size:23px; }
			.hero-visual { justify-self:stretch; padding:16px; }
			.feature-card { min-height:0; }
			[data-testid="stMetric"] { min-height:108px; padding:0.8rem; }
			[data-testid="stMetricValue"] { font-size:1.15rem; }
			h1 { font-size:1.65rem; }
		}
		</style>
		""",
		unsafe_allow_html=True,
	)


def main() -> None:
	add_global_styles()
	app_page = st.Page(_route_app, title="FinWise AI", url_path="home", default=True)
	st.navigation([app_page], position="hidden").run()


def _route_app() -> None:
	user_id = st.session_state.get("user_id")
	active_user_id = st.session_state.get("_active_user_id")
	if user_id != active_user_id:
		st.session_state.clear()
		if user_id:
			st.session_state["user_id"] = user_id
			st.session_state["_active_user_id"] = user_id
	user = get_user_by_id(user_id) if user_id else None
	if user is None:
		st.session_state.pop("user_id", None)
		st.session_state.pop("user_role", None)
		_render_public_app()
		return
	st.session_state["user_role"] = user["role"]

	try:
		store_path = user_transactions_path(user["user_id"])
		frame = load_transactions(store_path)
	except (OSError, ValueError) as error:
		st.error(f"Could not load this account's transaction ledger: {error}")
		st.stop()

	with st.sidebar:
		st.markdown(
			"<div class='brand-lockup'><span class='brand-mark'>F</span>FinWise <span>AI</span></div>",
			unsafe_allow_html=True,
		)
		st.divider()
		avatar = user_avatar_path(user)
		if avatar is not None:
			st.image(str(avatar), width=52)
		else:
			st.markdown(
				f"<div class='profile-initial' style='width:52px;height:52px;font-size:20px;'>{user['display_name'][:1].upper()}</div>",
				unsafe_allow_html=True,
			)
		st.markdown(
			f"<div class='user-name'>{user['display_name']}</div><div class='user-email'>{user['email']}</div>",
			unsafe_allow_html=True,
		)
		st.divider()
		selected_page = st.radio(
			"Your workspace",
			options=list(NAVIGATION),
			label_visibility="collapsed",
			key="finwise_workspace_page",
		)
		if user.get("role") == "admin":
			st.markdown(
				"<div style='font:700 11px Manrope,sans-serif;color:#64748B;padding:8px 0 4px;'>ADMINISTRATION</div>",
				unsafe_allow_html=True,
			)
			admin_page = st.radio(
				"Admin tools",
				options=["Admin Console", "How Accurate Are the Tools?"],
				label_visibility="collapsed",
				key="finwise_admin_page",
			)
			if admin_page in {"Admin Console", "How Accurate Are the Tools?"}:
				selected_page = admin_page
		st.divider()
		if st.button("Sign out", use_container_width=True):
			for key in list(st.session_state.keys()):
				del st.session_state[key]
			st.rerun()

	if selected_page == "Admin Console":
		admin.render(user, frame, store_path)
	elif selected_page == "How Accurate Are the Tools?":
		if user.get("role") == "admin":
			model_evaluation.render(frame)
		else:
			st.error("Administrator access is required for model evaluation.")
	elif selected_page == "Income & Expenses":
		NAVIGATION[selected_page].render(frame, store_path)
	elif selected_page == "Dashboard":
		NAVIGATION[selected_page].render(frame, store_path)
	else:
		NAVIGATION[selected_page].render(frame)


def _render_public_app() -> None:
	def authenticate(profile_data: dict) -> None:
		st.session_state["user_id"] = profile_data["user_id"]
		user_transactions_path(profile_data["user_id"])
		st.rerun()

	def open_login() -> None:
		st.session_state["auth_view"] = "login"

	def open_register() -> None:
		st.session_state["auth_view"] = "register"

	def open_landing() -> None:
		st.session_state["auth_view"] = "welcome"

	auth_view = st.session_state.get("auth_view", "welcome")
	if auth_view == "login":
		authentication.render_login(authenticate, open_register, open_landing)
	elif auth_view == "register":
		authentication.render_register(authenticate, open_login, open_landing)
	else:
		authentication.render_landing(authenticate, open_login, open_register)


if __name__ == "__main__":
	main()
