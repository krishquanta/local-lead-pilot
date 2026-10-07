"""
Outreach Message Generator:
Creates natural, conversational, human-written messages (WhatsApp, Cold Call, and Email)
tailored for Tamil Nadu local business owners without sounding like automated spam or AI bots.
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
_CORE = _ROOT / "core"
for _p in [str(_ROOT), str(_CORE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


import re
from typing import Dict, Any

def clean_business_name(name: str) -> str:
    """Removes trailing city suffixes, branches, and corporate tags so the name sounds natural."""
    if not name:
        return "there"
    # Remove common suffixes like "- Coimbatore", ", Trichy", "| Chennai", "Pvt Ltd", etc.
    clean = re.sub(r"\s*[-–—|•,]\s*(Coimbatore|Chennai|Trichy|Madurai|Salem|Tiruppur|Erode|Vellore|Tirunelveli|Tamil Nadu|TN|Branch|Head Office|Main Branch).*$", "", name, flags=re.IGNORECASE)
    clean = re.sub(r"\s*[-–—|•]\s*(Makeup Artist|Salon|Restaurant|Bakery|Studio|Sweets|Bakes|Spa|Boutique).*$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*(Pvt\.?\s*Ltd\.?|LLP|Ltd\.?|LLC)", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*\([^)]*\)", "", clean)
    clean = clean.strip()
    return clean or name


def generate_whatsapp_pitch(lead: Dict[str, Any], sender_name: str = "") -> str:
    """
    Short, polite, conversational WhatsApp opener (3-4 lines).
    References a quick video recording of a mobile template from a previous project.
    Avoids aggressive sales jargon and cliché emojis.
    """
    raw_name = lead.get("Business Name") or lead.get("name", "there")
    name = clean_business_name(raw_name)
    city = lead.get("City") or lead.get("city", "Tamil Nadu")
    status = lead.get("Verification Status") or lead.get("verification_status", "")
    has_socials = "HAS SOCIALS" in str(status).upper() or bool(lead.get("Social Profiles")) or bool(lead.get("Social Media URL"))

    if has_socials:
        return (
            f"Hi, is this the owner or manager at {name}?\n\n"
            f"I came across your place while looking at popular shops in {city}. Loved your customer reviews and your social page!\n\n"
            f"I noticed you don't have an official website linked on Google for customers to view your services or order directly on WhatsApp.\n\n"
            f"I'm a freelance web designer from Tamil Nadu. I have a quick 15-second video preview of a clean mobile template from one of my previous client projects with direct WhatsApp ordering.\n\n"
            f"Can I share the short video recording here so you can check it out?"
        )
    else:
        return (
            f"Hi, is this the owner or manager at {name}?\n\n"
            f"Found your shop on Google Maps in {city} with great reviews. I noticed your profile doesn't have an official website listed for people searching on Google.\n\n"
            f"I'm a freelance web designer from Tamil Nadu. I have a quick 15-second video preview of a clean mobile template from one of my previous client projects showing how customers can order directly on WhatsApp.\n\n"
            f"Can I share the short preview recording here so you can take a look?"
        )


def generate_cold_call_script(lead: Dict[str, Any]) -> str:
    raw_name = lead.get("Business Name") or lead.get("name", "there")
    name = clean_business_name(raw_name)
    city = lead.get("City") or lead.get("city", "your city")
    reviews = lead.get("Review Count") or lead.get("review_count", 0)

    return f"""[Cold Call Script - 30 Seconds - Conversational & Respectful]

1. Friendly check:
   "Hi, is this the owner or store manager at {name}?"
   "My name is Krishna. I know you're busy running the shop, so I'll be super quick — do you have 20 seconds?"

2. Genuine observation (not hyped):
   "I was looking at top-rated businesses in {city} and saw you have over {reviews} good reviews on Google Maps."

3. Simple gap:
   "I noticed people searching for you can't view a menu or product list online because there's no website linked."

4. No-pressure offer:
   "I actually have a quick 15-second video preview of a clean mobile template from one of my previous client projects with a direct WhatsApp order button. No sales pitch — can I WhatsApp the short preview recording to this number so you can check it out when you have a free minute?"
"""


import os
from dotenv import load_dotenv

load_dotenv()
DEFAULT_SENDER = os.getenv("SENDER_NAME", "Krishna").strip() or "Krishna"


def generate_email_pitch(lead: Dict[str, Any], sender_name: str = "") -> Dict[str, Any]:
    """
    Generates a natural, human cold email.
    References a video preview of a mobile template from a previous project.
    High-converting personalized subject line, relaxed tone, zero spam keywords.
    """
    if not sender_name:
        sender_name = DEFAULT_SENDER
    raw_name = lead.get("Business Name") or lead.get("name", "there")
    name = clean_business_name(raw_name)
    city = lead.get("City") or lead.get("city", "Tamil Nadu")
    status = lead.get("Verification Status") or lead.get("verification_status", "")
    has_socials = "HAS SOCIALS" in str(status).upper() or bool(lead.get("Social Profiles")) or bool(lead.get("Social Media URL"))
    
    try:
        reviews = int(lead.get("Review Count") or lead.get("review_count") or 0)
    except Exception:
        reviews = 0

    category = (lead.get("Category") or lead.get("category") or "").lower()

    # Dynamic high-converting subject options
    subject_options = [
        f"Quick video preview: mobile template for {name}",
        f"Video preview for {name} ({city})",
        f"Quick idea for {name} ({city})",
        f"Mobile template preview ({name})",
        f"{name} on Google Maps"
    ]
    if reviews >= 40:
        subject_options.insert(2, f"Loved your reviews for {name} - quick video")

    # Remove duplicates while preserving order
    subject_options = list(dict.fromkeys(subject_options))
    subject = subject_options[0]

    if has_socials:
        body = f"""Hi, is this the owner or manager at {name}?

I came across your place while looking at popular shops in {city}. Loved your customer reviews and your social page!

I noticed you don't have an official website linked on Google for customers to view your services or order directly on WhatsApp.

I'm a freelance web designer from Tamil Nadu. I have a quick 15-second video preview of a clean mobile template from one of my previous client projects with direct WhatsApp ordering.

Can I share the short video recording with you so you can check it out?

Best,
{sender_name}"""
    else:
        body = f"""Hi, is this the owner or manager at {name}?

Found your shop on Google Maps in {city} with great reviews. I noticed your profile doesn't have an official website listed for people searching on Google to view your menu or services and order directly on WhatsApp.

I'm a freelance web designer from Tamil Nadu. I have a quick 15-second video preview of a clean mobile template from one of my previous client projects showing how customers can order directly on WhatsApp.

Can I share the short preview recording with you so you can take a look?

Best,
{sender_name}"""

    return {
        "subject": subject,
        "subject_options": subject_options,
        "body": body
    }


