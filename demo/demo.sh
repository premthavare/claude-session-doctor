#!/usr/bin/env bash
#
# Runnable demo of claude-session-doctor.
#
# Sets up a temporary fake project tree containing a deliberately broken
# session, then walks through the tool's main features. Safe to run -- it
# only touches the temp directory it creates and cleans up at the end.
#
# To record an asciinema cast yourself:
#   asciinema rec demo.cast -c demo/demo.sh
#
# Note: we deliberately do NOT use `set -e` here. claude-session-doctor uses
# meaningful exit codes (0 clean, 1 issues found, 2 issues remain after fix,
# 3 input error) and several scenarios below intentionally trigger non-zero
# exits as part of the demo.
set -uo pipefail

# Resolve the tool location relative to this script.
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TOOL="${HERE}/../claude-session-doctor"
if [[ ! -x "$TOOL" ]]; then
    echo "Tool not found at $TOOL" >&2
    exit 1
fi

# Set up a throwaway project tree with a broken session.
BASE=$(mktemp -d -t csd-demo-XXXXXX)
trap "rm -rf '$BASE'" EXIT
PROJ="$BASE/.claude/projects/my-app"
SID="abaca37e-792e-4168-94f7-0c6a6ef24aa7"
SESSION="$PROJ/$SID.jsonl"
mkdir -p "$PROJ"
cat > "$SESSION" << 'EOF'
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"refactor the auth module"}]}}
{"type":"assistant","message":{"id":"m1","role":"assistant","content":[{"type":"text","text":"On it. Reading the current implementation now."}]}}
{"type":"assistant","message":{"id":"m2","role":"assistant","content":[{"type":"tool_use","id":"toolu_lost","name":"Read","input":{"file_path":"src/auth.py"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"also check the tests folder"}]}}
this is not valid json
{"type":"assistant","message":{"id":"err","role":"assistant","isApiErrorMessage":true,"content":[{"type":"text","text":"API Error: 400 messages.4.content.0: tool_use without tool_result"}]}}
{"type":"system","content":"reconnecting…"}
EOF

# Convenience wrapper so commands look short in the recording.
csd() {
    "$TOOL" --dir "$BASE/.claude/projects" "$@"
}

banner() {
    echo
    printf "\033[1;36m# %s\033[0m\n" "$1"
    echo "────────────────────────────────────────────────────────────"
    sleep 1
}

banner "triage all sessions at a glance"
echo "$ claude-session-doctor --list"
csd --list
sleep 2

banner "diagnose the broken session"
echo "$ claude-session-doctor $SID"
echo q | csd "$SID"
sleep 2

banner "dry-run shows the concrete effect before any write"
echo "$ claude-session-doctor --fix-all $SID --dry-run"
csd --fix-all "$SID" --dry-run
sleep 2

banner "apply all safe fixes for real"
echo "$ claude-session-doctor --fix-all $SID"
csd --fix-all "$SID"
sleep 2

banner "--json for monitoring scripts"
echo "$ claude-session-doctor --json $SID"
csd --json "$SID"
sleep 2

banner "restore is one command (showing --dry-run)"
echo "$ claude-session-doctor --restore $SID --dry-run"
csd --restore "$SID" --dry-run
sleep 1

echo
echo "Demo complete. The temporary project tree at $BASE is cleaned up on exit."
