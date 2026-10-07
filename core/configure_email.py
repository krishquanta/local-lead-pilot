"""
1-Minute Interactive Gmail Setup & Verification Utility.
Prompts for email & app password, tests the connection to Google SMTP,
and saves verified credentials directly to .env.
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
_CORE = _ROOT / "core"
for _p in [str(_ROOT), str(_CORE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


import sys
import smtplib
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ENV_FILE = (Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()) / ".env"

def main():
    print("=" * 65)
    print(" ✉️  Gmail Auto-Mailer Quick Setup & Live Test")
    print("=" * 65)
    print("Google requires a 16-character 'App Password' for Python to send mail.")
    print("\n👉 If you don't have one yet:")
    print("1. Ensure 2-Step Verification is turned ON on your Google Account.")
    print("2. Open: https://myaccount.google.com/apppasswords")
    print("3. Enter app name 'ShopMailer' and click Create.")
    print("4. Copy the 16-character code shown (e.g. abcd efgh ijkl mnop).")
    print("=" * 65 + "\n")

    sender_email = input("1. Enter your Gmail address: ").strip()
    if not sender_email or "@" not in sender_email:
        print("❌ Invalid email address.")
        return

    sender_name = input("2. Enter your Name (appears in From & signature) [Web Designer]: ").strip() or "Web Designer"
    
    raw_app_password = input("3. Enter your 16-character Google App Password: ").strip()
    app_password = raw_app_password.replace(" ", "")

    if len(app_password) != 16:
        print(f"\n⚠️  Warning: App passwords are usually exactly 16 letters (you entered {len(app_password)} chars).")

    print("\n🔄 Testing live connection to smtp.gmail.com:587 ...")
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.ehlo()
        server.starttls()
        server.login(sender_email, app_password)
        server.quit()
        print("✅ SUCCESS! Google accepted your credentials. Authentication verified!\n")
    except smtplib.SMTPAuthenticationError as e:
        print(f"\n❌ Google Authentication Failed!")
        print("Reason: Google rejected the username or app password.")
        print("Troubleshooting tips:")
        print(" • Make sure 2-Step Verification is ON in your Google Account.")
        print(" • Generate a new App Password at https://myaccount.google.com/apppasswords")
        print(" • Do NOT use your regular Gmail login password (Google blocks regular passwords).")
        return
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        return

    # Write to .env
    env_content = f"""# ==============================================================
# GMAIL OUTREACH CONFIGURATION (Verified)
# ==============================================================
SENDER_EMAIL={sender_email}
SENDER_NAME={sender_name}
GMAIL_APP_PASSWORD={app_password}
AUTO_SEND_EMAILS=true
"""
    with open(ENV_FILE, mode="w", encoding="utf-8") as f:
        f.write(env_content)

    print(f"🎉 Saved to {ENV_FILE.name} successfully!")
    print("Your continuous scraper and `run.bat mailer` can now send cold emails completely automatically with ZERO approval needed.\n")

if __name__ == "__main__":
    main()
