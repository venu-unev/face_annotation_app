"""
Face Identity Annotation Tool
==============================
A Streamlit app for collecting human annotations on face pair identity verification.
Saves results to Google Sheets in real-time.

Usage:
    streamlit run app.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent


# =============================================================================
# CONFIGURATION - Edit these settings as needed
# =============================================================================

# Google Sheets settings
SPREADSHEET_ID = "1BIwI9Q7m1bXQ-LyMPZx7yzg9w6mq5Lkgb3Gvgq3xKXU"
CREDENTIALS_FILE = "credentials.json"  # Path to your service account JSON

# Data settings
PAIRS_CSV = "pairs.csv"
IMAGE_BASE_PATH = "images/"

# If using URLs for images (e.g., from a server), set this to True
USE_IMAGE_URLS = False
IMAGE_URL_BASE = "https://yourserver.com/images/"  # Base URL if using URLs

# Validation settings
MIN_NAME_LENGTH = 5
MIN_EXPLANATION_LENGTH = 20

# Super user(s): review everything without explanations
SUPER_USERS = {"venus"}


# =============================================================================
# GOOGLE SHEETS FUNCTIONS
# =============================================================================

@st.cache_resource
def get_google_sheet():
    """Connect to Google Sheets."""
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        # Try to load credentials from file or Streamlit secrets
        if os.path.exists(CREDENTIALS_FILE):
            creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        elif hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"], scopes=scopes
            )
        else:
            st.error("No credentials found. Please add credentials.json file.")
            return None

        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1

        # Initialize headers if sheet is empty
        if not sheet.get_all_values():
            headers = [
                "timestamp", "annotator_id", "pair_index", "image_a", "image_b",
                "ground_truth", "celeb_id", "human_decision", "initial_explanation",
                "is_correct", "followup_explanation"
            ]
            sheet.append_row(headers)

        return sheet
    except Exception as e:
        st.error(f"Could not connect to Google Sheets: {e}")
        return None


def save_annotation(sheet, annotation_data):
    """Save a single annotation to Google Sheets."""
    if sheet is None:
        st.error("Cannot save annotation: Google Sheets is not available.")
        return False

    try:
        row = [
            annotation_data.get("timestamp", ""),
            annotation_data.get("annotator_id", ""),
            annotation_data.get("pair_index", ""),
            annotation_data.get("image_a", ""),
            annotation_data.get("image_b", ""),
            annotation_data.get("ground_truth", ""),
            annotation_data.get("celeb_id", ""),
            annotation_data.get("human_decision", ""),
            annotation_data.get("initial_explanation", ""),
            annotation_data.get("is_correct", ""),
            annotation_data.get("followup_explanation", "")
        ]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"Error saving annotation: {e}")
        return False


def get_completed_pairs(sheet, annotator_id):
    """Get list of pair indices already completed by this annotator from Google Sheets."""
    if sheet is None or not annotator_id:
        return []
    try:
        records = sheet.get_all_records()
        completed = []
        for r in records:
            if r.get("annotator_id") == annotator_id:
                try:
                    completed.append(int(r["pair_index"]))
                except (ValueError, TypeError, KeyError):
                    continue
        return completed
    except Exception:
        return []


# =============================================================================
# DATA LOADING
# =============================================================================

@st.cache_data
def load_pairs():
    """Load image pairs from CSV."""
    try:
        df = pd.read_csv(PAIRS_CSV)
        return df
    except Exception as e:
        st.error(f"Could not load pairs CSV: {e}")
        return None


def get_image_path(filename):
    """Get the full path or URL for an image."""
    if USE_IMAGE_URLS:
        return IMAGE_URL_BASE + str(filename)
    return os.path.join(IMAGE_BASE_PATH, str(filename))


def infer_dataset_prefix(filename: str) -> str:
    """Infer dataset name from filename prefix (best-effort)."""
    if not isinstance(filename, str):
        return "unknown"
    if filename.startswith("celeba_"):
        return "celeba"
    if filename.startswith("casia_"):
        return "casia"
    if filename.startswith("vggface2_"):
        return "vggface2"
    if filename.startswith("lfw_"):
        return "lfw"
    return "other"


# =============================================================================
# UI COMPONENTS
# =============================================================================

def ensure_local_progress_initialized(sheet, pairs_df):
    """
    Ensure st.session_state.completed_local exists and is initialized from
    Google Sheets for the current annotator (hybrid model).
    """
    annotator_id = st.session_state.annotator_id
    if "completed_local" not in st.session_state:
        if annotator_id and sheet is not None:
            from_sheet = get_completed_pairs(sheet, annotator_id)
            st.session_state.completed_local = set(from_sheet)
        else:
            st.session_state.completed_local = set()

    # Optionally enforce only valid indices
    valid_indices = set(pairs_df["index"].tolist())
    st.session_state.completed_local = {
        i for i in st.session_state.completed_local if i in valid_indices
    }


def show_instructions(pairs_df, sheet):
    """Display the instructions page."""

    st.markdown("""
# Face Identity Annotation Task

Decide if two face photos show the **Same person** or **Different people**, then write **1–3 sentences** explaining *which facial evidence* supports your choice.
""")

    # Compact workflow + key rule
    c1, c2 = st.columns([1.1, 1.2], gap="large")

    with c1:
        st.markdown("""
### Workflow (fast checklist)
1. Compare both faces (side-by-side).
2. Choose **Same** or **Different**.
3. Justify using **specific facial parts** (not vague impressions).
4. If feedback disagrees, reflect on what you missed.
""")

    with c2:
        st.markdown("""
### Key rule
Prefer **stable structure** over changeable appearance.

**Structure (good evidence):** face shape, jawline, cheekbones, eye spacing, nose/lip shape, ears  
**Appearance (weak evidence):** hair, makeup, lighting, expression, camera angle, image quality
""")

    st.markdown("---")

    # Image + context, compact side-by-side
    img_path = Path("types/image.jpeg")
    ic1, ic2 = st.columns([1, 1.2], gap="large")

    with ic1:
        if img_path.exists():
            st.image(str(img_path), use_container_width=True)
            st.caption("Reference: facial regions that often carry identity signal.")
        else:
            st.error("Instruction image `image.jpeg` not found in app directory.")

    with ic2:
        st.markdown("""
### Use this guide while comparing
When deciding, actively check **multiple** regions shown in the diagram:

- **Eyes & brows:** spacing, brow shape, eyelid fold, lash line
- **Nose:** bridge width, tip shape, nostril shape
- **Mouth & lips:** lip thickness, cupid’s bow, mouth corners
- **Face structure:** jawline, chin shape, cheekbone prominence
- **Ears (high value):** outer rim shape, earlobe attachment

Aim to cite **2–4 concrete cues** in your explanation.
""")

        # --- Visual reference grid: facial feature types ---
    st.markdown("### Visual references (use these while annotating)")
    st.caption(
        "While comparing a pair, actively cross-check these example feature types (eyes, nose, chin, face shape). "
        "They are intended to help you describe *specific* differences or matches."
    )

    types_paths = [
        ("Eyes", Path("types/eyes.jpg")),
        ("Nose", Path("types/nose.png")),
        ("Chin", Path("types/chin.jpg")),
        ("Face shape", Path("types/face.jpg")),
    ]

    # 2x2 grid (change to 3 or 4 columns if you want it tighter)
    cols = st.columns(2, gap="medium")
    for i, (label, p) in enumerate(types_paths):
        with cols[i % 2]:
            if p.exists():
                st.image(str(p), caption=label, use_container_width=True)
            else:
                st.warning(f"Missing: {p}")

    st.markdown("---")

    # Examples: Same vs Different
    e1, e2 = st.columns(2, gap="large")

    with e1:
        st.markdown("""
### Example — Same person (strong)
> “Same person. The eye spacing and brow shape match closely, and the nose bridge width with the nostril shape is consistent. Despite lighting differences, the jawline contour and chin shape align.”
""")

    with e2:
        st.markdown("""
### Example — Different people (strong)
> “Different people. The nose tip and nostril shape differ (one is narrower with a sharper tip), and the eye spacing is noticeably wider in the second image. The jawline is more angular in the first face, while the second has a rounder chin and fuller cheeks.”
""")

    with st.expander("Optional tips for tricky cases"):
        st.markdown("""
- If one image is low quality or angled, **downweight** surface details and rely more on **global structure** (jaw/chin/cheekbones).
- Don’t over-trust hairline, beard, makeup, or expression.
- If uncertain, explain what conflicts (e.g., “eyes match but jawline differs”).
""")

    st.divider()

    # If we already have an annotator, show their progress
    if st.session_state.annotator_id:
        ensure_local_progress_initialized(sheet, pairs_df)
        completed = st.session_state.completed_local
        total = len(pairs_df)

        st.info(f"Welcome back, **{st.session_state.annotator_id}**!")

        progress = len(completed) / total if total > 0 else 0
        st.progress(progress)
        st.caption(f"Your progress: {len(completed)} / {total} pairs completed")

        if st.button("Continue", type="primary"):
            st.session_state.show_instructions = False
            st.rerun()

        st.divider()
        st.markdown("##### Switch to a different user:")

    # Annotator ID input
    annotator_id = st.text_input(
        f"Enter your name or ID (minimum {MIN_NAME_LENGTH} characters):",
        placeholder="e.g., john_doe or student_01",
        key="annotator_input"
    )

    name_valid = len(annotator_id.strip()) >= MIN_NAME_LENGTH

    if annotator_id:
        if not name_valid:
            st.warning(
                f"Please enter at least {MIN_NAME_LENGTH} characters "
                f"({len(annotator_id.strip())}/{MIN_NAME_LENGTH})"
            )
        else:
            st.success(f"Name valid ({len(annotator_id.strip())} characters)")

    if st.button("I understand, continue", type="primary"):
        if not name_valid:
            st.error(f"Your name/ID must be at least {MIN_NAME_LENGTH} characters.")
        else:
            st.session_state.annotator_id = annotator_id.strip()
            st.session_state.is_super = (st.session_state.annotator_id in SUPER_USERS)
            st.session_state.mode = "review" if st.session_state.is_super else "annotate"

            if sheet is not None:
                from_sheet = get_completed_pairs(sheet, st.session_state.annotator_id)
                st.session_state.completed_local = set(from_sheet)
            else:
                st.session_state.completed_local = set()

            st.session_state.show_instructions = False
            st.session_state.submitted = False
            st.rerun()


def show_super_review_interface(pairs_df):
    """Super user review-only interface: browse all pairs & see exact filenames."""
    st.markdown("### Super User Review Mode")
    st.caption("Browse all pairs and record issues for offline editing of pairs.csv. No explanations required.")

    # Add dataset column for filtering
    if "dataset" not in pairs_df.columns:
        pairs_df = pairs_df.copy()
        pairs_df["dataset"] = pairs_df["A"].apply(infer_dataset_prefix)

    # Init flags list
    if "super_flags" not in st.session_state:
        st.session_state.super_flags = []
    if "super_pos" not in st.session_state:
        st.session_state.super_pos = 0

    # Sidebar filters + management
    with st.sidebar:
        st.markdown("#### Review Controls")

        dataset_filter = st.multiselect(
            "Dataset filter",
            options=sorted(pairs_df["dataset"].unique().tolist()),
            default=sorted(pairs_df["dataset"].unique().tolist()),
        )

        gt_options = sorted(pairs_df["ground_truth"].astype(str).str.lower().unique().tolist())
        gt_filter = st.multiselect(
            "Ground truth filter",
            options=gt_options,
            default=gt_options,
        )

        search_text = st.text_input("Search filename substring (A or B)", value="").strip()

        st.divider()
        st.markdown("#### Offline Fix List")
        st.caption("Flag pairs while reviewing; download as CSV for offline edits.")
        if st.button("Clear flagged list"):
            st.session_state.super_flags = []
            st.success("Cleared flagged list.")

    # Filter view
    view_df = pairs_df.copy()
    view_df["ground_truth"] = view_df["ground_truth"].astype(str).str.lower()
    view_df = view_df[view_df["dataset"].isin(dataset_filter)]
    view_df = view_df[view_df["ground_truth"].isin(gt_filter)]

    if search_text:
        mask = (
            view_df["A"].astype(str).str.contains(search_text, case=False, na=False)
            | view_df["B"].astype(str).str.contains(search_text, case=False, na=False)
        )
        view_df = view_df[mask]

    view_df = view_df.sort_values("index")

    if view_df.empty:
        st.warning("No pairs match the current filters/search.")
        return

    # Clamp position
    max_pos = len(view_df) - 1
    st.session_state.super_pos = min(max(st.session_state.super_pos, 0), max_pos)

    # Navigation UI
    nav1, nav2, nav3, nav4 = st.columns([1, 1, 2, 2])
    with nav1:
        if st.button("◀ Previous"):
            st.session_state.super_pos = max(st.session_state.super_pos - 1, 0)
            st.rerun()
    with nav2:
        if st.button("Next ▶"):
            st.session_state.super_pos = min(st.session_state.super_pos + 1, max_pos)
            st.rerun()
    with nav3:
        jump_index = st.number_input(
            "Jump to pair index",
            min_value=int(pairs_df["index"].min()),
            max_value=int(pairs_df["index"].max()),
            value=int(view_df.iloc[st.session_state.super_pos]["index"]),
            step=1,
        )
        if st.button("Go", key="super_go"):
            indices = view_df["index"].tolist()
            if jump_index in indices:
                st.session_state.super_pos = indices.index(jump_index)
            else:
                nearest_pos = min(range(len(indices)), key=lambda i: abs(indices[i] - jump_index))
                st.session_state.super_pos = nearest_pos
            st.rerun()
    with nav4:
        st.markdown(f"**Showing:** {st.session_state.super_pos + 1} / {len(view_df)} (filtered view)")

    row = view_df.iloc[st.session_state.super_pos]
    pair_index = int(row["index"])

    st.markdown("#### Pair metadata (from pairs.csv)")
    st.code(
        "\n".join(
            [
                f"index: {pair_index}",
                f"A: {row['A']}",
                f"B: {row['B']}",
                f"ground_truth: {row['ground_truth']}",
                f"celeb_id: {row.get('celeb_id', '')}",
                f"dataset: {row.get('dataset', '')}",
            ]
        )
    )

    st.markdown("#### Images")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Face A**")
        img_a = get_image_path(row["A"])
        try:
            st.image(img_a, width=340)
        except Exception:
            st.error(f"Could not load: {img_a}")
        st.caption(str(row["A"]))
    with c2:
        st.markdown("**Face B**")
        img_b = get_image_path(row["B"])
        try:
            st.image(img_b, width=340)
        except Exception:
            st.error(f"Could not load: {img_b}")
        st.caption(str(row["B"]))

    st.divider()
    st.markdown("#### Flag this pair for offline fix (optional)")

    # Note stored per pair (doesn't require a flag)
    note = st.text_input("Optional note (stored with flag)", key=f"note_{pair_index}")

    b1, b2, b3 = st.columns([1.2, 1.2, 1.2])
    with b1:
        if st.button("Flag: should be SAME"):
            st.session_state.super_flags.append(
                {
                    "index": pair_index,
                    "A": row["A"],
                    "B": row["B"],
                    "current_ground_truth": row["ground_truth"],
                    "suggested_ground_truth": "same",
                    "issue_type": "wrong_gt",
                    "notes": note,
                }
            )
            st.success("Flagged (suggested SAME).")
    with b2:
        if st.button("Flag: should be DIFFERENT"):
            st.session_state.super_flags.append(
                {
                    "index": pair_index,
                    "A": row["A"],
                    "B": row["B"],
                    "current_ground_truth": row["ground_truth"],
                    "suggested_ground_truth": "different",
                    "issue_type": "wrong_gt",
                    "notes": note,
                }
            )
            st.success("Flagged (suggested DIFFERENT).")
    with b3:
        if st.button("Flag: broken / unusable"):
            st.session_state.super_flags.append(
                {
                    "index": pair_index,
                    "A": row["A"],
                    "B": row["B"],
                    "current_ground_truth": row["ground_truth"],
                    "suggested_ground_truth": "",
                    "issue_type": "broken_unusable",
                    "notes": note,
                }
            )
            st.success("Flagged (broken/unusable).")

    if st.session_state.super_flags:
        st.markdown("#### Flagged list (this session)")
        flags_df = pd.DataFrame(st.session_state.super_flags)

        # Keep most recent flag per index
        flags_df = flags_df.drop_duplicates(subset=["index"], keep="last").sort_values("index")
        st.dataframe(flags_df, use_container_width=True)

        csv_bytes = flags_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download flagged list as CSV",
            data=csv_bytes,
            file_name="pairs_flags_for_offline_editing.csv",
            mime="text/csv",
        )
    else:
        st.info("No pairs flagged yet in this session.")


def show_annotation_interface(pairs_df, sheet):
    """Display the main annotation interface (compact layout)."""

    annotator_id = st.session_state.annotator_id
    ensure_local_progress_initialized(sheet, pairs_df)

    completed = st.session_state.completed_local
    all_pairs = pairs_df['index'].tolist()
    remaining = [i for i in all_pairs if i not in completed]

    total = len(all_pairs)
    num_completed = len(completed)
    progress = num_completed / total if total > 0 else 0

    # Top row: title + progress bar
    header_col, progress_col = st.columns([1.2, 2])
    with header_col:
        st.markdown("### Face Identity Annotation")
        st.markdown(
            f"<span class='small-caption'>Annotator: <b>{annotator_id}</b> &nbsp;|&nbsp; "
            f"Completed: {num_completed} / {total}</span>",
            unsafe_allow_html=True,
        )
    with progress_col:
        st.progress(progress)

    # All done
    if not remaining:
        st.success("You have completed all annotations! Thank you!")
        if st.button("Start over (re-annotate all pairs)"):
            st.session_state.completed_local = set()
            st.session_state.submitted = False
            st.rerun()
        return

    # Current pair (always first remaining)
    current_pair = remaining[0]
    pair_data = pairs_df[pairs_df['index'] == current_pair].iloc[0]

    # Are we in "review incorrect" mode for this pair?
    review_mode = st.session_state.get("submitted", False)

    # Sidebar (minimal)
    with st.sidebar:
        st.markdown("#### Session")
        st.markdown(f"**Annotator:** {annotator_id}")
        st.markdown(f"**Current Pair:** `{current_pair}`")
        st.markdown(f"**Completed:** {num_completed} / {total}")

        st.divider()
        if st.button("View Instructions"):
            st.session_state.show_instructions = True
            st.rerun()
        if st.button("Switch Annotator"):
            st.session_state.annotator_id = None
            st.session_state.show_instructions = True
            if "completed_local" in st.session_state:
                del st.session_state.completed_local
            st.session_state.submitted = False
            st.rerun()

    st.markdown("#### 1. Compare these faces")

    outer_left, outer_center, outer_right = st.columns([0.1, 0.8, 0.1])
    with outer_center:
        img_col1, img_col2 = st.columns(2)
        with img_col1:
            st.markdown("**Face A**")
            image_a_path = get_image_path(pair_data['A'])
            try:
                st.image(image_a_path, width=320)
            except Exception:
                st.error(f"Could not load image: {image_a_path}")
        with img_col2:
            st.markdown("**Face B**")
            image_b_path = get_image_path(pair_data['B'])
            try:
                st.image(image_b_path, width=320)
            except Exception:
                st.error(f"Could not load image: {image_b_path}")

    st.markdown("---")

    st.markdown("#### 2. Your decision and explanation")
    decision_col, expl_col = st.columns([1, 2])

    with decision_col:
        decision = st.radio(
            "Are these the same person?",
            options=["same", "different"],
            index=None,
            horizontal=False,
            key=f"decision_{current_pair}",
        )

    if decision == "same":
        expl_placeholder = (
            "Describe the facial features that indicate these are the same person "
            "(e.g., nose shape, eye spacing, jawline, distinctive marks)..."
        )
    elif decision == "different":
        expl_placeholder = (
            "Describe the facial features that indicate these are different people "
            "(e.g., different nose shape, face structure, distinguishing features)..."
        )
    else:
        expl_placeholder = "First choose whether they are the same or different person on the left."

    with expl_col:
        initial_explanation = st.text_area(
            f"Explanation (minimum {MIN_EXPLANATION_LENGTH} characters):",
            placeholder=expl_placeholder,
            key=f"explanation_{current_pair}",
            disabled=(decision is None),
            height=110,
        )

    explanation_valid = len(initial_explanation.strip()) >= MIN_EXPLANATION_LENGTH

    feedback_col, _ = st.columns([2, 1])
    with feedback_col:
        if initial_explanation:
            if not explanation_valid:
                st.markdown(
                    f"<span class='small-caption' style='color:#cc6600;'>"
                    f"Explanation length: {len(initial_explanation.strip())} / {MIN_EXPLANATION_LENGTH}</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<span class='small-caption' style='color:#228B22;'>"
                    f"Explanation length OK: {len(initial_explanation.strip())} characters</span>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    if not review_mode:
        st.markdown("#### 3. Submit")
        if st.button("Submit Answer", type="primary", key=f"submit_{current_pair}"):
            if decision is None:
                st.error("Please select whether these are the same person or different people before submitting.")
            elif not explanation_valid:
                st.error(
                    f"Your explanation must be at least {MIN_EXPLANATION_LENGTH} characters "
                    f"({len(initial_explanation.strip())}/{MIN_EXPLANATION_LENGTH})."
                )
            else:
                ground_truth = str(pair_data['ground_truth']).lower()
                is_correct = (decision == ground_truth)

                if is_correct:
                    annotation = {
                        "timestamp": datetime.now().isoformat(),
                        "annotator_id": annotator_id,
                        "pair_index": int(pair_data['index']),
                        "image_a": pair_data['A'],
                        "image_b": pair_data['B'],
                        "ground_truth": ground_truth,
                        "celeb_id": str(pair_data.get('celeb_id', "")),
                        "human_decision": decision,
                        "initial_explanation": initial_explanation,
                        "is_correct": True,
                        "followup_explanation": "",
                    }
                    if save_annotation(sheet, annotation):
                        st.session_state.completed_local.add(int(pair_data['index']))
                        st.session_state.submitted = False
                        st.rerun()
                else:
                    st.session_state.submitted = True
                    st.session_state.is_correct = False
                    st.session_state.ground_truth = ground_truth
                    st.session_state.decision = decision
                    st.session_state.initial_explanation = initial_explanation
                    st.session_state.pair_data = pair_data
                    st.rerun()

    if st.session_state.get("submitted", False):
        is_correct = st.session_state.is_correct
        ground_truth = st.session_state.ground_truth
        decision = st.session_state.decision
        initial_explanation = st.session_state.initial_explanation
        pair_state = st.session_state.pair_data

        if is_correct:
            st.session_state.submitted = False
            st.rerun()

        st.markdown("#### 3. Review (your answer was incorrect)")
        st.markdown(
            f"**Ground truth:** {ground_truth.upper()} &nbsp;&nbsp; "
            f"**Your answer:** {decision}"
        )
        st.markdown(
            "Now that you know the correct answer, what features might you have "
            "overlooked or misinterpreted?"
        )

        followup_explanation = st.text_area(
            f"Reflection (minimum {MIN_EXPLANATION_LENGTH} characters):",
            placeholder=(
                "Describe what features you might have missed or misinterpreted. "
                "What would you look for differently next time?"
            ),
            key=f"followup_reflect_{current_pair}",
            height=110,
        )

        followup_valid = len(followup_explanation.strip()) >= MIN_EXPLANATION_LENGTH

        if followup_explanation:
            if not followup_valid:
                st.markdown(
                    f"<span class='small-caption' style='color:#cc6600;'>"
                    f"Reflection length: {len(followup_explanation.strip())} / {MIN_EXPLANATION_LENGTH}</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<span class='small-caption' style='color:#228B22;'>"
                    f"Reflection length OK: {len(followup_explanation.strip())} characters</span>",
                    unsafe_allow_html=True,
                )

        if st.button("Next Pair", type="primary", key=f"next_incorrect_{current_pair}"):
            if not followup_valid:
                st.error(
                    f"Your reflection must be at least {MIN_EXPLANATION_LENGTH} characters "
                    f"({len(followup_explanation.strip())}/{MIN_EXPLANATION_LENGTH})."
                )
            else:
                annotation = {
                    "timestamp": datetime.now().isoformat(),
                    "annotator_id": annotator_id,
                    "pair_index": int(pair_state['index']),
                    "image_a": pair_state['A'],
                    "image_b": pair_state['B'],
                    "ground_truth": ground_truth,
                    "celeb_id": str(pair_state.get('celeb_id', "")),
                    "human_decision": decision,
                    "initial_explanation": initial_explanation,
                    "is_correct": False,
                    "followup_explanation": followup_explanation,
                }
                if save_annotation(sheet, annotation):
                    st.session_state.completed_local.add(int(pair_state['index']))
                    st.session_state.submitted = False
                    st.rerun()


# =============================================================================
# MAIN APP
# =============================================================================

def main():
    st.set_page_config(
        page_title="Face Annotation Tool",
        page_icon="",
        layout="wide"
    )

    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1000px;
            padding-top: 2.6rem;
            padding-bottom: 1.6rem;
            padding-left: 2rem;
            padding-right: 2rem;
            margin-left: auto;
            margin-right: auto;
        }
        h1, h2, h3, h4 {
            margin-top: 0.6rem;
            margin-bottom: 0.4rem;
        }
        .small-caption {
            font-size: 0.85rem;
            color: #666666;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Initialize session state
    if 'show_instructions' not in st.session_state:
        st.session_state.show_instructions = True
    if 'annotator_id' not in st.session_state:
        st.session_state.annotator_id = None
    if 'submitted' not in st.session_state:
        st.session_state.submitted = False
    if 'is_super' not in st.session_state:
        st.session_state.is_super = False
    if 'mode' not in st.session_state:
        st.session_state.mode = "annotate"  # super users can switch to "review"

    # Load data
    pairs_df = load_pairs()
    if pairs_df is None:
        st.error("Could not load pairs data. Please check your pairs.csv file.")
        return

    # Connect to Google Sheets (still used for normal annotators)
    sheet = get_google_sheet()
    if sheet is None:
        st.warning("Running without Google Sheets. Annotations will not be saved.")

    # Route pages
    if st.session_state.show_instructions:
        show_instructions(pairs_df, sheet)
        return

    if st.session_state.annotator_id is None:
        st.session_state.show_instructions = True
        st.rerun()
        return

    # Super user mode selector
    if st.session_state.is_super:
        with st.sidebar:
            st.markdown("#### Mode")
            selected = st.radio(
                "Select mode",
                options=["review", "annotate"],
                index=0 if st.session_state.mode == "review" else 1
            )
            st.session_state.mode = selected

    if st.session_state.is_super and st.session_state.mode == "review":
        show_super_review_interface(pairs_df)
    else:
        show_annotation_interface(pairs_df, sheet)


if __name__ == "__main__":
    main()
