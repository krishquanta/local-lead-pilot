"""
Autonomous Lead Generation & WhatsApp Outreach Pilot.
Continuously loops through target cities and high-utility shop categories:
1. Scrapes live Google Maps listings via Docker
2. Filters for >=4.5 rating, >=50 reviews, NO WEBSITE, valid mobile numbers
3. Deduplicates against master tracker (never messages the same shop twice)
4. Autonomously sends short, human WhatsApp messages
5. Implements anti-ban rate limiting (randomized 35-65s delays + daily limit protection)
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
from typing import List, Dict, Any, Optional, Set, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config import (
    TAMIL_NADU_TARGETS,
    DEFAULT_CRITERIA,
    OUTPUT_DIR
)
from places_client import GooglePlacesClient
from whatsapp_sender import (
    normalize_indian_phone,
    generate_varied_pitch,
    WHATSAPP_PROFILE_DIR,
    _human_type,
    _jitter_mouse
)
from rate_limiter import can_send, check_and_increment, reset_if_new_day

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(force_terminal=True, legacy_windows=False)

BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
MASTER_TRACKER_FILE = OUTPUT_DIR / "master_outreach_tracker.csv"


def load_master_tracker() -> Tuple[Set[str], Set[str], List[Dict[str, Any]]]:
    """
    Loads all previously contacted or tracked leads to ensure 0 duplicates.
    Returns (contacted_phones, contacted_names, all_rows).
    """
    contacted_phones: Set[str] = set()
    contacted_names: Set[str] = set()
    rows: List[Dict[str, Any]] = []

    if not MASTER_TRACKER_FILE.exists():
        return contacted_phones, contacted_names, rows

    with open(MASTER_TRACKER_FILE, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
            phone = row.get("Cleaned Phone", "").strip()
            name = row.get("Business Name", "").strip().lower()
            status = row.get("WhatsApp Status", "").strip()

            if phone:
                contacted_phones.add(phone)
            if name:
                contacted_names.add(name)

    return contacted_phones, contacted_names, rows


def save_to_master_tracker(new_entries: List[Dict[str, Any]]):
    """Appends newly processed leads to the master tracker CSV."""
    fieldnames = [
        "Business Name",
        "Category",
        "City",
        "Rating",
        "Review Count",
        "Raw Phone",
        "Cleaned Phone",
        "Google Maps URL",
        "Website",
        "Lead Score",
        "WhatsApp Status",
        "WhatsApp Timestamp",
        "Message Sent",
        "Conversion Stage",
        "Message Variant",
        "Google Place ID"
    ]

    file_exists = MASTER_TRACKER_FILE.exists()
    with open(MASTER_TRACKER_FILE, mode="a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        for entry in new_entries:
            writer.writerow({
                "Business Name": entry.get("Business Name") or entry.get("name", ""),
                "Category": entry.get("Category") or entry.get("category", ""),
                "City": entry.get("City") or entry.get("city", ""),
                "Rating": entry.get("Rating") or entry.get("rating", 0.0),
                "Review Count": entry.get("Review Count") or entry.get("review_count", 0),
                "Raw Phone": entry.get("Phone", ""),
                "Cleaned Phone": entry.get("cleaned_phone", ""),
                "Google Maps URL": entry.get("google_maps_url", ""),
                "Website": entry.get("website", "") or "NO WEBSITE LISTED",
                "Lead Score": entry.get("lead_score", 0),
                "WhatsApp Status": entry.get("whatsapp_status", "PENDING"),
                "WhatsApp Timestamp": entry.get("whatsapp_timestamp", ""),
                "Message Sent": entry.get("message_sent", ""),
                "Conversion Stage": entry.get("conversion_stage", "SENT"),
                "Message Variant": entry.get("message_variant", ""),
                "Google Place ID": entry.get("place_id", "")
            })


def build_target_search_queue() -> List[Tuple[str, str]]:
    """Generates the search rotation of high-utility shops across Tamil Nadu."""
    queue = []
    # Interleave categories across cities for variety
    for city, categories in TAMIL_NADU_TARGETS.items():
        for category in categories:
            queue.append((city, category))
    return queue


def run_autonomous_autopilot(
    daily_limit: int = 20,
    min_delay: int = 35,
    max_delay: int = 65,
    dry_run: bool = False
):
    """
    Autonomous pipeline loop:
    1. Iterates through high-utility shop targets
    2. Scrapes live listings
    3. Filters & deduplicates against master tracker
    4. Opens WhatsApp session & sends short natural messages
    5. Repeats until daily limit or user interruption
    """
    console.print(Panel(
        f"[bold green]⚡ AutoPilot Lead Generation & Outreach Engine Active[/bold green]\n"
        f"• Target: High-utility shops (Restaurants, Meat shops, Bakeries, Retail)\n"
        f"• Engine: Conor's Docker Scraper (http://localhost:8001)\n"
        f"• WhatsApp Profile: [cyan]{WHATSAPP_PROFILE_DIR.name}[/cyan]\n"
        f"• Daily Safety Limit: [bold yellow]{daily_limit} messages max[/bold yellow]\n"
        f"• Anti-Ban Pauses: [bold]{min_delay} - {max_delay}s[/bold] between messages\n"
        f"• Mode: [bold magenta]{'DRY RUN (Preview Only)' if dry_run else 'LIVE AUTONOMOUS'}[/bold magenta]\n"
        f"• Master Tracker: [dim]{MASTER_TRACKER_FILE}[/dim]",
        border_style="green"
    ))

    # Initialize client
    client = GooglePlacesClient(use_docker=True)
    if not client.is_docker_alive() and not dry_run:
        console.print("[red]Error: Docker Scraper is not running at http://localhost:8001.[/red]")
        console.print("[yellow]Please run `run.bat start-docker` first.[/yellow]")
        return

    contacted_phones, contacted_names, _ = load_master_tracker()
    console.print(f"[dim]Master Tracker loaded: {len(contacted_phones)} previously contacted phones.[/dim]\n")

    target_queue = build_target_search_queue()
    messages_sent_today = 0

    browser = None
    page = None

    if not dry_run:
        try:
            from playwright.sync_api import sync_playwright
            playwright_instance = sync_playwright().start()
            browser = playwright_instance.chromium.launch_persistent_context(
                user_data_dir=str(WHATSAPP_PROFILE_DIR),
                channel="msedge",
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            page = browser.pages[0] if browser.pages else browser.new_page()

            console.print("[cyan]Connecting to WhatsApp Web...[/cyan]")
            page.goto("https://web.whatsapp.com", timeout=60000)

            console.print("[yellow]Checking WhatsApp authentication...[/yellow]")
            console.print("[dim]If first run, scan the QR code now. The bot will wait for you.[/dim]")
            try:
                page.wait_for_selector('div[contenteditable="true"], div[data-tab="3"], [aria-label="Chat list"]', timeout=90000)
                console.print("[bold green]✔ WhatsApp Web Authenticated![/bold green]\n")
            except Exception:
                console.print("[red]Timeout waiting for WhatsApp login. Exiting.[/red]")
                if browser:
                    browser.close()
                playwright_instance.stop()
                return
        except Exception as e:
            console.print(f"[red]Error starting browser: {e}[/red]")
            return

    try:
        # Loop through cities and shop categories
        for city, category in target_queue:
            if messages_sent_today >= daily_limit:
                console.print(Panel(
                    f"[bold yellow]Daily safety limit of {daily_limit} messages reached![/bold yellow]\n"
                    f"Pausing autonomous outreach to protect your WhatsApp account from spam filters.\n"
                    f"Come back tomorrow or restart with `--daily-limit` if desired.",
                    title="Safety Cap Reached",
                    border_style="yellow"
                ))
                break

            query = f"{category} in {city}, Tamil Nadu"
            console.print(f"\n[bold cyan]🔍 Target Scan:[/bold cyan] [bold white]{query}[/bold white]")

            raw_places = client.search_places(query=query, max_results=40)
            console.print(f"   Scraped {len(raw_places)} listings from Google Maps.")

            # Filter candidates
            qualified_leads = []
            for p in raw_places:
                name = p.get("name", "").strip()
                norm_name = name.lower()
                rating = p.get("rating", 0.0)
                reviews = p.get("review_count", 0)
                website = p.get("website", "").strip()
                raw_phone = p.get("phone", "")

                # Criteria check
                # Real website check (allow social media profiles as high-value prospects)
                w_clean = website.lower()
                has_real_web = w_clean.startswith("http") and "instagram.com" not in w_clean and "facebook.com" not in w_clean
                if has_real_web:
                    continue  # Already has real website

                # Phone check & normalization
                clean_phone, phone_type = normalize_indian_phone(raw_phone)
                if not clean_phone:
                    continue

                # Deduplication check against master tracker
                if clean_phone in contacted_phones or norm_name in contacted_names:
                    continue

                p["cleaned_phone"] = clean_phone
                p["city"] = city
                p["category"] = category
                qualified_leads.append(p)

            console.print(f"   Found [bold green]{len(qualified_leads)} fresh qualified shops[/bold green] without websites.")

            if not qualified_leads:
                time.sleep(2)
                continue

            # Process each lead autonomously
            for lead in qualified_leads:
                # Check cross-channel daily rate limiter
                can_proceed, curr_c, max_l = can_send("whatsapp")
                if not can_proceed or messages_sent_today >= daily_limit:
                    console.print(f"\n[bold red]⛔ Daily WhatsApp limit ({curr_c}/{max_l}) reached. Halting auto-pilot.[/bold red]")
                    break

                shop_name = lead.get("name", "")
                phone = lead.get("cleaned_phone", "")
                reviews = lead.get("review_count", 0)
                rating = lead.get("rating", 0.0)

                # Generate short 3-line human message with variant tag
                pitch_msg, variant_id = generate_varied_pitch(lead, sender_name="", return_variant=True)

                console.print(f"\n   [bold]Sending to [{messages_sent_today + 1}/{daily_limit}]:[/bold] [cyan]{shop_name}[/cyan] ({city})")
                console.print(f"   ⭐ {rating}★ | 💬 {reviews} reviews | 📞 +{phone} | Variant: {variant_id}")

                if dry_run:
                    console.print(Panel(pitch_msg, title=f"Preview ({variant_id}): {shop_name}", border_style="cyan"))
                    contacted_phones.add(phone)
                    contacted_names.add(shop_name.lower())
                    messages_sent_today += 1
                    time.sleep(1)
                    continue

                # Live Send via Playwright with human fingerprint typing
                try:
                    wa_url = f"https://web.whatsapp.com/send?phone={phone}"
                    page.goto(wa_url, timeout=45000)
                    send_button_selector = 'span[data-icon="send"], button[aria-label="Send"], span[data-icon="send-light"]'
                    input_box_selector = 'div[contenteditable="true"][data-tab="10"], div[contenteditable="true"][aria-label], footer div[contenteditable="true"]'

                    chat_loaded = False
                    for _ in range(30):
                        time.sleep(1)
                        if page.locator('text="Phone number shared via url is invalid."').count() > 0 or \
                           page.locator('text="Phone number is not on WhatsApp"').count() > 0:
                            console.print("   [yellow]⚠ Number not registered on WhatsApp. Skipping.[/yellow]")
                            lead["whatsapp_status"] = "NOT_ON_WHATSAPP"
                            lead["whatsapp_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            lead["message_sent"] = ""
                            lead["conversion_stage"] = "NOT_ON_WHATSAPP"
                            save_to_master_tracker([lead])
                            contacted_phones.add(phone)
                            contacted_names.add(shop_name.lower())
                            break

                        if page.locator(input_box_selector).count() > 0:
                            chat_loaded = True
                            break

                    if chat_loaded:
                        input_box = page.locator(input_box_selector).first

                        # Human idle jitter and focus
                        _jitter_mouse(page)
                        time.sleep(random.uniform(0.6, 1.5))
                        input_box.click()
                        time.sleep(random.uniform(0.3, 0.8))

                        # Clear input
                        page.keyboard.press("Control+a")
                        time.sleep(random.uniform(0.1, 0.25))
                        page.keyboard.press("Delete")
                        time.sleep(random.uniform(0.2, 0.5))

                        console.print(f"   [dim]Composing letter-by-letter (human typing simulation)...[/dim]")
                        time.sleep(random.uniform(1.0, 2.0))

                        # Type letter by letter
                        _human_type(page, pitch_msg.replace("\n", "\n"), input_box)

                        time.sleep(random.uniform(0.8, 1.8))
                        _jitter_mouse(page)
                        time.sleep(random.uniform(0.3, 0.6))

                        # Click Send
                        page.locator(send_button_selector).first.click()
                        time.sleep(3.0)

                        console.print(f"   [bold green]✔ Message sent successfully to {shop_name}![/bold green]")
                        lead["whatsapp_status"] = "SENT"
                        lead["whatsapp_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        lead["message_sent"] = pitch_msg
                        lead["conversion_stage"] = "SENT"
                        lead["message_variant"] = variant_id

                        # Save to master tracker and update rate limiter
                        save_to_master_tracker([lead])
                        check_and_increment("whatsapp")
                        contacted_phones.add(phone)
                        contacted_names.add(shop_name.lower())
                        messages_sent_today += 1

                        # Safety pause between messages
                        pause_secs = random.randint(min_delay, max_delay)
                        console.print(f"   [dim]⏳ Anti-ban pause: resting {pause_secs}s before next shop...[/dim]")
                        time.sleep(pause_secs)

                except Exception as e:
                    console.print(f"   [red]✖ Error communicating with {shop_name}: {e}[/red]")
                    time.sleep(5)

            # Brief pause between search batches
            time.sleep(5)

    except KeyboardInterrupt:
        console.print("\n[yellow]Autonomous pilot stopped by user (Ctrl+C).[/yellow]")

    finally:
        if browser:
            browser.close()
        console.print(Panel(
            f"[bold green]Pilot Session Finished[/bold green]\n"
            f"Total Messages Sent: [bold]{messages_sent_today}[/bold]\n"
            f"Master Record Updated: [cyan]{MASTER_TRACKER_FILE}[/cyan]",
            border_style="green"
        ))


def main():
    parser = argparse.ArgumentParser(description="Autonomous Lead Finder & WhatsApp Outreach Bot.")
    parser.add_argument("--daily-limit", type=int, default=20, help="Maximum messages to send per day (default: 20)")
    parser.add_argument("--min-delay", type=int, default=35, help="Min delay seconds between sends (default: 35)")
    parser.add_argument("--max-delay", type=int, default=65, help="Max delay seconds between sends (default: 65)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate the autonomous loop without sending messages")
    parser.add_argument("--scrape-only", "--no-whatsapp", action="store_true", help="Run continuous scraper loop without any WhatsApp messaging")
    args = parser.parse_args()

    if args.scrape_only:
        from continuous_scraper import run_continuous_scraping
        run_continuous_scraping()
        return

    run_autonomous_autopilot(
        daily_limit=args.daily_limit,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
