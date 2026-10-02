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

To bootstrap an administrator, set `FINWISE_ADMIN_EMAIL` before registering that email, for example `$env:FINWISE_ADMIN_EMAIL = 'admin@example.com'` in PowerShell. Public registration cannot choose an admin role.

On macOS or Linux, activate the environment with `source .venv/bin/activate`.

## Project layout

- `app.py`: Streamlit entry point, public/authenticated routing, and shared styling.
- `pages/`: Landing/auth screens, account profile, transaction management, preprocessing, dashboard, ML advisors, optimization, planning, evaluation, and integrated guidance.
- `utils/auth.py`: SQLite accounts, PBKDF2 password hashes, local avatar validation, and per-user data paths.
- `utils/data_loader.py`: Transaction CSV validation, persistence, CRUD, and upload operations.
- `utils/calculations.py`: Financial summaries and monthly derived metrics.
- `models/preprocessing.py`: Reusable imputation, categorical encoding, MinMax scaling, and feature engineering.
- `models/spending_clustering.py`: Three-cluster K-Means model over monthly financial features.
- `models/purchase_classifier.py`: Logistic Regression primary model and scaled KNN comparison model.
- `models/purchase_features.py`: Shared feature schema for model training and live purchase checks.
- `models/budget_csp.py`: Backtracking, forward checking, and MRV budget search.
- `models/rule_engine.py`: Explainable threshold-based financial rules.
- `models/goal_astar.py`: A* monthly savings planner with an admissible heuristic.
- `data/finwise_users.sqlite3`: Local user accounts and salted password hashes, created on first account use.
- `data/user_data/<user-id>/transactions.csv`: Private persistent transaction ledger for each account.
- `data/profile_images/<user-id>.webp`: Resized local profile image for each account.
- `data/transactions.csv`: Included example ledger, copied into an account only when the user explicitly chooses the demo-data action.
- `data/synthetic_purchase_training.csv`: Labeled synthetic/demo purchase examples, generated locally on first model training.
- `data/sample_data.csv`: Compact CSV example for upload testing.
- `assets/`: Space for future static assets.

## Transaction data

CSV uploads use `date,type,category,amount,description`. Amounts must be positive when supplied; type is `income` or `expense`. Each account's private ledger adds a stable `transaction_id` column for editing and deletion. Uploads append to that account's CSV; manual add, edit, and delete operations write to the same account-specific file. The original included example ledger is not used as a shared live account store.

Rows with missing fields are preserved when imported. Data Processing displays their missing-value counts and imputes values for model features without changing the stored source row. Financial totals do not count imputed amounts.

Supported income categories are Salary, Freelance, Investment, Gift, Loan, and Debt Repaid. Supported expense categories are Housing, Food, Transportation, Entertainment, Health, and Education. Entertainment is currently treated as discretionary; the other supported expense categories are treated as essential.

## Algorithms and evaluation

- Purchase risk uses Logistic Regression as the primary classifier and a StandardScaler + KNN comparison. There is no labeled purchase-outcome dataset, so both models train on explicitly labeled synthetic/demo examples. Their accuracy, precision, recall, F1, and confusion matrices measure agreement with those synthetic labels only.
- Purchase verdicts are Strong Yes, Cautious Yes, Better Wait, and No. Goal impact uses the selected user's saved target, savings, deadline, and monthly saving limit; it does not infer a bank balance.
- Spending analysis fits K-Means with three clusters on monthly transaction features. Profile names are ranked from the fitted cluster centroids and are relative to the user's history. Fewer than six monthly observations are flagged as insufficient for reliable evaluation.
- Budget optimization searches discrete target allocations using recursive backtracking, forward checking, MRV, and branch-and-bound. Flexible targets use 0%, 25%, 50%, 75%, and 100% candidate levels; the solver has a 200,000-node cap.
- Goal planning uses A* over monthly savings states. The heuristic is a lower bound on months remaining; the search has a 50,000-state cap.
- Rule recommendations are deterministic threshold checks. Thresholds are illustrative and can produce false positives or false negatives.

## Limitations

- Purchase predictions are educational demonstrations, not validated for real-world financial decisions or financial advice.
- The sample ledger covers four months. More history is needed for reliable behavioral clustering or silhouette evaluation.
- Emergency reserve balances, debt payments, opening bank balances, and goal savings are not reliably identifiable from the transaction schema; related page inputs must be entered by the user.
- The transaction page's current balance is cumulative income minus expenses from a zero opening balance, not a bank-account balance.
- Monthly burn rate extrapolates the trailing seven-calendar-day average through the latest recorded transaction date.
- Integrated Guidance combines completed module runs for the current Streamlit session. It flags outputs as stale when the transaction ledger changes; rerun the source module to refresh them.
- Transaction data is stored as local CSV without encryption; simultaneous writes to the same account from multiple tabs are not serialized. There is no external bank connection.

## Accounts and privacy

Accounts are local to this application installation. Passwords are stored as PBKDF2-HMAC-SHA256 hashes with per-account salts; uploaded profile images are validated, resized, and stored locally. Each signed-in account receives its own transaction CSV, saved goals, and preferences; the app clears per-user model and form state when the active account changes. Admins see aggregate counts and global demo-model metrics, not other users' transaction rows. This is suitable for a local university project, not a hardened public production service: there is no email verification, password recovery, remote database, TLS termination, or multi-host storage coordination. Back up the `data/` directory to preserve accounts and ledgers.

K-Means is refitted from the current user's ledger on app reruns. Purchase classifiers use synthetic/demo training labels because no real labeled purchase-outcome dataset is available; they do not learn from a user's personal purchase decisions and their evaluation scores are not real-world financial accuracy.

The application computes all displayed metrics and model outputs dynamically from the shared ledger or the explicitly labeled synthetic purchase-training data. No purchase, budgeting, rule, or goal result is fabricated.
