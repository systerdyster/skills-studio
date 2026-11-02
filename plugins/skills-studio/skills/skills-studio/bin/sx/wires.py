"""Wires between skills, read from their bodies. The text is the only source of truth: a wire A → B
is any whole-word mention of B in A's body, awkward mentions included. A reference that looks like a
skill — a /slash-command, or a `kebab-name` on a line that says "skill" — but names nothing in scope
is a broken wire."""

import re

NAME_CHAR = r"[A-Za-z0-9_-]"
KEBAB = r"[a-z0-9]+(?:-[a-z0-9]+)+"
SLASH_REFERENCE = re.compile(rf"(?<![\w/.~-])/({KEBAB})(?!{NAME_CHAR}|/)")
TICKED_REFERENCE = re.compile(rf"`({KEBAB})`")
SAYS_SKILL = re.compile(r"skill", re.IGNORECASE)


def wires(skills):
    names = {skill["name"] for skill in skills}
    patterns = {name: re.compile(rf"(?<!{NAME_CHAR}){re.escape(name)}(?!{NAME_CHAR})") for name in names}
    result = []
    for skill in skills:
        body = skill.get("body") or ""
        first = {}
        for name, pattern in patterns.items():
            if name == skill["name"]:
                continue
            match = pattern.search(body)
            if match:
                first[name] = (match.start(), False)
        for name, at in _skill_looking_references(body):
            if name not in names and name not in first:
                first[name] = (at, True)
        ordered = sorted(first.items(), key=lambda item: item[1][0])
        for order, (name, (at, broken)) in enumerate(ordered, start=1):
            result.append({
                "from": skill["name"],
                "to": name,
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
