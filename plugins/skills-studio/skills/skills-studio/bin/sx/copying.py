"""Copy a skill into the project as a template: the whole folder (links resolved), the frontmatter's
name changed, and the origin recorded under metadata as copied_from and copied_hash. The frontmatter
is edited line by line rather than re-written, so everything else in it stays as its author wrote it."""

import re
import shutil
from pathlib import Path

from sx.checks import content_hash
from sx.frontmatter import parse

TOP_KEY = re.compile(r"^([A-Za-z0-9_-]+):")


class CopyError(RuntimeError):
    pass


def copy_skill(project_skills, source, name):
    target = Path(project_skills) / name
    if target.exists():
        raise CopyError(f"{target} already exists")
    source_file = Path(source["path"])
    text = source_file.read_text(encoding="utf-8")
    shutil.copytree(source_file.parent.resolve(), target, symlinks=False)
    made = target / "SKILL.md"
    made.write_text(_renamed(text, name, source["id"], content_hash(text)), encoding="utf-8")
    return made


def _renamed(text, name, origin, digest):
    frontmatter, body = parse(text)
    origin_lines = [f"  copied_from: {origin}", f"  copied_hash: {digest}"]
    if frontmatter is None:
        return "\n".join(["---", f"name: {name}", "metadata:", *origin_lines, "---", body])
    lines = text.split("\n")
    end = lines.index("---", 1)
    head = lines[1:end]
    head = [f"name: {name}" if line.startswith("name:") else line for line in head]
    if not any(line.startswith("name:") for line in head):
        head.insert(0, f"name: {name}")
    if any(line.startswith("metadata:") for line in head):
        at = next(i for i, line in enumerate(head) if line.startswith("metadata:")) + 1
        while at < len(head) and not TOP_KEY.match(head[at]):
            at += 1
        head[at:at] = origin_lines
    else:
        head += ["metadata:", *origin_lines]
    return "\n".join(["---", *head, "---", body])
