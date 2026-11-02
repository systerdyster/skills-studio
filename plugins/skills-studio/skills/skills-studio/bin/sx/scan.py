"""Find every skill a project can see and describe each one. Only the project's own skills are
writable; user, synced and plugin skills are read-only references."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from sx.frontmatter import FrontmatterError, parse
from sx.wires import skill_id

CHARS_PER_TOKEN = 4


def scan(project, home):
    project, home = Path(project), Path(home)
    user_skills = home / ".claude" / "skills"
    found = []
    found += _folder(project / ".claude" / "skills", "project")
    found += _folder(user_skills, "user", skip={"synced"})
    for synced in _subfolders(user_skills / "synced"):
        found += _folder(synced, "synced")
    for plugin, skills_dir in _plugin_skill_dirs(project, home):
        found += _folder(skills_dir, "plugin", plugin=plugin)
    return found


def _subfolders(path):
    if not path.is_dir():
        return []
    return sorted(p for p in path.iterdir() if p.is_dir() and not p.name.startswith("."))


def _folder(path, source, skip=(), plugin=None):
    return [
        _describe(folder, source, plugin)
        for folder in _subfolders(path)
        if folder.name not in skip and (folder / "SKILL.md").is_file()
    ]


def _describe(folder, source, plugin):
    path = folder / "SKILL.md"
    text = path.read_text(encoding="utf-8", errors="replace")
    stat = path.stat()
    frontmatter, body, error = None, text, None
    try:
        frontmatter, body = parse(text)
        if frontmatter is None:
            error = "missing frontmatter"
    except FrontmatterError as problem:
        error = str(problem)
    name = _text(frontmatter, "name") or folder.name
    description = _text(frontmatter, "description") or ""
    record = {
        "name": name,
        "source": source,
        "folder": folder.name,
        "path": str(path),
        "real_path": str(path.resolve()),
        "writable": source == "project",
        "frontmatter": frontmatter,
        "body": body,
        "body_line": text.count("\n", 0, len(text) - len(body)) + 1,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
        "tokens": {
            "listing": _tokens(name + description),
            "body": _tokens(body),
        },
        "error": error,
    }
    if plugin:
        record["plugin"] = plugin
    record["id"] = skill_id(record)
    return record


def _text(frontmatter, key):
    value = (frontmatter or {}).get(key)
    return value.strip() if isinstance(value, str) else None


def _tokens(text):
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def _plugin_skill_dirs(project, home):
    """Each installed plugin that applies to this project, once: a project- or local-scoped install
    for this project wins over a user-scoped one."""
    registry = home / ".claude" / "plugins" / "installed_plugins.json"
    try:
        installs = json.loads(registry.read_text()).get("plugins", {})
    except (OSError, ValueError):
        return []
    chosen = {}
    for key, entries in installs.items():
        plugin = key.split("@", 1)[0]
        for entry in entries:
            scope = entry.get("scope")
            here = scope in ("project", "local") and Path(entry.get("projectPath", "")) == project
            if here or (scope == "user" and plugin not in chosen):
                chosen[plugin] = Path(entry.get("installPath", ""))
    dirs = []
    for plugin, install in sorted(chosen.items()):
        for skills_dir in _declared_skill_dirs(install):
            dirs.append((plugin, skills_dir))
    return dirs


def _declared_skill_dirs(install):
    dirs = [install / "skills"]
    try:
        manifest = json.loads((install / ".claude-plugin" / "plugin.json").read_text())
    except (OSError, ValueError):
        return dirs
    declared = manifest.get("skills")
    for extra in [declared] if isinstance(declared, str) else declared or []:
        path = (install / extra).resolve()
        if path not in dirs:
            dirs.append(path)
    return dirs
