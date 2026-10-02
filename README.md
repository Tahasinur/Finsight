# FinWise AI

FinWise AI is a university AI laboratory project for personal finance workflows. It includes a public landing page, local account registration and sign-in, per-account profiles and ledgers, data processing, a transaction-backed dashboard, K-Means spending profiles, supervised purchase-risk demos, a CSP budget optimizer, an IF-THEN rule engine, A* goal planning, and integrated guidance.

## Run locally

Python 3.10 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

To run the automated test suite:

```powershell
pytest tests/ -v
```

To bootstrap an administrator, set `FINWISE_ADMIN_EMAIL` before registering that email, for example `$env:FINWISE_ADMIN_EMAIL = 'admin@example.com'` in PowerShell. Public registration cannot choose an admin role.

On macOS or Linux, activate the environment with `source .venv/bin/activate`.

## Project layout

- `app.py`: Streamlit entry point, public/authenticated routing, session invalidation on logout, and shared styling.
- `pages/`: Landing/auth screens, account profile, transaction management, preprocessing, dashboard, ML advisors, optimization, planning, evaluation, and integrated guidance.
- `utils/auth.py`: SQLite user stores, PBKDF2 password hashing, brute-force rate-limiting, custom category management, rule thresholds, and user data export/cleanup.
- `utils/data_loader.py`: SQLite transaction storage, ACID persistence, CSV normalization, smart column mapping, and legacy CSV migration.
- `utils/calculations.py`: Financial summaries, monthly cash flow, category aggregations, and deterministic transaction fingerprinting.
- `models/preprocessing.py`: Reusable imputation, categorical encoding, MinMax scaling, and feature engineering.
- `models/spending_clustering.py`: Three-cluster K-Means model over monthly financial features with centroid ranking.
- `models/purchase_classifier.py`: Logistic Regression primary model and scaled KNN comparison model.
- `models/purchase_features.py`: Shared feature schema for model training and live purchase checks.
- `models/budget_csp.py`: Backtracking, forward checking, and MRV budget search with branch-and-bound pruning.
- `models/rule_engine.py`: Explainable rule engine with configurable `RuleThresholds`.
- `models/goal_astar.py`: A* monthly savings planner with an admissible heuristic and lifestyle disruption penalties.
- `tests/`: End-to-end unit and integration tests covering auth, CSP budget solver, A* goal planner, CSV mapping, SQLite CRUD, and migration.
- `data/finwise_users.sqlite3`: Local SQLite database storing users, preferences, goals, transactions, custom categories, login attempts, and analysis runs.
- `data/profile_images/<user-id>.webp`: Resized local profile image for each account.
- `data/transactions.csv`: Included example ledger, copied into an account only when the user explicitly chooses the demo-data action.
- `data/synthetic_purchase_training.csv`: Labeled synthetic/demo purchase examples, generated locally on first model training.
- `data/sample_data.csv`: Compact CSV example for upload testing.

## Transaction data & SQLite Storage

User transactions are stored directly in SQLite (`transactions` table) with ACID transaction guarantees, eliminating multi-tab race conditions and file-locking bottlenecks:
- Schema: `transactions(transaction_id, user_id, date, type, category, amount, description, created_at)`
- Automated startup migration (`migrate_existing_csv_ledgers`): On launch, any legacy `user_data/<user_id>/transactions.csv` ledgers are imported into SQLite and backed up as `transactions.csv.migrated`.
- Custom Categories: Users can define custom income and expense categories in Settings, which integrate seamlessly into transaction management, filtering, and budget targets.
- Flexible CSV Import: Column mapping and amount polarity auto-inference support arbitrary bank statement exports.

Supported base income categories are Salary, Freelance, Investment, Gift, Loan, and Debt Repaid. Supported base expense categories are Housing, Food, Transportation, Entertainment, Health, and Education, expandable via custom user categories.

## Algorithms and evaluation

- Purchase risk uses Logistic Regression as the primary classifier and a StandardScaler + KNN comparison. Both models train on explicitly labeled synthetic/demo examples. Their accuracy, precision, recall, F1, and confusion matrices measure agreement with those synthetic labels.
- Purchase verdicts are Strong Yes, Cautious Yes, Better Wait, and No.
- Spending analysis fits K-Means with three clusters on monthly transaction features. Profile names are ranked from the fitted cluster centroids and are relative to the user's history.
- Budget optimization searches discrete target allocations using recursive backtracking, forward checking, MRV, and branch-and-bound.
- Goal planning uses A* over monthly savings states with an admissible heuristic.
- Rule recommendations evaluate configurable thresholds (`RuleThresholds`), editable directly by users in Settings.

## Limitations

- Purchase predictions are educational demonstrations, not validated for real-world financial decisions or financial advice.
- The sample ledger covers four months. More history is needed for reliable behavioral clustering or silhouette evaluation.
- Emergency reserve balances, debt payments, opening bank balances, and goal savings are not reliably identifiable from raw transactions; related page inputs must be entered by the user.
- Monthly burn rate extrapolates the trailing seven-calendar-day average through the latest recorded transaction date.
- Integrated Guidance combines completed module runs for the current Streamlit session. It flags outputs as stale when the transaction ledger changes.

## Security, Accounts and privacy

- Accounts are local to this application installation. Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes (100,000 iterations).
- Brute-Force Rate Limiting: 5 consecutive failed login attempts lock the account for 5 minutes, tracked in `login_attempts`. Successful logins clear failed attempts.
- Session Isolation: Sign-out completely purges all sensitive keys from Streamlit session state and forces a clean state reload.
- Data Ownership: Users can export all account data (profile, goals, preferences, transactions) as a single ZIP archive, or clear all financial records while retaining account credentials.
- Admins see aggregate counts and global demo-model metrics, not other users' transaction details.
