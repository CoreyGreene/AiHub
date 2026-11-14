"""The code lock: when it's on, nothing on the site can be seen or used
until the six-digit code is typed on the lock page (web/lock.html).

A server option, set by hand in server/settings.local.json (never
committed), then restart the server:  "lock": true, "lock_code": "123456".
It is not on the website's Settings page on purpose.
A browser that typed the right code gets a cookie and isn't asked again for
LOCK_DAYS; changing the code asks everyone again. Simple, not bank-grade:
it keeps people out who don't know the code.
"""

import hashlib
import hmac
import time

from . import settings

COOKIE = "imageai_lock"
LOCK_DAYS = 30
CODE_LENGTH = 6
MAX_WRONG = 5  # wrong codes in a row before a short wait
WAIT_SECONDS = 60

_wrong = 0
_wait_until = 0.0


def code() -> str:
    return str(settings.get().get("lock_code", ""))


def is_on() -> bool:
    """On only if switched on and a code is set."""
    return bool(settings.get().get("lock")) and code_is_set()


def describe() -> str:
    """One line for the server's start-up messages."""
    if not settings.get().get("lock"):
        return "Code lock: off"
    if not code_is_set():
        return 'Code lock: NOT on: "lock_code" must be six digits (server/settings.local.json)'
    return "Code lock: on (code in server/settings.local.json)"


def code_is_set() -> bool:
    c = code()
    return len(c) == CODE_LENGTH and c.isdigit()


def token() -> str:
    """What the cookie holds: made from the code, so a new code locks
    everyone out again."""
    return hashlib.sha256(f"imageai-lock:{code()}".encode()).hexdigest()


def is_open(cookie: str | None) -> bool:
    return not is_on() or (cookie is not None and hmac.compare_digest(cookie, token()))


class Wait(Exception):
    """Too many wrong codes: try again later."""


def check(typed: str) -> bool:
    """Is this the code? After MAX_WRONG wrong ones in a row, nothing is
    checked for WAIT_SECONDS."""
    global _wrong, _wait_until
    if time.monotonic() < _wait_until:
        raise Wait()
    if hmac.compare_digest(typed.encode(), code().encode()):
        _wrong = 0
        return True
    _wrong += 1
    if _wrong >= MAX_WRONG:
        _wrong = 0
        _wait_until = time.monotonic() + WAIT_SECONDS
    return False
