import re
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.skills.basic import fmt_number, parse_number
from app.skills.context import SkillContext

HEADERS = {"User-Agent": "NovaAssistant/0.1 (personal learning project)"}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=settings.http_timeout, headers=HEADERS)


# ===================== Weather (Open-Meteo) =====================
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "heavy rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "a thunderstorm", 96: "a thunderstorm with hail", 99: "a thunderstorm with hail",
}


def _day_offset(text: str) -> int:
    lowered = text.lower()
    if "day after tomorrow" in lowered:
        return 2
    if "tomorrow" in lowered or "naalaikku" in lowered:
        return 1
    return 0


async def weather_skill(text: str, entities: dict, ctx: SkillContext) -> str | None:
    place = (entities.get("location") or "").strip() or settings.default_location
    offset = _day_offset(text)

    try:
        async with _client() as client:
            geo = await client.get(
                GEOCODE_URL,
                params={"name": place, "count": 1, "language": "en", "format": "json"},
            )
            geo.raise_for_status()
            results = geo.json().get("results") or []
            if not results:
                return f"I could not find a place called {place}."
            spot = results[0]

            forecast = await client.get(
                FORECAST_URL,
                params={
                    "latitude": spot["latitude"],
                    "longitude": spot["longitude"],
                    "current": "temperature_2m,weather_code",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto",
                    "forecast_days": 3,
                },
            )
            forecast.raise_for_status()
            data = forecast.json()
    except httpx.HTTPError:
        return "I could not reach the weather service right now."

    name = spot["name"]
    daily = data["daily"]
    high = round(daily["temperature_2m_max"][offset])
    low = round(daily["temperature_2m_min"][offset])
    rain = daily["precipitation_probability_max"][offset]
    description = WEATHER_CODES.get(daily["weather_code"][offset], "mixed weather")

    if offset == 0:
        current = data["current"]
        now_temp = round(current["temperature_2m"])
        now_desc = WEATHER_CODES.get(current["weather_code"], "mixed weather")
        reply = (
            f"In {name} it is {now_temp} degrees Celsius right now, with {now_desc}. "
            f"Today's high is {high} and the low is {low}."
        )
    else:
        when = "tomorrow" if offset == 1 else "the day after tomorrow"
        reply = f"For {when} in {name}: {description}, with a high of {high} and a low of {low}."

    if rain is not None:
        reply += f" The chance of rain is {rain} percent."
    return reply


# ===================== Currency (Frankfurter / ECB) =====================
CURRENCY_URL = "https://api.frankfurter.dev/v1/latest"

CURRENCY_ALIASES = {
    "usd": "USD", "dollar": "USD", "dollars": "USD", "us dollar": "USD", "us dollars": "USD",
    "inr": "INR", "rupee": "INR", "rupees": "INR",
    "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "gbp": "GBP", "pound": "GBP", "pounds": "GBP",
    "jpy": "JPY", "yen": "JPY",
    "cny": "CNY", "yuan": "CNY",
    "chf": "CHF", "franc": "CHF", "francs": "CHF",
    "aud": "AUD", "australian dollar": "AUD", "australian dollars": "AUD",
    "cad": "CAD", "canadian dollar": "CAD", "canadian dollars": "CAD",
    "sgd": "SGD", "singapore dollar": "SGD", "singapore dollars": "SGD",
}
CURRENCY_NAMES = {
    "USD": "US dollars", "INR": "Indian rupees", "EUR": "euros", "GBP": "British pounds",
    "JPY": "Japanese yen", "CNY": "Chinese yuan", "CHF": "Swiss francs",
    "AUD": "Australian dollars", "CAD": "Canadian dollars", "SGD": "Singapore dollars",
}
_CURRENCY_WORD_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, CURRENCY_ALIASES), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _resolve_currency(value) -> str | None:
    if not value:
        return None
    cleaned = str(value).strip().lower()
    if cleaned in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[cleaned]
    if re.fullmatch(r"[a-z]{3}", cleaned):
        return cleaned.upper()
    return None


def _currencies_in_text(text: str) -> list[str]:
    found: list[str] = []
    for match in _CURRENCY_WORD_RE.finditer(text):
        code = CURRENCY_ALIASES[match.group(1).lower()]
        if not found or found[-1] != code:
            found.append(code)
    return found


def _currency_name(code: str) -> str:
    return CURRENCY_NAMES.get(code, code)


async def currency_skill(text: str, entities: dict, ctx: SkillContext) -> str | None:
    source = _resolve_currency(entities.get("from_currency"))
    target = _resolve_currency(entities.get("to_currency"))

    if not (source and target):
        found = _currencies_in_text(text)
        if len(found) >= 2:
            source, target = found[0], found[1]
        elif len(found) == 1 and found[0] != settings.home_currency:
            source, target = found[0], settings.home_currency  # "dollar rate" -> INR
        else:
            return None

    if source == target:
        return None

    amount = parse_number(entities.get("amount"))
    if amount is None:
        amount = parse_number(text)
    if amount is None:
        amount = 1.0

    try:
        async with _client() as client:
            response = await client.get(CURRENCY_URL, params={"base": source, "symbols": target})
            response.raise_for_status()
            rate = response.json()["rates"][target]
    except httpx.HTTPStatusError:
        return "I could not find exchange rates for that currency pair."
    except (httpx.HTTPError, KeyError, ValueError):
        return "I could not reach the exchange rate service right now."

    converted = amount * rate
    return (
        f"{fmt_number(amount)} {_currency_name(source)} is about {converted:,.2f} "
        f"{_currency_name(target)}, based on the latest reference rate."
    )


# ===================== Search (Wikipedia) =====================
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"


def _strip_search_words(text: str) -> str:
    cleaned = re.sub(
        r"^(?:please\s+)?(?:search(?: the web)?(?: online)?(?: for)?|google|look ?up|find(?: out)?(?: about)?)\s+",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )
    return cleaned.strip(" ?.!")


async def search_skill(text: str, entities: dict, ctx: SkillContext) -> str | None:
    query = (entities.get("query") or "").strip() or _strip_search_words(text)
    if not query:
        return None

    try:
        async with _client() as client:
            found = await client.get(
                WIKI_API,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 1,
                    "format": "json",
                },
            )
            found.raise_for_status()
            hits = found.json().get("query", {}).get("search", [])
            if not hits:
                return f"I could not find anything about {query}."

            title = hits[0]["title"]
            summary = await client.get(WIKI_SUMMARY + quote(title.replace(" ", "_"), safe=""))
            summary.raise_for_status()
            extract = summary.json().get("extract", "")
    except httpx.HTTPError:
        return "I could not reach the search service right now."

    if not extract:
        return f"I found a page called {title}, but it has no summary."

    sentences = re.split(r"(?<=[.!?])\s+", extract)
    short = " ".join(sentences[:2])[:400]
    return f"Here is what Wikipedia says about {title}. {short}"