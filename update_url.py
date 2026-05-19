#!/usr/bin/env python
import sys
import re
from config import save_download_url, ORDER_NUMBER

def extract_url_from_email_text(text: str) -> str:
    """Extract the download URL from email text."""
    # Look for URLs containing our order number
    pattern = f"https://[^\s]+Order_{ORDER_NUMBER}\.zip"
    match = re.search(pattern, text)
    if match:
        return match.group(0)
    return None

def main():
    # If URL provided directly, use it
    if len(sys.argv) > 1:
        url = sys.argv[1]
        if ORDER_NUMBER not in url:
            print(f"Warning: URL doesn't contain expected order number {ORDER_NUMBER}")
        save_download_url(url)
        print(f"Saved download URL: {url}")
        return

    # Otherwise, read from stdin (piped email text)
    print("Paste the email content (press Ctrl+D when done):")
    email_text = sys.stdin.read()
    
    url = extract_url_from_email_text(email_text)
    if url:
        save_download_url(url)
        print(f"Saved download URL: {url}")
    else:
        print(f"No URL found containing order number {ORDER_NUMBER}")
        sys.exit(1)

if __name__ == "__main__":
    main()