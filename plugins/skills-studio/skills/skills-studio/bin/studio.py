#!/usr/bin/env python3
"""skills-cli: the Skills Studio's machinery. Every command prints JSON and exits non-zero on failure."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from sx import graph, insights, lease, tasks, wirekinds
from sx.copying import CopyError, copy_skill
from sx.graph import LEVELS
from sx.lease import LeaseHeld
from sx.scan import scan
from sx.state import StudioPaths, running
from sx.tasks import TaskError
from sx.insights import InsightsError
from sx.wirekinds import KindsError
from sx.wires import wires

SERVER = Path(__file__).resolve().parent.parent / "server.py"
WATCH_EVERY = 1.0
RENEW_EVERY = 60.0
OPEN_TIMEOUT = 10.0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="skills-cli",
        description="Scan, wire and check a project's Claude skills, and run the studio's tasks. Prints JSON.",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=".", help="project folder (default: current)")
    common.add_argument("--home", default=str(Path.home()), help="home folder (default: yours)")
    commands = parser.add_subparsers(dest="command", metavar="command")

    commands.add_parser("scan", parents=[common], help="every skill the project can see, described")
    commands.add_parser("graph", parents=[common], help="the scan plus the wires between skills")
    check = commands.add_parser("check", parents=[common], help="the local checks' findings, worst first")
    check.add_argument("--text", action="store_true", help="one line per finding, for reading")

    commands.add_parser("open", parents=[common], help="start the studio for this project if it is not running; print its URL")
    commands.add_parser("stop", parents=[common], help="stop this project's studio server")

    held = commands.add_parser("lease", parents=[common], help="one studio session per project")
    held.add_argument("action", choices=["take", "renew", "release"])
    held.add_argument("--holder", required=True, help="this session's lease name")

    watch = commands.add_parser("watch", parents=[common], help="one line per new task, for ever; keeps the lease")
    watch.add_argument("--holder", required=True, help="this session's lease name")

    commands.add_parser("tasks", parents=[common], help="tasks waiting and active")
    task = commands.add_parser("task", parents=[common], help="one task: submit, show, start or file it")
    task.add_argument("action", choices=["submit", "show", "start", "progress", "done"])
    task.add_argument("ref", help="the task as JSON (submit) or its id")
    task.add_argument("--outcome", choices=tasks.OUTCOMES, help="done: how it ended")
    task.add_argument("--note", default="", help="done: one line on what was done, or why not; progress: where it is now")

    copy = commands.add_parser("copy", parents=[common], help="copy a skill into the project under a new name")
    copy.add_argument("source", help="the skill's id")
    copy.add_argument("name", help="the new name")

    kinds = commands.add_parser("kinds", parents=[common], help="Analyse: which wires are calls and which mentions")
    kinds.add_argument("action", choices=["pending", "save"])
    kinds.add_argument("file", nargs="?", help="save: the judgement as JSON")

    found = commands.add_parser("insights", parents=[common], help="Analyse: findings and suggestions only a reading can make")
    found.add_argument("action", choices=["show", "save"])
    found.add_argument("file", nargs="?", help="save: the findings as a JSON list; replaces the last set")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    project, home = Path(args.project).resolve(), Path(args.home).resolve()
    paths = StudioPaths(project)
    try:
        return COMMANDS[args.command](args, project, home, paths)
    except (TaskError, CopyError, KindsError, InsightsError) as error:
        return _fail(str(error))
    except LeaseHeld as error:
        return _fail(str(error), held_by=error.lease["holder"])


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2), flush=True)
    return 0


def _fail(message, **extra):
    _print({"error": message, **extra})
    return 1


def _scan(args, project, home, paths):
    return _print({"project": str(project), "skills": scan(project, home)})


def _graph(args, project, home, paths):
    built = graph.build(project, home)
    return _print({key: built[key] for key in ("project", "skills", "wires", "flows", "insights")})


def _kinds(args, project, home, paths):
    """Analyse's machinery for calls and mentions: what needs judging, and saving the judgement."""
    skills = scan(project, home)
    found, texts = wires(skills), graph.texts(skills)
    if args.action == "pending":
        return _print({"pending": wirekinds.pending(skills, found, texts, wirekinds.read(paths))})
    if not args.file:
        return _fail("save needs the judgement file")
    try:
        raw = json.loads(Path(args.file).read_text())
    except (OSError, ValueError) as error:
        return _fail(f"cannot read {args.file}: {error}")
    return _print({"saved": sorted(wirekinds.save(paths, raw, skills, found, texts))})


def _insights(args, project, home, paths):
    """Analyse's findings: the ones that still hold, or saving a new set in place of the last."""
    skills = scan(project, home)
    texts = graph.texts(skills)
    if args.action == "show":
        return _print({"insights": insights.live(insights.read(paths), texts)})
    if not args.file:
        return _fail("save needs the findings file")
    try:
        raw = json.loads(Path(args.file).read_text())
    except (OSError, ValueError) as error:
        return _fail(f"cannot read {args.file}: {error}")
    return _print({"saved": len(insights.save(paths, raw, skills, texts))})


def _check(args, project, home, paths):
    built = graph.build(project, home)
    skills, findings = built["skills"], built["findings"]
    if not args.text:
        return _print({"project": str(project), "findings": findings})
    for f in findings:
        where = f"{f['skill']}:{f['line']}" if f["line"] else f["skill"]
        print(f"{f['level']:7}  {where:40}  {f['message']}")
    counts = ", ".join(f"{sum(f['level'] == level for f in findings)} {level}" for level in LEVELS)
    print(f"{len(skills)} skills · {counts}")
    return 0


def _open(args, project, home, paths):
    existing = running(paths)
    if existing:
        return _print({"url": existing["url"], "started": False})
    paths.ensure()
    with open(paths.root / "server.log", "a") as log:
        subprocess.Popen([sys.executable, str(SERVER), "--project", str(project), "--home", str(home)],
                         stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + OPEN_TIMEOUT
    while time.monotonic() < deadline:
        record = running(paths)
        if record:
            return _print({"url": record["url"], "started": True})
        time.sleep(0.2)
    return _fail(f"the studio did not start; see {paths.root / 'server.log'}")


def _stop(args, project, home, paths):
    record = running(paths)
    if not record:
        return _print({"stopped": False})
    os.kill(record["pid"], signal.SIGTERM)
    return _print({"stopped": True, "pid": record["pid"]})


def _lease(args, project, home, paths):
    if args.action == "release":
        lease.release(paths, args.holder)
        return _print({"released": True})
    action = lease.take if args.action == "take" else lease.renew
    return _print(action(paths, args.holder))


def _watch(args, project, home, paths):
    """Monitor's event stream: one line per task that arrives, waiting ones first. It renews the
    lease as it goes and stops, saying so, if another session has taken it."""
    seen, renewed = set(), 0.0
    while True:
        if time.monotonic() - renewed >= RENEW_EVERY:
            try:
                lease.renew(paths, args.holder)
            except LeaseHeld as error:
                print(json.dumps({"lease_lost": error.lease["holder"]}), flush=True)
                return 1
            renewed = time.monotonic()
        for task in tasks.new_since(paths, seen):
            print(json.dumps({"task": task["id"], "kind": task["kind"]}), flush=True)
        time.sleep(WATCH_EVERY)


def _tasks(args, project, home, paths):
    return _print({"tasks": tasks.in_flight(paths)})


def _task(args, project, home, paths):
    if args.action == "submit":
        try:
            raw = json.loads(args.ref)
        except ValueError:
            return _fail("submit takes the task as JSON")
        return _print(tasks.submit(paths, raw, scan(project, home)))
    if args.action == "show":
        found = [t for t in tasks.in_flight(paths) if t["id"] == args.ref]
        if not found:
            return _fail(f"no task {args.ref} waiting or active")
        return _print(_brief(found[0], scan(project, home)))
    if args.action == "start":
        skills = scan(project, home)
        return _print(_brief(tasks.start(paths, args.ref, skills), skills))
    if args.action == "progress":
        if not args.note:
            return _fail("progress needs --note")
        updated = tasks.progress(paths, args.ref, args.note)
        return _print({"id": updated["id"], "progress": updated["progress"]})
    if not args.outcome:
        return _fail("done needs --outcome")
    finished = tasks.done(paths, args.ref, args.outcome, args.note)
    return _print({k: v for k, v in finished.items() if k not in ("before", "after")})


def _brief(task, skills):
    """A task as the session needs it: the fields, and the file it changes. Texts stay on disk."""
    brief = {k: v for k, v in task.items() if k not in ("before", "after")}
    brief["target_file"] = tasks.target_file(task, skills)
    return brief


def _copy(args, project, home, paths):
    skills = scan(project, home)
    tasks.validate({"kind": "copy", "source": args.source, "name": args.name}, skills)
    source = next(s for s in skills if s["id"] == args.source)
    made = copy_skill(project / ".claude" / "skills", source, args.name)
    return _print({"path": str(made), "copied_from": args.source})


COMMANDS = {
    "scan": _scan, "graph": _graph, "check": _check, "open": _open, "stop": _stop, "lease": _lease,
    "watch": _watch, "tasks": _tasks, "task": _task, "copy": _copy, "kinds": _kinds, "insights": _insights,
}


if __name__ == "__main__":
    sys.exit(main())
