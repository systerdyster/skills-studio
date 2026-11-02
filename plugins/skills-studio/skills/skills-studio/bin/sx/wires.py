"""Wires between skills, read from their bodies. The text is the only source of truth: a wire A → B
is a mention of B in A's body by the name Claude knows B by, awkward mentions included.

- Plugin and synced skills count only by their qualified name (`atlassian:triage-issue`,
  `anthropic-skills:docs`), so a plain word that happens to be a skill's name is just a word.
- Project and user skills count by their bare name; a one-word name only when it is written as a
  skill: in backticks or as a /slash-command. The same goes for a plugin skill named by a sibling in
  its own plugin.

A reference that looks like a skill — a /slash-command, or a `kebab-name` on a line that says
"skill" — but names nothing in scope is a broken wire."""

import re

NAME_CHAR = r"[A-Za-z0-9_-]"
NOT_AFTER = r"(?<![A-Za-z0-9_:-])"
SLASH_START = r"(?<![\w/.~-])/"
KEBAB = r"[a-z0-9]+(?:-[a-z0-9]+)+"
SLASH_REFERENCE = re.compile(rf"{SLASH_START}({KEBAB})(?!{NAME_CHAR}|/)")
TICKED_REFERENCE = re.compile(rf"`({KEBAB})`")
SAYS_SKILL = re.compile(r"skill", re.IGNORECASE)
SYNCED_PREFIX = "anthropic-skills"


def skill_id(skill):
    """The name Claude knows a skill by."""
    if skill.get("source") == "plugin":
        return f"{skill['plugin']}:{skill['name']}"
    if skill.get("source") == "synced":
        return f"{SYNCED_PREFIX}:{skill['name']}"
    return skill["name"]


def _mention(name):
    target = re.escape(name)
    if "-" in name:
        return re.compile(rf"{NOT_AFTER}{target}(?!{NAME_CHAR})")
    return re.compile(rf"`{target}`|{SLASH_START}{target}(?!{NAME_CHAR}|/)")


def _qualified(name):
    return re.compile(rf"{NOT_AFTER}{re.escape(name)}(?!{NAME_CHAR})")


def wires(skills):
    targets = {}
    for skill in skills:
        qualified = skill.get("source") in ("plugin", "synced")
        targets[skill_id(skill)] = (skill, _qualified(skill_id(skill)) if qualified else _mention(skill["name"]))
    known = set(targets) | {skill["name"] for skill in skills}
    result = []
    for skill in skills:
        source = skill_id(skill)
        body = skill.get("body") or ""
        first = {}
        for target, (other, pattern) in targets.items():
            if target == source:
                continue
            match = pattern.search(body)
            if not match and skill.get("plugin") and other.get("plugin") == skill["plugin"]:
                match = _mention(other["name"]).search(body)
            if match:
                first[target] = (match.start(), False)
        for name, at in _skill_looking_references(body):
            if name not in known and name not in first:
                first[name] = (at, True)
        ordered = sorted(first.items(), key=lambda item: item[1][0])
        for order, (target, (at, broken)) in enumerate(ordered, start=1):
            result.append({
                "from": source,
                "to": target,
                "order": order,
                "line": skill.get("body_line", 1) + body.count("\n", 0, at),
                "broken": broken,
            })
    return result


def _skill_looking_references(body):
    found = [(m.group(1), m.start(1)) for m in SLASH_REFERENCE.finditer(body)]
    offset = 0
    for line in body.split("\n"):
        if SAYS_SKILL.search(line):
            found += [(m.group(1), offset + m.start(1)) for m in TICKED_REFERENCE.finditer(line)]
        offset += len(line) + 1
    return sorted(found, key=lambda item: item[1])
