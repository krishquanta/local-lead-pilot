"""
Email Validation Service.
Performs multi-layer verification before sending cold emails:
1. RFC 5322 Syntax & Structure Check
2. Extension & False-Positive Filter (avoids images, scripts, version tags)
3. Disposable / Burner Email Detection
4. Domain DNS & Mail Exchange (MX) Record Verification
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
_CORE = _ROOT / "core"
for _p in [str(_ROOT), str(_CORE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


import re
import socket
import subprocess
from typing import Tuple, Optional, List

# Disposable / Temporary Email Domains
DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
    "throwawaymail.com", "sharklasers.com", "yopmail.com", "trashmail.com",
    "getairmail.com", "dispostable.com", "mytemp.email"
}

# Domains that are placeholders or system services
BLOCKED_DOMAINS = {
    "example.com", "example.org", "domain.com", "test.com", "email.com",
    "sentry.io", "wixpress.com", "schema.org", "w3.org", "cloudflare.com",
    "googleapis.com", "google.com", "github.com", "facebook.com", "instagram.com"
}

# Common invalid file extensions mistaken for email
INVALID_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".json", ".xml"
)

# Email syntax pattern
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

# Cache MX lookups in memory to avoid redundant DNS calls
_MX_CACHE = {}


def check_mx_records(domain: str) -> Tuple[bool, str]:
    """
    Queries DNS for Mail Exchange (MX) records.
    Returns (is_valid, reason).
    """
    domain = domain.lower().strip()
    if domain in _MX_CACHE:
        return _MX_CACHE[domain]

    # 1. Native Windows nslookup for MX records
    try:
        cmd = f"nslookup -type=mx {domain}"
        out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT, timeout=4)
        mx_records = re.findall(r"mail exchanger\s*=\s*(.*)", out, re.IGNORECASE)
        if mx_records:
            _MX_CACHE[domain] = (True, f"MX verified ({len(mx_records)} mail server(s))")
            return _MX_CACHE[domain]
    except Exception:
        pass

    # 2. Fallback: Check if domain has a valid host IP (A record)
    try:
        socket.gethostbyname(domain)
        _MX_CACHE[domain] = (True, "Host IP verified (A record fallback)")
        return _MX_CACHE[domain]
    except Exception as e:
        _MX_CACHE[domain] = (False, f"Domain has no active mail servers or DNS records ({e})")
        return _MX_CACHE[domain]


def validate_email_address(email: str) -> Tuple[bool, str]:
    """
    Comprehensive multi-stage email validation.
    Returns: (is_valid: bool, reason: str)
    """
    if not email or not isinstance(email, str):
        return False, "Empty or non-string email"

    email = email.strip()

    # 1. Length checks
    if len(email) < 6:
        return False, f"Email too short ({len(email)} chars)"
    if len(email) > 254:
        return False, f"Email exceeds RFC limit of 254 chars"

    # 2. Syntax check
    if not EMAIL_REGEX.match(email):
        return False, "Invalid email syntax format"

    # Split local part and domain
    parts = email.split("@")
    if len(parts) != 2:
        return False, "Email must contain exactly one '@'"

    local_part, domain = parts[0].lower(), parts[1].lower()

    if len(local_part) > 64:
        return False, "Local part exceeds 64 characters"

    if ".." in local_part or ".." in domain:
        return False, "Consecutive dots are not allowed"

    # 3. File extension false-positive check
    if any(domain.endswith(ext) for ext in INVALID_EXTENSIONS):
        return False, "Email ends with an asset file extension (false positive)"

    # 4. Check for library version numbers (e.g. bootstrap@5.3.0)
    if re.match(r"^\d", domain):
        return False, "Domain starts with a digit/version number"

    # 5. Check TLD validity
    domain_parts = domain.split(".")
    tld = domain_parts[-1]
    if len(tld) < 2 or not tld.isalpha():
        return False, f"Invalid top-level domain '.{tld}'"

    # 6. Blocklist / Disposable / Placeholder check
    if domain in BLOCKED_DOMAINS:
        return False, f"Domain '{domain}' is a placeholder or system domain"

    if domain in DISPOSABLE_DOMAINS:
        return False, f"Domain '{domain}' is a disposable/burner email service"

    # 7. DNS & MX Record check
    has_mx, mx_reason = check_mx_records(domain)
    if not has_mx:
        return False, f"DNS validation failed: {mx_reason}"

    return True, f"Valid email ({mx_reason})"


if __name__ == "__main__":
    # Test suite
    test_cases = [
        "info@covaimail.com",
        "sample.business@gmail.com",
        "fakeuser12345@thisdomaindoesntexistatall999.com",
        "image.png@domain.com",
        "bootstrap@5.3.0",
        "user@mailinator.com",
        "user@example.com",
        "invalid..syntax@gmail.com",
        "test@gmail.com"
    ]
    print("--- Running Email Validator Test Suite ---")
    for t in test_cases:
        valid, msg = validate_email_address(t)
        mark = "PASS" if valid else "FAIL"
        print(f"[{mark}] {t:<45} -> {msg}")
