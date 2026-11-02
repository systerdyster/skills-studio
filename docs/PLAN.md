# Skills Studio — plan

Builds the design in [DESIGN.md](DESIGN.md). Each task ends in something that runs and has its own
commit. Logic (scanning, parsing, wires, checks, tasks) is built test-first; the page is checked by
hand in a browser.

## Shape

Mirrors the software factory's layout, so the two plugins read alike:

```
.claude-plugin/marketplace.json        local marketplace, one plugin
plugins/skills-studio/
  .claude-plugin/plugin.json
  bin/skills-cli                       sh shim → skills/skills-studio/bin/studio.py
  bin/skills-studio                    sh shim → skills/skills-studio/server.py
  skills/skills-studio/
    SKILL.md                           /skills-studio: start, watch, run tasks
    server.py                          127.0.0.1 + token, serves the page and the JSON API
    studio.html                        the page
    vendor/                            canvas library, pinned, no CDN
    bin/studio.py                      skills-cli entry: prints JSON
    bin/sx/                            scan · frontmatter · wires · checks · tasks · state
    bin/tests/                         unittest, stdlib only
```

- Python standard library only, as in the factory. Tests: `python3 -m unittest discover` in `bin/`.
- Studio state lives in `.skills-studio/` in the project, git-ignored: `inbox/`, `done/`,
  `analysis/`, `lease.json`.
- Canvas library: **Drawflow** (MIT, vanilla JS, one JS and one CSS file, no build step, Node-RED-like
  nodes and wires). Vendored at a pinned version. If it falls short in task 6, LiteGraph is the
  fallback; anything needing a bundler is ruled out.

## Tasks

### 1. Skeleton
Marketplace, plugin manifest, the two shims, an empty `SKILL.md`, the test runner.
**Done:** `claude plugin validate plugins/skills-studio` passes; `bin/skills-cli --help` runs; the test
suite runs (empty).

### 2. Scan and parse
`skills-cli scan` finds skills in the project's `.claude/skills/`, `~/.claude/skills/` (following
symlinks) and installed plugins, and prints one record each: name, source, path, frontmatter,
body, size, modified, ≈tokens for listing and body.
Frontmatter is parsed by a small reader of our own (stdlib has no YAML) that handles what skills
use: scalars, quoted strings, lists, one nested map (`metadata:`). Anything it cannot read is a
parse error on that skill, not a crash.
**Done:** tests on fixture skills cover a clean skill, missing frontmatter, broken frontmatter,
quoted description with colons, nested `metadata`, a symlinked folder whose name differs from the
skill's `name`. Run against this machine, it lists the ten user skills by their `name`, not their
folder.

### 3. Wires
`skills-cli graph` adds wires: A → B for every whole-word mention of B's name in A's body; a
mention of a name not in scope is a broken wire. Order is the position of the first mention.
**Done:** tests cover a plain call, an awkward mention (still a wire), a name that is a substring of
another (`brain-review` vs `brain-review-security`), a missing target (broken), a self-mention
(ignored). Against this machine, `brain-code-review` wires to the four `brain-review-*` skills.

### 4. Local checks
`skills-cli check`: missing/broken frontmatter, missing `name`/`description`, broken wires,
duplicate names across sources, description too long/short, trigger overlap by word similarity,
personal content in a copy (`~/Brain`, vault pointers), `copied_from` source changed since copy.
Thresholds live in one place, named.
**Done:** one test per check, firing and not firing.

### 5. Server
`server.py` on 127.0.0.1, random port and token, Host check — the factory's approach. API:
`GET /graph` (scan + wires + checks for the project), `POST /task` (writes a task to `inbox/`),
`GET /analysis`. Read-only scope enforced here: a task may only name project skills as targets.
**Done:** tests for token refusal, wrong Host, a task naming a user skill refused, a valid task
landing in `inbox/` as one JSON file.

### 6. Canvas
`studio.html` with Drawflow: project skills as nodes with a warning badge, wires from `/graph`
(broken in red), palette with project / user / plugin (plugin behind a filter, the latter two
read-only). Drawing a wire, Deploy, Analyse, New skill and Copy as template each post a task.
Double-click opens the skill view: frontmatter, body, lints, ≈tokens; name and description edit in
place (as a task).
**Done:** checked by hand in a browser against a fixture project and against this machine.
Layout positions are kept in `.skills-studio/layout.json`, never in the skills.

### 7. Tasks and the session
`SKILL.md` for `/skills-studio`:
- take the lease, or name the session that holds it;
- start the server, open the page;
- arm a `Monitor` on `inbox/` (poll with `ls`), re-arm on expiry and on start, and first run any
  task already waiting;
- for each task: show what it asks, do it with the developer in the chat (Deploy edits the parent's
  text; New skill hands over to skill-creator; Copy as template copies, renames, writes
  `metadata.copied_from`), then move it to `done/` with its outcome.

Task kinds and their fields are one schema, shared by `server.py` and `SKILL.md` through
`skills-cli task show`.
**Done:** a run-through in a fixture project: draw a wire, Deploy, see the session wake and edit
the parent, see the wire on the canvas after reload; a second session refused by the lease.

### 8. Analyse
An Analyse task makes the session read all project skills (with user and plugin skills as reference)
and write suggestions to `analysis/` in one schema: split, merge, tighten, reuse — each with the
skills it touches, a reason, and the Deploy task it would become.
**Done:** run on a fixture project with a known-too-big skill and two overlapping ones; both show
up as suggestions; sending one becomes a Deploy task.

### 9. Before and after
For a Deploy that rewrites a parent, the skill view shows the parent before and after side by side
(the previous text kept in the task's `done/` record), so the developer can run it and judge.
**Done:** visible after the task-7 run-through.

## Order and checkpoints

1–4 are the CLI and stand on their own: after task 4, `skills-cli check` is already useful in the
terminal. Checkpoint with Fredrik after 4 and after 7.

## Left open, on purpose

- A mod as a quieter watcher than `Monitor` (no empty wake-ups every 30 minutes). Revisit after 7.
- Behaviour-test harness for splits. Its own project, if ever.
