"""
Single-file Streamlit app for Local Food Wastage Management System.

Features:
- Works with PostgreSQL (via st.secrets or env vars) OR falls back to local SQLite.
- Creates tables if missing, can insert sample data (Admin page).
- Pages: Overview, Listings, Providers, Receivers, Claims, Analytics, Admin.
- Parameterized queries and simple input validation.
- Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime, date, timedelta
import plotly.express as px

st.set_page_config(page_title="Local Food Wastage", layout="wide")

class DB:
    def __init__(self):
        # Decide backend: postgres if secrets or env vars exist, else sqlite
        try:
            if "db_host" in st.secrets:
                self.db_type = "postgres"
            else:
                self.db_type = "sqlite"
        except Exception:
            # no st.secrets available (e.g., running via python, not streamlit)
            if os.getenv("DB_HOST") or os.getenv("DB_NAME"):
                self.db_type = "postgres"
            else:
                self.db_type = "sqlite"
        self._conn = None

    def get_conn(self):
        if self._conn is None:
            if self.db_type == "postgres":
                # lazy import to avoid error when psycopg2 not installed and sqlite is used
                import psycopg2
                params = {
                    "host": st.secrets.get("db_host", os.getenv("DB_HOST")),
                    "dbname": st.secrets.get("db_name", os.getenv("DB_NAME")),
                    "user": st.secrets.get("db_user", os.getenv("DB_USER")),
                    "password": st.secrets.get("db_pass", os.getenv("DB_PASS")),
                    "port": st.secrets.get("db_port", os.getenv("DB_PORT", "5432")),
                }
                self._conn = psycopg2.connect(**params)
            else:
                path = os.path.join(os.getcwd(), "local_food.db")
                conn = sqlite3.connect(path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                self._conn = conn
        return self._conn

    def _adapt_sql(self, sql: str) -> str:
        # Convert %s placeholders to ? for sqlite
        if self.db_type == "sqlite":
            return sql.replace("%s", "?")
        return sql

    def run_query(self, sql: str, params: tuple = None) -> pd.DataFrame:
        conn = self.get_conn()
        sql_exec = self._adapt_sql(sql)
        # pandas handles parameters for both psycopg2 and sqlite
        df = pd.read_sql_query(sql_exec, conn, params=params)
        return df

    def run_execute(self, sql: str, params: tuple = None):
        conn = self.get_conn()
        sql_exec = self._adapt_sql(sql)
        cur = conn.cursor()
        cur.execute(sql_exec, params or ())
        conn.commit()
        # For INSERT .. RETURNING (postgres) the cursor may hold rows, but we keep it simple
        return cur

    def create_tables(self):
        if self.db_type == "postgres":
            q_providers = """
            CREATE TABLE IF NOT EXISTS providers (
                provider_id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT,
                address TEXT,
                city TEXT,
                contact TEXT
            );
            """
            q_receivers = """
            CREATE TABLE IF NOT EXISTS receivers (
                receiver_id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT,
                city TEXT,
                contact TEXT
            );
            """
            q_food = """
            CREATE TABLE IF NOT EXISTS food_listings (
                food_id SERIAL PRIMARY KEY,
                food_name TEXT NOT NULL,
                quantity INT CHECK (quantity > 0),
                expiry_date DATE NOT NULL,
                provider_id INT,
                provider_type TEXT,
                location TEXT,
                food_type TEXT,
                meal_type TEXT,
                FOREIGN KEY (provider_id) REFERENCES providers(provider_id)
            );
            """
            q_claims = """
            CREATE TABLE IF NOT EXISTS claims (
                claim_id SERIAL PRIMARY KEY,
                food_id INT,
                receiver_id INT,
                status VARCHAR(20) DEFAULT 'Pending',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (food_id) REFERENCES food_listings(food_id),
                FOREIGN KEY (receiver_id) REFERENCES receivers(receiver_id)
            );
            """
        else:
            # SQLite version (AUTOINCREMENT)
            q_providers = """
            CREATE TABLE IF NOT EXISTS providers (
                provider_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT,
                address TEXT,
                city TEXT,
                contact TEXT
            );
            """
            q_receivers = """
            CREATE TABLE IF NOT EXISTS receivers (
                receiver_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT,
                city TEXT,
                contact TEXT
            );
            """
            q_food = """
            CREATE TABLE IF NOT EXISTS food_listings (
                food_id INTEGER PRIMARY KEY AUTOINCREMENT,
                food_name TEXT NOT NULL,
                quantity INTEGER CHECK (quantity > 0),
                expiry_date DATE NOT NULL,
                provider_id INTEGER,
                provider_type TEXT,
                location TEXT,
                food_type TEXT,
                meal_type TEXT,
                FOREIGN KEY (provider_id) REFERENCES providers(provider_id)
            );
            """
            q_claims = """
            CREATE TABLE IF NOT EXISTS claims (
                claim_id INTEGER PRIMARY KEY AUTOINCREMENT,
                food_id INTEGER,
                receiver_id INTEGER,
                status TEXT DEFAULT 'Pending',
                timestamp DATETIME DEFAULT (CURRENT_TIMESTAMP),
                FOREIGN KEY (food_id) REFERENCES food_listings(food_id),
                FOREIGN KEY (receiver_id) REFERENCES receivers(receiver_id)
            );
            """
        for q in (q_providers, q_receivers, q_food, q_claims):
            self.run_execute(q)

    def insert_sample_data(self):
        # Insert only if no providers exist (safety)
        dfp = self.run_query("SELECT COUNT(*) AS cnt FROM providers")
        if int(dfp.iloc[0, 0]) > 0:
            return "Sample data already present."
        # Providers
        self.run_execute("INSERT INTO providers (name, type, address, city, contact) VALUES (%s,%s,%s,%s,%s)",
                         ("FreshBites Restaurant", "Restaurant", "123 Market Street", "Mumbai", "+91-9876543210"))
        self.run_execute("INSERT INTO providers (name, type, address, city, contact) VALUES (%s,%s,%s,%s,%s)",
                         ("Happy Meals", "Caterer", "45 Food Plaza", "Delhi", "+91-9876501234"))
        # Receivers
        self.run_execute("INSERT INTO receivers (name, type, city, contact) VALUES (%s,%s,%s,%s)",
                         ("Helping Hands NGO", "NGO", "Mumbai", "9988776655"))
        self.run_execute("INSERT INTO receivers (name, type, city, contact) VALUES (%s,%s,%s,%s)",
                         ("Care Kitchen", "Community Kitchen", "Delhi", "8877665544"))
        # Food listings (expiry in near future)
        today = date.today()
        ed1 = (today + timedelta(days=3)).isoformat()
        ed2 = (today + timedelta(days=1)).isoformat()
        self.run_execute("INSERT INTO food_listings (food_name, quantity, expiry_date, provider_id, provider_type, location, food_type, meal_type) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                         ("Vegetable Curry", 20, ed1, 1, "Restaurant", "Mumbai", "Vegetarian", "Lunch"))
        self.run_execute("INSERT INTO food_listings (food_name, quantity, expiry_date, provider_id, provider_type, location, food_type, meal_type) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                         ("Chicken Biryani", 15, ed2, 2, "Caterer", "Delhi", "Non-Vegetarian", "Dinner"))
        # Claims
        self.run_execute("INSERT INTO claims (food_id, receiver_id, status, timestamp) VALUES (%s,%s,%s,%s)",
                         (1, 1, "Completed", datetime.now().isoformat(sep=' ')))
        self.run_execute("INSERT INTO claims (food_id, receiver_id, status, timestamp) VALUES (%s,%s,%s,%s)",
                         (2, 2, "Pending", datetime.now().isoformat(sep=' ')))
        return "Sample data inserted."


# Instantiate DB (cached resource)
@st.cache_resource
def get_db():
    return DB()


db = get_db()


# ---------- UI Helpers ----------
def safe_scalar(df):
    """Return first item or 0 if empty."""
    if df is None or df.empty:
        return 0
    return df.iloc[0, 0]


def sidebar_navigation():
    return st.sidebar.selectbox("Go to", ["Overview", "Listings", "Providers", "Receivers", "Claims", "Analytics", "Admin"])


page = sidebar_navigation()


# ---------- PAGES ----------
if page == "Overview":
    st.title("🍲 Overview")
    st.markdown("Quick KPIs and summary")

    total_listings = safe_scalar(db.run_query(
        "SELECT COUNT(*) FROM food_listings WHERE expiry_date >= CURRENT_DATE;"
    ))
    total_qty = safe_scalar(db.run_query(
        "SELECT COALESCE(SUM(quantity),0) FROM food_listings WHERE expiry_date >= CURRENT_DATE;"
    ))
    completed = safe_scalar(db.run_query(
        "SELECT COUNT(*) FROM claims WHERE status = 'Completed';"
    ))
    total_claims = safe_scalar(db.run_query(
        "SELECT COUNT(*) FROM claims;"
    ))
    providers_count = safe_scalar(db.run_query("SELECT COUNT(*) FROM providers;"))
    receivers_count = safe_scalar(db.run_query("SELECT COUNT(*) FROM receivers;"))

    col1, col2, col3 = st.columns(3)
    col1.metric("Active Listings", int(total_listings))
    col2.metric("Total Quantity", int(total_qty))
    pct_completed = f"{round((completed / total_claims * 100),2)}%" if total_claims else "0%"
    col3.metric("Claims Completed", pct_completed)

    st.write(f"Providers: **{providers_count}** — Receivers: **{receivers_count}**")

    # small charts
    st.subheader("Listings by City")
    city_df = db.run_query("SELECT COALESCE(location,'Unknown') AS location, COUNT(*) AS listings FROM food_listings GROUP BY location ORDER BY listings DESC;")
    if not city_df.empty:
        fig_city = px.bar(city_df, x="location", y="listings", labels={"location": "City", "listings": "Listings"})
        st.plotly_chart(fig_city, use_container_width=True)
    else:
        st.info("No listings to show.")

elif page == "Listings":
    st.title("📋 Listings")
    st.markdown("Browse and claim available food listings (non-expired).")

    # Filters
    locations = db.run_query("SELECT DISTINCT COALESCE(location,'Unknown') AS location FROM food_listings ORDER BY location;")
    loc_options = ["All"] + locations['location'].tolist() if not locations.empty else ["All"]
    selected_loc = st.selectbox("City", loc_options)

    food_types = db.run_query("SELECT DISTINCT COALESCE(food_type,'Unknown') AS food_type FROM food_listings ORDER BY food_type;")
    ft_options = ["All"] + food_types['food_type'].tolist() if not food_types.empty else ["All"]
    selected_ft = st.selectbox("Food Type", ft_options)

    # Build query
    q = "SELECT food_id, food_name, quantity, expiry_date, provider_id, provider_type, location, food_type, meal_type FROM food_listings WHERE expiry_date >= CURRENT_DATE"
    params = []
    if selected_loc != "All":
        q += " AND location = %s"
        params.append(selected_loc)
    if selected_ft != "All":
        q += " AND food_type = %s"
        params.append(selected_ft)
    q += " ORDER BY expiry_date ASC;"

    df = db.run_query(q, tuple(params) if params else None)
    if df.empty:
        st.info("No available listings with current filters.")
    else:
        st.dataframe(df)

        st.subheader("Make a Claim")
        with st.form("claim_form"):
            food_ids = df['food_id'].tolist()
            food_choice = st.selectbox("Select Food ID", food_ids)
            receiver_id = st.number_input("Your Receiver ID", min_value=1, step=1)
            submitted = st.form_submit_button("Claim Now")
            if submitted:
                # create claim: status Pending
                try:
                    db.run_execute("INSERT INTO claims (food_id, receiver_id, status) VALUES (%s,%s,%s);",
                                   (int(food_choice), int(receiver_id), "Pending"))
                    st.success("Claim submitted (Pending). Admin/provider should update status after pickup.")
                except Exception as e:
                    st.error(f"Failed to submit claim: {e}")

elif page == "Providers":
    st.title("🏪 Providers")
    st.markdown("View and add providers.")

    df = db.run_query("SELECT * FROM providers ORDER BY provider_id;")
    st.dataframe(df)

    st.subheader("Add Provider")
    with st.form("add_provider"):
        pname = st.text_input("Name")
        ptype = st.text_input("Type (e.g., Restaurant, Caterer)")
        paddress = st.text_input("Address")
        pcity = st.text_input("City")
        pcontact = st.text_input("Contact")
        if st.form_submit_button("Add Provider"):
            if not pname:
                st.warning("Name is required.")
            else:
                db.run_execute("INSERT INTO providers (name, type, address, city, contact) VALUES (%s,%s,%s,%s,%s);",
                               (pname, ptype, paddress, pcity, pcontact))
                st.success("Provider added. Refresh to see the list.")

elif page == "Receivers":
    st.title("👥 Receivers")
    st.markdown("View and add receivers.")

    df = db.run_query("SELECT * FROM receivers ORDER BY receiver_id;")
    st.dataframe(df)

    st.subheader("Add Receiver")
    with st.form("add_receiver"):
        rname = st.text_input("Name")
        rtype = st.text_input("Type (e.g., NGO, Community Kitchen)")
        rcity = st.text_input("City")
        rcontact = st.text_input("Contact")
        if st.form_submit_button("Add Receiver"):
            if not rname:
                st.warning("Name is required.")
            else:
                db.run_execute("INSERT INTO receivers (name, type, city, contact) VALUES (%s,%s,%s,%s);",
                               (rname, rtype, rcity, rcontact))
                st.success("Receiver added. Refresh to see the list.")

elif page == "Claims":
    st.title("📑 Claims")
    st.markdown("View and update claim statuses.")

    status_filter = st.selectbox("Filter status", ["All", "Pending", "Completed", "Cancelled"])
    q = "SELECT claim_id, food_id, receiver_id, status, timestamp FROM claims"
    params = []
    if status_filter != "All":
        q += " WHERE status = %s"
        params.append(status_filter)
    q += " ORDER BY timestamp DESC;"
    df = db.run_query(q, tuple(params) if params else None)
    st.dataframe(df)

    st.subheader("Update Claim Status")
    with st.form("update_claim"):
        cid = st.number_input("Claim ID", min_value=1, step=1)
        new_status = st.selectbox("New Status", ["Pending", "Completed", "Cancelled"])
        if st.form_submit_button("Update"):
            try:
                db.run_execute("UPDATE claims SET status = %s WHERE claim_id = %s;", (new_status, int(cid)))
                st.success("Claim status updated.")
            except Exception as e:
                st.error(f"Failed to update claim: {e}")

elif page == "Analytics":
    st.title("📈 Analytics")
    st.markdown("Visual insights")

    city_data = db.run_query("SELECT COALESCE(location,'Unknown') AS location, COUNT(*) AS listings FROM food_listings GROUP BY location ORDER BY listings DESC;")
    if not city_data.empty:
        fig1 = px.bar(city_data, x="location", y="listings", title="Listings by City")
        st.plotly_chart(fig1, use_container_width=True)

    ft = db.run_query("SELECT COALESCE(food_type,'Unknown') AS food_type, COUNT(*) AS cnt FROM food_listings GROUP BY food_type;")
    if not ft.empty:
        fig2 = px.pie(ft, names="food_type", values="cnt", title="Food Type Distribution")
        st.plotly_chart(fig2, use_container_width=True)

    claims_time = db.run_query("SELECT DATE(timestamp) AS day, COUNT(*) AS cnt FROM claims GROUP BY day ORDER BY day;")
    if not claims_time.empty:
        fig3 = px.line(claims_time, x="day", y="cnt", title="Claims Over Time")
        st.plotly_chart(fig3, use_container_width=True)

elif page == "Admin":
    st.title("⚙️ Admin")
    st.markdown("Create schema, insert sample data, and export CSVs.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Create tables (if missing)"):
            try:
                db.create_tables()
                st.success("Tables created or already exist.")
            except Exception as e:
                st.error(f"Create tables failed: {e}")

        if st.button("Insert sample data (if empty)"):
            try:
                msg = db.insert_sample_data()
                st.success(msg)
            except Exception as e:
                st.error(f"Inserting sample data failed: {e}")

    with col2:
        if st.button("Export providers.csv"):
            dfp = db.run_query("SELECT * FROM providers;")
            st.download_button("Download providers.csv", dfp.to_csv(index=False), "providers.csv", "text/csv")
        if st.button("Export food_listings.csv"):
            dff = db.run_query("SELECT * FROM food_listings;")
            st.download_button("Download food_listings.csv", dff.to_csv(index=False), "food_listings.csv", "text/csv")
        if st.button("Export claims.csv"):
            dfc = db.run_query("SELECT * FROM claims;")
            st.download_button("Download claims.csv", dfc.to_csv(index=False), "claims.csv", "text/csv")

    st.markdown("---")
    st.write("Notes:")
    st.write("- If you want to use PostgreSQL, add `.streamlit/secrets.toml` with db credentials, or set DB_HOST/DB_NAME/... environment variables.")
    st.write("- Without DB credentials, this app uses a local `local_food.db` SQLite file created in the project folder.")


# Footer note
st.sidebar.markdown("---")
st.sidebar.info("Run `streamlit run app.py` to start. Use Admin -> Create tables, Insert sample data to initialize.")
