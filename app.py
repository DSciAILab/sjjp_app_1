# ============================================================
# SJJP Requests Portal - app.py
# Version: v3.7 (2025-11-07)
# Changelog vs v3.6:
# - Admin can edit and delete any request (no status restriction)
# - Coaches remain limited to their own Pending requests
# - "Coach PS Number" column visible only to Admin
# - Wide layout, no emojis, fully self-contained JSON persistence
# ============================================================

# ----------------------------
# 0) Imports and page config
# ----------------------------
import os
import json
from datetime import datetime
import uuid
import streamlit as st
import pandas as pd

# Configure page
st.set_page_config(page_title="SJJP - Requests Portal", layout="wide")

# ----------------------------
# 1) File paths and bootstrap
# ----------------------------
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")

FILES = {
    "users": os.path.join(DATA_DIR, "users.json"),
    "coaches": os.path.join(DATA_DIR, "coaches.json"),
    "schools": os.path.join(DATA_DIR, "schools.json"),
    "materials": os.path.join(DATA_DIR, "materials.json"),
    "requests": os.path.join(DATA_DIR, "requests.json"),
}

os.makedirs(DATA_DIR, exist_ok=True)


def ensure_json(path: str, default_content):
    """Create the JSON file with default_content if it does not exist."""
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_content, f, ensure_ascii=False, indent=2)


def load_json(path: str):
    """Load JSON safely; fallback to empty list on error."""
    try:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_json(path: str, data):
    """Save JSON prettily."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Bootstrap base data
ensure_json(
    FILES["users"],
    [{"ps_number": "PS1724", "password": "PS1724", "credential": "Admin", "name": "Administrator"}],
)
ensure_json(FILES["coaches"], [])
ensure_json(FILES["schools"], [])
ensure_json(FILES["materials"], [])
ensure_json(FILES["requests"], [])

# ----------------------------
# 2) Authentication
# ----------------------------
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
    with st.form("login_form", clear_on_submit=False):
        ps = st.text_input("PS Number", placeholder="PS1234")
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


# ----------------------------
# 3) Data utilities
# ----------------------------
def ensure_request_id_and_defaults(rows: list) -> list:
    changed = False
    for r in rows:
        if "id" not in r:
            r["id"] = str(uuid.uuid4())
            changed = True
        if "status" not in r:
            r["status"] = "Pending"
            changed = True
        if "ps_number" not in r:
            r["ps_number"] = "unknown"
            changed = True
        r["ps_number"] = str(r.get("ps_number", "unknown"))
    if changed:
        save_json(FILES["requests"], rows)
    return rows


def list_user_schools(user: dict, schools: list) -> list:
    if user["credential"] == "Admin":
        return schools
    ps = user["ps_number"]
    return [s for s in schools if ps in s.get("coaches", [])]


def materials_by_category(materials: list, category: str) -> list:
    return [m for m in materials if m.get("category") == category]


# ----------------------------
# 4) App body
# ----------------------------
user = require_login()

try:
    menu_selected = st.segmented_control(
        "Select a section:",
        ["Submit Request", "Manage Requests", "Admin Schools"],
    )
except Exception:
    menu_selected = st.radio(
        "Select a section:",
        ["Submit Request", "Manage Requests", "Admin Schools"],
        horizontal=True,
    )

st.divider()

# ----------------------------
# 4.1 Submit Request
# ----------------------------
if menu_selected == "Submit Request":
    st.header("Submit Request")

    schools = load_json(FILES["schools"])
    materials = load_json(FILES["materials"])

    if not materials:
        st.warning("No materials found.")
    if not schools:
        st.warning("No schools found.")

    visible_schools = list_user_schools(user, schools)
    school_label_map = [f"{s.get('nome','(no name)')} ({s.get('id','')})" for s in visible_schools]
    school_choice = st.selectbox("School", school_label_map) if visible_schools else None
    selected_school_id = None
    if school_choice:
        selected_school_id = school_choice.split("(")[-1].replace(")", "").strip()

    categories = sorted(set(m.get("category", "") for m in materials)) if materials else []
    category = st.selectbox("Category", categories) if categories else None
    filtered = materials_by_category(materials, category) if category else []
    sub_item_options = [f"{m.get('subcategory','')} {m.get('item','')}".strip() for m in filtered]
    material_choice = st.selectbox("Subcategory + Item", sub_item_options) if filtered else None
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
            "ps_number": str(user["ps_number"]),
            "status": "Pending"
        })
        st.success("Item added to the batch.")

    if st.session_state["pending_request"]:
        st.subheader("Current Batch")
        batch_df = pd.DataFrame(st.session_state["pending_request"]).drop(columns=["id"], errors="ignore")
        st.dataframe(batch_df, use_container_width=True)

        if st.button("Submit Request", type="primary"):
            all_requests = load_json(FILES["requests"])
            for item in st.session_state["pending_request"]:
                if "id" not in item or not item["id"]:
                    item["id"] = str(uuid.uuid4())
                all_requests.append(item)
            save_json(FILES["requests"], all_requests)
            st.success("Request submitted successfully.")
            st.session_state["pending_request"] = []
            st.rerun()

# ----------------------------
# 4.2 Manage Requests
# ----------------------------
elif menu_selected == "Manage Requests":
    st.header("Manage Requests")
    st.info("Admins can edit any request; coaches can edit only their Pending requests.")

    rows = ensure_request_id_and_defaults(load_json(FILES["requests"]))

    if user["credential"] == "Admin":
        visible = rows
    else:
        visible = [r for r in rows if r.get("ps_number") == user["ps_number"]]

    if not visible:
        st.info("No requests found.")
    else:
        df = pd.DataFrame(visible)
        if "id" in df.columns:
            df = df.drop(columns=["id"])
        # Admin sees PS number; coach does not
        if user["credential"] != "Admin" and "ps_number" in df.columns:
            df = df.drop(columns=["ps_number"])

        if "Delete" not in df.columns:
            df["Delete"] = False
        df = df[["Delete"] + [c for c in df.columns if c != "Delete"]]

        status_options = ["Pending", "Approved", "Rejected", "Delivered"]

        disabled_mask = pd.DataFrame(False, index=df.index, columns=df.columns)
        if user["credential"] != "Admin":
            is_pending = df["status"] == "Pending"
            disabled_mask.loc[~is_pending, :] = True

        column_config = {
            "status": st.column_config.SelectboxColumn("Status", options=status_options),
            "Delete": st.column_config.CheckboxColumn("Delete")
        }

        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            column_config=column_config,
            disabled=disabled_mask,
            hide_index=True,
        )

        if st.button("Delete Selected Items", type="secondary"):
            to_delete_indices = edited_df.index[edited_df["Delete"] == True].tolist()
            to_delete_ids = set([visible[i]["id"] for i in to_delete_indices])
            kept = []
            for r in rows:
                can_see = (user["credential"] == "Admin") or (r.get("ps_number") == user["ps_number"])
                is_sel = r.get("id") in to_delete_ids
                if is_sel and can_see:
                    if user["credential"] != "Admin" and r.get("status") != "Pending":
                        kept.append(r)
                    continue
                kept.append(r)
            save_json(FILES["requests"], kept)
            st.success(f"Deleted {len(to_delete_ids)} request(s).")
            st.rerun()

        if st.button("Save Changes", type="primary"):
            by_id = {r["id"]: r for r in rows}
            for idx, er in edited_df.iterrows():
                rid = visible[idx]["id"]
                if not rid or rid not in by_id:
                    continue
                original = by_id[rid]
                can_see = (user["credential"] == "Admin") or (original.get("ps_number") == user["ps_number"])
                if not can_see:
                    continue
                if user["credential"] != "Admin" and original.get("status") != "Pending":
                    continue
                for k in ["school_id", "category", "material", "quantity", "status", "date"]:
                    if k in er:
                        original[k] = er[k]
                by_id[rid] = original
            save_json(FILES["requests"], list(by_id.values()))
            st.success("Changes saved successfully.")
            st.rerun()

# ----------------------------
# 4.3 Admin Schools
# ----------------------------
elif menu_selected == "Admin Schools":
    st.header("Admin Schools")
    if user["credential"] != "Admin":
        st.warning("You do not have permission to access this section.")
        st.stop()

    schools = load_json(FILES["schools"])
    if not schools:
        st.info("No schools found. Use the editor below to add entries.")

    df = pd.DataFrame(schools) if schools else pd.DataFrame(columns=["id", "nome", "city", "coaches"])
    st.subheader("Schools Table")
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id": st.column_config.TextColumn("ID"),
            "nome": st.column_config.TextColumn("Name"),
            "city": st.column_config.TextColumn("City"),
            "coaches": st.column_config.ListColumn("Coaches (PS Numbers)"),
        },
    )

    if st.button("Save Changes"):
        clean = edited_df.fillna("").to_dict(orient="records")
        for s in clean:
            if not isinstance(s.get("coaches"), list):
                raw = s.get("coaches", "")
                if isinstance(raw, str) and raw.strip():
                    s["coaches"] = [x.strip() for x in raw.split(",")]
                else:
                    s["coaches"] = []
        save_json(FILES["schools"], clean)
        st.success("Schools updated successfully.")
        st.rerun()
