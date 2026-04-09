import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import json

# --- Config ---
TARGET_EMAIL = "bhuwan36ch23@gmail.com"
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

def get_site_text(url):
    """Attempts to scrape with browser-like headers."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.get_text(separator=' ', strip=True)[:15000]
    except Exception as e:
        return f"SCRAPE_ERROR: {e}"

def send_debug_email(subject, message):
    """Sends a direct email to you no matter what."""
    msg = MIMEText(message)
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = TARGET_EMAIL
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, [TARGET_EMAIL], msg.as_string())
        print(f"Debug email sent to {TARGET_EMAIL}")
    except Exception as e:
        print(f"SMTP Critical Failure: {e}")

def run_check():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"Checking for {today}...")

    # 1. Scrape
    content = get_site_text("https://www.sharesansar.com/existing-issues")
    
    # 2. GPT Analysis
    prompt = f"Date: {today}. Find any IPO opening today in this text. Return JSON: {{'items': [...]}}. Text: {content}"
    
    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        ai_raw = completion.choices[0].message.content
        found = json.loads(ai_raw).get("items", [])
        
        if found:
            # Send the actual alert
            for ipo in found:
                send_debug_email(f"🔔 IPO OPEN: {ipo.get('name')}", f"Details: {json.dumps(ipo, indent=2)}")
        else:
            # Send a 'Nothing Found' email so you KNOW the script ran
            send_debug_email(f"Daily Check: No IPO Found", f"AI looked at the site but saw nothing for {today}.\n\nAI Response: {ai_raw}")

    except Exception as e:
        send_debug_email("Script Error Alert", f"The script crashed with error: {e}")

if __name__ == "__main__":
    run_check()
