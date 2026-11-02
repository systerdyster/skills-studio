"""The project's flows, so the canvas can show one at a time. A flow starts at an entry — a project
skill nothing outside its own loop calls — and holds everything the entry reaches. Only project skills
are followed: a user or plugin skill a flow calls is a leaf of it, and never an entry."""


def flows(skills, wires):
    project = sorted(s["id"] for s in skills if s.get("source") == "project")
    calls = {}
    for wire in wires:
        if not wire.get("broken"):
            calls.setdefault(wire["from"], set()).add(wire["to"])
    reach = {skill: _reachable(skill, calls, set(project)) for skill in project}
    entries = []
    for skill in project:
        loop = sorted(other for other in project if skill in reach[other] and other in reach[skill])
        callers = {other for other in project if skill in reach[other] and other not in loop}
        if not callers and loop[0] == skill:
            entries.append(loop)
    return [{"entry": loop, "skills": sorted(set().union(*(reach[skill] for skill in loop)))} for loop in entries]


def _reachable(start, calls, followed):
    seen = {start}
    todo = [start]
    while todo:
        for target in calls.get(todo.pop(), ()):
            if target not in seen:
                seen.add(target)
                if target in followed:
                    todo.append(target)
    return seen
