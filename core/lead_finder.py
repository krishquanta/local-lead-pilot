"""
Lead Finder: Searches Google Places API, applies qualification criteria,
deduplicates results, calculates lead scores, and exports to CSV & Excel.
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
import csv
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import (
    GOOGLE_PLACES_API_KEY,
    DEFAULT_CRITERIA,
    OUTPUT_DIR,
    TAMIL_NADU_TARGETS,
)
from places_client import GooglePlacesClient

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(force_terminal=True, legacy_windows=False)


def calculate_lead_score(place: Dict[str, Any]) -> Tuple[int, str]:
    """
    Calculate an actionable lead score (0 - 100) based on local authority,
    review volume, rating, and contactability.
    """
    reviews = place.get("review_count", 0)
    rating = place.get("rating", 0.0)
    has_phone = bool(place.get("phone"))
    has_website = bool(place.get("website"))

    score = 0

    # 1. Review volume weight (up to 50 pts)
    # High review count = established business with cash flow and serious local clientele
    if reviews >= 500:
        score += 50
    elif reviews >= 200:
        score += 38
    elif reviews >= 100:
        score += 26
    elif reviews >= 50:
        score += 15
    else:
        score += 5

    # 2. Rating strength (up to 30 pts)
    if rating >= 4.8:
        score += 30
    elif rating >= 4.6:
        score += 22
    elif rating >= 4.5:
        score += 14
    else:
        score += 5

    # 3. Direct contactability (10 pts)
    if has_phone:
        score += 10

    # 4. Digital gap opportunity (10 pts)
    if not has_website:
        score += 10

    # Determine lead priority tier
    if reviews >= 500:
        priority = "🔥 HOT (500+ Reviews)"
    elif reviews >= 150 and rating >= 4.6:
        priority = "⭐ HIGH PRIORITY"
    elif reviews >= 50:
        priority = "✅ QUALIFIED"
    else:
        priority = "🌱 LOW VOLUME"

    return min(100, score), priority


def is_qualified_lead(place: Dict[str, Any], criteria: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Applies strict lead filters matching the user's criteria:
    - Business status == OPERATIONAL
    - Rating >= min_rating
    - Review count >= min_reviews
    - Website is missing/empty (if only_no_website=True)
    - Phone number present (if require_phone=True)
    """
    if criteria.get("operational_only", True):
        status = place.get("business_status", "OPERATIONAL")
        if status != "OPERATIONAL":
            return False, f"Not operational ({status})"

    rating = place.get("rating", 0.0)
    min_rating = criteria.get("min_rating", 4.5)
    if rating < min_rating:
        return False, f"Rating {rating} < {min_rating}"

    reviews = place.get("review_count", 0)
    min_reviews = criteria.get("min_reviews", 50)
    if reviews < min_reviews:
        return False, f"Reviews {reviews} < {min_reviews}"

    website = place.get("website", "").strip()
    if criteria.get("only_no_website", True) and website:
        return False, f"Has existing website: {website}"

    phone = place.get("phone", "").strip()
    if criteria.get("require_phone", False) and not phone:
        return False, "Missing phone number"

    return True, "Qualified"


def export_to_csv(leads: List[Dict[str, Any]], filepath: Path) -> Path:
    """Export qualified leads into an outreach-ready CSV file."""
    fieldnames = [
        "Business Name",
        "Category",
        "City",
        "Rating",
        "Review Count",
        "Phone",
        "Address",
        "Google Maps URL",
        "Website",
        "Lead Score",
        "Priority Tier",
        "Verification Status",
        "Verification Notes",
        "Google Place ID"
    ]

    with open(filepath, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for lead in leads:
            writer.writerow({
                "Business Name": lead.get("name", ""),
                "Category": lead.get("category", ""),
                "City": lead.get("city", ""),
                "Rating": lead.get("rating", 0.0),
                "Review Count": lead.get("review_count", 0),
                "Phone": lead.get("phone", ""),
                "Address": lead.get("address", ""),
                "Google Maps URL": lead.get("google_maps_url", ""),
                "Website": lead.get("website", "") or "NO WEBSITE LISTED",
                "Lead Score": lead.get("lead_score", 0),
                "Priority Tier": lead.get("priority", ""),
                "Verification Status": lead.get("verification_status", "PENDING VERIFICATION"),
                "Verification Notes": lead.get("verification_notes", ""),
                "Google Place ID": lead.get("place_id", "")
            })

    return filepath


def export_to_excel(leads: List[Dict[str, Any]], filepath: Path) -> Path:
    """Optional styled Excel export if xlsxwriter is available."""
    try:
        import xlsxwriter
        workbook = xlsxwriter.Workbook(str(filepath))
        worksheet = workbook.add_worksheet("Leads")

        # Formats
        header_format = workbook.add_format({
            "bold": True,
            "font_color": "white",
            "bg_color": "#1A73E8",
            "border": 1,
            "align": "center",
            "valign": "vcenter"
        })
        cell_format = workbook.add_format({"border": 1, "valign": "vcenter"})
        score_format = workbook.add_format({"border": 1, "bold": True, "align": "center"})
        highlight_format = workbook.add_format({"border": 1, "bold": True, "bg_color": "#E6F4EA", "font_color": "#137333"})

        headers = [
            ("Business Name", 28),
            ("Category", 20),
            ("City", 14),
            ("Rating", 10),
            ("Review Count", 14),
            ("Phone", 18),
            ("Address", 35),
            ("Google Maps URL", 28),
            ("Website Status", 18),
            ("Lead Score", 12),
            ("Priority Tier", 22),
            ("Verification Status", 22),
            ("Verification Notes", 25)
        ]

        for col_idx, (col_name, width) in enumerate(headers):
            worksheet.write(0, col_idx, col_name, header_format)
            worksheet.set_column(col_idx, col_idx, width)

        for row_idx, lead in enumerate(leads, start=1):
            worksheet.write(row_idx, 0, lead.get("name", ""), cell_format)
            worksheet.write(row_idx, 1, lead.get("category", ""), cell_format)
            worksheet.write(row_idx, 2, lead.get("city", ""), cell_format)
            worksheet.write(row_idx, 3, lead.get("rating", 0.0), cell_format)
            worksheet.write(row_idx, 4, lead.get("review_count", 0), cell_format)
            worksheet.write(row_idx, 5, lead.get("phone", ""), cell_format)
            worksheet.write(row_idx, 6, lead.get("address", ""), cell_format)
            worksheet.write(row_idx, 7, lead.get("google_maps_url", ""), cell_format)
            worksheet.write(row_idx, 8, lead.get("website", "") or "NO WEBSITE LISTED", cell_format)
            worksheet.write(row_idx, 9, lead.get("lead_score", 0), score_format)
            worksheet.write(row_idx, 10, lead.get("priority", ""), highlight_format)
            worksheet.write(row_idx, 11, lead.get("verification_status", "PENDING VERIFICATION"), cell_format)
            worksheet.write(row_idx, 12, lead.get("verification_notes", ""), cell_format)

        worksheet.autofilter(0, 0, len(leads), len(headers) - 1)
        worksheet.freeze_panes(1, 0)
        workbook.close()
        return filepath
    except Exception as e:
        console.print(f"[yellow]Notice: Excel export skipped ({e}), CSV output is intact.[/yellow]")
        return filepath


def run_lead_pipeline(
    queries: List[Tuple[str, str]],
    api_key: str,
    criteria: Dict[str, Any],
    engine: str = "docker",
    output_filename: str = None
) -> Tuple[List[Dict[str, Any]], Path, Path]:
    """
    Executes the complete lead discovery pipeline:
    1. Query Google Places (via Docker Scraper or Official API) per (City, Category)
    2. Deduplicate listings across queries
    3. Filter by rating, review count, missing website
    4. Compute lead scores & priorities
    5. Sort leads by priority/reviews
    6. Export clean CSV and Excel files
    """
    client = GooglePlacesClient(
        api_key=api_key,
        is_demo=(engine == "demo"),
        use_docker=(engine == "docker")
    )

    seen_place_ids: Set[str] = set()
    qualified_leads: List[Dict[str, Any]] = []
    total_inspected = 0
    filtered_out_stats = {"has_website": 0, "low_rating": 0, "low_reviews": 0, "other": 0}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        overall_task = progress.add_task("[cyan]Searching Google Places...", total=len(queries))

        for city, category in queries:
            query_str = f"{category} in {city}, Tamil Nadu"
            progress.update(overall_task, description=f"[cyan]Searching: [bold]{query_str}[/bold]")

            raw_places = client.search_places(
                query=query_str,
                max_results=criteria.get("max_results_per_query", 60)
            )

            for place in raw_places:
                place_id = place.get("place_id") or f"{place['name']}_{city}"
                if place_id in seen_place_ids:
                    continue
                seen_place_ids.add(place_id)
                total_inspected += 1

                # Tag city
                place["city"] = city

                # Check qualification
                qualified, reason = is_qualified_lead(place, criteria)
                if not qualified:
                    if "existing website" in reason:
                        filtered_out_stats["has_website"] += 1
                    elif "Rating" in reason:
                        filtered_out_stats["low_rating"] += 1
                    elif "Reviews" in reason:
                        filtered_out_stats["low_reviews"] += 1
                    else:
                        filtered_out_stats["other"] += 1
                    continue

                # Lead scoring & priority
                score, priority = calculate_lead_score(place)
                place["lead_score"] = score
                place["priority"] = priority
                place["verification_status"] = "PENDING VERIFICATION"
                place["verification_notes"] = ""

                qualified_leads.append(place)

            progress.advance(overall_task)

    # Sort leads descending by Review Count (and then score)
    qualified_leads.sort(key=lambda x: (x.get("review_count", 0), x.get("lead_score", 0)), reverse=True)

    # Determine output file paths
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not output_filename:
        if len(queries) == 1:
            city, cat = queries[0]
            clean_name = f"{city.lower()}_{cat.lower().replace(' ', '_')}_leads_{timestamp}"
        else:
            clean_name = f"tamil_nadu_leads_{timestamp}"
    else:
        clean_name = output_filename

    csv_path = OUTPUT_DIR / f"{clean_name}.csv"
    xlsx_path = OUTPUT_DIR / f"{clean_name}.xlsx"

    export_to_csv(qualified_leads, csv_path)
    export_to_excel(qualified_leads, xlsx_path)

    # Display results table
    display_results_summary(qualified_leads, total_inspected, filtered_out_stats, csv_path)

    return qualified_leads, csv_path, xlsx_path


def display_results_summary(
    leads: List[Dict[str, Any]],
    total_inspected: int,
    filtered_stats: Dict[str, int],
    csv_path: Path
):
    """Render a terminal summary and preview table using rich."""
    console.print()
    console.print(Panel(
        f"[bold green]✔ Lead Generation Run Complete![/bold green]\n"
        f"Total Inspected: [bold]{total_inspected}[/bold] | Qualified Leads Found: [bold yellow]{len(leads)}[/bold yellow]\n"
        f"Filtered Out: [dim]{filtered_stats['has_website']} had websites, {filtered_stats['low_reviews']} under review threshold, {filtered_stats['low_rating']} under rating threshold[/dim]\n"
        f"Output CSV: [cyan]{csv_path}[/cyan]",
        title="[bold blue]Summary Report[/bold blue]",
        border_style="green"
    ))

    if not leads:
        console.print("[yellow]No leads matched the specified criteria. Try lowering the review/rating threshold or changing category.[/yellow]")
        return

    table = Table(title=f"Top Qualified Leads (Sorted by Review Count)", show_lines=True)
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("Business Name", style="bold white", width=30)
    table.add_column("City", style="cyan", width=12)
    table.add_column("Category", style="magenta", width=18)
    table.add_column("Rating", justify="center", style="yellow", width=8)
    table.add_column("Reviews", justify="right", style="green", width=10)
    table.add_column("Phone", style="blue", width=16)
    table.add_column("Website", justify="center", width=10)
    table.add_column("Score", justify="center", style="bold yellow", width=8)
    table.add_column("Priority", style="bold red", width=22)

    for idx, lead in enumerate(leads[:15], start=1):
        has_phone = "✓" if lead.get("phone") else "❌"
        website_indicator = "❌ None" if not lead.get("website") else "✓ Has URL"

        table.add_row(
            str(idx),
            lead.get("name", "")[:28],
            lead.get("city", ""),
            lead.get("category", "")[:16],
            f"{lead.get('rating', 0.0):.1f}★",
            f"{lead.get('review_count', 0):,}",
            lead.get("phone", "N/A") or "N/A",
            website_indicator,
            str(lead.get("lead_score", 0)),
            lead.get("priority", "")
        )

    console.print(table)
    if len(leads) > 15:
        console.print(f"[dim]... and {len(leads) - 15} more leads saved in CSV.[/dim]\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Google Places Lead Generator for Web Design Outreach in Tamil Nadu"
    )
    parser.add_argument("--city", type=str, help="Target city (e.g. Coimbatore, Chennai, Trichy)")
    parser.add_argument("--category", type=str, help="Target category (e.g. salons, travel agencies, restaurants)")
    parser.add_argument("--preset", type=str, choices=["tamil_nadu"], help="Run all curated Tamil Nadu cities & categories")
    parser.add_argument("--engine", type=str, choices=["docker", "google", "demo"], default=None, help="Scraper engine: 'docker' (Free, No Credit Card), 'google', or 'demo'")
    parser.add_argument("--min-rating", type=float, default=DEFAULT_CRITERIA["min_rating"], help="Minimum Google Star Rating (default: 4.5)")
    parser.add_argument("--min-reviews", type=int, default=DEFAULT_CRITERIA["min_reviews"], help="Minimum Google Review Count (default: 50)")
    parser.add_argument("--all-websites", action="store_true", help="Include businesses that already have a website (default: False)")
    parser.add_argument("--require-phone", action="store_true", help="Only keep leads with a phone number (default: False)")
    parser.add_argument("--demo", action="store_true", help="Run in mock/demo mode without requiring Docker or API key")
    parser.add_argument("--api-key", type=str, default=GOOGLE_PLACES_API_KEY, help="Google Places API Key (if using engine=google)")
    parser.add_argument("--output", type=str, help="Custom output filename prefix")
    return parser.parse_args()


def main():
    args = parse_args()

    # Determine engine (docker is default because no credit card required)
    if args.demo:
        engine = "demo"
    elif args.engine:
        engine = args.engine
    elif args.api_key:
        engine = "google"
    else:
        engine = "docker"

    if engine == "docker":
        console.print(Panel(
            "[bold cyan]Selected Engine: Conor's Local Docker Scraper[/bold cyan]\n"
            "• 100% Free Google Maps Scraping (No Credit Card or Google API Key required)\n"
            "• Endpoint: [bold]http://localhost:8001[/bold]\n"
            "[dim]Tip: Make sure Docker Desktop is open and run `run.bat start-docker` or `cd gmaps_scraper && docker compose up -d`[/dim]",
            title="Engine: Conor's Docker Scraper",
            border_style="cyan"
        ))
    elif engine == "google":
        console.print(Panel(
            "[bold green]Selected Engine: Official Google Places API[/bold green]",
            title="Engine: Google Places API",
            border_style="green"
        ))
    else:
        console.print(Panel(
            "[bold yellow]Selected Engine: Demo / Offline Mode[/bold yellow]\n"
            "Using realistic Tamil Nadu business samples for testing.",
            title="Engine: Demo",
            border_style="yellow"
        ))

    criteria = {
        "min_rating": args.min_rating,
        "min_reviews": args.min_reviews,
        "only_no_website": not args.all_websites,
        "require_phone": args.require_phone,
        "operational_only": True,
        "max_results_per_query": DEFAULT_CRITERIA["max_results_per_query"]
    }

    # Determine query list
    queries: List[Tuple[str, str]] = []

    if args.preset == "tamil_nadu":
        console.print("[bold cyan]Selected Preset: Curated Tamil Nadu Target Matrix[/bold cyan]")
        for city, categories in TAMIL_NADU_TARGETS.items():
            for cat in categories:
                queries.append((city, cat))
    elif args.city and args.category:
        queries.append((args.city, args.category))
    elif args.city and not args.category:
        cats = TAMIL_NADU_TARGETS.get(args.city, ["restaurants", "meat shops", "bakeries", "sweet stalls"])
        for cat in cats:
            queries.append((args.city, cat))
    else:
        console.print("[bold]Defaulting to: [cyan]Coimbatore - restaurants[/cyan] (Use --help to view all options)[/bold]")
        queries.append(("Coimbatore", "restaurants"))

    console.print(f"[dim]Total search queries to execute: {len(queries)}[/dim]\n")
    run_lead_pipeline(
        queries=queries,
        api_key=args.api_key.strip(),
        criteria=criteria,
        engine=engine,
        output_filename=args.output
    )


if __name__ == "__main__":
    main()
