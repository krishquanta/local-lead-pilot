"""
Social Media and Gmail Discovery Engine for Local Businesses.
Searches for official Instagram / Facebook profiles and Gmail / business email addresses.
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
_CORE = _ROOT / "core"
for _p in [str(_ROOT), str(_CORE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


import re
import base64
import urllib.parse
from typing import Dict, Tuple, Optional
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

IGNORED_SOCIAL_PATHS = [
    '/login', '/explore', '/directory', '/reels', '/p/', '/sharer',
    '/help', '/recover', 'facebook.com/public', 'facebook.com/pages'
]

EMAIL_EXCLUDE = [
    'example', 'bing', 'microsoft', 'user', 'domain', 'support',
    'feedback', 'sentry', 'wixpress', 'duckduckgo', 'google', 'apple'
]


def decode_bing_url(u: str) -> str:
    """Decodes Bing redirect link containing base64 destination."""
    if "bing.com/ck" in u:
        match = re.search(r'u=a1([a-zA-Z0-9_-]+)', u)
        if match:
            b64 = match.group(1)
            b64 += '=' * ((4 - len(b64) % 4) % 4)
            try:
                return base64.urlsafe_b64decode(b64).decode('utf-8', errors='ignore')
            except Exception:
                pass
    return u


def is_relevant_social(url: str, full_text: str, name_tokens: list) -> bool:
    """Ensures social profile is related to the business and not a celebrity or random page."""
    low_url = url.lower()
    low_text = full_text.lower()
    
    # Must match at least one significant business name token
    token_match = any(tok in low_url or tok in low_text for tok in name_tokens)
    return token_match


def search_socials_and_gmail(name: str, city: str, category: str = "") -> Dict[str, str]:
    """
    Searches online for:
    1. Social profile: Instagram or Facebook
    2. Gmail address: [username]@gmail.com or other valid email

    Returns:
    {
        "social_url": "...",
        "gmail": "...",
        "verification_status": "HAS SOCIALS BUT NO WEBSITE" | "NO WEBSITE OR SOCIALS"
    }
    """
    social_url = ""
    gmail = ""
    
    # Extract significant keywords from business name
    stop_words = {"the", "and", "&", "in", "at", "for", "of", "a", "an", "tamil", "nadu", "pvt", "ltd"}
    name_tokens = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', name) if w.lower() not in stop_words]
    if category:
        cat_tokens = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', category) if w.lower() not in stop_words]
        name_tokens.extend(cat_tokens)

    # Query 1: Business + City + Instagram + Facebook
    q1 = f'"{name}" {city}'
    url1 = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(q1)

    try:
        r = requests.get(url1, headers=HEADERS, timeout=6)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for item in soup.select('li.b_algo'):
                title = item.find('h2').get_text() if item.find('h2') else ""
                snippet = item.select_one('.b_caption p').get_text() if item.select_one('.b_caption p') else ""
                full_item_text = f"{title} {snippet}"

                a = item.find('a', href=True)
                if a:
                    real_href = decode_bing_url(a['href'])
                    low_href = real_href.lower()

                    # Check for Instagram / Facebook
                    if ("instagram.com/" in low_href or "facebook.com/" in low_href) and not social_url:
                        if not any(ign in low_href for ign in IGNORED_SOCIAL_PATHS):
                            if is_relevant_social(real_href, full_item_text, name_tokens):
                                social_url = real_href.split('?')[0].rstrip('/')

                # Check for Gmail
                if not gmail:
                    gm = re.findall(r'[a-zA-Z0-9._%+-]+@gmail\.com', full_item_text, re.IGNORECASE)
                    valid_gm = [m.lower() for m in gm if not any(x in m.lower() for x in EMAIL_EXCLUDE)]
                    if valid_gm:
                        gmail = valid_gm[0]
                    else:
                        all_em = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_item_text, re.IGNORECASE)
                        valid_em = [m.lower() for m in all_em if not any(x in m.lower() for x in EMAIL_EXCLUDE)]
                        if valid_em:
                            gmail = valid_em[0]
    except Exception:
        pass

    # Query 2: Targeted Instagram search if not found
    if not social_url:
        try:
            q2 = f'{name} {city} instagram'
            url2 = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(q2)
            r2 = requests.get(url2, headers=HEADERS, timeout=5)
            if r2.status_code == 200:
                soup2 = BeautifulSoup(r2.text, 'html.parser')
                for item in soup2.select('li.b_algo'):
                    title = item.find('h2').get_text() if item.find('h2') else ""
                    snippet = item.select_one('.b_caption p').get_text() if item.select_one('.b_caption p') else ""
                    full_item_text = f"{title} {snippet}"

                    a = item.find('a', href=True)
                    if a:
                        real_href = decode_bing_url(a['href'])
                        low_href = real_href.lower()
                        if "instagram.com/" in low_href and not any(ign in low_href for ign in IGNORED_SOCIAL_PATHS):
                            if is_relevant_social(real_href, full_item_text, name_tokens):
                                social_url = real_href.split('?')[0].rstrip('/')
                                break

                    if not gmail:
                        gm = re.findall(r'[a-zA-Z0-9._%+-]+@gmail\.com', full_item_text, re.IGNORECASE)
                        valid_gm = [m.lower() for m in gm if not any(x in m.lower() for x in EMAIL_EXCLUDE)]
                        if valid_gm:
                            gmail = valid_gm[0]
        except Exception:
            pass

    # Query 3: Targeted Gmail search if still no email found
    if not gmail:
        try:
            q3 = f'"{name}" {city} gmail'
            url3 = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(q3)
            r3 = requests.get(url3, headers=HEADERS, timeout=5)
            if r3.status_code == 200:
                text3 = BeautifulSoup(r3.text, 'html.parser').get_text()
                gm3 = re.findall(r'[a-zA-Z0-9._%+-]+@gmail\.com', text3, re.IGNORECASE)
                valid_gm3 = [m.lower() for m in gm3 if not any(x in m.lower() for x in EMAIL_EXCLUDE)]
                if valid_gm3:
                    gmail = valid_gm3[0]
        except Exception:
            pass

    status = "HAS SOCIALS BUT NO WEBSITE" if social_url else "NO WEBSITE OR SOCIALS"

    return {
        "social_url": social_url,
        "gmail": gmail,
        "verification_status": status
    }
