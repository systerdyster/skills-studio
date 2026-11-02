"""Tasks: what the canvas asks the session to do. Each is checked against the scan before it is
written to inbox/ — only project skills may be changed, a new name must be free — and written
atomically, so a watcher never reads half a task."""

import json
import os
import re
import secrets
from datetime import datetime, timezone

MAX_TEXT = 4000
MAX_SKILL_TEXT = 60000
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EDITABLE_FIELDS = ("name", "description")

# kind -> fields it carries, and how each is checked:
#   writable: a project skill's id   any: any skill's id in scope   free: a new, unused kebab name
#   field: one of EDITABLE_FIELDS    text: free text, capped    whole: a skill's whole text, refused if too long
#   rename: the skill's name as it is, or a free kebab name
KINDS = {
    "link": {"from": "writable", "to": "any"},
    "unlink": {"from": "writable", "to": "any"},
    "edit": {"skill": "writable", "field": "field", "value": "text"},
    "save": {"skill": "writable", "name": "rename", "description": "text", "body": "whole"},
    "change": {"skill": "writable", "text": "text"},
    "improve": {"skill": "writable", "focus": "text"},
    "delete": {"skill": "writable"},
    "new": {"name": "free", "description": "text", "intent": "text"},
    "copy": {"source": "any", "name": "free"},
    "analyse": {},
    "close": {},
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
        if rule == "rename":
            continue
        task[field] = _check(field, rule, value.strip() if rule not in ("text", "whole") else value, by_id)
    for field, rule in KINDS[raw["kind"]].items():
        if rule == "rename":
            current = by_id[task["skill"]]["name"]
            wanted = raw[field].strip()
            task[field] = wanted if wanted == current else _check(field, "free", wanted, by_id)
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
    elif rule == "whole":
        if len(value) > MAX_SKILL_TEXT:
            raise TaskError(f"{field}: at most {MAX_SKILL_TEXT} characters; cutting it would lose the rest")
    return value


def submit(paths, raw, skills):
    task = validate(raw, skills)
    now = datetime.now(timezone.utc)
    task["id"] = f"{now.strftime('%Y%m%dT%H%M%S%fZ')}-{task['kind']}-{secrets.token_hex(3)}"
    task["created_at"] = now.isoformat(timespec="seconds")
    paths.ensure()
    paths.inbox.mkdir(exist_ok=True)
    target = paths.inbox / f"{task['id']}.json"
    partial = target.with_suffix(".partial")
    partial.write_text(json.dumps(task, ensure_ascii=False, indent=2))
    os.replace(partial, target)
    return task


# ---- a task's life: inbox/ -> active/ -> done/ ---------------------------------------------

OUTCOMES = ("done", "declined", "failed")
TASK_ID = re.compile(r"^[0-9TZ]+-[a-z]+-[0-9a-f]+$")
TARGET_FIELD = {"link": "from", "unlink": "from", "edit": "skill", "change": "skill", "improve": "skill",
                "delete": "skill", "save": "skill"}


def pending(paths):
    return [_read(path) for path in _listed(paths.inbox)]


def in_flight(paths):
    return ([{**task, "state": "waiting"} for task in pending(paths)]
            + [{**_read(path), "state": "active"} for path in _listed(paths.active)])


def new_since(paths, seen):
    """Waiting tasks not reported before; adds them to `seen`."""
    fresh = [task for task in pending(paths) if task["id"] not in seen]
    seen.update(task["id"] for task in fresh)
    return fresh


def start(paths, task_id, skills):
    """The session takes a task: it moves to active/ with its target's text as it is now."""
    task = _read(_located(paths.inbox, task_id))
    task["started_at"] = _stamp()
    task["before"] = _texts(_target_files(task, skills))
    _move(paths, task, paths.inbox, paths.active)
    return task


def progress(paths, task_id, note):
    """The session says where it is in an active task, for the page to show while it waits."""
    if not (paths.active / f"{_checked(task_id)}.json").exists():
        raise TaskError(f"task {task_id} is not active; start it first")
    target = paths.active / f"{task_id}.json"
    task = _read(target)
    task.update(progress=note[:200], progress_at=_stamp())
    partial = target.with_suffix(".partial")
    partial.write_text(json.dumps(task, ensure_ascii=False, indent=2))
    os.replace(partial, target)
    return task


def done(paths, task_id, outcome, note):
    if outcome not in OUTCOMES:
        raise TaskError(f"outcome must be one of {', '.join(OUTCOMES)}")
    folder = paths.active if (paths.active / f"{_checked(task_id)}.json").exists() else paths.inbox
    task = _read(_located(folder, task_id))
    task.update(outcome=outcome, note=note[:MAX_TEXT], finished_at=_stamp())
    if "before" in task:
        task["after"] = _texts(task["before"])
    _move(paths, task, folder, paths.done)
    return task


def target_file(task, skills):
    """The SKILL.md a task changes, or None for tasks that make a new skill."""
    field = TARGET_FIELD.get(task["kind"])
    by_id = {s["id"]: s for s in skills}
    return by_id[task[field]]["path"] if field and task.get(field) in by_id else None


def _target_files(task, skills):
    path = target_file(task, skills)
    return [path] if path else []


def _texts(files):
    texts = {}
    for path in files:
        try:
            texts[str(path)] = open(path, encoding="utf-8").read()
        except OSError:
            texts[str(path)] = None
    return texts


def _checked(task_id):
    if not TASK_ID.match(task_id or ""):
        raise TaskError(f"not a task id: {task_id!r}")
    return task_id


def _located(folder, task_id):
    path = folder / f"{_checked(task_id)}.json"
    if not path.exists():
        raise TaskError(f"no task {task_id} in {folder.name}/")
    return path


def _listed(folder):
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def _read(path):
    return json.loads(path.read_text())


def _move(paths, task, source, target):
    target.mkdir(parents=True, exist_ok=True)
    destination = target / f"{task['id']}.json"
    partial = destination.with_suffix(".partial")
    partial.write_text(json.dumps(task, ensure_ascii=False, indent=2))
    os.replace(partial, destination)
    (source / f"{task['id']}.json").unlink()


def _stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
