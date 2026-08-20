"""Things Jarvis can DO, not just say.

Each tool is a schema in DEFINITIONS (Anthropic format; converted for
Ollama) plus a plain python function. Add a tool by writing a function,
registering it in _FUNCS, and describing it in DEFINITIONS - descriptions
are what the model reads to decide when to use it.

Tool results are returned as strings and fed back to the model, which then
answers out loud. Keep results short: they end up in the context window.
"""

import os
import re
import subprocess

import requests

# Wikipedia rejects requests without a descriptive User-Agent.
_HEADERS = {"User-Agent": "Jarvis-voice-assistant/1.0 (personal project)"}

# Set by app.py so the switch_brain tool can reconfigure the live Brain.
SWITCH_BRAIN_HOOK = None

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


def look_at_screen(question: str) -> str:
    import vision

    return vision.describe_screen(question)


def open_url(url: str) -> str:
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    r = subprocess.run(["open", url], capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        return f"Opened {url} in the browser."
    return f"Could not open {url}: {r.stderr.strip() or 'unknown error'}"


def get_browser_tab() -> str:
    for app_name, script in (
        (
            "Google Chrome",
            'tell application "Google Chrome" to get {title, URL} of active tab of front window',
        ),
        (
            "Safari",
            'tell application "Safari" to get {name, URL} of front document',
        ),
    ):
        try:
            r = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                title, _, url = r.stdout.strip().rpartition(", ")
                return f"Current browser tab: {title} — {url}"
        except Exception:
            continue
    return "Could not find an open browser tab (is Chrome or Safari running?)."


def search_web(query: str) -> str:
    try:
        r = requests.get(
            "https://lite.duckduckgo.com/lite/",
            params={"q": query},
            headers=_HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        hits = re.findall(
            r'<a rel="nofollow" href="([^"]+)"[^>]*>(.*?)</a>', r.text
        )
        lines = []
        for url, title in hits[:5]:
            title = re.sub(r"<[^>]+>", "", title).strip()
            if title:
                lines.append(f"{title} — {url}")
        return "\n".join(lines) or "No web results found."
    except Exception as e:
        return f"Web search failed: {e}"


def search_files(query: str, limit: int = 8) -> str:
    def _mdfind(args):
        r = subprocess.run(
            ["mdfind"] + args, capture_output=True, text=True, timeout=15
        )
        return [p for p in r.stdout.splitlines() if p.strip()]

    paths = _mdfind(["-name", query]) or _mdfind([query])
    if not paths:
        return f"No files found matching {query}."
    lines = [
        f"{os.path.basename(p)} — {p}" for p in paths[: int(limit)]
    ]
    return "\n".join(lines)


def read_text_file(path: str) -> str:
    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return f"No file found at {path}."
    with open(path, "rb") as fp:
        head = fp.read(1024)
    if b"\x00" in head:
        return f"{os.path.basename(path)} is not a text file I can read."
    with open(path, "r", errors="replace") as fp:
        return fp.read(3000)


def switch_brain(target: str) -> str:
    if SWITCH_BRAIN_HOOK is None:
        return "Brain switching is not wired up."
    return str(SWITCH_BRAIN_HOOK(target))


DEFINITIONS = [
    {
        "name": "look_at_screen",
        "description": (
            "Look at the user's screen and answer a question about what is "
            "visible. Use whenever the user asks about anything on screen: "
            "'what's on my screen', a video they're watching, a game, an "
            "error dialog, a document, a website."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "What to figure out from the screen",
                }
            },
            "required": ["question"],
        },
    },
    {
        "name": "open_url",
        "description": "Open a web page in the user's default browser.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to open"}},
            "required": ["url"],
        },
    },
    {
        "name": "get_browser_tab",
        "description": (
            "Get the title and URL of the browser tab the user currently has "
            "open (Chrome or Safari). Use when they mention 'this page', "
            "'this video', or 'what I'm looking at' in the browser."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_web",
        "description": "Search the web and return the top result titles and links.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_files",
        "description": (
            "Search the user's Mac for files by name or content (Spotlight). "
            "Use when they ask to find a file, document, download, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "File name or keywords"},
                "limit": {"type": "integer", "description": "Max results (default 8)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_text_file",
        "description": "Read the contents of a text file at a given path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or ~ path"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "switch_brain",
        "description": (
            "Switch which AI model powers Jarvis. Target can be 'claude', "
            "'ollama', or an Ollama model name like 'llama3.1' or "
            "'gemma3:4b'. Use when the user asks to switch models/brains."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Provider or model name"}
            },
            "required": ["target"],
        },
    },
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
    "look_at_screen": look_at_screen,
    "open_url": open_url,
    "get_browser_tab": get_browser_tab,
    "search_web": search_web,
    "search_files": search_files,
    "read_text_file": read_text_file,
    "switch_brain": switch_brain,
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
