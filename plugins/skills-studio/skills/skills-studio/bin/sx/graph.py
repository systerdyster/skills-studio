"""The whole picture of a project's skills: the scan, the wires, the local checks' findings and the
flows the canvas can show one at a time."""

from pathlib import Path

from sx.checks import checks
from sx.flows import flows
from sx.scan import scan
from sx.wires import wires

LEVELS = ("error", "warning", "info")


def build(project, home):
    skills = scan(project, home)
    found_wires = wires(skills)
    sources = {s["id"]: Path(s["path"]).read_text(encoding="utf-8", errors="replace") for s in skills}
    findings = sorted(checks(skills, found_wires, sources),
                      key=lambda f: (LEVELS.index(f["level"]), f["skill"], f["check"]))
    return {"project": str(project), "skills": skills, "wires": found_wires, "findings": findings,
            "flows": flows(skills, found_wires)}
