import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import json

# --- HARDCODED CONFIGURATION ---
TARGET_EMAIL = "bhuwan36ch23@gmail.com"
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

def get_site_text(url):
    """Fetches text from the IPO portals."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.get_text(separator=' ', strip=True)[:12000]
    except Exception as e:
        print(f"Scraper Error ({url}): {e}")
        return ""

def send_email(ipo_data):
    """Sends the alert directly to you."""
    subject = f"🔔 IPO OPEN TODAY: {ipo_data.get('name')}"
    body = f"""
    IPO ALERT - {datetime.now().strftime('%Y-%m-%d')}
    -------------------------------------------
    COMPANY: {ipo_data.get('name')}
    CATEGORY: {ipo_data.get('category')}
    PRICE: Rs. {ipo_data.get('price')}
    UNITS: {ipo_data.get('units')}
    CLOSING: {ipo_data.get('closing_date')}
    
    Check MeroShare: https://meroshare.cdsc.com.np/
    -------------------------------------------
    """
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = TARGET_EMAIL

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, [TARGET_EMAIL], msg.as_string())
        print(f"✅ Email sent to {TARGET_EMAIL}")
    except Exception as e:
        print(f"❌ Email failed: {e}")

def check_ipo():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"--- Running IPO Check for {today} ---")

    # Scrape data
    site_data = get_site_text("https://www.sharesansar.com/existing-issues")
    
    prompt = f"""
    Today is {today}. Look at this text and find any IPO opening EXACTLY TODAY for 'General Public' or 'Foreign Employee'.
    Text: {site_data}
    
    Return ONLY JSON: {{"items": [{{"name": "", "category": "", "price": "", "units": "", "closing_date": ""}}]}}
    If nothing opens today, return {{"items": []}}
    """

    try:
        # FIXED: Corrected API call for GPT-4o
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        # FIXED: Corrected property access
        content = response.choices[0].message.content
        print(f"AI Response: {content}")
        
        found_ipos = json.loads(content).get("items", [])
        
        if not found_ipos:
            print("No IPOs found for today.")
            return

        for ipo in found_ipos:
            send_email(ipo)

    except Exception as e:
        print(f"Error during execution: {e}")

if __name__ == "__main__":
    check_ipo()
