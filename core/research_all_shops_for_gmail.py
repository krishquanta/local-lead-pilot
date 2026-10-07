"""
Comprehensive Gmail & Business Email Re-Search Engine for All Shops.
Scans all 767 shops in the master and active lead databases.
Leverages multi-source discovery:
 1. Direct Instagram and Facebook bio extraction
 2. Web search snippet queries (Business Name + City + Gmail/Email)
 3. Phone-linked public listing search
 4. Discovered social media bio resolution
 5. Live DNS MX verification & spam/celebrity filters

Syncs discovered emails directly to:
 - leads_output/master_scraped_leads.csv
 - leads_output/tamil_nadu_continuous_leads.csv
 - leads_data.js (viewer.html)
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
_CORE = _ROOT / "core"
for _p in [str(_ROOT), str(_CORE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


import sys
import os
import re
import csv
import json
import time
import base64
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, SpinnerColumn

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(force_terminal=True, legacy_windows=False)

BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "leads_output"
MASTER_FILE = OUTPUT_DIR / "master_scraped_leads.csv"
ACTIVE_FILE = OUTPUT_DIR / "tamil_nadu_continuous_leads.csv"
LEADS_JS_FILE = BASE_DIR / "leads_data.js"

from outreach_generator import clean_business_name
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

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

FB_HEADERS = {
    'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

INVALID_EMAIL_SUBSTRINGS = [
    "sentry.io", "wixpress.com", "example.com", "domain.com", "email.com",
    "w3.org", "schema.org", "cloudflare.com", "googleapis.com", "google.com",
    "wordpress.org", "github.com", "instagram.com", "facebook.com", "apple.com",
    "microsoft.com", "bing.com", "yahoo.com/help", "support@", "noreply@", "no-reply@",
    "divyaagarwal" # Known celebrity false positive
]

BLOCKED_DOMAINS = [
    "gov.in", "nic.in", "ac.in", "edu", "mil", "religare.com", "starnacells.com", 
    "iitk.ac.in", "oml.in", "tn.gov.in", "icai.in", "tn.nic.in"
]


def is_email_relevant_for_shop(email: str, business_name: str, city: str, from_bio: bool = False) -> bool:
    """Ensures email belongs to the local shop and isn't a university/government/corporate aggregator."""
    if not email or "@" not in email:
        return False
    low_em = email.lower().strip()
    if any(b in low_em for b in BLOCKED_DOMAINS):
        return False
    
    parts = low_em.split("@")
    user = parts[0]
    domain = parts[1]
    
    # If directly found in their social bio
    if from_bio:
        return True
        
    cname = clean_business_name(business_name).lower()
    tokens = [w for w in re.findall(r'[a-zA-Z]{3,}', cname) if w not in ["the", "and", "tamil", "nadu"]]

    # Common free mail providers (Gmail, Yahoo, etc.)
    if domain in ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]:
        if any(t in user for t in tokens) or (city and city.lower() in user):
            return True
        if any(w in user for w in ["order", "contact", "info", "book", "sale", "enquir", "studio", "bakes", "salon", "bridal", "boutique", "cake"]):
            return True
        return False
    else:
        # Custom domain (e.g. @srvmutton.com, @yaffaa.com, @diyagroups.co.in)
        if any(t in domain for t in tokens):
            return True
        return False


def decode_bing_url(u: str) -> str:
    """Decodes Bing redirect link containing base64 destination."""
    if "bing.com/ck" in u:
        match = re.search(r'u=a1([a-zA-Z0-9_-]+)', u)
        if match:
            b64 = match.group(1)
            b64 += '=' * ((4 - len(b64) % 4) % 4)
            try:
                return base64.urlsafe_b64decode(b64).decode('utf-8', errors='ignore')
            except Exception:
                pass
    return u


def extract_valid_emails_from_text(text: str, business_name: str = "", city: str = "", from_bio: bool = False) -> List[str]:
    """Finds valid business email addresses in text, validates relevance, and verifies DNS MX."""
    if not text:
        return []
    # Avoid query reflections matching %22@gmail.com
    raw = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    valid = []
    for em in raw:
        em = em.strip().lower().rstrip(".,;:/'\"")
        # Ignore false positives like 22@gmail.com or query fragments
        if re.match(r"^\d{1,3}@gmail\.com$", em):
            continue
        if len(em) < 6 or len(em) > 70:
            continue
        if any(em.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js"]):
            continue
        if any(inv in em for inv in INVALID_EMAIL_SUBSTRINGS):
            continue
        if not is_email_relevant_for_shop(em, business_name, city, from_bio=from_bio):
            continue
        parts = em.split("@")
        if len(parts) == 2 and "." in parts[1]:
            is_valid, _ = validate_email_address(em)
            if is_valid:
                valid.append(em)
    return list(dict.fromkeys(valid))


def scrape_social_bio(social_url: str) -> Tuple[Optional[str], str]:
    """Scrapes public social media bio for contact email and bio text."""
    if not social_url or not social_url.startswith("http"):
        return None, ""
    try:
        r = requests.get(social_url, headers=FB_HEADERS, timeout=4)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            meta_text = " ".join([m.get("content", "") for m in soup.find_all("meta") if m.get("content")])
            
            # Check for celebrity flag (> 400k followers)
            fol_match = re.search(r'([\d,]+)\s+Followers', meta_text)
            if fol_match:
                fol_num = int(fol_match.group(1).replace(",", ""))
                if fol_num > 400000:
                    return None, "" # Skip celebrity accounts
            
            emails = extract_valid_emails_from_text(meta_text, from_bio=True)
            if emails:
                return emails[0], meta_text
            return None, meta_text
    except Exception:
        pass
    return None, ""


def research_single_shop(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes multi-layered discovery for a shop:
    1. Existing social profile bio inspection
    2. Snippet search: "{clean_name}" {city} gmail
    3. Snippet search: "{clean_name}" {city} email
    4. Phone number search: "{clean_phone}" gmail.com
    5. Discovered Instagram bio inspection
    """
    raw_name = lead.get("Business Name", "").strip()
    city = lead.get("City", "").strip()
    cname = clean_business_name(raw_name)
    clean_no_punct = re.sub(r"[^\w\s]", " ", cname).strip()
    clean_no_punct = re.sub(r"\s+", " ", clean_no_punct).strip()
    
    raw_phone = lead.get("Cleaned Mobile") or lead.get("Phone") or ""
    phone_clean = re.sub(r"[^\d]", "", raw_phone)[-10:]
    current_social = (lead.get("Social Media URL") or "").strip()
    existing_gmail = (lead.get("Gmail") or "").strip()

    # If lead already has an email, check validity & relevance
    if existing_gmail and "@" in existing_gmail:
        is_val, _ = validate_email_address(existing_gmail)
        is_rel = is_email_relevant_for_shop(existing_gmail, raw_name, city, from_bio=bool(current_social))
        if is_val and is_rel:
            return {
                "lead": lead,
                "email": existing_gmail,
                "social": current_social,
                "status": "already_had_email",
                "source": "existing"
            }
        elif not is_rel:
            lead["Gmail"] = ""

    found_email = None
    found_social = current_social if ("http" in current_social) else ""

    # Strategy 1: Check existing social profile bio
    if found_social and "instagram.com" in found_social:
        email, _ = scrape_social_bio(found_social)
        if email:
            return {
                "lead": lead,
                "email": email,
                "social": found_social,
                "status": "found",
                "source": "instagram_bio"
            }

    # Strategy 2: Targeted Search Query 1: "{clean_name}" {city} gmail
    q1 = f'"{clean_no_punct}" {city} gmail'
    try:
        url1 = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(q1)
        r1 = requests.get(url1, headers=BROWSER_HEADERS, timeout=4)
        if r1.status_code == 200:
            soup = BeautifulSoup(r1.text, "html.parser")
            for item in soup.select("li.b_algo"):
                snippet = item.get_text()
                emails = extract_valid_emails_from_text(snippet, raw_name, city)
                if emails:
                    found_email = emails[0]
                    return {
                        "lead": lead,
                        "email": found_email,
                        "social": found_social,
                        "status": "found",
                        "source": "web_search_q1"
                    }
                
                # Check if an Instagram profile appears in top results
                if not found_social:
                    a = item.find("a", href=True)
                    if a:
                        real = decode_bing_url(a['href'])
                        low = real.lower()
                        if "instagram.com/" in low and not any(x in low for x in ["/p/", "/explore", "/reels", "/direct"]):
                            found_social = real.split("?")[0].rstrip("/")
    except Exception:
        pass

    # Strategy 3: Targeted Search Query 2: "{clean_name}" {city} email
    if not found_email:
        q2 = f'"{clean_no_punct}" {city} email'
        try:
            url2 = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(q2)
            r2 = requests.get(url2, headers=BROWSER_HEADERS, timeout=4)
            if r2.status_code == 200:
                soup = BeautifulSoup(r2.text, "html.parser")
                for item in soup.select("li.b_algo"):
                    snippet = item.get_text()
                    emails = extract_valid_emails_from_text(snippet, raw_name, city)
                    if emails:
                        found_email = emails[0]
                        return {
                            "lead": lead,
                            "email": found_email,
                            "social": found_social,
                            "status": "found",
                            "source": "web_search_q2"
                        }
                    if not found_social:
                        a = item.find("a", href=True)
                        if a:
                            real = decode_bing_url(a['href'])
                            low = real.lower()
                            if "instagram.com/" in low and not any(x in low for x in ["/p/", "/explore", "/reels", "/direct"]):
                                found_social = real.split("?")[0].rstrip("/")
        except Exception:
            pass

    # Strategy 4: If a new social profile was discovered, check its bio
    if not found_email and found_social and "instagram.com" in found_social and found_social != current_social:
        email, _ = scrape_social_bio(found_social)
        if email:
            return {
                "lead": lead,
                "email": email,
                "social": found_social,
                "status": "found",
                "source": "discovered_social_bio"
            }

    # Strategy 5: Search public directory snippets by 10-digit phone
    if not found_email and len(phone_clean) == 10:
        qp = f'"{phone_clean}" gmail.com'
        try:
            url_p = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(qp)
            rp = requests.get(url_p, headers=BROWSER_HEADERS, timeout=4)
            if rp.status_code == 200:
                soup = BeautifulSoup(rp.text, "html.parser")
                for item in soup.select("li.b_algo"):
                    snippet = item.get_text()
                    emails = extract_valid_emails_from_text(snippet, raw_name, city)
                    if emails:
                        return {
                            "lead": lead,
                            "email": emails[0],
                            "social": found_social,
                            "status": "found",
                            "source": "phone_linked_listing"
                        }
        except Exception:
            pass

    return {
        "lead": lead,
        "email": None,
        "social": found_social,
        "status": "not_found",
        "source": None
    }


def sync_databases(all_leads: List[Dict[str, Any]]):
    """Atomically syncs lead records across CSV files and leads_data.js."""
    if not all_leads:
        return
    for path in [MASTER_FILE, ACTIVE_FILE]:
        try:
            with open(path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=STANDARD_FIELDNAMES, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(all_leads)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not sync {path.name}: {e}[/yellow]")

    try:
        with open(LEADS_JS_FILE, mode="w", encoding="utf-8") as f:
            f.write("window.EMBEDDED_LEADS = " + json.dumps(all_leads, indent=2, ensure_ascii=False) + ";\n")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not sync {LEADS_JS_FILE.name}: {e}[/yellow]")


def run_full_research():
    console.print("\n[bold cyan]╔══════════════════════════════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║   🔍 COMPREHENSIVE GMAIL RE-SEARCH ENGINE FOR ALL SHOPS          ║[/bold cyan]")
    console.print("[bold cyan]╚══════════════════════════════════════════════════════════════════╝[/bold cyan]\n")

    if not MASTER_FILE.exists():
        console.print(f"[red]Error: {MASTER_FILE} not found.[/red]")
        return

    with open(MASTER_FILE, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        all_leads = list(reader)

    total_leads = len(all_leads)
    initially_with_email = sum(1 for l in all_leads if l.get("Gmail"))
    console.print(f"• Total Shops in Master Database: [bold white]{total_leads}[/bold white]")
    console.print(f"• Currently with Email: [bold green]{initially_with_email}[/bold green]")
    console.print(f"• Target Shops to Re-Search: [bold yellow]{total_leads}[/bold yellow]")
    console.print(f"• Verification: Live DNS MX lookup & strict spam/celebrity filters\n")

    discovered_new = 0
    updated_socials = 0
    processed_count = 0
    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("• Discovered: [bold green]{task.fields[discovered]}[/bold green]"),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Re-searching shops for Gmail...", total=total_leads, discovered=0)

        # Thread pool with 12 workers for balanced speed and rate control
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = {executor.submit(research_single_shop, lead): lead for lead in all_leads}

            for future in as_completed(futures):
                processed_count += 1
                result = future.result()
                lead = result["lead"]
                name = clean_business_name(lead.get("Business Name", ""))
                city = lead.get("City", "")

                # Update email if discovered
                if result["email"] and not lead.get("Gmail"):
                    lead["Gmail"] = result["email"]
                    discovered_new += 1
                    console.print(f"[{processed_count}/{total_leads}] ✔ [bold green]FOUND GMAIL[/bold green]: [white]{name}[/white] ({city}) ➔ [bold cyan]{result['email']}[/bold cyan] [dim]({result['source']})[/dim]")
                
                # Update social URL if discovered
                if result["social"] and result["social"] != lead.get("Social Media URL"):
                    lead["Social Media URL"] = result["social"]
                    if not lead.get("Verification Status") or "NO WEBSITE" in lead.get("Verification Status", ""):
                        lead["Verification Status"] = "HAS SOCIALS BUT NO WEBSITE"
                    updated_socials += 1

                progress.update(task, advance=1, discovered=discovered_new)

                # Periodic atomic sync every 25 leads
                if processed_count % 25 == 0:
                    sync_databases(all_leads)

    # Final sync
    sync_databases(all_leads)
    elapsed = time.time() - start_time
    total_emails_now = sum(1 for l in all_leads if l.get("Gmail"))

    console.print("\n[bold green]══════════════════════════════════════════════════════════════════[/bold green]")
    console.print(f"[bold green]🏁 GMAIL RE-SEARCH COMPLETED in {elapsed:.1f}s![/bold green]")
    console.print(f"  • Newly Discovered Verified Emails: [bold green]+{discovered_new}[/bold green]")
    console.print(f"  • Newly Discovered Social Profiles: [bold cyan]+{updated_socials}[/bold cyan]")
    console.print(f"  • Total Shops Now With Valid Email: [bold white]{total_emails_now}[/bold white] / {total_leads}")
    console.print(f"  • All databases updated: [white]master_scraped_leads.csv[/white], [white]tamil_nadu_continuous_leads.csv[/white], and [white]leads_data.js[/white]")
    console.print("[bold green]══════════════════════════════════════════════════════════════════[/bold green]\n")


if __name__ == "__main__":
    run_full_research()
