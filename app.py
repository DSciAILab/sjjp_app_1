# ============================================================
# SJJP Requests Portal - app.py
# Version: v3.6 (2025-11-07)
# Changelog vs v3.5:
# - Restored full script after accidental truncation.
# - Single-page app with segmented control (no sidebar nav).
# - Robust JSON persistence with automatic file creation.
# - Requests now have stable "id" for reliable edit/delete.
# - "Manage Requests": shows role-filtered rows; only Pending rows are editable/deletable.
# - Minimal, clean English UI; wide layout; no emojis.
# ============================================================

# ----------------------------
# 0) Imports and page config
# ----------------------------
import os  # file checks
import json  # JSON read/write
from datetime import datetime  # timestamp for requests
import uuid  # stable IDs for rows
import streamlit as st  # Streamlit core
import pandas as pd  # tabular views

# Configure page (must be first Streamlit call)
st.set_page_config(page_title="SJJP - Requests Portal", layout="wide")  # wide layout for tables

# ----------------------------
# 1) File paths and bootstrap
# ----------------------------
BASE_DIR = os.path.dirname(__file__)  # folder of app.py
DATA_DIR = os.path.join(BASE_DIR, "data")  # JSON directory

# Central registry of JSON files used by the app
FILES = {
    "users": os.path.join(DATA_DIR, "users.json"),
    "coaches": os.path.join(DATA_DIR, "coaches.json"),
    "schools": os.path.join(DATA_DIR, "schools.json"),
    "materials": os.path.join(DATA_DIR, "materials.json"),
    "requests": os.path.join(DATA_DIR, "requests.json"),
}

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

def ensure_json(path: str, default_content):
    """Create the JSON file with default_content if it does not exist."""
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_content, f, ensure_ascii=False, indent=2)

def load_json(path: str):
    """Load JSON safely; create with sensible default when missing/corrupted."""
    try:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # Fallback in case of corrupted file
        return []

def save_json(path: str, data):
    """Persist JSON prettily."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Bootstrap minimal files
ensure_json(FILES["users"], [
    # Default admin user (PS1724 / PS1724)
    {"ps_number": "PS1724", "password": "PS1724", "credential": "Admin", "name": "Administrator"}
])
ensure_json(FILES["coaches"], [])           # optional: mirror of coaches directory if you want
ensure_json(FILES["schools"], [])           # expects objects: {id, nome, city, coaches:[PS...]}
ensure_json(FILES["materials"], [])         # expects objects: {category, subcategory, item}
ensure_json(FILES["requests"], [])          # will store list of request items with id/status

# ----------------------------
# 2) Authentication helpers
# ----------------------------
def authenticate(ps_number: str, password: str):
    """Authenticate user first against users.json, then coaches.json (coach pass == PS)."""
    users = load_json(FILES["users"])
    # Check users.json
    for u in users:
        if u.get("ps_number") == ps_number and u.get("password") == password:
            return {"ps_number": u["ps_number"], "credential": u.get("credential", "Coach"), "name": u.get("name", u["ps_number"])}

    # Fallback to coaches.json where password is the PS itself
    coaches = load_json(FILES["coaches"])
    for c in coaches:
        if c.get("ps_number") == ps_number and password == ps_number:
            return {"ps_number": c["ps_number"], "credential": "Coach", "name": c.get("name", c["ps_number"])}

    return None  # invalid credentials

def require_login():
    """Render login UI if not logged in; return user dict when logged."""
    if st.session_state.get("user"):
        return st.session_state["user"]

    st.header("Login")
    with st.form("login_form", clear_on_submit=False):
        ps = st.text_input("PS Number", value="", placeholder="PS1234")
        pw = st.text_input("Password", value="", type="password")
        submitted = st.form_submit_button("Sign In")
    if submitted:
        user = authenticate(ps.strip(), pw.strip())
        if user:
            st.session_state["user"] = user
            st.success("Signed in successfully.")
            st.rerun()
        else:
            st.error("Invalid PS Number or password.")
    st.stop()  # do not render the rest if not authenticated

# ----------------------------
# 3) Data utilities
# ----------------------------
def ensure_request_id_and_defaults(rows: list) -> list:
    """Ensure each request row has an 'id' and required default fields."""
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
        # Normalize ps_number to string
        r["ps_number"] = str(r.get("ps_number", "unknown"))
    if changed:
        save_json(FILES["requests"], rows)
    return rows

def list_user_schools(user: dict, schools: list) -> list:
    """Return schools visible to the user (Admin: all; Coach: assigned only)."""
    if user["credential"] == "Admin":
        return schools
    ps = user["ps_number"]
    return [s for s in schools if ps in s.get("coaches", [])]

def materials_by_category(materials: list, category: str) -> list:
    """Filter materials of a given category."""
    return [m for m in materials if m.get("category") == category]

# ----------------------------
# 4) App body (single page)
# ----------------------------
user = require_login()  # enforce login; returns dict with ps_number/credential/name

# Segmented control for single-page navigation (fallback to radio if segmented_control is not available)
try:
    menu_selected = st.segmented_control(
        "Select a section:",
        ["Submit Request", "Manage Requests", "Admin Schools"]
    )
except Exception:
    menu_selected = st.radio(
        "Select a section:",
        ["Submit Request", "Manage Requests", "Admin Schools"],
        horizontal=True
    )

st.divider()  # visual separation

# ----------------------------
# 4.1) Submit Request (batch mode)
# ----------------------------
if menu_selected == "Submit Request":
    st.header("Submit Request")

    # Load data
    schools = load_json(FILES["schools"])
    materials = load_json(FILES["materials"])

    # Validate data presence
    if not materials:
        st.warning("No materials found. Please populate data/materials.json.")
    if not schools:
        st.warning("No schools found. Please populate data/schools.json.")

    visible_schools = list_user_schools(user, schools)

    # School selector
    school_label_map = [f"{s.get('nome','(no name)')} ({s.get('id','')})" for s in visible_schools]
    school_choice = st.selectbox("School", school_label_map) if visible_schools else None
    selected_school_id = None
    if school_choice:
        selected_school_id = school_choice.split("(")[-1].replace(")", "").strip()

    # Category + Material selection
    categories = sorted(set(m.get("category", "") for m in materials)) if materials else []
    category = st.selectbox("Category", categories) if categories else None
    filtered = materials_by_category(materials, category) if category else []
    sub_item_options = [f"{m.get('subcategory','')} {m.get('item','')}".strip() for m in filtered]
    material_choice = st.selectbox("Subcategory + Item", sub_item_options) if filtered else None
    qty = st.number_input("Quantity", min_value=1, value=1, step=1)

    # Initialize pending cart in session
    if "pending_request" not in st.session_state:
        st.session_state["pending_request"] = []

    # Add Another Item
    if st.button("Add Another Item", type="secondary", disabled=not (selected_school_id and material_choice)):
        st.session_state["pending_request"].append({
            "id": str(uuid.uuid4()),                                # temp id for batch table; final will be preserved
            "school_id": selected_school_id,
            "category": category,
            "material": material_choice,
            "quantity": int(qty),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ps_number": str(user["ps_number"]),
            "status": "Pending"
        })
        st.success("Item added to the current request batch.")

    # Show the current batch items
    if st.session_state["pending_request"]:
        st.subheader("Current Batch")
        batch_df = pd.DataFrame(st.session_state["pending_request"])
        if "id" in batch_df.columns:
            batch_df = batch_df.drop(columns=["id"])
        st.dataframe(batch_df, use_container_width=True)

        # Submit Request (save all)
        if st.button("Submit Request", type="primary"):
            all_requests = load_json(FILES["requests"])
            # Ensure IDs exist and append
            for item in st.session_state["pending_request"]:
                if "id" not in item or not item["id"]:
                    item["id"] = str(uuid.uuid4())
                # Normalize again
                item["ps_number"] = str(user["ps_number"])
                item["status"] = item.get("status", "Pending") or "Pending"
                all_requests.append(item)
            save_json(FILES["requests"], all_requests)
            st.success("Request submitted successfully.")
            # Clear batch
            st.session_state["pending_request"] = []
            st.rerun()

# ----------------------------
# 4.2) Manage Requests (edit/delete with Pending constraint)
# ----------------------------
elif menu_selected == "Manage Requests":
    st.header("Manage Requests")
    st.info("Only requests with status 'Pending' can be modified or deleted.")

    # Load and normalize requests
    rows = load_json(FILES["requests"])
    rows = ensure_request_id_and_defaults(rows)

    # Role-agnostic filtering: users see only their own requests
    visible = [r for r in rows if r.get("ps_number") == user["ps_number"]]

    st.info(f"Showing {len(visible)} requests.")

    if not visible:
        st.info("No requests found to display.")
    else:
        # Build dataframe from visible rows. Keep 'id' (read-only) but hide 'ps_number'.
        df = pd.DataFrame(visible)
        if "ps_number" in df.columns:
            df = df.drop(columns=["ps_number"])
        # Keep 'id' so we can merge edits by id reliably; it will be shown read-only.

        # Ensure Delete column exists (checkboxes)
        if "Delete" not in df.columns:
            df["Delete"] = False

        # Move Delete to first column for visibility
        cols = ["Delete"] + [c for c in df.columns if c != "Delete"]
        df = df[cols]

        # Status select options
        status_options = ["Pending", "Approved", "Rejected", "Delivered"]

        # Build per-cell disabled mask: default all disabled, then enable specific columns for Pending rows
        disabled_mask = pd.DataFrame(True, index=df.index, columns=df.columns)
        is_pending = df["status"] == "Pending"
        # Columns we want editable for Pending rows
        editable_cols = [c for c in ["Delete", "status", "quantity", "material", "category", "school_id", "date"] if c in df.columns]
        for col in editable_cols:
            disabled_mask.loc[is_pending, col] = False

        # Use modern column_config API without emojis; help text for clarity
        # Configure columns: make 'id' read-only text, status as select, Delete as checkbox
        column_config = {
            "id": st.column_config.TextColumn("ID", help="Internal id", disabled=True),
            "status": st.column_config.SelectboxColumn("Status", options=status_options, help="Change status only for pending requests"),
            "Delete": st.column_config.CheckboxColumn("Delete", help="Mark to delete pending request")
        }

        # Editable grid with hide_index and improved row selectability
        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            column_config=column_config,
            disabled=disabled_mask,
            hide_index=True
        )

        # Delete selected
        if st.button("Delete Selected Items", type="secondary"):
            # Collect ids directly from the edited dataframe for rows marked Delete=True
            to_delete_ids = set()
            if "Delete" in edited_df.columns and "id" in edited_df.columns:
                for _, row in edited_df.iterrows():
                    try:
                        if bool(row.get("Delete", False)):
                            rid = row.get("id")
                            if rid:
                                to_delete_ids.add(rid)
                    except Exception:
                        continue

            if not to_delete_ids:
                st.warning("No requests selected for deletion.")
            else:
                # Only delete rows that are Pending (and within visibility/permission)
                kept = []
                for r in rows:
                    can_see = (r.get("ps_number") == user["ps_number"])  # only own requests
                    is_sel = r.get("id") in to_delete_ids
                    if is_sel and can_see and r.get("status") == "Pending":
                        # skip (delete)
                        continue
                    kept.append(r)
                save_json(FILES["requests"], kept)
                st.success(f"Deleted {len(to_delete_ids)} request(s).")
                st.rerun()

        # Save changes
        if st.button("Save Changes", type="primary"):
            # Merge changes by id; only apply to Pending rows within permissions
            by_id = {r["id"]: r for r in rows}

            # First, collect ids marked for deletion directly from the edited dataframe
            to_delete_ids = set()
            if "Delete" in edited_df.columns and "id" in edited_df.columns:
                for _, er in edited_df.iterrows():
                    try:
                        if bool(er.get("Delete", False)):
                            rid = er.get("id")
                            if rid:
                                to_delete_ids.add(rid)
                    except Exception:
                        continue

            # Apply edits
            for _, er in edited_df.iterrows():
                # Use the 'id' value from the edited row to map back to the original
                rid = er.get("id") if "id" in er else None
                if not rid or rid not in by_id:
                    # Row added in the editor or can't be mapped -> skip
                    continue
                # If this id is marked for deletion, skip applying edits
                if rid in to_delete_ids:
                    continue

                original = by_id[rid]
                can_see = (original.get("ps_number") == user["ps_number"])  # only own requests
                if not can_see:
                    continue
                if original.get("status") != "Pending":
                    # Only Pending rows are editable
                    continue

                # Apply allowed fields back (ignore the Delete column)
                for k in ["school_id", "category", "material", "quantity", "status", "date"]:
                    if k in er:
                        original[k] = er[k]
                by_id[rid] = original

            # Remove deleted ids from the persisted data (respect Pending + permission rules)
            if to_delete_ids:
                # Only actually delete those that are Pending and visible to the user
                deletable = set()
                for r in rows:
                    if r.get("id") in to_delete_ids:
                        can_see = (r.get("ps_number") == user["ps_number"])  # only own requests
                        if can_see and r.get("status") == "Pending":
                            deletable.add(r.get("id"))
                for d in deletable:
                    by_id.pop(d, None)

            # Persist merged list
            save_json(FILES["requests"], list(by_id.values()))
            st.success("Changes saved successfully.")
            st.rerun()

# ----------------------------
# 4.3) Admin Schools (admin only)
# ----------------------------
elif menu_selected == "Admin Schools":
    st.header("Admin Schools")
    if user["credential"] != "Admin":
        st.warning("You do not have permission to access this section.")
        st.stop()

    schools = load_json(FILES["schools"])
    if not schools:
        st.info("No schools found. Use the editor below to add entries.")

    # Present editor
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
            "coaches": st.column_config.ListColumn("Coaches (PS Numbers)")
        }
    )

    if st.button("Save Changes"):
        # Convert NaN to valid Python types
        clean = edited_df.fillna("").to_dict(orient="records")
        # Ensure 'coaches' is a list
        for s in clean:
            if not isinstance(s.get("coaches"), list):
                # Try to parse comma-separated
                raw = s.get("coaches", "")
                if isinstance(raw, str) and raw.strip():
                    s["coaches"] = [x.strip() for x in raw.split(",")]
                else:
                    s["coaches"] = []
        save_json(FILES["schools"], clean)
        st.success("Schools updated successfully.")
        st.rerun()
