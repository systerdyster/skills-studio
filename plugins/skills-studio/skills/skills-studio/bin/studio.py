#!/usr/bin/env python3
"""skills-cli: the Skills Studio's machinery. Every command prints JSON and exits non-zero on failure."""

import argparse
import json
import sys
from pathlib import Path

from sx.scan import scan
from sx.wires import wires


def build_parser():
    parser = argparse.ArgumentParser(
        prog="skills-cli",
        description="Scan, wire and check a project's Claude skills. Prints JSON.",
    )
    commands = parser.add_subparsers(dest="command", metavar="command")
    for name, summary in [
        ("scan", "every skill the project can see, described"),
        ("graph", "the scan plus the wires between skills, read from their bodies"),
    ]:
        command = commands.add_parser(name, help=summary)
        command.add_argument("--project", default=".", help="project folder (default: current)")
        command.add_argument("--home", default=str(Path.home()), help="home folder (default: yours)")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    project, home = Path(args.project).resolve(), Path(args.home).resolve()
    skills = scan(project, home)
    out = {"project": str(project), "skills": skills}
    if args.command == "graph":
        out["wires"] = wires(skills)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
