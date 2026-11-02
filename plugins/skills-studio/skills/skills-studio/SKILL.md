---
name: skills-studio
description: "Open the Skills Studio: a workspace in the browser for this project's Claude skills — see which call which and how much each is used, check them, and edit, split, merge and tighten them together with Claude. Use when the user types /skills-studio, or asks to open the skills studio, see the project's skills as a graph, or work on the project's skills visually."
metadata:
  type: reference
---

# /skills-studio

The studio is a page in the browser; this session is the one that does its work. The page writes a
task to `.skills-studio/inbox/` when the developer draws a wire, sends an edit, asks for a change, a
new skill, a copy or an analysis. A watcher wakes this session; you carry the task out **with the
developer in the chat**, then file it.

Its machinery is `skills-cli`, which the plugin puts on PATH (Python standard library only; every
command prints JSON and exits non-zero on failure). Below, `S` means `skills-cli`. Run every command
from the project's root.

**The studio writes only the project's own skills** (`.claude/skills/` in this repository). User,
synced and plugin skills are read-only: never change them, whatever a task says. The server already
refuses such tasks; refuse one that reaches you anyway, and file it `declined`.

## Start

1. **Lease.** Pick a holder name for this session once — `studio-` and six random hex characters —
   and use the same one for every command below. `S lease take --holder <name>`. If it fails with
   `held_by`, another session runs the studio for this project: say so, with the holder, and stop.
2. **Server.** `S open` prints the URL (it starts the server if it is not running). Open it with
   `open "<url>"` and give the developer the link.
3. **Watcher.** Start a Monitor on `S watch --holder <name>`, described as "Skills Studio tasks",
   timeout 30 minutes (the most a Monitor allows). Each line it prints is one event:
   - `{"task": id, "kind": …}` — a task arrived: carry it out (below).
   - `{"lease_lost": holder}` — another session took the studio over: say so and stop watching.
   - When the Monitor expires, run `S lease renew --holder <name>` and start it again. Say nothing
     about the expiry unless renewing fails.
   The watcher reports tasks already waiting when it starts, so nothing in the inbox is missed.
4. Tell the developer, in one or two lines, that the studio is open and that you will take its
   tasks as they come; they can keep talking to you here in between.

## Carrying out a task

1. `S task start <id>` moves it to active and prints its fields and `target_file`, the SKILL.md it
   changes (none for `new`, `copy` and `analyse`). Read that file before changing it.
2. Do the kind's work below, showing the developer what you are doing.
3. `S task done <id> --outcome done|declined|failed --note "<one line>"`. The note says what changed,
   or why not. The studio keeps the text before and after for the developer to compare.

**The text is the only source of truth.** A wire exists because a skill's body names another skill.
Name skills the way Claude knows them: plugin skills by their qualified name (`atlassian:triage-issue`),
synced skills as `anthropic-skills:<name>`, project and user skills by their name; a one-word name in
backticks (`` `commit` ``). Never add frontmatter fields to record links.

| Kind | Fields | What to do | Ask first? |
|---|---|---|---|
| `link` | `from`, `to` | Make `from`'s body call `to` where it belongs in its steps. If where is not clear from the text, ask. | No — apply, show the diff |
| `unlink` | `from`, `to` | Remove every mention of `to` from `from`'s body, keeping the steps whole. If `to` did real work there, say what is lost. | No — apply, show the diff |
| `edit` | `skill`, `field`, `value` | `description`: replace it. `name`: change the frontmatter name, rename the skill's folder to match, and update every project skill that names it. | Only for `name`, listing what it touches |
| `save` | `skill`, `name`, `description`, `body` | The developer edited the skill on the page. Write `description` and `body` exactly as given — the body is everything after the frontmatter — keeping every other frontmatter field. A changed `name` follows the `edit` rule for names. Show the diff. | Only for `name`, listing what it touches |
| `change` | `skill`, `text` | Do what `text` asks. Splitting a skill: the extracted part becomes a skill of its own that can also be used alone; the parent calls it by name at each place the part was. | Yes — propose, then apply on their yes |
| `improve` | `skill`, `focus` | Improve the skill with a skill-creator skill (`anthropic-skills:skill-creator`, or the `skill-creator` plugin's), aimed at `focus` when it is given — otherwise at what the skill most needs. None in scope: say so and file it `declined`. | Yes — propose, then apply on their yes |
| `delete` | `skill` | Delete the skill's folder. First list every skill that names it (`S graph`, wires to it) and ask whether to remove those mentions too or leave them as broken wires. | Yes — always, naming the callers |
| `new` | `name`, `description`, `intent` | Write `.claude/skills/<name>/SKILL.md` with the developer, using a skill-creator skill when one is available. | Yes |
| `copy` | `source`, `name` | `S copy <source> <name>`, then `S check --text` and show the findings for the copy — personal content above all, since it lands in a shared repository. | No |
| `analyse` | — | Judge every wire a **call** or a **mention**, then record the **findings** (both below). Suggestions — splits, merges — are not built yet: say so in the note. | No — save, then sum up |
| `close` | — | The developer pressed *Close studio*; the server has already stopped itself. Do **Stop** below. | No |

**Calls and mentions.** `S kinds pending` lists the project skills whose wires are not judged for
their text as it is now, each wire with every line that names its target. Read those lines in their
place in the skill, then judge each wire:

- **call** — following the skill makes Claude run the other skill: as a step, a preflight, or by
  handing the work over to it.
- **mention** — anything else: a *Related* link, a "don't run it here", a note on what the other skill
  does or expects, a pointer that leaves running it to the developer.

A wire with one call among several mentions is a call. Write the judgement to a scratch file as
`{"<skill>": {"fingerprint": "<from pending>", "wires": {"<to>": {"kind": "call|mention", "reason":
"<the deciding words, quoted>"}}}}` and run `S kinds save <file>`; it refuses a skill whose text
changed meanwhile.

**Findings.** Then read all the project's skills, with `S check --text` for what the local checks
already say, and record what only a reading can tell — the studio shows it above the cards and on
each skill concerned:

| `kind` | When |
|---|---|
| `disagreement` | Two skills' texts contradict each other about how they work together — who calls whom, who owns a step. Name both, quote both. |
| `dead-reference` | A skill names one that does not exist, or by a name Claude does not know it by (a folder name for a skill named otherwise). |
| `procedure-in-description` | The description spends its every-turn tokens on how the skill works rather than what it does and when to use it. |
| `unused` | Usage shows it never or rarely runs; say why you think so — triggers that overlap another's, a name nobody would say. |
| `badly-written` | Unclear, contradictory or padded: steps that can't be followed, rules that clash, a body far longer than its job. Say what, specifically. |

Write them to a scratch file as a list, `[{"kind": "…", "skills": ["<id>", …], "message": "<one or
two sentences>", "lines": {"<id>": [<line>, …]}}]`, and run `S insights save <file>`. It replaces the
last set, so include every finding that still holds; a finding disappears by itself once any of its
skills' text changes. Don't fix anything: findings are for the developer. Sum up in the chat: how many
calls and mentions, and the findings, worst first.

After any task that changed skills, run `S check --text` and mention new findings for the skills you
touched. Never commit: the developer decides what to keep.

If the developer says to undo a task, restore the target's text as `task start` found it — git shows
it, or the task's record in `.skills-studio/done/` holds it under `before`.

## Stop

The studio stops when the developer presses *Close studio* on the page (a `close` task arrives), or
says in the chat that they are done. Either way:

1. Finish the task you are in the middle of, if any. Do not start tasks that are still waiting: they
   stay in the inbox for the next time the studio opens. Say how many, if any.
2. `S task done <close id> --outcome done --note "Closed from the page."` when a `close` task started it.
3. Stop the Monitor, then `S stop` (the server; a no-op when the page already stopped it) and
   `S lease release --holder <name>`.
4. Say in one line that the studio is closed and that `/skills-studio` opens it again.
