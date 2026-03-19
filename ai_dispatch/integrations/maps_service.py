"""
Maps Service — unified interface for Google Maps and Apple Maps APIs.

Provides:
  - Distance matrix (batch lat/lon → distance + travel time)
  - Route details + encoded polyline
  - Geocoding (address → lat/lon)
  - Reverse geocoding (lat/lon → address)
  - Real-time traffic-aware ETAs
  - Deep link URL generation for Google and Apple Maps
"""

from __future__ import annotations
import asyncio
import logging
import math
import os
import time
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

# Google Maps API base URLs
GMAPS_DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
GMAPS_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
GMAPS_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Simple in-process cache TTL (seconds)
CACHE_TTL = 300  # 5 minutes


class _CacheEntry:
    def __init__(self, value: Any, ttl: int = CACHE_TTL):
        self.value = value
        self.expires_at = time.time() + ttl


class MapsService:
    """
    Unified Maps service supporting Google Maps (primary) and Apple Maps (deep links).

    Apple MapKit JS requires server-side JWT signing and is used here only
    for deep link generation (maps:// URL scheme) on iOS/macOS.
    For server-side routing, Google Maps API is the primary engine.
    """

    def __init__(
        self,
        google_api_key: Optional[str] = None,
        apple_maps_team_id: Optional[str] = None,
        apple_maps_key_id: Optional[str] = None,
        apple_maps_private_key_path: Optional[str] = None,
        traffic_model: str = "best_guess",    # best_guess | pessimistic | optimistic
        circuit_breaker_threshold: int = 3,   # failures before disabling API
        circuit_breaker_cooldown: int = 300,  # seconds to stay in open state
    ):
        self.google_api_key = google_api_key or os.getenv("GOOGLE_MAPS_API_KEY", "")
        self.apple_team_id = apple_maps_team_id or os.getenv("APPLE_MAPS_TEAM_ID", "")
        self.apple_key_id = apple_maps_key_id or os.getenv("APPLE_MAPS_KEY_ID", "")
        self.apple_key_path = apple_maps_private_key_path or os.getenv("APPLE_MAPS_PRIVATE_KEY_PATH", "")
        self.traffic_model = traffic_model
        self._cache: Dict[str, _CacheEntry] = {}

        # Circuit breaker state — prevents hammering a failing API
        self._cb_threshold = circuit_breaker_threshold
        self._cb_cooldown = circuit_breaker_cooldown
        self._cb_failures: int = 0
        self._cb_open_until: Optional[datetime] = None

        if not self.google_api_key:
            logger.warning("GOOGLE_MAPS_API_KEY not set. Will use Haversine fallback.")

    # ─── Cache helpers ────────────────────────────────────────────────────────

    def _cache_get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry and time.time() < entry.expires_at:
            return entry.value
        self._cache.pop(key, None)
        return None

    def _cache_set(self, key: str, value: Any):
        self._cache[key] = _CacheEntry(value)

    # ─── Circuit breaker helpers ───────────────────────────────────────────────

    def _is_api_healthy(self) -> bool:
        """Returns False when the circuit is open (API is cooling down)."""
        if self._cb_open_until and datetime.utcnow() < self._cb_open_until:
            return False
        if self._cb_open_until and datetime.utcnow() >= self._cb_open_until:
            # Cooldown expired — reset and allow a probe request through
            logger.info("Maps API circuit breaker: cooldown expired, probing API again.")
            self._cb_open_until = None
            self._cb_failures = 0
        return True

    def _record_api_success(self):
        """Reset circuit breaker on a successful API call."""
        self._cb_failures = 0
        self._cb_open_until = None

    def _record_api_failure(self, error: Exception):
        """Increment failure counter; open circuit after threshold is reached."""
        self._cb_failures += 1
        if self._cb_failures >= self._cb_threshold:
            self._cb_open_until = datetime.utcnow() + timedelta(seconds=self._cb_cooldown)
            logger.warning(
                "Maps API circuit breaker OPEN after %d consecutive failures. "
                "Falling back to Haversine for %d seconds. Last error: %s",
                self._cb_failures,
                self._cb_cooldown,
                error,
            )

    # ─── Distance Matrix ──────────────────────────────────────────────────────

    def get_distance_matrix(
        self,
        origins: List[Tuple[float, float]],
        destinations: List[Tuple[float, float]],
        departure_time: str = "now",
    ) -> List[Dict[str, Any]]:
        """
        Get distance and travel time for each origin→destination pair.
        Returns list of dicts: {"distance_km": float, "duration_minutes": float}
        Falls back to Haversine if API unavailable.
        """
        if not self.google_api_key or not self._is_api_healthy():
            return self._haversine_matrix(origins, destinations)

        cache_key = f"dm:{origins}:{destinations}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        origins_str = "|".join(f"{lat},{lon}" for lat, lon in origins)
        dests_str = "|".join(f"{lat},{lon}" for lat, lon in destinations)

        params = {
            "origins": origins_str,
            "destinations": dests_str,
            "key": self.google_api_key,
            "departure_time": departure_time,
            "traffic_model": self.traffic_model,
            "units": "metric",
        }

        try:
            response = httpx.get(GMAPS_DISTANCE_MATRIX_URL, params=params, timeout=5.0)
            response.raise_for_status()
            data = response.json()

            results = []
            for row in data.get("rows", []):
                for element in row.get("elements", []):
                    if element.get("status") == "OK":
                        dist_km = element["distance"]["value"] / 1000.0
                        # Use duration_in_traffic if available, else duration
                        dur_key = "duration_in_traffic" if "duration_in_traffic" in element else "duration"
                        dur_min = element[dur_key]["value"] / 60.0
                        results.append({
                            "distance_km": round(dist_km, 2),
                            "duration_minutes": round(dur_min, 1),
                            "distance_text": element["distance"]["text"],
                            "duration_text": element[dur_key]["text"],
                        })
                    else:
                        results.append(self._haversine_matrix([origins[0]], [destinations[0]])[0])

            self._record_api_success()
            self._cache_set(cache_key, results)
            return results

        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.warning(f"Google Distance Matrix API error: {e}. Using Haversine fallback.")
            self._record_api_failure(e)
            return self._haversine_matrix(origins, destinations)

    def _haversine_matrix(
        self,
        origins: List[Tuple[float, float]],
        destinations: List[Tuple[float, float]],
    ) -> List[Dict[str, Any]]:
        """Pure math fallback when API is unavailable."""
        results = []
        for lat1, lon1 in origins:
            for lat2, lon2 in destinations:
                dist = _haversine_km(lat1, lon1, lat2, lon2)
                travel = (dist / 40.0) * 60  # Assume 40 km/h urban average
                results.append({
                    "distance_km": round(dist, 2),
                    "duration_minutes": round(travel, 1),
                    "distance_text": f"{dist:.1f} km",
                    "duration_text": f"{int(travel)} min",
                    "source": "haversine",
                })
        return results

    # ─── Directions + Route ───────────────────────────────────────────────────

    def get_directions(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        waypoints: Optional[List[Tuple[float, float]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get full route details including encoded polyline for map display.
        Returns None if API unavailable or circuit is open.
        """
        if not self.google_api_key or not self._is_api_healthy():
            return None

        cache_key = f"dir:{origin}:{destination}:{waypoints}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        params: Dict[str, Any] = {
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{destination[0]},{destination[1]}",
            "key": self.google_api_key,
            "departure_time": "now",
            "traffic_model": self.traffic_model,
        }

        if waypoints:
            params["waypoints"] = "|".join(f"{lat},{lon}" for lat, lon in waypoints)

        try:
            response = httpx.get(GMAPS_DIRECTIONS_URL, params=params, timeout=8.0)
            response.raise_for_status()
            data = response.json()

            if data.get("routes"):
                route = data["routes"][0]
                leg = route["legs"][0]
                dur_key = "duration_in_traffic" if "duration_in_traffic" in leg else "duration"
                result = {
                    "distance_km": leg["distance"]["value"] / 1000.0,
                    "duration_minutes": leg[dur_key]["value"] / 60.0,
                    "start_address": leg["start_address"],
                    "end_address": leg["end_address"],
                    "polyline": route["overview_polyline"]["points"],
                    "steps": [
                        {
                            "instruction": step.get("html_instructions", ""),
                            "distance_m": step["distance"]["value"],
                            "duration_s": step["duration"]["value"],
                        }
                        for step in leg.get("steps", [])
                    ],
                }
                self._record_api_success()
                self._cache_set(cache_key, result)
                return result
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.warning(f"Google Directions API error: {e}. Circuit breaker updated.")
            self._record_api_failure(e)
        except Exception as e:
            logger.warning(f"Google Directions API unexpected error: {e}")
        return None

    # ─── Geocoding ────────────────────────────────────────────────────────────

    def geocode(self, address: str) -> Optional[Tuple[float, float]]:
        """Convert a street address to (latitude, longitude). Returns None on failure."""
        if not self.google_api_key or not self._is_api_healthy():
            if not self.google_api_key:
                logger.warning("Cannot geocode without GOOGLE_MAPS_API_KEY")
            return None

        cache_key = f"gc:{address}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        try:
            response = httpx.get(
                GMAPS_GEOCODE_URL,
                params={"address": address, "key": self.google_api_key},
                timeout=5.0,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("results"):
                loc = data["results"][0]["geometry"]["location"]
                result = (loc["lat"], loc["lng"])
                self._record_api_success()
                self._cache_set(cache_key, result)
                return result
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.warning(f"Geocode failed for '{address}': {e}")
            self._record_api_failure(e)
        except Exception as e:
            logger.warning(f"Geocode unexpected error for '{address}': {e}")
        return None

    def reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """Convert lat/lon to a formatted address string."""
        if not self.google_api_key or not self._is_api_healthy():
            return None

        cache_key = f"rgc:{lat:.5f},{lon:.5f}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        try:
            response = httpx.get(
                GMAPS_GEOCODE_URL,
                params={"latlng": f"{lat},{lon}", "key": self.google_api_key},
                timeout=5.0,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("results"):
                address = data["results"][0]["formatted_address"]
                self._record_api_success()
                self._cache_set(cache_key, address)
                return address
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.warning(f"Reverse geocode failed: {e}")
            self._record_api_failure(e)
        except Exception as e:
            logger.warning(f"Reverse geocode unexpected error: {e}")
        return None

    # ─── Deep Link URL Generation ─────────────────────────────────────────────

    @staticmethod
    def google_maps_nav_url(
        dest_lat: float,
        dest_lon: float,
        dest_name: Optional[str] = None,
        origin_lat: Optional[float] = None,
        origin_lon: Optional[float] = None,
    ) -> str:
        """
        Generate a Google Maps navigation deep link.
        Works in browser and Android Google Maps app.
        """
        url = f"https://www.google.com/maps/dir/?api=1"
        if origin_lat and origin_lon:
            url += f"&origin={origin_lat},{origin_lon}"
        url += f"&destination={dest_lat},{dest_lon}&travelmode=driving"
        if dest_name:
            url += f"&destination_place_id={quote(dest_name)}"
        return url

    @staticmethod
    def apple_maps_nav_url(
        dest_lat: float,
        dest_lon: float,
        dest_name: Optional[str] = None,
        origin_lat: Optional[float] = None,
        origin_lon: Optional[float] = None,
    ) -> str:
        """
        Generate an Apple Maps navigation deep link.
        Opens native Maps app on iOS/macOS; falls back to web on other platforms.
        """
        if dest_name:
            url = f"maps://?daddr={quote(dest_name)}&dirflg=d"
        else:
            url = f"maps://?daddr={dest_lat},{dest_lon}&dirflg=d"
        if origin_lat and origin_lon:
            url += f"&saddr={origin_lat},{origin_lon}"
        return url

    @staticmethod
    def waze_nav_url(dest_lat: float, dest_lon: float) -> str:
        """Waze navigation deep link as bonus option."""
        return f"https://waze.com/ul?ll={dest_lat},{dest_lon}&navigate=yes"

    # ─── Batch async wrapper ──────────────────────────────────────────────────

    async def get_distance_matrix_async(
        self,
        origins: List[Tuple[float, float]],
        destinations: List[Tuple[float, float]],
    ) -> List[Dict[str, Any]]:
        """Async wrapper for the distance matrix call."""
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self.get_distance_matrix,
            origins,
            destinations,
        )


# ─── Standalone helper ────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
