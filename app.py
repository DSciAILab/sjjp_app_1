# ============================================================
# SJJP Requests Portal - app.py
# Version: v3.8 (2025-11-08)
# ============================================================
# Changelog:
# ✅ Hybrid mode (local + cloud)
# ✅ Supabase integration (read/write)
# ✅ Admin-only “Sync Local Data to Cloud” button
# ✅ Local fallback if Supabase unavailable
# ✅ Clean, minimal, English UI
# ============================================================

import os
import json
import uuid
from datetime import datetime
import streamlit as st
import pandas as pd

# Optional cloud imports
try:
    from supabase import create_client
except ImportError:
    create_client = None

# ============================================================
# 1) Configuration
# ============================================================

st.set_page_config(page_title="SJJP - Requests Portal", layout="wide")

MODE = "local"  # options: "local" or "cloud"

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

FILES = {
    "users": os.path.join(DATA_DIR, "users.json"),
    "coaches": os.path.join(DATA_DIR, "coaches.json"),
    "schools": os.path.join(DATA_DIR, "schools.json"),
    "materials": os.path.join(DATA_DIR, "materials.json"),
    "requests": os.path.join(DATA_DIR, "requests.json"),
}

def ensure_json(path: str, default_content):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_content, f, ensure_ascii=False, indent=2)

def load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

ensure_json(FILES["users"], [{"ps_number": "PS1724", "password": "PS1724", "credential": "Admin", "name": "Administrator"}])
ensure_json(FILES["coaches"], [])
ensure_json(FILES["schools"], [])
ensure_json(FILES["materials"], [])
ensure_json(FILES["requests"], [])

# ============================================================
# 2) Supabase connection (if available)
# ============================================================

def get_supabase_client():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception:
        return None

supabase = get_supabase_client() if MODE == "cloud" and create_client else None

def supabase_enabled():
    return supabase is not None

# ============================================================
# 3) Authentication
# ============================================================

def authenticate(ps_number: str, password: str):
    users = load_json(FILES["users"])
    for u in users:
        if u.get("ps_number") == ps_number and u.get("password") == password:
            return {"ps_number": u["ps_number"], "credential": u.get("credential", "Coach"), "name": u.get("name", u["ps_number"])}
    coaches = load_json(FILES["coaches"])
    for c in coaches:
        if c.get("ps_number") == ps_number and password == ps_number:
            return {"ps_number": c["ps_number"], "credential": "Coach", "name": c.get("name", c["ps_number"])}
    return None

def require_login():
    if st.session_state.get("user"):
        return st.session_state["user"]
    st.header("Login")
    with st.form("login_form"):
        ps = st.text_input("PS Number")
        pw = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign In")
    if submitted:
        user = authenticate(ps.strip(), pw.strip())
        if user:
            st.session_state["user"] = user
            st.success("Signed in successfully.")
            st.rerun()
        else:
            st.error("Invalid PS Number or password.")
    st.stop()

user = require_login()

# ============================================================
# 4) Utility functions
# ============================================================

def ensure_request_id(rows):
    changed = False
    for r in rows:
        if "id" not in r:
            r["id"] = str(uuid.uuid4())
            changed = True
        if "status" not in r:
            r["status"] = "Pending"
            changed = True
    if changed:
        save_json(FILES["requests"], rows)
    return rows

def list_user_schools(user, schools):
    if user["credential"] == "Admin":
        return schools
    ps = user["ps_number"]
    return [s for s in schools if ps in s.get("coaches", [])]

def materials_by_category(materials, category):
    return [m for m in materials if m.get("category") == category]

# ============================================================
# 5) Cloud Sync logic
# ============================================================

def sync_to_cloud():
    if not supabase_enabled():
        st.warning("Supabase is not configured.")
        return
    local_data = load_json(FILES["requests"])
    if not local_data:
        st.info("No local data to sync.")
        return

    existing = supabase.table("requests").select("id").execute()
    existing_ids = {x["id"] for x in existing.data}

    to_upload = [r for r in local_data if r["id"] not in existing_ids]
    if not to_upload:
        st.info("No new requests to upload.")
        return

    try:
        for r in to_upload:
            supabase.table("requests").insert(r).execute()
        st.success(f"Synchronized {len(to_upload)} new request(s) to cloud.")
    except Exception as e:
        st.error(f"Error during sync: {e}")

# ============================================================
# 6) Navigation (segmented control)
# ============================================================

try:
    menu = st.segmented_control(
        "Select a section:",
        ["Submit Request", "Manage Requests", "Admin Schools"],
    )
except Exception:
    menu = st.radio(
        "Select a section:",
        ["Submit Request", "Manage Requests", "Admin Schools"],
        horizontal=True,
    )

st.divider()

# ============================================================
# 7) Submit Request
# ============================================================

if menu == "Submit Request":
    st.header("Submit Request")

    schools = load_json(FILES["schools"])
    materials = load_json(FILES["materials"])
    visible_schools = list_user_schools(user, schools)

    school_label_map = [f"{s.get('nome','')} ({s.get('id','')})" for s in visible_schools]
    school_choice = st.selectbox("School", school_label_map) if visible_schools else None
    selected_school_id = school_choice.split("(")[-1].replace(")", "").strip() if school_choice else None

    categories = sorted(set(m.get("category", "") for m in materials))
    category = st.selectbox("Category", categories)
    filtered = materials_by_category(materials, category)
    sub_item_options = [f"{m.get('subcategory','')} {m.get('item','')}".strip() for m in filtered]
    material_choice = st.selectbox("Material (subcategory + item)", sub_item_options)
    qty = st.number_input("Quantity", min_value=1, value=1, step=1)

    if "pending_request" not in st.session_state:
        st.session_state["pending_request"] = []

    if st.button("Add Another Item", type="secondary", disabled=not (selected_school_id and material_choice)):
        st.session_state["pending_request"].append({
            "id": str(uuid.uuid4()),
            "school_id": selected_school_id,
            "category": category,
            "material": material_choice,
            "quantity": int(qty),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ps_number": user["ps_number"],
            "status": "Pending",
        })
        st.success("Item added to batch.")

    if st.session_state["pending_request"]:
        st.subheader("Current Batch")
        df = pd.DataFrame(st.session_state["pending_request"])
        st.dataframe(df.drop(columns=["id"]), use_container_width=True)

        if st.button("Submit Request", type="primary"):
            all_requests = load_json(FILES["requests"])
            all_requests.extend(st.session_state["pending_request"])
            save_json(FILES["requests"], all_requests)
            st.session_state["pending_request"] = []
            st.success("Request submitted successfully.")
            st.rerun()

# ============================================================
# 8) Manage Requests
# ============================================================

elif menu == "Manage Requests":
    st.header("Manage Requests")
    st.info("Only 'Pending' requests can be modified or deleted.")

    rows = load_json(FILES["requests"])
    rows = ensure_request_id(rows)

    if user["credential"] == "Admin":
        visible = rows
    else:
        visible = [r for r in rows if r.get("ps_number") == user["ps_number"]]

    if not visible:
        st.info("No requests found.")
    else:
        df = pd.DataFrame(visible)
        df = df.drop(columns=["ps_number", "id"], errors="ignore")
        if "Delete" not in df.columns:
            df["Delete"] = False

        status_options = ["Pending", "Approved", "Rejected", "Delivered"]
        disabled_mask = pd.DataFrame(False, index=df.index, columns=df.columns)
        is_pending = df["status"] == "Pending"
        disabled_mask.loc[~is_pending, :] = True

        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            disabled=disabled_mask,
            hide_index=True,
        )

        if st.button("Delete Selected"):
            to_delete_indices = edited_df.index[edited_df["Delete"] == True].tolist()
            to_delete_ids = {visible[i]["id"] for i in to_delete_indices}
            kept = [
                r for r in rows
                if not (r["id"] in to_delete_ids and (user["credential"] == "Admin" or r["ps_number"] == user["ps_number"]) and r["status"] == "Pending")
            ]
            save_json(FILES["requests"], kept)
            st.success(f"Deleted {len(to_delete_ids)} request(s).")
            st.rerun()

        if st.button("Save Changes", type="primary"):
            by_id = {r["id"]: r for r in rows}
            for idx, er in edited_df.iterrows():
                rid = visible[idx]["id"]
                original = by_id.get(rid)
                if not original:
                    continue
                if user["credential"] != "Admin" and original["ps_number"] != user["ps_number"]:
                    continue
                if original["status"] != "Pending" and user["credential"] != "Admin":
                    continue
                for k in ["school_id", "category", "material", "quantity", "status", "date"]:
                    if k in er:
                        original[k] = er[k]
                by_id[rid] = original
            save_json(FILES["requests"], list(by_id.values()))
            st.success("Changes saved.")
            st.rerun()

# ============================================================
# 9) Admin Schools
# ============================================================

elif menu == "Admin Schools":
    st.header("Admin Schools")
    if user["credential"] != "Admin":
        st.warning("Access denied.")
        st.stop()

    schools = load_json(FILES["schools"])
    df = pd.DataFrame(schools) if schools else pd.DataFrame(columns=["id", "nome", "city", "coaches"])
    st.subheader("Schools Table")
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    if st.button("Save Schools"):
        clean = edited_df.fillna("").to_dict(orient="records")
        for s in clean:
            if not isinstance(s.get("coaches"), list):
                raw = s.get("coaches", "")
                if isinstance(raw, str):
                    s["coaches"] = [x.strip() for x in raw.split(",") if x.strip()]
                else:
                    s["coaches"] = []
        save_json(FILES["schools"], clean)
        st.success("Schools saved.")
        st.rerun()

# ============================================================
# 10) Admin-only: Sync to Cloud
# ============================================================

if user["credential"] == "Admin" and MODE == "local":
    st.divider()
    st.subheader("Cloud Synchronization")
    if st.button("Sync Local Data to Cloud"):
        sync_to_cloud()
