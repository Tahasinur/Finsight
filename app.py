"""FinWise AI Streamlit application entry point."""

import importlib
from pathlib import Path
import textwrap
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
	"Overview": dashboard,
	"Transactions": transactions,
	"Spending insights": spending_analysis,
	"Goals": goal_planner,
	"FinWise AI": integrated_guidance,
	"Settings": settings,
	"My Profile": profile,
	# Legacy navigation keys for seamless backward compatibility:
	"Dashboard": dashboard,
	"Your Money Snapshot": integrated_guidance,
	"Income & Expenses": transactions,
	"Clean My Data": data_processing,
	"Spending Insights": spending_analysis,
	"Should I Buy This?": purchase_advisor,
	"Smart Budget Helper": budget_optimizer,
	"Money Rules": rule_advisor,
	"Goal Pathfinder": goal_planner,
}


def add_global_styles() -> None:
	st.markdown(
		textwrap.dedent(
			"""\
			<style>
			@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400..700;1,9..40,400..700&family=Manrope:wght@500;600;700;800&display=swap');

			:root {
				--primary: #0F766E;
				--primary-dark: #0D5C4E;
				--primary-light: #E6F7F2;
				--background: #F8FAFC;
				--card: #FFFFFF;
				--border: #E2E8F0;
				--ink: #0F172A;
				--muted: #64748B;
			}
			html, body, [class*="css"] {
				font-family: 'DM Sans', sans-serif;
				color: var(--ink);
			}
			.stApp { background: var(--background) !important; }
			[data-testid="stHeader"] { background: transparent; }
			
			/* Sidebar styling */
			[data-testid="stSidebar"] {
				background: #FFFFFF !important;
				border-right: 1px solid #F1F5F9 !important;
			}
			[data-testid="stSidebar"] > div:first-child {
				padding-top: 1.25rem !important;
				padding-left: 1.25rem !important;
				padding-right: 1.25rem !important;
			}
			[data-testid="stSidebarCollapseButton"] {
				display: none !important;
			}

			/* Sidebar Brand Lockup */
			.fw-sidebar-header {
				display: flex;
				justify-content: space-between;
				align-items: center;
				padding: 0 4px 18px 4px;
			}
			.fw-sidebar-brand {
				display: inline-flex;
				align-items: center;
				gap: 10px;
			}
			.fw-brand-icon-bars {
				width: 34px;
				height: 34px;
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
			.fw-brand-text {
				font-family: 'Manrope', sans-serif !important;
				font-weight: 800 !important;
				font-size: 19px !important;
				color: #0F172A !important;
				letter-spacing: -0.3px !important;
			}
			.fw-sidebar-close-btn {
				width: 32px;
				height: 32px;
				background: #FFFFFF;
				border: 1px solid #E2E8F0;
				border-radius: 8px;
				display: flex;
				align-items: center;
				justify-content: center;
				cursor: pointer;
				transition: all 0.15s ease;
			}
			.fw-sidebar-close-btn:hover {
				background: #F8FAFC;
			}
			.fw-sidebar-section-title {
				font-family: 'DM Sans', sans-serif;
				font-size: 11px;
				font-weight: 800;
				letter-spacing: 1.2px;
				color: #94A3B8;
				text-transform: uppercase;
				margin: 10px 0 8px 8px;
			}

			/* Custom Sidebar Navigation Radio */
			[data-testid="stSidebar"] div[data-testid="stRadio"] > label {
				display: none !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] {
				gap: 4px !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label {
				padding: 10px 14px !important;
				border-radius: 12px !important;
				margin-bottom: 2px !important;
				cursor: pointer !important;
				display: flex !important;
				align-items: center !important;
				transition: all 0.15s ease !important;
				background: transparent !important;
				width: 100% !important;
				box-sizing: border-box !important;
			}
			/* Hide ONLY the radio input and radio circle, never the label text */
			[data-testid="stSidebar"] div[data-testid="stRadio"] input {
				display: none !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label div[class*="e1mpz0hj4"],
			[data-testid="stSidebar"] div[data-testid="stRadio"] label input + div,
			[data-testid="stSidebar"] div[data-testid="stRadio"] label > div > div:first-child {
				display: none !important;
				width: 0 !important;
				height: 0 !important;
				margin: 0 !important;
				padding: 0 !important;
				border: none !important;
				overflow: hidden !important;
				visibility: hidden !important;
				opacity: 0 !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label div[class*="e1mpz0hj5"],
			[data-testid="stSidebar"] div[data-testid="stRadio"] label > div > div:last-child {
				display: flex !important;
				align-items: center !important;
				width: 100% !important;
				flex: 1 !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label [data-testid="stMarkdownContainer"] {
				display: block !important;
				width: 100% !important;
				visibility: visible !important;
				opacity: 1 !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label p {
				font-family: 'DM Sans', sans-serif !important;
				font-size: 14px !important;
				font-weight: 500 !important;
				color: #475569 !important;
				margin: 0 !important;
				display: flex !important;
				align-items: center !important;
				width: 100% !important;
				visibility: visible !important;
				opacity: 1 !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:hover {
				background: #F8FAFC !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:hover p {
				color: #0F172A !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input:checked) {
				background: #E6F7F2 !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input:checked) p {
				color: #0D5C4E !important;
				font-weight: 700 !important;
			}
			/* Hide native sidebar collapse button so custom brand lockup close button handles it */
			[data-testid="stSidebarCollapseButton"] {
				display: none !important;
			}

			/* Targeted Icon Injection for Each Navigation Item */
			/* 1. Overview */
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input[value="Overview"]) p::before,
			[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > div:nth-child(1) label p::before {
				content: '' !important;
				display: inline-block !important;
				width: 18px !important;
				height: 18px !important;
				min-width: 18px !important;
				margin-right: 12px !important;
				background-size: contain !important;
				background-repeat: no-repeat !important;
				background-position: center !important;
				background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23475569' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect width='7' height='7' x='3' y='3' rx='1'/%3E%3Crect width='7' height='7' x='14' y='3' rx='1'/%3E%3Crect width='7' height='7' x='14' y='14' rx='1'/%3E%3Crect width='7' height='7' x='3' y='14' rx='1'/%3E%3C/svg%3E") !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input[value="Overview"]):has(input:checked) p::before,
			[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > div:nth-child(1) label:has(input:checked) p::before {
				background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%230D5C4E' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect width='7' height='7' x='3' y='3' rx='1'/%3E%3Crect width='7' height='7' x='14' y='3' rx='1'/%3E%3Crect width='7' height='7' x='14' y='14' rx='1'/%3E%3Crect width='7' height='7' x='3' y='14' rx='1'/%3E%3C/svg%3E") !important;
			}

			/* 2. Transactions */
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input[value="Transactions"]) p::before,
			[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > div:nth-child(2) label p::before {
				content: '' !important;
				display: inline-block !important;
				width: 18px !important;
				height: 18px !important;
				min-width: 18px !important;
				margin-right: 12px !important;
				background-size: contain !important;
				background-repeat: no-repeat !important;
				background-position: center !important;
				background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23475569' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect width='20' height='14' x='2' y='5' rx='2'/%3E%3Cline x1='2' x2='22' y1='10' y2='10'/%3E%3C/svg%3E") !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input[value="Transactions"]):has(input:checked) p::before,
			[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > div:nth-child(2) label:has(input:checked) p::before {
				background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%230D5C4E' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect width='20' height='14' x='2' y='5' rx='2'/%3E%3Cline x1='2' x2='22' y1='10' y2='10'/%3E%3C/svg%3E") !important;
			}

			/* 3. Spending insights */
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input[value="Spending insights"]) p::before,
			[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > div:nth-child(3) label p::before {
				content: '' !important;
				display: inline-block !important;
				width: 18px !important;
				height: 18px !important;
				min-width: 18px !important;
				margin-right: 12px !important;
				background-size: contain !important;
				background-repeat: no-repeat !important;
				background-position: center !important;
				background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23475569' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='12' x2='12' y1='20' y2='10'/%3E%3Cline x1='18' x2='18' y1='20' y2='4'/%3E%3Cline x1='6' x2='6' y1='20' y2='16'/%3E%3C/svg%3E") !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input[value="Spending insights"]):has(input:checked) p::before,
			[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > div:nth-child(3) label:has(input:checked) p::before {
				background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%230D5C4E' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='12' x2='12' y1='20' y2='10'/%3E%3Cline x1='18' x2='18' y1='20' y2='4'/%3E%3Cline x1='6' x2='6' y1='20' y2='16'/%3E%3C/svg%3E") !important;
			}

			/* 4. Goals */
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input[value="Goals"]) p::before,
			[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > div:nth-child(4) label p::before {
				content: '' !important;
				display: inline-block !important;
				width: 18px !important;
				height: 18px !important;
				min-width: 18px !important;
				margin-right: 12px !important;
				background-size: contain !important;
				background-repeat: no-repeat !important;
				background-position: center !important;
				background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23475569' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='10'/%3E%3Ccircle cx='12' cy='12' r='6'/%3E%3Ccircle cx='12' cy='12' r='2'/%3E%3C/svg%3E") !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input[value="Goals"]):has(input:checked) p::before,
			[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > div:nth-child(4) label:has(input:checked) p::before {
				background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%230D5C4E' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='10'/%3E%3Ccircle cx='12' cy='12' r='6'/%3E%3Ccircle cx='12' cy='12' r='2'/%3E%3C/svg%3E") !important;
			}

			/* 5. FinWise AI */
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input[value="FinWise AI"]) p::before,
			[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > div:nth-child(5) label p::before {
				content: '' !important;
				display: inline-block !important;
				width: 18px !important;
				height: 18px !important;
				min-width: 18px !important;
				margin-right: 12px !important;
				background-size: contain !important;
				background-repeat: no-repeat !important;
				background-position: center !important;
				background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23475569' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z'/%3E%3C/svg%3E") !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input[value="FinWise AI"]):has(input:checked) p::before,
			[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > div:nth-child(5) label:has(input:checked) p::before {
				background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%230D5C4E' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z'/%3E%3C/svg%3E") !important;
			}
			[data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input[value="FinWise AI"]) p::after,
			[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > div:nth-child(5) label p::after {
				content: 'NEW' !important;
				font-size: 9px !important;
				font-weight: 800 !important;
				color: #0D5C4E !important;
				background: #D1FAE5 !important;
				padding: 2px 7px !important;
				border-radius: 999px !important;
				margin-left: auto !important;
				letter-spacing: 0.5px !important;
			}

			/* Sidebar Sign out Ghost Button */
			[data-testid="stSidebar"] div[data-testid="stButton"] button {
				background: transparent !important;
				border: 1px solid #F1F5F9 !important;
				color: #94A3B8 !important;
				font-size: 11.5px !important;
				font-weight: 600 !important;
				padding: 6px 12px !important;
				border-radius: 10px !important;
				transition: all 0.15s ease !important;
				box-shadow: none !important;
			}
			[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {
				background: #FEE2E2 !important;
				border-color: #FECACA !important;
				color: #EF4444 !important;
			}

			/* Sidebar Weekly Insight Card */
			.fw-sidebar-insight-card {
				background: #EBF9F4;
				border: 1px solid #D1F2E7;
				border-radius: 16px;
				padding: 16px;
				margin: 18px 0 12px 0;
			}
			.fw-insight-icon-bubble {
				width: 28px;
				height: 28px;
				background: rgba(255, 255, 255, 0.85);
				border-radius: 50%;
				display: flex;
				align-items: center;
				justify-content: center;
				margin-bottom: 8px;
			}
			.fw-insight-title {
				font-family: 'Manrope', sans-serif;
				font-size: 13.5px;
				font-weight: 800;
				color: #0A251E;
				margin-bottom: 3px;
			}
			.fw-insight-desc {
				font-family: 'DM Sans', sans-serif;
				font-size: 12px;
				color: #475569;
				line-height: 1.4;
				margin-bottom: 10px;
			}
			.fw-insight-link {
				font-family: 'DM Sans', sans-serif;
				font-size: 12px;
				font-weight: 700;
				color: #0D5C4E !important;
				text-decoration: none !important;
			}

			/* Sidebar Bottom Items */
			.fw-sidebar-bottom-item {
				display: flex;
				align-items: center;
				gap: 10px;
				padding: 9px 12px;
				border-radius: 12px;
				font-family: 'DM Sans', sans-serif;
				font-size: 13.5px;
				font-weight: 600;
				color: #475569 !important;
				text-decoration: none !important;
				margin-top: 14px;
				margin-bottom: 8px;
				transition: all 0.15s ease;
			}
			.fw-sidebar-bottom-item:hover {
				background: #F8FAFC;
				color: #0F172A !important;
			}
			.fw-sidebar-user-card {
				display: flex;
				align-items: center;
				gap: 10px;
				padding: 10px 12px;
				border-radius: 14px;
				text-decoration: none !important;
				background: transparent;
				transition: all 0.15s ease;
			}
			.fw-sidebar-user-card:hover {
				background: #F8FAFC;
			}
			.fw-sidebar-user-avatar {
				width: 36px;
				height: 36px;
				border-radius: 50%;
				background: #0D5C4E;
				color: #FFFFFF;
				font-family: 'Manrope', sans-serif;
				font-weight: 800;
				font-size: 13px;
				display: flex;
				align-items: center;
				justify-content: center;
			}
			.fw-sidebar-user-info {
				flex: 1;
				display: flex;
				flex-direction: column;
			}
			.fw-sidebar-user-name {
				font-family: 'Manrope', sans-serif;
				font-size: 13.5px;
				font-weight: 700;
				color: #0F172A;
				line-height: 1.2;
			}
			.fw-sidebar-user-role {
				font-family: 'DM Sans', sans-serif;
				font-size: 11px;
				color: #64748B;
			}
			</style>
			"""
		),
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

	# Query Param Navigation
	query_nav = st.query_params.get("nav")
	if query_nav:
		nav_map = {
			"overview": "Overview",
			"transactions": "Transactions",
			"spending": "Spending insights",
			"goals": "Goals",
			"ai": "FinWise AI",
			"settings": "Settings",
			"profile": "My Profile",
		}
		if query_nav in nav_map:
			st.session_state["finwise_workspace_page"] = nav_map[query_nav]
			st.query_params.clear()

	with st.sidebar:
		st.markdown(
			textwrap.dedent(
				"""\
				<div class="fw-sidebar-header">
				  <div class="fw-sidebar-brand">
				    <div class="fw-brand-icon-bars">
				      <span style="height: 10px;"></span>
				      <span style="height: 18px;"></span>
				      <span style="height: 14px;"></span>
				    </div>
				    <span class="fw-brand-text">FinWise</span>
				  </div>
				  <div class="fw-sidebar-close-btn" onclick="window.parent.document.querySelector('[data-testid=stSidebarCollapseButton] button')?.click();">
				    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#64748B" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
				      <line x1="18" y1="6" x2="6" y2="18"></line>
				      <line x1="6" y1="6" x2="18" y2="18"></line>
				    </svg>
				  </div>
				</div>
				<div class="fw-sidebar-section-title">WORKSPACE</div>
				"""
			),
			unsafe_allow_html=True,
		)

		primary_nav = ["Overview", "Transactions", "Spending insights", "Goals", "FinWise AI"]
		current_sel = st.session_state.get("finwise_workspace_page", "Overview")
		if current_sel in ("Dashboard", "Your Money Snapshot"):
			current_sel = "Overview"
			st.session_state["finwise_workspace_page"] = "Overview"

		selected_nav = st.radio(
			"",
			options=primary_nav,
			index=primary_nav.index(current_sel) if current_sel in primary_nav else 0,
			label_visibility="collapsed",
			key="finwise_workspace_page",
		)
		selected_page = selected_nav

		# Weekly insight card
		st.markdown(
			textwrap.dedent(
				"""\
				<div class="fw-sidebar-insight-card">
				  <div class="fw-insight-icon-bubble">
				    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0D5C4E" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
				      <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>
				    </svg>
				  </div>
				  <div class="fw-insight-title">Weekly insight</div>
				  <div class="fw-insight-desc">You spent 12% less on dining this week.</div>
				  <a href="?nav=spending" class="fw-insight-link">View insight &rsaquo;</a>
				</div>
				"""
			),
			unsafe_allow_html=True,
		)

		d_name = user.get("display_name", "Tahasinur")
		user_initials = "TM" if "tahas" in d_name.lower() else (d_name[:2]).upper()
		st.markdown(
			textwrap.dedent(
				f"""\
				<div style="margin-top: 10px;">
				  <div style="border-top: 1px solid #F1F5F9; margin: 16px 0 10px 0;"></div>
				  <a href="?nav=settings" class="fw-sidebar-bottom-item">
				    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#475569" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				      <circle cx="12" cy="12" r="3"></circle>
				      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
				    </svg>
				    <span>Settings</span>
				  </a>
				  <a href="?nav=profile" class="fw-sidebar-user-card">
				    <div class="fw-sidebar-user-avatar">{user_initials}</div>
				    <div class="fw-sidebar-user-info">
				      <div class="fw-sidebar-user-name">{user['display_name']}</div>
				      <div class="fw-sidebar-user-role">Personal account</div>
				    </div>
				    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
				      <polyline points="9 18 15 12 9 6"></polyline>
				    </svg>
				  </a>
				</div>
				"""
			),
			unsafe_allow_html=True,
		)

		if user.get("role") == "admin":
			st.markdown(
				"<div style='font:700 11px Manrope,sans-serif;color:#64748B;padding:12px 0 4px 8px;'>ADMINISTRATION</div>",
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

		st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
		if st.button("Sign out", use_container_width=True):
			for key in list(st.session_state.keys()):
				del st.session_state[key]
			st.rerun()

	# Page Dispatcher
	if selected_page == "Admin Console":
		admin.render(user, frame, store_path)
	elif selected_page == "How Accurate Are the Tools?":
		if user.get("role") == "admin":
			model_evaluation.render(frame)
		else:
			st.error("Administrator access is required for model evaluation.")
	elif selected_page in ("Overview", "Dashboard"):
		importlib.reload(dashboard)
		dashboard.render(frame, store_path)
	elif selected_page in ("Transactions", "Income & Expenses"):
		transactions.render(frame, store_path)
	elif selected_page in ("Spending insights", "Spending Insights"):
		spending_analysis.render(frame)
	elif selected_page in ("Goals", "Goal Pathfinder"):
		goal_planner.render(frame)
	elif selected_page in ("FinWise AI", "Your Money Snapshot"):
		integrated_guidance.render(frame)
	elif selected_page == "Settings":
		settings.render(frame)
	elif selected_page in ("My Profile", "Profile"):
		profile.render(frame)
	else:
		if selected_page in NAVIGATION:
			NAVIGATION[selected_page].render(frame)


def _render_public_app() -> None:
	importlib.reload(authentication)
	query_auth = st.query_params.get("auth")
	if query_auth in ("login", "register"):
		st.session_state["auth_view"] = query_auth
		st.query_params.clear()
	elif query_auth == "welcome":
		st.session_state["auth_view"] = "welcome"
		st.query_params.clear()

	def authenticate(profile_data: dict) -> None:
		st.session_state["user_id"] = profile_data["user_id"]
		user_transactions_path(profile_data["user_id"])
		st.rerun()

	def open_login() -> None:
		st.session_state["auth_view"] = "login"
		st.query_params.clear()

	def open_register() -> None:
		st.session_state["auth_view"] = "register"
		st.query_params.clear()

	def open_landing() -> None:
		st.session_state["auth_view"] = "welcome"
		st.query_params.clear()
		st.rerun()

	auth_view = st.session_state.get("auth_view", "welcome")
	if auth_view == "login":
		authentication.render_login(authenticate, open_register, open_landing)
	elif auth_view == "register":
		authentication.render_register(authenticate, open_login, open_landing)
	else:
		authentication.render_landing(authenticate, open_login, open_register)


if __name__ == "__main__":
	main()
