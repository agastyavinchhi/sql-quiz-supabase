# Chinook SQL Quiz (Supabase + Streamlit)

**Live quiz:** https://sql-quiz-supabase.streamlit.app/

A 20-point SQL quiz that runs against a live PostgreSQL database. Users sign in, pick a question, write SQL, run it, and see the result table from the database.

## How to use the quiz
1. Open https://sql-quiz-supabase.streamlit.app/
2. In the left sidebar choose **Sign up**, enter any email and a password (6+ chars), and click **Sign up**. (Email confirmation is off, so you are signed in immediately.) Returning users choose **Sign in**.
3. Pick a question from the **Question** dropdown (5 questions × 4 points = 20 points).
4. Write your SQL in the box and click **Run** to see the result rows from the database.
5. Click **Save answer** to store your answer.
6. Open **Hint** under each question to see the expected SQL and expected result.

Signed-out users can read questions, but **Run** and **Save answer** are disabled.

## Quiz questions (dataset: Chinook music store)
| # | Topic | Points |
|---|---|---|
| Q1 | Count Rock tracks (JOIN + COUNT) | 4 |
| Q2 | Top 5 countries by customer count (GROUP BY) | 4 |
| Q3 | Each support rep's top customer (CTE + RANK() OVER PARTITION BY) | 4 |
| Q4 | Yearly sales, year-over-year change, running total (CTE + LAG + SUM OVER) | 4 |
| Q5 | Top 5 genres by revenue and % of total (CTE + SUM() OVER ()) | 4 |

Results are graded on the result set, not on matching the hint SQL character-for-character.

## Architecture
```
Browser ──► Streamlit app (app.py, Streamlit Community Cloud)
              ├── Supabase Auth (email/password sign-up & sign-in)
              └── psycopg2 ──SSL──► Supabase Session pooler ──► PostgreSQL (Chinook data)
GitHub Actions (db-check.yml) ──secrets──► same database, runs ci_check.py
```

| Component | Details |
|---|---|
| Database | Supabase PostgreSQL, loaded from `Chinook_PostgreSql.sql`. Connected through the **Session pooler** with `sslmode=require`. |
| Auth | Supabase Auth (email + password) via the `supabase` Python client. |
| App | `app.py` (Streamlit), deployed on Streamlit Community Cloud. Credentials are stored in Streamlit **Secrets**, not in git. |
| DB role | The app connects as a limited role, **`quiz_reader`**, not the `postgres` admin. It has `SELECT` on the Chinook tables and `INSERT` on `audit_log` only. Taker SQL also runs in a read-only transaction. |
| Row Level Security | RLS is on. Policies allow only `quiz_reader` to read the quiz tables and insert into `audit_log`; Supabase's public `anon`/`authenticated` API roles get nothing. |
| CI | `.github/workflows/db-check.yml` runs on every push to `main` (and manually). It reads the DB credentials from **GitHub Secrets** and runs `ci_check.py`. |

## GitHub Actions + Secrets
The workflow `Database check` installs dependencies and runs `ci_check.py`, which:
1. connects to Supabase as `quiz_reader` using the secrets,
2. checks that two quiz answers still match their hints (Q1 = 1297 Rock tracks, total sales = 2328.60),
3. checks that `quiz_reader` **cannot** `UPDATE` the audit log.

Repository secrets used (Settings → Secrets and variables → Actions):
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `DB_HOST`. No password appears in the workflow file or anywhere in the repo; `.env` is in `.gitignore`.

## Extra credit
- **Parameterized queries:** the app's own writes use `%s` placeholders (`log_action` in `app.py`; `ci_check.py`), with no f-string SQL.
- **Audit log:** every **Run** and **Save** by a signed-in user is recorded in the `audit_log` table (`user_email`, `action` = run/save, `question_id`, `sql_text`, `created_at`).
- **Integrity check:** `audit_log` is append-only.
  - `quiz_reader` has only `INSERT` (no `SELECT`/`UPDATE`/`DELETE`/`TRUNCATE`), so takers cannot change or read the log.
  - A trigger (`block_audit_changes`) rejects every `UPDATE`, `DELETE`, and `TRUNCATE`, even from the admin.
  - CI verifies this on every push.

## Database setup (run in the Supabase SQL Editor)
1. Run `Chinook_PostgreSql.sql` to create and load the Chinook tables.
2. Create the limited role and grant read access:
   ```sql
   CREATE ROLE quiz_reader WITH LOGIN PASSWORD '<password>';
   ALTER ROLE quiz_reader SET statement_timeout = '5s';
   GRANT USAGE ON SCHEMA public TO quiz_reader;
   GRANT SELECT ON album, artist, customer, employee, genre, invoice,
                   invoice_line, media_type, playlist, playlist_track, track TO quiz_reader;
   ```
3. Create the append-only `audit_log` table, grant `INSERT` + sequence usage to `quiz_reader`, and add the `block_audit_changes` trigger.
4. Add RLS policies: `FOR SELECT TO quiz_reader USING (true)` on each Chinook table, and `FOR INSERT TO quiz_reader WITH CHECK (true)` on `audit_log`.
5. In Supabase **Authentication → Sign In / Providers**, turn **Confirm email** off so new users can sign in right away.

## Run locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py      # opens http://localhost:8501
python ci_check.py        # same checks as GitHub Actions
```
Create a `.env` file (never committed):
```
POSTGRES_DB=postgres
POSTGRES_USER=quiz_reader.<project-ref>
POSTGRES_PASSWORD=<quiz_reader password>
DB_HOST=aws-0-<region>.pooler.supabase.com
DB_PORT=5432
DB_SSLMODE=require
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<publishable/anon key>
```
On Streamlit Cloud, the same keys are entered under **App settings → Secrets** (TOML format).

## Files
| File | Purpose |
|---|---|
| `app.py` | Streamlit quiz: auth, questions, hints, Run, Save, audit logging |
| `ci_check.py` | Database check run by GitHub Actions |
| `.github/workflows/db-check.yml` | GitHub Actions workflow (uses GitHub Secrets) |
| `Chinook_PostgreSql.sql` | Schema + data for the Chinook database |
| `query.py` | In-class lab script (Python ↔ Postgres CRUD demo) |
| `requirements.txt` | Python dependencies |