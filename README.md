# claude-session-doctor

> Diagnose and repair corrupted Claude Code session files. Recover bricked sessions instead of starting over.

A single-file Python CLI that scans your Claude Code session history (`~/.claude/projects/*/*.jsonl`), shows everything wrong with each session, and lets you choose which problems to fix. Every write is preceded by an automatic timestamped backup, and every fix can be previewed without touching disk.

No dependencies — Python 3.8+ standard library only.

**Current version: 1.1** — adds a recommendation engine, preview-before-confirm, `--dry-run`, `--restore`, `--fix-all`, `--json`, and four new detectors. See the [changelog](CHANGELOG.md).

---

## The problem

Claude Code stores each session as a JSONL file. When the file's history gets structurally corrupted, every subsequent message fails with a 400 from the API and the session becomes unrecoverable through the CLI. The most common form is:

```
API Error: 400 messages.N.content.M: `thinking` or `redacted_thinking` blocks in
the latest assistant message cannot be modified. These blocks must remain as
they were in the original response.
```

Retrying does nothing. Restarting Claude Code does nothing. `claude --resume` lands you right back on the same broken state. Worse, manually trimming lines from the JSONL tends to make it *more* fragile — thinking blocks are cryptographically signed and position-sensitive, so hand-editing easily orphans or mismatches them in new ways.

This tool fixes those structural problems and several more (orphaned tool calls, alternation violations, trailing API-error noise, invalid JSON lines, duplicate messages, etc.) without forcing you to start a fresh session and lose your context.

## Quick start

```bash
git clone https://github.com/premthavare/claude-session-doctor.git
cd claude-session-doctor
chmod +x claude-session-doctor

./claude-session-doctor                          # scan everything, pick & fix interactively
./claude-session-doctor SESSION_ID               # jump straight to one session
./claude-session-doctor --list                   # list all sessions + issue counts
./claude-session-doctor --fix-all SESSION_ID     # non-interactive repair
./claude-session-doctor --restore SESSION_ID     # roll back the most recent change
./claude-session-doctor SESSION_ID --dry-run     # preview without writing
```

A typical recovery: pick the broken session → read the recommendation → press `a` to apply all safe fixes → review the preview → confirm → `claude --resume SESSION_ID`. If that still errors, run again and press `n` for the nuclear option.

## Demo

![claude-session-doctor demo](demo/demo.gif)

A walkthrough of every major feature — diagnosis, the recommendation engine, dry-run preview, `--fix-all`, `--json`, and `--restore`. The clip is generated from real tool output by [`demo/generate.py`](demo/generate.py); see [`demo/README.md`](demo/README.md) to regenerate it.

## What it detects and fixes

| Issue | Severity | What it is | How it's fixed |
|---|---|---|---|
| Interleaved thinking blocks | critical | Consecutive assistant lines with different message IDs and stray thinking blocks — the main cause of the "cannot be modified" error | Remove the thinking-only intruder lines (signature-safe; never mutates signed content) |
| Orphan `tool_use` | critical | Assistant called a tool but there's no matching `tool_result` | Insert a synthetic `tool_result` marked as a session repair |
| Alternation violation | critical | Two consecutive `user` records with no `assistant` turn between them — the API requires alternating roles | Insert a synthetic assistant turn between them |
| Invalid / blank JSON lines | critical | Truncated or partially written lines that break parsing | Drop them |
| Orphan `tool_result` | warning | `tool_result` block referencing a `tool_use` that doesn't exist | Remove the orphan block |
| Empty assistant messages | warning | Assistant entries with empty content arrays | Drop them |
| Trailing API-error / noise | warning | Error messages, system noise, and progress lines at the end | Trim back to the last clean turn |
| Oversized message | warning | A single message larger than 200 KB — context bomb | Reported only — review or salvage |
| Empty `tool_result` content | warning | `tool_result` with null/empty content body | Reported only |
| Duplicate consecutive messages | warning | Same assistant text repeated in two consecutive turns (≥50 chars) | Remove the duplicate |
| Misordered timestamps | info | A record has a timestamp earlier than the previous one — race condition signal | Reported only |
| Oversized session | info | More than 4000 lines — interleaving and auto-compact failures get more likely | Reported only — suggests `/compact` or a fresh start |
| **Nuke option** | n/a | Always available regardless of detection | Strip every `thinking` / `redacted_thinking` block from every assistant message. Text, tool calls, and tool results all preserved. Most reliable cure when targeted fixes don't hold. |

## The recommendation engine

Pressing the wrong button on a recovery tool can cost you a session's worth of work. The recommendation engine reads the diagnosis and tells you what to do, prominently, before the menu:

```
┌────────────────────────────────────────────────────────────────
│ RECOMMENDATION: FIX
│ Critical structural issues, but NO thinking-block corruption.
│ Recommended: `a` (safe fixes only). Nuke is NOT advised here
│ -- it would strip thinking from every message without
│ addressing the actual problems.
└────────────────────────────────────────────────────────────────
```

The label is one of:

- **OK** — session is healthy, no action needed.
- **ADVISE** — only informational issues; consider `/compact` if the session is large.
- **FIX** — there are critical issues; specifies whether targeted fixes are enough or whether nuke should be the fallback.
- **TIDY** — only warnings; safe fixes for hygiene, no nuke.

The engine specifically guards against the most expensive mistake: nuking thinking blocks when no thinking-block corruption is actually present. In that case it explicitly says nuke is **not** advised.

## Preview before confirm

When you select fixes, the tool computes the effect on a deep copy of the session and shows concrete counts before asking you to confirm:

```
Preview:
  • Remove invalid/blank JSON lines: removed 1 invalid/blank line(s)
  • Pair tool_use/tool_result (insert + clean): added 1 synthetic tool_result(s)
  • Trim trailing API-error / noise: trimmed 1 trailing noise line(s)
  Net change: remove 2 line(s), add 1 synthetic line(s)
Proceed? [y/N]
```

If the "net change" doesn't look right, answer `N` and nothing is written. The originals were never touched in the first place.

## Installation

### Option 1: pipx (recommended for general use)

If you have [pipx](https://pipx.pypa.io/) installed:

```bash
pipx install git+https://github.com/premthavare/claude-session-doctor.git
claude-session-doctor --help
```

pipx puts the script onto your `PATH` in an isolated virtual environment, with no impact on your system Python.

### Option 2: Clone and run (no install)

```bash
git clone https://github.com/premthavare/claude-session-doctor.git
cd claude-session-doctor
chmod +x claude-session-doctor
./claude-session-doctor
```

### Option 3: Single-file download (when you just need it working)

```bash
curl -fsSL https://raw.githubusercontent.com/premthavare/claude-session-doctor/main/claude-session-doctor -o claude-session-doctor
chmod +x claude-session-doctor
./claude-session-doctor
```

Stdlib only — no dependencies — so this works on any machine with Python 3.8+.

### Option 4: Put it on your PATH manually

```bash
sudo cp claude-session-doctor /usr/local/bin/
# or, without sudo:
mkdir -p ~/.local/bin
cp claude-session-doctor ~/.local/bin/
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

## Usage

```
Usage: claude-session-doctor [SESSION_ID] [OPTIONS]

Positional:
  SESSION_ID         Session UUID. With no other flags, enters interactive mode.

Mode flags (mutually exclusive — pick one):
  --list             Print every session with its issue count and exit.
  --json             Machine-readable diagnosis to stdout. Optionally with SESSION_ID.
  --fix-all          Non-interactive: apply every safe fix (no nuke) to SESSION_ID.
  --restore          Restore SESSION_ID from its most recent backup.

Modifiers:
  --dir PATH         Use a custom projects directory.
                     Default: ~/.claude/projects
  --dry-run          Preview the effect of any operation without writing.

Exit codes:
  0    Clean / success
  1    Issues detected (diagnosis-only mode)
  2    Fix applied but issues remain
  3    User / input error (no such session, etc.)
```

### Examples

```bash
# Interactive, with recommendation and preview
./claude-session-doctor abaca37e-792e-4168-94f7-0c6a6ef24aa7

# Quick triage across all sessions
./claude-session-doctor --list

# Machine-readable for a monitoring script
./claude-session-doctor --json | jq '.sessions[] | select(.issues | length > 0)'

# Auto-repair every safe issue, no prompts (good for cron)
./claude-session-doctor --fix-all abaca37e-792e-4168-94f7-0c6a6ef24aa7

# Preview what --fix-all would do without writing
./claude-session-doctor --fix-all abaca37e-792e-4168-94f7-0c6a6ef24aa7 --dry-run

# Roll back the most recent change
./claude-session-doctor --restore abaca37e-792e-4168-94f7-0c6a6ef24aa7

# Scan a backup directory
./claude-session-doctor --dir /path/to/backup/.claude/projects
```

### Interactive keys (per session)

```
  a   apply all safe fixes (everything except nuke)
  n   nuke — strip ALL thinking blocks (always available, stable key)
  1,3 comma-separated numbers for specific fixes
  b   back to session list
  q   quit
```

## Safety

- **Automatic backup before any write.** Each repaired session file gets a timestamped backup next to it: `<id>.jsonl.<unix_ts>.backup`. Restore with `--restore SESSION_ID` (one command), or copy the backup over manually.
- **Restore is itself reversible.** Running `--restore` first backs up the current (broken) state before overwriting it with the chosen backup. You can always go forwards again.
- **Atomic writes.** New content is written to `<id>.jsonl.tmp` and atomically `rename`d into place, so a crash mid-write can't leave you with a half-written session.
- **Preview before commit.** Every fix is previewed with concrete change counts before you confirm.
- **Dry-run for everything.** `--dry-run` works with the interactive flow, `--fix-all`, and `--restore`. Use it freely.
- **Idempotent fixes.** Running any fix twice produces the same result as running it once. Applying several in sequence is always safe.
- **Removal over mutation.** Where there's a choice between deleting a corrupt block and rewriting it, the tool deletes. Removal can never invalidate a cryptographic signature; rewriting can.

To restore an original manually if needed:

```bash
cp ~/.claude/projects/myproj/SESSION_ID.jsonl.1730000000.backup \
   ~/.claude/projects/myproj/SESSION_ID.jsonl
```

## JSON output schema

`--json` produces a stable schema suitable for dashboards and monitoring:

```json
{
  "sessions": [
    {
      "id": "abaca37e-...",
      "path": "/Users/.../session.jsonl",
      "project": "my-project",
      "mtime": 1730000000.123,
      "line_count": 13071,
      "issues": [
        {
          "kind": "orphan_tool_use",
          "severity": "critical",
          "summary": "1 tool_use with no matching tool_result",
          "lines": [12131]
        }
      ],
      "recommendation": {
        "level": "warn",
        "label": "FIX",
        "message": "Critical structural issues, but NO thinking-block corruption..."
      }
    }
  ]
}
```

Exit code is `1` if any session has critical issues, `0` otherwise — making it easy to wire into pre-commit hooks or cron checks.

## How the fixes work

Each fix is small, global, and idempotent — running them twice produces the same result as running them once, and selecting several in sequence is always safe.

**Removing interleaved thinking blocks.** When two API responses' chunks land adjacent in the JSONL, Claude Code merges them into a single assistant message containing thinking blocks from *different* signed responses. The API validates each thinking block byte-for-byte against its signature; any mutation breaks it. Rather than try to re-mint signatures (impossible) or merge thinking text (also breaks the signature), the fix removes the stray *thinking-only* intruder lines. Removal can't invalidate a signature, and the conversation's actual text remains intact.

**Pairing tool calls and results.** Every `tool_use` in an assistant message must have a matching `tool_result` in a following user message. The fix finds unmatched `tool_use` blocks and inserts a synthetic user message right after with `is_error: true` and content `[session repaired: original tool result was lost]`. It also strips `tool_result` blocks whose `tool_use_id` references a `tool_use` that no longer exists.

**Repairing alternation.** The API requires user/assistant turns to alternate. When two `user` records appear back-to-back with no `assistant` between, the fix inserts a synthetic assistant turn containing `[session repaired: missing assistant turn]`.

**Trimming trailing noise.** When the session is stuck, the tail of the file accumulates API error entries, system messages, and progress noise. The fix walks backwards from the end deleting non-conversational lines until it reaches the last clean user/assistant message.

**Removing duplicates.** When the same assistant text (≥50 characters) appears in two consecutive assistant turns, the fix keeps the first and drops the rest. Shorter text isn't flagged — duplicate "ok" responses are normal.

**Removing invalid lines.** Truncated writes or partial flushes can leave unparseable lines. They're dropped — they can't be recovered.

**Removing empty assistant messages.** Assistant entries with no content can't represent a turn and are dropped.

**Nuke.** Every `thinking` and `redacted_thinking` block is filtered out of every assistant message's content array. If a message becomes empty as a result, it's dropped. All `text`, `tool_use`, and `tool_result` blocks are preserved. Because there are then zero thinking blocks in the history, the "cannot be modified" error can't physically recur from that source. You lose the model's internal reasoning traces; you keep everything else.

## Out of scope

Some Claude Code errors look similar at first glance but aren't session-file problems. This tool won't help with them; the right response is different in each case:

- **Auth / credentials errors** — re-run `claude login` or check `~/.claude/credentials`.
- **Rate limits / 429s** — wait and retry, or check your plan.
- **Network 5xx / API outages** — check [status.anthropic.com](https://status.anthropic.com).
- **Model unavailability** — fall back to a different model in `~/.claude/config.json` or via CLI flag.
- **Bugs in Claude Code itself** unrelated to history corruption — file an issue at [anthropics/claude-code](https://github.com/anthropics/claude-code/issues).

## Compatibility

- **Python:** 3.8 or newer. Standard library only.
- **OS:** macOS, Linux. Windows works via WSL; native PowerShell support is untested.
- **Claude Code versions:** developed against the current JSONL schema (assistant/user message blocks with `content` arrays of typed blocks). Major future format changes may require an update.

If the JSONL schema changes in a way that breaks detection, please open an issue with a small redacted sample.

## Troubleshooting

**`zsh: command not found: claude-session-doctor`**
The script isn't on your `PATH`. Either run it with a path prefix (`./claude-session-doctor`) or copy it to `~/.local/bin` and add that directory to your `PATH` — see [Option 3](#option-3-put-it-on-your-path).

**`No session file for id '...' under ~/.claude/projects`**
Check the ID and that your Claude projects directory matches the default. If your installation uses a different location, pass `--dir`. List candidates with `ls ~/.claude/projects/*/*.jsonl`.

**The targeted fix runs but the same error keeps coming back.**
The session has signature mismatches that targeted removal can't reach. Run again and press `n` for nuke — that removes all thinking blocks at once and is the most reliable cure.

**The tool repaired a session I didn't want repaired.**
Run `./claude-session-doctor --restore SESSION_ID`. The most recent backup is rolled in, and the current (post-repair) state is saved as a new backup so the restore is itself reversible.

**I want to see what would happen without committing.**
Use `--dry-run`. It works for interactive sessions, `--fix-all`, and `--restore`.

## Why this happens (brief technical background)

There are two interacting bugs in Claude Code's session persistence:

1. **Streaming interleaving.** During long sessions, chunks from parallel or rapidly sequential API responses can land adjacent in the JSONL. Claude Code reconstructs API messages by merging consecutive assistant lines, so the merged message ends up containing thinking blocks from two different responses — with two different signatures.

2. **Repair-time mutation.** Claude Code's `ensureToolResultPairing` repair logic, run before submission, can split merged messages, mutate `redacted_thinking` blocks (whose opaque payloads aren't fully persisted in JSONL), or reorder content blocks. The API validates thinking blocks byte-for-byte against their cryptographic signatures, so any mutation triggers a 400.

The result: the session file enters a state Claude Code itself can't recover, and the only recourse is direct repair of the file. For a deeper write-up of this analysis, see the [prior art](#prior-art).

## Contributing

Issues and pull requests welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, test instructions, and the bar for new detectors/fixers.

If you've hit a corruption pattern this tool doesn't catch, please open an issue with:
- A redacted sample of the JSONL section that broke
- Your Claude Code version (`claude --version`)
- The exact API error you saw

## Prior art

The root-cause analysis and the targeted-fix / nuke distinction were pioneered by [miteshashar/claude-code-thinking-blocks-fix](https://github.com/miteshashar/claude-code-thinking-blocks-fix). That tool focuses specifically on thinking-block corruption; `claude-session-doctor` extends the approach to a wider range of session-file issues (tool pairing, alternation, trailing noise, invalid JSON, duplicates, etc.), adds a recommendation engine to guide users away from destructive mistakes, and provides an interactive picker, dry-run mode, JSON output, and one-command restore.

## License

[MIT](LICENSE).
