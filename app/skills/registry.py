import re

from app.security.access import check_permission
from app.security.audit import audit_event
from app.skills.basic import calculator_skill, settings_skill, time_date_skill, unit_skill
from app.skills.timers import reminder_skill, timer_skill
from app.skills.web import currency_skill, search_skill, weather_skill


async def music_skill(text, entities, ctx):
    return "I cannot control music yet. That feature is coming in a later phase."


async def smart_home_skill(text, entities, ctx):
    return "I cannot control smart home devices yet. That feature is coming in a later phase."


# Intent -> skill function. Puthu skill add panna inga oru line + skill function.
_RAW_SKILLS = {
    "weather": weather_skill,
    "set_timer": timer_skill,
    "set_reminder": reminder_skill,
    "calculator": calculator_skill,
    "unit_conversion": unit_skill,
    "currency_conversion": currency_skill,
    "web_search": search_skill,
    "time_date": time_date_skill,
    "assistant_settings": settings_skill,
    "play_music": music_skill,
    "smart_home": smart_home_skill,
}


def _with_permission(name: str, skill):
    """Ovvoru skill kum munnaadi permission check. Deny aana skill run aagaadhu, audit la record aagum."""

    async def wrapper(text, entities, ctx):
        denial = check_permission(name)
        if denial:
            audit_event("permission.denied", actor="agent", skill=name)
            return denial
        return await skill(text, entities, ctx)

    return wrapper


SKILLS = {name: _with_permission(name, skill) for name, skill in _RAW_SKILLS.items()}

# Guard: intent sariyaa irundhaalum, sentence la indha words irundha mattum skill run aagum.
# ("What is my name?" ku date solla koodaadhu.) Guard illaadha intents (calculator, units,
# currency) skill kulla thaane validate pannum.
_GUARD_PATTERNS = {
    "weather": r"\b(weather|rain|raining|rainy|temperature|hot|cold|sunny|cloudy|forecast|umbrella|humid|humidity|windy|wind|mazhai)\b",
    "time_date": r"\b(time|date|day|month|year|clock)\b",
    "set_timer": r"\b(timer|countdown|stopwatch)\b",
    "set_reminder": r"\b(remind|reminder|alarm|wake)\b",
    "web_search": r"\b(search|google|look ?up|wikipedia|find (?:out|information|info))\b",
    "assistant_settings": r"\b(speak|talk|voice|volume|louder|quieter|faster|slower|speed|loud|quiet|softer)\b",
    "play_music": r"\b(play|song|songs|music|playlist|pause|skip|spotify|youtube|resume)\b",
    "smart_home": r"\b(turn|switch|light|lights|fan|ac|tv|lock|unlock|dim|thermostat)\b",
}
GUARDS = {intent: re.compile(pattern, re.IGNORECASE) for intent, pattern in _GUARD_PATTERNS.items()}