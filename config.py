"""
Configuration and criteria settings for Google Places Lead Generation.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(BASE_DIR / ".env")

# Google Places API Key (optional if using Docker scraper)
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()

# Data source provider: 'docker' (Conor's Scraper), 'google_api', or 'demo'
DATA_SOURCE = os.getenv("DATA_SOURCE", "docker").lower()
DOCKER_SCRAPER_URL = os.getenv("DOCKER_SCRAPER_URL", "http://localhost:8001").rstrip("/")

# Default lead qualification criteria
DEFAULT_CRITERIA = {
    "min_rating": float(os.getenv("MIN_RATING", "4.5")),
    "min_reviews": int(os.getenv("MIN_REVIEWS", "50")),
    "only_no_website": os.getenv("ONLY_NO_WEBSITE", "true").lower() in ("1", "true", "yes"),
    "require_phone": os.getenv("REQUIRE_PHONE", "false").lower() in ("1", "true", "yes"),
    "operational_only": os.getenv("OPERATIONAL_ONLY", "true").lower() in ("1", "true", "yes"),
    "max_results_per_query": int(os.getenv("MAX_RESULTS_PER_QUERY", "60")),
}

# Output directories
OUTPUT_DIR = BASE_DIR / "leads_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Curated Tamil Nadu Target Matrix (High-ROI shops that benefit most from websites)
TAMIL_NADU_TARGETS = {
    "Coimbatore": ["restaurants", "meat shops", "bakeries", "sweet stalls", "furniture showrooms"],
    "Chennai": ["restaurants", "meat shops", "bakeries", "organic stores", "clothing boutiques"],
    "Madurai": ["restaurants", "meat shops", "sweet stalls", "textile showrooms"],
    "Trichy": ["restaurants", "meat shops", "bakeries", "furniture stores"],
    "Salem": ["restaurants", "meat shops", "bakeries", "textile stores"],
    "Tiruppur": ["clothing stores", "restaurants", "meat shops", "tailoring studios"],
    "Erode": ["textile showrooms", "restaurants", "meat shops", "bakeries"],
    "Vellore": ["restaurants", "meat shops", "bakeries", "clinics"],
    "Thanjavur": ["restaurants", "hotels", "bakeries", "handicrafts"],
    "Tirunelveli": ["restaurants", "sweet stalls", "meat shops", "bakeries"],
}

