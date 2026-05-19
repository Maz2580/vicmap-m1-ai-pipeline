import os
import shutil
import zipfile
import logging
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

from config import (
    get_download_url,
    DOWNLOAD_DIR,
    EXTRACT_DIR,
    ORDER_NUMBER
)

logger = logging.getLogger(__name__)

def setup_directories():
    """Ensure download and extract directories exist."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Download directory: {DOWNLOAD_DIR}")
    logger.info(f"Extract directory: {EXTRACT_DIR}")

def clean_existing_data():
    """Remove existing zip files and extracted data."""
    # Clean old zip files in download directory
    if DOWNLOAD_DIR.exists():
        logger.info(f"Cleaning download directory: {DOWNLOAD_DIR}")
        for item in DOWNLOAD_DIR.glob(f"*{ORDER_NUMBER}*.zip"):
            if item.is_file():
                logger.info(f"Removing old zip file: {item}")
                item.unlink()
                
    # Clean extract directory completely
    if EXTRACT_DIR.exists():
        logger.info(f"Cleaning extract directory: {EXTRACT_DIR}")
        # Remove all contents of the extract directory
        for item in EXTRACT_DIR.iterdir():
            if item.is_file():
                logger.info(f"Removing file: {item}")
                item.unlink()
            elif item.is_dir():
                logger.info(f"Removing directory: {item}")
                shutil.rmtree(item)
        logger.info("Extract directory cleaned")

def download_data(url: str) -> Path:
    """Download data from URL to the download directory.
    
    Returns:
        Path to downloaded file
    """
    # Parse filename from URL
    filename = os.path.basename(urlparse(url).path)
    download_path = DOWNLOAD_DIR / filename
    
    logger.info(f"Downloading from {url}")
    logger.info(f"Saving to {download_path}")
    
    # Stream download to handle large files
    try:
        with requests.get(url, stream=True, timeout=30) as response:
            response.raise_for_status()
            
            # Get total file size if available
            total_size = int(response.headers.get('content-length', 0))
            if total_size:
                logger.info(f"File size: {total_size / (1024*1024):.2f} MB")
            
            downloaded = 0
            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Log progress every 10MB
                    if total_size and downloaded % (10 * 1024 * 1024) < 8192:
                        progress = (downloaded / total_size) * 100
                        logger.info(f"Download progress: {progress:.1f}%")
                        
        logger.info("Download complete")
        logger.info(f"Downloaded file: {download_path}")
        logger.info(f"File size: {download_path.stat().st_size / (1024*1024):.2f} MB")
        return download_path
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Download failed: {e}")
        raise

def extract_data(zip_path: Path):
    """Extract downloaded zip file to extract directory."""
    logger.info(f"Extracting {zip_path}")
    logger.info(f"Destination: {EXTRACT_DIR}")
    
    try:
        with zipfile.ZipFile(zip_path) as zf:
            # List contents
            file_list = zf.namelist()
            logger.info(f"Zip contains {len(file_list)} files/folders")
            
            # Extract all
            zf.extractall(EXTRACT_DIR)
            
        logger.info("Extraction complete")
        
        # Log extracted contents
        extracted_items = list(EXTRACT_DIR.iterdir())
        logger.info(f"Extracted {len(extracted_items)} items to {EXTRACT_DIR}")
        for item in extracted_items[:10]:  # Show first 10 items
            logger.info(f"  - {item.name}")
        if len(extracted_items) > 10:
            logger.info(f"  ... and {len(extracted_items) - 10} more items")
            
    except zipfile.BadZipFile as e:
        logger.error(f"Invalid zip file: {e}")
        raise
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        raise

def main():
    """Main execution function."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    logger.info("="*60)
    logger.info("Starting Download and Extract Process")
    logger.info("="*60)
    
    # Get latest download URL
    url = get_download_url()
    if not url:
        logger.error("No download URL found. Run email_monitor.py first.")
        return
    
    logger.info(f"Download URL: {url}")
        
    try:
        # Prepare directories
        logger.info("\n[1/4] Setting up directories...")
        setup_directories()
        
        # Clean existing data
        logger.info("\n[2/4] Cleaning existing data...")
        clean_existing_data()
        
        # Download new data
        logger.info("\n[3/4] Downloading data...")
        zip_path = download_data(url)
        
        # Extract data
        logger.info("\n[4/4] Extracting data...")
        extract_data(zip_path)
        
        logger.info("\n" + "="*60)
        logger.info("✓ Process completed successfully!")
        logger.info("="*60)
        logger.info(f"Downloaded to: {zip_path}")
        logger.info(f"Extracted to: {EXTRACT_DIR}")
        
    except Exception as e:
        logger.error("\n" + "="*60)
        logger.error("✗ Process failed!")
        logger.error("="*60)
        logger.exception("Error during download/extract process: %s", e)

if __name__ == "__main__":
    main()