# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import math
import os
import urllib.parse
import urllib.request
from typing import Any, Optional
import google.auth
from google.auth.transport.requests import Request
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.tools.load_memory_tool import LoadMemoryTool
from google.cloud import firestore
from google.genai import types

MODEL = "gemini-3.8-flash"

# CRITICAL: Hardcode project ID as string. Do not use google.auth.default() or GOOGLE_CLOUD_PROJECT.
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-04-d718c29e3c1e"


def _get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with the hardcoded project ID."""
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


# =========================================================
# REAL DATA & ACTION TOOLS (100% Free, Zero API Keys Required)
# =========================================================


def get_destination_weather(destination: str) -> dict[str, Any]:
    """Fetches real-time current weather, 5-day temperature forecast, and dynamic packing recommendations.

    Uses Open-Meteo's free open meteorological REST API (no API key required).

    Args:
        destination: Name of city or destination (e.g. 'Paris', 'Kyoto', 'Rome', 'Reykjavik', 'Bangkok').

    Returns:
        dict containing current temperature (°C/°F), weather description, 5-day daily forecast, and packing advice.
    """
    clean_dest = destination.strip()
    try:
        # Step 1: Resolve coordinates via free geocoding API
        encoded_dest = urllib.parse.quote(clean_dest)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_dest}&count=1&language=en&format=json"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "VoyageConciergeAgent/1.0"})
        with urllib.request.urlopen(req, timeout=6) as response:
            geo_data = json.loads(response.read().decode())

        if not geo_data.get("results"):
            return {
                "status": "error",
                "message": f"Could not find coordinates for destination '{clean_dest}'.",
            }

        place = geo_data["results"][0]
        lat, lon = place["latitude"], place["longitude"]
        city_name = place.get("name", clean_dest)
        country = place.get("country", "")

        # Step 2: Fetch current & forecast weather
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current_weather=true&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto"
        )
        req_w = urllib.request.Request(weather_url, headers={"User-Agent": "VoyageConciergeAgent/1.0"})
        with urllib.request.urlopen(req_w, timeout=6) as response_w:
            w_data = json.loads(response_w.read().decode())

        current = w_data.get("current_weather", {})
        temp_c = current.get("temperature", 20.0)
        temp_f = round((temp_c * 9 / 5) + 32, 1)
        windspeed = current.get("windspeed", 0)
        weathercode = current.get("weathercode", 0)

        # WMO Weather interpretation codes
        weather_descriptions = {
            0: "Clear sky ☀️",
            1: "Mainly clear 🌤️",
            2: "Partly cloudy ⛅",
            3: "Overcast ☁️",
            45: "Foggy 🌫️",
            48: "Depositing rime fog 🌫️",
            51: "Light drizzle 🌦️",
            53: "Moderate drizzle 🌧️",
            55: "Dense drizzle 🌧️",
            61: "Slight rain 🌧️",
            63: "Moderate rain 🌧️",
            65: "Heavy rain ⛈️",
            71: "Slight snow 🌨️",
            73: "Moderate snow ❄️",
            75: "Heavy snow ❄️",
            80: "Rain showers 🌦️",
            81: "Moderate rain showers 🌧️",
            82: "Violent rain showers ⛈️",
            95: "Thunderstorm ⚡",
        }
        condition = weather_descriptions.get(weathercode, "Clear / Variable 🌤️")

        # Daily outlook
        daily = w_data.get("daily", {})
        forecast_days = []
        time_list = daily.get("time", [])[:5]
        max_temps = daily.get("temperature_2m_max", [])[:5]
        min_temps = daily.get("temperature_2m_min", [])[:5]
        rain_probs = daily.get("precipitation_probability_max", [])[:5]

        for i in range(len(time_list)):
            forecast_days.append({
                "date": time_list[i],
                "high_c": max_temps[i] if i < len(max_temps) else None,
                "low_c": min_temps[i] if i < len(min_temps) else None,
                "rain_prob_pct": rain_probs[i] if i < len(rain_probs) else 0,
            })

        # Dynamic packing advice based on real data
        packing_tips = []
        if temp_c < 10:
            packing_tips.append("Pack thermal layers, a warm insulated coat, scarf, and warm socks.")
        elif temp_c < 18:
            packing_tips.append("Pack light layers, a cardigan or light jacket, and comfortable walking boots.")
        elif temp_c < 26:
            packing_tips.append("Pack breathable cotton/linen clothing, comfortable sneakers, and sunglasses.")
        else:
            packing_tips.append("Warm weather: pack lightweight sun-protective clothing, sunscreen, and a sunhat.")

        max_rain = max(rain_probs) if rain_probs else 0
        if max_rain > 30 or weathercode in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
            packing_tips.append(f"Rain likelihood is {max_rain}%: bring a compact umbrella or waterproof shell.")

        return {
            "status": "success",
            "destination": f"{city_name}, {country}",
            "current_temperature_c": temp_c,
            "current_temperature_f": temp_f,
            "condition": condition,
            "windspeed_kmh": windspeed,
            "forecast_5_day": forecast_days,
            "packing_recommendations": packing_tips,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Could not retrieve real-time weather for '{clean_dest}': {str(e)}",
        }


def convert_currency_and_estimate_budget(
    amount: float,
    from_currency: str,
    to_currency: str,
    duration_days: int = 4,
    budget_tier: str = "moderate",
) -> dict[str, Any]:
    """Calculates live currency exchange and provides a realistic destination budget breakdown.

    Uses the free, public Open Exchange Rates service (open.er-api.com).

    Args:
        amount: Amount in from_currency (e.g. 1500 for total trip spending money).
        from_currency: Traveler's home currency 3-letter code (e.g. 'USD', 'EUR', 'GBP', 'CAD', 'AUD').
        to_currency: Destination currency 3-letter code (e.g. 'JPY', 'THB', 'EUR', 'ISK', 'GBP').
        duration_days: Trip length in days (default 4).
        budget_tier: Traveler's spending style ('budget-friendly', 'moderate', 'luxury').

    Returns:
        dict with live exchange rate, converted sum, daily recommended allowance, and money-saving tips.
    """
    from_curr = from_currency.strip().upper()
    to_curr = to_currency.strip().upper()

    try:
        url = f"https://open.er-api.com/v6/latest/{from_curr}"
        req = urllib.request.Request(url, headers={"User-Agent": "VoyageConciergeAgent/1.0"})
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode())

        rates = data.get("rates", {})
        rate = rates.get(to_curr)

        if not rate:
            return {
                "status": "error",
                "message": f"Currency code '{to_curr}' not found in exchange rate tables.",
            }

        converted_total = round(amount * rate, 2)
        daily_from = round(amount / max(duration_days, 1), 2)
        daily_to = round(converted_total / max(duration_days, 1), 2)

        # Typical daily distribution based on budget tier
        allocations = {
            "budget-friendly": {"meals_pct": 35, "activities_pct": 25, "transit_pct": 20, "souvenirs_pct": 20},
            "moderate": {"meals_pct": 40, "activities_pct": 30, "transit_pct": 15, "souvenirs_pct": 15},
            "luxury": {"meals_pct": 45, "activities_pct": 35, "transit_pct": 10, "souvenirs_pct": 10},
        }
        alloc = allocations.get(budget_tier.lower(), allocations["moderate"])

        daily_breakdown = {
            "meals_and_dining": f"{round(daily_to * alloc['meals_pct'] / 100, 2)} {to_curr}",
            "activities_and_entries": f"{round(daily_to * alloc['activities_pct'] / 100, 2)} {to_curr}",
            "local_transit": f"{round(daily_to * alloc['transit_pct'] / 100, 2)} {to_curr}",
            "shopping_and_misc": f"{round(daily_to * alloc['souvenirs_pct'] / 100, 2)} {to_curr}",
        }

        money_tips = [
            f"1 {from_curr} = {rate:.4f} {to_curr}.",
            "Use a credit card with zero foreign transaction fees for general purchases.",
            f"Keep a modest amount of cash ({to_curr}) for smaller street vendors, traditional markets, and temple donation boxes.",
            "Always choose to be charged in the local currency when paying by card at point-of-sale to avoid dynamic currency conversion markups.",
        ]

        return {
            "status": "success",
            "base_currency": from_curr,
            "target_currency": to_curr,
            "exchange_rate": rate,
            "total_budget_converted": f"{converted_total:,.2f} {to_curr}",
            "daily_allowance": f"{daily_to:,.2f} {to_curr} / day (~{daily_from:,.2f} {from_curr})",
            "budget_tier": budget_tier,
            "suggested_daily_allocation": daily_breakdown,
            "traveler_currency_tips": money_tips,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Currency exchange calculation error: {str(e)}",
        }


def calculate_flight_duration_and_route(
    departure_city: str,
    destination_city: str,
) -> dict[str, Any]:
    """Computes great-circle flight distance, estimated non-stop or layover flight duration, and booking lead-time advice.

    Calculates realistic flight times using spherical coordinates and jet cruise speeds.

    Args:
        departure_city: Origin city (e.g. 'San Francisco', 'New York', 'London', 'Tokyo').
        destination_city: Destination city (e.g. 'Paris', 'Kyoto', 'Rome', 'Bangkok', 'Reykjavik').

    Returns:
        dict with flight distance (miles & km), estimated airborne flight hours, route tips, and booking timeline.
    """
    try:
        def get_coords(city_name: str) -> tuple[float, float, str, str]:
            encoded = urllib.parse.quote(city_name.strip())
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded}&count=1&language=en&format=json"
            req = urllib.request.Request(geo_url, headers={"User-Agent": "VoyageConciergeAgent/1.0"})
            with urllib.request.urlopen(req, timeout=6) as response:
                data = json.loads(response.read().decode())
            if not data.get("results"):
                raise ValueError(f"Could not locate '{city_name}'")
            res = data["results"][0]
            return res["latitude"], res["longitude"], res.get("name", city_name), res.get("country", "")

        lat1, lon1, origin_name, origin_country = get_coords(departure_city)
        lat2, lon2, dest_name, dest_country = get_coords(destination_city)

        # Haversine distance formula
        r_km = 6371.0
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        dist_km = round(r_km * c)
        dist_miles = round(dist_km * 0.621371)

        # Typical jet cruising speed ~850 km/h + 35 mins for takeoff/approach/taxi
        flight_hours_raw = (dist_km / 850.0) + 0.6
        flight_hours = int(flight_hours_raw)
        flight_minutes = int(round((flight_hours_raw - flight_hours) * 60))

        is_long_haul = dist_km > 5000

        timeline_advice = (
            "Book international flights 8 to 12 weeks before departure for prime fares."
            if is_long_haul
            else "Book domestic/regional flights 4 to 8 weeks ahead."
        )

        jetlag_tips = (
            "Long-haul route: hydrate actively, avoid alcohol on board, and shift sleeping hours 1-2 hours towards the destination time zone 3 days prior."
            if is_long_haul
            else "Short/medium-haul route: minimal jet lag anticipated."
        )

        return {
            "status": "success",
            "departure": f"{origin_name}, {origin_country}",
            "destination": f"{dest_name}, {dest_country}",
            "distance_km": dist_km,
            "distance_miles": dist_miles,
            "estimated_nonstop_flight_time": f"{flight_hours}h {flight_minutes}m",
            "route_classification": "Long-Haul Transcontinental" if is_long_haul else "Regional / Medium-Haul",
            "recommended_booking_window": timeline_advice,
            "travel_comfort_tips": jetlag_tips,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to compute flight routing: {str(e)}",
        }


def get_destination_wiki_summary(place_or_landmark: str) -> dict[str, Any]:
    """Fetches real-world cultural, historical, and architectural summaries from Wikipedia's public REST API.

    Public API listed in public-apis (Wikipedia REST API). No API key required.
    Supports optional WIKIMEDIA_USER_AGENT or WIKIMEDIA_API_KEY from environment variables.

    Args:
        place_or_landmark: Name of city, neighborhood, or landmark (e.g. 'Kyoto', 'Eiffel Tower', 'Louvre Museum', 'Alhambra').

    Returns:
        dict with factual description, encyclopedia extract, official page URL, and thumbnail image URL.
    """
    clean_query = place_or_landmark.strip().replace(" ", "_")
    encoded_title = urllib.parse.quote(clean_query)
    wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"

    # Read optional user agent or token from env per guidelines
    custom_ua = os.environ.get("WIKIMEDIA_USER_AGENT", "VoyageConcierge/1.0 (travel-agent-demo@example.com)")
    headers = {"User-Agent": custom_ua, "Accept": "application/json"}
    api_token = os.environ.get("WIKIMEDIA_API_KEY")
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    try:
        req = urllib.request.Request(wiki_url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode())

        title = data.get("title", place_or_landmark)
        description = data.get("description", "")
        extract = data.get("extract", "")
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{encoded_title}")
        thumbnail_url = data.get("thumbnail", {}).get("source") or data.get("originalimage", {}).get("source")

        return {
            "status": "success",
            "title": title,
            "description": description,
            "extract": extract,
            "source_url": page_url,
            "image_url": thumbnail_url,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Could not retrieve Wikipedia summary for '{place_or_landmark}': {str(e)}",
        }


# =========================================================
# GOOGLE MAPS & PLACES (NEW) API TOOLS
# =========================================================


def _get_maps_auth_headers(use_json: bool = True) -> tuple[dict[str, str], Optional[str]]:
    """Helper to return headers and API key for Google Maps Platform calls.

    Prioritizes GOOGLE_MAPS_API_KEY from environment. Falls back to Application Default Credentials (OAuth token)
    with X-Goog-User-Project header if the API key has service restrictions.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    headers: dict[str, str] = {}
    if use_json:
        headers["Content-Type"] = "application/json"

    # Also obtain ADC token as robust fallback
    try:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
        headers["Authorization"] = f"Bearer {creds.token}"
        headers["X-Goog-User-Project"] = FIRESTORE_PROJECT_ID
    except Exception:
        pass

    return headers, api_key


def geocode_address(address: str) -> dict[str, Any]:
    """Converts a street address, city, or landmark name into exact geographic latitude and longitude coordinates.

    Calls Google Maps Geocoding API directly using REST endpoints.
    Reads GOOGLE_MAPS_API_KEY from environment.

    Args:
        address: The address, place name, or landmark to geocode (e.g. 'Eiffel Tower Paris', '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        dict with formatted address, latitude, longitude, and place ID.
    """
    clean_addr = address.strip()
    headers, api_key = _get_maps_auth_headers(use_json=False)

    # Strategy 1: Geocoding v4 REST endpoint (supports both API key and Bearer auth)
    encoded = urllib.parse.quote(clean_addr)
    url_v4 = f"https://geocode.googleapis.com/v4/geocode/address?address.addressLines={encoded}"
    if api_key:
        url_v4 += f"&key={api_key}"

    try:
        req = urllib.request.Request(url_v4, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode())

        results = data.get("results", [])
        if results:
            first = results[0]
            loc = first.get("location", {})
            return {
                "status": "success",
                "name": clean_addr,
                "formatted_address": first.get("formattedAddress", clean_addr),
                "location": {
                    "latitude": loc.get("latitude"),
                    "longitude": loc.get("longitude"),
                },
                "place_id": first.get("placeId"),
            }
    except Exception:
        pass

    # Strategy 2: Geocoding v3 REST endpoint with API key
    if api_key:
        try:
            url_v3 = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded}&key={api_key}"
            req_v3 = urllib.request.Request(url_v3)
            with urllib.request.urlopen(req_v3, timeout=8) as response_v3:
                data_v3 = json.loads(response_v3.read().decode())

            if data_v3.get("status") == "OK" and data_v3.get("results"):
                first_v3 = data_v3["results"][0]
                geometry = first_v3.get("geometry", {}).get("location", {})
                return {
                    "status": "success",
                    "name": clean_addr,
                    "formatted_address": first_v3.get("formatted_address", clean_addr),
                    "location": {
                        "latitude": geometry.get("lat"),
                        "longitude": geometry.get("lng"),
                    },
                    "place_id": first_v3.get("place_id"),
                }
        except Exception as e_v3:
            return {
                "status": "error",
                "message": f"Geocoding failed for '{clean_addr}': {str(e_v3)}",
            }

    return {
        "status": "error",
        "message": f"Could not find coordinates for address: '{clean_addr}'.",
    }


def search_nearby_places(
    place_type: str,
    latitude: float,
    longitude: float,
    radius_meters: float = 1000.0,
    max_results: int = 5,
) -> dict[str, Any]:
    """Finds nearby places of a given type around specific geographic coordinates using the Places API (New).

    Directly invokes POST https://places.googleapis.com/v1/places:searchNearby with required X-Goog-FieldMask header.
    Key fields returned: name, address, and location.

    Args:
        place_type: Type of place, e.g. 'restaurant', 'cafe', 'hotel', 'tourist_attraction', 'museum', 'bakery', 'bar'.
        latitude: Latitude of the center point.
        longitude: Longitude of the center point.
        radius_meters: Search radius in meters (default 1000m, max 50000m).
        max_results: Max number of places to return (default 5, max 20).

    Returns:
        dict with list of nearby places containing name, address, and location coordinates.
    """
    endpoint = "https://places.googleapis.com/v1/places:searchNearby"
    headers, api_key = _get_maps_auth_headers(use_json=True)

    # Required field mask header confirmed via Developer Knowledge MCP
    headers["X-Goog-FieldMask"] = "places.displayName,places.formattedAddress,places.location,places.types"
    if api_key:
        headers["X-Goog-Api-Key"] = api_key

    payload = {
        "includedTypes": [place_type.lower().strip()],
        "maxResultCount": min(max(max_results, 1), 20),
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                },
                "radius": float(radius_meters),
            }
        },
    }

    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

        places = []
        for p in data.get("places", []):
            display_name = p.get("displayName", {}).get("text", "Unknown Name")
            places.append({
                "name": display_name,
                "address": p.get("formattedAddress", "Address unavailable"),
                "location": p.get("location", {}),
            })

        return {
            "status": "success",
            "place_type": place_type,
            "center": {"latitude": latitude, "longitude": longitude},
            "radius_meters": radius_meters,
            "count": len(places),
            "places": places,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to search nearby places: {str(e)}",
            "places": [],
        }


# ==========================================
# FIRESTORE TOOLS (Read & Write Catalog)
# ==========================================


def list_travel_destinations(
    region: Optional[str] = None,
    travel_vibe: Optional[str] = None,
) -> dict[str, Any]:
    """Reads and lists travel destinations from the Firestore 'travel_destinations' collection.

    Can optionally filter by geographic region or travel vibe/interest.

    Args:
        region: Optional geographic filter, e.g. 'Europe', 'Asia', 'Southeast Asia', 'Nordic / Europe'.
        travel_vibe: Optional interest/vibe filter, e.g. 'art', 'nature', 'culinary', 'history', 'culture'.

    Returns:
        dict containing the list of matching destinations with their highlights, best seasons, and vibes.
    """
    try:
        db = _get_firestore_client()
        docs = db.collection("travel_destinations").stream()
        results = []

        for doc in docs:
            data = doc.to_dict()
            if region and region.lower() not in data.get("region", "").lower():
                continue
            if travel_vibe:
                vibes = [v.lower() for v in data.get("travel_vibes", [])]
                if not any(travel_vibe.lower() in v for v in vibes):
                    continue
            results.append(data)

        return {
            "status": "success",
            "count": len(results),
            "destinations": results,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to read from Firestore: {str(e)}",
            "destinations": [],
        }


def get_destination_details(destination_id_or_name: str) -> dict[str, Any]:
    """Retrieves full details for a specific travel destination from Firestore.

    Args:
        destination_id_or_name: The destination ID (e.g. 'paris-france', 'kyoto-japan') or destination name (e.g. 'Paris', 'Kyoto').

    Returns:
        dict with comprehensive details including neighborhoods, dining scene, best season, and highlights.
    """
    try:
        db = _get_firestore_client()
        coll = db.collection("travel_destinations")

        # Try direct document lookup first
        doc_ref = coll.document(destination_id_or_name.lower().strip())
        doc = doc_ref.get()
        if doc.exists:
            return {"status": "success", "destination": doc.to_dict()}

        # Search by name match
        docs = coll.stream()
        for d in docs:
            data = d.to_dict()
            if destination_id_or_name.lower().strip() in data.get("name", "").lower():
                return {"status": "success", "destination": data}

        return {
            "status": "not_found",
            "message": f"Destination '{destination_id_or_name}' not found in Firestore collection.",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to retrieve destination details: {str(e)}",
        }


def add_travel_destination(
    name: str,
    country: str,
    region: str,
    travel_vibes: list[str],
    ideal_duration_days: int,
    best_season: str,
    highlights: list[str],
    dining_scene: str,
    base_budget_level: str = "moderate",
) -> dict[str, Any]:
    """Writes a new curated destination into the Firestore 'travel_destinations' collection.

    Args:
        name: Name of the destination city or region (e.g. 'Barcelona').
        country: Country (e.g. 'Spain').
        region: Geographic region (e.g. 'Europe').
        travel_vibes: List of vibes/interests (e.g. ['architecture', 'beaches', 'tapas']).
        ideal_duration_days: Recommended stay length in days.
        best_season: Best time of year to visit.
        highlights: Key sights and activities.
        dining_scene: Culinary highlights and specialties.
        base_budget_level: Budget category ('budget-friendly', 'moderate', 'luxury').

    Returns:
        dict confirming destination was stored in Firestore.
    """
    try:
        doc_id = f"{name.lower().replace(' ', '-')}-{country.lower().replace(' ', '-')}"
        data = {
            "id": doc_id,
            "name": name,
            "country": country,
            "region": region,
            "travel_vibes": travel_vibes,
            "ideal_duration_days": ideal_duration_days,
            "best_season": best_season,
            "highlights": highlights,
            "dining_scene": dining_scene,
            "base_budget_level": base_budget_level,
            "created_at": datetime.datetime.now().isoformat(),
        }

        db = _get_firestore_client()
        db.collection("travel_destinations").document(doc_id).set(data)

        return {
            "status": "success",
            "message": f"Destination '{name}' successfully added to Firestore with ID '{doc_id}'.",
            "destination": data,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to write destination to Firestore: {str(e)}",
        }


# ==========================================
# SESSION STATE TOOLS (Profile & Checklist)
# ==========================================


def save_traveler_profile(
    traveler_name: Optional[str] = None,
    travel_history: Optional[str] = None,
    travel_companions: Optional[str] = None,
    food_habits_and_allergies: Optional[str] = None,
    hotel_preferences: Optional[str] = None,
    packing_and_shopping_interests: Optional[str] = None,
    destination_interests: Optional[str] = None,
    trip_duration_days: Optional[int] = None,
    budget_tier: Optional[str] = None,
    passport_country: Optional[str] = None,
    additional_preferences: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Saves or updates individual attributes of the traveler's profile in session state.

    Supports partial, incremental updates so all user details, answers, and preferences
    are recorded and remembered to curate custom travel itineraries and recommendations.
    """
    existing_profile = tool_context.state.get("traveler_profile", {}) if tool_context else {}

    if traveler_name:
        existing_profile["traveler_name"] = traveler_name
    if travel_history:
        existing_profile["travel_history"] = travel_history
    if travel_companions:
        existing_profile["travel_companions"] = travel_companions
    if food_habits_and_allergies:
        existing_profile["food_habits_and_allergies"] = food_habits_and_allergies
    if hotel_preferences:
        existing_profile["hotel_preferences"] = hotel_preferences
    if packing_and_shopping_interests:
        existing_profile["packing_and_shopping_interests"] = packing_and_shopping_interests
    if destination_interests:
        existing_profile["destination_interests"] = destination_interests
    if trip_duration_days:
        existing_profile["trip_duration_days"] = trip_duration_days
    if budget_tier:
        existing_profile["budget_tier"] = budget_tier
    if passport_country:
        existing_profile["passport_country"] = passport_country
    if additional_preferences:
        existing_profile["additional_preferences"] = additional_preferences

    existing_profile["updated_at"] = datetime.datetime.now().isoformat()

    if tool_context:
        tool_context.state["traveler_profile"] = existing_profile

    return {
        "status": "success",
        "message": "Traveler profile updated successfully.",
        "profile": existing_profile,
    }


def get_traveler_profile(tool_context: ToolContext) -> dict[str, Any]:
    """Retrieves the stored traveler profile and known preferences from session state.

    Returns:
        dict containing the traveler's profile or indicating which fields are still unknown.
    """
    profile = tool_context.state.get("traveler_profile")
    if not profile:
        return {
            "status": "empty",
            "message": "No profile details collected yet in this session.",
            "known_fields": {},
            "missing_fields": [
                "traveler_name",
                "travel_companions",
                "food_habits_and_allergies",
                "hotel_preferences",
                "packing_and_shopping_interests",
                "destination_interests",
                "trip_duration_days",
                "budget_tier",
                "passport_country",
            ],
        }

    all_fields = [
        "traveler_name",
        "travel_companions",
        "food_habits_and_allergies",
        "hotel_preferences",
        "packing_and_shopping_interests",
        "destination_interests",
        "trip_duration_days",
        "budget_tier",
        "passport_country",
        "travel_history",
        "additional_preferences",
    ]
    known = {k: v for k, v in profile.items() if v and k != "updated_at"}
    missing = [f for f in all_fields if f not in known]

    return {
        "status": "success",
        "profile": profile,
        "known_fields": known,
        "missing_fields": missing,
    }


def reset_traveler_profile_and_checklist(tool_context: ToolContext) -> dict[str, Any]:
    """Clears and resets any previous traveler profile and checklist in the session state."""
    tool_context.state.pop("traveler_profile", None)
    tool_context.state.pop("trip_checklist", None)
    return {
        "status": "success",
        "message": "Traveler profile and checklist have been completely cleared.",
    }


def check_visa_and_passport_requirements(
    destination_country: str,
    citizen_country: str,
    passport_valid_months_remaining: int,
) -> dict[str, Any]:
    """Looks up visa regulations, entry requirements, and passport validity rules for a destination.

    Args:
        destination_country: The country the user wants to visit (e.g. 'Japan', 'France', 'Thailand').
        citizen_country: The country of user's citizenship / passport (e.g. 'United States', 'India', 'Canada').
        passport_valid_months_remaining: How many months until user's passport expires.

    Returns:
        dict containing visa policy, minimum passport validity rule, and required travel documents.
    """
    dest = destination_country.strip().title()
    cit = citizen_country.strip().title()
    passport_ok = passport_valid_months_remaining >= 6

    visa_rules = {
        "Japan": {
            "United States": "Visa-free for tourism up to 90 days. Digital Visit Japan Web QR code recommended for expedited customs/immigration.",
            "Canada": "Visa-free for tourism up to 90 days. Register on Visit Japan Web.",
            "United Kingdom": "Visa-free up to 90 days. Complete immigration declarations online.",
            "India": "eVisa or standard Tourist Visa required before arrival. Processing takes ~5-7 business days.",
            "default": "Check Japanese embassy portal; OECD passports generally visa-free for 90 days.",
        },
        "France": {
            "United States": "Schengen Area 90-day visa waiver for US citizens (valid 90 days within any 180-day window). ETIAS pre-authorization required when launched.",
            "Canada": "Schengen Area 90-day visa waiver. ETIAS pre-authorization required.",
            "United Kingdom": "90 days within any 180-day period without visa.",
            "India": "Schengen Tourist Visa (short stay type C) required prior to departure. Requires appointment and travel insurance min 30,000 EUR.",
            "default": "Schengen rules apply. Passports must have at least 3 months validity beyond intended departure from Schengen area.",
        },
        "Italy": {
            "United States": "Schengen Area 90-day visa waiver. ETIAS pre-authorization required.",
            "Canada": "Schengen Area 90-day visa waiver.",
            "India": "Schengen Tourist Visa required. Apply through VFS Global 4-8 weeks in advance.",
            "default": "Schengen area regulations apply.",
        },
        "Spain": {
            "United States": "Schengen Area 90-day visa waiver.",
            "Canada": "Schengen Area 90-day visa waiver.",
            "India": "Schengen Tourist Visa required.",
            "default": "Schengen area regulations apply.",
        },
        "Thailand": {
            "United States": "Visa exemption for up to 60 days for tourism.",
            "Canada": "Visa exemption for up to 60 days for tourism.",
            "India": "Visa exemption / Visa on Arrival scheme applicable.",
            "default": "Visa exemption available for eligible nationalities; others eligible for Visa on Arrival.",
        },
        "Iceland": {
            "United States": "Schengen Area 90-day visa waiver.",
            "Canada": "Schengen Area 90-day visa waiver.",
            "India": "Schengen Tourist Visa required before arrival.",
            "default": "Schengen area rules apply.",
        },
    }

    country_info = visa_rules.get(dest, {})
    rule_detail = country_info.get(cit, country_info.get("default", f"Consult official embassy / consulate of {dest} for entry regulations."))

    return {
        "status": "success",
        "destination": dest,
        "citizenship": cit,
        "passport_valid_months_remaining": passport_valid_months_remaining,
        "passport_validity_adequate": passport_ok,
        "passport_guidance": "Passport validity is sufficient (>= 6 months)." if passport_ok else "WARNING: Most international destinations require at least 6 months passport validity. Renew your passport before booking non-refundable travel.",
        "visa_requirements": rule_detail,
        "mandatory_steps": [
            "Ensure passport is valid at least 6 months past return date.",
            "Check entry requirements and obtain any required digital authorizations (e.g. Visit Japan Web, ETIAS).",
            "Purchase travel and emergency medical insurance.",
        ],
    }


def search_destination_and_itinerary(
    destination: str,
    duration_days: int,
    travel_vibe: str,
    dietary_preferences: str,
    accommodation_style: str,
) -> dict[str, Any]:
    """Generates a structured destination highlights guide and day-by-day itinerary tailored strictly to provided traveler parameters.

    Args:
        destination: City or region of interest (e.g. 'Paris, France', 'Kyoto, Japan').
        duration_days: Number of travel days.
        travel_vibe: Vibe explicitly stated by the user (or 'general cultural sightseeing' if unspecified).
        dietary_preferences: Food habits or restrictions explicitly specified by user (or 'no restrictions specified' if unspecified).
        accommodation_style: Hotel preference explicitly specified by user (or 'standard central hotels' if unspecified).

    Returns:
        dict with recommended neighborhoods, hotel archetypes, dining guidance, and day-by-day itinerary outline.
    """
    diet_str = dietary_preferences if dietary_preferences and dietary_preferences != "none" else "diverse local cuisine"
    vibe_str = travel_vibe if travel_vibe and travel_vibe != "none" else "highlights and cultural discovery"
    hotel_str = accommodation_style if accommodation_style and accommodation_style != "none" else "centrally located accommodations"

    return {
        "status": "success",
        "destination": destination,
        "duration_days": duration_days,
        "vibe": vibe_str,
        "dietary_consideration": diet_str,
        "accommodation_style": hotel_str,
        "recommended_neighborhoods": [
            f"Central Iconic Quarter of {destination} (walkable access to major sights)",
            f"Cultural & Historic Quarter (museums, cafes, and architecture)",
            f"Lively Dining & Evening District",
        ],
        "hotel_archetypes": [
            {"style": hotel_str, "perks": "Convenient transit access, neighborhood charm"},
        ],
        "itinerary_blueprint": {
            "day_1": f"Arrival in {destination}, hotel check-in, orientation walk, and welcome dinner.",
            "day_2": f"Explore iconic landmarks and scenic viewpoints of {destination}.",
            "day_3": f"Cultural immersion ({vibe_str}): museums, neighborhood walks, and local culinary experiences.",
            "subsequent_days": f"Further neighborhood explorations, day trips, and leisure through day {duration_days}.",
            "departure_day": "Farewell breakfast, last-minute shopping, and airport/station transfer.",
        },
        "booking_timelines": {
            "flights": "Book 8 to 12 weeks ahead for international routes.",
            "hotels": "Reserve 6 to 10 weeks ahead with flexible cancellation.",
            "major_attractions": "Reserve time-slot tickets 3-4 weeks ahead.",
        },
    }


def manage_trip_checklist(
    action: str,
    item_title: str,
    category: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Manages the traveler's preparation checklist and status follow-ups.

    Args:
        action: One of 'add', 'complete', 'list', 'init_defaults'.
        item_title: The checklist item task name.
        category: Category for the task ('documents', 'bookings', 'packing', 'logistics').

    Returns:
        dict containing the updated checklist and completion stats.
    """
    checklist = tool_context.state.get("trip_checklist", [])

    if action == "init_defaults":
        default_items = [
            {"id": 1, "title": "Check passport expiry (ensure > 6 months validity)", "category": "documents", "done": False},
            {"id": 2, "title": "Confirm visa / digital entry pre-authorization requirements", "category": "documents", "done": False},
            {"id": 3, "title": "Book international flights and reserve seat selection", "category": "bookings", "done": False},
            {"id": 4, "title": "Reserve accommodations with flexible cancellation", "category": "bookings", "done": False},
            {"id": 5, "title": "Purchase comprehensive travel and medical insurance", "category": "documents", "done": False},
            {"id": 6, "title": "Notify bank of international travel & verify credit cards (zero foreign transaction fees)", "category": "logistics", "done": False},
            {"id": 7, "title": "Order international eSIM or portable Wi-Fi device", "category": "logistics", "done": False},
            {"id": 8, "title": "Pack electrical plug adapter & portable charger in carry-on", "category": "packing", "done": False},
            {"id": 9, "title": "Pack essential medications and travel documents in personal item", "category": "packing", "done": False},
        ]
        tool_context.state["trip_checklist"] = default_items
        checklist = default_items

    elif action == "add":
        new_id = len(checklist) + 1
        new_item = {"id": new_id, "title": item_title, "category": category or "general", "done": False}
        checklist.append(new_item)
        tool_context.state["trip_checklist"] = checklist

    elif action == "complete":
        for item in checklist:
            if item_title.lower() in item["title"].lower():
                item["done"] = True
        tool_context.state["trip_checklist"] = checklist

    total = len(checklist)
    completed = sum(1 for item in checklist if item.get("done"))
    pending = total - completed

    return {
        "status": "success",
        "action_performed": action,
        "total_items": total,
        "completed_items": completed,
        "pending_items": pending,
        "checklist": checklist,
    }


SYSTEM_INSTRUCTION = """
You are the **Voyage Concierge**, an expert, deeply personalized, and highly interactive AI travel concierge.

### POWERFUL CAPABILITIES & REAL DATA TOOLS:
1. **Real-time Weather & Packing**:
   - Call `get_destination_weather` whenever a traveler asks about weather, what clothes to pack, or conditions in a destination.
2. **Live Currency & Budgeting**:
   - Call `convert_currency_and_estimate_budget` to give exact live exchange rates (USD/EUR to JPY, THB, ISK, etc.), daily spending breakdowns, and tipping etiquette.
3. **Flight Time & Route Estimator**:
   - Call `calculate_flight_duration_and_route` to calculate distance, real flight hours, and booking lead-time advice.
4. **Google Maps & Places (New)**:
   - Call `geocode_address` to resolve any street address or landmark to exact geographic coordinates.
   - Call `search_nearby_places` to find real nearby restaurants, cafes, hotels, museums, or attractions around coordinates.
5. **Wikipedia Encyclopedia & Landmark Lookups**:
   - Call `get_destination_wiki_summary` to fetch real encyclopedia summaries, history, official article links, and landmark photos for cities or attractions.
6. **Firestore Destination Catalog**:
   - Call `list_travel_destinations` and `get_destination_details` to pull curated recommendations from the database.
   - Call `add_travel_destination` if the user wants to save a custom travel spot.
7. **Visa & Entry Requirements**:
   - Call `check_visa_and_passport_requirements` for passport validity and visa rules.
8. **Preparation Checklist**:
   - Call `manage_trip_checklist` to organize actionable preparation tasks.

---

### CORE INTERACTION PRINCIPLE: ONE QUESTION AT A TIME
To ensure a delightful, conversational, and non-overwhelming experience:
1. **NEVER bombard the user with a laundry list or numbered list of multiple questions at once.**
2. **Conduct the discovery conversation incrementally, asking ONE single, focused question per turn.**
3. When the user provides an answer:
   - Acknowledge their response warmly.
   - Immediately call `save_traveler_profile` to record the newly learned attribute in session state.
   - Then, ask the NEXT single question.

---

### PROGRESSIVE DISCOVERY QUESTION SEQUENCE:
Follow this natural conversational order when learning about the traveler:
* **Step 1 (Name & Companions)**: Ask for their name and who they usually travel with (e.g. solo, partner/spouse, family with kids, or friends).
* **Step 2 (Dining & Allergies)**: Once they answer companions, ask about their dining habits, dietary preferences, and any severe allergies or foods they avoid.
* **Step 3 (Accommodation Style)**: Once dining is recorded, ask what type of hotels or stays they feel most comfortable in (e.g. quiet boutique hotels, historic villas/ryokans, luxury resorts, central apartments).
* **Step 4 (Interests, Packing & Shopping)**: Next, ask about their travel interests and packing habits.
* **Step 5 (Upcoming Trip Destination & Dates)**: Ask where they are dreaming of heading next (or offer recommendations from Firestore catalog), and for how many days.
* **Step 6 (Passport & Visas)**: Ask what country issued their passport and approximate validity to verify visa requirements.

*(Note: If the user provides multiple answers at once in a single message, accept them all, save them with `save_traveler_profile`, and then only ask for the remaining missing detail.)*

---

### CRITICAL GROUNDING, MEMORY UTILIZATION & ZERO-HALLUCINATION RULES:
1. **NEVER assume, invent, or hallucinate user preferences, dietary restrictions, or travel style.**
2. **ACTIVE MEMORY UTILIZATION**:
   - Cross-session memory is automatically preloaded into your context via `PreloadMemoryTool` and can also be queried on demand using `load_memory`.
   - **Check memories and profile first**: Before asking the user any questions, check if their name, companions, dietary needs, preferred hotel styles, budget tier, or previous destinations are already recorded in memory or session state.
   - If a detail is already known from a past conversation or turn, **DO NOT re-ask it**. Warmly acknowledge it (e.g. *"Welcome back, Alex! Since I know you love quiet boutique hotels and prefer vegetarian dining..."*) and proceed directly to curating suggestions tailored to those saved facts.
   - Whenever the user shares any preference, constraint, or fact, actively incorporate it into all subsequent recommendations, itinerary plans, packing suggestions, restaurant options, and budget calculations.
3. Call `get_traveler_profile` to check session state, and use `save_traveler_profile` whenever the user provides details or answers.
4. Use real tools (`get_destination_weather`, `geocode_address`, `search_nearby_places`, `convert_currency_and_estimate_budget`, etc.) to provide accurate, factual data tailored to the user's specific preferences.

Tone: Warm, engaging, attentive, conversational, and genuinely interactive. Keep messages concise and easy to read.
"""


# WRITE: after each turn, send the session to Memory Bank for durable extraction.
async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None


root_agent = Agent(
    name="travel_concierge",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=SYSTEM_INSTRUCTION,
    tools=[
        # Cross-session Memory tools:
        # PreloadMemoryTool injects durable memories at turn start; LoadMemoryTool allows on-demand memory recall
        PreloadMemoryTool(),
        LoadMemoryTool(),
        # Real-data tools (Weather, Currency, Route, Wikipedia)
        get_destination_weather,
        convert_currency_and_estimate_budget,
        calculate_flight_duration_and_route,
        get_destination_wiki_summary,
        # Google Maps & Places (New) tools
        geocode_address,
        search_nearby_places,
        # Firestore catalog tools
        list_travel_destinations,
        get_destination_details,
        add_travel_destination,
        # Session profile & checklist tools
        get_traveler_profile,
        save_traveler_profile,
        reset_traveler_profile_and_checklist,
        check_visa_and_passport_requirements,
        search_destination_and_itinerary,
        manage_trip_checklist,
    ],
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="travel_concierge_app",
)
