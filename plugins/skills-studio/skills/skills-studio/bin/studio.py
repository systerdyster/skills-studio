#!/usr/bin/env python3
"""skills-cli: the Skills Studio's machinery. Every command prints JSON and exits non-zero on failure."""

import argparse
import json
import sys
from pathlib import Path

from sx.checks import checks
from sx.scan import scan
from sx.wires import wires

LEVELS = ("error", "warning", "info")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="skills-cli",
        description="Scan, wire and check a project's Claude skills. Prints JSON.",
    )
    commands = parser.add_subparsers(dest="command", metavar="command")
    for name, summary in [
        ("scan", "every skill the project can see, described"),
        ("graph", "the scan plus the wires between skills, read from their bodies"),
        ("check", "the local checks' findings, worst first"),
    ]:
        command = commands.add_parser(name, help=summary)
        command.add_argument("--project", default=".", help="project folder (default: current)")
        command.add_argument("--home", default=str(Path.home()), help="home folder (default: yours)")
    commands.choices["check"].add_argument("--text", action="store_true", help="one line per finding, for reading")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    project, home = Path(args.project).resolve(), Path(args.home).resolve()
    skills = scan(project, home)
    if args.command == "check":
        return _check(project, skills, args.text)
    out = {"project": str(project), "skills": skills}
    if args.command == "graph":
        out["wires"] = wires(skills)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _check(project, skills, as_text):
    sources = {s["id"]: Path(s["path"]).read_text(encoding="utf-8", errors="replace") for s in skills}
    findings = sorted(checks(skills, wires(skills), sources),
                      key=lambda f: (LEVELS.index(f["level"]), f["skill"], f["check"]))
    if not as_text:
        print(json.dumps({"project": str(project), "findings": findings}, ensure_ascii=False, indent=2))
        return 0
    for f in findings:
        where = f"{f['skill']}:{f['line']}" if f["line"] else f["skill"]
        print(f"{f['level']:7}  {where:40}  {f['message']}")
    counts = ", ".join(f"{sum(f['level'] == level for f in findings)} {level}" for level in LEVELS)
    print(f"{len(skills)} skills · {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
