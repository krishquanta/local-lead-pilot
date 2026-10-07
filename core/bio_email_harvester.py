"""
Social Media Bio & Web Presence Email Harvester.
Crawls discovered Instagram and Facebook profiles and online snippets for Tamil Nadu local businesses.
Extracts official contact emails, verifies them with live DNS MX lookups,
and automatically updates the master lead database for the email outreach engine.
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
_CORE = _ROOT / "core"
for _p in [str(_ROOT), str(_CORE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


import sys
import re
import csv
import json
import time
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Set, Tuple
import urllib.parse
from bs4 import BeautifulSoup

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "leads_output"
MASTER_FILE = OUTPUT_DIR / "master_scraped_leads.csv"
ACTIVE_FILE = OUTPUT_DIR / "tamil_nadu_continuous_leads.csv"
LEADS_JS_FILE = BASE_DIR / "leads_data.js"

from email_validator_service import validate_email_address

STANDARD_FIELDNAMES = [
    "Business Name",
    "Category",
    "City",
    "Rating",
    "Review Count",
    "Phone",
    "Cleaned Mobile",
    "Gmail",
    "Website",
    "Website Status",
    "Social Media URL",
    "Address",
    "Google Maps URL",
    "Lead Score",
    "Priority Tier",
    "Verification Status",
    "Verification Notes",
    "Google Place ID",
    "Email Sent At",
    "Scraped At"
]

CRAWLER_HEADERS = {
    "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

INVALID_EMAIL_SUBSTRINGS = [
    "sentry.io", "wixpress.com", "example.com", "domain.com", "email.com",
    "w3.org", "schema.org", "cloudflare.com", "googleapis.com", "google.com",
    "wordpress.org", "github.com", "instagram.com", "facebook.com", "apple.com",
    "microsoft.com", "bing.com", "yahoo.com/help", "support@", "noreply@", "no-reply@"
]
INVALID_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".ico"
)


def extract_emails_from_text(text: str) -> List[str]:
    """Finds valid business email addresses in raw text string."""
    if not text:
        return []
    raw = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    valid = []
    for em in raw:
        em = em.strip().lower().rstrip(".,;:/'\"")
        if len(em) < 6 or len(em) > 75:
            continue
        if any(em.endswith(ext) for ext in INVALID_EXTENSIONS):
            continue
        if any(inv in em for inv in INVALID_EMAIL_SUBSTRINGS):
            continue
        parts = em.split("@")
        if len(parts) == 2:
            domain = parts[1]
            if not "." in domain or len(domain.split(".")[-1]) < 2:
                continue
            if re.match(r"^\d", domain):
                continue
        valid.append(em)
    return list(dict.fromkeys(valid))


def scrape_social_bio(social_url: str, business_name: str = "", city: str = "") -> Optional[str]:
    """
    Crawls an Instagram or Facebook profile to locate the contact email in the bio,
    and searches web indices for verified public contact info.
    """
    if not social_url or not social_url.startswith("http"):
        return None

    # Method 1: Fetch social page with Facebook Crawler UA (exposes bio in description meta)
    try:
        r = requests.get(social_url, headers=CRAWLER_HEADERS, timeout=6)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            texts_to_check = []
            for m in soup.find_all("meta"):
                c = m.get("content", "")
                if c:
                    texts_to_check.append(c)
            full_meta_text = " ".join(texts_to_check)
            emails = extract_emails_from_text(full_meta_text)
            for em in emails:
                is_valid, _ = validate_email_address(em)
                if is_valid:
                    return em
    except Exception:
        pass

    # Method 2: Extract handle and perform targeted index query
    handle = ""
    if "instagram.com/" in social_url.lower():
        match = re.search(r"instagram\.com/([a-zA-Z0-9_.-]+)", social_url)
        if match:
            h = match.group(1).rstrip("/")
            if h not in ["p", "explore", "reels", "stories", "direct", "share", "invites"]:
                handle = h

    if handle:
        query = f"site:instagram.com/{handle} email OR gmail"
        url = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(query)
        try:
            r2 = requests.get(url, headers=BROWSER_HEADERS, timeout=5)
            if r2.status_code == 200:
                soup2 = BeautifulSoup(r2.text, "html.parser")
                for item in soup2.select("li.b_algo"):
                    snippet = item.get_text()
                    emails2 = extract_emails_from_text(snippet)
                    for em in emails2:
                        is_valid, _ = validate_email_address(em)
                        if is_valid:
                            return em
        except Exception:
            pass

    # Method 3: Business name + City targeted search for public contact email
    if business_name and city:
        clean_name = re.sub(r"[^\w\s]", "", business_name).strip()
        query = f'"{clean_name}" "{city}" email OR gmail'
        url = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(query)
        try:
            r3 = requests.get(url, headers=BROWSER_HEADERS, timeout=5)
            if r3.status_code == 200:
                soup3 = BeautifulSoup(r3.text, "html.parser")
                for item in soup3.select("li.b_algo"):
                    snippet = item.get_text()
                    emails3 = extract_emails_from_text(snippet)
                    for em in emails3:
                        is_valid, _ = validate_email_address(em)
                        if is_valid:
                            return em
        except Exception:
            pass

    return None


def sync_all_files(all_leads: List[Dict[str, Any]]):
    """Syncs updated leads with both CSVs and leads_data.js in standard schema."""
    if not all_leads:
        return
    for path in [MASTER_FILE, ACTIVE_FILE]:
        if path.exists():
            with open(path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=STANDARD_FIELDNAMES, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(all_leads)

    try:
        with open(LEADS_JS_FILE, mode="w", encoding="utf-8") as f:
            f.write("window.EMBEDDED_LEADS = " + json.dumps(all_leads, indent=2, ensure_ascii=False) + ";\n")
    except Exception:
        pass


def run_bio_harvester():
    print("=" * 65)
    print("  📱 SOCIAL BIO & WEB EMAIL HARVESTER (Option 1)")
    print("=" * 65)
    print(f"  • Target: Tamil Nadu shops with no website")
    print(f"  • Reading leads from: {MASTER_FILE.name}")
    print(f"  • Verifying all discovered emails via live DNS MX lookups")
    print("=" * 65 + "\n")

    if not MASTER_FILE.exists():
        print(f"❌ Error: {MASTER_FILE} does not exist.")
        return

    with open(MASTER_FILE, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        all_leads = list(reader)

    # Find shops that have Social Media URL and no email yet, and have NO website
    candidates = []
    for l in all_leads:
        soc = (l.get("Social Media URL") or "").strip()
        current_email = (l.get("Gmail") or "").strip()
        web = (l.get("Website") or "").strip().lower()
        has_web = web.startswith("http") and "instagram.com" not in web and "facebook.com" not in web

        if soc and not current_email and not has_web:
            candidates.append(l)

    print(f"[*] Found {len(candidates)} high-priority shops with active social pages ready for bio scanning.\n")

    discovered_count = 0
    checked_count = 0

    # Multi-threaded worker for high performance
    def process_lead(lead: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
        soc = (lead.get("Social Media URL") or "").strip()
        name = lead.get("Business Name", "")
        city = lead.get("City", "")
        found = scrape_social_bio(soc, name, city)
        return lead, found

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(process_lead, lead): lead for lead in candidates}
        for future in as_completed(futures):
            checked_count += 1
            lead, found_email = future.result()
            name = lead.get("Business Name", "Shop")
            city = lead.get("City", "Tamil Nadu")

            if found_email:
                discovered_count += 1
                lead["Gmail"] = found_email
                print(f"[{checked_count}/{len(candidates)}] ✔ [FOUND EMAIL] {name} ({city}) ➔ {found_email}")
                # Save periodically
                sync_all_files(all_leads)
            else:
                if checked_count % 15 == 0 or checked_count == len(candidates):
                    print(f"[{checked_count}/{len(candidates)}] Scanned bios & snippets... (Discovered: {discovered_count})")

    # Final sync
    sync_all_files(all_leads)
    print("\n" + "=" * 65)
    print(f"  🏁 Bio Harvester Finished! Total Newly Discovered Emails: {discovered_count}")
    print(f"  • Updated {MASTER_FILE.name} and leads_data.js")
    print("=" * 65)


if __name__ == "__main__":
    run_bio_harvester()
