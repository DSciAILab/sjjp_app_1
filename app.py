# ============================================================
# SJJP Requests Portal - Supabase Integrated Version
# Version: v4.0 (2025-11-09)
# ============================================================

import os
import json
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
# 1) Initialize Supabase connection (via Streamlit Secrets)
# ------------------------------------------------------------
SUPABASE_URL = None
SUPABASE_KEY = None
supabase: Client | None = None

try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    st.session_state["supabase_connected"] = True
except Exception:
    st.session_state["supabase_connected"] = False

if not st.session_state["supabase_connected"]:
    st.error("Supabase is not configured. Please check your Streamlit Secrets.")
    st.stop()

# ------------------------------------------------------------
# 2) Authentication
# ------------------------------------------------------------
def authenticate(ps_number: str, password: str):
    users = supabase.table("users").select("*").eq("ps_number", ps_number).execute()
    data = users.data
    if data:
        user = data[0]
        if user.get("password") == password:
            return user
    # Fallback: coaches table
    coaches = supabase.table("coaches").select("*").eq("ps_number", ps_number).execute()
    if coaches.data and password == ps_number:
        return {"ps_number": ps_number, "credential": "Coach", "name": ps_number}
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

    # Fetch materials and schools from Supabase
    schools = supabase.table("schools").select("*").execute().data
    materials = supabase.table("materials").select("*").execute().data

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

    # Load requests (admin sees all)
    if user["credential"] == "Admin":
        query = supabase.table("requests").select("*")
    else:
        query = supabase.table("requests").select("*").eq("ps_number", user["ps_number"])

    rows = query.execute().data
    if not rows:
        st.info("No requests found.")
        st.stop()

    df = pd.DataFrame(rows)
    if "id" in df.columns:
        df.set_index("id", inplace=True)

    df["Delete"] = False
    st.dataframe(df, use_container_width=True)

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