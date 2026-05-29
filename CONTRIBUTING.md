# Contributing

Thanks for considering a contribution. This is a small project, so the bar is mostly *make the tool safer and more useful for people whose sessions are broken*.

## Development setup

No dependencies. Clone, run, test:

```bash
git clone https://github.com/YOUR_USERNAME/claude-session-doctor.git
cd claude-session-doctor
python3 -m unittest discover -s tests -v
```

Python 3.8+ standard library only, please. Adding a runtime dependency would defeat the point of a recovery tool that has to run wherever Python does.

## Running the tool locally

Use a throwaway sessions directory rather than your real one:

```bash
mkdir -p /tmp/cc-test/myproj
cp ~/.claude/projects/some/session.jsonl /tmp/cc-test/myproj/
./claude-session-doctor --dir /tmp/cc-test
```

## Adding a detector

A detector is a function that takes the record list and returns a list of issue dicts:

```python
def detect_my_problem(records):
    bad = [i + 1 for i, r in enumerate(records) if my_check(r)]
    if not bad:
        return []
    return [{
        "kind": "my_problem",
        "severity": "warning",       # or "critical" / "info"
        "summary": f"{len(bad)} ...",
        "lines": bad,
    }]
```

Register it by appending to the `DETECTORS` list. Severity guidance: `critical` if the session will fail the next API call, `warning` if it's degraded but functional, `info` for advisories.

## Adding a fixer

A fixer takes the records list, mutates in place (`r.deleted = True`, `r.new_obj = {...}`, or replaces the list entirely), and returns a short human-readable report string. Fixers must be:

- **Global.** They scan the whole file rather than operating on indices passed in from a detector. That makes them robust to other fixes running first.
- **Idempotent.** Running the same fixer twice produces the same result as once.
- **Safety-first.** Prefer removal over mutation. Removing a corrupt block can never invalidate a cryptographic signature; rewriting one can.

Register the fixer in the `FIXES` dict, keyed by the issue `kind` it addresses.

## Testing changes

Every new detector or fixer should ship with tests. The pattern is in `tests/test_doctor.py`: write a small synthetic JSONL covering the case, run the detector or fixer, assert the outcome. End-to-end "dirty → fix all → clean" tests are particularly valuable.

Run the full suite before opening a PR:

```bash
python3 -m unittest discover -s tests -v
```

## Filing issues

The most useful issue includes:

- A redacted sample of the JSONL section that broke (minimal — a few surrounding lines are enough).
- Your Claude Code version (`claude --version`).
- The full API error message you saw.
- Your OS and Python version (`python3 --version`).

Please don't paste real session files containing private code or secrets. Redacted examples reproducing the structural pattern are what we need.

## Pull request bar

- Tests for any new detector or fixer.
- Docstring or inline comment explaining the corruption pattern you're addressing.
- README updated if the new fix changes the user-visible behaviour (the detection table, the help text, or the safety story).
- No new runtime dependencies.

Small PRs land faster than big ones. If you're planning a large change, open an issue first to discuss the approach.
