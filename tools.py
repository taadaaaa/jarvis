"""Things Jarvis can DO, not just say.

Each tool is a schema in DEFINITIONS (Anthropic format; converted for
Ollama) plus a plain python function. Add a tool by writing a function,
registering it in _FUNCS, and describing it in DEFINITIONS - descriptions
are what the model reads to decide when to use it.

Tool results are returned as strings and fed back to the model, which then
answers out loud. Keep results short: they end up in the context window.
"""

import subprocess

import requests

# Wikipedia rejects requests without a descriptive User-Agent.
_HEADERS = {"User-Agent": "Jarvis-voice-assistant/1.0 (personal project)"}

# WMO weather interpretation codes (open-meteo uses these)
_WEATHER_CODES = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "heavy freezing rain", 71: "light snow",
    73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers",
    81: "showers", 82: "violent showers", 85: "snow showers",
    86: "heavy snow showers", 95: "thunderstorm",
    96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


def open_app(app_name: str) -> str:
    r = subprocess.run(
        ["open", "-a", app_name], capture_output=True, text=True, timeout=10
    )
    if r.returncode == 0:
        return f"Opened {app_name}."
    return f"Could not open {app_name}: {r.stderr.strip() or 'app not found'}"


def read_clipboard() -> str:
    out = subprocess.run(
        ["pbpaste"], capture_output=True, text=True, timeout=5
    ).stdout
    if not out.strip():
        return "The clipboard is empty."
    return out[:2000]


def set_volume(percent: int) -> str:
    percent = max(0, min(100, int(percent)))
    subprocess.run(
        ["osascript", "-e", f"set volume output volume {percent}"], timeout=5
    )
    return f"Volume set to {percent} percent."


def get_weather(location: str) -> str:
    geo = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1},
        timeout=10,
    ).json()
    if not geo.get("results"):
        return f"Could not find a place called {location}."
    spot = geo["results"][0]
    w = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": spot["latitude"],
            "longitude": spot["longitude"],
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "forecast_days": 1,
            "timezone": "auto",
        },
        timeout=10,
    ).json()
    cur, day = w["current"], w["daily"]
    sky = _WEATHER_CODES.get(cur["weather_code"], "unknown conditions")
    return (
        f"Weather in {spot['name']}: {sky}, {round(cur['temperature_2m'])}F "
        f"(feels like {round(cur['apparent_temperature'])}F), wind "
        f"{round(cur['wind_speed_10m'])} mph. Today: high "
        f"{round(day['temperature_2m_max'][0])}F, low "
        f"{round(day['temperature_2m_min'][0])}F, "
        f"{day['precipitation_probability_max'][0]}% chance of precipitation."
    )


def search_wikipedia(query: str) -> str:
    hits = requests.get(
        "https://en.wikipedia.org/w/rest.php/v1/search/page",
        params={"q": query, "limit": 1},
        headers=_HEADERS,
        timeout=10,
    ).json()
    if not hits.get("pages"):
        return f"No Wikipedia article found for {query}."
    key = hits["pages"][0]["key"]
    page = requests.get(
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{key}",
        headers=_HEADERS,
        timeout=10,
    ).json()
    extract = page.get("extract", "No summary available.")
    return f"Wikipedia ({page.get('title', key)}): {extract[:1500]}"


DEFINITIONS = [
    {
        "name": "open_app",
        "description": "Open a macOS application by name, e.g. Safari, Spotify, Notes, Calculator.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "The application's name"}
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "read_clipboard",
        "description": "Read the text currently on the user's clipboard. Use when they mention 'my clipboard' or 'what I copied'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_volume",
        "description": "Set the Mac's output volume, 0 (mute) to 100 (max).",
        "input_schema": {
            "type": "object",
            "properties": {
                "percent": {"type": "integer", "description": "Volume 0-100"}
            },
            "required": ["percent"],
        },
    },
    {
        "name": "get_weather",
        "description": "Get current weather and today's forecast for a city or place.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City or place name"}
            },
            "required": ["location"],
        },
    },
    {
        "name": "search_wikipedia",
        "description": "Look up a person, place, event, or thing on Wikipedia. Use for factual questions you are not sure about.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Topic to look up"}
            },
            "required": ["query"],
        },
    },
]

_FUNCS = {
    "open_app": open_app,
    "read_clipboard": read_clipboard,
    "set_volume": set_volume,
    "get_weather": get_weather,
    "search_wikipedia": search_wikipedia,
}


def execute(name: str, args: dict) -> str:
    """Run a tool and always return a string the model can work with."""
    fn = _FUNCS.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    try:
        return str(fn(**(args or {})))[:4000]
    except Exception as e:
        return f"Tool {name} failed: {e}"


def anthropic_tools():
    return DEFINITIONS


def ollama_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": d["name"],
                "description": d["description"],
                "parameters": d["input_schema"],
            },
        }
        for d in DEFINITIONS
    ]
