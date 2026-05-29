# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file Python CLI (`claude-session-doctor`, ~1200 lines, stdlib only, Python 3.8+) that diagnoses and repairs corrupted Claude Code session JSONL files under `~/.claude/projects/*/*.jsonl`. The single-file, dependency-free design is a hard product constraint: people whose sessions are bricked must be able to `curl` one file and run it anywhere Python exists. **Do not add runtime dependencies and do not split the script into a package.**

## Commands

```bash
# Run the full test suite (the only build/test step there is)
python3 -m unittest discover -s tests -v

# Run a single test case
python3 -m unittest tests.test_doctor.TestClassName.test_method -v

# Smoke-test the CLI (CI runs this too)
python3 claude-session-doctor --help

# Run against throwaway data — NEVER develop against your real ~/.claude
mkdir -p /tmp/cc-test/myproj
cp ~/.claude/projects/some/session.jsonl /tmp/cc-test/myproj/
./claude-session-doctor --dir /tmp/cc-test
```

CI (`.github/workflows/test.yml`) runs the unittest suite + `--help` smoke test across Python 3.8–3.12 on Ubuntu and macOS. There is no lint step; match existing style.

## Architecture

The script is organized into clearly commented sections in this order: terminal color, `Record` model, JSONL accessors, detectors, fixers, recommendation engine, session discovery/backup, apply/preview, output rendering, interactive flow, command handlers, `main()`.

**The `Record` model is the spine.** `load_records()` wraps every line — including blank and unparseable ones — in a `Record(raw, obj)`, where `obj` is `None` if the line didn't parse. Fixers never rewrite the file directly; they mutate records in place via three channels: `r.deleted = True`, `r.new_obj = {...}` (override), or replacing the whole list. `out_obj()` resolves `new_obj or obj`, and `write_records()` skips deleted/None records, writes to `<path>.tmp`, and `os.replace`s atomically. `deep_copy_records()` is what makes dry-run and preview possible — every fix can be simulated on an independent copy.

**Detectors and fixers are decoupled via registries.** A detector takes the record list and returns issue dicts `{kind, severity, summary, lines}`; all are listed in `DETECTORS` and run by `diagnose()`. A fixer takes the record list, mutates in place, and returns a `_report(removed, added, modified, summary)` dict; they're mapped by issue `kind` in the `FIXES` dict. `NUKE` (strip all thinking blocks) is separate and always available regardless of diagnosis. `ADVISORY_KINDS` are detected but have no auto-fix (reported only). Note multiple kinds can map to the same fixer (e.g. both `orphan_tool_use` and `orphan_tool_result` → `fix_tool_pairing`); `apply_fixes()` dedupes by function identity so selecting both runs it once.

**Fixers must be global, idempotent, and removal-first.** They scan the entire file rather than acting on the line numbers from a detector (robust to other fixes running first). Running any fixer twice equals running it once. **Prefer deletion over mutation**: thinking blocks are cryptographically signed and validated byte-for-byte by the API, so removing a corrupt block is always safe while rewriting one breaks the signature. This is why the interleaved-thinking fix removes intruder lines rather than merging, and why nuke strips blocks entirely.

**Severity drives the recommendation engine.** `recommend()` maps the set of issue kinds/severities to one of OK / ADVISE / FIX / TIDY plus guidance text. Its key safety job: when there are critical issues but NO `interleaved_thinking`, it explicitly advises *against* nuke (nuking would destroy all reasoning traces without fixing the real problem). Preserve this guardrail when editing.

## Conventions

- **Exit codes are part of the contract** (`EXIT_OK=0`, `EXIT_ISSUES_FOUND=1`, `EXIT_ISSUES_REMAIN=2`, `EXIT_INPUT_ERROR=3`). The `--json` and `--list` modes and scripts depend on them.
- **`--json` output schema is stable** (see README "JSON output schema"). Changing field names is a breaking change.
- **Backups before every write.** `backup()` writes `<id>.jsonl.<unix_ts>.backup`; `--restore` rolls back the newest and first backs up current state so restore is itself reversible.
- Tuning heuristics live as module constants: `LARGE_SESSION_LINES`, `LARGE_MESSAGE_BYTES`, `DUPLICATE_MIN_TEXT_LEN`.
- Color helpers (`red`, `green`, `bold`, …) auto-disable when not a TTY / under `NO_COLOR`; respect `FORCE_COLOR`.

## Adding a detector or fixer

1. Write the function following the contracts above.
2. Register it: detectors append to `DETECTORS`; fixers add to `FIXES` keyed by the issue `kind` (or `ADVISORY_KINDS` if report-only).
3. Add a test in `tests/test_doctor.py` — build a small synthetic JSONL for the case and assert detection/fix outcome. End-to-end "dirty → fix-all → clean" tests are especially valued.
4. Update the README detection table and `--help` text if user-visible behavior changes.

Severity guidance: `critical` = next API call will fail; `warning` = degraded but functional; `info` = advisory.
