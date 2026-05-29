"""Tests for claude-session-doctor.

The script's filename has a hyphen, so we load it via importlib rather than
a regular import.
"""

import importlib.util
import json
import os
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "claude-session-doctor"
_spec = importlib.util.spec_from_loader("csd", SourceFileLoader("csd", str(SCRIPT)))
csd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(csd)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write_jsonl(lines):
    """Write a list of JSON-encoded strings (or raw strings) to a temp .jsonl
    file. Returns the path."""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for l in lines:
            f.write(l + "\n")
    return path


def _user(text):
    return json.dumps({"type": "user", "message": {"role": "user",
            "content": [{"type": "text", "text": text}]}})


def _assistant_text(msg_id, text):
    return json.dumps({"type": "assistant", "message": {"id": msg_id, "role": "assistant",
            "content": [{"type": "text", "text": text}]}})


def _assistant_thinking(msg_id, thinking, sig="sig"):
    return json.dumps({"type": "assistant", "message": {"id": msg_id, "role": "assistant",
            "content": [{"type": "thinking", "thinking": thinking, "signature": sig}]}})


def _assistant_tool_use(msg_id, tool_id, name="Bash"):
    return json.dumps({"type": "assistant", "message": {"id": msg_id, "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": {}}]}})


def _user_tool_result(tool_id, content="ok"):
    return json.dumps({"type": "user", "message": {"role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": content}]}})


def _kinds(issues):
    return sorted({i["kind"] for i in issues})


# ---------------------------------------------------------------------------
# Detector tests
# ---------------------------------------------------------------------------
class TestDetectors(unittest.TestCase):

    def test_clean_session_has_no_issues(self):
        path = _write_jsonl([
            _user("hi"),
            _assistant_text("m1", "hello"),
        ])
        issues = csd.diagnose(csd.load_records(path))
        self.assertEqual(issues, [])

    def test_invalid_json_is_critical(self):
        path = _write_jsonl([_user("hi"), "this is not json at all"])
        issues = csd.diagnose(csd.load_records(path))
        self.assertIn("invalid_json", _kinds(issues))
        self.assertEqual(
            next(i for i in issues if i["kind"] == "invalid_json")["severity"],
            "critical",
        )

    def test_interleaved_thinking_detected(self):
        path = _write_jsonl([
            _assistant_thinking("A", "host", sig="sigA"),
            _assistant_thinking("B", "intruder", sig="sigB"),  # different msg_id
            _assistant_text("A", "the answer"),
        ])
        issues = csd.diagnose(csd.load_records(path))
        self.assertIn("interleaved_thinking", _kinds(issues))

    def test_single_msg_id_run_is_not_flagged_as_interleaved(self):
        path = _write_jsonl([
            _assistant_thinking("A", "thinking", sig="sigA"),
            _assistant_text("A", "answer"),
        ])
        issues = csd.diagnose(csd.load_records(path))
        self.assertNotIn("interleaved_thinking", _kinds(issues))

    def test_orphan_tool_use_detected(self):
        path = _write_jsonl([_assistant_tool_use("m1", "tool_1")])
        issues = csd.diagnose(csd.load_records(path))
        self.assertIn("orphan_tool_use", _kinds(issues))

    def test_orphan_tool_result_detected(self):
        path = _write_jsonl([_user_tool_result("ghost_id")])
        issues = csd.diagnose(csd.load_records(path))
        self.assertIn("orphan_tool_result", _kinds(issues))

    def test_paired_tool_use_and_result_clean(self):
        path = _write_jsonl([
            _assistant_tool_use("m1", "tool_1"),
            _user_tool_result("tool_1"),
        ])
        issues = csd.diagnose(csd.load_records(path))
        self.assertNotIn("orphan_tool_use", _kinds(issues))
        self.assertNotIn("orphan_tool_result", _kinds(issues))

    def test_empty_assistant_detected(self):
        path = _write_jsonl([json.dumps({"type": "assistant", "message":
                {"id": "m1", "role": "assistant", "content": []}})])
        issues = csd.diagnose(csd.load_records(path))
        self.assertIn("empty_assistant", _kinds(issues))

    def test_trailing_api_error_detected(self):
        path = _write_jsonl([
            _user("hi"),
            _assistant_text("m1", "answer"),
            json.dumps({"type": "assistant", "message": {"id": "err", "role": "assistant",
                    "isApiErrorMessage": True,
                    "content": [{"type": "text", "text": "API Error: 400"}]}}),
            json.dumps({"type": "system", "content": "noise"}),
        ])
        issues = csd.diagnose(csd.load_records(path))
        self.assertIn("trailing_noise", _kinds(issues))


# ---------------------------------------------------------------------------
# Fixer tests
# ---------------------------------------------------------------------------
class TestFixers(unittest.TestCase):

    def test_nuke_strips_thinking_keeps_text_and_tools(self):
        path = _write_jsonl([
            json.dumps({"type": "assistant", "message": {"id": "m1", "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "reasoning", "signature": "s"},
                        {"type": "text", "text": "Hello"},
                    ]}}),
            _assistant_tool_use("m2", "tool_1"),
            _user_tool_result("tool_1"),
        ])
        records = csd.load_records(path)
        csd.fix_nuke_thinking(records)
        survivors = [r.out_obj() for r in records if not r.deleted]
        # thinking is gone
        for r in survivors:
            for b in csd.content_of(csd.Record(json.dumps(r), r)):
                self.assertNotIn(b.get("type"), csd.THINKING_TYPES)
        # text "Hello" still present
        flat = json.dumps(survivors)
        self.assertIn("Hello", flat)
        # tool_use and tool_result still present
        self.assertIn("tool_1", flat)

    def test_nuke_drops_messages_that_become_empty(self):
        path = _write_jsonl([
            _assistant_thinking("m1", "lone thinking"),  # only content is thinking
        ])
        records = csd.load_records(path)
        csd.fix_nuke_thinking(records)
        survivors = [r for r in records if not r.deleted]
        self.assertEqual(survivors, [])

    def test_interleaved_fix_removes_intruder_keeps_host_text(self):
        path = _write_jsonl([
            _assistant_thinking("A", "host", sig="sigA"),
            _assistant_thinking("B", "intruder", sig="sigB"),
            _assistant_text("A", "the answer"),
        ])
        records = csd.load_records(path)
        csd.fix_interleaved_thinking(records)
        survivors = [r.out_obj() for r in records if not r.deleted]
        flat = json.dumps(survivors)
        # both stray thinking-only lines (different msg_ids in a multi-id run) go
        self.assertNotIn("host", flat)
        self.assertNotIn("intruder", flat)
        # text answer survives
        self.assertIn("the answer", flat)

    def test_tool_pairing_inserts_synthetic_result(self):
        path = _write_jsonl([_assistant_tool_use("m1", "tool_orphan")])
        records = csd.load_records(path)
        csd.fix_tool_pairing(records)
        survivors = [r.out_obj() for r in records if not r.deleted]
        # tool_orphan is now paired
        result_found = any(
            isinstance(b, dict) and b.get("type") == "tool_result"
                and b.get("tool_use_id") == "tool_orphan"
            for r in survivors
            for b in (r.get("message", {}).get("content") or [])
        )
        self.assertTrue(result_found)

    def test_tool_pairing_removes_orphan_result(self):
        path = _write_jsonl([
            _user_tool_result("ghost_id"),
            _assistant_tool_use("m1", "tool_real"),
            _user_tool_result("tool_real"),
        ])
        records = csd.load_records(path)
        csd.fix_tool_pairing(records)
        survivors_flat = json.dumps(
            [r.out_obj() for r in records if not r.deleted])
        self.assertNotIn("ghost_id", survivors_flat)
        self.assertIn("tool_real", survivors_flat)

    def test_invalid_json_removed(self):
        path = _write_jsonl([_user("hi"), "garbage line"])
        records = csd.load_records(path)
        csd.fix_invalid_json(records)
        self.assertTrue(all(r.obj is not None for r in records if not r.deleted))

    def test_trailing_noise_trimmed(self):
        path = _write_jsonl([
            _user("hi"),
            _assistant_text("m1", "answer"),
            json.dumps({"type": "system", "content": "noise"}),
            json.dumps({"type": "system", "content": "more noise"}),
        ])
        records = csd.load_records(path)
        csd.fix_trailing_noise(records)
        survivors = [r.out_obj() for r in records if not r.deleted]
        # noise gone
        self.assertEqual(len(survivors), 2)
        self.assertEqual(csd.rtype(csd.Record("", survivors[-1])), "assistant")


# ---------------------------------------------------------------------------
# Idempotency and end-to-end
# ---------------------------------------------------------------------------
class TestIdempotencyAndEndToEnd(unittest.TestCase):

    def test_fixers_are_idempotent(self):
        path = _write_jsonl([
            _assistant_thinking("A", "host", sig="sigA"),
            _assistant_thinking("B", "intruder", sig="sigB"),
            _assistant_text("A", "the answer"),
        ])
        records = csd.load_records(path)
        csd.fix_interleaved_thinking(records)
        survivors_1 = [r.out_obj() for r in records if not r.deleted]
        csd.fix_interleaved_thinking(records)  # apply again
        survivors_2 = [r.out_obj() for r in records if not r.deleted]
        self.assertEqual(survivors_1, survivors_2)

    def test_end_to_end_dirty_to_clean(self):
        """All issue types in one file; all fixes applied; diagnosis comes back clean."""
        path = _write_jsonl([
            _user("hi"),
            _assistant_thinking("A", "host", sig="sigA"),
            _assistant_thinking("B", "intruder", sig="sigB"),
            _assistant_text("A", "answer"),
            _assistant_tool_use("C", "tool_orphan"),
            _user_tool_result("ghost"),
            json.dumps({"type": "assistant", "message":
                {"id": "empty", "role": "assistant", "content": []}}),
            "not json",
            json.dumps({"type": "assistant", "message":
                {"id": "err", "role": "assistant", "isApiErrorMessage": True,
                 "content": [{"type": "text", "text": "API Error: 400"}]}}),
            json.dumps({"type": "system", "content": "noise"}),
        ])
        records = csd.load_records(path)
        # apply every safe fix in the order the menu would
        csd.fix_invalid_json(records)
        csd.fix_interleaved_thinking(records)
        csd.fix_tool_pairing(records)
        csd.fix_empty_assistant(records)
        csd.fix_trailing_noise(records)
        csd.write_records(path, records)
        # re-load fresh, re-diagnose
        records2 = csd.load_records(path)
        issues = csd.diagnose(records2)
        self.assertEqual(issues, [], f"expected clean session, got: {issues}")
        # everything is valid JSON
        with open(path) as f:
            for line in f:
                json.loads(line)

    def test_write_records_is_atomic(self):
        """The written file is valid JSONL — no half-written lines."""
        path = _write_jsonl([_user("hi"), _assistant_text("m1", "hello")])
        records = csd.load_records(path)
        csd.write_records(path, records)
        with open(path) as f:
            for line in f:
                json.loads(line)


# ---------------------------------------------------------------------------
# v1.1: new detectors
# ---------------------------------------------------------------------------
class TestNewDetectors(unittest.TestCase):

    def test_alternation_violation_detected(self):
        path = _write_jsonl([_user("first"), _user("second with no assistant between")])
        issues = csd.diagnose(csd.load_records(path))
        kinds = sorted({i["kind"] for i in issues})
        self.assertIn("alternation_violation", kinds)

    def test_alternation_clean_when_alternating(self):
        path = _write_jsonl([
            _user("hi"), _assistant_text("m1", "hello"),
            _user("bye"), _assistant_text("m2", "ok"),
        ])
        issues = csd.diagnose(csd.load_records(path))
        self.assertNotIn("alternation_violation",
                {i["kind"] for i in issues})

    def test_oversized_message_detected(self):
        big = "x" * (300 * 1024)  # 300 KB > 200 KB threshold
        path = _write_jsonl([_assistant_text("m1", big)])
        issues = csd.diagnose(csd.load_records(path))
        self.assertIn("oversized_message",
                {i["kind"] for i in issues})

    def test_empty_tool_result_detected(self):
        path = _write_jsonl([
            _assistant_tool_use("m1", "tool_1"),
            json.dumps({"type": "user", "message": {"role": "user",
                    "content": [{"type": "tool_result",
                            "tool_use_id": "tool_1", "content": ""}]}}),
        ])
        issues = csd.diagnose(csd.load_records(path))
        self.assertIn("empty_tool_result",
                {i["kind"] for i in issues})

    def test_duplicate_consecutive_detected(self):
        text = "This is a sufficiently long assistant message to qualify for duplicate detection."
        path = _write_jsonl([
            _assistant_text("m1", text),
            _assistant_text("m2", text),
        ])
        issues = csd.diagnose(csd.load_records(path))
        self.assertIn("duplicate_consecutive",
                {i["kind"] for i in issues})

    def test_misordered_timestamps_detected(self):
        path = _write_jsonl([
            json.dumps({"type": "user", "timestamp": 1000.0, "message":
                    {"role": "user", "content": [{"type": "text", "text": "a"}]}}),
            json.dumps({"type": "assistant", "timestamp": 500.0, "message":
                    {"id": "m1", "role": "assistant",
                     "content": [{"type": "text", "text": "b"}]}}),
        ])
        issues = csd.diagnose(csd.load_records(path))
        self.assertIn("misordered_timestamps",
                {i["kind"] for i in issues})


# ---------------------------------------------------------------------------
# v1.1: new fixers
# ---------------------------------------------------------------------------
class TestNewFixers(unittest.TestCase):

    def test_alternation_fix_inserts_synthetic_assistant(self):
        path = _write_jsonl([_user("a"), _user("b")])
        records = csd.load_records(path)
        rep = csd.fix_alternation_violation(records)
        self.assertEqual(rep["added"], 1)
        # there should now be assistant between the two users
        roles = [csd.rtype(r) for r in records if not r.deleted]
        self.assertEqual(roles, ["user", "assistant", "user"])

    def test_duplicate_consecutive_fix_keeps_first(self):
        text = "This is a sufficiently long assistant message to qualify."
        path = _write_jsonl([
            _assistant_text("m1", text),
            _assistant_text("m2", text),
            _assistant_text("m3", text),
        ])
        records = csd.load_records(path)
        rep = csd.fix_duplicate_consecutive(records)
        self.assertEqual(rep["removed"], 2)
        survivors = [r for r in records if not r.deleted]
        self.assertEqual(len(survivors), 1)


# ---------------------------------------------------------------------------
# v1.1: recommendation engine
# ---------------------------------------------------------------------------
class TestRecommendation(unittest.TestCase):

    def test_clean_session_recommendation(self):
        level, label, _ = csd.recommend([])
        self.assertEqual(level, "clean")
        self.assertEqual(label, "OK")

    def test_critical_without_interleaved_advises_against_nuke(self):
        # mimics the user's real session: orphan tool_use + invalid JSON, no interleaved
        issues = [
            {"kind": "invalid_json", "severity": "critical",
             "summary": "x", "lines": [12896, 12899]},
            {"kind": "orphan_tool_use", "severity": "critical",
             "summary": "x", "lines": [12131]},
            {"kind": "trailing_noise", "severity": "warning",
             "summary": "x", "lines": []},
        ]
        level, label, msg = csd.recommend(issues)
        self.assertEqual(label, "FIX")
        self.assertIn("NOT advised", msg)

    def test_interleaved_thinking_recommends_safe_then_nuke(self):
        issues = [{"kind": "interleaved_thinking", "severity": "critical",
                "summary": "x", "lines": [1, 2]}]
        _, label, msg = csd.recommend(issues)
        self.assertEqual(label, "FIX")
        self.assertIn("safe fixes", msg)
        self.assertIn("nuke", msg)

    def test_only_info_recommends_no_repair(self):
        issues = [{"kind": "large_session", "severity": "info",
                "summary": "x", "lines": []}]
        level, label, _ = csd.recommend(issues)
        self.assertEqual(level, "info")


# ---------------------------------------------------------------------------
# v1.1: preview / dry-run
# ---------------------------------------------------------------------------
class TestPreviewAndDryRun(unittest.TestCase):

    def test_preview_does_not_mutate_originals(self):
        path = _write_jsonl([_user("hi"), "garbage", _assistant_text("m1", "hi")])
        records = csd.load_records(path)
        before = [r.deleted for r in records]
        reports = csd.preview_fixes(records, [("Remove invalid", csd.fix_invalid_json)])
        after = [r.deleted for r in records]
        self.assertEqual(before, after)  # originals untouched
        self.assertEqual(reports[0]["removed"], 1)  # but preview saw the work

    def test_format_totals(self):
        reports = [
            {"removed": 5, "added": 0, "modified": 0, "summary": ""},
            {"removed": 2, "added": 1, "modified": 0, "summary": ""},
        ]
        s = csd.format_totals(reports)
        self.assertIn("remove 7", s)
        self.assertIn("add 1", s)


# ---------------------------------------------------------------------------
# v1.1: restore + non-interactive CLI commands
# ---------------------------------------------------------------------------
class TestRestoreAndCommands(unittest.TestCase):

    def _make_project(self, lines):
        """Create a fake projects dir with one session. Returns (base, sid, path)."""
        base = tempfile.mkdtemp()
        proj = os.path.join(base, "proj")
        os.makedirs(proj)
        sid = "11111111-2222-3333-4444-555555555555"
        path = os.path.join(proj, sid + ".jsonl")
        with open(path, "w") as f:
            for l in lines:
                f.write(l + "\n")
        return base, sid, path

    def test_list_backups_sorts_newest_first(self):
        base, sid, path = self._make_project([_user("hi")])
        b1 = csd.backup(path); time.sleep(1.1)
        b2 = csd.backup(path)
        bks = csd.list_backups(path)
        self.assertEqual(bks[0], b2)
        self.assertEqual(bks[1], b1)

    def test_cmd_restore_overwrites_with_most_recent_backup(self):
        base, sid, path = self._make_project([_user("original content")])
        bk = csd.backup(path)
        # corrupt the live file
        with open(path, "w") as f:
            f.write("CORRUPTED\n")
        # restore (auto-confirm via monkeypatched input)
        orig_input = __builtins__.input if hasattr(__builtins__, "input") \
                else __builtins__["input"]
        try:
            import builtins
            builtins.input = lambda _: "y"
            rc = csd.cmd_restore(base, sid, dry_run=False)
        finally:
            import builtins
            builtins.input = orig_input
        self.assertEqual(rc, csd.EXIT_OK)
        with open(path) as f:
            content = f.read()
        self.assertIn("original content", content)
        self.assertNotIn("CORRUPTED", content)

    def test_cmd_restore_dry_run_does_not_write(self):
        base, sid, path = self._make_project([_user("original")])
        csd.backup(path)
        with open(path, "w") as f:
            f.write("CORRUPTED\n")
        rc = csd.cmd_restore(base, sid, dry_run=True)
        self.assertEqual(rc, csd.EXIT_OK)
        # live file still corrupted (dry-run wrote nothing)
        with open(path) as f:
            self.assertIn("CORRUPTED", f.read())

    def test_cmd_fix_all_clean_session_exits_zero(self):
        base, sid, path = self._make_project([_user("hi"), _assistant_text("m1", "hello")])
        rc = csd.cmd_fix_all(base, sid, dry_run=False, json_out=False)
        self.assertEqual(rc, csd.EXIT_OK)

    def test_cmd_fix_all_dry_run_does_not_write(self):
        base, sid, path = self._make_project([_user("hi"), "garbage"])
        with open(path) as f:
            before = f.read()
        rc = csd.cmd_fix_all(base, sid, dry_run=True, json_out=False)
        self.assertEqual(rc, csd.EXIT_OK)
        with open(path) as f:
            self.assertEqual(f.read(), before)

    def test_cmd_fix_all_repairs_and_returns_zero(self):
        base, sid, path = self._make_project([
            _user("hi"),
            _assistant_thinking("A", "host", sig="sigA"),
            _assistant_thinking("B", "intruder", sig="sigB"),
            _assistant_text("A", "answer"),
            "this is garbage json",
        ])
        rc = csd.cmd_fix_all(base, sid, dry_run=False, json_out=False)
        self.assertEqual(rc, csd.EXIT_OK)
        # file now diagnoses clean
        issues = csd.diagnose(csd.load_records(path))
        criticals = [i for i in issues if i["severity"] == "critical"]
        self.assertEqual(criticals, [])


if __name__ == "__main__":
    unittest.main()
