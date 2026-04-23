"""
Brute-force mitigation for PIN login (4-digit PIN is weak).
Uses Django cache; configure CACHES in settings (locmem is fine for single-process dev).
"""

from __future__ import annotations

from django.core.cache import cache

# After this many failed attempts for the same IP+identifier, block further tries.
MAX_ATTEMPTS = 8
ATTEMPT_WINDOW_SEC = 300
# After lockout, block this IP from any login for a cooldown (simple IP throttle).
IP_LOCKOUT_SEC = 600


def _ip(request) -> str:
    return request.META.get("REMOTE_ADDR", "unknown")


def is_login_blocked(request, identifier: str) -> bool:
    ip = _ip(request)
    if cache.get(f"login_ip_block:{ip}"):
        return True
    key = f"login_fail:{ip}:{identifier.strip().lower()}"
    return (cache.get(key) or 0) >= MAX_ATTEMPTS


def record_login_failure(request, identifier: str) -> None:
    ip = _ip(request)
    key = f"login_fail:{ip}:{identifier.strip().lower()}"
    n = (cache.get(key) or 0) + 1
    cache.set(key, n, ATTEMPT_WINDOW_SEC)
    if n >= MAX_ATTEMPTS:
        cache.set(f"login_ip_block:{ip}", 1, IP_LOCKOUT_SEC)


def clear_login_failures(request, identifier: str) -> None:
    ip = _ip(request)
    cache.delete(f"login_fail:{ip}:{identifier.strip().lower()}")


def clear_ip_block(request) -> None:
    cache.delete(f"login_ip_block:{_ip(request)}")
