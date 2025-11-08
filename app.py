# ============================================================
# SJJP - Supabase Connection Test
# Version: v1.0 (2025-11-09)
# ============================================================

import streamlit as st
from supabase import create_client

st.set_page_config(page_title="SJJP - Supabase Test", layout="centered")

st.title("🔍 Supabase Connection Test")
st.write("This page verifies if the Streamlit app is correctly connected to your Supabase project.")

# ============================================================
# 1️⃣ Load credentials from Streamlit Secrets
# ============================================================

try:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    st.success("✅ Secrets loaded successfully.")
except Exception as e:
    st.error(f"❌ Could not read Supabase secrets: {e}")
    st.stop()

# ============================================================
# 2️⃣ Try to connect to Supabase
# ============================================================

try:
    supabase = create_client(url, key)
    st.success("✅ Connected to Supabase.")
except Exception as e:
    st.error(f"❌ Connection failed: {e}")
    st.stop()

# ============================================================
# 3️⃣ Attempt to read from a test table
# ============================================================

st.write("Now checking if the table `requests` exists...")

try:
    data = supabase.table("requests").select("*").limit(5).execute()
    rows = data.data
    if rows:
        st.success(f"✅ Connection successful. Found {len(rows)} record(s) in `requests`.")
        st.json(rows)
    else:
        st.info("🟡 Connected, but no records found in `requests` table.")
except Exception as e:
    st.warning(f"⚠️ Could not access table `requests`: {e}")

# ============================================================
# 4️⃣ Debug info
# ============================================================

with st.expander("🔧 Debug Info"):
    st.write("Supabase URL:", url)
    st.write("Supabase Key (first 10 chars):", key[:10] + "..." if key else "(missing)")