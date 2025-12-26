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
import json
import os

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
                    # Skip rows with bad/missing data
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
        return IMAGE_URL_BASE + filename
    else:
        return os.path.join(IMAGE_BASE_PATH, filename)


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

    # ---------- Top instructions ----------
    st.markdown("""
# Face Identity Annotation Task

## Instructions

You will review **two face images** and decide whether they show the **same person** or **different people**.
After choosing, you must briefly explain *which visual evidence* informed your decision.

### Workflow

1. **Inspect both images carefully** (side-by-side).
2. **Select a label**: *Same person* or *Different people*.
3. **Write a short justification** citing specific facial cues.
4. **Review feedback** if your answer differs from the ground truth.
""")

    # ---------- Instruction image ----------
    img_path = Path("image.jpeg")

    if img_path.exists():
        st.image(str(img_path), use_container_width=True)
    else:
        st.error("Instruction image `image.jpeg` not found in app directory.")

    # ---------- Remaining instructions ----------
    st.markdown("""
### What to focus on

- **Stable facial geometry**: face shape, jawline, cheekbones, eye spacing, nose shape, lip structure
- **Distinctive markers**: scars, moles, freckles, eyebrow shape, ear shape, asymmetries

### What to be cautious about

- **Changeable factors**: hairstyle, facial hair, makeup, lighting, expression, camera angle
- Apparent differences caused by image quality or pose

### Example justification (strong)

> “Same person. The nose bridge and nostril shape match closely, and the eye spacing and brow shape are consistent. Lighting differs, but the jawline contour and cheekbone structure align.”

---

*Your progress is saved automatically. You may stop and resume later.*
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
        
        if st.button("Continue Annotating", type="primary"):
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
    
    # Button always enabled; validate when clicked
    if st.button("I understand, start annotating", type="primary"):
        if not name_valid:
            st.error(f"Your name/ID must be at least {MIN_NAME_LENGTH} characters.")
        else:
            st.session_state.annotator_id = annotator_id.strip()
            # Initialize local progress from Google Sheets exactly once at login
            if sheet is not None:
                from_sheet = get_completed_pairs(sheet, st.session_state.annotator_id)
                st.session_state.completed_local = set(from_sheet)
            else:
                st.session_state.completed_local = set()
            
            st.session_state.show_instructions = False
            
            # Reset any submission state
            st.session_state.submitted = False
            if 'current_pair_idx' in st.session_state:
                del st.session_state.current_pair_idx
            
            st.rerun()


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
    
    # ------------------------------------------------------------
    # 1. Images (centered and a bit closer)
    # ------------------------------------------------------------
    st.markdown("#### 1. Compare these faces")
    
    # Center the two images inside a slightly narrower row
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
            #st.caption(f"`{pair_data['A']}`")
        with img_col2:
            st.markdown("**Face B**")
            image_b_path = get_image_path(pair_data['B'])
            try:
                st.image(image_b_path, width=320)
            except Exception:
                st.error(f"Could not load image: {image_b_path}")
            #st.caption(f"`{pair_data['B']}`")
    
    st.markdown("---")
    
    # ------------------------------------------------------------
    # 2. Decision + explanation (always shown, even in review mode)
    # ------------------------------------------------------------
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
    
    # ------------------------------------------------------------
    # 3. Submit (only shown when NOT in review mode)
    # ------------------------------------------------------------
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
                    # CORRECT: save immediately and advance
                    annotation = {
                        "timestamp": datetime.now().isoformat(),
                        "annotator_id": annotator_id,
                        "pair_index": int(pair_data['index']),
                        "image_a": pair_data['A'],
                        "image_b": pair_data['B'],
                        "ground_truth": ground_truth,
                        "celeb_id": str(pair_data['celeb_id']),
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
                    # INCORRECT: store state and go into review mode
                    st.session_state.submitted = True
                    st.session_state.is_correct = False
                    st.session_state.ground_truth = ground_truth
                    st.session_state.decision = decision
                    st.session_state.initial_explanation = initial_explanation
                    st.session_state.pair_data = pair_data
                    st.rerun()
    
    # ------------------------------------------------------------
    # 4. Reveal + reflect (only when incorrect / review_mode)
    # ------------------------------------------------------------
    if st.session_state.get("submitted", False):
        # We are in incorrect-review mode
        is_correct = st.session_state.is_correct
        ground_truth = st.session_state.ground_truth
        decision = st.session_state.decision
        initial_explanation = st.session_state.initial_explanation
        pair_state = st.session_state.pair_data

        # Safety: should not happen, but if correct just reset
        if is_correct:
            st.session_state.submitted = False
            st.rerun()
        
        # No big red block, just a simple header + text
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
                    "celeb_id": str(pair_state['celeb_id']),
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
    
    # --- Compact layout CSS (with a bit more top padding so headings aren't cropped) ---
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
    ...


    # Initialize session state
    if 'show_instructions' not in st.session_state:
        st.session_state.show_instructions = True
    if 'annotator_id' not in st.session_state:
        st.session_state.annotator_id = None
    if 'submitted' not in st.session_state:
        st.session_state.submitted = False
    
    # Load data
    pairs_df = load_pairs()
    if pairs_df is None:
        st.error("Could not load pairs data. Please check your pairs.csv file.")
        return
    
    # Connect to Google Sheets
    sheet = get_google_sheet()
    if sheet is None:
        st.warning("Running without Google Sheets. Annotations will not be saved.")
    
    # Show appropriate page
    if st.session_state.show_instructions:
        show_instructions(pairs_df, sheet)
    elif st.session_state.annotator_id is None:
        st.session_state.show_instructions = True
        st.rerun()
    else:
        show_annotation_interface(pairs_df, sheet)


if __name__ == "__main__":
    main()
