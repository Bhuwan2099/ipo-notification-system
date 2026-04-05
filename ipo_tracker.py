import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import json

# --- Configuration ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_FILE = "emails.txt"
LOG_FILE = "ipo_history.json"

client = OpenAI(api_key=OPENAI_API_KEY)


def get_site_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)[:10000]

        if len(text) < 200:
            print(f"WARNING: Content from {url} looks too short ({len(text)} chars) — site may have blocked scraper or uses JS rendering.")
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
    if not os.path.exists(EMAIL_FILE):
        print("WARNING: emails.txt not found!")
        return []
    receivers = [line.strip() for line in open(EMAIL_FILE) if line.strip()]
    if not receivers:
        print("WARNING: emails.txt is empty — no receivers!")
    return receivers


def load_sent_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            return json.load(f)
    return []


def save_sent_log(sent_log):
    with open(LOG_FILE, 'w') as f:
        json.dump(sent_log, f)


def check_ipo_with_gpt():
    today_date = datetime.now().strftime("%Y-%m-%d")
    print(f"--- IPO Check Started for {today_date} ---")

    sebon_text = get_site_text("https://www.sebon.gov.np/ipo-approved")
    sharesansar_text = get_site_text("https://www.sharesansar.com/existing-issues")

    if not sebon_text and not sharesansar_text:
        print("ERROR: Both sources returned empty content. Cannot proceed.")
        return

    prompt = f"""
    Today's date is {today_date} (format: YYYY-MM-DD).

    Analyze the text from Nepal's IPO portals below.
    Find any IPO that OPENS TODAY for ONLY these two categories:
    1. 'General Public'
    2. 'Foreign Employee' or 'Migrant Workers'

    IMPORTANT — Date matching rules:
    - The opening date may appear in various formats: "2025-06-15", "2025/06/15", "June 15, 2025", "15 Jun 2025", "15-06-2025", Nepali BS date, etc.
    - Convert any format to determine if the opening date matches today: {today_date}.
    - If the text says the IPO is "currently open" or "open now" without an explicit date, treat it as opening today.
    - If the opening date is ambiguous but close to today (within 1 day), include it.

    STRICT RULES:
    - ONLY return IPOs for 'General Public' OR 'Foreign Employee'/'Migrant Workers' categories.
    - Completely IGNORE and DO NOT return: 'Local Residents', 'Staff', 'Mutual Fund', or any other quota.
    - Each company should appear AT MOST ONCE in the results, even if it has both General Public and FE quotas.
      In that case, set category as "General Public & Foreign Employee".
    - Return ONLY valid JSON, no extra text.

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
        print(f"GPT raw response: {raw_content}")
        found_ipos = json.loads(raw_content).get("items", [])
    except Exception as e:
        print(f"GPT API Error: {e}")
        return

    if not found_ipos:
        print("No new IPOs opening today.")
        return

    print(f"Found {len(found_ipos)} IPO(s): {[i['name'] for i in found_ipos]}")

    sent_log = load_sent_log()

    for ipo in found_ipos:
        # ✅ Keyed by company name only — ensures 1 email per company ever
        unique_id = ipo['name'].strip().lower()
        if unique_id not in sent_log:
            send_email(ipo)
            sent_log.append(unique_id)
            save_sent_log(sent_log)
            print(f"Email sent and logged for: {ipo['name']}")
        else:
            print(f"Skipping {ipo['name']} — already sent previously.")


def send_email(ipo):
    receivers = get_receivers()
    if not receivers:
        return

    subject = f"🔔 IPO ALERT: {ipo['name']} is now OPEN!"
    body = f"""
    -------------------------------------------
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
    msg['To'] = EMAIL_SENDER

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, receivers, msg.as_string())
        print(f"Alert sent to {len(receivers)} people.")
    except Exception as e:
        print(f"Email failed: {e}")


if __name__ == "__main__":
    check_ipo_with_gpt()
