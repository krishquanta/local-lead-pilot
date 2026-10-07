"""
Automated WhatsApp Outreach Bot for Verified Google Places Leads.
Features:
- Persistent WhatsApp Web session profile (scan QR code once, session is saved)
- Strict Anti-Ban safeguards (randomized 25-45s delays, daily message batch limits)
- Dynamic message spinning (rotates greetings, hooks, and compliments to prevent identical text flags)
- Smart Indian mobile number normalization (filters out landlines)
- Automatic CSV lead status tracking ('OUTREACH_SENT', timestamp)
- Dry-run mode for testing and message inspection
- Human fingerprint simulation: letter-by-letter typing, randomized keystroke pacing,
  micro-pauses after punctuation/spaces, occasional typo+backspace corrections,
  idle mouse jitter before and during typing — avoids WhatsApp bot detection.
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
import time
import random
import argparse
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import OUTPUT_DIR
from outreach_generator import clean_business_name
from rate_limiter import can_send, check_and_increment, reset_if_new_day, get_status_summary
from reply_tracker import scan_for_replies
from follow_up_scheduler import get_followup_candidates, generate_followup_message, mark_followup_sent

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(force_terminal=True, legacy_windows=False)

BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
WHATSAPP_PROFILE_DIR = BASE_DIR / "whatsapp_profile"
WHATSAPP_PROFILE_DIR.mkdir(exist_ok=True)


def normalize_indian_phone(raw_phone: str) -> Tuple[Optional[str], str]:
    """
    Normalizes Indian contact numbers for WhatsApp Web URL (wa.me/91...).
    Returns (cleaned_phone, reason_or_type).
    """
    if not raw_phone:
        return None, "Missing phone number"

    digits = re.sub(r"[^\d]", "", raw_phone)

    # Landline pattern check: (e.g. 0422... Coimbatore landline)
    # Indian mobile numbers start with 6, 7, 8, 9
    if digits.startswith("0") and len(digits) == 11:
        core = digits[1:]
        if core[0] in "6789":
            return f"91{core}", "Mobile"
        else:
            return None, f"Landline detected (STD: 0{digits[1:4]}), cannot receive WhatsApp"

    # Already has 91 country code (12 digits total)
    if digits.startswith("91") and len(digits) == 12:
        if digits[2] in "6789":
            return digits, "Mobile"
        else:
            return None, "Landline with 91 prefix"

    # 10 digits standard mobile
    if len(digits) == 10:
        if digits[0] in "6789":
            return f"91{digits}", "Mobile"
        else:
            return None, "Likely landline (does not start with 6-9)"

    return None, f"Invalid phone length ({len(digits)} digits)"


MASTER_TRACKER_FILE = OUTPUT_DIR / "master_outreach_tracker.csv"


def load_all_contacted_leads() -> Tuple[Set[str], Set[str]]:
    """
    Scans master_outreach_tracker.csv AND all CSVs in leads_output to build
    a comprehensive set of previously contacted phones and business names.
    This guarantees 0 duplicate messages ever get sent.
    """
    contacted_phones: Set[str] = set()
    contacted_names: Set[str] = set()

    # 1. Check dedicated master tracker if present
    if MASTER_TRACKER_FILE.exists():
        try:
            with open(MASTER_TRACKER_FILE, mode="r", encoding="utf-8-sig", errors="ignore") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    ph = (r.get("Cleaned Phone") or r.get("Phone") or "").strip()
                    nm = (r.get("Business Name") or "").strip().lower()
                    st = (r.get("WhatsApp Status") or "").strip().upper()
                    if st in ("SENT", "DELIVERED", "REPLIED", "FOLLOW_UP_SENT") or r.get("WhatsApp Timestamp"):
                        if ph:
                            contacted_phones.add(ph)
                        if nm:
                            contacted_names.add(nm)
        except Exception:
            pass

    # 2. Check all lead CSVs in leads_output
    if OUTPUT_DIR.exists():
        for csv_path in OUTPUT_DIR.glob("*.csv"):
            try:
                with open(csv_path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        st = (r.get("WhatsApp Status") or "").strip().upper()
                        ts = r.get("WhatsApp Timestamp") or ""
                        if st in ("SENT", "DELIVERED", "REPLIED", "FOLLOW_UP_SENT") or ts:
                            raw_p = (r.get("Cleaned Mobile") or r.get("Cleaned Phone") or r.get("Phone") or "").strip()
                            norm_p, _ = normalize_indian_phone(raw_p)
                            if norm_p:
                                contacted_phones.add(norm_p)
                            elif raw_p:
                                digits_only = re.sub(r"[^\d]", "", raw_p)
                                if len(digits_only) >= 10:
                                    contacted_phones.add(digits_only[-10:])
                            nm = (r.get("Business Name") or "").strip().lower()
                            if nm:
                                contacted_names.add(nm)
            except Exception:
                pass

    return contacted_phones, contacted_names


def record_outreach_to_master(row: Dict[str, Any], phone: str, variant_id: str, is_followup: bool = False):
    """Appends successful send directly to master_outreach_tracker.csv."""
    fieldnames = [
        "Business Name", "Category", "City", "Rating", "Review Count",
        "Phone", "Cleaned Phone", "Website", "WhatsApp Status",
        "WhatsApp Timestamp", "Message Variant", "Conversion Stage"
    ]
    file_exists = MASTER_TRACKER_FILE.exists()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = {
        "Business Name": row.get("Business Name", ""),
        "Category": row.get("Category", ""),
        "City": row.get("City", ""),
        "Rating": row.get("Rating", ""),
        "Review Count": row.get("Review Count", ""),
        "Phone": row.get("Phone", ""),
        "Cleaned Phone": phone,
        "Website": row.get("Website", ""),
        "WhatsApp Status": "FOLLOW_UP_SENT" if is_followup else "SENT",
        "WhatsApp Timestamp": now_str,
        "Message Variant": variant_id,
        "Conversion Stage": "FOLLOW_UP_SENT" if is_followup else "SENT"
    }

    try:
        with open(MASTER_TRACKER_FILE, mode="a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerow(entry)
    except Exception:
        pass


def generate_varied_pitch(lead: Dict[str, Any], sender_name: str = "", return_variant: bool = False) -> Any:
    """
    Generates a short, natural, human WhatsApp message (3-4 lines).
    Avoids robotic templates and excessive sales hype.
    Optionally returns (message, variant_id) for A/B testing.
    """
    raw_name = (lead.get("Business Name") or lead.get("name") or "there").strip()
    name = clean_business_name(raw_name)
    city = (lead.get("City") or lead.get("city") or "Tamil Nadu").strip()
    reviews = lead.get("Review Count") or lead.get("review_count") or 50
    category = (lead.get("Category") or lead.get("category") or "").lower()

    # Clean review count
    try:
        rev_int = int(re.sub(r"[^\d]", "", str(reviews)))
        rev_str = f"{rev_int:,}"
    except Exception:
        rev_str = str(reviews)

    # 1. Restaurant / Food pitch (focus on direct menu orders & WhatsApp)
    if any(k in category for k in ["restaurant", "food", "cafe", "mess", "hotel", "biryani", "bites"]):
        cat_tag = "WA_Food"
        openers = [
            f"Hi, is this the owner or manager at {name}?",
            f"Hello, reaching out to {name} in {city}."
        ]
        questions = [
            f"I saw your place on Google Maps with great reviews ({rev_str}+). Noticed you don't have a direct website for customers to view your menu and order on WhatsApp.",
            f"Came across {name} on Maps while looking at popular food spots in {city}. Noticed your profile doesn't have an official menu website linked."
        ]
        ctas = [
            f"I'm a freelance web designer and recorded a quick 15-second video preview of a mobile template from one of my previous client projects with 1-click WhatsApp ordering. Can I share the short video here to take a look?",
            f"I have a short video preview showing a clean mobile template from a recent local project. Ok if I send the quick recording here?"
        ]

    # 2. Meat / Fish / Poultry shop pitch (focus on daily home delivery & WhatsApp orders)
    elif any(k in category for k in ["meat", "chicken", "mutton", "fish", "butcher", "poultry"]):
        cat_tag = "WA_Meat"
        openers = [
            f"Hi, is this the owner at {name}?",
            f"Hello team {name},"
        ]
        questions = [
            f"Found your shop on Google Maps in {city} with strong customer reviews ({rev_str}+). Noticed you don't have a website for daily fresh cuts and WhatsApp delivery orders.",
            f"Saw {name} on Google Maps while looking for fresh meat in {city}. Noticed you don't have an online catalogue linked."
        ]
        ctas = [
            f"I recorded a quick 15-second video preview of a mobile template from one of my recent client projects with WhatsApp ordering. Can I share the short video here?",
            f"I have a quick video recording of a mobile template from a previous project. Ok if I send the preview video here?"
        ]

    # 3. Bakery / Cake / Sweets pitch (focus on custom cake orders & festival bookings)
    elif any(k in category for k in ["bakery", "cake", "sweet", "bakes", "pastry"]):
        cat_tag = "WA_Bakes"
        openers = [
            f"Hi, is this the owner or manager at {name}?",
            f"Hello team {name},"
        ]
        questions = [
            f"Saw {name} on Google Maps in {city} with impressive reviews ({rev_str}+). Noticed there's no website linked for customers to browse your cake/sweet designs and order directly.",
            f"Found your shop on Google Maps in {city}. Noticed your profile doesn't have an official website for online orders or party bookings."
        ]
        ctas = [
            f"I recorded a quick 15-second video preview of a mobile catalogue template from one of my previous projects. Would it be ok if I send the short video here?",
            f"I have a short video recording of a clean mobile template from a recent local shop project. Can I share the preview video so you can take a look?"
        ]

    # 4. General retail shop / Service business
    else:
        cat_tag = "WA_Retail"
        openers = [
            f"Hi, is this the owner or manager at {name}?",
            f"Hello, reaching out to {name} in {city}."
        ]
        questions = [
            f"Found your shop on Google Maps in {city} with great customer reviews ({rev_str}+). Noticed you don't have an official website listed for people searching on Google.",
            f"Saw your business profile on Google Maps in {city}. Noticed there's no website linked for customers to check your services or pricing."
        ]
        ctas = [
            f"I'm a freelance web designer and recorded a quick 15-second video preview of a mobile template from one of my previous client projects. Can I send the short recording here to see what you think?",
            f"I have a short video preview of a clean mobile template from a recent project with a direct WhatsApp contact button. Ok if I share the quick recording?"
        ]

    line1 = random.choice(openers)
    line2 = random.choice(questions)
    line3 = random.choice(ctas)

    o_idx = openers.index(line1) + 1
    q_idx = questions.index(line2) + 1
    c_idx = ctas.index(line3) + 1
    variant_id = f"{cat_tag}_O{o_idx}_Q{q_idx}_C{c_idx}"

    message = f"{line1}\n\n{line2}\n\n{line3}"

    if sender_name and sender_name.strip():
        message += f"\n\n- {sender_name.strip()}"

    if return_variant:
        return message, variant_id
    return message


def find_latest_csv() -> Optional[Path]:
    master_file = OUTPUT_DIR / "master_scraped_leads.csv"
    if master_file.exists() and master_file.stat().st_size > 0:
        return master_file
    csv_files = sorted(OUTPUT_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return csv_files[0] if csv_files else None


# ---------------------------------------------------------------------------
# Human fingerprint helpers
# ---------------------------------------------------------------------------

# Characters that are commonly fat-fingered (adjacent keys on QWERTY)
_ADJACENT_KEYS: Dict[str, List[str]] = {
    "a": ["s", "q", "z"], "b": ["v", "n", "g"], "c": ["x", "v", "d"],
    "d": ["s", "f", "e", "c"], "e": ["w", "r", "d"], "f": ["d", "g", "r"],
    "g": ["f", "h", "t", "b"], "h": ["g", "j", "y", "n"], "i": ["u", "o", "k"],
    "j": ["h", "k", "u", "m"], "k": ["j", "l", "i"], "l": ["k", "o", "p"],
    "m": ["n", "j", "k"], "n": ["b", "m", "h"], "o": ["i", "p", "l"],
    "p": ["o", "l"], "q": ["w", "a"], "r": ["e", "t", "f"],
    "s": ["a", "d", "w", "x"], "t": ["r", "y", "g"], "u": ["y", "i", "j"],
    "v": ["c", "b", "f"], "w": ["q", "e", "s"], "x": ["z", "c", "s"],
    "y": ["t", "u", "h"], "z": ["a", "x", "s"],
}


def _jitter_mouse(page, viewport_width: int = 1280, viewport_height: int = 800) -> None:
    """
    Move mouse to a random screen position and back, simulating idle hand movement.
    Does 2–4 small random moves in quick succession.
    """
    moves = random.randint(2, 4)
    for _ in range(moves):
        x = random.randint(100, viewport_width - 100)
        y = random.randint(100, viewport_height - 100)
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.05, 0.18))


def _human_type(page, text: str, input_box) -> None:
    """
    Types `text` into `input_box` one character at a time, mimicking a human:
    - Randomised base typing speed (~160–280ms per key)
    - Faster bursts mid-word, slower start-of-sentence
    - Extra pause after sentence punctuation (. ! ?), commas, and newlines
    - Small pause after every space (inter-word gap)
    - ~6% chance of a fat-finger typo followed by Backspace correction
    - Random mouse micro-jitter every 15–25 characters
    """
    jitter_countdown = random.randint(15, 25)
    char_index = 0

    # Decide a random "burst speed" for the current word (reset per space)
    burst_delay = random.uniform(0.08, 0.18)  # fast burst base delay (seconds)

    for char in text:
        # --- Typo simulation ---
        lower_char = char.lower()
        if (
            char.isalpha()
            and lower_char in _ADJACENT_KEYS
            and random.random() < 0.06   # ~6% typo rate
        ):
            typo = random.choice(_ADJACENT_KEYS[lower_char])
            input_box.type(typo, delay=0)          # type wrong key
            time.sleep(random.uniform(0.08, 0.20)) # brief pause before realising
            page.keyboard.press("Backspace")        # correct it
            time.sleep(random.uniform(0.05, 0.14)) # micro-pause after delete

        # --- Type the correct character ---
        input_box.type(char, delay=0)

        # --- Compute natural delay after this character ---
        if char in ".!?":
            # End of sentence – longer thinking pause
            delay = random.uniform(0.35, 0.75)
        elif char == ",":
            delay = random.uniform(0.20, 0.45)
        elif char == "\n":
            # After pressing Enter (newline in multi-line box) – big pause
            delay = random.uniform(0.40, 0.90)
        elif char == " ":
            # Inter-word gap – reset burst speed
            burst_delay = random.uniform(0.06, 0.20)
            delay = random.uniform(0.10, 0.28)
        else:
            # Normal character within a word – use current burst speed with noise
            delay = burst_delay + random.gauss(0, 0.03)
            delay = max(0.04, delay)  # floor at 40ms

        time.sleep(delay)

        # --- Mouse jitter every N characters ---
        jitter_countdown -= 1
        if jitter_countdown <= 0:
            _jitter_mouse(page)
            jitter_countdown = random.randint(15, 25)

        char_index += 1

    # Final "I just finished typing" pause before we hit send
    time.sleep(random.uniform(0.5, 1.4))


# ---------------------------------------------------------------------------
# Main bot
# ---------------------------------------------------------------------------

def run_whatsapp_bot(
    csv_file: Path,
    sender_name: str = "",
    limit: int = 10,
    min_delay: int = 25,
    max_delay: int = 45,
    dry_run: bool = False,
    is_followup: bool = False,
    filter_city: str = "",
    filter_category: str = ""
):
    """
    Main WhatsApp Web automation loop using Playwright.
    Uses human-like typing (letter-by-letter) and mouse jitter to avoid bot flags.
    Integrates daily rate-limiting, inbound reply detection, and 48h follow-up nudges.
    """
    if not csv_file.exists():
        console.print(f"[red]Error: CSV file not found at {csv_file}[/red]")
        return

    # Check daily rate limit
    reset_if_new_day()
    allowed_to_send, sent_today, max_daily = can_send("whatsapp")
    remaining_today = max(0, max_daily - sent_today)

    if not allowed_to_send and not dry_run:
        console.print(Panel(
            f"[bold red]⛔ Daily WhatsApp outreach limit reached ({sent_today}/{max_daily})[/bold red]\n"
            f"Halting execution to protect your WhatsApp account from spam filters.\n"
            f"Limit will reset automatically tomorrow, or adjust `DAILY_WA_LIMIT` in `.env`.",
            border_style="red"
        ))
        return

    with open(csv_file, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # Ensure tracking columns exist
    for col in ["WhatsApp Status", "WhatsApp Timestamp", "Follow Up Timestamp", "WhatsApp Reply", "WhatsApp Reply At", "Conversion Stage", "Message Variant"]:
        if col not in fieldnames:
            fieldnames.append(col)

    # Load master contacted database across all CSVs to prevent any duplicates
    contacted_phones, contacted_names = load_all_contacted_leads()

    # Filter candidate leads:
    candidates = []

    if is_followup:
        # Retrieve leads due for 48h gentle nudge
        followup_tuples = get_followup_candidates(hours_threshold=48, target_csv=csv_file)
        for _, idx, row in followup_tuples:
            raw_phone = row.get("Cleaned Mobile") or row.get("Phone") or ""
            phone, _ = normalize_indian_phone(raw_phone)
            if phone:
                candidates.append((idx, row, phone))
        queue_label = "Eligible 48h Follow-up Leads"
    else:
        for idx, row in enumerate(rows):
            status = (row.get("WhatsApp Status") or "").strip()
            if status in ("SENT", "DELIVERED", "REPLIED", "FOLLOW_UP_SENT"):
                continue  # Already reached out

            # Cross-CSV Deduplication: Check if phone or business name was already messaged
            raw_phone = row.get("Cleaned Mobile") or row.get("Phone", "")
            phone, phone_type = normalize_indian_phone(raw_phone)
            b_name = (row.get("Business Name") or "").strip().lower()

            if phone and (phone in contacted_phones or phone[-10:] in [p[-10:] for p in contacted_phones]):
                row["WhatsApp Status"] = "SKIPPED (ALREADY CONTACTED)"
                continue

            if b_name and b_name in contacted_names:
                row["WhatsApp Status"] = "SKIPPED (ALREADY CONTACTED)"
                continue

            # Strictly skip businesses that already have an official website
            website = (row.get("Website") or "").strip().lower()
            ver_status = (row.get("Verification Status") or "").strip().upper()
            has_real_website = website.startswith("http") and "instagram.com" not in website and "facebook.com" not in website
            if has_real_website or "WEBSITE FOUND" in ver_status:
                row["WhatsApp Status"] = "SKIPPED (HAS WEBSITE)"
                continue

            # Optional city and category filters
            if filter_city:
                row_city = (row.get("City") or "").strip().lower()
                if filter_city.lower() not in row_city:
                    continue

            if filter_category:
                row_cat = (row.get("Category") or "").strip().lower()
                row_name = (row.get("Business Name") or "").strip().lower()
                target_cat = filter_category.lower()
                if target_cat not in row_cat and target_cat not in row_name:
                    continue

            raw_phone = row.get("Cleaned Mobile") or row.get("Phone", "")
            phone, phone_type = normalize_indian_phone(raw_phone)
            if not phone:
                row["WhatsApp Status"] = f"SKIPPED ({phone_type})"
                continue

            candidates.append((idx, row, phone))
        queue_label = "Qualified Prospects (No Website, Mobile Verified)"

    if not candidates:
        if is_followup:
            console.print("[yellow]No leads currently qualify for a 48h follow-up nudge.[/yellow]")
        else:
            console.print("[yellow]No pending leads with valid mobile numbers to send to.[/yellow]")
        return

    # Cap by limit and remaining daily quota
    effective_limit = min(limit, remaining_today) if not dry_run else limit
    leads_to_process = candidates[:effective_limit]

    mode_title = "FOLLOW-UP NUDGE" if is_followup else "INITIAL OUTREACH"
    console.print(Panel(
        f"[bold green]WhatsApp Outreach Bot Initialized ({mode_title})[/bold green]\n"
        f"File: [cyan]{csv_file.name}[/cyan]\n"
        f"{queue_label} in queue: [bold yellow]{len(candidates)}[/bold yellow]\n"
        f"Batch send limit: [bold green]{len(leads_to_process)}[/bold green] (Daily remaining: [yellow]{remaining_today}[/yellow])\n"
        f"Anti-Ban safety delay between messages: [bold]{min_delay} - {max_delay} seconds[/bold]\n"
        f"Mode: [bold magenta]{'DRY RUN (Preview Only)' if dry_run else 'LIVE AUTOMATION'}[/bold magenta]",
        border_style="green"
    ))

    # Show preview table
    table = Table(title=f"Leads Scheduled for WhatsApp {mode_title}", show_lines=True)
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("Business Name", style="bold white", width=28)
    table.add_column("City", style="cyan", width=12)
    table.add_column("Mobile Number", style="green", width=16)
    table.add_column("Reviews", justify="right", style="yellow", width=10)

    for i, (_, lead, phone) in enumerate(leads_to_process, start=1):
        table.add_row(
            str(i),
            lead.get("Business Name", "")[:26],
            lead.get("City", ""),
            f"+{phone}",
            str(lead.get("Review Count", 0))
        )
    console.print(table)

    if dry_run:
        console.print("\n[bold cyan]-- Dry Run Message Sample Preview --[/bold cyan]")
        sample_lead = leads_to_process[0][1]
        if is_followup:
            sample_pitch = generate_followup_message(sample_lead, sender_name)
            v_id = "WA_FollowUp_48h"
        else:
            sample_pitch, v_id = generate_varied_pitch(sample_lead, sender_name, return_variant=True)
        console.print(Panel(sample_pitch, title=f"Preview Message ({v_id})", border_style="cyan"))
        console.print("[dim]Dry run complete. No messages were sent. Run without `--dry-run` to send live.[/dim]")
        return

    # Check for playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        console.print("[red]Error: Playwright is not installed yet. Run: `pip install playwright && playwright install chromium`[/red]")
        return

    console.print("\n[bold]Launching browser session with persistent WhatsApp profile...[/bold]")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(WHATSAPP_PROFILE_DIR),
            channel="msedge",
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--start-maximized"
            ]
        )

        page = browser.pages[0] if browser.pages else browser.new_page()
        try:
            page.bring_to_front()
        except Exception:
            pass

        console.print("[cyan]Navigating to WhatsApp Web...[/cyan]")
        page.goto("https://web.whatsapp.com", timeout=60000)

        # Check if already logged in or needs QR scan
        console.print("[yellow]Checking WhatsApp login status...[/yellow]")
        console.print("[dim]If this is your first time, please scan the QR code on the browser window now (waiting up to 120s)...[/dim]")

        try:
            page.wait_for_selector('div[contenteditable="true"], div[data-tab="3"], [aria-label="Chat list"]', timeout=120000)
            console.print("[bold green]✔ WhatsApp Web authenticated successfully![/bold green]\n")
        except Exception:
            console.print("[red]Timeout waiting for WhatsApp Web login. Please run again and scan the QR code.[/red]")
            browser.close()
            return

        # Scan for replies from previously contacted businesses
        try:
            scan_for_replies(page, target_csv=csv_file)
        except Exception as e:
            console.print(f"   [dim]Notice during reply check: {e}[/dim]")

        sent_count = 0

        for seq, (row_idx, lead, phone) in enumerate(leads_to_process, start=1):
            # Check rate limiter before each message
            can_proceed, curr_c, max_l = can_send("whatsapp")
            if not can_proceed:
                console.print(f"\n[bold red]⛔ Daily WhatsApp limit ({curr_c}/{max_l}) reached. Halting batch.[/bold red]")
                break

            name = lead.get("Business Name", "Business")
            console.print(f"\n[bold cyan]Processing [{seq}/{len(leads_to_process)}]:[/bold cyan] [bold white]{name}[/bold white] (+{phone})")

            # Generate pitch
            if is_followup:
                pitch_text = generate_followup_message(lead, sender_name)
                variant_id = "WA_FollowUp_48h"
            else:
                pitch_text, variant_id = generate_varied_pitch(lead, sender_name, return_variant=True)

            try:
                wa_url = f"https://web.whatsapp.com/send?phone={phone}"
                page.goto(wa_url, timeout=45000)

                send_button_selector = 'span[data-icon="send"], button[aria-label="Send"], span[data-icon="send-light"]'
                input_box_selector = 'div[contenteditable="true"][data-tab="10"], div[contenteditable="true"][aria-label], footer div[contenteditable="true"]'

                console.print("   Waiting for chat to load...")

                chat_loaded = False
                for _ in range(30):
                    time.sleep(1)
                    if (
                        page.locator('text="Phone number shared via url is invalid."').count() > 0
                        or page.locator('text="Phone number is not on WhatsApp"').count() > 0
                    ):
                        console.print("   [yellow]⚠ Phone number not registered on WhatsApp. Skipping.[/yellow]")
                        rows[row_idx]["WhatsApp Status"] = "NOT_ON_WHATSAPP"
                        rows[row_idx]["WhatsApp Timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        break

                    if page.locator(input_box_selector).count() > 0:
                        chat_loaded = True
                        break

                if chat_loaded:
                    input_box = page.locator(input_box_selector).first

                    # Human pre-typing ritual
                    _jitter_mouse(page)
                    time.sleep(random.uniform(0.6, 1.5))

                    input_box.click()
                    time.sleep(random.uniform(0.3, 0.8))

                    # Clear input box
                    page.keyboard.press("Control+a")
                    time.sleep(random.uniform(0.1, 0.25))
                    page.keyboard.press("Delete")
                    time.sleep(random.uniform(0.2, 0.5))

                    console.print(f"   [dim]Composing message ({variant_id}) letter-by-letter...[/dim]")
                    time.sleep(random.uniform(1.0, 2.5))

                    # Type message with human fingerprint pacing
                    _human_type(page, pitch_text.replace("\n", "\n"), input_box)

                    time.sleep(random.uniform(0.8, 2.0))
                    _jitter_mouse(page)
                    time.sleep(random.uniform(0.3, 0.7))

                    send_btn = page.locator(send_button_selector).first
                    send_btn.click()
                    time.sleep(random.uniform(2.0, 3.5))

                    console.print(f"   [bold green]✔ Message sent to {name}![/bold green]")
                    
                    # Update status and tracking
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    rows[row_idx]["Message Variant"] = variant_id
                    if is_followup:
                        rows[row_idx]["WhatsApp Status"] = "FOLLOW_UP_SENT"
                        rows[row_idx]["Follow Up Timestamp"] = now_str
                        rows[row_idx]["Conversion Stage"] = "FOLLOW_UP_SENT"
                    else:
                        rows[row_idx]["WhatsApp Status"] = "SENT"
                        rows[row_idx]["WhatsApp Timestamp"] = now_str
                        rows[row_idx]["Conversion Stage"] = "SENT"

                    check_and_increment("whatsapp")
                    record_outreach_to_master(rows[row_idx], phone, variant_id, is_followup=is_followup)
                    sent_count += 1
                else:
                    if rows[row_idx].get("WhatsApp Status") != "NOT_ON_WHATSAPP":
                        console.print("   [red]✖ Chat could not load in time. Skipping.[/red]")
                        rows[row_idx]["WhatsApp Status"] = "FAILED_TIMEOUT"

            except Exception as e:
                console.print(f"   [red]✖ Error sending to {name}: {e}[/red]")
                rows[row_idx]["WhatsApp Status"] = f"ERROR: {str(e)[:30]}"

            # Save progress in CSV after every message sent
            with open(csv_file, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

            # Anti-ban sleep delay between messages
            if seq < len(leads_to_process):
                sleep_secs = random.randint(min_delay, max_delay)
                console.print(f"   [dim]⏳ Safety anti-spam pause: waiting {sleep_secs}s before next lead...[/dim]")
                time.sleep(sleep_secs)

        console.print(Panel(
            f"[bold green]WhatsApp Outreach Batch Complete![/bold green]\n"
            f"Successfully Sent: [bold]{sent_count}[/bold] / {len(leads_to_process)}\n"
            f"Updated CSV: [cyan]{csv_file}[/cyan]",
            border_style="green"
        ))

        browser.close()


def main():
    parser = argparse.ArgumentParser(description="Automated WhatsApp Web Outreach Bot for Qualified Leads.")
    parser.add_argument("--file", type=str, help="Path to leads CSV (defaults to latest generated)")
    parser.add_argument("--sender", type=str, default="", help="Optional your name / sign-off (default: None)")
    parser.add_argument("--limit", type=int, default=10, help="Max messages to send in this batch (default: 10)")
    parser.add_argument("--min-delay", type=int, default=25, help="Min delay seconds between sends (default: 25)")
    parser.add_argument("--max-delay", type=int, default=45, help="Max delay seconds between sends (default: 45)")
    parser.add_argument("--follow-up", action="store_true", help="Send 48h follow-up nudge to non-responding leads")
    parser.add_argument("--dry-run", action="store_true", help="Preview messages and targets without opening WhatsApp")
    parser.add_argument("--city", type=str, default="", help="Filter by city (e.g. Chennai)")
    parser.add_argument("--category", type=str, default="", help="Filter by category (e.g. meat)")
    args = parser.parse_args()

    csv_path = Path(args.file) if args.file else find_latest_csv()

    if not csv_path or not csv_path.exists():
        console.print("[red]No lead CSV found! Run `python lead_finder.py` first to generate leads.[/red]")
        sys.exit(1)

    run_whatsapp_bot(
        csv_file=csv_path,
        sender_name=args.sender,
        limit=args.limit,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        dry_run=args.dry_run,
        is_followup=args.follow_up,
        filter_city=args.city,
        filter_category=args.category
    )


if __name__ == "__main__":
    main()

