"""
Leads Command Center Server:
Serves the web dashboard and provides live API endpoints to read and save leads CSVs.
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
import json
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading
import time

BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "leads_output"
PORT = 8521


def get_latest_csv() -> Path:
    """Find the most comprehensive or recently modified CSV in leads_output/."""
    master = OUTPUT_DIR / "master_scraped_leads.csv"
    continuous = OUTPUT_DIR / "tamil_nadu_continuous_leads.csv"
    if master.exists() and master.stat().st_size > 1000:
        return master
    if continuous.exists() and continuous.stat().st_size > 1000:
        return continuous
    csv_files = sorted(OUTPUT_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return csv_files[0] if csv_files else None


def read_latest_leads() -> list:
    latest = get_latest_csv()
    if not latest or not latest.exists():
        return []
    leads = []
    with open(latest, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            leads.append(row)
    return leads


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        # Redirect root to viewer.html
        if self.path in ("/", ""):
            self.send_response(302)
            self.send_header("Location", "/viewer.html")
            self.end_headers()
            return

        # API endpoint for latest leads
        if self.path.startswith("/api/latest-leads"):
            leads = read_latest_leads()
            latest_file = get_latest_csv()
            filename = latest_file.name if latest_file else "None"
            response_data = {
                "file": filename,
                "leads": leads
            }
            body = json.dumps(response_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # API endpoint for funnel stats
        if self.path.startswith("/api/funnel-stats"):
            try:
                from conversion_tracker import get_funnel_counts, STAGES, STAGE_ICONS
                counts = get_funnel_counts()
                total = sum(counts.values())
                response_data = {
                    "total": total,
                    "counts": counts,
                    "stages": STAGES,
                    "icons": STAGE_ICONS
                }
            except Exception as e:
                response_data = {"error": str(e)}
            body = json.dumps(response_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # API endpoint for daily summary
        if self.path.startswith("/api/daily-summary"):
            try:
                from rate_limiter import get_status_summary
                rl = get_status_summary()
            except Exception:
                rl = {}
            body = json.dumps(rl).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Fallback to serving static files (viewer.html, etc.)
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/update-stage"):
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length)
            try:
                data = json.loads(post_body.decode("utf-8"))
                identifier = data.get("identifier", "").strip()
                stage = data.get("stage", "").strip()
                from conversion_tracker import update_lead_stage
                updated = update_lead_stage(identifier, stage)

                # Re-sync leads_data.js
                latest_csv = get_latest_csv()
                if latest_csv:
                    all_leads = read_latest_leads()
                    js_file = BASE_DIR / "leads_data.js"
                    with open(js_file, mode="w", encoding="utf-8") as f:
                        f.write("window.EMBEDDED_LEADS = " + json.dumps(all_leads, indent=2, ensure_ascii=False) + ";\n")

                resp = json.dumps({"status": "success", "updated": updated, "stage": stage}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                err = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(err)
            return

        if self.path.startswith("/api/save-leads"):
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length)
            try:
                data = json.loads(post_body.decode("utf-8"))
                leads = data.get("leads", [])
                latest_csv = get_latest_csv()
                if latest_csv and leads:
                    fieldnames = list(leads[0].keys())
                    with open(latest_csv, mode="w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(leads)
                
                resp = json.dumps({"status": "success", "count": len(leads)}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                err = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(err)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        # Quiet log to keep terminal clean
        pass


def main():
    print(f"========================================================")
    print(f"  Tamil Nadu Leads Command Center")
    print(f"========================================================")
    print(f"  Local Dashboard: http://localhost:{PORT}")
    print(f"  Viewer Page:     http://localhost:{PORT}/viewer.html")
    print(f"========================================================\n")

    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Dashboard server stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
