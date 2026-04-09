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
    """Fetches text from the IPO portals."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.get_text(separator=' ', strip=True)[:10000]
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def get_receivers():
    """Reads the subscriber list."""
    if not os.path.exists(EMAIL_FILE): return []
    with open(EMAIL_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

def send_email(ipo):
    """Sends the alert to everyone in emails.txt."""
    receivers = get_receivers()
    if not receivers: return

    subject = f"🔔 DAILY IPO ALERT: {ipo['name']} is now OPEN!"
    body = f"""
    -------------------------------------------
    A new IPO has opened today for application.

    🏢 COMPANY: {ipo.get('name')}
    📌 CATEGORY: {ipo.get('category')}
    💰 UNIT PRICE: Rs. {ipo.get('price')}
    📊 TOTAL UNITS: {ipo.get('units')}
    ⏳ CLOSING DATE: {ipo.get('closing_date')}

    🚀 Good luck with your allotment!
    --------------------------------------------
    IPO Tracking System
    """

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = f"IPO Tracker <{EMAIL_SENDER}>"
    msg['To'] = EMAIL_SENDER 

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, receivers, msg.as_string())
        print(f"✅ Alert sent for {ipo['name']}")
    except Exception as e:
        print(f"❌ Email failed: {e}")

def check_ipo_with_gpt():
    today_date = datetime.now().strftime("%Y-%m-%d")
    print(f"--- Checking IPOs for {today_date} ---")

    sebon_text = get_site_text("https://www.sebon.gov.np/ipo-approved")
    sharesansar_text = get_site_text("https://www.sharesansar.com/existing-issues")

    prompt = f"""
    Today's date is {today_date}. Identify IPOs opening TODAY ({today_date}) for 'General Public' or 'Foreign Employee'. 
    Return ONLY JSON: {{"items": [{{"name": "", "units": "", "price": "", "closing_date": "", "category": ""}}]}}
    If none, return {{"items": []}}.
    Text: {sebon_text} | {sharesansar_text}
    """

    try:
        # Fixed syntax for GPT-4o
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        found_ipos = json.loads(response.choices[0].message.content).get("items", [])
    except Exception as e:
        print(f"GPT Error: {e}")
        return

    if not found_ipos:
        print("No new IPOs opening today.")
        return

    # Load history to prevent double-sending
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            try: sent_log = json.load(f)
            except: sent_log = []
    else:
        sent_log = []

    for ipo in found_ipos:
        unique_id = f"{ipo['name']}_{ipo['category']}_{today_date}"
        if unique_id not in sent_log:
            send_email(ipo)
            sent_log.append(unique_id)

    with open(LOG_FILE, 'w') as f:
        json.dump(sent_log, f)

if __name__ == "__main__":
    check_ipo_with_gpt()
