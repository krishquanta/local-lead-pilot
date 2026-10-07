"""
A/B Message Variant Tracker & Copy Performance Analyzer.
Tracks which openers, questions, and CTAs yield the highest reply and conversion rates
across WhatsApp and Cold Email outreach.
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
from collections import defaultdict

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


def get_all_outreach_records() -> List[Dict[str, Any]]:
    records = []
    seen = set()
    for fpath in [TRACKER_FILE, MASTER_FILE, ACTIVE_FILE]:
        if not fpath.exists():
            continue
        try:
            with open(fpath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    uid = (row.get("Cleaned Mobile") or row.get("Phone") or row.get("Gmail") or row.get("Business Name") or "").strip()
                    if uid and uid not in seen:
                        seen.add(uid)
                        records.append(row)
        except Exception:
            continue
    return records


def analyze_variants() -> Dict[str, Dict[str, Any]]:
    records = get_all_outreach_records()
    stats = defaultdict(lambda: {"sent": 0, "replied": 0, "interested": 0, "client": 0})

    for r in records:
        wa_status = (r.get("WhatsApp Status") or "").upper()
        email_sent = bool((r.get("Email Sent At") or "").strip())
        variant = (r.get("Message Variant") or "").strip()
        stage = (r.get("Conversion Stage") or "").upper()
        has_reply = bool((r.get("WhatsApp Reply") or "").strip()) or wa_status == "REPLIED"

        if not variant:
            if wa_status in ("SENT", "DELIVERED", "REPLIED", "FOLLOW_UP_SENT"):
                variant = "WA_Standard_V1"
            elif email_sent:
                variant = "Email_Standard_V1"
            else:
                continue

        stats[variant]["sent"] += 1
        if has_reply or stage in ("REPLIED", "INTERESTED", "VIDEO_SENT", "CLIENT"):
            stats[variant]["replied"] += 1
        if stage in ("INTERESTED", "VIDEO_SENT", "CLIENT"):
            stats[variant]["interested"] += 1
        if stage == "CLIENT":
            stats[variant]["client"] += 1

    return dict(stats)


def print_ab_report() -> None:
    stats = analyze_variants()
    total_sent = sum(v["sent"] for v in stats.values())

    console.print(Panel(
        f"[bold cyan]A/B Message Variant Performance Report[/bold cyan]\n"
        f"Total Tracked Sends with Variants: [bold yellow]{total_sent}[/bold yellow]",
        border_style="cyan"
    ))

    if not stats:
        console.print("[dim]No variant performance data recorded yet. As you run outreach, stats will populate here.[/dim]")
        return

    table = Table(title="Outreach Copy Benchmark (Ranked by Reply Rate)", show_lines=True)
    table.add_column("Message Variant", style="bold white", width=25)
    table.add_column("Sent", justify="right", style="cyan", width=8)
    table.add_column("Replied", justify="right", style="green", width=8)
    table.add_column("Reply Rate %", justify="right", style="bold yellow", width=14)
    table.add_column("Interested", justify="right", style="magenta", width=12)
    table.add_column("Clients Won", justify="right", style="bold green", width=12)

    # Sort by reply rate descending
    sorted_variants = sorted(
        stats.items(),
        key=lambda x: (x[1]["replied"] / x[1]["sent"] if x[1]["sent"] > 0 else 0),
        reverse=True
    )

    for var_name, counts in sorted_variants:
        sent = counts["sent"]
        replied = counts["replied"]
        rr = (replied / sent * 100) if sent > 0 else 0
        table.add_row(
            var_name,
            str(sent),
            str(replied),
            f"{rr:.1f}%",
            str(counts["interested"]),
            str(counts["client"])
        )

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="A/B Outreach Copy Analyzer")
    parser.add_argument("--report", action="store_true", help="Print variant performance report")
    args = parser.parse_args()
    print_ab_report()


if __name__ == "__main__":
    main()
