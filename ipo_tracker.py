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
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Configuration ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_FILE = "emails.txt"
LOG_FILE = "ipo_history.json"
NOTIFY_EMAIL = "bhuwan36ch23@gmail.com"

client = OpenAI(api_key=OPENAI_API_KEY)

def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=options)
    return driver

def get_site_text_selenium(driver, url, wait_for_selector=None, wait_seconds=5):
    try:
        print(f"  Loading: {url}")
        driver.get(url)
        if wait_for_selector:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
                )
            except:
                print(f"  ⚠️ Selector '{wait_for_selector}' not found, waiting {wait_seconds}s anyway...")
                time.sleep(wait_seconds)
        else:
            time.sleep(wait_seconds)

        html = driver.page_source
        print(f"  Page source: {len(html)} chars")
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style']):
            tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
        print(f"  Extracted text: {len(text)} chars")
        return text[:25000]
    except Exception as e:
        print(f"  ❌ Selenium error for {url}: {e}")
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
    --------------------------------------------
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

    print("\n[Scraping sources with Selenium...]")
    driver = get_driver()
    try:
        sebon       = get_site_text_selenium(driver, "https://www.sebon.gov.np/ipo-approved",       wait_for_selector="table tr", wait_seconds=6)
        sharesansar = get_site_text_selenium(driver, "https://www.sharesansar.com/existing-issues", wait_for_selector="table tr", wait_seconds=6)
        merolagani  = get_site_text_selenium(driver, "https://merolagani.com/IPOResult.aspx",       wait_for_selector="table tr", wait_seconds=6)
    finally:
        driver.quit()

    print(f"\nSebon: {len(sebon)} chars | Sharesansar: {len(sharesansar)} chars | Merolagani: {len(merolagani)} chars")

    if not sebon and not sharesansar and not merolagani:
        print("❌ All sources empty — cannot proceed.")
        return

    prompt = f"""
    Current Date: {today_date}.
    Task: Extract any IPO that is OPEN for application TODAY from the text below.
    An IPO is open today if its opening date <= {today_date} AND closing date >= {today_date}.
    Target categories: 'General Public' or 'Foreign Employee/Migrant Workers'.

    SOURCE 1 - SEBON:
    {sebon}
    ---
    SOURCE 2 - SHARESANSAR:
    {sharesansar}
    ---
    SOURCE 3 - MEROLAGANI:
    {merolagani}

    RULES:
    1. Include any IPO whose application window covers today {today_date}.
    2. Return JSON only: {{"items": [{{"name": "", "units": "", "price": "", "closing_date": "", "category": ""}}]}}
    3. If nothing is open today return {{"items": []}}.
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
