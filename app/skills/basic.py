import ast
import math
import operator
import re
from datetime import datetime, timedelta

from app.nlu.entities import _replace_number_words
from app.skills.context import SkillContext


# ===================== Helpers =====================
def fmt_number(x: float) -> str:
    """Voice ku ethamaadhiri number format. 8.0 -> '8', 0.33333 -> '0.3333'."""
    if isinstance(x, int):
        return str(x)
    if abs(x - round(x)) < 1e-9 and abs(x) < 1e15:
        return str(int(round(x)))
    if abs(x) >= 1e6 or abs(x) < 1e-3:
        return f"{x:.6g}"
    return f"{x:.4f}".rstrip("0").rstrip(".")


def parse_number(raw) -> float | None:
    """'5', 'five', '1,200', 'about 3.5' -> float. Puriyala na None."""
    if raw is None:
        return None
    text = _replace_number_words(str(raw).lower()).replace(",", "")
    try:
        return float(text)
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group()) if match else None


# ===================== Time / Date =====================
async def time_date_skill(text: str, entities: dict, ctx: SkillContext) -> str | None:
    now = datetime.now()
    lowered = text.lower()

    if re.search(r"\b(time|clock)\b", lowered):
        return f"It is {now.strftime('%I:%M %p').lstrip('0')}."
    if "tomorrow" in lowered:
        return f"Tomorrow is {(now + timedelta(days=1)).strftime('%A, %d %B %Y')}."
    if "month" in lowered:
        return f"It is {now.strftime('%B %Y')}."
    if "year" in lowered:
        return f"It is {now.year}."
    return f"Today is {now.strftime('%A, %d %B %Y')}."


# ===================== Calculator =====================
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round}
_CONSTS = {"pi": math.pi, "e": math.e}

_WORD_OPS = [
    (r"\bto the power of\b", "**"),
    (r"\bsquared\b", "**2"),
    (r"\bcubed\b", "**3"),
    (r"\bmultiplied by\b", "*"),
    (r"\btimes\b", "*"),
    (r"\bdivided by\b", "/"),
    (r"\bover\b", "/"),
    (r"\bplus\b", "+"),
    (r"\bminus\b", "-"),
    (r"\bmodulo\b", "%"),
]


def _eval(node):
    """Safe evaluator: numbers + (+ - * / // % **) + sqrt/abs/round mattum. Vera edhuvum anumadhi illa."""
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too big")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCS
        and not node.keywords
        and len(node.args) <= 2
    ):
        return _FUNCS[node.func.id](*[_eval(arg) for arg in node.args])
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    raise ValueError("not allowed")


def safe_eval(expression: str):
    return _eval(ast.parse(expression, mode="eval"))


def _clean_expression(expr: str) -> str:
    expr = expr.lower().replace("×", "*").replace("÷", "/").replace("^", "**").replace(",", "")
    expr = re.sub(r"(\d)\s*x\s*(\d)", r"\1*\2", expr)
    expr = re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s*of\s*(\d+(?:\.\d+)?)", r"(\1/100)*\2", expr
    )
    return expr.strip().rstrip("?.=! ")


def _expression_from_text(text: str) -> str:
    """LLM expression thappa kuduthaa, user sentence la irundhu namma thaane expression ah eduthukkurom."""
    s = _replace_number_words(text.lower())
    s = re.sub(r"^(?:please\s+)?(?:what is|what's|calculate|compute|how much is|tell me)\s+", "", s)
    s = s.strip(" ?.!")
    s = re.sub(r"^add\s+(.+?)\s+and\s+(.+)$", r"\1 + \2", s)
    s = re.sub(r"^subtract\s+(.+?)\s+from\s+(.+)$", r"\2 - \1", s)
    s = re.sub(r"^multiply\s+(.+?)\s+by\s+(.+)$", r"\1 * \2", s)
    s = re.sub(r"^divide\s+(.+?)\s+by\s+(.+)$", r"\1 / \2", s)
    s = re.sub(r"(?:the\s+)?square root of\s+(\d+(?:\.\d+)?)", r"sqrt(\1)", s)
    for pattern, symbol in _WORD_OPS:
        s = re.sub(pattern, symbol, s)
    return _clean_expression(s)


def _has_operator(expr: str) -> bool:
    body = expr[1:] if expr[:1] in "+-" else expr
    return bool(re.search(r"[-+*/%(]", body))


async def calculator_skill(text: str, entities: dict, ctx: SkillContext) -> str | None:
    candidates = []
    if entities.get("expression"):
        candidates.append(_clean_expression(str(entities["expression"])))
    candidates.append(_expression_from_text(text))

    for expression in candidates:
        if not expression or not _has_operator(expression):
            continue
        try:
            result = safe_eval(expression)
        except ZeroDivisionError:
            return "I cannot divide by zero."
        except (ValueError, SyntaxError, TypeError, OverflowError, RecursionError):
            continue
        return f"The answer is {fmt_number(result)}."

    return None  # puriyala -> chat ku anuppu


# ===================== Unit conversion =====================
# key: (category, factor_to_base, spoken_name)
_UNIT_TABLE = {
    "m": ("length", 1.0, "meters"),
    "km": ("length", 1000.0, "kilometers"),
    "cm": ("length", 0.01, "centimeters"),
    "mm": ("length", 0.001, "millimeters"),
    "mi": ("length", 1609.344, "miles"),
    "yd": ("length", 0.9144, "yards"),
    "ft": ("length", 0.3048, "feet"),
    "in": ("length", 0.0254, "inches"),
    "kg": ("mass", 1.0, "kilograms"),
    "g": ("mass", 0.001, "grams"),
    "mg": ("mass", 1e-6, "milligrams"),
    "lb": ("mass", 0.45359237, "pounds"),
    "oz": ("mass", 0.028349523125, "ounces"),
    "t": ("mass", 1000.0, "tonnes"),
    "l": ("volume", 1.0, "liters"),
    "ml": ("volume", 0.001, "milliliters"),
    "gal": ("volume", 3.785411784, "gallons"),
    "cup": ("volume", 0.2365882365, "cups"),
    "tbsp": ("volume", 0.01478676478, "tablespoons"),
    "tsp": ("volume", 0.00492892159, "teaspoons"),
    "s": ("time", 1.0, "seconds"),
    "min": ("time", 60.0, "minutes"),
    "h": ("time", 3600.0, "hours"),
    "day": ("time", 86400.0, "days"),
    "week": ("time", 604800.0, "weeks"),
    "c": ("temp", 1.0, "degrees Celsius"),
    "f": ("temp", 1.0, "degrees Fahrenheit"),
    "k": ("temp", 1.0, "kelvin"),
}

_ALIASES = {
    "m": ["m", "meter", "meters", "metre", "metres"],
    "km": ["km", "kms", "kilometer", "kilometers", "kilometre", "kilometres"],
    "cm": ["cm", "centimeter", "centimeters", "centimetre", "centimetres"],
    "mm": ["mm", "millimeter", "millimeters", "millimetre", "millimetres"],
    "mi": ["mi", "mile", "miles"],
    "yd": ["yd", "yds", "yard", "yards"],
    "ft": ["ft", "foot", "feet"],
    "in": ["in", "inch", "inches"],
    "kg": ["kg", "kgs", "kilo", "kilos", "kilogram", "kilograms"],
    "g": ["g", "gram", "grams"],
    "mg": ["mg", "milligram", "milligrams"],
    "lb": ["lb", "lbs", "pound", "pounds"],
    "oz": ["oz", "ounce", "ounces"],
    "t": ["tonne", "tonnes"],
    "l": ["l", "liter", "liters", "litre", "litres"],
    "ml": ["ml", "milliliter", "milliliters", "millilitre", "millilitres"],
    "gal": ["gal", "gallon", "gallons"],
    "cup": ["cup", "cups"],
    "tbsp": ["tbsp", "tablespoon", "tablespoons"],
    "tsp": ["tsp", "teaspoon", "teaspoons"],
    "s": ["s", "sec", "secs", "second", "seconds"],
    "min": ["min", "mins", "minute", "minutes"],
    "h": ["h", "hr", "hrs", "hour", "hours"],
    "day": ["day", "days"],
    "week": ["week", "weeks"],
    "c": ["c", "celsius", "centigrade"],
    "f": ["f", "fahrenheit"],
    "k": ["k", "kelvin"],
}
_LOOKUP = {alias: key for key, aliases in _ALIASES.items() for alias in aliases}


def _canon(unit: str) -> str | None:
    cleaned = re.sub(r"\bdegrees?\b", "", unit.lower()).replace(".", "").strip()
    return _LOOKUP.get(cleaned)


def _to_celsius(value: float, key: str) -> float:
    if key == "f":
        return (value - 32) * 5 / 9
    if key == "k":
        return value - 273.15
    return value


def _from_celsius(value: float, key: str) -> float:
    if key == "f":
        return value * 9 / 5 + 32
    if key == "k":
        return value + 273.15
    return value


def _convert(value: float, from_key: str, to_key: str) -> float | None:
    from_cat, from_factor, _ = _UNIT_TABLE[from_key]
    to_cat, to_factor, _ = _UNIT_TABLE[to_key]
    if from_cat != to_cat:
        return None
    if from_cat == "temp":
        return _from_celsius(_to_celsius(value, from_key), to_key)
    return value * from_factor / to_factor


async def unit_skill(text: str, entities: dict, ctx: SkillContext) -> str | None:
    from_key = _canon(str(entities.get("from_unit") or ""))
    to_key = _canon(str(entities.get("to_unit") or ""))
    value = parse_number(entities.get("value"))
    if value is None:
        value = parse_number(text)

    if from_key is None or to_key is None or value is None:
        return None  # puriyala -> chat ku anuppu

    from_name = _UNIT_TABLE[from_key][2]
    to_name = _UNIT_TABLE[to_key][2]
    result = _convert(value, from_key, to_key)
    if result is None:
        return f"I cannot convert {from_name} to {to_name}."
    return f"{fmt_number(value)} {from_name} is about {fmt_number(result)} {to_name}."


# ===================== Assistant settings (speed / volume) =====================
_VOLUME_RE = re.compile(r"\b(volume|louder|quieter|loud|quiet|softer|loudly|quietly|softly)\b")
_SPEED_RE = re.compile(r"\b(speed|faster|slower|fast|slow|quicker|quickly|slowly)\b")
_UP_RE = re.compile(r"\b(faster|louder|increase|raise|higher|quicker|fast|loud|loudly|quickly|up)\b")
_DOWN_RE = re.compile(r"\b(slower|quieter|softer|lower|decrease|reduce|slow|quiet|slowly|quietly|softly|down)\b")


async def settings_skill(text: str, entities: dict, ctx: SkillContext) -> str | None:
    tts = ctx.tts
    if tts is None:
        return "I cannot change my voice settings right now."

    lowered = text.lower()
    up, down = bool(_UP_RE.search(lowered)), bool(_DOWN_RE.search(lowered))
    if up == down:
        return "Tell me if you want me to speak faster, slower, louder, or quieter."
    step = 0.2 if up else -0.2

    if _VOLUME_RE.search(lowered):
        new_volume = min(max(tts.volume + step, 0.1), 1.0)
        if new_volume == tts.volume:
            return "I am already at that volume limit."
        tts.volume = new_volume
        return f"Okay, volume is now {int(round(new_volume * 100))} percent."

    if _SPEED_RE.search(lowered):
        new_speed = min(max(tts.speed + step, 0.5), 2.0)
        if new_speed == tts.speed:
            return "I am already at that speed limit."
        tts.speed = new_speed
        return f"Okay, speaking speed is now {new_speed:.1f} times normal."

    return "Tell me if you want me to change my speaking speed or my volume."