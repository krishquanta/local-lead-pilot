"""
Daily Operations & Outreach Summary Report.
Aggregates daily performance across Scraper, WhatsApp, Cold Email, Inbound Replies,
and Pipeline Conversions with actionable next steps.
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
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns

# Ensure UTF-8 output on Windows consoles
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
TRACKER_FILE = OUTPUT_DIR / "master_outreach_tracker.csv"

console = Console(force_terminal=True, legacy_windows=False)

try:
    from rate_limiter import get_status_summary
except ImportError:
    get_status_summary = None

try:
    from follow_up_scheduler import get_followup_candidates
except ImportError:
    get_followup_candidates = None


def is_matching_date(ts_str: str, target_date: str) -> bool:
    if not ts_str:
        return False
    return ts_str.strip().startswith(target_date)


def load_all_leads() -> List[Dict[str, Any]]:
    leads = []
    seen = set()
    for fpath in [TRACKER_FILE, MASTER_FILE, ACTIVE_FILE]:
        if not fpath.exists():
            continue
        try:
            with open(fpath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    uid = (r.get("Google Place ID") or "").strip() or (r.get("Cleaned Mobile") or r.get("Phone") or "").strip() or (r.get("Business Name") or "").strip().lower()
                    if uid and uid not in seen:
                        seen.add(uid)
                        leads.append(r)
        except Exception:
            continue
    return leads


def generate_daily_report(target_date: Optional[str] = None) -> None:
    if not target_date:
        target_date = datetime.now().strftime("%Y-%m-%d")

    leads = load_all_leads()

    scraped_today = 0
    wa_today = 0
    email_today = 0
    followup_today = 0
    replies_today = 0
    clients_today = 0

    city_breakdown = {}
    category_breakdown = {}

    for r in leads:
        scraped_at = r.get("Scraped At", "")
        wa_ts = r.get("WhatsApp Timestamp", "")
        email_ts = r.get("Email Sent At", "")
        fu_ts = r.get("Follow Up Timestamp", "")
        reply_ts = r.get("WhatsApp Reply At", "")
        stage = (r.get("Conversion Stage") or "").upper()

        if is_matching_date(scraped_at, target_date):
            scraped_today += 1
            city = r.get("City", "Unknown")
            cat = r.get("Category", "General")
            city_breakdown[city] = city_breakdown.get(city, 0) + 1
            category_breakdown[cat] = category_breakdown.get(cat, 0) + 1

        if is_matching_date(wa_ts, target_date) and (r.get("WhatsApp Status") or "") in ("SENT", "DELIVERED"):
            wa_today += 1

        if is_matching_date(email_ts, target_date):
            email_today += 1

        if is_matching_date(fu_ts, target_date):
            followup_today += 1

        if is_matching_date(reply_ts, target_date) or ((r.get("WhatsApp Status") or "") == "REPLIED" and is_matching_date(wa_ts, target_date)):
            replies_today += 1

        if stage == "CLIENT" and (is_matching_date(wa_ts, target_date) or is_matching_date(email_ts, target_date)):
            clients_today += 1

    # Header Panel
    console.print(Panel(
        f"[bold green]Daily Operations & Outreach Summary[/bold green]\n"
        f"Date: [bold cyan]{target_date}[/bold cyan] | Total Database Size: [bold yellow]{len(leads):,}[/bold yellow] leads",
        border_style="green"
    ))

    # Metrics Table
    table = Table(title="Today's Performance KPIs", show_lines=True)
    table.add_column("Channel / Metric", style="bold white", width=26)
    table.add_column("Count Today", justify="right", style="cyan", width=14)
    table.add_column("All-Time Total", justify="right", style="dim", width=16)
    table.add_column("Status / Safety", style="white")

    total_scraped = len(leads)
    total_emails = sum(1 for r in leads if (r.get("Email Sent At") or "").strip())
    total_wa = sum(1 for r in leads if (r.get("WhatsApp Status") or "").upper() in ("SENT", "DELIVERED", "REPLIED", "FOLLOW_UP_SENT"))
    total_replies = sum(1 for r in leads if (r.get("WhatsApp Status") or "").upper() == "REPLIED" or (r.get("WhatsApp Reply") or "").strip())
    total_clients = sum(1 for r in leads if (r.get("Conversion Stage") or "").upper() == "CLIENT")

    # Rate limit status
    rl_info = get_status_summary() if get_status_summary else None
    wa_rem = rl_info["whatsapp"]["remaining"] if rl_info else "-"
    email_rem = rl_info["email"]["remaining"] if rl_info else "-"

    table.add_row(
        "🔎 Leads Scraped",
        f"[bold green]+{scraped_today}[/bold green]" if scraped_today > 0 else "0",
        f"{total_scraped:,}",
        "[green]Active[/green]" if scraped_today > 0 else "[dim]Idle[/dim]"
    )
    table.add_row(
        "✉️ Cold Emails Sent",
        f"[bold green]+{email_today}[/bold green]" if email_today > 0 else "0",
        f"{total_emails:,}",
        f"{email_rem} remaining today" if rl_info else "Safe pacing active"
    )
    table.add_row(
        "💬 WhatsApp Messages Sent",
        f"[bold green]+{wa_today}[/bold green]" if wa_today > 0 else "0",
        f"{total_wa:,}",
        f"{wa_rem} remaining today" if rl_info else "Anti-ban limits active"
    )
    table.add_row(
        "⏳ 48h Follow-ups Sent",
        f"[bold yellow]+{followup_today}[/bold yellow]" if followup_today > 0 else "0",
        "-",
        "Gentle nudges"
    )
    table.add_row(
        "📬 Inbound Replies",
        f"[bold magenta]{replies_today}[/bold magenta]",
        f"{total_replies:,}",
        "High-intent opportunities"
    )
    table.add_row(
        "🏆 New Clients Won",
        f"[bold yellow]{clients_today}[/bold yellow]",
        f"{total_clients:,}",
        "Website orders signed"
    )

    console.print(table)

    # Next Steps & Follow-up Queue
    if get_followup_candidates:
        candidates = get_followup_candidates(hours_threshold=48)
        console.print(f"\n[cyan]📋 Actionable Follow-up Queue:[/cyan] [bold yellow]{len(candidates)}[/bold yellow] leads are ready for their 48h follow-up message.")
        if candidates:
            console.print("   [dim]Run: `python whatsapp_sender.py --follow-up --limit 5` to send gentle nudges.[/dim]")

    console.print("[dim]Command center: run `python dashboard.py` to view cards in viewer.html.[/dim]\n")


def main():
    parser = argparse.ArgumentParser(description="Daily Operations Summary")
    parser.add_argument("--date", type=str, help="Specific date YYYY-MM-DD (defaults to today)")
    args = parser.parse_args()
    generate_daily_report(args.date)


if __name__ == "__main__":
    main()
