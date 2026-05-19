"""
Diagnostic script to investigate why the email monitor
isn't finding the latest VicMap email.

Run: python diagnose_email.py
"""
import imaplib
import email
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

ORDER_NUMBER = "RK36R8"

server = os.getenv("EMAIL_SERVER")
port = int(os.getenv("EMAIL_IMAP_PORT", "993"))
email_user = os.getenv("EMAIL_USER")
email_pass = os.getenv("EMAIL_PASS")

print(f"Connecting to {server}:{port} as {email_user}...")
mail = imaplib.IMAP4_SSL(server, port)
mail.login(email_user, email_pass)
print("Login successful\n")

# ── Test 1: Check what folders exist ──────────────────────────
print("=" * 60)
print("TEST 1: Available mailbox folders")
print("=" * 60)
status, folders = mail.list()
for f in folders:
    print(f"  {f.decode()}")
print()

# ── Test 2: Current INBOX search (your existing criteria) ────
print("=" * 60)
print("TEST 2: Current search criteria (exact match)")
print("=" * 60)
mail.select("INBOX")
search_criteria = f'(FROM "noreply@datashare.maps.vic.gov.au" SUBJECT "Your order #{ORDER_NUMBER} is ready to download")'
print(f"  Criteria: {search_criteria}")
_, messages = mail.search(None, search_criteria)
msg_nums = messages[0].split() if messages[0] else []
print(f"  Found: {len(msg_nums)} emails")
for num in msg_nums:
    _, data = mail.fetch(num, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])")
    header = data[0][1].decode("utf-8", errors="ignore")
    print(f"    #{num.decode()}: {header.strip()}")
print()

# ── Test 3: Broader search — just FROM datashare ─────────────
print("=" * 60)
print("TEST 3: Broader search (FROM datashare only, no SUBJECT filter)")
print("=" * 60)
search_criteria_broad = '(FROM "datashare.maps.vic.gov.au")'
print(f"  Criteria: {search_criteria_broad}")
_, messages = mail.search(None, search_criteria_broad)
msg_nums = messages[0].split() if messages[0] else []
print(f"  Found: {len(msg_nums)} emails")
for num in msg_nums:
    _, data = mail.fetch(num, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM)])")
    header = data[0][1].decode("utf-8", errors="ignore")
    print(f"    #{num.decode()}:")
    for line in header.strip().split("\r\n"):
        if line.strip():
            print(f"      {line.strip()}")
    print()

# ── Test 4: Search by SINCE date (last 30 days from datashare)
print("=" * 60)
print("TEST 4: SINCE date search (last 30 days, from datashare)")
print("=" * 60)
since_date = (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")
search_criteria_since = f'(FROM "datashare.maps.vic.gov.au" SINCE {since_date})'
print(f"  Criteria: {search_criteria_since}")
_, messages = mail.search(None, search_criteria_since)
msg_nums = messages[0].split() if messages[0] else []
print(f"  Found: {len(msg_nums)} emails")
for num in msg_nums:
    _, data = mail.fetch(num, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])")
    header = data[0][1].decode("utf-8", errors="ignore")
    print(f"    #{num.decode()}: {header.strip()}")
print()

# ── Test 5: Check Junk/Clutter/Other folders ─────────────────
print("=" * 60)
print("TEST 5: Searching other folders for datashare emails")
print("=" * 60)
folders_to_check = [
    "Junk Email", "Junk", "JUNK",
    "Clutter",
    "Deleted Items",
    '"Focused"',
    "INBOX/Focused", "INBOX/Other",
]
for folder_name in folders_to_check:
    try:
        status, _ = mail.select(folder_name, readonly=True)
        if status == "OK":
            _, messages = mail.search(None, '(FROM "datashare.maps.vic.gov.au")')
            msg_nums = messages[0].split() if messages[0] else []
            if msg_nums:
                print(f"  [{folder_name}] Found {len(msg_nums)} email(s)!")
                for num in msg_nums[-3:]:  # last 3 only
                    _, data = mail.fetch(num, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])")
                    header = data[0][1].decode("utf-8", errors="ignore")
                    print(f"    #{num.decode()}: {header.strip()}")
            else:
                print(f"  [{folder_name}] No datashare emails")
        else:
            print(f"  [{folder_name}] Could not select folder")
    except Exception as e:
        print(f"  [{folder_name}] Error: {e}")
print()

# ── Test 6: Check latest email body for URL pattern ──────────
print("=" * 60)
print("TEST 6: Check URL extraction from latest matching email")
print("=" * 60)
mail.select("INBOX")
_, messages = mail.search(None, '(FROM "datashare.maps.vic.gov.au")')
msg_nums = messages[0].split() if messages[0] else []
if msg_nums:
    # Get the LAST (newest by IMAP sequence) message
    latest_num = msg_nums[-1]
    _, msg_data = mail.fetch(latest_num, "(RFC822)")
    email_msg = email.message_from_bytes(msg_data[0][1])
    print(f"  Subject: {email_msg['subject']}")
    print(f"  Date:    {email_msg['date']}")
    print(f"  From:    {email_msg['from']}")

    # Extract body
    text = ""
    html = ""
    for part in email_msg.walk():
        ct = part.get_content_type()
        if ct == "text/plain":
            payload = part.get_payload(decode=True)
            if payload:
                text += payload.decode("utf-8", errors="ignore")
        elif ct == "text/html":
            payload = part.get_payload(decode=True)
            if payload:
                html += payload.decode("utf-8", errors="ignore")

    # Try the existing regex pattern
    pattern_strict = f"https://s3[.]ap-southeast-2[.]amazonaws[.]com/cl-isd-prd-datashare-s3-delivery/Order_{ORDER_NUMBER}[.]zip"
    # Also try a looser pattern
    pattern_loose = r"https?://\S*Order_\S*\.zip"
    pattern_any_s3 = r"https?://s3[.\w-]*amazonaws\.com/\S+"

    for label, content in [("Plain text", text), ("HTML", html)]:
        if not content:
            print(f"\n  {label}: (empty)")
            continue
        print(f"\n  {label} ({len(content)} chars):")
        match_strict = re.search(pattern_strict, content)
        match_loose = re.search(pattern_loose, content)
        match_s3 = re.search(pattern_any_s3, content)
        print(f"    Strict regex match:  {'YES -> ' + match_strict.group(0) if match_strict else 'NO'}")
        print(f"    Loose Order_ match:  {'YES -> ' + match_loose.group(0) if match_loose else 'NO'}")
        print(f"    Any S3 URL match:    {'YES -> ' + match_s3.group(0)[:120] if match_s3 else 'NO'}")

    # Check date parsing
    print(f"\n  Date parsing test:")
    date_str = email_msg["date"]
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S"]:
        try:
            parsed = datetime.strptime(date_str, fmt)
            print(f"    Format '{fmt}' -> {parsed}")
            break
        except ValueError:
            print(f"    Format '{fmt}' -> FAILED")
else:
    print("  No datashare emails found in INBOX at all!")

print()

# ── Test 7: UID-based search (bypasses sequence issues) ──────
print("=" * 60)
print("TEST 7: UID search (bypasses sequence number issues)")
print("=" * 60)
mail.select("INBOX")
search_criteria = f'(FROM "noreply@datashare.maps.vic.gov.au")'
_, messages = mail.uid("search", None, search_criteria)
uid_nums = messages[0].split() if messages[0] else []
print(f"  UID search found: {len(uid_nums)} emails")
if uid_nums:
    print(f"  UIDs: {[u.decode() for u in uid_nums[-5:]]}")
    for uid in uid_nums[-3:]:
        _, data = mail.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])")
        header = data[0][1].decode("utf-8", errors="ignore")
        print(f"    UID {uid.decode()}: {header.strip()}")

mail.close()
mail.logout()
print("\nDone. Share the output above so we can identify the root cause.")
