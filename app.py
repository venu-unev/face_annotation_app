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
    """Get list of pair indices already completed by this annotator."""
    try:
        records = sheet.get_all_records()
        completed = [
            r["pair_index"] for r in records 
            if r.get("annotator_id") == annotator_id
        ]
        return completed
    except:
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

def show_instructions():
    """Display the instructions page."""
    st.markdown("""
    # Face Identity Annotation Task
    
    ## Instructions
    
    Welcome! Your task is to determine whether two face images show the **same person** 
    or **different people**, and explain your reasoning.
    
    ### How it works:
    
    1. **View the image pair** - You will see two face images side by side
    2. **Make your decision** - Are they the same person or different people?
    3. **Explain your reasoning** - Describe what features led to your decision
    4. **Learn from feedback** - If your answer differs from the ground truth, you will 
       be asked to reflect on what you might have missed
    
    ### Tips for good annotations:
    
    - Look at **facial structure**: nose shape, eye spacing, jawline, face shape
    - Consider **distinctive features**: moles, scars, ear shape, eyebrows
    - Do not be fooled by **changeable features**: hairstyle, lighting, expression, makeup
    - When explaining, be **specific** about which features you observed
    
    ### Example of a good explanation:
    
    > *"These appear to be the same person. The nose bridge width and nostril shape 
    > are identical. The eye spacing and brow ridge structure match. Despite different 
    > lighting, the jawline contour is consistent."*
    
    ---
    
    *Your annotations will be saved automatically. You can take breaks and continue later.*
    """)
    
    st.divider()
    
    # Check if user already has a stored ID
    if st.session_state.annotator_id:
        st.info(f"Welcome back, **{st.session_state.annotator_id}**!")
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
    
    # Validate length
    name_valid = len(annotator_id.strip()) >= MIN_NAME_LENGTH
    
    if annotator_id and not name_valid:
        st.warning(f"Please enter at least {MIN_NAME_LENGTH} characters for your name or ID.")
    
    # Button always visible, disabled if invalid
    if st.button("I understand, start annotating", type="primary", disabled=not name_valid):
        st.session_state.annotator_id = annotator_id.strip()
        st.session_state.show_instructions = False
        st.rerun()


def show_annotation_interface(pairs_df, sheet):
    """Display the main annotation interface."""
    
    # Get current annotator
    annotator_id = st.session_state.annotator_id
    
    # Get completed pairs for this annotator
    completed = get_completed_pairs(sheet, annotator_id)
    
    # Find next pair to annotate
    remaining = [i for i in pairs_df['index'].tolist() if i not in completed]
    
    if not remaining:
        st.success("You have completed all annotations! Thank you!")
        st.info(f"Total annotations: {len(completed)}")
        
        if st.button("Start over (re-annotate all pairs)"):
            st.session_state.current_pair_idx = 0
            st.rerun()
        return
    
    # Get current pair index
    if 'current_pair_idx' not in st.session_state:
        st.session_state.current_pair_idx = 0
    
    # Get the actual pair index from remaining list
    current_pair = remaining[min(st.session_state.current_pair_idx, len(remaining) - 1)]
    pair_data = pairs_df[pairs_df['index'] == current_pair].iloc[0]
    
    # Progress bar
    progress = len(completed) / len(pairs_df)
    st.progress(progress)
    st.caption(f"Progress: {len(completed)} / {len(pairs_df)} pairs completed")
    
    # Sidebar with annotator info
    with st.sidebar:
        st.markdown(f"**Annotator:** {annotator_id}")
        st.markdown(f"**Pair:** {current_pair}")
        st.divider()
        if st.button("View Instructions"):
            st.session_state.show_instructions = True
            st.rerun()
        if st.button("Switch Annotator"):
            st.session_state.annotator_id = None
            st.session_state.show_instructions = True
            st.rerun()
    
    # ===================
    # STEP 1: Show images
    # ===================
    st.markdown("## Compare these faces")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Face A")
        image_a_path = get_image_path(pair_data['A'])
        try:
            st.image(image_a_path, use_container_width=True)
        except:
            st.error(f"Could not load image: {image_a_path}")
        st.caption(f"`{pair_data['A']}`")
    
    with col2:
        st.markdown("### Face B")
        image_b_path = get_image_path(pair_data['B'])
        try:
            st.image(image_b_path, use_container_width=True)
        except:
            st.error(f"Could not load image: {image_b_path}")
        st.caption(f"`{pair_data['B']}`")
    
    st.divider()
    
    # ===================
    # STEP 2: Decision
    # ===================
    st.markdown("## Are these the same person?")
    
    decision = st.radio(
        "Select your answer:",
        options=["same", "different"],
        index=None,
        horizontal=True,
        key=f"decision_{current_pair}"
    )
    
    # ===================
    # STEP 3: Initial explanation
    # ===================
    st.divider()
    
    if decision == "same":
        st.markdown("## Why do you think they are the **same person**?")
        placeholder = "Describe the facial features that indicate these are the same person (e.g., nose shape, eye spacing, jawline, distinctive marks)..."
    elif decision == "different":
        st.markdown("## Why do you think they are **different people**?")
        placeholder = "Describe the facial features that indicate these are different people (e.g., different nose shape, face structure, distinguishing features)..."
    else:
        st.markdown("## Explain your reasoning")
        placeholder = "First select whether they are the same or different person above..."
    
    initial_explanation = st.text_input(
        f"Your explanation (minimum {MIN_EXPLANATION_LENGTH} characters):",
        placeholder=placeholder,
        key=f"explanation_{current_pair}",
        disabled=(decision is None)
    )
    
    # Check if explanation is sufficient
    explanation_valid = len(initial_explanation.strip()) >= MIN_EXPLANATION_LENGTH
    
    if initial_explanation and not explanation_valid:
        st.warning(f"Please provide a more detailed explanation (at least {MIN_EXPLANATION_LENGTH} characters)")
    
    # ===================
    # STEP 4: Submit and compare
    # ===================
    st.divider()
    
    # Determine if form is complete
    form_valid = decision is not None and explanation_valid
    
    if st.button("Submit Answer", type="primary", key=f"submit_{current_pair}", disabled=not form_valid):
        # Compare with ground truth
        ground_truth = pair_data['ground_truth'].lower()
        is_correct = (decision == ground_truth)
        
        # Store in session state for reveal
        st.session_state.submitted = True
        st.session_state.is_correct = is_correct
        st.session_state.ground_truth = ground_truth
        st.session_state.decision = decision
        st.session_state.initial_explanation = initial_explanation
        st.session_state.pair_data = pair_data
        st.rerun()
    
    # ===================
    # STEP 5: Reveal and reflect (if submitted)
    # ===================
    if st.session_state.get('submitted', False):
        is_correct = st.session_state.is_correct
        ground_truth = st.session_state.ground_truth
        decision = st.session_state.decision
        initial_explanation = st.session_state.initial_explanation
        pair_data = st.session_state.pair_data
        
        st.divider()
        
        if is_correct:
            # CORRECT - Simple confirmation and move on
            st.success("## Correct!")
            st.markdown("Your assessment matches the ground truth. Great job!")
            
            if st.button("Next Pair", type="primary", key="next_correct"):
                # Save annotation
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
                    "followup_explanation": ""
                }
                
                if save_annotation(sheet, annotation):
                    st.session_state.submitted = False
                    st.session_state.current_pair_idx += 1
                    st.rerun()
        
        else:
            # INCORRECT - Reveal and ask for reflection
            st.error("## Incorrect")
            
            st.markdown(f"""
            ### The ground truth says: **{ground_truth.upper()}**
            
            You said **{decision}**, but these faces are actually **{ground_truth}**.
            """)
            
            st.divider()
            
            st.markdown("## Reflect: What did you miss?")
            st.markdown("Now that you know the correct answer, what features might you have overlooked or misinterpreted?")
            
            followup_explanation = st.text_input(
                f"Your reflection (minimum {MIN_EXPLANATION_LENGTH} characters):",
                placeholder="Describe what features you might have missed or misinterpreted. What would you look for differently next time?",
                key=f"followup_{current_pair}"
            )
            
            followup_valid = len(followup_explanation.strip()) >= MIN_EXPLANATION_LENGTH
            
            if followup_explanation and not followup_valid:
                st.warning(f"Please provide a more detailed reflection (at least {MIN_EXPLANATION_LENGTH} characters)")
            
            if st.button("Next Pair", type="primary", key="next_incorrect", disabled=not followup_valid):
                # Save annotation
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
                    "is_correct": False,
                    "followup_explanation": followup_explanation
                }
                
                if save_annotation(sheet, annotation):
                    st.session_state.submitted = False
                    st.session_state.current_pair_idx += 1
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
        show_instructions()
    elif st.session_state.annotator_id is None:
        st.session_state.show_instructions = True
        st.rerun()
    else:
        show_annotation_interface(pairs_df, sheet)


if __name__ == "__main__":
    main()