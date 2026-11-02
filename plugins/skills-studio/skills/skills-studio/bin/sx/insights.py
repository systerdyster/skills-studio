"""Analyse's findings: what only a reading of the skills can tell — two skills that contradict each
other, a reference by the wrong name, a description spent on procedure, a skill never used and why,
a skill that is badly written. Claude makes them in an Analyse task; this module only keeps them.

Each is saved with a fingerprint of every skill it concerns, in .skills-studio/insights.json, and
lives only while all those texts are unchanged. Analyse replaces the whole set each time it runs."""

import json
import os
import tempfile

from sx.wirekinds import fingerprint

# kind -> the level its finding shows at
KINDS = {
    "disagreement": "warning",
    "dead-reference": "warning",
    "badly-written": "warning",
    "procedure-in-description": "info",
    "unused": "info",
}
MAX_MESSAGE = 600


class InsightsError(ValueError):
    pass


def read(paths):
    try:
        kept = json.loads(paths.insights.read_text())
    except (OSError, ValueError):
        return []
    return kept if isinstance(kept, list) else []


def save(paths, raw, skills, texts):
    """Checks each finding and stamps it with the fingerprints of the texts as they are now."""
    if not isinstance(raw, list):
        raise InsightsError("expected a list of {kind, skills, message, lines}")
    by_id = {s["id"]: s for s in skills}
    kept = []
    for item in raw:
        if not isinstance(item, dict) or item.get("kind") not in KINDS:
            raise InsightsError(f"kind must be one of {', '.join(KINDS)}")
        named = item.get("skills")
        if not isinstance(named, list) or not named or not all(isinstance(s, str) for s in named):
            raise InsightsError("skills: a list of the skill ids it concerns")
        for skill_id in named:
            if skill_id not in by_id:
                raise InsightsError(f"skills: no skill {skill_id!r} in scope")
        if not any(by_id[s].get("source") == "project" for s in named):
            raise InsightsError("skills: a finding must concern at least one of the project's own skills")
        message = item.get("message")
        if not isinstance(message, str) or not message.strip():
            raise InsightsError("message: say what is wrong, in a sentence")
        lines = item.get("lines") or {}
        if not isinstance(lines, dict):
            raise InsightsError("lines: {skill id: [line, …]}")
        kept.append({
            "kind": item["kind"],
            "skills": named,
            "message": message.strip()[:MAX_MESSAGE],
            "lines": {s: [n for n in lines.get(s, []) if isinstance(n, int)] for s in named},
            "fingerprints": {s: fingerprint(texts.get(s, "")) for s in named},
        })
    paths.ensure()
    handle, partial = tempfile.mkstemp(dir=paths.root, prefix=".insights-", suffix=".partial")
    with os.fdopen(handle, "w") as out:
        out.write(json.dumps(kept, ensure_ascii=False, indent=2))
    os.replace(partial, paths.insights)
    return kept


def live(kept, texts):
    """The findings whose every skill still has the text they were made on."""
    return [item for item in kept
            if all(s in texts and fingerprint(texts[s]) == fp for s, fp in (item.get("fingerprints") or {}).items())]


def as_findings(items):
    """One finding per skill concerned, in the shape the local checks use."""
    found = []
    for item in items:
        for skill_id in item["skills"]:
            others = [s for s in item["skills"] if s != skill_id]
            finding = {"skill": skill_id, "check": f"analyse-{item['kind']}", "level": KINDS[item["kind"]],
                       "message": item["message"], "line": (item["lines"].get(skill_id) or [None])[0]}
            if others:
                finding["other"] = others[0]
            found.append(finding)
    return found
