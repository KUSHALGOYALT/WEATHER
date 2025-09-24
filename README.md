## Weather downloader CLI

Fetch current weather by latitude/longitude from OpenWeather, AccuWeather, WeatherAPI, or Open‑Meteo.

### Setup

1. Create a Python 3.9+ virtualenv (optional).
2. Install deps:

```bash
pip install -r requirements.txt
```

3. Set API keys via env or `.env` file (only needed for OpenWeather/AccuWeather/WeatherAPI):

- `OPENWEATHER_API_KEY`
- `ACCUWEATHER_API_KEY`
- `WEATHERAPI_API_KEY`

You can copy `.env.example` to `.env` and fill the values.

### Usage

- OpenWeather:

```bash
python3 weather_cli.py --provider openweather --coords 37.7749,-122.4194 40.7128,-74.0060 --out openweather.json
```

- AccuWeather:

```bash
python3 weather_cli.py --provider accuweather --coords 51.5074,-0.1278 --format csv --out london.csv
```

- WeatherAPI:

```bash
python3 weather_cli.py --provider weatherapi --coords 28.6139,77.2090 --out delhi.json
```

- Open‑Meteo (no API key required):

```bash
python3 weather_cli.py --provider openmeteo --coords 37.7749,-122.4194
```

If `--coords` is omitted, the script uses sample coords (SF, NYC, London).

Add `--delay-seconds 1.0` to be gentle with rate limits when querying many points.

### Output

- `--format json` (default): array of normalized readings, including a `raw` object with the full provider payload.
- `--format csv`: selected normalized fields only.

### Providers and free tier notes

- OpenWeather: Current Weather endpoint. See `https://openweathermap.org/current`.
- AccuWeather: Geoposition Search → Current Conditions. See `https://developer.accuweather.com`.
- WeatherAPI: Current weather; see [WeatherAPI login/signup](https://www.weatherapi.com/my/).
- Open‑Meteo: Free, no key; see `https://open-meteo.com`.

### Notes

- The CLI normalizes common fields (temp, humidity, wind, etc.) and retains full `raw` data for reference.
- AccuWeather/WeatherAPI wind speeds are converted from km/h to m/s.
- Extendable: add more providers by implementing a client with `fetch_current(lat, lon)` returning `WeatherReading`.
