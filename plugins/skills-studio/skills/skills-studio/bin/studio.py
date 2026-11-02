#!/usr/bin/env python3
"""skills-cli: the Skills Studio's machinery. Every command prints JSON and exits non-zero on failure."""

import argparse
import json
import sys
from pathlib import Path

from sx.scan import scan


def build_parser():
    parser = argparse.ArgumentParser(
        prog="skills-cli",
        description="Scan, wire and check a project's Claude skills. Prints JSON.",
    )
    commands = parser.add_subparsers(dest="command", metavar="command")
    scanning = commands.add_parser("scan", help="every skill the project can see, described")
    scanning.add_argument("--project", default=".", help="project folder (default: current)")
    scanning.add_argument("--home", default=str(Path.home()), help="home folder (default: yours)")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    project, home = Path(args.project).resolve(), Path(args.home).resolve()
    print(json.dumps({"project": str(project), "skills": scan(project, home)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
