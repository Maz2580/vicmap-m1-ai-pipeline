import os
import imaplib
import email
import logging
from pathlib import Path
from typing import Optional, Tuple, List
from datetime import datetime, timedelta
import re
from dotenv import load_dotenv
from bs4 import BeautifulSoup

from config import ORDER_NUMBER, save_download_url, get_download_info

logger = logging.getLogger(__name__)

def parse_email_date(date_str: str) -> Optional[datetime]:
    """Parse email date string into datetime object."""
    try:
        # Try standard email date format
        return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        try:
            # Try without timezone
            return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S")
        except ValueError:
            logger.warning(f"Could not parse date: {date_str}")
            return None

def extract_url_from_content(content: str) -> Optional[str]:
    """Extract download URL from email content."""
    pattern = f"https://s3[.]ap-southeast-2[.]amazonaws[.]com/cl-isd-prd-datashare-s3-delivery/Order_{ORDER_NUMBER}[.]zip"
    match = re.search(pattern, content)
    return match.group(0) if match else None

def check_email_for_download_url() -> Optional[Tuple[str, datetime]]:
    """Check email for download URLs and return the MOST RECENT one.
    
    Returns:
        Tuple of (url, email_date) from the most recent email, None otherwise
    """
    load_dotenv()
    
    # Get server settings from .env
    server = os.getenv("EMAIL_SERVER")
    port = int(os.getenv("EMAIL_IMAP_PORT", "993"))
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")
    
    if not all([email_user, email_pass]):
        raise ValueError("Email settings not configured in .env file")
    
    try:
        logger.info(f"Connecting to {server}:{port} with user {email_user}")
        mail = imaplib.IMAP4_SSL(server, port)
        
        try:
            logger.info("Attempting login...")
            mail.login(email_user, email_pass)
            logger.info("Login successful")
        except imaplib.IMAP4.error as e:
            logger.error("Login failed - authentication error")
            logger.error("For Office 365, you might need to:")
            logger.error("1. Enable IMAP in Outlook settings")
            logger.error("2. Create an App Password if 2FA is enabled")
            logger.error("3. Allow less secure app access temporarily")
            raise RuntimeError("Authentication failed - check email settings") from e
        
        mail.select('INBOX')
        
        # Search for the specific order email
        # Use two searches to handle both old and new VicMap subject formats:
        #   Old: "Your order #RK36R8 is ready to download"
        #   New: "Your DataShare Order RK36R8 is ready to download"
        search_criteria_old = f'(FROM "noreply@datashare.maps.vic.gov.au" SUBJECT "Your order #{ORDER_NUMBER} is ready to download")'
        search_criteria_new = f'(FROM "noreply@datashare.maps.vic.gov.au" SUBJECT "Your DataShare Order {ORDER_NUMBER} is ready to download")'

        all_message_nums = set()
        for criteria in [search_criteria_old, search_criteria_new]:
            logger.info(f"Searching with criteria: {criteria}")
            _, messages = mail.search(None, criteria)
            if messages[0]:
                all_message_nums.update(messages[0].split())

        if not all_message_nums:
            logger.warning(f"No messages found for order {ORDER_NUMBER}")
            return None
            
        message_nums = sorted(all_message_nums, key=lambda x: int(x))
        logger.info(f"Found {len(message_nums)} messages matching order {ORDER_NUMBER}")

        # Store all found emails with their dates
        emails_found = []

        # Process each matching message
        for msg_num in message_nums:
            _, msg_data = mail.fetch(msg_num, '(RFC822)')
            email_msg = email.message_from_bytes(msg_data[0][1])
            
            subject = email_msg['subject'] or 'No Subject'
            from_addr = email_msg['from'] or 'No From'
            date_str = email_msg['date'] or ''
            
            logger.info(f"\nChecking email:")
            logger.info(f"  Subject: {subject}")
            logger.info(f"  From: {from_addr}")
            logger.info(f"  Date: {date_str}")
            
            # Parse email date
            email_date = parse_email_date(date_str)
            if not email_date:
                logger.warning(f"Skipping email with unparseable date: {date_str}")
                continue
            
            # Get email content
            text = ""
            html = ""
            for part in email_msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        content = part.get_payload(decode=True)
                        if isinstance(content, bytes):
                            text += content.decode('utf-8', errors='ignore')
                        else:
                            text += str(content)
                    except Exception as e:
                        logger.warning(f"Could not decode text content: {e}")
                elif content_type == "text/html":
                    try:
                        content = part.get_payload(decode=True)
                        if isinstance(content, bytes):
                            html += content.decode('utf-8', errors='ignore')
                        else:
                            html += str(content)
                    except Exception as e:
                        logger.warning(f"Could not decode HTML content: {e}")
                    
            # Extract text from HTML if no plain text found
            if not text and html:
                try:
                    soup = BeautifulSoup(html, 'html.parser')
                    text = soup.get_text()
                except Exception as e:
                    logger.warning(f"Could not parse HTML content: {e}")
            
            # Look for URL in both plain text and HTML
            url = None
            for source in [text, html]:
                if source:
                    url = extract_url_from_content(source)
                    if url:
                        break
            
            if url:
                logger.info(f"Found download URL: {url}")
                emails_found.append({
                    'url': url,
                    'date': email_date,
                    'date_str': date_str
                })
            else:
                logger.warning("No download URL found in this email")
        
        # Close mail connection
        mail.close()
        mail.logout()
        
        # If no emails with URLs found
        if not emails_found:
            logger.warning("No emails with download URLs found")
            return None
        
        # Sort by date to find the most recent
        emails_found.sort(key=lambda x: x['date'], reverse=True)
        most_recent = emails_found[0]
        
        logger.info(f"\n{'='*60}")
        logger.info(f"SUMMARY: Found {len(emails_found)} email(s) with download URLs")
        for i, email_info in enumerate(emails_found, 1):
            status = "✓ MOST RECENT" if i == 1 else "  (older)"
            logger.info(f"{status} - Email from {email_info['date_str']}")
        logger.info(f"{'='*60}\n")
        
        return most_recent['url'], most_recent['date']
                
    except Exception as e:
        logger.exception("Error checking email: %s", e)
        return None

def test_connection():
    """Test connection to email server."""
    import socket
    server = "outlook.office365.com"
    try:
        # Try DNS lookup first
        ip = socket.gethostbyname(server)
        print(f"DNS lookup successful: {server} -> {ip}")
        
        # Try connecting to the IMAP port
        sock = socket.create_connection((server, 993), timeout=10)
        sock.close()
        print("Connection test successful")
        return True
    except socket.gaierror as e:
        print(f"DNS lookup failed: {e}")
        print("Possible issues:")
        print("1. No internet connection")
        print("2. DNS issues - try using 8.8.8.8 as DNS server")
        return False
    except socket.error as e:
        print(f"Connection failed: {e}")
        print("Possible issues:")
        print("1. Firewall blocking IMAP")
        print("2. Proxy server interference")
        return False

def main():
    """Command line interface to check email and update URL."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    if not test_connection():
        return
    
    # Check for existing download info
    existing_info = get_download_info()
    if existing_info and existing_info.get('email_date'):
        existing_date = datetime.fromisoformat(existing_info['email_date'])
        logger.info(f"\nCurrently saved email date: {existing_date}")
    else:
        logger.info("\nNo existing download info found")
    
    # Check for new emails
    result = check_email_for_download_url()
    if result:
        url, email_date = result
        
        # Compare with existing email date
        if existing_info and existing_info.get('email_date'):
            existing_date = datetime.fromisoformat(existing_info['email_date'])
            
            # Remove timezone info for comparison if needed
            email_date_compare = email_date.replace(tzinfo=None) if email_date.tzinfo else email_date
            existing_date_compare = existing_date.replace(tzinfo=None) if existing_date.tzinfo else existing_date
            
            if email_date_compare <= existing_date_compare:
                print(f"\n⚠ The most recent email found ({email_date}) is not newer than the saved one ({existing_date})")
                print("No update needed - you already have the latest data")
                return
            else:
                print(f"\n✓ Found newer email! ({email_date} vs saved {existing_date})")
        
        # Save the new URL and date
        save_download_url(url, email_date)
        print(f"\n✓ Successfully saved new download URL from email dated {email_date}")
        print(f"URL: {url}")
    else:
        print("\n⚠ No download URLs found in emails")

if __name__ == "__main__":
    main()