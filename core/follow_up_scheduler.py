"""
48-Hour WhatsApp Follow-Up Engine.
Identifies leads contacted >= 48 hours ago who haven't replied,
and generates polite, non-pushy follow-up messages.
Strictly sends at most ONE follow-up per business to avoid annoyance.
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
import time
import random
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "leads_output"
MASTER_FILE = OUTPUT_DIR / "master_scraped_leads.csv"
ACTIVE_FILE = OUTPUT_DIR / "tamil_nadu_continuous_leads.csv"
TRACKER_FILE = OUTPUT_DIR / "master_outreach_tracker.csv"

console = Console(force_terminal=True, legacy_windows=False)

FOLLOW_UP_TEMPLATES = [
    "Hi, just following up on my note from a couple days ago about {name}. Recorded a short 15s mobile template preview with direct WhatsApp ordering — ok if I share it here?",
    "Hello team {name}, just checking in quickly! Let me know if you'd like to see the quick video preview of the mobile catalogue template. No pressure at all 🙂",
    "Hi there, wanted to follow up on the short video preview I mentioned for {name}. If you're busy or it's not a priority right now, completely understand! Let me know if interested.",
    "Hi, quick follow-up for {name} — did you get a chance to see my earlier message? Happy to send the 15-second mobile template preview if helpful!"
]


def clean_shop_name(raw_name: str) -> str:
    clean = re.sub(r"\s*[-–—|•,]\s*(Coimbatore|Chennai|Trichy|Madurai|Salem|Tiruppur|Erode|Vellore|Tirunelveli|Tamil Nadu|TN|Branch).*$", "", raw_name, flags=re.IGNORECASE)
    clean = re.sub(r"\s*(Pvt\.?\s*Ltd\.?|LLP|Ltd\.?|LLC)", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*\([^)]*\)", "", clean)
    return clean.strip() or raw_name


def generate_followup_message(lead: Dict[str, Any], sender_name: str = "") -> str:
    raw_name = lead.get("Business Name") or lead.get("name") or "there"
    name = clean_shop_name(raw_name)
    template = random.choice(FOLLOW_UP_TEMPLATES)
    msg = template.format(name=name)
    if sender_name and sender_name.strip():
        msg += f"\n\n- {sender_name.strip()}"
    return msg


def parse_timestamp(ts_str: str) -> Optional[datetime]:
    if not ts_str:
        return None
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts_str.strip(), fmt)
        except Exception:
            pass
    return None


def get_followup_candidates(
    hours_threshold: int = 48,
    target_csv: Optional[Path] = None
) -> List[Tuple[Path, int, Dict[str, Any]]]:
    """
    Finds leads whose initial WhatsApp outreach occurred >= hours_threshold ago,
    who haven't replied, and who haven't already received a follow-up.
    Returns: list of (file_path, row_index, row_dict).
    """
    candidates = []
    seen_phones = set()
    cutoff_time = datetime.now() - timedelta(hours=hours_threshold)

    files_to_check = [target_csv] if target_csv else [TRACKER_FILE, MASTER_FILE, ACTIVE_FILE]

    for fpath in files_to_check:
        if not fpath or not fpath.exists():
            continue
        try:
            with open(fpath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            for idx, row in enumerate(rows):
                status = (row.get("WhatsApp Status") or "").strip().upper()
                phone = re.sub(r"[^\d]", "", row.get("Cleaned Mobile") or row.get("Phone") or row.get("Cleaned Phone") or "")

                # Skip if already replied, already followed up, or not on WhatsApp
                if status in ("REPLIED", "FOLLOW_UP_SENT", "NOT_ON_WHATSAPP", "INTERESTED", "CLIENT", "NOT_INTERESTED"):
                    continue

                if status == "SENT":
                    ts_str = row.get("WhatsApp Timestamp") or row.get("Scraped At") or ""
                    ts = parse_timestamp(ts_str)
                    if ts and ts <= cutoff_time:
                        if phone and phone not in seen_phones:
                            seen_phones.add(phone)
                            candidates.append((fpath, idx, row))
        except Exception as e:
            console.print(f"[red]Error reading {fpath.name}: {e}[/red]")

    return candidates


def mark_followup_sent(fpath: Path, row_idx: int, phone: str) -> None:
    """Updates the lead status to FOLLOW_UP_SENT in the CSV."""
    if not fpath.exists():
        return
    try:
        with open(fpath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = list(reader.fieldnames or [])

        for col in ["Follow Up Timestamp", "Conversion Stage"]:
            if col not in fieldnames:
                fieldnames.append(col)

        if 0 <= row_idx < len(rows):
            rows[row_idx]["WhatsApp Status"] = "FOLLOW_UP_SENT"
            rows[row_idx]["Follow Up Timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows[row_idx]["Conversion Stage"] = "FOLLOW_UP_SENT"

        with open(fpath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    except Exception as e:
        console.print(f"[red]Failed to update follow-up status in {fpath.name}: {e}[/red]")


def main():
    parser = argparse.ArgumentParser(description="48-Hour WhatsApp Follow-Up Engine")
    parser.add_argument("--hours", type=int, default=48, help="Hours since initial contact (default: 48)")
    parser.add_argument("--limit", type=int, default=10, help="Max candidates to show or queue (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Preview follow-up candidates without modifying")
    args = parser.parse_args()

    candidates = get_followup_candidates(hours_threshold=args.hours)

    console.print(Panel(
        f"[bold cyan]WhatsApp 48-Hour Follow-Up Engine[/bold cyan]\n"
        f"Cutoff window: Older than [bold yellow]{args.hours} hours[/bold yellow]\n"
        f"Qualified candidates due for gentle follow-up: [bold green]{len(candidates)}[/bold green]\n"
        f"Batch display limit: [bold white]{args.limit}[/bold white]",
        border_style="cyan"
    ))

    if not candidates:
        console.print("[dim]No leads currently due for follow-up (all recent or already replied/followed-up).[/dim]")
        return

    table = Table(title="Leads Scheduled for Follow-Up", show_lines=True)
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("Business Name", style="bold white", width=28)
    table.add_column("City", style="cyan", width=12)
    table.add_column("Mobile", style="green", width=16)
    table.add_column("Original Sent At", style="yellow", width=20)
    table.add_column("Sample Follow-Up Pitch", style="white")

    for i, (fpath, idx, row) in enumerate(candidates[:args.limit], start=1):
        sample_msg = generate_followup_message(row)
        table.add_row(
            str(i),
            row.get("Business Name", "")[:26],
            row.get("City", ""),
            row.get("Cleaned Mobile") or row.get("Phone", ""),
            row.get("WhatsApp Timestamp", "Earlier"),
            sample_msg[:60] + "..."
        )

    console.print(table)


if __name__ == "__main__":
    main()
