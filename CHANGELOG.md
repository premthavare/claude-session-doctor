# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-05-29

### Added
- **`pyproject.toml`** for `pipx install` and `pip install`. The single-file script is shipped as-is via setuptools `script-files`, preserving the no-dependency, drop-in-PATH model.
- **Demo directory** ([`demo/`](demo/)) with three artefacts:
  - `demo.cast` — a pre-recorded asciinema v2 walkthrough.
  - `demo.sh` — a runnable shell script that sets up a throwaway broken session and walks the tool through six scenarios.
  - `generate.py` — regenerates the cast deterministically from real tool output, so the demo stays in sync.
- **`FORCE_COLOR=1`** environment variable to force ANSI colour output even when stdout isn't a TTY (used by the demo generator; also useful in containers, CI logs, and tools that pipe through `less -R`).
- **Recommendation engine.** A prominent recommendation box above the fix menu summarises the diagnosis and tells you which path to take. Explicitly guards against nuking when no thinking-block corruption is present.
- **Preview before confirm.** When fixes are selected, the tool computes the effect on a deep copy and reports concrete change counts (`Net change: remove N line(s), add M synthetic line(s)`) before asking you to confirm. The originals are untouched until you say yes.
- **`--dry-run`** modifier. Works with the interactive flow, `--fix-all`, and `--restore`. Computes and reports the effect without writing.
- **`--restore SESSION_ID`** command. Roll back to the most recent backup with one command. The current (pre-restore) state is itself backed up first, so a restore is reversible.
- **`--fix-all SESSION_ID`** non-interactive command. Apply every safe fix without prompts. Suitable for scripting and cron. Exits 0 on success, 2 if issues remain.
- **`--json`** machine-readable diagnosis output. Stable schema with `sessions[].issues[]` and `sessions[].recommendation`. Exits 1 if any critical issue is found, 0 otherwise.
- **Four new detectors:**
  - `alternation_violation` (critical, fixable): two consecutive `user` records with no assistant turn between them. The fix inserts a synthetic assistant turn.
  - `oversized_message` (warning, advisory): a single message larger than 200 KB.
  - `empty_tool_result` (warning, advisory): `tool_result` block with null/empty content.
  - `duplicate_consecutive` (warning, fixable): same assistant text in two consecutive turns (≥50 chars). The fix keeps the first and drops the rest.
  - `misordered_timestamps` (info, advisory): a record's timestamp is earlier than the previous one.
- **Defined exit codes:** 0 (clean / success), 1 (issues detected in diagnosis-only mode), 2 (fix applied but issues remain), 3 (user / input error).
- Collision-safe backup filenames: if two backups would land in the same wall-clock second, a counter suffix is appended (`<id>.jsonl.1234-1.backup`).

### Changed
- Fixers now return structured reports (`{removed, added, modified, summary}`) instead of plain strings, enabling preview totals.
- Backup ordering is computed from the timestamp embedded in the filename rather than mtime, since `shutil.copy2` preserves the source's mtime.

## [1.0.0] - 2026-05-28

### Added
- Initial public release.
- Session discovery under `~/.claude/projects/*/*.jsonl` with mtime-sorted listing.
- Six detectors: interleaved thinking blocks, orphan `tool_use`, orphan `tool_result`, invalid JSON lines, empty assistant messages, trailing API-error / noise. Plus an informational oversized-session warning.
- Five targeted fixers + a nuclear strip-all-thinking option, each global and idempotent.
- Interactive picker with `a` (all safe fixes), `n` (nuke), comma-separated number selection, and re-diagnosis after each apply.
- Automatic timestamped backups before any write.
- Atomic writes via temp file + rename.
- `--list` non-interactive mode for scripting and dashboards.
- `--dir` flag for custom projects directories.
- Direct-session shortcut: `claude-session-doctor SESSION_ID`.
- ANSI colour output, auto-disabled when not a TTY or when `NO_COLOR` is set.
