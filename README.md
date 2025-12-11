# Face Identity Annotation Tool

A Streamlit app for collecting human annotations on face pair identity verification with real-time Google Sheets saving.

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Add Your Credentials

Place your Google Service Account JSON file in this folder and rename it to `credentials.json`.

### 3. Prepare Your Data

Edit `pairs.csv` with your image pairs:

```csv
index,A,B,ground_truth,celeb_id
0,image1.jpg,image2.jpg,same,1234
1,image3.jpg,image4.jpg,different,5678_9012
```

### 4. Add Your Images

Create an `images/` folder and add your face images:

```
annotation_app/
├── app.py
├── credentials.json
├── pairs.csv
├── requirements.txt
└── images/
    ├── image1.jpg
    ├── image2.jpg
    └── ...
```

### 5. Run the App

```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

---

## Configuration

Edit the top of `app.py` to change settings:

```python
# Google Sheets settings
SPREADSHEET_ID = "your-spreadsheet-id"
CREDENTIALS_FILE = "credentials.json"

# Data settings
PAIRS_CSV = "pairs.csv"
IMAGE_BASE_PATH = "images/"

# If using URLs for images
USE_IMAGE_URLS = False
IMAGE_URL_BASE = "https://yourserver.com/images/"
```

---

## Hosting Options

### Option A: Run Locally
Just run `streamlit run app.py` on your machine.

### Option B: University Server
```bash
# SSH to server
ssh vshah3@regulus.cedar.buffalo.edu

# Navigate to app folder
cd /path/to/annotation_app

# Run with specific port
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Then access at `http://regulus.cedar.buffalo.edu:8501`

### Option C: Streamlit Cloud (Free)
1. Push code to GitHub
2. Go to share.streamlit.io
3. Connect your repo
4. Add credentials as secrets (see below)

For Streamlit Cloud, add credentials in the app settings under "Secrets":
```toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "annotation-bot@....iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
```

---

## Output Format

Annotations are saved to Google Sheets with these columns:

| Column | Description |
|--------|-------------|
| timestamp | When the annotation was submitted |
| annotator_id | Who made the annotation |
| pair_index | Index of the image pair |
| image_a | Filename of first image |
| image_b | Filename of second image |
| ground_truth | Correct answer (same/different) |
| celeb_id | Celebrity ID from dataset |
| human_decision | Annotator's answer |
| initial_explanation | Why they made that decision |
| is_correct | Whether they matched ground truth |
| followup_explanation | Reflection if they were wrong |

---

## Customization

### Change Instructions
Edit the `show_instructions()` function in `app.py`.

### Add Questions
Add new fields in the `show_annotation_interface()` function.

### Change Styling
Add custom CSS at the top of `main()`:
```python
st.markdown("""
<style>
    .stButton button { background-color: #4CAF50; }
</style>
""", unsafe_allow_html=True)
```
