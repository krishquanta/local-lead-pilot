"""
Autonomous Cold Email Outreach Engine for Scraped Leads.
Features:
- Zero approval needed: Automatically emails qualified scraped leads with discovered Gmails
- Works with Gmail SMTP (smtp.gmail.com:587) via Google App Passwords
- Automatically loads credentials from .env (prompts once to setup if missing)
- --auto: Processes all pending scraped leads in batch with safe pacing (8-12s delays)
- --watch: Continuous background worker that checks for newly scraped leads every 20s and auto-sends
- Prevents duplicates: Tracks 'Email Sent At' timestamp directly in CSVs
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
_CORE = _ROOT / "core"
for _p in [str(_ROOT), str(_CORE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


import os
import sys
import csv
import time
import random
import smtplib
import argparse
import getpass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from dotenv import load_dotenv

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
ENV_FILE = BASE_DIR / ".env"
MASTER_CSV_PATH = BASE_DIR / "leads_output" / "master_scraped_leads.csv"
ACTIVE_CSV_PATH = BASE_DIR / "leads_output" / "tamil_nadu_continuous_leads.csv"

# Load environment
load_dotenv(ENV_FILE)

from outreach_generator import clean_business_name, generate_email_pitch
from email_validator_service import validate_email_address
from rate_limiter import can_send, check_and_increment, reset_if_new_day


def ensure_credentials() -> Dict[str, str]:
    """Retrieves credentials from .env or prompts user once to configure them."""
    sender_email = os.getenv("SENDER_EMAIL", "").strip()
    sender_name = os.getenv("SENDER_NAME", "").strip() or "Web Designer"
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

    if sender_email and app_password:
        return {
            "sender_email": sender_email,
            "sender_name": sender_name,
            "app_password": app_password
        }

    print("\n" + "=" * 60)
    print(" ⚙️  Gmail Configuration Required (One-time Setup)")
    print("=" * 60)
    print("To send emails automatically via your Gmail account, we need:")
    print("1. Your Gmail address")
    print("2. Your 16-character Google App Password")
    print("   (Generate one in 30 seconds at: https://myaccount.google.com/apppasswords)")
    print("=" * 60 + "\n")

    if not sender_email:
        sender_email = input("Enter your Gmail address: ").strip()
    if not sender_name:
        sender_name = input("Enter your Sender Name (e.g. Web Designer): ").strip() or "Web Designer"
    if not app_password:
        app_password = getpass.getpass("Enter your 16-character App Password (hidden): ").strip()

    if not sender_email or not app_password:
        print("\n❌ Error: Gmail address and App Password are required to send emails.")
        sys.exit(1)

    # Save to .env so user never has to type it again
    env_content = ""
    if ENV_FILE.exists():
        with open(ENV_FILE, mode="r", encoding="utf-8") as f:
            env_content = f.read()

    new_lines = []
    has_email = has_name = has_pass = False
    for line in env_content.splitlines():
        if line.startswith("SENDER_EMAIL="):
            new_lines.append(f"SENDER_EMAIL={sender_email}")
            has_email = True
        elif line.startswith("SENDER_NAME="):
            new_lines.append(f"SENDER_NAME={sender_name}")
            has_name = True
        elif line.startswith("GMAIL_APP_PASSWORD="):
            new_lines.append(f"GMAIL_APP_PASSWORD={app_password}")
            has_pass = True
        else:
            new_lines.append(line)

    if not has_email:
        new_lines.append(f"SENDER_EMAIL={sender_email}")
    if not has_name:
        new_lines.append(f"SENDER_NAME={sender_name}")
    if not has_pass:
        new_lines.append(f"GMAIL_APP_PASSWORD={app_password}")

    with open(ENV_FILE, mode="w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")

    print(f"\n✅ Credentials saved to {ENV_FILE.name} for future automatic runs!\n")
    return {
        "sender_email": sender_email,
        "sender_name": sender_name,
        "app_password": app_password
    }


def send_single_lead_email(
    lead: Dict[str, Any],
    sender_email: str,
    sender_name: str,
    app_password: str,
    smtp_server: Optional[smtplib.SMTP] = None
) -> bool:
    """Sends an email pitch to a lead via Gmail SMTP."""
    recipient_email = (lead.get("Gmail") or lead.get("Email") or "").strip()
    if not recipient_email or "@" in recipient_email is False:
        return False

    # CRITICAL RULE 1: Validate email format, syntax, disposable domains, and DNS MX records
    is_valid, validation_reason = validate_email_address(recipient_email)
    if not is_valid:
        print(f"   ❌ REJECTED INVALID EMAIL: {recipient_email} - Reason: {validation_reason}")
        return False

    # CRITICAL RULE 2: NEVER send emails to businesses that already have a website
    website = (lead.get("Website") or "").strip().lower()
    status = (lead.get("Verification Status") or "").strip().upper()
    has_real_website = website.startswith("http") and "instagram.com" not in website and "facebook.com" not in website
    if has_real_website or "WEBSITE FOUND" in status:
        print(f"   ⛔ SKIPPED {lead.get('Business Name', '')}: Business already has a website ({website}).")
        return False

    pitch = generate_email_pitch(lead, sender_name=sender_name)
    subject = pitch["subject"]
    body = pitch["body"]

    msg = MIMEMultipart()
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    owns_server = False
    server = smtp_server
    try:
        if server is None:
            owns_server = True
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
            server.ehlo()
            server.starttls()
            server.login(sender_email, app_password)

        server.sendmail(sender_email, [recipient_email], msg.as_string())
        return True
    except Exception as e:
        print(f"   ❌ Failed to email {recipient_email}: {e}")
        return False
    finally:
        if owns_server and server is not None:
            try:
                server.quit()
            except Exception:
                pass


def load_all_leads_and_pending(csv_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Loads all leads from CSV and filters pending qualified leads with Gmail."""
    if not csv_path.exists():
        return [], [], []

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        all_leads = list(reader)

    for col in ["Email Sent At", "Conversion Stage", "Message Variant"]:
        if col not in fieldnames:
            fieldnames.append(col)

    pending = []
    for lead in all_leads:
        gmail = (lead.get("Gmail") or lead.get("Email") or "").strip()
        sent_at = (lead.get("Email Sent At") or "").strip()
        status = (lead.get("Verification Status") or "").strip().upper()

        # Strict filter: ONLY qualified leads without a website that have a Gmail
        website = (lead.get("Website") or "").strip().lower()
        has_real_website = website.startswith("http") and "instagram.com" not in website and "facebook.com" not in website
        is_website_found = "WEBSITE FOUND" in status

        if has_real_website or is_website_found:
            continue

        if gmail and "@" in gmail and not sent_at:
            is_valid, _ = validate_email_address(gmail)
            if is_valid and ("HAS SOCIALS" in status or "NO WEBSITE" in status or status == ""):
                pending.append(lead)

    return all_leads, pending, fieldnames


def sync_lead_sent_status(csv_path: Path, all_leads: List[Dict[str, Any]], fieldnames: List[str]):
    """Safely updates CSV with new sent timestamps and syncs leads_data.js."""
    temp_path = csv_path.with_suffix(".tmp")
    with open(temp_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_leads)
    temp_path.replace(csv_path)

    # Also sync leads_data.js for viewer.html real-time updates
    try:
        import json
        js_file = BASE_DIR / "leads_data.js"
        with open(js_file, mode="w", encoding="utf-8") as f:
            f.write("window.EMBEDDED_LEADS = " + json.dumps(all_leads, indent=2, ensure_ascii=False) + ";\n")
    except Exception:
        pass


def process_pending_leads(creds: Dict[str, str], delay_range: tuple = (8.0, 14.0)) -> int:
    """Processes all pending scraped leads automatically without human approval."""
    reset_if_new_day()
    all_leads, pending_leads, fieldnames = load_all_leads_and_pending(MASTER_CSV_PATH)
    if not pending_leads:
        return 0

    can_proceed, sent_today, max_daily = can_send("email")
    if not can_proceed:
        print(f"\n⛔ Daily Cold Email limit reached ({sent_today}/{max_daily}). Halting to protect domain reputation.")
        return 0

    print(f"\n🚀 Found {len(pending_leads)} qualified scraped lead(s) with Gmail to contact automatically. (Daily sent: {sent_today}/{max_daily})")

    # Connect to SMTP
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=25)
        server.ehlo()
        server.starttls()
        server.login(creds["sender_email"], creds["app_password"])
    except Exception as e:
        print(f"❌ Failed to connect to Gmail SMTP: {e}")
        return 0

    sent_count = 0
    try:
        for idx, lead in enumerate(pending_leads, 1):
            can_send_next, curr_c, max_l = can_send("email")
            if not can_send_next:
                print(f"\n⛔ Daily Cold Email limit ({curr_c}/{max_l}) reached. Halting batch.")
                break

            name = clean_business_name(lead.get("Business Name", ""))
            city = lead.get("City", "Tamil Nadu")
            gmail = lead.get("Gmail") or lead.get("Email")

            print(f"[{idx}/{len(pending_leads)}] ✉️ Auto-sending email to: {name} in {city} ({gmail}) ...", end="", flush=True)

            success = send_single_lead_email(
                lead=lead,
                sender_email=creds["sender_email"],
                sender_name=creds["sender_name"],
                app_password=creds["app_password"],
                smtp_server=server
            )

            if success:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                lead["Email Sent At"] = timestamp
                lead["Conversion Stage"] = "SENT"
                pitch = generate_email_pitch(lead, sender_name=creds["sender_name"])
                lead["Message Variant"] = f"Email_{pitch.get('subject_options', ['General'])[0][:20].replace(' ', '_')}"
                check_and_increment("email")
                sent_count += 1
                print(f" ✔ Sent!")

                # Update master CSV immediately
                sync_lead_sent_status(MASTER_CSV_PATH, all_leads, fieldnames)

                # Also update active dashboard CSV if present
                if ACTIVE_CSV_PATH.exists():
                    try:
                        act_leads, _, act_fields = load_all_leads_and_pending(ACTIVE_CSV_PATH)
                        for a in act_leads:
                            if a.get("Business Name") == lead.get("Business Name"):
                                a["Email Sent At"] = timestamp
                                a["Conversion Stage"] = "SENT"
                                a["Message Variant"] = lead["Message Variant"]
                        sync_lead_sent_status(ACTIVE_CSV_PATH, act_leads, act_fields)
                    except Exception:
                        pass

                # Anti-spam pause between sends
                if idx < len(pending_leads):
                    delay = random.uniform(*delay_range)
                    print(f"   [Pacing] Sleeping {delay:.1f}s before next email...")
                    time.sleep(delay)
            else:
                print(f" ❌ Failed.")

    finally:
        try:
            server.quit()
        except Exception:
            pass

    return sent_count


def watch_mode(creds: Dict[str, str], poll_interval: int = 25):
    """Continuously checks for newly scraped leads with Gmail and sends automatically."""
    print("=" * 65)
    print(" ⚡ Continuous Auto-Email Worker Active (Zero Approval Mode)")
    print(f" • Monitoring: {MASTER_CSV_PATH.name}")
    print(f" • Sender: {creds['sender_name']} <{creds['sender_email']}>")
    print(f" • Polling every {poll_interval} seconds for newly scraped leads...")
    print(" • Press Ctrl+C anytime to stop.")
    print("=" * 65 + "\n")

    total_sent = 0
    try:
        while True:
            sent = process_pending_leads(creds)
            total_sent += sent
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print(f"\n[Auto-Email] Stopped by user. Total emails sent: {total_sent}")


def main():
    parser = argparse.ArgumentParser(description="Autonomous Cold Email Sender for Scraped Leads")
    parser.add_argument("--watch", action="store_true", help="Continuously watch CSV and auto-email new leads")
    parser.add_argument("--interval", type=int, default=25, help="Poll interval in seconds for --watch")
    args = parser.parse_args()

    creds = ensure_credentials()

    if args.watch:
        watch_mode(creds, poll_interval=args.interval)
    else:
        # Default run: auto-send to all current pending leads
        sent = process_pending_leads(creds)
        if sent == 0:
            print("No pending scraped leads with Gmail found right now.")
            print("Tip: Run with '--watch' to automatically send as the scraper discovers new leads:")
            print("     py -3 send_cold_emails.py --watch")
        else:
            print(f"\n🎉 Successfully sent {sent} cold email(s) automatically!")


if __name__ == "__main__":
    main()
