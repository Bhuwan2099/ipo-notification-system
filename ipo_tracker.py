import os
import smtplib
import json
import io
import traceback
import sys
import time
from email.mime.text import MIMEText
from datetime import datetime
from bs4 import BeautifulSoup
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Configuration ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
EMAIL_PASSWORD  = os.environ.get("EMAIL_PASSWORD")
EMAIL_SENDER    = os.environ.get("EMAIL_SENDER")
EMAIL_FILE      = "emails.txt"
LOG_FILE        = "ipo_history.json"
NOTIFY_EMAIL    = "bhuwan36ch23@gmail.com"

client = OpenAI(api_key=OPENAI_API_KEY)

def get_driver():
    options = Options()
    options.binary_location = "/usr/bin/chromium-browser"
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    return driver

def get_site_text(driver, url):
    try:
        print(f"  Loading: {url}")
        driver.get(url)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tr"))
            )
        except:
            time.sleep(6)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        for tag in soup(['script', 'style']): tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
        print(f"  Extracted: {len(text)} chars")
        return text[:20000]
    except Exception as e:
        print(f"  ❌ Error {url}: {e}")
        return ""

def send_log_email(subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From']    = f"IPO Tracker <{EMAIL_SENDER}>"
        msg['To']      = NOTIFY_EMAIL
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.sendmail(EMAIL_SENDER, [NOTIFY_EMAIL], msg.as_string())
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
           IPO TRACKING SYSTEM
-------------------------------------------
A new IPO has opened today for application.

🏢 COMPANY:      {ipo.get('name')}
📌 CATEGORY:     {ipo.get('category')}
💰 UNIT PRICE:   Rs. {ipo.get('price')}
📊 TOTAL UNITS:  {ipo.get('units')}
⏳ CLOSING DATE: {ipo.get('closing_date')}

🚀 Good luck with your allotment!
-------------------------------------------
See you with another IPO update      -- Bhuwan Chaulagain
    """
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From']    = f"IPO Tracker <{EMAIL_SENDER}>"
    msg['To']      = "Undisclosed Recipeints"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.sendmail(EMAIL_SENDER, receivers, msg.as_string())
        print(f"✅ Alert sent for {ipo['name']}")
    except Exception as e:
        print(f"❌ Email failed: {e}")

def check_ipo_with_gpt():
    today_date = datetime.now().strftime("%Y-%m-%d")
    print(f"--- Running Critical Check: {today_date} ---")

    driver = get_driver()
    try:
        sharesansar = get_site_text(driver, "https://www.sharesansar.com/existing-issues")
        merolagani  = get_site_text(driver, "https://merolagani.com/IPOResult.aspx")
    finally:
        driver.quit()

    print(f"\nSharesansar: {len(sharesansar)} | Merolagani: {len(merolagani)}")

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

    sent_log = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            try: sent_log = json.load(f)
            except: sent_log = []

    for ipo in found_ipos:
        name     = ipo.get('name', 'Unknown')
        category = ipo.get('category', 'General')
        uid      = f"{name}_{category}_{today_date}"
        if uid not in sent_log:
            send_email(ipo)
            sent_log.append(uid)
        else:
            print(f"Already sent: {uid}")

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
        full = f"OUTPUT:\n{output}\n\nERROR:\n{error}"
        print(full)
        send_log_email("❌ IPO Tracker — CRASHED", full)
