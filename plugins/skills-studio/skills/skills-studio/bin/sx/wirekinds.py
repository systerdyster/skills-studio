"""Whether a wire is a call or a mention. A call: following the skill makes Claude run the other
skill, now or as a handoff. A mention: anything else — a related link, a "don't", a note on what the
other skill does, a pointer for the developer.

That is a judgement, so Claude makes it in an Analyse task; this module only keeps it. Each project
skill's judgement is stored with a fingerprint of its text, in .skills-studio/wire-kinds.json. When
the text changes the judgement no longer applies, and its wires carry no kind until judged again."""

import hashlib
import json
import os
import tempfile

KINDS = ("call", "mention")
MAX_REASON = 300


class KindsError(ValueError):
    pass


def fingerprint(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read(paths):
    try:
        saved = json.loads(paths.wire_kinds.read_text())
    except (OSError, ValueError):
        return {}
    return saved if isinstance(saved, dict) else {}


def _current(skill_id, texts, saved):
    judged = saved.get(skill_id)
    if isinstance(judged, dict) and skill_id in texts and judged.get("fingerprint") == fingerprint(texts[skill_id]):
        return judged.get("wires") or {}
    return None


def apply(wires, texts, saved):
    """The wires, each with its `kind` and `reason` — None when not judged for the text as it is."""
    result = []
    for wire in wires:
        judged = _current(wire["from"], texts, saved) or {}
        verdict = judged.get(wire["to"]) or {}
        result.append({**wire, "kind": verdict.get("kind"), "reason": verdict.get("reason")})
    return result


def _judgeable(skills, wires):
    project = {s["id"] for s in skills if s.get("source") == "project"}
    by_skill = {}
    for wire in wires:
        if wire["from"] in project and not wire.get("broken"):
            by_skill.setdefault(wire["from"], []).append(wire)
    return by_skill


def pending(skills, wires, texts, saved):
    """Project skills whose wires need judging, each mention with its line, for the session."""
    found = []
    for skill_id, own in sorted(_judgeable(skills, wires).items()):
        judged = _current(skill_id, texts, saved)
        if judged is not None and all(w["to"] in judged for w in own):
            continue
        lines = texts.get(skill_id, "").split("\n")
        found.append({
            "skill": skill_id,
            "fingerprint": fingerprint(texts.get(skill_id, "")),
            "wires": [{"to": w["to"], "lines": [{"line": n, "text": lines[n - 1].strip() if n <= len(lines) else ""}
                                                for n in w.get("lines", [w.get("line")])]} for w in own],
        })
    return found


def save(paths, raw, skills, wires, texts):
    if not isinstance(raw, dict):
        raise KindsError("expected {skill id: {fingerprint, wires: {to: {kind, reason}}}}")
    judgeable = _judgeable(skills, wires)
    project = {s["id"] for s in skills if s.get("source") == "project"}
    checked = {}
    for skill_id, judged in raw.items():
        if skill_id not in project:
            raise KindsError(f"{skill_id}: only the project's own skills are judged")
        if not isinstance(judged, dict) or judged.get("fingerprint") != fingerprint(texts.get(skill_id, "")):
            raise KindsError(f"{skill_id}: its text changed since it was read; judge it again")
        verdicts = judged.get("wires")
        if not isinstance(verdicts, dict):
            raise KindsError(f"{skill_id}: wires must map each target to {{kind, reason}}")
        targets = {w["to"] for w in judgeable.get(skill_id, [])}
        for to, verdict in verdicts.items():
            if to not in targets:
                raise KindsError(f"{skill_id}: no wire to {to}")
            if not isinstance(verdict, dict) or verdict.get("kind") not in KINDS:
                raise KindsError(f"{skill_id} → {to}: kind must be call or mention")
        missing = targets - set(verdicts)
        if missing:
            raise KindsError(f"{skill_id}: not judged: {', '.join(sorted(missing))}")
        checked[skill_id] = {
            "fingerprint": judged["fingerprint"],
            "wires": {to: {"kind": v["kind"], "reason": str(v.get("reason") or "")[:MAX_REASON]}
                      for to, v in verdicts.items()},
        }
    merged = {**read(paths), **checked}
    paths.ensure()
    handle, partial = tempfile.mkstemp(dir=paths.root, prefix=".wire-kinds-", suffix=".partial")
    with os.fdopen(handle, "w") as out:
        out.write(json.dumps(merged, ensure_ascii=False, indent=2))
    os.replace(partial, paths.wire_kinds)
    return checked
