# Skills Studio

A workspace in the browser for a project's Claude Code skills. It shows which skills call which, how
much each one is used and what it costs, and lets you read, edit and tidy them — with the Claude
session that opened the studio doing the writing, in the chat, where you can see and steer it.

Skills tend to grow and tangle: one skill mentions five others, two overlap, a third was never used.
The studio is there to make that visible and cheap to fix.

## What you see

- **Cards.** Every project skill that nothing calls is a card. The skills it calls sit inside it, in
  the order it calls them; what it only *mentions* is listed at its foot. A skill called from several
  places is shown in full once and collapsed elsewhere; a loop is marked, not followed.
- **Usage.** Each card shows how often the skill has been used. Skills never used are faded. The
  numbers come from Claude Code's own `/skill-doctor` report.
- **Findings.** Local checks flag what needs a look: missing or broken frontmatter, a description too
  long or too short, duplicate names, triggers that overlap, references to skills that do not exist.
- **The skill itself.** Opening a card shows the whole `SKILL.md` on one page, in two parts:
  - *Every turn* — the frontmatter Claude reads in every session to decide when to use the skill,
    with what it costs and the description's length against the 1024-character limit;
  - *When it runs* — the rest of the file, rendered as markdown, with every skill it names marked as
    a call, a mention or missing.

## Calls and mentions

A reference is a **call** when following the skill makes Claude run the other one — as a step, a
preflight or a handoff. Anything else is a **mention**: a *Related* link, a "don't run it here", a
pointer for the developer. Only calls nest a card inside another.

Telling the two apart is a judgement, so the studio does not guess: **Analyse** asks the Claude
session to judge every reference and keeps the verdict per skill, together with a fingerprint of its
text. When a skill's text changes, its references are judged again. Until then they count as calls.

## Changing skills

The studio only ever writes the project's own skills (`.claude/skills/`). User, synced and plugin
skills are read-only; one can be copied into the project as a template.

Every change is a task the page hands to the Claude session, which does it with you in the chat and
shows the diff:

- **Edit** a skill in place — name, description and the markdown text — and save it as one task.
- **Change it with Claude** in words ("extract the git handling into its own skill").
- **Improve it with skill-creator**, optionally with a focus.
- **Add a call** to another skill; Claude decides where in the text it belongs.
- **Delete** a skill; Claude asks first what to do with the skills that name it.
- **New skill** from a name, a description and an intent.

The session never commits. What to keep is yours to decide.

## Install

The repository is a Claude Code plugin marketplace with one plugin.

```sh
claude plugin marketplace add systerdyster/skills-studio
claude plugin install skills-studio@skills-studio
```

To work on the studio itself, add your clone instead: `claude plugin marketplace add /path/to/skills-studio`.

Needs Claude Code and Python 3. Nothing else: the server and the CLI use the standard library only,
and the page loads nothing from outside.

## Use

In the project whose skills you want to see, run:

```
/skills-studio
```

The session takes a lease (one studio per project), starts the server on `127.0.0.1` with a random
token, opens the page and watches for tasks. Keep talking to the session as usual in between. *Close
studio* on the page, or saying you are done, stops it.

The studio keeps its state in `.skills-studio/` in the project — tasks, the call/mention verdicts, the
lease — and that folder ignores itself in git, so the project's `.gitignore` is never touched.

## How it is built

```
.claude-plugin/marketplace.json    the marketplace
plugins/skills-studio/
  bin/skills-cli                   the session's machinery: prints JSON
  bin/skills-studio                the server
  skills/skills-studio/
    SKILL.md                       /skills-studio: start, watch, carry out tasks
    server.py                      127.0.0.1 + token; the page and its JSON API
    studio.html                    the page, no libraries
    bin/sx/                        scan · frontmatter · wires · checks · flows · usage · tasks · state
    bin/tests/                     unittest
docs/DESIGN.md                     why it works the way it does
```

The page never asks a model anything itself. It writes a task to `.skills-studio/inbox/`; the session's
watcher wakes it, and the work happens in the chat.

Run the tests from `plugins/skills-studio/skills/skills-studio/bin`:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
```
