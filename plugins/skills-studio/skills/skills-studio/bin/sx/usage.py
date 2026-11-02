"""How much each skill is used, from Claude Code's /skill-doctor report (`claude -p "/skill-doctor"`).

The report is text only, so its table is read by columns: skill, source, context, 7d tokens, uses,
last used. Its shape belongs to Claude Code and may change; a report with no readable rows is a
failed fetch, never an empty answer. Fetching starts a claude process and takes seconds, so it runs
in the background and the last good rows are kept."""

import re
import subprocess
import threading
from datetime import datetime, timezone

COMMAND = ["claude", "-p", "/skill-doctor"]
TIMEOUT_SECONDS = 180
ROW = re.compile(r"^\s+(?P<skill>\S+)\s{2,}(?P<source>\S.*?)\s{2,}(?P<context>~\d+|<\s*\d+)\s+"
                 r"(?P<tokens>-|[\d.]+[km]?)\s+(?P<uses>\d+)×\s+(?P<last>\S.*?)\s*$")
FOLDER_SOURCES = ("project", "user")


def parse(text):
    rows = {}
    for line in text.splitlines():
        found = ROW.match(line)
        if found:
            rows[found["skill"]] = {
                "context": found["context"],
                "tokens_7d": None if found["tokens"] == "-" else found["tokens"],
                "uses": int(found["uses"]),
                "last_used": found["last"],
            }
    return rows


def match(rows, skills):
    """Rows by studio id. The report names project and user skills by folder, the rest by id."""
    result = {}
    for skill in skills:
        row = rows.get(skill["id"])
        if row is None and skill.get("source") in FOLDER_SOURCES:
            row = rows.get(skill.get("folder"))
        if row is not None:
            result[skill["id"]] = row
    return result


def report_from_claude(project):
    def report():
        done = subprocess.run(COMMAND, cwd=project, capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS, stdin=subprocess.DEVNULL)
        if done.returncode != 0:
            raise OSError((done.stderr or done.stdout).strip()[:300] or f"exit {done.returncode}")
        return done.stdout
    return report


class Usage:
    def __init__(self, report):
        self._report = report
        self._lock = threading.Lock()
        self._thread = None
        self._state = {"status": "idle", "rows": {}, "fetched_at": None, "error": None}

    def refresh(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._state["status"] = "loading"
            self._thread = threading.Thread(target=self._fetch, daemon=True)
            self._thread.start()

    def wait(self, timeout=None):
        thread = self._thread
        if thread:
            thread.join(timeout)

    def state(self):
        with self._lock:
            return {**self._state, "rows": dict(self._state["rows"])}

    def _fetch(self):
        try:
            rows = parse(self._report())
            if not rows:
                raise ValueError("the /skill-doctor report had no table this version can read")
            update = {"status": "ready", "rows": rows, "error": None,
                      "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            update = {"status": "failed", "error": str(error)}
        with self._lock:
            self._state.update(update)
