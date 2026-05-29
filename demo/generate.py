#!/usr/bin/env python3
"""
Demo generator for claude-session-doctor.

Sets up a synthetic broken session, runs the tool through its main flows,
and writes three artefacts:

    demo/demo.cast       asciinema v2 cast file (colour, replayable)
    demo/demo.txt        plain-text capture (for paste into the README)

Re-run after any UX change so the demo stays in sync with the tool:

    python3 demo/generate.py
"""
import json
import os
import shutil
import subprocess
import tempfile
import time

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(HERE)
TOOL = os.path.join(REPO, "claude-session-doctor")

# Pacing knobs ---------------------------------------------------------------
PROMPT_DELAY = 0.6        # pause before each new prompt
TYPING_SPEED = 0.04       # seconds between typed characters
COMMAND_PAUSE = 0.4       # pause after pressing enter
OUTPUT_DELAY = 0.15       # pause before output appears
SECTION_PAUSE = 1.2       # longer pause between scenarios

PROMPT = "\x1b[1;32m$\x1b[0m "  # bold green "$ "

# ---------------------------------------------------------------------------
# Cast file event recorder
# ---------------------------------------------------------------------------
class Cast:
    def __init__(self, width=100, height=30):
        self.width = width
        self.height = height
        self.events = []
        self.t = 0.0

    def wait(self, seconds):
        self.t += seconds

    def emit(self, text):
        # asciinema player emulates a TTY; bare \n moves down without
        # returning to col 0. Normalise any \n not already preceded by \r.
        import re
        text = re.sub(r"(?<!\r)\n", "\r\n", text)
        self.events.append([round(self.t, 3), "o", text])

    def typed(self, command, delay=TYPING_SPEED):
        for ch in command:
            self.wait(delay)
            self.emit(ch)

    def prompt(self):
        self.wait(PROMPT_DELAY)
        self.emit(PROMPT)

    def run_visible(self, command, output, extra_pause=0.0):
        """Show a prompt, type the command, press enter, print output."""
        self.prompt()
        self.typed(command)
        self.wait(COMMAND_PAUSE)
        self.emit("\r\n")
        self.wait(OUTPUT_DELAY)
        # Asciinema renders \n; sources we capture already use \n
        self.emit(output if output.endswith("\n") else output + "\n")
        if extra_pause:
            self.wait(extra_pause)

    def write(self, path):
        header = {
            "version": 2,
            "width": self.width,
            "height": self.height,
            "timestamp": int(time.time()),
            "env": {"SHELL": "/bin/zsh", "TERM": "xterm-256color"},
            "title": "claude-session-doctor demo",
        }
        with open(path, "w") as f:
            f.write(json.dumps(header) + "\n")
            for ev in self.events:
                f.write(json.dumps(ev) + "\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def run(cmd, **kw):
    """Run the tool under FORCE_COLOR so the cast captures ANSI colour."""
    env = os.environ.copy()
    env["FORCE_COLOR"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.run(cmd, env=env, capture_output=True, text=True, **kw)


def make_broken_session():
    """Build a fake projects dir that mimics a real user's bricked session."""
    base = tempfile.mkdtemp(prefix="csd-demo-")
    proj = os.path.join(base, ".claude", "projects", "my-app")
    os.makedirs(proj)
    sid = "abaca37e-792e-4168-94f7-0c6a6ef24aa7"
    path = os.path.join(proj, sid + ".jsonl")
    # Recreate a realistic mix of problems
    lines = [
        '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"refactor the auth module"}]}}',
        '{"type":"assistant","message":{"id":"m1","role":"assistant","content":[{"type":"text","text":"On it. Reading the current implementation now."}]}}',
        '{"type":"assistant","message":{"id":"m2","role":"assistant","content":[{"type":"tool_use","id":"toolu_lost","name":"Read","input":{"file_path":"src/auth.py"}}]}}',
        '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"also check the tests folder"}]}}',
        'this is not valid json',
        '{"type":"assistant","message":{"id":"err","role":"assistant","isApiErrorMessage":true,"content":[{"type":"text","text":"API Error: 400 messages.4.content.0: tool_use without tool_result"}]}}',
        '{"type":"system","content":"reconnecting…"}',
    ]
    with open(path, "w") as f:
        for line in lines:
            f.write(line + "\n")
    return base, sid


# ---------------------------------------------------------------------------
# Build the scenario
# ---------------------------------------------------------------------------
def main():
    base, sid = make_broken_session()
    proj_dir = os.path.join(base, ".claude", "projects")

    cast = Cast()
    transcript = []

    # The tool prints absolute session paths; `base` is a random tempdir that
    # would otherwise bake a machine-specific path into the cast and churn the
    # diff on every regen. Normalise it to a stable, generic placeholder.
    def clean(output):
        return output.replace(base, "/Users/you")

    def show(command, output, extra_pause=0.0):
        output = clean(output)
        cast.run_visible(command, output, extra_pause=extra_pause)
        transcript.append((command, output))

    def banner(text):
        msg = f"\x1b[1;36m# {text}\x1b[0m\r\n"
        cast.prompt()
        cast.emit(msg)
        cast.wait(SECTION_PAUSE)
        transcript.append((None, f"# {text}"))

    # ----- Scenario 1: triage with --list -----
    banner("triage all sessions at a glance")
    r = run([TOOL, "--dir", proj_dir, "--list"])
    show("claude-session-doctor --list", r.stdout, extra_pause=SECTION_PAUSE)

    # ----- Scenario 2: interactive diagnosis (just diagnosis + recommendation) -----
    banner("diagnose the broken session and read the recommendation")
    r = run([TOOL, "--dir", proj_dir, sid], input="q\n")
    # Only show through the recommendation box + menu; trim post-interaction
    out = r.stdout
    cut = out.find("What would you like to fix?")
    if cut != -1:
        out = out[:cut + len("What would you like to fix? ")] + "\r\n"
    show(f"claude-session-doctor {sid}", out, extra_pause=SECTION_PAUSE)

    # ----- Scenario 3: dry-run shows concrete preview -----
    banner("dry-run shows the concrete effect before any write")
    r = run([TOOL, "--dir", proj_dir, "--fix-all", sid, "--dry-run"])
    show(f"claude-session-doctor --fix-all {sid[:8]}… --dry-run",
         r.stdout, extra_pause=SECTION_PAUSE)

    # ----- Scenario 4: actually fix it -----
    banner("apply all safe fixes for real")
    r = run([TOOL, "--dir", proj_dir, "--fix-all", sid])
    show(f"claude-session-doctor --fix-all {sid[:8]}…",
         r.stdout, extra_pause=SECTION_PAUSE)

    # ----- Scenario 5: machine-readable JSON for monitoring -----
    banner("--json for monitoring scripts (post-fix)")
    r = run([TOOL, "--dir", proj_dir, "--json", sid])
    # truncate to the recommendation field to keep the cast tight
    parsed = json.loads(r.stdout)
    summary = {
        "session": parsed["sessions"][0]["id"][:12] + "…",
        "issues": len(parsed["sessions"][0]["issues"]),
        "recommendation": parsed["sessions"][0]["recommendation"]["label"],
    }
    pretty = json.dumps(summary, indent=2)
    show(f"claude-session-doctor --json {sid[:8]}… | jq '...'",
         pretty, extra_pause=SECTION_PAUSE)

    # ----- Scenario 6: restore (just the plan, in --dry-run) -----
    banner("restore is one command (--dry-run shown)")
    r = run([TOOL, "--dir", proj_dir, "--restore", sid, "--dry-run"])
    show(f"claude-session-doctor --restore {sid[:8]}… --dry-run",
         r.stdout, extra_pause=SECTION_PAUSE)

    # Final prompt to close on a clean line
    cast.prompt()

    cast_path = os.path.join(HERE, "demo.cast")
    cast.write(cast_path)
    print(f"wrote {cast_path}  ({len(cast.events)} events, "
          f"{cast.t:.1f}s playback)")

    txt_path = os.path.join(HERE, "demo.txt")
    with open(txt_path, "w") as f:
        for cmd, out in transcript:
            if cmd is None:
                f.write("\n" + out + "\n" + "─" * 60 + "\n")
            else:
                f.write(f"\n$ {cmd}\n{out}")
    print(f"wrote {txt_path}")

    # Cleanup
    shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
