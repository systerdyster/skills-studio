"""Where each node sits on the canvas: .skills-studio/layout.json, never in the skills themselves."""

import json
import numbers
import os
import tempfile

MAX_NODES = 1000


class LayoutError(ValueError):
    pass


def read(paths):
    try:
        return json.loads(paths.layout.read_text())
    except (OSError, ValueError):
        return {"positions": {}}


def write(paths, raw):
    positions = raw.get("positions") if isinstance(raw, dict) else None
    if not isinstance(positions, dict) or len(positions) > MAX_NODES:
        raise LayoutError("expected {\"positions\": {id: [x, y]}}")
    for key, value in positions.items():
        if not (isinstance(key, str) and isinstance(value, list) and len(value) == 2
                and all(isinstance(v, numbers.Real) and not isinstance(v, bool) for v in value)):
            raise LayoutError(f"position of {key!r} must be [x, y]")
    layout = {"positions": positions}
    paths.root.mkdir(parents=True, exist_ok=True)
    # A temporary file of its own per write: the page may save twice at once.
    handle, partial = tempfile.mkstemp(dir=paths.root, prefix=".layout-", suffix=".partial")
    with os.fdopen(handle, "w") as out:
        out.write(json.dumps(layout))
    os.replace(partial, paths.layout)
    return layout
