from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from pathlib import Path
import sys
import os

# Reuse provider clients from the CLI module
BASE_DIR = Path(__file__).resolve().parents[2]
CLI_PATH = BASE_DIR / "weather_cli.py"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from weather_cli import (
        OpenWeatherClient,
        AccuWeatherClient,
        WeatherAPIClient,
        OpenMeteoClient,
        parse_coords,
        to_serializable,
        ProviderError,
    )
except Exception:  # pragma: no cover
    OpenWeatherClient = AccuWeatherClient = WeatherAPIClient = OpenMeteoClient = None
    parse_coords = to_serializable = None
    class ProviderError(Exception):
        pass


@api_view(["GET"])
def weather(request):
    provider = request.query_params.get("provider", "openmeteo").lower()
    coords_param = request.query_params.getlist("coords") or request.query_params.get("coords", "")
    if isinstance(coords_param, str):
        coords_list = coords_param.split() if coords_param else []
    else:
        coords_list = coords_param

    try:
        coords = parse_coords(coords_list) if coords_list else [(37.7749, -122.4194)]
    except Exception as e:
        return Response({"error": f"invalid coords: {e}"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        if provider == "openweather":
            client = OpenWeatherClient(api_key=os.getenv("OPENWEATHER_API_KEY", ""))
        elif provider == "accuweather":
            client = AccuWeatherClient(api_key=os.getenv("ACCUWEATHER_API_KEY", ""))
        elif provider == "weatherapi":
            client = WeatherAPIClient(api_key=os.getenv("WEATHERAPI_API_KEY", ""))
        elif provider == "openmeteo":
            client = OpenMeteoClient()
        else:
            return Response({"error": "unsupported provider"}, status=status.HTTP_400_BAD_REQUEST)

        readings = [to_serializable(client.fetch_current(lat, lon)) for (lat, lon) in coords]
        return Response(readings)
    except ProviderError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:  # pragma: no cover
        return Response({"error": f"unexpected error: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Create your views here.
