#!/usr/bin/env python3
"""
Weather data downloader for given coordinates.

Supports providers:
- openweather: Current weather by lat/lon using OpenWeather Current Weather API
- accuweather: Current conditions via AccuWeather (geoposition -> location key -> conditions)
- weatherapi: Current weather using WeatherAPI.com current.json endpoint
- openmeteo: Current weather using Open-Meteo free API (no key)

API Keys (env vars or CLI flags):
- OPENWEATHER_API_KEY
- ACCUWEATHER_API_KEY
- WEATHERAPI_API_KEY

Examples:
  python3 weather_cli.py --provider openweather --coords 37.7749,-122.4194 40.7128,-74.0060 --out results.json
  python3 weather_cli.py --provider accuweather --coords 51.5074,-0.1278 --format csv --out london.csv
  python3 weather_cli.py --provider openmeteo --coords 37.7749,-122.4194
"""

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests


DEFAULT_SAMPLE_COORDS: List[Tuple[float, float]] = [
    (37.7749, -122.4194),  # San Francisco
    (40.7128, -74.0060),   # New York
    (51.5074, -0.1278),    # London
]


class ProviderError(Exception):
    pass


@dataclass
class WeatherReading:
    provider: str
    latitude: float
    longitude: float
    observed_at_unix: Optional[int]
    temperature_c: Optional[float]
    temperature_f: Optional[float]
    humidity_pct: Optional[int]
    pressure_hpa: Optional[float]
    wind_speed_ms: Optional[float]
    wind_direction_deg: Optional[int]
    condition_code: Optional[str]
    condition_text: Optional[str]
    raw: Dict[str, Any]


class OpenWeatherClient:
    """Client for OpenWeather Current Weather Data API.

    Docs: https://openweathermap.org/current
    Endpoint: https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API key}&units=metric
    """

    def __init__(self, api_key: str, session: Optional[requests.Session] = None) -> None:
        if not api_key:
            raise ProviderError("OpenWeather API key is required")
        self.api_key = api_key
        self.session = session or requests.Session()

    def fetch_current(self, latitude: float, longitude: float) -> WeatherReading:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": self.api_key,
            "units": "metric",
        }
        response = self.session.get(url, params=params, timeout=20)
        if response.status_code != 200:
            raise ProviderError(f"OpenWeather error {response.status_code}: {response.text}")
        data = response.json()

        main = data.get("main", {})
        wind = data.get("wind", {})
        weather_arr = data.get("weather", []) or [{}]
        weather0 = weather_arr[0] if weather_arr else {}
        dt_unix = data.get("dt")

        temp_c = main.get("temp")
        temp_f = (temp_c * 9 / 5 + 32) if isinstance(temp_c, (int, float)) else None
        humidity = main.get("humidity")
        pressure = main.get("pressure")
        wind_speed = wind.get("speed")
        wind_deg = wind.get("deg")

        return WeatherReading(
            provider="openweather",
            latitude=latitude,
            longitude=longitude,
            observed_at_unix=dt_unix,
            temperature_c=_ensure_float(temp_c),
            temperature_f=_ensure_float(temp_f),
            humidity_pct=_ensure_int(humidity),
            pressure_hpa=_ensure_float(pressure),
            wind_speed_ms=_ensure_float(wind_speed),
            wind_direction_deg=_ensure_int(wind_deg),
            condition_code=str(weather0.get("id")) if weather0.get("id") is not None else None,
            condition_text=weather0.get("description"),
            raw=data,
        )


class AccuWeatherClient:
    """Client for AccuWeather free APIs.

    Flow:
      1) Use Geoposition Search to get location key
      2) Use Current Conditions API with that key

    Docs:
      - Geoposition Search: https://developer.accuweather.com/accuweather-locations-api/apis/get/locations/v1/cities/geoposition/search
      - Current Conditions: https://developer.accuweather.com/accuweather-current-conditions-api/apis/get/currentconditions/v1/%7BlocationKey%7D
    """

    def __init__(self, api_key: str, session: Optional[requests.Session] = None) -> None:
        if not api_key:
            raise ProviderError("AccuWeather API key is required")
        self.api_key = api_key
        self.session = session or requests.Session()

    def _geoposition_to_location_key(self, latitude: float, longitude: float) -> str:
        url = "https://dataservice.accuweather.com/locations/v1/cities/geoposition/search"
        params = {"apikey": self.api_key, "q": f"{latitude},{longitude}"}
        r = self.session.get(url, params=params, timeout=20)
        if r.status_code != 200:
            raise ProviderError(f"AccuWeather geoposition error {r.status_code}: {r.text}")
        payload = r.json() or {}
        location_key = payload.get("Key")
        if not location_key:
            raise ProviderError("AccuWeather: no location key returned for coordinates")
        return str(location_key)

    def fetch_current(self, latitude: float, longitude: float) -> WeatherReading:
        location_key = self._geoposition_to_location_key(latitude, longitude)
        url = f"https://dataservice.accuweather.com/currentconditions/v1/{location_key}"
        params = {"apikey": self.api_key, "details": "true"}
        r = self.session.get(url, params=params, timeout=20)
        if r.status_code != 200:
            raise ProviderError(f"AccuWeather current conditions error {r.status_code}: {r.text}")
        arr = r.json() or []
        data = arr[0] if arr else {}

        epoch_time = data.get("EpochTime")
        temp_c = _dig(data, "Temperature", "Metric", "Value")
        temp_f = _dig(data, "Temperature", "Imperial", "Value")
        humidity = data.get("RelativeHumidity")
        pressure = _dig(data, "Pressure", "Metric", "Value")
        wind_speed = _dig(data, "Wind", "Speed", "Metric", "Value")
        wind_deg = _dig(data, "Wind", "Direction", "Degrees")
        weather_text = data.get("WeatherText")
        weather_icon = data.get("WeatherIcon")

        return WeatherReading(
            provider="accuweather",
            latitude=latitude,
            longitude=longitude,
            observed_at_unix=_ensure_int(epoch_time),
            temperature_c=_ensure_float(temp_c),
            temperature_f=_ensure_float(temp_f),
            humidity_pct=_ensure_int(humidity),
            pressure_hpa=_ensure_float(pressure),
            wind_speed_ms=_metric_kmh_or_ms_to_ms(wind_speed, unit_hint="kmh"),
            wind_direction_deg=_ensure_int(wind_deg),
            condition_code=str(weather_icon) if weather_icon is not None else None,
            condition_text=weather_text,
            raw=data,
        )


class WeatherAPIClient:
    """Client for WeatherAPI.com current weather.

    Docs: https://www.weatherapi.com/docs/
    Endpoint: https://api.weatherapi.com/v1/current.json?key=KEY&q=LAT,LON
    """

    def __init__(self, api_key: str, session: Optional[requests.Session] = None) -> None:
        if not api_key:
            raise ProviderError("WeatherAPI API key is required")
        self.api_key = api_key
        self.session = session or requests.Session()

    def fetch_current(self, latitude: float, longitude: float) -> WeatherReading:
        url = "https://api.weatherapi.com/v1/current.json"
        params = {"key": self.api_key, "q": f"{latitude},{longitude}"}
        r = self.session.get(url, params=params, timeout=20)
        if r.status_code != 200:
            raise ProviderError(f"WeatherAPI error {r.status_code}: {r.text}")
        data = r.json()
        current = data.get("current", {})

        epoch = current.get("last_updated_epoch")
        temp_c = current.get("temp_c")
        temp_f = current.get("temp_f")
        humidity = current.get("humidity")
        pressure = current.get("pressure_mb")  # millibars ~= hPa
        wind_kph = current.get("wind_kph")
        wind_deg = current.get("wind_degree")
        cond = current.get("condition", {})

        return WeatherReading(
            provider="weatherapi",
            latitude=latitude,
            longitude=longitude,
            observed_at_unix=_ensure_int(epoch),
            temperature_c=_ensure_float(temp_c),
            temperature_f=_ensure_float(temp_f),
            humidity_pct=_ensure_int(humidity),
            pressure_hpa=_ensure_float(pressure),
            wind_speed_ms=_metric_kmh_or_ms_to_ms(wind_kph, unit_hint="kmh"),
            wind_direction_deg=_ensure_int(wind_deg),
            condition_code=str(cond.get("code")) if cond.get("code") is not None else None,
            condition_text=cond.get("text"),
            raw=data,
        )


class OpenMeteoClient:
    """Client for Open-Meteo current weather (no key).

    Docs: https://open-meteo.com/en/docs
    Example: https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&current=temperature_2m,relative_humidity_2m,pressure_msl,wind_speed_10m,wind_direction_10m&wind_speed_unit=ms
    """

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()

    def fetch_current(self, latitude: float, longitude: float) -> WeatherReading:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,pressure_msl,wind_speed_10m,wind_direction_10m",
            "wind_speed_unit": "ms",
        }
        r = self.session.get(url, params=params, timeout=20)
        if r.status_code != 200:
            raise ProviderError(f"Open-Meteo error {r.status_code}: {r.text}")
        data = r.json()
        cur = data.get("current", {})

        temp_c = cur.get("temperature_2m")
        humidity = cur.get("relative_humidity_2m")
        pressure = cur.get("pressure_msl")
        wind_speed_ms = cur.get("wind_speed_10m")
        wind_deg = cur.get("wind_direction_10m")

        return WeatherReading(
            provider="openmeteo",
            latitude=latitude,
            longitude=longitude,
            observed_at_unix=None,
            temperature_c=_ensure_float(temp_c),
            temperature_f=_c_to_f(temp_c),
            humidity_pct=_ensure_int(humidity),
            pressure_hpa=_ensure_float(pressure),
            wind_speed_ms=_ensure_float(wind_speed_ms),
            wind_direction_deg=_ensure_int(wind_deg),
            condition_code=None,
            condition_text=None,
            raw=data,
        )


def _dig(obj: Dict[str, Any], *keys: str) -> Optional[Any]:
    cur: Any = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
        if cur is None:
            return None
    return cur


def _ensure_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _ensure_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _metric_kmh_or_ms_to_ms(value: Any, unit_hint: str = "mps") -> Optional[float]:
    v = _ensure_float(value)
    if v is None:
        return None
    if unit_hint == "mps":
        return v
    return v / 3.6


def _c_to_f(value: Any) -> Optional[float]:
    v = _ensure_float(value)
    if v is None:
        return None
    return v * 9 / 5 + 32


def parse_coords(raw_list: List[str]) -> List[Tuple[float, float]]:
    coords: List[Tuple[float, float]] = []
    for item in raw_list:
        parts = item.split(",")
        if len(parts) != 2:
            raise ValueError(f"Invalid coordinate '{item}'. Expected 'lat,lon'.")
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
        coords.append((lat, lon))
    return coords


def parse_coords_file(path: str) -> List[Tuple[float, float]]:
    coords: List[Tuple[float, float]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split(",")
            if len(parts) != 2:
                raise ValueError(f"Invalid line in coords file: '{line.strip()}'")
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            coords.append((lat, lon))
    return coords


def to_serializable(reading: WeatherReading) -> Dict[str, Any]:
    return {
        "provider": reading.provider,
        "latitude": reading.latitude,
        "longitude": reading.longitude,
        "observed_at_unix": reading.observed_at_unix,
        "temperature_c": reading.temperature_c,
        "temperature_f": reading.temperature_f,
        "humidity_pct": reading.humidity_pct,
        "pressure_hpa": reading.pressure_hpa,
        "wind_speed_ms": reading.wind_speed_ms,
        "wind_direction_deg": reading.wind_direction_deg,
        "condition_code": reading.condition_code,
        "condition_text": reading.condition_text,
        "raw": reading.raw,
    }


def write_output(
    readings: List[WeatherReading],
    fmt: str,
    output_path: Optional[str],
) -> None:
    records = [to_serializable(r) for r in readings]
    if fmt == "json":
        text = json.dumps(records, indent=2, sort_keys=False)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text)
        else:
            print(text)
    elif fmt == "csv":
        fieldnames = [
            "provider",
            "latitude",
            "longitude",
            "observed_at_unix",
            "temperature_c",
            "temperature_f",
            "humidity_pct",
            "pressure_hpa",
            "wind_speed_ms",
            "wind_direction_deg",
            "condition_code",
            "condition_text",
        ]
        dest = open(output_path, "w", newline="", encoding="utf-8") if output_path else sys.stdout
        close_after = dest is not sys.stdout
        writer = csv.DictWriter(dest, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            writer.writerow({k: rec.get(k) for k in fieldnames})
        if close_after:
            dest.close()
    else:
        raise ValueError(f"Unsupported format: {fmt}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download weather for coordinates")
    parser.add_argument(
        "--provider",
        required=True,
        choices=["openweather", "accuweather", "weatherapi", "openmeteo"],
        help="Weather provider to use",
    )
    parser.add_argument(
        "--coords",
        nargs="*",
        default=[],
        help="List of 'lat,lon' pairs. If omitted, uses sample coords.",
    )
    parser.add_argument(
        "--coords-file",
        default=None,
        help="Path to a text file with one 'lat,lon' per line (supports # comments)",
    )
    parser.add_argument(
        "--format",
        default="json",
        choices=["json", "csv"],
        help="Output format",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output file path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--openweather-api-key",
        default=os.getenv("OPENWEATHER_API_KEY"),
        help="Override OpenWeather API key (or set OPENWEATHER_API_KEY)",
    )
    parser.add_argument(
        "--accuweather-api-key",
        default=os.getenv("ACCUWEATHER_API_KEY"),
        help="Override AccuWeather API key (or set ACCUWEATHER_API_KEY)",
    )
    parser.add_argument(
        "--weatherapi-api-key",
        default=os.getenv("WEATHERAPI_API_KEY"),
        help="Override WeatherAPI API key (or set WEATHERAPI_API_KEY)",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Optional delay between requests to avoid rate limits",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    coords: List[Tuple[float, float]]
    if args.coords_file:
        coords = parse_coords_file(args.coords_file)
    else:
        coords = parse_coords(args.coords) if args.coords else DEFAULT_SAMPLE_COORDS

    if args.provider == "openweather":
        client = OpenWeatherClient(api_key=args.openweather_api_key)
    elif args.provider == "accuweather":
        client = AccuWeatherClient(api_key=args.accuweather_api_key)
    elif args.provider == "weatherapi":
        client = WeatherAPIClient(api_key=args.weatherapi_api_key)
    elif args.provider == "openmeteo":
        client = OpenMeteoClient()
    else:
        parser.error("Unsupported provider")
        return 2

    readings: List[WeatherReading] = []
    for idx, (lat, lon) in enumerate(coords):
        reading = client.fetch_current(lat, lon)
        readings.append(reading)
        if args.delay_seconds and idx < len(coords) - 1:
            time.sleep(args.delay_seconds)

    write_output(readings, args.format, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
