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
    """
    Your old scraper returns EMPTY data.
    So we FIX it by calling Sharesansar API.
    GPT can still read the plain text.
    """
    try:
        api_data = requests.get(
            "https://www.sharesansar.com/api/ipo/existing-issues",
            timeout=30
        ).json()

        # Convert JSON to readable text for GPT
        text_block = json.dumps(api_data, indent=2)
        return text_block[:15000]

    except Exception as e:
        return f"SCRAPE_ERROR: {e}"

def send_debug_email(subject, message):
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

    # 1. Scrape (now fixed, real IPO data)
    content = get_site_text("https://www.sharesansar.com/existing-issues")

    # 2. GPT Analysis (unchanged)
    prompt = f"""
    Date: {today}.
    Find IPOs opening today in the provided data.
    Return strict JSON: {{"items": [{{"name": "", "open_date": "", "close_date": ""}}]}}.
    Text: {content}
    """

    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        ai_raw = completion.choices[0].message.content
        found = json.loads(ai_raw).get("items", [])

        if found:
            for ipo in found:
                send_debug_email(
                    f"🔔 IPO OPEN: {ipo.get('name')}",
                    f"Details: {json.dumps(ipo, indent=2)}"
                )
        else:
            send_debug_email(
                "Daily Check: No IPO Found",
                f"AI looked at the site but saw nothing for {today}.\n\nAI Response: {ai_raw}"
            )

    except Exception as e:
        send_debug_email("Script Error Alert", f"The script crashed with error: {e}")

if __name__ == "__main__":
    run_check()
