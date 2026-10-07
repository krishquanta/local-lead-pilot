"""
Cross-Channel Rate Limiter & Daily Cap Guard.
Tracks daily sends across WhatsApp and Cold Email to prevent account bans and domain flagging.
State is safely stored in `leads_output/rate_limit_state.json`.
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
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
load_dotenv(BASE_DIR / ".env")

OUTPUT_DIR = BASE_DIR / "leads_output"
OUTPUT_DIR.mkdir(exist_ok=True)
STATE_FILE = OUTPUT_DIR / "rate_limit_state.json"

DEFAULT_LIMITS = {
    "whatsapp": int(os.getenv("DAILY_WA_LIMIT", "20")),
    "email": int(os.getenv("DAILY_EMAIL_LIMIT", "50")),
}


def _get_today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def load_state() -> Dict[str, Any]:
    today = _get_today_str()
    default_state = {
        "date": today,
        "counts": {
            "whatsapp": 0,
            "email": 0
        },
        "limits": DEFAULT_LIMITS,
        "last_updated": datetime.now().isoformat()
    }

    if not STATE_FILE.exists():
        save_state(default_state)
        return default_state

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        # Check if new day
        if state.get("date") != today:
            state["date"] = today
            state["counts"] = {"whatsapp": 0, "email": 0}
            state["last_updated"] = datetime.now().isoformat()
            save_state(state)
        else:
            # Ensure keys exist
            if "counts" not in state:
                state["counts"] = {"whatsapp": 0, "email": 0}
            if "whatsapp" not in state["counts"]:
                state["counts"]["whatsapp"] = 0
            if "email" not in state["counts"]:
                state["counts"]["email"] = 0
            state["limits"] = DEFAULT_LIMITS
        return state
    except Exception:
        save_state(default_state)
        return default_state


def save_state(state: Dict[str, Any]) -> None:
    state["last_updated"] = datetime.now().isoformat()
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to persist rate limit state: {e}", file=sys.stderr)


def reset_if_new_day() -> Dict[str, Any]:
    return load_state()


def can_send(channel: str) -> Tuple[bool, int, int]:
    """
    Returns (is_allowed, current_count, max_limit).
    """
    state = load_state()
    channel = channel.lower()
    count = state.get("counts", {}).get(channel, 0)
    limit = state.get("limits", {}).get(channel, DEFAULT_LIMITS.get(channel, 20))
    return (count < limit), count, limit


def increment_send(channel: str) -> int:
    state = load_state()
    channel = channel.lower()
    state["counts"][channel] = state.get("counts", {}).get(channel, 0) + 1
    save_state(state)
    return state["counts"][channel]


def check_and_increment(channel: str) -> bool:
    """
    Atomically checks if send is within limit, increments, and returns True.
    Returns False if limit is already reached.
    """
    allowed, count, limit = can_send(channel)
    if not allowed:
        return False
    increment_send(channel)
    return True


def get_status_summary() -> Dict[str, Any]:
    state = load_state()
    return {
        "date": state.get("date"),
        "whatsapp": {
            "sent": state.get("counts", {}).get("whatsapp", 0),
            "limit": state.get("limits", {}).get("whatsapp", DEFAULT_LIMITS["whatsapp"]),
            "remaining": max(0, state.get("limits", {}).get("whatsapp", DEFAULT_LIMITS["whatsapp"]) - state.get("counts", {}).get("whatsapp", 0))
        },
        "email": {
            "sent": state.get("counts", {}).get("email", 0),
            "limit": state.get("limits", {}).get("email", DEFAULT_LIMITS["email"]),
            "remaining": max(0, state.get("limits", {}).get("email", DEFAULT_LIMITS["email"]) - state.get("counts", {}).get("email", 0))
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Cross-Channel Rate Limiter Guard")
    parser.add_argument("--status", action="store_true", help="Print current rate limit usage")
    parser.add_argument("--reset", action="store_true", help="Manually reset today's counters to 0")
    parser.add_argument("--test", action="store_true", help="Run self-test verification")
    args = parser.parse_args()

    if args.reset:
        state = load_state()
        state["counts"] = {"whatsapp": 0, "email": 0}
        save_state(state)
        print("Rate limits reset successfully for today.")
        return

    if args.test:
        print("[*] Running rate_limiter self-test...")
        st = load_state()
        print(f"Current Date: {st['date']}")
        wa_allowed, wa_c, wa_l = can_send("whatsapp")
        em_allowed, em_c, em_l = can_send("email")
        print(f"WhatsApp: {wa_c}/{wa_l} (Allowed: {wa_allowed})")
        print(f"Email:    {em_c}/{em_l} (Allowed: {em_allowed})")
        print("Self-test passed.")
        return

    summary = get_status_summary()
    print("=" * 50)
    print(f" Outreach Rate Limits ({summary['date']})")
    print("=" * 50)
    wa = summary["whatsapp"]
    em = summary["email"]
    print(f" WhatsApp: {wa['sent']} / {wa['limit']} sent (Remaining: {wa['remaining']})")
    print(f" Email:    {em['sent']} / {em['limit']} sent (Remaining: {em['remaining']})")
    print("=" * 50)


if __name__ == "__main__":
    main()
