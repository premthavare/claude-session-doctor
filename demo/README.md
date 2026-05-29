# Demo

The animated walkthrough shown in the project README. Two artefacts:

| File | What it is |
|---|---|
| [`demo.gif`](demo.gif) | The animated demo embedded in the README. This is what users watch — no tooling required. |
| [`generate.py`](generate.py) | Regenerates the demo deterministically from the current tool output. Re-run after any UX change so the demo stays in sync. |

## Regenerate after tool changes

The demo is built from real tool output, not hand-written. After any change that affects formatting, severity wording, recommendation text, or the menu, regenerate it:

```bash
# 1. produce a fresh recording from the current tool
python3 demo/generate.py        # writes demo/demo.cast

# 2. convert it to the GIF the README embeds
agg demo/demo.cast demo/demo.gif
```

`generate.py` sets up a throwaway broken session, runs the tool through six scenarios (`--list`, interactive diagnosis, `--fix-all --dry-run`, `--fix-all`, `--json`, `--restore --dry-run`), and writes a recording with deterministic timing and machine-agnostic paths. [`agg`](https://github.com/asciinema/agg) renders that recording to `demo.gif`.

> The intermediate `demo.cast` is gitignored — only `demo.gif` is committed.
