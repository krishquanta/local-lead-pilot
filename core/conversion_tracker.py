"""
Conversion & Client Funnel Tracker for Local Web Design Outreach.
Manages stages: DISCOVERED -> SENT -> REPLIED -> INTERESTED -> VIDEO_SENT -> CALL_SCHEDULED -> CLIENT.
Generates metrics and enables 1-click status updates directly from dashboard or CLI.
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
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

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

STAGES = [
    "DISCOVERED",
    "SENT",
    "REPLIED",
    "INTERESTED",
    "VIDEO_SENT",
    "CALL_SCHEDULED",
    "CLIENT",
    "NOT_INTERESTED"
]

STAGE_ICONS = {
    "DISCOVERED": "🔍",
    "SENT": "📨",
    "FOLLOW_UP_SENT": "⏳",
    "REPLIED": "💬",
    "INTERESTED": "⭐",
    "VIDEO_SENT": "🎬",
    "CALL_SCHEDULED": "📞",
    "CLIENT": "🏆",
    "NOT_INTERESTED": "❌"
}


def normalize_digits(phone: str) -> str:
    return re.sub(r"[^\d]", "", phone or "")


def determine_stage(row: Dict[str, Any]) -> str:
    """Infers current conversion stage if not explicitly recorded."""
    explicit = (row.get("Conversion Stage") or "").strip().upper()
    if explicit in STAGES:
        return explicit

    wa_status = (row.get("WhatsApp Status") or "").strip().upper()
    email_sent = bool((row.get("Email Sent At") or "").strip())
    has_reply = bool((row.get("WhatsApp Reply") or "").strip())

    if wa_status == "CLIENT" or explicit == "CLIENT":
        return "CLIENT"
    if wa_status == "REPLIED" or has_reply:
        return "REPLIED"
    if wa_status == "FOLLOW_UP_SENT":
        return "FOLLOW_UP_SENT"
    if wa_status in ("SENT", "DELIVERED") or email_sent:
        return "SENT"
    return "DISCOVERED"


def get_all_leads() -> List[Dict[str, Any]]:
    """Loads all unique leads across master and session files."""
    leads = []
    seen = set()
    for fpath in [MASTER_FILE, ACTIVE_FILE, TRACKER_FILE]:
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


def get_funnel_counts() -> Dict[str, int]:
    leads = get_all_leads()
    counts = {stage: 0 for stage in STAGES}
    counts["FOLLOW_UP_SENT"] = 0

    for lead in leads:
        stage = determine_stage(lead)
        if stage in counts:
            counts[stage] += 1
        else:
            counts["DISCOVERED"] += 1
    return counts


def update_lead_stage(identifier: str, new_stage: str) -> int:
    """
    Updates the stage of a lead matched by Phone or Business Name across all CSVs.
    Returns number of rows updated.
    """
    new_stage = new_stage.strip().upper()
    if new_stage not in STAGES and new_stage != "FOLLOW_UP_SENT":
        raise ValueError(f"Invalid stage '{new_stage}'. Must be one of: {STAGES}")

    target_digits = normalize_digits(identifier)
    target_name = identifier.strip().lower()
    updated_count = 0

    for fpath in [MASTER_FILE, ACTIVE_FILE, TRACKER_FILE]:
        if not fpath.exists():
            continue
        try:
            with open(fpath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                fieldnames = list(reader.fieldnames or [])

            if "Conversion Stage" not in fieldnames:
                fieldnames.append("Conversion Stage")

            modified = False
            for row in rows:
                row_digits = normalize_digits(row.get("Cleaned Mobile") or row.get("Phone") or "")
                row_name = (row.get("Business Name") or "").strip().lower()

                match = False
                if target_digits and len(target_digits) >= 10 and (target_digits in row_digits or row_digits in target_digits):
                    match = True
                elif target_name and target_name in row_name:
                    match = True

                if match:
                    row["Conversion Stage"] = new_stage
                    if new_stage in ("REPLIED", "CLIENT", "INTERESTED", "NOT_INTERESTED"):
                        row["WhatsApp Status"] = new_stage
                    modified = True
                    updated_count += 1

            if modified:
                with open(fpath, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(rows)
        except Exception as e:
            console.print(f"[red]Error updating {fpath.name}: {e}[/red]")

    return updated_count


def print_funnel() -> None:
    counts = get_funnel_counts()
    total_leads = sum(counts.values())

    console.print(Panel(
        f"[bold green]Tamil Nadu Web Design Outreach Funnel[/bold green]\n"
        f"Total Tracked Businesses: [bold yellow]{total_leads:,}[/bold yellow]",
        border_style="green"
    ))

    table = Table(title="Conversion Pipeline Breakdown", show_lines=True)
    table.add_column("Stage", style="bold white", width=20)
    table.add_column("Count", justify="right", style="cyan", width=10)
    table.add_column("% of Total", justify="right", style="yellow", width=12)
    table.add_column("Next Step Action", style="white")

    stage_actions = {
        "DISCOVERED": "Verify phone/socials or queue for email/WA",
        "SENT": "Waiting for reply (or 48h follow-up)",
        "FOLLOW_UP_SENT": "Gentle nudge sent; await response",
        "REPLIED": "Respond promptly; offer 15s mobile preview video",
        "INTERESTED": "Send personalized video link or WhatsApp preview",
        "VIDEO_SENT": "Ask for thoughts; schedule 5-min review call",
        "CALL_SCHEDULED": "Close website proposal and timeline",
        "CLIENT": "Onboard & build website! 🚀",
        "NOT_INTERESTED": "Politely acknowledge; archive lead"
    }

    all_stages = ["DISCOVERED", "SENT", "FOLLOW_UP_SENT", "REPLIED", "INTERESTED", "VIDEO_SENT", "CALL_SCHEDULED", "CLIENT", "NOT_INTERESTED"]

    for stg in all_stages:
        cnt = counts.get(stg, 0)
        pct = (cnt / total_leads * 100) if total_leads > 0 else 0
        icon = STAGE_ICONS.get(stg, "•")
        table.add_row(
            f"{icon} {stg}",
            f"{cnt:,}",
            f"{pct:.1f}%",
            stage_actions.get(stg, "")
        )

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Outreach Conversion Funnel Tracker")
    parser.add_argument("--funnel", action="store_true", help="Print the conversion funnel stats")
    parser.add_argument("--update", type=str, help="Business Name or Phone number to update")
    parser.add_argument("--stage", type=str, help=f"New stage ({', '.join(STAGES)})")
    args = parser.parse_args()

    if args.update and args.stage:
        updated = update_lead_stage(args.update, args.stage)
        console.print(f"[bold green]✔ Successfully updated {updated} records to stage '{args.stage}'![/bold green]")
        return

    print_funnel()


if __name__ == "__main__":
    main()
