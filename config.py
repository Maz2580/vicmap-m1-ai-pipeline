import os
import json
from pathlib import Path
from datetime import datetime

# Default configuration values, overridable via environment variables
BASE_DIR = Path(os.environ.get("M1_BASE_DIR", Path(__file__).resolve().parent))

# Data source configuration
ORDER_NUMBER = "RK36R8"  # Fixed order number
DOWNLOAD_URL_FILE = BASE_DIR / "download_url.json"

def get_download_info():
    """Get the most recently configured download URL and its email date."""
    if DOWNLOAD_URL_FILE.exists():
        with open(DOWNLOAD_URL_FILE) as f:
            data = json.load(f)
            return {
                "url": data.get("url"),
                "email_date": data.get("email_date"),
                "last_updated": data.get("last_updated")
            }
    return None

def get_download_url():
    """Get the most recently configured download URL."""
    info = get_download_info()
    return info["url"] if info else None

def save_download_url(url: str, email_date: datetime = None):
    """Save a new download URL with timestamp and email date."""
    DOWNLOAD_URL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DOWNLOAD_URL_FILE, "w") as f:
        data = {
            "url": url,
            "order_number": ORDER_NUMBER,
            "last_updated": datetime.now().isoformat(),
            "email_date": email_date.isoformat() if email_date else None
        }
        json.dump(data, f, indent=2)

DATA_URL = os.environ.get("M1_DATA_URL", get_download_url())

# Updated directory paths to use the correct location
# Default to E:\Administration\Data\Updates\Updated Zip Files
DEFAULT_DATA_DIR = Path("E:/Administration/Data/Updates/Updated Zip Files")

# Download directory - where zip files are saved
DOWNLOAD_DIR = Path(os.environ.get("M1_DOWNLOAD_DIR", DEFAULT_DATA_DIR))

# Extract directory - where zip files are extracted (subfolder with order number)
EXTRACT_DIR = Path(os.environ.get("M1_EXTRACT_DIR", DEFAULT_DATA_DIR / f"Order_{ORDER_NUMBER}"))

# FME Configuration
# Main workflow that runs other workspaces.
# M1_FME_WORKSPACE and M1_FME_EXE must be set in .env per deployment.
# Example values are shown in .env.example.
FME_WORKSPACE = Path(os.environ.get("M1_FME_WORKSPACE", ""))
FME_EXE = Path(os.environ.get("M1_FME_EXE", ""))

# Pozi Connect Configuration.
# M1_POZI_DIR must be set in .env (path to the Pozi Connect install dir).
POZI_DIR = Path(os.environ.get("M1_POZI_DIR", ""))
POZI_EXE = POZI_DIR / "PoziConnect.exe"
POZI_TASKS_DIR = POZI_DIR / "tasks"
POZI_OUTPUT_DIR = POZI_DIR / "output" / "M1"  # M1 output directory

# Pozi Connect Tasks (in execution order).
# Populate POZI_TASKS via config/settings.json. See config/settings.example.json
# for the schema. Each entry is {"name": "Display Name", "ini": "<YourLGA>/<file>.ini"}.
# When adopters set this up, the SettingsManager.get('pozi_tasks') call in app.py
# loads the list from settings.json at runtime.
POZI_TASKS: list[dict[str, str]] = []

# Recipe directory for Pozi
POZI_RECIPE_DIR = BASE_DIR / "recipes"

RATES_DB_CSV = Path(os.environ.get("M1_RATES_DB_CSV", BASE_DIR / "data/rates/rates_export.csv"))
QA_REPORT = Path(os.environ.get("M1_QA_REPORT", BASE_DIR / "reports/m1_qa.csv"))

LOG_DIR = Path(os.environ.get("M1_LOG_DIR", BASE_DIR / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)