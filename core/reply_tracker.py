"""
WhatsApp Reply Monitor & Incoming Message Tracker.
Scans WhatsApp Web chat pane for incoming replies from previously contacted numbers,
records replies into CSV databases, and raises alerts for high-intent business leads.
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
import re
import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "leads_output"
MASTER_FILE = OUTPUT_DIR / "master_scraped_leads.csv"
ACTIVE_FILE = OUTPUT_DIR / "tamil_nadu_continuous_leads.csv"
TRACKER_FILE = OUTPUT_DIR / "master_outreach_tracker.csv"

console = Console(force_terminal=True, legacy_windows=False)


def send_telegram_alert(message: str) -> bool:
    """Optional Telegram webhook notification if configured in .env."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        return False
    try:
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def load_contacted_leads(csv_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Loads all leads that have been messaged on WhatsApp."""
    target_files = [csv_path] if csv_path else [TRACKER_FILE, MASTER_FILE, ACTIVE_FILE]
    seen_phones = set()
    contacted = []

    for fpath in target_files:
        if not fpath or not fpath.exists():
            continue
        try:
            with open(fpath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    status = (row.get("WhatsApp Status") or "").strip().upper()
                    phone = re.sub(r"[^\d]", "", row.get("Cleaned Mobile") or row.get("Phone") or row.get("Cleaned Phone") or "")
                    if phone and phone not in seen_phones and status in ("SENT", "DELIVERED", "REPLIED", "FOLLOW_UP_SENT"):
                        seen_phones.add(phone)
                        contacted.append(row)
        except Exception:
            continue

    return contacted


def scan_for_replies(page, target_csv: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Scans the open WhatsApp Web page chat list pane for incoming replies.
    Returns a list of newly detected replies: [{'phone': ..., 'name': ..., 'text': ...}].
    """
    new_replies = []
    if not page:
        return new_replies

    console.print("[cyan]🔍 Scanning WhatsApp chat list for incoming replies...[/cyan]")
    try:
        # Wait for chat list to be visible
        chat_pane_selector = '#pane-side, div[aria-label="Chat list"], div[data-tab="3"]'
        if page.locator(chat_pane_selector).count() == 0:
            console.print("   [dim]Chat list not currently visible or still loading.[/dim]")
            return new_replies

        # Look for chat items with unread badges or incoming activity
        # WhatsApp Web uses data-testid="cell-frame-container" or role="listitem"
        chat_items = page.locator('div[role="listitem"], div[data-testid="cell-frame-container"]')
        item_count = min(chat_items.count(), 20)  # check top 20 recent chats

        for i in range(item_count):
            item = chat_items.nth(i)
            text_content = item.inner_text() or ""
            
            # Check for unread badge indicator
            unread_badge = item.locator('span[data-testid="icon-unread-count"], span[aria-label*="unread"]')
            has_unread = unread_badge.count() > 0

            # Check if this chat has an outgoing checkmark icon
            has_outgoing_check = item.locator('span[data-icon="msg-dblcheck"], span[data-icon="msg-check"], span[data-icon="status-v3-unread"]').count() > 0

            # If there's an unread badge or the preview does NOT show outgoing checkmark:
            lines = [l.strip() for l in text_content.split("\n") if l.strip()]
            if not lines:
                continue

            header_text = lines[0] # Often contact name or phone
            phone_digits = re.sub(r"[^\d]", "", header_text)

            # Match against our contacted database
            if has_unread or (not has_outgoing_check and len(lines) >= 2):
                preview_snippet = lines[1] if len(lines) > 1 else ""
                reply_data = {
                    "contact_header": header_text,
                    "phone": phone_digits,
                    "preview": preview_snippet,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                new_replies.append(reply_data)

    except Exception as e:
        console.print(f"   [dim]Reply scan encountered notice: {e}[/dim]")

    if new_replies:
        console.print(f"[bold green]🎉 Found {len(new_replies)} active conversation(s) with potential replies![/bold green]")
        record_replies(new_replies, target_csv)
    else:
        console.print("   [dim]No unread or new incoming replies detected in top chats.[/dim]")

    return new_replies


def record_replies(replies: List[Dict[str, Any]], target_csv: Optional[Path] = None) -> int:
    """Updates CSV files marking matching leads as REPLIED with preview and timestamp."""
    if not replies:
        return 0

    csv_targets = [target_csv] if target_csv else [TRACKER_FILE, MASTER_FILE, ACTIVE_FILE]
    updated_total = 0

    for fpath in csv_targets:
        if not fpath or not fpath.exists():
            continue
        try:
            with open(fpath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                fieldnames = list(reader.fieldnames or [])

            for col in ["WhatsApp Reply", "WhatsApp Reply At", "Conversion Stage"]:
                if col not in fieldnames:
                    fieldnames.append(col)

            modified = False
            for row in rows:
                row_phone = re.sub(r"[^\d]", "", row.get("Cleaned Mobile") or row.get("Phone") or row.get("Cleaned Phone") or "")
                row_name = (row.get("Business Name") or "").lower()

                for rep in replies:
                    rep_phone = rep.get("phone", "")
                    rep_header = rep.get("contact_header", "").lower()

                    match = False
                    if rep_phone and len(rep_phone) >= 10 and (rep_phone in row_phone or row_phone in rep_phone):
                        match = True
                    elif row_name and rep_header and (row_name in rep_header or rep_header in row_name):
                        match = True

                    if match:
                        row["WhatsApp Status"] = "REPLIED"
                        row["WhatsApp Reply"] = rep.get("preview", "Customer replied on WhatsApp")
                        row["WhatsApp Reply At"] = rep.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        row["Conversion Stage"] = "REPLIED"
                        modified = True
                        updated_total += 1
                        send_telegram_alert(f"🚀 *New Lead Reply!*\nBusiness: {row.get('Business Name')}\nMessage: {rep.get('preview')}")

            if modified:
                with open(fpath, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(rows)
        except Exception as e:
            console.print(f"[red]Error updating {fpath.name} with replies: {e}[/red]")

    return updated_total


def list_replied_leads() -> List[Dict[str, Any]]:
    """Returns all leads from CSVs that have replied."""
    replied = []
    seen = set()
    for fpath in [TRACKER_FILE, MASTER_FILE, ACTIVE_FILE]:
        if not fpath.exists():
            continue
        with open(fpath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if (r.get("WhatsApp Status") or "").upper() == "REPLIED" or r.get("WhatsApp Reply"):
                    phone = r.get("Cleaned Mobile") or r.get("Phone") or ""
                    if phone not in seen:
                        seen.add(phone)
                        replied.append(r)
    return replied


def main():
    replied = list_replied_leads()
    console.print(Panel(
        f"[bold green]WhatsApp Reply Monitor[/bold green]\n"
        f"Total Inbound Replies Recorded: [bold yellow]{len(replied)}[/bold yellow]",
        border_style="green"
    ))

    if not replied:
        console.print("[dim]No replies recorded yet. Once leads message back, they will appear here and in viewer.html.[/dim]")
        return

    table = Table(title="Leads That Replied on WhatsApp", show_lines=True)
    table.add_column("Business Name", style="bold white")
    table.add_column("City", style="cyan")
    table.add_column("Phone", style="green")
    table.add_column("Latest Reply / Preview", style="yellow")
    table.add_column("Replied At", style="dim")

    for r in replied:
        table.add_row(
            r.get("Business Name", "Unknown"),
            r.get("City", ""),
            r.get("Cleaned Mobile") or r.get("Phone", ""),
            (r.get("WhatsApp Reply") or "Active conversation")[:45],
            r.get("WhatsApp Reply At") or r.get("WhatsApp Timestamp") or ""
        )
    console.print(table)


if __name__ == "__main__":
    main()
