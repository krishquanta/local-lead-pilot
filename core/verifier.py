"""
Lead Verification Assistant:
Helps manually and semi-automatically verify whether leads truly lack a website
before sending cold outreach.

Tags:
- NO WEBSITE
- SOCIAL ONLY
- WEBSITE FOUND
- UNCERTAIN
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
_CORE = _ROOT / "core"
for _p in [str(_ROOT), str(_CORE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


import sys
import csv
import webbrowser
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt

from config import OUTPUT_DIR

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(force_terminal=True, legacy_windows=False)

# Directory aggregators to ignore when checking for actual standalone website
IGNORED_DOMAINS = [
    "justdial.com", "sulekha.com", "indiamart.com", "zaubacorp.com",
    "facebook.com", "instagram.com", "youtube.com", "linkedin.com",
    "twitter.com", "x.com", "tripadvisor.com", "zomato.com", "swiggy.com",
    "yellowpages.com", "google.com", "maps.google.com"
]


def find_latest_csv() -> Optional[Path]:
    """Find the leads CSV file in OUTPUT_DIR (prioritizing master_scraped_leads.csv)."""
    master_file = OUTPUT_DIR / "master_scraped_leads.csv"
    if master_file.exists() and master_file.stat().st_size > 0:
        return master_file
    csv_files = sorted(OUTPUT_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return csv_files[0] if csv_files else None


def quick_web_check(name: str, city: str) -> Dict[str, Any]:
    """
    Optional automated search using duckduckgo_search to assist verification.
    Identifies if social media accounts or potential standalone websites show up.
    """
    try:
        from duckduckgo_search import DDGS
        query = f'"{name}" {city}'
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append(r)

        found_social = []
        found_domains = []

        for r in results:
            href = r.get("href", "")
            title = r.get("title", "")
            lower_href = href.lower()

            if "instagram.com" in lower_href or "facebook.com" in lower_href:
                found_social.append(href)
            else:
                is_directory = any(ign in lower_href for ign in IGNORED_DOMAINS)
                if not is_directory and ("http://" in lower_href or "https://" in lower_href):
                    found_domains.append(href)

        suggestion = "NO WEBSITE"
        if found_domains:
            suggestion = f"POSSIBLE WEBSITE FOUND ({found_domains[0]})"
        elif found_social:
            suggestion = "SOCIAL ONLY"

        return {
            "suggestion": suggestion,
            "social_links": found_social,
            "domain_links": found_domains
        }
    except Exception as e:
        return {"suggestion": "UNCERTAIN", "error": str(e), "social_links": [], "domain_links": []}


def verify_leads_file(filepath: Path, auto_search: bool = True):
    """Interactive loop to review and verify leads."""
    if not filepath.exists():
        console.print(f"[red]Error: File not found at {filepath}[/red]")
        return

    with open(filepath, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if not rows:
        console.print("[yellow]No rows found in CSV.[/yellow]")
        return

    console.print(Panel(
        f"[bold cyan]Lead Verification Stage[/bold cyan]\n"
        f"File: [bold]{filepath.name}[/bold]\n"
        f"Total Leads: [bold]{len(rows)}[/bold]\n\n"
        f"[dim]Keys: [1] NO WEBSITE  [2] SOCIAL ONLY  [3] WEBSITE FOUND  [4] UNCERTAIN  [o] Open Search  [s] Skip  [q] Quit[/dim]",
        border_style="cyan"
    ))

    modified = False

    for idx, row in enumerate(rows, start=1):
        name = row.get("Business Name", "")
        city = row.get("City", "")
        rating = row.get("Rating", "")
        reviews = row.get("Review Count", "")
        current_status = row.get("Verification Status", "PENDING VERIFICATION")

        console.print(f"\n[bold green]Lead #{idx}/{len(rows)}:[/bold green] [bold white]{name}[/bold white] ({city})")
        console.print(f"⭐ {rating}★ | 💬 {reviews} reviews | 📞 {row.get('Phone', 'N/A')}")
        console.print(f"Current Status: [italic]{current_status}[/italic]")

        # Perform fast web search hint if requested
        if auto_search:
            with console.status("[dim]Checking web & social presence...[/dim]", spinner="dots"):
                check_result = quick_web_check(name, city)
            sugg = check_result.get("suggestion", "")
            console.print(f"🤖 Bot Hint: [bold yellow]{sugg}[/bold yellow]")
            if check_result.get("social_links"):
                console.print(f"   Social: {', '.join(check_result['social_links'][:2])}")
            if check_result.get("domain_links"):
                console.print(f"   Links: {', '.join(check_result['domain_links'][:2])}")

        search_query = f"{name} {city}"
        encoded_query = urllib.parse.quote(search_query)
        google_url = f"https://www.google.com/search?q={encoded_query}"
        insta_url = f"https://www.instagram.com/explore/tags/{urllib.parse.quote(name.replace(' ', ''))}/"

        while True:
            choice = Prompt.ask(
                "[bold cyan]Action[/bold cyan] (1=No Site, 2=Social Only, 3=Website Found, 4=Uncertain, o=Open in Browser, s=Skip, q=Quit)",
                choices=["1", "2", "3", "4", "o", "s", "q"],
                default="1"
            )

            if choice == "o":
                console.print(f"Opening Google Search for: [dim]{search_query}[/dim]")
                webbrowser.open(google_url)
                continue
            elif choice == "1":
                row["Verification Status"] = "NO WEBSITE"
                modified = True
                break
            elif choice == "2":
                row["Verification Status"] = "SOCIAL ONLY"
                modified = True
                break
            elif choice == "3":
                found_url = Prompt.ask("Enter the website URL found (or press Enter)", default="")
                row["Verification Status"] = "WEBSITE FOUND"
                row["Website"] = found_url if found_url else "Website verified elsewhere"
                modified = True
                break
            elif choice == "4":
                row["Verification Status"] = "UNCERTAIN"
                modified = True
                break
            elif choice == "s":
                break
            elif choice == "q":
                break

        if choice == "q":
            break

    if modified:
        with open(filepath, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        console.print(f"\n[bold green]✔ Saved verification updates back to: {filepath}[/bold green]")
    else:
        console.print("\n[dim]No changes were made.[/dim]")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Second-stage verification tool for Google Places leads.")
    parser.add_argument("--file", type=str, help="Path to CSV file to verify (defaults to latest in leads_output/)")
    parser.add_argument("--no-auto-search", action="store_true", help="Disable automatic web hints")
    args = parser.parse_args()

    if args.file:
        csv_path = Path(args.file)
    else:
        csv_path = find_latest_csv()

    if not csv_path or not csv_path.exists():
        console.print("[red]No lead CSV found! Run `python lead_finder.py` first to generate leads.[/red]")
        sys.exit(1)

    verify_leads_file(csv_path, auto_search=not args.no_auto_search)


if __name__ == "__main__":
    main()
