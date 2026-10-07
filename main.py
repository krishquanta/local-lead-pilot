"""
⚡ Tamil Nadu Local Business Outreach Engine - Master CLI
Unified command center for lead generation, verification, scraping, and automated outreach.
"""
import sys
import os
from pathlib import Path

# Ensure project root and core/ are in sys.path
BASE_DIR = Path(__file__).parent.resolve()
CORE_DIR = BASE_DIR / "core"
for p in [str(CORE_DIR), str(BASE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def print_banner():
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console(force_terminal=True, legacy_windows=False)
        banner = (
            "[bold cyan]⚡ Tamil Nadu Local Business Outreach Command Center[/bold cyan]\n"
            "[dim]Lead Generation, Verification, and Safe Anti-Ban Outreach Pipeline[/dim]"
        )
        console.print(Panel(banner, border_style="cyan"))

        table = Table(title="Available Subcommands", border_style="dim")
        table.add_column("Command", style="bold green", no_wrap=True)
        table.add_column("Aliases", style="yellow")
        table.add_column("Description", style="white")

        table.add_row("whatsapp", "wa", "Send WhatsApp outreach with human typing & 48h nudges")
        table.add_row("mailer", "email", "Send automated cold emails with safe pacing (Zero approval)")
        table.add_row("autopilot", "auto", "Continuous autonomous scrape + filter + WhatsApp cycle")
        table.add_row("scraper", "scrape", "Continuous Google Maps & website discovery scraper")
        table.add_row("leads", "find", "Search shops by city & category (e.g. --city Coimbatore --category salons)")
        table.add_row("research", "gmail", "Deep-scan Instagram/Facebook bios and search engines for Gmails")
        table.add_row("summary", "stats", "View today's operations KPIs and channel safety quotas")
        table.add_row("funnel", "pipeline", "Inspect lead conversion funnel distribution (Discovered -> Client)")
        table.add_row("ab", "tester", "View A/B message variant reply & conversion leaderboard")
        table.add_row("verify", "check", "Interactive single-key terminal lead verification CLI")
        table.add_row("dashboard", "ui", "Start local web dashboard server (http://localhost:8521)")
        table.add_row("config-email", "setup", "Interactive Gmail App Password setup & SMTP test")

        console.print(table)
        console.print("\n[bold]Quick Examples:[/bold]")
        console.print("  [cyan]python main.py summary[/cyan]                     - View daily operations summary")
        console.print("  [cyan]python main.py whatsapp --dry-run[/cyan]           - Preview WhatsApp outreach without sending")
        console.print("  [cyan]python main.py whatsapp --limit 10[/cyan]          - Send WhatsApp messages (10 shops)")
        console.print("  [cyan]python main.py whatsapp --follow-up[/cyan]         - Send 48h follow-up nudges")
        console.print("  [cyan]python main.py mailer --watch[/cyan]               - Dispatch cold emails to discovered Gmails")
        console.print("  [cyan]python main.py dashboard[/cyan]                    - Launch web command center\n")
    except Exception:
        print("Usage: python main.py <command> [options]")
        print("Commands: whatsapp, mailer, autopilot, scraper, leads, research, summary, funnel, ab, verify, dashboard, config-email")


def dispatch():
    if len(sys.argv) < 2 or sys.argv[1].lower() in ("-h", "--help", "help"):
        print_banner()
        return

    cmd = sys.argv[1].lower().strip()
    sub_args = sys.argv[2:]

    # Map aliases to canonical commands
    alias_map = {
        "wa": "whatsapp",
        "email": "mailer",
        "auto": "autopilot",
        "scrape": "scraper",
        "find": "leads",
        "gmail": "research",
        "stats": "summary",
        "pipeline": "funnel",
        "tester": "ab",
        "check": "verify",
        "ui": "dashboard",
        "web": "dashboard",
        "setup": "config-email",
        "config": "config-email",
    }
    canonical = alias_map.get(cmd, cmd)

    if canonical == "whatsapp":
        import whatsapp_sender
        sys.argv = ["whatsapp_sender.py"] + sub_args
        whatsapp_sender.main()

    elif canonical == "mailer":
        import send_cold_emails
        sys.argv = ["send_cold_emails.py"] + sub_args
        send_cold_emails.main()

    elif canonical == "autopilot":
        import auto_pilot
        sys.argv = ["auto_pilot.py"] + sub_args
        auto_pilot.main()

    elif canonical == "scraper":
        import continuous_scraper
        sys.argv = ["continuous_scraper.py"] + sub_args
        continuous_scraper.main()

    elif canonical == "leads":
        import lead_finder
        sys.argv = ["lead_finder.py"] + sub_args
        lead_finder.main()

    elif canonical == "research":
        import research_all_shops_for_gmail
        sys.argv = ["research_all_shops_for_gmail.py"] + sub_args
        research_all_shops_for_gmail.main()

    elif canonical == "summary":
        import daily_summary
        sys.argv = ["daily_summary.py"] + sub_args
        daily_summary.main()

    elif canonical == "funnel":
        import conversion_tracker
        sys.argv = ["conversion_tracker.py", "--funnel"] + sub_args
        conversion_tracker.main()

    elif canonical == "ab":
        import message_ab_tester
        sys.argv = ["message_ab_tester.py"] + sub_args
        message_ab_tester.main()

    elif canonical == "verify":
        import verifier
        sys.argv = ["verifier.py"] + sub_args
        verifier.main()

    elif canonical == "dashboard":
        import dashboard
        sys.argv = ["dashboard.py"] + sub_args
        dashboard.main()

    elif canonical == "config-email":
        import configure_email
        sys.argv = ["configure_email.py"] + sub_args
        configure_email.main()

    else:
        print(f"[!] Unknown command: '{cmd}'")
        print("Run `python main.py --help` to see available commands.")
        sys.exit(1)


if __name__ == "__main__":
    dispatch()
