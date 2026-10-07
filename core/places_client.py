"""
Dual-Engine Client for Google Places Lead Generation:
Supports:
1. Local Docker Scraper (Conor's Scraper at http://localhost:8001) - 100% Free, NO CREDIT CARD
2. Official Google Places API (New) Text Search
3. Offline Demo / Mock Engine
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent if Path(__file__).parent.name == "core" else Path(__file__).parent.resolve()
_CORE = _ROOT / "core"
for _p in [str(_ROOT), str(_CORE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


import time
import re
import requests
from typing import List, Dict, Any, Optional

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.businessStatus",
    "places.primaryTypeDisplayName",
    "places.types"
])


class GooglePlacesClient:
    def __init__(
        self,
        api_key: str = "",
        is_demo: bool = False,
        use_docker: bool = True,
        docker_url: str = "http://localhost:8001"
    ):
        self.api_key = api_key.strip()
        self.docker_url = docker_url.rstrip("/")
        self.is_demo = is_demo

        # Auto-detect engine:
        # If user explicitly chose demo, use demo.
        # Otherwise, if use_docker is True or no API key, prefer Docker scraper.
        if self.is_demo:
            self.engine = "demo"
        elif use_docker or not self.api_key:
            self.engine = "docker"
        else:
            self.engine = "google_api"

    def is_docker_alive(self) -> bool:
        """Check if Conor's local Docker scraper is running."""
        try:
            r = requests.get(f"{self.docker_url}/", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def search_places(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Dispatches search to the active engine (Docker Scraper, Official API, or Demo).
        """
        if self.engine == "demo":
            return self._generate_mock_places(query, max_results)

        if self.engine == "docker":
            return self._search_via_docker(query, max_results)

        return self._search_via_google_api(query, max_results)

    def _search_via_docker(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """
        Queries Conor's Playwright scraper running inside Docker.
        Endpoint: /scrape-get?query=...
        """
        if not self.is_docker_alive():
            print(f"\n[!] Notice: Docker Scraper is not running at {self.docker_url}")
            print("[!] To start it:")
            print("    1. Open Docker Desktop")
            print("    2. Run: cd gmaps_scraper && docker compose up -d")
            print("[!] Falling back to demo mode for this run...\n")
            return self._generate_mock_places(query, max_results)

        endpoint = f"{self.docker_url}/scrape-get"
        params = {
            "query": query,
            "max_places": max_results,
            "lang": "en",
            "headless": "true",
            "concurrency": 5
        }

        try:
            print(f"[*] Dispatching scrape to Docker Scraper for: '{query}' (limit: {max_results})...")
            resp = requests.get(endpoint, params=params, timeout=360)
            if resp.status_code != 200:
                print(f"[!] Docker Scraper returned error {resp.status_code}: {resp.text}")
                return []

            raw_results = resp.json()
            if not isinstance(raw_results, list):
                print(f"[!] Unexpected response format from Docker scraper: {raw_results}")
                return []

            normalized = []
            for item in raw_results:
                norm = self._normalize_docker_place(item, query)
                if norm.get("name"):
                    normalized.append(norm)

            return normalized

        except requests.Timeout:
            print(f"[!] Scraping request timed out for query '{query}'. Try lowering max_places or increasing concurrency.")
            return []
        except requests.RequestException as e:
            print(f"[!] Network error connecting to Docker Scraper: {e}")
            return []

    def _normalize_docker_place(self, raw: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Normalize output dictionary from Conor's scraper."""
        name = raw.get("name") or raw.get("title") or ""
        
        # Rating extraction
        rating_raw = raw.get("rating")
        try:
            if isinstance(rating_raw, str):
                rating_match = re.search(r"(\d+(\.\d+)?)", rating_raw)
                rating = float(rating_match.group(1)) if rating_match else 0.0
            else:
                rating = float(rating_raw or 0.0)
        except Exception:
            rating = 0.0

        # Review count extraction
        reviews_raw = raw.get("reviews_count") or raw.get("reviews") or 0
        try:
            if isinstance(reviews_raw, str):
                rev_clean = re.sub(r"[^\d]", "", reviews_raw)
                reviews = int(rev_clean) if rev_clean else 0
            else:
                reviews = int(reviews_raw or 0)
        except Exception:
            reviews = 0

        # Category
        categories = raw.get("categories")
        if isinstance(categories, list) and categories:
            category = categories[0]
        elif isinstance(categories, str) and categories:
            category = categories
        else:
            category = raw.get("category") or "Local Business"

        # Website
        website = raw.get("website") or ""
        if isinstance(website, str) and website.lower() in ("none", "null", "n/a"):
            website = ""

        phone = raw.get("phone") or raw.get("phone_number") or ""
        address = raw.get("address") or ""
        google_maps_url = raw.get("link") or raw.get("url") or ""
        place_id = raw.get("place_id") or raw.get("cid") or f"{name}_{address[:15]}"

        return {
            "place_id": place_id,
            "name": name,
            "category": category,
            "address": address,
            "rating": rating,
            "review_count": reviews,
            "phone": phone,
            "website": website,
            "google_maps_url": google_maps_url,
            "business_status": "OPERATIONAL",
            "hours": raw.get("hours", []),
            "search_query": query
        }

    def _search_via_google_api(self, query: str, max_results: int = 60) -> List[Dict[str, Any]]:
        """Search places using Google Places API (New) Text Search."""
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": FIELD_MASK
        }

        results: List[Dict[str, Any]] = []
        page_token: Optional[str] = None

        while len(results) < max_results:
            payload: Dict[str, Any] = {
                "textQuery": query,
                "pageSize": min(20, max_results - len(results))
            }
            if page_token:
                payload["pageToken"] = page_token

            try:
                response = requests.post(PLACES_SEARCH_URL, headers=headers, json=payload, timeout=15)
                if response.status_code == 400:
                    err_msg = response.json().get("error", {}).get("message", response.text)
                    raise ValueError(f"Google Places API Error (400): {err_msg}")
                elif response.status_code == 403:
                    err_msg = response.json().get("error", {}).get("message", "API key invalid or Places API not enabled.")
                    raise PermissionError(f"Google Places API Permission Error (403): {err_msg}")
                elif response.status_code != 200:
                    raise RuntimeError(f"Google Places API returned status {response.status_code}: {response.text}")

                data = response.json()
                places = data.get("places", [])
                if not places:
                    break

                for raw_place in places:
                    results.append(self._normalize_google_place(raw_place, query))
                    if len(results) >= max_results:
                        break

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

                time.sleep(1.5)

            except requests.RequestException as e:
                print(f"[!] Network error fetching places for '{query}': {e}")
                break

        return results

    def _normalize_google_place(self, raw: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Normalize Google Places API response fields."""
        display_name = raw.get("displayName", {}).get("text", "") if isinstance(raw.get("displayName"), dict) else str(raw.get("displayName", ""))
        primary_type = raw.get("primaryTypeDisplayName", {}).get("text", "") if isinstance(raw.get("primaryTypeDisplayName"), dict) else ""
        if not primary_type:
            types = raw.get("types", [])
            primary_type = types[0].replace("_", " ").title() if types else "Local Business"

        phone = raw.get("nationalPhoneNumber") or raw.get("internationalPhoneNumber") or ""
        website = raw.get("websiteUri") or ""
        google_maps_url = raw.get("googleMapsUri") or (f"https://www.google.com/maps/search/?api=1&query_place_id={raw.get('id')}" if raw.get("id") else "")

        return {
            "place_id": raw.get("id", ""),
            "name": display_name,
            "category": primary_type,
            "address": raw.get("formattedAddress", ""),
            "rating": float(raw.get("rating", 0.0) or 0.0),
            "review_count": int(raw.get("userRatingCount", 0) or 0),
            "phone": phone,
            "website": website,
            "google_maps_url": google_maps_url,
            "business_status": raw.get("businessStatus", "OPERATIONAL"),
            "search_query": query
        }

    def _generate_mock_places(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Tamil Nadu demo dataset when running offline."""
        city = "Coimbatore"
        for c in ["Chennai", "Coimbatore", "Madurai", "Trichy", "Salem", "Tiruppur", "Erode", "Vellore", "Thanjavur", "Tirunelveli"]:
            if c.lower() in query.lower():
                city = c
                break

        all_samples = [
            {
                "place_id": f"mock_tn_{city.lower()}_01",
                "name": f"Aspire Holidays - Travel Agency in {city}",
                "category": "Travel Agency",
                "address": f"104 Cross Cut Road, Gandhipuram, {city}, Tamil Nadu 641012",
                "rating": 4.8,
                "review_count": 3761,
                "phone": "+91 98430 11223",
                "website": "",
                "google_maps_url": f"https://maps.google.com/?cid=1001_{city.lower()}",
                "business_status": "OPERATIONAL"
            },
            {
                "place_id": f"mock_tn_{city.lower()}_02",
                "name": f"Zazzle Luxury Salon & Spa - {city}",
                "category": "Beauty Salon",
                "address": f"45 Thillainagar Main Road, {city}, Tamil Nadu",
                "rating": 4.8,
                "review_count": 5788,
                "phone": "+91 94432 55667",
                "website": "",
                "google_maps_url": f"https://maps.google.com/?cid=1002_{city.lower()}",
                "business_status": "OPERATIONAL"
            },
            {
                "place_id": f"mock_tn_{city.lower()}_03",
                "name": f"{city} Self Drive Cars & Luxury Rentals",
                "category": "Car Rental Agency",
                "address": f"Near New Bus Stand, {city}, Tamil Nadu",
                "rating": 4.8,
                "review_count": 993,
                "phone": "+91 97880 33445",
                "website": "",
                "google_maps_url": f"https://maps.google.com/?cid=1003_{city.lower()}",
                "business_status": "OPERATIONAL"
            },
            {
                "place_id": f"mock_tn_{city.lower()}_04",
                "name": f"Sri Annapoorna Traditional Sweets & Bakes",
                "category": "Restaurant & Confectionery",
                "address": f"77 East Car Street, {city}, Tamil Nadu",
                "rating": 4.7,
                "review_count": 1420,
                "phone": "+91 422 245 6789",
                "website": "",
                "google_maps_url": f"https://maps.google.com/?cid=1004_{city.lower()}",
                "business_status": "OPERATIONAL"
            },
            {
                "place_id": f"mock_tn_{city.lower()}_05",
                "name": f"Grand Chettinad Mess & Catering",
                "category": "Restaurant",
                "address": f"23 North Veli Street, {city}, Tamil Nadu",
                "rating": 4.6,
                "review_count": 890,
                "phone": "+91 94421 99887",
                "website": "",
                "google_maps_url": f"https://maps.google.com/?cid=1007_{city.lower()}",
                "business_status": "OPERATIONAL"
            },
            {
                "place_id": f"mock_tn_{city.lower()}_06",
                "name": f"Royal Loom Silks & Designer Studio",
                "category": "Clothing Store",
                "address": f"8 Bazaar Street, {city}, Tamil Nadu",
                "rating": 4.6,
                "review_count": 480,
                "phone": "+91 98422 77112",
                "website": "",
                "google_maps_url": f"https://maps.google.com/?cid=1006_{city.lower()}",
                "business_status": "OPERATIONAL"
            },
            {
                "place_id": f"mock_tn_{city.lower()}_07",
                "name": f"Apex Academy & NEET Tuition Centre",
                "category": "Educational Institution",
                "address": f"12 VOC Nagar, {city}, Tamil Nadu",
                "rating": 4.9,
                "review_count": 312,
                "phone": "+91 99441 88990",
                "website": "",
                "google_maps_url": f"https://maps.google.com/?cid=1005_{city.lower()}",
                "business_status": "OPERATIONAL"
            },
            {
                "place_id": f"mock_tn_{city.lower()}_08",
                "name": f"Naturals Unisex Salon {city}",
                "category": "Beauty Salon",
                "address": f"Avinashi Road, {city}, Tamil Nadu",
                "rating": 4.7,
                "review_count": 1820,
                "phone": "+91 422 256 0011",
                "website": "https://naturals.in",
                "google_maps_url": f"https://maps.google.com/?cid=1008_{city.lower()}",
                "business_status": "OPERATIONAL"
            }
        ]

        for s in all_samples:
            s["search_query"] = query

        return all_samples[:max_results]
