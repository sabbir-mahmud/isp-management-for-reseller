"""Brute-force protection for the login form.

Deliberately small: a counter in the cache keyed by username *and* client IP,
so one attacker cannot lock every account out by guessing at them, and one
account cannot be hammered from a single host.
"""

from django.conf import settings
from django.core.cache import cache

PREFIX = "login-throttle"


def _keys(username: str, ip: str) -> list[str]:
    return [f"{PREFIX}:user:{username.lower()}", f"{PREFIX}:ip:{ip}"]


def client_ip(request) -> str:
    """Best-effort client address.

    `X-Forwarded-For` is only trusted when the deployment declares it is
    behind a proxy, otherwise a client can forge its own address.
    """
    if getattr(settings, "TRUST_PROXY_HEADERS", False):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def is_locked(username: str, ip: str) -> bool:
    limit = settings.LOGIN_FAILURE_LIMIT
    return any((cache.get(key) or 0) >= limit for key in _keys(username, ip))


def record_failure(username: str, ip: str) -> None:
    timeout = settings.LOGIN_FAILURE_TIMEOUT
    for key in _keys(username, ip):
        # `add` then `incr`: set the TTL once so the window does not slide
        # forever with each new attempt.
        cache.add(key, 0, timeout)
        try:
            cache.incr(key)
        except ValueError:  # pragma: no cover - key expired between add and incr
            cache.set(key, 1, timeout)


def reset(username: str, ip: str) -> None:
    cache.delete_many(_keys(username, ip))
