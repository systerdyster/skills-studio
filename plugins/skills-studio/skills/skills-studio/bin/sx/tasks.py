"""Tasks: what the canvas asks the session to do. Each is checked against the scan before it is
written to inbox/ — only project skills may be changed, a new name must be free — and written
atomically, so a watcher never reads half a task."""

import json
import os
import re
import secrets
from datetime import datetime, timezone

MAX_TEXT = 4000
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EDITABLE_FIELDS = ("name", "description")

# kind -> fields it carries, and how each is checked:
#   writable: a project skill's id   any: any skill's id in scope   free: a new, unused kebab name
#   field: one of EDITABLE_FIELDS    text: free text, capped
KINDS = {
    "link": {"from": "writable", "to": "any"},
    "unlink": {"from": "writable", "to": "any"},
    "edit": {"skill": "writable", "field": "field", "value": "text"},
    "change": {"skill": "writable", "text": "text"},
    "new": {"name": "free", "description": "text", "intent": "text"},
    "copy": {"source": "any", "name": "free"},
    "analyse": {},
}


class TaskError(ValueError):
    pass


def validate(raw, skills):
    if not isinstance(raw, dict) or raw.get("kind") not in KINDS:
        raise TaskError(f"unknown task kind; expected one of {', '.join(KINDS)}")
    by_id = {s["id"]: s for s in skills}
    task = {"kind": raw["kind"]}
    for field, rule in KINDS[raw["kind"]].items():
        value = raw.get(field)
        if not isinstance(value, str):
            raise TaskError(f"{field} is missing")
        task[field] = _check(field, rule, value.strip() if rule != "text" else value, by_id)
    return task


def _check(field, rule, value, by_id):
    if rule in ("writable", "any"):
        if value not in by_id:
            raise TaskError(f"{field}: no skill {value!r} in scope")
        if rule == "writable" and not by_id[value]["writable"]:
            raise TaskError(f"{field}: {value} is read-only; only the project's own skills can be changed")
    elif rule == "free":
        if not NAME.match(value) or len(value) > 64:
            raise TaskError(f"{field}: a skill name is lowercase words joined by hyphens, at most 64 characters")
        if value in by_id or any(s["name"] == value for s in by_id.values()):
            raise TaskError(f"{field}: {value} is taken")
    elif rule == "field":
        if value not in EDITABLE_FIELDS:
            raise TaskError(f"field: only {' or '.join(EDITABLE_FIELDS)} can be edited in place")
    elif rule == "text":
        value = value[:MAX_TEXT]
    return value


def submit(paths, raw, skills):
    task = validate(raw, skills)
    now = datetime.now(timezone.utc)
    task["id"] = f"{now.strftime('%Y%m%dT%H%M%S%fZ')}-{task['kind']}-{secrets.token_hex(3)}"
    task["created_at"] = now.isoformat(timespec="seconds")
    paths.inbox.mkdir(parents=True, exist_ok=True)
    target = paths.inbox / f"{task['id']}.json"
    partial = target.with_suffix(".partial")
    partial.write_text(json.dumps(task, ensure_ascii=False, indent=2))
    os.replace(partial, target)
    return task
