# ============================================================
# SJJP Requests Portal - Supabase Integrated + Auto Bootstrap
# Version: v4.5 (2025-11-09)
# ============================================================

import os
import pandas as pd
import streamlit as st
from datetime import datetime
from supabase import create_client, Client
import uuid

# ------------------------------------------------------------
# 0) Page setup
# ------------------------------------------------------------
st.set_page_config(page_title="SJJP - Requests Portal", layout="wide")
st.title("School Jiu-Jitsu Program - Requests Portal (Online)")

# ------------------------------------------------------------
# 1) Supabase connection
# ------------------------------------------------------------
SUPABASE_URL = st.secrets.get("supabase", {}).get("url")
SUPABASE_KEY = st.secrets.get("supabase", {}).get("key")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase is not configured. Please check your Streamlit Secrets.")
    st.stop()

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"❌ Failed to connect to Supabase: {e}")
    st.stop()

# ------------------------------------------------------------
# 1.1) Auto-verify and bootstrap Supabase tables
# ------------------------------------------------------------
def table_exists(table_name: str) -> bool:
    try:
        res = supabase.table(table_name).select("*").limit(1).execute()
        return not hasattr(res, "error")
    except Exception:
        return False

def bootstrap_tables():
    sql_scripts = {
        "users": """
            create table if not exists users (
              ps_number text primary key,
              password text not null,
              credential text default 'Coach',
              name text
            );
            insert into users (ps_number, password, credential, name)
            values ('PS1724', 'PS1724', 'Admin', 'Administrator')
            on conflict (ps_number) do nothing;
        """,
        "coaches": """
            create table if not exists coaches (
              ps_number text primary key,
              name text
            );
        """,
        "schools": """
            create table if not exists schools (
              id text primary key,
              nome text,
              city text,
              coaches text[] default array[]::text[]
            );
        """,
        "materials": """
            create table if not exists materials (
              category text,
              subcategory text,
              item text
            );
        """,
        "requests": """
            create table if not exists requests (
              id uuid primary key default gen_random_uuid(),
              school_id text,
              category text,
              material text,
              quantity int,
              date timestamp with time zone default now(),
              ps_number text,
              status text default 'Pending'
            );
        """
    }

    # Requires the SQL RPC helper function
    for table, query in sql_scripts.items():
        if not table_exists(table):
            try:
                supabase.rpc("sql", {"query": query}).execute()
                st.success(f"✅ Created missing table: {table}")
            except Exception as e:
                st.warning(f"⚠️ Could not create {table}: {e}")

try:
    bootstrap_tables()
except Exception as e:
    st.warning(f"⚠️ Auto-bootstrap skipped: {e}")

# ------------------------------------------------------------
# 2) Authentication
# ------------------------------------------------------------
def authenticate(ps_number: str, password: str):
    try:
        users = supabase.table("users").select("*").eq("ps_number", ps_number).execute()
        data = users.data
        if data:
            user = data[0]
            if user.get("password") == password:
                return user
        # Fallback: check coaches (password = PS number)
        coaches = supabase.table("coaches").select("*").eq("ps_number", ps_number).execute()
        if coaches.data and password == ps_number:
            return {"ps_number": ps_number, "credential": "Coach", "name": ps_number}
    except Exception:
        pass
    return None

def require_login():
    if st.session_state.get("user"):
        return st.session_state["user"]

    st.subheader("Login")
    ps = st.text_input("PS Number", "")
    pw = st.text_input("Password", "", type="password")
    if st.button("Sign In"):
        user = authenticate(ps.strip(), pw.strip())
        if user:
            st.session_state["user"] = user
            st.success("Login successful.")
            st.rerun()
        else:
            st.error("Invalid credentials.")
    st.stop()

user = require_login()

# ------------------------------------------------------------
# 3) Navigation
# ------------------------------------------------------------
try:
    menu = st.segmented_control(
        "Select a section:",
        ["Submit Request", "Manage Requests", "Admin Schools"]
    )
except Exception:
    menu = st.radio(
        "Select a section:",
        ["Submit Request", "Manage Requests", "Admin Schools"],
        horizontal=True
    )

st.divider()

# ------------------------------------------------------------
# 4) Submit Request
# ------------------------------------------------------------
if menu == "Submit Request":
    st.header("Submit Request")

    schools = supabase.table("schools").select("*").execute().data or []
    materials = supabase.table("materials").select("*").execute().data or []

    if not schools:
        st.warning("No schools found.")
        st.stop()
    if not materials:
        st.warning("No materials found.")
        st.stop()

    school_options = [f"{s['nome']} ({s['id']})" for s in schools]
    school_choice = st.selectbox("Select School", school_options)
    school_id = school_choice.split("(")[-1].replace(")", "").strip()

    category = st.selectbox("Category", sorted(set(m["category"] for m in materials)))
    filtered = [m for m in materials if m["category"] == category]
    item_choice = st.selectbox("Material", [f"{m['subcategory']} {m['item']}".strip() for m in filtered])
    qty = st.number_input("Quantity", min_value=1, value=1)

    if st.button("Submit Request", type="primary"):
        data = {
            "id": str(uuid.uuid4()),
            "school_id": school_id,
            "category": category,
            "material": item_choice,
            "quantity": qty,
            "date": datetime.now().isoformat(),
            "ps_number": user["ps_number"],
            "status": "Pending"
        }
        supabase.table("requests").insert(data).execute()
        st.success("Request submitted successfully.")
        st.rerun()

# ------------------------------------------------------------
# 5) Manage Requests
# ------------------------------------------------------------
elif menu == "Manage Requests":
    st.header("Manage Requests")
    st.caption("Only Pending requests can be modified or deleted.")

    if user["credential"] == "Admin":
        query = supabase.table("requests").select("*")
    else:
        query = supabase.table("requests").select("*").eq("ps_number", user["ps_number"])

    rows = query.execute().data or []
    if not rows:
        st.info("No requests found.")
        st.stop()

    df = pd.DataFrame(rows)
    if "id" in df.columns:
        df.set_index("id", inplace=True)

    df["Delete"] = False
    st.data_editor(df, use_container_width=True)

    to_delete = st.multiselect("Select IDs to delete:", df.index)
    if st.button("Delete Selected"):
        for rid in to_delete:
            record = next((r for r in rows if r["id"] == rid), None)
            if record and record["status"] == "Pending":
                supabase.table("requests").delete().eq("id", rid).execute()
        st.success("Selected requests deleted.")
        st.rerun()

# ------------------------------------------------------------
# 6) Admin Schools
# ------------------------------------------------------------
elif menu == "Admin Schools":
    st.header("Admin Schools")
    if user["credential"] != "Admin":
        st.warning("You do not have permission to access this section.")
        st.stop()

    schools = supabase.table("schools").select("*").execute().data or []
    df = pd.DataFrame(schools)
    st.data_editor(df, use_container_width=True, disabled=True)