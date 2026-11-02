"""Local checks: always on, no model. Each finding names the skill by id, the check, a level
(error, warning, info) and a message; `line` and `other` where they apply."""

import hashlib
import itertools
import re

DESCRIPTION_MAX = 1024        # the Agent Skills limit on a description
DESCRIPTION_MIN = 40          # shorter than this rarely says when to use the skill
OVERLAP_THRESHOLD = 0.25      # Jaccard of description words; tuned on real skills, 2026-11-02
PERSONAL_MARKERS = re.compile(r"(?<![\w.~])~/[^\s`'\")]*|/Users/[^/\s`'\")]+|/home/[^/\s`'\")]+")  # the user's home
STOP_WORDS = frozenset(
    "the and for with that this when use user asks or a an to of in on is are be it its as by from "
    "any not only one into their them they what which who will can your you does do also like says "
    "say even".split()
)


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def checks(skills, wires, sources):
    """`sources` maps a skill id to its SKILL.md text, for comparing copies with their source."""
    findings = []
    for skill in skills:
        findings += _frontmatter(skill)
        findings += _copy(skill, sources)
    findings += _broken_wires(wires)
    findings += _duplicates(skills)
    findings += _overlaps(skills)
    return findings


def _finding(skill_id, check, level, message, line=None, other=None):
    finding = {"skill": skill_id, "check": check, "level": level, "message": message, "line": line}
    if other:
        finding["other"] = other
    return finding


def _frontmatter(skill):
    sid, frontmatter = skill["id"], skill.get("frontmatter")
    if skill.get("error") == "missing frontmatter":
        return [_finding(sid, "frontmatter-missing", "error", "No frontmatter: Claude has no name or description to go by.")]
    if skill.get("error"):
        return [_finding(sid, "frontmatter-broken", "error", f"Frontmatter cannot be read: {skill['error']}.")]
    found = []
    if not _text(frontmatter, "name"):
        found.append(_finding(sid, "name-missing", "error", "Frontmatter has no name."))
    description = _text(frontmatter, "description")
    if not description:
        found.append(_finding(sid, "description-missing", "error", "Frontmatter has no description: Claude cannot tell when to use it."))
    elif len(description) > DESCRIPTION_MAX:
        found.append(_finding(sid, "description-long", "warning",
                              f"Description is {len(description)} characters; the limit is {DESCRIPTION_MAX}."))
    elif len(description) < DESCRIPTION_MIN:
        found.append(_finding(sid, "description-short", "warning",
                              f"Description is {len(description)} characters: say what it does and when to use it."))
    return found


def _text(frontmatter, key):
    value = (frontmatter or {}).get(key)
    return value.strip() if isinstance(value, str) else ""


def _broken_wires(wires):
    return [
        _finding(w["from"], "wire-broken", "warning", f"Names {w['to']}, which is not in scope here.",
                 line=w["line"], other=w["to"])
        for w in wires if w["broken"]
    ]


def _duplicates(skills):
    by_id = {}
    for skill in skills:
        by_id.setdefault(skill["id"], []).append(skill)
    found = []
    for sid, same in by_id.items():
        if len(same) > 1:
            where = ", ".join(sorted({s["source"] for s in same}))
            found.append(_finding(sid, "name-duplicate", "warning",
                                  f"{len(same)} skills are called {sid} ({where}); one shadows the other."))
    return found


def _words(text):
    return {w for w in re.findall(r"[a-z][a-z-]{2,}", text.lower()) if w not in STOP_WORDS}


def _overlaps(skills):
    described = [(s["id"], _words(_text(s.get("frontmatter"), "description"))) for s in skills]
    found = []
    for (a, words_a), (b, words_b) in itertools.combinations(described, 2):
        if a == b or not words_a or not words_b:
            continue
        similarity = len(words_a & words_b) / len(words_a | words_b)
        if similarity >= OVERLAP_THRESHOLD:
            message = f"Triggers overlap with {{}} ({similarity:.0%} of description words shared)."
            found.append(_finding(a, "trigger-overlap", "info", message.format(b), other=b))
            found.append(_finding(b, "trigger-overlap", "info", message.format(a), other=a))
    return found


def _copy(skill, sources):
    metadata = (skill.get("frontmatter") or {}).get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("copied_from"):
        return []
    sid, origin = skill["id"], metadata["copied_from"]
    found = []
    personal = PERSONAL_MARKERS.search(skill.get("body") or "")
    if personal:
        found.append(_finding(sid, "copy-personal", "warning",
                              f"Copied from {origin} and still holds personal content ({personal.group(0)}); "
                              "it lands in a repository the team shares."))
    if origin not in sources:
        found.append(_finding(sid, "copy-source-gone", "info", f"Copied from {origin}, which is no longer in scope.", other=origin))
    elif content_hash(sources[origin]) != metadata.get("copied_hash"):
        found.append(_finding(sid, "copy-source-changed", "info", f"{origin} has changed since this copy was taken.", other=origin))
    return found
