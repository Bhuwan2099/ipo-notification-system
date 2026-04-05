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

client = OpenAI(api_key=OPENAI_API_KEY)


def get_site_text(url):
    """Fetches raw text from a website for GPT to process."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.get_text(separator=' ', strip=True)[:10000]
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""


def get_receivers():
    """Reads email addresses from the emails.txt file."""
    if not os.path.exists(EMAIL_FILE):
        return []
    with open(EMAIL_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]


def check_ipo_with_gpt():
    today_date = datetime.now().strftime("%Y-%m-%d")
    print(f"--- IPO Check Started for {today_date} ---")

    sebon_text = get_site_text("https://www.sebon.gov.np/ipo-approved")
    sharesansar_text = get_site_text("https://www.sharesansar.com/existing-issues")

    prompt = f"""
    Today's date is {today_date}. 
    Analyze the text from Nepal's IPO portals below. 
    Find any IPO that OPENS TODAY ({today_date}) for:
    1. 'General Public' 
    2. 'Foreign Employee' or 'Migrant Workers'.

    STRICT RULES:
    - Only return an IPO if its OPENING DATE is exactly {today_date}.
    - Ignore 'Local Residents', 'Staff', or 'Mutual Fund' quotas.
    - Return ONLY valid JSON.

    Text: SEBON: {sebon_text} | ShareSansar: {sharesansar_text}

    Return format: {{"items": [{{"name": "", "units": "", "price": "", "closing_date": "", "category": ""}}]}}
    If none, return {{"items": []}}.
    """

    try:
        response = client.responses.create(
            model="gpt-4o",
            input=[
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        found_ipos = json.loads(response.output_text).get("items", [])
    except Exception as e:
        print(f"GPT API Error: {e}")
        return

    if not found_ipos:
        print("No new IPOs opening today.")
        return

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

    with open(LOG_FILE, 'w') as f:
        json.dump(sent_log, f)


def send_email(ipo):
    receivers = get_receivers()
    if not receivers: return

    subject = f"🔔 DAILY IPO ALERT: {ipo['name']} is now OPEN!"
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

    # ✔ dummy header (no receiver leaked)
    msg['To'] = EMAIL_SENDER


    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)

            # ✔ single fast send
            server.sendmail(EMAIL_SENDER, receivers, msg.as_string())

        print(f"Daily Alert sent to {len(receivers)} people.")

    except Exception as e:
        print(f"Email failed: {e}")
