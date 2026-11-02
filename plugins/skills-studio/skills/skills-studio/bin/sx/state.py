"""Where the studio keeps its state: .skills-studio/ in the project, git-ignored."""

from pathlib import Path


class StudioPaths:
    def __init__(self, project):
        self.project = Path(project)
        self.root = self.project / ".skills-studio"
        self.inbox = self.root / "inbox"
        self.done = self.root / "done"
        self.analysis = self.root / "analysis"
        self.server = self.root / "server.json"
        self.lease = self.root / "lease.json"
        self.layout = self.root / "layout.json"
