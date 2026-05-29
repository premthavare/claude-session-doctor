# Demo

This directory contains a self-contained walkthrough of `claude-session-doctor`. Three artefacts:

| File | What it is |
|---|---|
| [`demo.cast`](demo.cast) | Pre-recorded asciinema v2 cast file. Play offline with `asciinema play demo.cast`, or upload to <https://asciinema.org> for an embeddable player. |
| [`demo.sh`](demo.sh) | Runnable shell script. Sets up a throwaway project tree containing a broken session, walks the tool through its main features, and cleans up. Safe to run anywhere — no real Claude data is touched. |
| [`generate.py`](generate.py) | Regenerates `demo.cast` and `demo.txt` deterministically from the current state of the tool. Re-run after any UX change so the demo stays in sync. |

## Watch it

Locally, without any account:

```bash
pip install asciinema   # or: pipx install asciinema
asciinema play demo/demo.cast
```

To get a shareable URL with an embedded player:

```bash
asciinema upload demo/demo.cast
```

That returns a `https://asciinema.org/a/<id>` link. The matching SVG badge for the README is `https://asciinema.org/a/<id>.svg`.

## Record your own

If you want a fresh recording — perhaps after customising the demo script:

```bash
asciinema rec demo/demo.cast -c demo/demo.sh
```

The `-c` flag runs the script inside the recording. When the script finishes, recording stops.

## Regenerate after tool changes

`demo.cast` and `demo.txt` are built from real tool output, not hand-written. After any change that affects formatting, severity wording, recommendation text, or the menu, re-run:

```bash
python3 demo/generate.py
```

This sets up the same broken session, runs the tool through six scenarios (`--list`, interactive diagnosis, `--fix-all --dry-run`, `--fix-all`, `--json`, `--restore --dry-run`), and writes a new cast file with deterministic timing.
