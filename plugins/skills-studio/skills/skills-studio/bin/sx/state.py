"""Where the studio keeps its state: .skills-studio/ in the project, git-ignored."""

import json
import os
import socket
from pathlib import Path


class StudioPaths:
    def __init__(self, project):
        self.project = Path(project)
        self.root = self.project / ".skills-studio"
        self.inbox = self.root / "inbox"
        self.active = self.root / "active"
        self.done = self.root / "done"
        self.analysis = self.root / "analysis"
        self.server = self.root / "server.json"
        self.lease = self.root / "lease.json"
        self.wire_kinds = self.root / "wire-kinds.json"
        self.insights = self.root / "insights.json"

    def ensure(self):
        """Create the studio's folder, ignored by git from inside, so the project's .gitignore stays
        untouched."""
        self.root.mkdir(parents=True, exist_ok=True)
        ignore = self.root / ".gitignore"
        if not ignore.exists():
            ignore.write_text("*\n")
        return self.root


def running(paths):
    """The studio already serving this project, from server.json: its process is alive and its port
    answers. A record left by one that died is removed."""
    try:
        record = json.loads(paths.server.read_text())
        os.kill(record["pid"], 0)
        socket.create_connection(("127.0.0.1", record["port"]), timeout=1).close()
        return record
    except (OSError, ValueError, KeyError, TypeError):
        paths.server.unlink(missing_ok=True)
        return None
