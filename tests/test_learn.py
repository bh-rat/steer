import json

from steer.learn import (
    Learnings,
    LessonRejected,
    MAX_ACTIVE_LESSONS,
    reflect,
    scan_transcript,
)
from tests.helpers import SteerTestCase


class TestCapture(SteerTestCase):
    def test_note_and_get(self):
        with Learnings("t") as learn:
            result = learn.note("Use the EU endpoint for EU accounts",
                                kind="correction", context="EU accounts")
            self.assertEqual(result["action"], "added")
            lesson = learn.get(result["id"])
            self.assertEqual(lesson["kind"], "correction")
            self.assertEqual(lesson["confirmations"], 1)

    def test_duplicate_confirms_instead_of_duplicating(self):
        with Learnings("t") as learn:
            first = learn.note("Always run tests before committing.")
            second = learn.note("always run  tests before committing")
            self.assertEqual(second["action"], "confirmed")
            self.assertEqual(second["id"], first["id"])
            self.assertEqual(learn.get(first["id"])["confirmations"], 2)
            self.assertEqual(len(learn.lessons()), 1)

    def test_secret_shaped_lesson_rejected(self):
        with Learnings("t") as learn:
            for bad in ("the key is sk-abc123def456gh",
                        "set API_KEY=supersecret123",
                        "use AKIA0123456789AB for s3"):
                with self.assertRaises(LessonRejected):
                    learn.note(bad)

    def test_oversized_lesson_rejected(self):
        with Learnings("t") as learn:
            with self.assertRaises(LessonRejected):
                learn.note("x" * 600)

    def test_runs_and_stats(self):
        with Learnings("t") as learn:
            learn.record_run("ok")
            learn.record_run("ok")
            learn.record_run("failed", note="timeout")
            stats = learn.stats()
            self.assertEqual(stats["runs"]["total"], 3)
            self.assertAlmostEqual(stats["success_rate"], 2 / 3)


class TestCuration(SteerTestCase):
    def test_dispute_beyond_confirmations_archives(self):
        with Learnings("t") as learn:
            lesson_id = learn.note("Wrong lesson")["id"]
            learn.dispute(lesson_id)          # 1 vs 1 -> stays
            self.assertEqual(learn.get(lesson_id)["status"], "active")
            learn.dispute(lesson_id)          # 2 vs 1 -> archived
            self.assertEqual(learn.get(lesson_id)["status"], "archived")
            self.assertEqual(learn.lessons(), [])

    def test_confirm_revives_archived(self):
        with Learnings("t") as learn:
            lesson_id = learn.note("Borderline lesson")["id"]
            learn.dispute(lesson_id)
            learn.dispute(lesson_id)
            self.assertEqual(learn.get(lesson_id)["status"], "archived")
            learn.confirm(lesson_id)
            self.assertEqual(learn.get(lesson_id)["status"], "active")

    def test_pinned_sorts_first(self):
        with Learnings("t") as learn:
            learn.note("popular lesson")
            popular = learn.lessons()[0]["id"]
            for _ in range(5):
                learn.confirm(popular)
            pinned_id = learn.note("pinned lesson")["id"]
            learn.pin(pinned_id)
            ranked = learn.lessons()
            self.assertEqual(ranked[0]["id"], pinned_id)

    def test_cap_evicts_weakest(self):
        with Learnings("t") as learn:
            first = learn.note("lesson zero")["id"]
            learn.confirm(first)              # strongest
            for i in range(MAX_ACTIVE_LESSONS + 10):
                learn.note(f"lesson number {i}")
            active = learn.lessons(["active", "pinned"])
            self.assertLessEqual(len(active), MAX_ACTIVE_LESSONS)
            self.assertIn(first, [lesson["id"] for lesson in active])

    def test_forget(self):
        with Learnings("t") as learn:
            lesson_id = learn.note("temporary")["id"]
            learn.forget(lesson_id)
            self.assertEqual(learn.lessons(), [])
            everything = learn.lessons(["archived"])
            self.assertEqual(everything[0]["id"], lesson_id)


class TestDigestAndPromotion(SteerTestCase):
    def test_digest_empty(self):
        with Learnings("t") as learn:
            self.assertIn("no lessons recorded", learn.digest())

    def test_digest_bounded_and_ranked(self):
        with Learnings("t") as learn:
            for i in range(50):
                learn.note(f"lesson with some reasonable length number {i}")
            digest = learn.digest(budget=400)
            self.assertLessEqual(len(digest), 400 + 200)  # + footer lines
            self.assertIn("more: steer learn review", digest)
            self.assertIn("steer learn confirm", digest)

    def test_digest_marks_stale_version(self):
        with Learnings("t") as learn:
            learn.note("old lesson", skill_version="0.1.0")
            digest = learn.digest(current_version="0.2.0")
            self.assertIn("[from v0.1.0]", digest)

    def test_promote_writes_learnings_md(self):
        skill_dir = self.make_skill("promotable-skill")
        with Learnings("promotable-skill") as learn:
            lesson_id = learn.note("Use bulk endpoints over per-item calls",
                                   context="more than 50 items")["id"]
            path = learn.promote(lesson_id, skill_dir)
            content = path.read_text()
            self.assertIn("Use bulk endpoints", content)
            self.assertIn("when: more than 50 items", content)
            self.assertIn(f"steer:lesson {lesson_id}", content)
            self.assertEqual(learn.get(lesson_id)["status"], "promoted")
            self.assertNotIn(lesson_id, [lesson["id"] for lesson in learn.lessons()])

    def test_promote_requires_skill_dir(self):
        with Learnings("t") as learn:
            lesson_id = learn.note("anything")["id"]
            with self.assertRaises(FileNotFoundError):
                learn.promote(lesson_id, self.root / "not-a-skill")

    def test_lessons_live_outside_skill_dir(self):
        with Learnings("t") as learn:
            learn.note("must not ship with the skill")
            self.assertTrue(str(learn.path).startswith(str(self.home)))


class TestMirror(SteerTestCase):
    def test_mirror_created_and_updated(self):
        with Learnings("t") as learn:
            learn.note("Use bulk endpoints", kind="preference")
            mirror = learn.mirror_path()
            self.assertTrue(mirror.exists())
            content = mirror.read_text()
            self.assertIn("# Learnings: t", content)
            self.assertIn("Use bulk endpoints", content)
            self.assertIn("auto-generated by steer learn", content)
            lesson_id = learn.lessons()[0]["id"]
            learn.forget(lesson_id)
            content = mirror.read_text()
            self.assertIn("Recently archived", content)

    def test_mirror_lives_next_to_db(self):
        with Learnings("t") as learn:
            learn.note("anything at all")
            self.assertEqual(learn.mirror_path().parent, learn.path.parent)
            self.assertTrue(str(learn.mirror_path()).startswith(str(self.home)))


def _transcript_line(role, text):
    return json.dumps({"message": {"role": role,
                                   "content": [{"type": "text", "text": text}]}})


class TestReflect(SteerTestCase):
    def _write_transcript(self, *lines):
        path = self.root / "transcript.jsonl"
        path.write_text("\n".join(lines) + "\n")
        return str(path)

    def test_scan_detects_corrections_failures_capture(self):
        path = self._write_transcript(
            _transcript_line("user", "build the report"),
            _transcript_line("assistant", "done"),
            _transcript_line("user", "No, that's wrong - use the EU endpoint"),
            json.dumps({"type": "tool_result", "is_error": True,
                        "content": "boom"}),
            _transcript_line("assistant", "ran steer learn note \"x\""),
        )
        scan = scan_transcript(path)
        self.assertEqual(scan["corrections"], 1)
        self.assertEqual(scan["failures"], 1)
        self.assertTrue(scan["captured"])

    def test_reflect_blocks_once_with_instructions(self):
        path = self._write_transcript(
            _transcript_line("user", "no, use uv not pip"),
        )
        decision = reflect({"transcript_path": path,
                            "stop_hook_active": False}, "t")
        self.assertEqual(decision["decision"], "block")
        self.assertIn("steer learn note", decision["reason"])
        self.assertIn("--skill t", decision["reason"])

    def test_reflect_honors_stop_hook_active(self):
        path = self._write_transcript(_transcript_line("user", "no, wrong."))
        self.assertIsNone(reflect({"transcript_path": path,
                                   "stop_hook_active": True}, "t"))

    def test_reflect_quiet_when_no_signals(self):
        path = self._write_transcript(
            _transcript_line("user", "please generate the report"),
            _transcript_line("assistant", "done"),
        )
        self.assertIsNone(reflect({"transcript_path": path,
                                   "stop_hook_active": False}, "t"))

    def test_reflect_quiet_when_already_captured(self):
        path = self._write_transcript(
            _transcript_line("user", "no, wrong approach"),
            _transcript_line("assistant",
                             'Bash: steer learn note "use Y" --skill t'),
        )
        self.assertIsNone(reflect({"transcript_path": path,
                                   "stop_hook_active": False}, "t"))

    def test_reflect_quiet_on_missing_transcript(self):
        self.assertIsNone(reflect({"transcript_path": "/nope/missing.jsonl",
                                   "stop_hook_active": False}, "t"))


class TestLearnCLI(SteerTestCase):
    def _run(self, *argv):
        import contextlib
        import io

        from steer.cli import main

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_note_show_confirm_cycle(self):
        code, out, _ = self._run("learn", "note", "Prefer rg over grep",
                                 "--kind", "preference", "--skill", "t")
        self.assertEqual(code, 0)
        code, out, _ = self._run("learn", "show", "--skill", "t")
        self.assertEqual(code, 0)
        self.assertIn("Prefer rg over grep", out)
        code, out, _ = self._run("learn", "confirm", "1", "--skill", "t")
        self.assertEqual(code, 0)
        self.assertIn("+2", out)

    def test_review_json(self):
        import json

        self._run("learn", "note", "a lesson", "--skill", "t")
        code, out, _ = self._run("learn", "review", "--skill", "t", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)), 1)

    def test_secret_note_rejected_via_cli(self):
        code, _, err = self._run("learn", "note", "token=ghp_" + "a" * 24,
                                 "--skill", "t")
        self.assertEqual(code, 1)
        self.assertIn("steer secrets", err)

    def test_scaffold_with_learn_validates_clean(self):
        from steer.create import create_skill
        from steer.validate import has_errors, validate_skill

        create_skill(
            "learning-skill", parent_dir=str(self.root),
            description="Does learning things with data. Use when the user "
                        "wants learning things.",
            components=["learn"],
        )
        skill_dir = self.root / "learning-skill"
        findings = validate_skill(skill_dir)
        self.assertFalse(has_errors(findings), findings)
        content = (skill_dir / "SKILL.md").read_text()
        self.assertIn("steer learn show", content)
        self.assertIn("steer learn note", content)
        self.assertIn("steer learn run ok", content)

    def test_promote_via_cli_with_dir(self):
        skill_dir = self.make_skill("cli-promote")
        self._run("learn", "note", "promoted via cli", "--skill", "cli-promote")
        code, out, _ = self._run("learn", "promote", "1",
                                 "--skill", "cli-promote",
                                 "--dir", str(skill_dir))
        self.assertEqual(code, 0, out)
        self.assertTrue((skill_dir / "learnings.md").exists())

    def test_reflect_via_cli_with_transcript_flag(self):
        path = self.root / "tr.jsonl"
        path.write_text(_transcript_line("user", "no, that's wrong") + "\n")
        code, out, _ = self._run("learn", "reflect", "--skill", "t",
                                 "--transcript", str(path))
        self.assertEqual(code, 0)
        decision = json.loads(out)
        self.assertEqual(decision["decision"], "block")

    def test_auto_learn_scaffold_round_trips(self):
        from steer.create import create_skill
        from steer.skill import Skill
        from steer.validate import has_errors, validate_skill

        create_skill(
            "auto-skill", parent_dir=str(self.root),
            description="Does auto things with data. Use when the user "
                        "wants auto things.",
            auto_learn=True,
        )
        skill_dir = self.root / "auto-skill"
        skill = Skill.load(skill_dir)
        self.assertEqual(skill.problems, [])
        hook = skill.frontmatter["hooks"]["Stop"][0]["hooks"][0]
        self.assertEqual(hook["command"],
                         "steer learn reflect --skill auto-skill")
        self.assertEqual(hook["timeout"], 15)
        findings = validate_skill(skill_dir)
        self.assertFalse(has_errors(findings), findings)
        codes = {f.code for f in findings}
        self.assertIn("PORTABILITY", codes)  # hooks is Claude-Code-only
        content = (skill_dir / "SKILL.md").read_text()
        self.assertIn("Auto-learning is on", content)

    def test_validate_flags_long_unreferenced_learnings(self):
        skill_dir = self.make_skill("long-learn")
        (skill_dir / "learnings.md").write_text(
            "# Learnings\n" + "- a lesson\n" * 200
        )
        code, out, _ = self._run("validate", str(skill_dir))
        self.assertEqual(code, 0)  # warnings, not errors
        self.assertIn("LEARNINGS_LONG", out)
        self.assertIn("LEARNINGS_UNREFERENCED", out)


class TestEvidenceHygiene(SteerTestCase):
    def test_credential_in_evidence_rejected(self):
        with Learnings("t") as learn:
            with self.assertRaises(LessonRejected):
                learn.note("Use the EU endpoint",
                           evidence="Authorization: Bearer sk-abc123456789")
