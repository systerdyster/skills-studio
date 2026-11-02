"""The whole picture of a project's skills: the scan, the wires (each a call or a mention once Analyse
has judged it), the findings — the local checks' and Analyse's that still hold and were not dismissed — and the flows. Flows
follow calls only; a wire not judged yet counts as one."""

from pathlib import Path

from sx import insights, wirekinds
from sx.checks import checks
from sx.flows import flows
from sx.scan import scan
from sx.state import StudioPaths
from sx.wires import wires

LEVELS = ("error", "warning", "info")


def build(project, home):
    paths = StudioPaths(project)
    skills = scan(project, home)
    sources = texts(skills)
    found_wires = wirekinds.apply(wires(skills), sources, wirekinds.read(paths))
    analysed, dismissed = insights.partition(insights.live(insights.read(paths), sources), insights.dismissals(paths))
    findings = sorted(checks(skills, found_wires, sources) + insights.as_findings(analysed),
                      key=lambda f: (LEVELS.index(f["level"]), f["skill"], f["check"]))
    calls = [w for w in found_wires if w["kind"] != "mention"]
    return {"project": str(project), "skills": skills, "wires": found_wires, "findings": findings,
            "insights": analysed, "dismissed": dismissed, "flows": flows(skills, calls)}


def texts(skills):
    """Each skill's SKILL.md as it is on disk, by id."""
    return {s["id"]: Path(s["path"]).read_text(encoding="utf-8", errors="replace") for s in skills}
