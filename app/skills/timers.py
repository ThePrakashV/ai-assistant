import re
import time
from datetime import datetime, timedelta

import dateparser

from app.nlu.entities import _replace_number_words
from app.skills.context import SkillContext

MAX_TIMER_SECONDS = 7 * 24 * 3600  # 1 week

_EXPLICIT_DAY_RE = re.compile(
    r"\b(today|tomorrow|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"ago|next|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)\b|\d{1,2}[/-]\d{1,2}",
    re.IGNORECASE,
)


def spoken_duration(seconds: int) -> str:
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    return " ".join(parts) or "0 seconds"


# ===================== Timer =====================
async def timer_skill(text: str, entities: dict, ctx: SkillContext) -> str | None:
    if ctx.scheduler is None:
        return None

    if re.search(r"\b(cancel|stop|delete|remove|clear)\b", text.lower()):
        count = ctx.scheduler.cancel_all("timer")
        if count == 0:
            return "You have no active timers."
        return "Okay, I cancelled your timer." if count == 1 else f"Okay, I cancelled {count} timers."

    seconds = entities.get("duration_seconds")
    if not seconds:
        return "I did not catch how long. Try saying, set a timer for 5 minutes."
    if seconds > MAX_TIMER_SECONDS:
        return "That timer is too long. I can set timers up to one week."

    label = (entities.get("label") or "").strip()
    ctx.scheduler.add("timer", label, time.time() + seconds)

    if label:
        return f"Okay, {spoken_duration(seconds)} timer for {label} is set."
    return f"Okay, timer set for {spoken_duration(seconds)}."


# ===================== Reminder / Alarm =====================
def _normalize_time_text(raw: str) -> str:
    """'6 in the morning', 'six pm', 'tomorrow morning' -> dateparser ku purira format."""
    s = _replace_number_words(raw.lower())
    s = s.replace("a.m.", "am").replace("p.m.", "pm")
    s = re.sub(r"(\d)\s*o'?clock", r"\1", s)
    s = re.sub(r"(\d+(?::\d+)?)\s*(?:in the |at )?morning", r"\1 am", s)
    s = re.sub(r"(\d+(?::\d+)?)\s*(?:in the |at )?(?:afternoon|evening|night)", r"\1 pm", s)
    if not re.search(r"\d", s):
        for word, replacement in (
            ("morning", "9 am"),
            ("afternoon", "3 pm"),
            ("evening", "6 pm"),
            ("tonight", "9 pm"),
            ("night", "9 pm"),
            ("noon", "12 pm"),
        ):
            if word in s:
                s = s.replace(word, replacement)
                break
    return s.strip()


def _parse_when(raw: str) -> datetime | None:
    normalized = _normalize_time_text(raw)
    now = datetime.now()
    parsed = dateparser.parse(
        normalized, settings={"PREFER_DATES_FROM": "future", "RELATIVE_BASE": now}
    )
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    # "6 pm" nu sonnaa, ippo 7 pm na naalaikku 6 pm
    if parsed <= now and not _EXPLICIT_DAY_RE.search(normalized):
        parsed += timedelta(days=1)
    return parsed


def _spoken_when(moment: datetime) -> str:
    clock = moment.strftime("%I:%M %p").lstrip("0")
    days = (moment.date() - datetime.now().date()).days
    if days == 0:
        day = "today"
    elif days == 1:
        day = "tomorrow"
    else:
        day = moment.strftime("%A, %d %B")
    return f"{clock} {day}"


def _you(task: str) -> str:
    """'take my medicine' -> 'take your medicine' (Nova unnai paathu pesum bodhu)."""
    task = re.sub(r"\bmy\b", "your", task, flags=re.IGNORECASE)
    task = re.sub(r"\bmyself\b", "yourself", task, flags=re.IGNORECASE)
    return re.sub(r"\bme\b", "you", task, flags=re.IGNORECASE)


async def reminder_skill(text: str, entities: dict, ctx: SkillContext) -> str | None:
    if ctx.scheduler is None:
        return None

    is_alarm = bool(re.search(r"\b(alarm|wake me)\b", text.lower()))
    task = (entities.get("task") or "").strip().rstrip(".")
    time_text = (entities.get("time") or "").strip()

    if not time_text:
        if is_alarm:
            return "What time should I set the alarm for?"
        return "When should I remind you? Try saying, remind me to call mom at 6 pm."

    moment = _parse_when(time_text)
    if moment is None:
        return "I could not understand the time. Try saying, remind me to call mom at 6 pm."
    if moment <= datetime.now():
        return "That time has already passed."

    if is_alarm and not task:
        ctx.scheduler.add("alarm", "alarm", moment.timestamp())
        return f"Okay, alarm set for {_spoken_when(moment)}."

    if not task:
        return "What should I remind you about? Try saying, remind me to call mom at 6 pm."

    ctx.scheduler.add("reminder", _you(task), moment.timestamp())
    return f"Okay, I will remind you to {_you(task)} at {_spoken_when(moment)}."