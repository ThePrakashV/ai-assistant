import time

from app.core.config import settings

# Internet use panra skills. Offline mode la idhellam off
NETWORK_SKILLS = {"weather", "currency_conversion", "web_search"}


def disabled_skills() -> set[str]:
    return {name.strip() for name in settings.disabled_skills.split(",") if name.strip()}


def check_permission(skill: str) -> str | None:
    """None = allowed. Illana user ku solla vendiya message."""
    if skill in disabled_skills():
        return "That skill is turned off in my settings."
    if settings.offline_mode and skill in NETWORK_SKILLS:
        return "Offline mode is on, so I will not use the internet for that."
    return None


class AuthThrottle:
    """Doorman. Oru IP la irundhu thappa token adikkadi vandha block pannum."""

    def __init__(self) -> None:
        self._fails: dict[str, list[float]] = {}
        self._blocked_until: dict[str, float] = {}

    def blocked_for(self, ip: str) -> int:
        remaining = self._blocked_until.get(ip, 0.0) - time.time()
        if remaining <= 0:
            self._blocked_until.pop(ip, None)
            return 0
        return int(remaining) + 1

    def fail(self, ip: str) -> bool:
        """Thappa token record pannum. Ippo block aanaa True."""
        now = time.time()
        recent = [t for t in self._fails.get(ip, []) if now - t < settings.auth_window_seconds] + [now]
        if len(recent) >= settings.auth_max_failures:
            self._blocked_until[ip] = now + settings.auth_lockout_seconds
            self._fails[ip] = []
            return True
        self._fails[ip] = recent
        return False

    def ok(self, ip: str) -> None:
        self._fails.pop(ip, None)


throttle = AuthThrottle()