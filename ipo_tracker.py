import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import json

# --- Configuration (Pulled from GitHub Secrets & Environment) ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_FILE = "emails.txt"
LOG_FILE = "ipo_history.json"

# ✅ Set to True for testing — forces an email even if no real IPO found today
TEST_MODE = True

client = OpenAI(api_key=OPENAI_API_KEY)


def get_site_text(url):
    """Fetches raw text from a website for GPT to process."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)[:10000]

        # ✅ FIX 2: Warn if content looks empty or suspiciously short
        if len(text) < 200:
            print(f"WARNING: Content from {url} looks too short ({len(text)} chars) — site may have blocked the scraper or uses JS rendering.")
            return ""

        print(f"OK: Fetched {len(text)} chars from {url}")
        return text

    except requests.HTTPError as e:
        print(f"HTTP Error fetching {url}: {e.response.status_code} {e}")
        return ""
    except requests.Timeout:
        print(f"Timeout fetching {url} — site took too long to respond.")
        return ""
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""


def get_receivers():
    """Reads email addresses from the emails.txt file."""
    if not os.path.exists(EMAIL_FILE):
        print("WARNING: emails.txt not found!")
        return []
    receivers = [line.strip() for line in open(EMAIL_FILE) if line.strip()]
    if not receivers:
        print("WARNING: emails.txt is empty — no receivers!")
    return receivers


def check_ipo_with_gpt():
    today_date = datetime.now().strftime("%Y-%m-%d")
    print(f"--- IPO Check Started for {today_date} ---")

    # ✅ TEST MODE: skip scraping and send a dummy email
    if TEST_MODE:
        print("TEST MODE is ON — sending a test email without scraping.")
        dummy_ipo = {
            "name": "Test Company Ltd.",
            "category": "General Public",
            "price": "100",
            "units": "500,000",
            "closing_date": "2025-06-20"
        }
        send_email(dummy_ipo, is_test=True)
        return

    sebon_text = get_site_text("https://www.sebon.gov.np/ipo-approved")
    sharesansar_text = get_site_text("https://www.sharesansar.com/existing-issues")

    # ✅ FIX 2: Abort early if both sources failed
    if not sebon_text and not sharesansar_text:
        print("ERROR: Both sources returned empty content. Cannot proceed. Check scraping or site availability.")
        return

    # ✅ FIX 1: More flexible date prompt — GPT handles varied date formats
    prompt = f"""
    Today's date is {today_date} (format: YYYY-MM-DD).
    
    Analyze the text from Nepal's IPO portals below.
    Find any IPO that OPENS TODAY for:
    1. 'General Public'
    2. 'Foreign Employee' or 'Migrant Workers'.

    IMPORTANT — Date matching rules:
    - The opening date may appear in various formats: "2025-06-15", "2025/06/15", "June 15, 2025", "15 Jun 2025", "15-06-2025", "2082-03-01" (Nepali BS date), etc.
    - Convert any format to determine if the opening date matches today: {today_date}.
    - If the text says the IPO is "currently open" or "open now" without an explicit date, treat it as opening today.
    - If the opening date is ambiguous but close to today (within 1 day), include it and note the uncertainty.

    STRICT RULES:
    - Ignore 'Local Residents', 'Staff', or 'Mutual Fund' quotas.
    - Return ONLY valid JSON.

    Text from SEBON: {sebon_text}
    Text from ShareSansar: {sharesansar_text}

    Return format: {{"items": [{{"name": "", "units": "", "price": "", "closing_date": "", "category": ""}}]}}
    If none found, return {{"items": []}}.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        raw_content = response.choices[0].message.content
        print(f"GPT raw response: {raw_content}")  # ✅ FIX 2: Log GPT output
        found_ipos = json.loads(raw_content).get("items", [])
    except Exception as e:
        print(f"GPT API Error: {e}")
        return

    if not found_ipos:
        print("No new IPOs opening today.")
        return

    print(f"Found {len(found_ipos)} IPO(s): {[i['name'] for i in found_ipos]}")

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            sent_log = json.load(f)
    else:
        sent_log = []

    for ipo in found_ipos:
        unique_id = f"{ipo['name']}_{ipo['category']}"
        if unique_id not in sent_log:
            send_email(ipo)
            sent_log.append(unique_id)
            print(f"Email sent for: {unique_id}")
        else:
            print(f"Skipping {unique_id} — already sent previously.")

    with open(LOG_FILE, 'w') as f:
        json.dump(sent_log, f)


def send_email(ipo, is_test=False):
    receivers = get_receivers()
    if not receivers:
        return

    test_banner = "\n    ⚠️  THIS IS A TEST EMAIL — not a real IPO alert.\n" if is_test else ""
    subject = f"{'[TEST] ' if is_test else ''}🔔 DAILY IPO ALERT: {ipo['name']} is now OPEN!"
    body = f"""
    -------------------------------------------
    {test_banner}
    A new IPO has opened today for application.

    🏢 COMPANY: {ipo['name']}
    📌 CATEGORY: {ipo['category']}
    💰 UNIT PRICE: Rs. {ipo['price']}
    📊 TOTAL UNITS: {ipo['units']}
    ⏳ CLOSING DATE: {ipo['closing_date']}

       🚀 Good luck with your allotment!

        Please note that this is an auto generated email, please check your meroshare (https://meroshare.cdsc.com.np/#/login) to verify it.
    --------------------------------------------
    IPO Tracking System by Bhuwan Chaulagain
    """

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = f"IPO-tracking-system <{EMAIL_SENDER}>"
    msg['To'] = "IPO Notification"

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, receivers, msg.as_string())
        print(f"{'Test alert' if is_test else 'Daily alert'} sent to {len(receivers)} people.")
    except Exception as e:
        print(f"Email failed: {e}")


if __name__ == "__main__":
    check_ipo_with_gpt()
