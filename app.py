import os

import pandas as pd
import psycopg2
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

# Locally these come from .env; on Streamlit Cloud they come from the app's Secrets.
load_dotenv()

DB = dict(
    dbname=os.getenv("POSTGRES_DB", "postgres"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT", "5432"),
    sslmode=os.getenv("DB_SSLMODE", "require"),
)
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

QUESTIONS = [
    {
        "id": 1, "points": 4,
        "text": "How many tracks are in the 'Rock' genre?",
        "sql": """SELECT COUNT(*) AS rock_tracks
FROM track t JOIN genre g ON g.genre_id = t.genre_id
WHERE g.name = 'Rock';""",
        "expected": "1 row: `rock_tracks = 1297`",
    },
    {
        "id": 2, "points": 4,
        "text": "List the top 5 countries by number of customers (ties broken alphabetically).",
        "sql": """SELECT country, COUNT(*) AS customers
FROM customer
GROUP BY country
ORDER BY customers DESC, country
LIMIT 5;""",
        "expected": """| country | customers |
|---|---|
| USA | 13 |
| Canada | 8 |
| Brazil | 5 |
| France | 5 |
| Germany | 4 |""",
    },
    {
        "id": 3, "points": 4,
        "text": "Using a CTE and RANK(), list each support rep's top-spending customer(s). Include ties.",
        "sql": """WITH spend AS (
  SELECT c.support_rep_id,
         c.first_name || ' ' || c.last_name AS customer,
         SUM(i.total) AS total_spent
  FROM customer c
  JOIN invoice i ON i.customer_id = c.customer_id
  GROUP BY c.customer_id, c.support_rep_id, customer
),
ranked AS (
  SELECT *, RANK() OVER (PARTITION BY support_rep_id ORDER BY total_spent DESC) AS rnk
  FROM spend
)
SELECT e.first_name || ' ' || e.last_name AS rep, r.customer, r.total_spent
FROM ranked r
JOIN employee e ON e.employee_id = r.support_rep_id
WHERE r.rnk = 1
ORDER BY rep, r.customer;""",
        "expected": """| rep | customer | total_spent |
|---|---|---|
| Jane Peacock | Hugh O'Reilly | 45.62 |
| Jane Peacock | Ladislav Kovács | 45.62 |
| Margaret Park | Richard Cunningham | 47.62 |
| Steve Johnson | Helena Holý | 49.62 |""",
    },
    {
        "id": 4, "points": 4,
        "text": "Using a CTE, show total sales per year, the change vs. the previous year (LAG), and a running total.",
        "sql": """WITH yearly AS (
  SELECT EXTRACT(YEAR FROM invoice_date)::int AS yr, SUM(total) AS sales
  FROM invoice
  GROUP BY yr
)
SELECT yr, sales,
       sales - LAG(sales) OVER (ORDER BY yr) AS change,
       SUM(sales) OVER (ORDER BY yr) AS running_total
FROM yearly
ORDER BY yr;""",
        "expected": """| yr | sales | change | running_total |
|---|---|---|---|
| 2021 | 449.46 | null | 449.46 |
| 2022 | 481.45 | 31.99 | 930.91 |
| 2023 | 469.58 | -11.87 | 1400.49 |
| 2024 | 477.53 | 7.95 | 1878.02 |
| 2025 | 450.58 | -26.95 | 2328.60 |""",
    },
    {
        "id": 5, "points": 4,
        "text": "Using a CTE and a window function, show the top 5 genres by revenue and each one's % of total revenue.",
        "sql": """WITH genre_rev AS (
  SELECT g.name AS genre, SUM(il.unit_price * il.quantity) AS revenue
  FROM invoice_line il
  JOIN track t ON t.track_id = il.track_id
  JOIN genre g ON g.genre_id = t.genre_id
  GROUP BY g.name
)
SELECT genre, revenue,
       ROUND(100 * revenue / SUM(revenue) OVER (), 2) AS pct_of_total
FROM genre_rev
ORDER BY revenue DESC
LIMIT 5;""",
        "expected": """| genre | revenue | pct_of_total |
|---|---|---|
| Rock | 826.65 | 35.50 |
| Latin | 382.14 | 16.41 |
| Metal | 261.36 | 11.22 |
| Alternative & Punk | 241.56 | 10.37 |
| TV Shows | 93.53 | 4.02 |""",
    },
]


def run_query(sql):
    """Run the taker's SQL in a read-only transaction and return a DataFrame."""
    conn = psycopg2.connect(**DB)
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                return None
            cols = [d[0] for d in cur.description]
            return pd.DataFrame(cur.fetchmany(500), columns=cols)
    finally:
        conn.close()


def log_action(email, action, question_id, sql):
    """Append to the audit log (parameterized, no f-string SQL)."""
    conn = psycopg2.connect(**DB)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_log (user_email, action, question_id, sql_text) VALUES (%s, %s, %s, %s)",
                (email, action, question_id, sql),
            )
    finally:
        conn.close()


st.set_page_config(page_title="Chinook SQL Quiz")
st.title("Chinook SQL Quiz")
st.caption("5 questions × 4 points = 20 points. Data: the Chinook music store database on Supabase.")

if "email" not in st.session_state:
    st.session_state.email = None

# --- Sign in / sign up (Supabase Auth) ---
with st.sidebar:
    if st.session_state.email:
        st.write(f"Signed in as **{st.session_state.email}**")
        if st.button("Sign out"):
            st.session_state.email = None
            st.rerun()
    else:
        mode = st.radio("Account", ["Sign in", "Sign up"], horizontal=True)
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button(mode):
            user = None
            try:
                creds = {"email": email, "password": password}
                if mode == "Sign in":
                    res = supabase.auth.sign_in_with_password(creds)
                else:
                    res = supabase.auth.sign_up(creds)
                if res.user and res.session:
                    user = res.user.email
                else:
                    st.error("Sign-up needs email confirmation. Confirm, then sign in.")
            except Exception as e:
                st.error(f"Authentication failed: {e}")
            if user:
                st.session_state.email = user
                st.rerun()

signed_in = st.session_state.email is not None
if not signed_in:
    st.info("Sign in (left sidebar) to run queries and save answers.")

# --- Quiz ---
q = st.selectbox("Question", QUESTIONS, format_func=lambda q: f"Q{q['id']} ({q['points']} pts)")
st.subheader(f"Q{q['id']}. {q['text']}")
with st.expander("Hint: expected SQL and result"):
    st.code(q["sql"], language="sql")
    st.markdown(q["expected"])

answer = st.text_area("Your SQL", height=200, key=f"sql_{q['id']}")
col1, col2 = st.columns(2)
run = col1.button("Run", disabled=not signed_in)
save = col2.button("Save answer", disabled=not signed_in)

if run and signed_in:
    try:
        log_action(st.session_state.email, "run", q["id"], answer)
        df = run_query(answer)
        if df is None:
            st.warning("Query ran but returned no result set.")
        else:
            st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"SQL error: {e}")

if save and signed_in:
    if answer.strip():
        log_action(st.session_state.email, "save", q["id"], answer)
        st.success("Answer saved.")
    else:
        st.warning("Write some SQL before saving.")