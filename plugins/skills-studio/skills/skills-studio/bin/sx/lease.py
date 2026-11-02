"""One studio session per project. The lease lapses after TTL unless renewed — the session renews it
each time it re-arms its watcher (at most every 30 minutes) and with each task — so a session that
died holds nothing for long."""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

TTL = timedelta(minutes=45)


class LeaseHeld(RuntimeError):
    def __init__(self, held):
        super().__init__(f"the studio is held by session {held['holder']} (since {held['taken_at']})")
        self.lease = held


def _now(now):
    return now or datetime.now(timezone.utc)


def current(paths, now=None):
    """The live lease, or None when there is none or it has lapsed."""
    try:
        held = json.loads(paths.lease.read_text())
        renewed = datetime.fromisoformat(held["renewed_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return held if _now(now) - renewed <= TTL else None


def take(paths, holder, now=None):
    now = _now(now)
    held = current(paths, now)
    if held and held["holder"] != holder:
        raise LeaseHeld(held)
    taken_at = held["taken_at"] if held else now.isoformat(timespec="seconds")
    return _write(paths, {"holder": holder, "taken_at": taken_at, "renewed_at": now.isoformat(timespec="seconds")})


def renew(paths, holder, now=None):
    held = current(paths, now)
    if not held or held["holder"] != holder:
        raise LeaseHeld(held or {"holder": "nobody", "taken_at": "-"})
    return _write(paths, {**held, "renewed_at": _now(now).isoformat(timespec="seconds")})


def release(paths, holder):
    """Lets go of the holder's lease, lapsed or not; another session's lease is left alone."""
    try:
        held = json.loads(paths.lease.read_text())
    except (OSError, ValueError):
        return
    if isinstance(held, dict) and held.get("holder") == holder:
        paths.lease.unlink(missing_ok=True)


def _write(paths, held):
    paths.ensure()
    handle, partial = tempfile.mkstemp(dir=paths.root, prefix=".lease-", suffix=".partial")
    with os.fdopen(handle, "w") as out:
        out.write(json.dumps(held))
    os.replace(partial, paths.lease)
    return held
