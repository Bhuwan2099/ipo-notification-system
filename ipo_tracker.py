import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import json
import io
import traceback
import sys

# --- Configuration ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_FILE = "emails.txt"
LOG_FILE = "ipo_history.json"
NOTIFY_EMAIL = "bhuwan36ch23@gmail.com"

client = OpenAI(api_key=OPENAI_API_KEY)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,*/*',
    'Accept-Language': 'en-US,en;q=0.9',
}

def get_site_text(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, 'html.parser')
        for tag in soup(['script', 'style']): tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
        print(f"  {url} — {len(text)} chars")
        return text[:20000]
    except Exception as e:
        print(f"  ❌ Error {url}: {e}")
        return ""

def send_log_email(subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"IPO Tracker <{EMAIL_SENDER}>"
        msg['To'] = NOTIFY_EMAIL
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, [NOTIFY_EMAIL], msg.as_string())
        print(f"✅ Log email sent to {NOTIFY_EMAIL}")
    except Exception as e:
        print(f"❌ Log email failed: {e}")

def get_receivers():
    if not os.path.exists(EMAIL_FILE): return []
    with open(EMAIL_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

def send_email(ipo):
    receivers = list(set(get_receivers() + [NOTIFY_EMAIL]))
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
-------------------------------------------
IPO Tracking System
    """
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = f"IPO Tracker <{EMAIL_SENDER}>"
    msg['To'] = ", ".join(receivers)
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, receivers, msg.as_string())
        print(f"✅ Alert successfully sent for {ipo['name']}")
    except Exception as e:
        print(f"❌ Email failed: {e}")

def check_ipo_with_gpt():
    today_date = datetime.now().strftime("%Y-%m-%d")
    print(f"--- Running Critical Check: {today_date} ---")

    sharesansar = get_site_text("https://www.sharesansar.com/existing-issues")
    merolagani  = get_site_text("https://merolagani.com/IPOResult.aspx")

    prompt = f"""
Today is {today_date}.
Find ALL IPOs currently open for application today from the data below.
An IPO is open if: opening_date <= {today_date} <= closing_date.
Target: General Public or Foreign Employee/Migrant Workers.

SHARESANSAR:
{sharesansar}
---
MEROLAGANI:
{merolagani}

Return ONLY this JSON:
{{"items": [{{"name": "", "units": "", "price": "", "closing_date": "", "category": ""}}]}}
If none: {{"items": []}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0
        )
        content = response.choices[0].message.content
        print(f"\nAI Output: {content}")
        found_ipos = json.loads(content).get("items", [])
    except Exception as e:
        print(f"GPT or JSON Error: {e}")
        return

    if not found_ipos:
        print(f"No IPOs found open on {today_date}.")
        return

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            try: sent_log = json.load(f)
            except: sent_log = []
    else:
        sent_log = []

    for ipo in found_ipos:
        name = ipo.get('name', 'Unknown')
        category = ipo.get('category', 'General')
        unique_id = f"{name}_{category}_{today_date}"
        if unique_id not in sent_log:
            send_email(ipo)
            sent_log.append(unique_id)
        else:
            print(f"Already sent: {unique_id}")

    with open(LOG_FILE, 'w') as f:
        json.dump(sent_log, f)

if __name__ == "__main__":
    log_capture = io.StringIO()
    sys.stdout = log_capture

    try:
        check_ipo_with_gpt()
        sys.stdout = sys.__stdout__
        output = log_capture.getvalue()
        print(output)
        send_log_email("📋 IPO Tracker — Run Complete", output)
    except Exception:
        sys.stdout = sys.__stdout__
        output = log_capture.getvalue()
        error = traceback.format_exc()
        full_output = f"OUTPUT:\n{output}\n\nERROR:\n{error}"
        print(full_output)
        send_log_email("❌ IPO Tracker — CRASHED", full_output)
