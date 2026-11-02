"""Analyse's findings: what only a reading of the skills can tell — two skills that contradict each
other, a reference by the wrong name, a description spent on procedure, a skill never used and why,
a skill that is badly written — and its suggestions: a split, a merge, a tightening, a reuse. Claude
makes them in an Analyse task; this module only keeps them.

A suggestion carries a proposal, the change task the developer can send from the page: which
project skill to change, and what to ask. A finding may carry one too.

Each is saved with a fingerprint of every skill it concerns, in .skills-studio/insights.json, and
lives only while all those texts are unchanged. Analyse replaces the whole set each time it runs."""

import json
import os
import tempfile

from sx.tasks import MAX_TEXT
from sx.wirekinds import fingerprint

# kind -> the level its finding shows at
KINDS = {
    "disagreement": "warning",
    "dead-reference": "warning",
    "badly-written": "warning",
    "procedure-in-description": "info",
    "unused": "info",
    "split": "info",
    "merge": "info",
    "tighten": "info",
    "reuse": "info",
}
SUGGESTIONS = ("split", "merge", "tighten", "reuse")
MAX_MESSAGE = 600


class InsightsError(ValueError):
    pass


def read(paths):
    return _read_list(paths.insights)


def _read_list(path):
    try:
        kept = json.loads(path.read_text())
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
        finding = {
            "kind": item["kind"],
            "skills": named,
            "message": message.strip()[:MAX_MESSAGE],
            "lines": {s: [n for n in lines.get(s, []) if isinstance(n, int)] for s in named},
            "fingerprints": {s: fingerprint(texts.get(s, "")) for s in named},
        }
        proposal = _proposal(item, by_id)
        if proposal:
            finding["proposal"] = proposal
        kept.append(finding)
    _write(paths, paths.insights, kept)
    return kept


def dismissals(paths):
    """The dismissals on file; an entry not in the shape dismiss() writes is ignored."""
    return [d for d in _read_list(paths.dismissed) if _is_named(d) and isinstance(d.get("fingerprints"), dict)]


def dismiss(paths, raw, texts):
    """Sets aside the item that holds now with this kind and these skills, for as long as their texts
    stay as they are. Dismissals whose texts have changed since are dropped on the way."""
    wanted = _named(raw)
    if not any(_named(item) == wanted for item in live(read(paths), texts)):
        raise InsightsError(f"no such finding or suggestion holds now: {wanted[0]} on {', '.join(sorted(wanted[1]))}")
    kept = [d for d in live(dismissals(paths), texts) if _named(d) != wanted]
    kept.append({"kind": wanted[0], "skills": sorted(wanted[1]),
                 "fingerprints": {s: fingerprint(texts[s]) for s in wanted[1]}})
    _write(paths, paths.dismissed, kept)


def restore(paths, raw):
    wanted = _named(raw)
    _write(paths, paths.dismissed, [d for d in dismissals(paths) if _named(d) != wanted])


def partition(items, dismissed):
    """The items still shown, and those set aside: dismissed on the same texts they were made on."""
    marks = {(_named(d), _frozen(d)) for d in dismissed}
    shown = [i for i in items if (_named(i), _frozen(i)) not in marks]
    return shown, [i for i in items if (_named(i), _frozen(i)) in marks]


def _named(item):
    """An item's kind and the set of its skills: what a dismissal is matched on."""
    if not isinstance(item, dict) or item.get("kind") not in KINDS:
        raise InsightsError(f"kind must be one of {', '.join(KINDS)}")
    if not _is_named(item):
        raise InsightsError("skills: a list of the skill ids it concerns")
    return item["kind"], frozenset(item["skills"])


def _is_named(item):
    skills = item.get("skills") if isinstance(item, dict) else None
    return (item.get("kind") in KINDS and isinstance(skills, list) and bool(skills)
            and all(isinstance(s, str) for s in skills))


def _frozen(item):
    return frozenset((item.get("fingerprints") or {}).items())


def _write(paths, target, data):
    paths.ensure()
    handle, partial = tempfile.mkstemp(dir=paths.root, prefix=f".{target.stem}-", suffix=".partial")
    with os.fdopen(handle, "w") as out:
        out.write(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(partial, target)


def _proposal(item, by_id):
    proposal = item.get("proposal")
    if proposal is None:
        if item["kind"] in SUGGESTIONS:
            raise InsightsError("proposal: a suggestion needs {skill, text}, the change it would send")
        return None
    if not isinstance(proposal, dict):
        raise InsightsError("proposal: {skill, text}")
    skill, text = proposal.get("skill"), proposal.get("text")
    if skill not in item["skills"] or by_id[skill].get("source") != "project":
        raise InsightsError("proposal: skill must be a project skill the finding concerns")
    if not isinstance(text, str) or not text.strip():
        raise InsightsError("proposal: text says what to change")
    return {"skill": skill, "text": text.strip()[:MAX_TEXT]}


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
