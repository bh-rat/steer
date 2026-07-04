from steer.validate import has_errors, validate_skill
from tests.helpers import SteerTestCase


def codes(findings, level=None):
    return {f.code for f in findings if level is None or f.level == level}


class TestValidate(SteerTestCase):
    def test_clean_skill(self):
        path = self.write(
            "good-skill/SKILL.md",
            "---\n"
            "name: good-skill\n"
            "description: Formats CSV files into reports. Use when the user "
            "asks for a CSV report.\n"
            "metadata:\n  version: \"0.1.0\"\n"
            "---\n\nDo the thing carefully.\n",
        ).parent
        findings = validate_skill(path)
        self.assertFalse(has_errors(findings), findings)

    def test_missing_skill_md(self):
        (self.root / "empty-dir").mkdir()
        findings = validate_skill(self.root / "empty-dir")
        self.assertIn("SKILL_MISSING", codes(findings, "error"))

    def test_name_rules(self):
        path = self.write(
            "BadName/SKILL.md",
            "---\nname: Bad--Name\ndescription: x\n---\nbody\n",
        ).parent
        errs = codes(validate_skill(path), "error")
        self.assertIn("NAME_INVALID", errs)
        self.assertIn("NAME_DIR_MISMATCH", errs)

    def test_name_reserved_warned(self):
        path = self.make_skill("claude-helper")
        self.assertIn("NAME_RESERVED", codes(validate_skill(path), "warning"))

    def test_description_limits(self):
        path = self.write(
            "long-desc/SKILL.md",
            f"---\nname: long-desc\ndescription: {'x' * 1100}\n---\nbody\n",
        ).parent
        self.assertIn("DESC_TOO_LONG", codes(validate_skill(path), "error"))

    def test_thin_description(self):
        path = self.make_skill("thin-skill", description="Does stuff.")
        self.assertIn("DESC_THIN", codes(validate_skill(path), "warning"))

    def test_body_budget(self):
        path = self.make_skill("long-body", body="line\n" * 600)
        self.assertIn("BODY_LONG", codes(validate_skill(path), "warning"))

    def test_broken_link_is_error(self):
        path = self.make_skill(
            "link-skill", body="See [the guide](references/guide.md).\n"
        )
        self.assertIn("LINK_BROKEN", codes(validate_skill(path), "error"))

    def test_existing_link_ok(self):
        path = self.make_skill(
            "link-ok", body="See [the guide](references/guide.md).\n"
        )
        self.write("link-ok/references/guide.md", "guide\n")
        self.assertNotIn("LINK_BROKEN", codes(validate_skill(path)))

    def test_portability_warning(self):
        path = self.write(
            "cc-only/SKILL.md",
            "---\nname: cc-only\ndescription: Does helpful things with files. "
            "Use when the user asks.\ncontext: fork\n---\nbody\n",
        ).parent
        self.assertIn("PORTABILITY", codes(validate_skill(path), "warning"))

    def test_unknown_field_warning(self):
        path = self.write(
            "custom-field/SKILL.md",
            "---\nname: custom-field\ndescription: Does helpful things with "
            "files. Use when the user asks.\nmade-up: yes\n---\nbody\n",
        ).parent
        self.assertIn("UNKNOWN_FIELD", codes(validate_skill(path), "warning"))

    def test_secret_file_warns_then_blocks_packaging(self):
        path = self.make_skill("leaky-skill")
        self.write("leaky-skill/.env", "KEY=value\n")
        self.assertIn("SECRET_FILE", codes(validate_skill(path), "warning"))
        self.assertIn(
            "SECRET_FILE",
            codes(validate_skill(path, for_packaging=True), "error"),
        )


class TestTriggerMode(SteerTestCase):
    def test_user_invoked_skips_trigger_checks(self):
        path = self.write(
            "manual-skill/SKILL.md",
            "---\n"
            "name: manual-skill\n"
            "description: Short.\n"
            "disable-model-invocation: true\n"
            "metadata:\n  version: \"0.1.0\"\n"
            "---\n\nDo the thing.\n",
        ).parent
        findings = validate_skill(path)
        self.assertNotIn("DESC_THIN", codes(findings))
        self.assertNotIn("DESC_NO_TRIGGER", codes(findings))
        # still flagged as Claude-Code-only, but softly
        self.assertIn("PORTABILITY", codes(findings, "info"))
        self.assertNotIn("PORTABILITY", codes(findings, "warning"))

    def test_model_invoked_keeps_trigger_checks(self):
        path = self.make_skill("auto-skill", description="Short.")
        findings = validate_skill(path)
        self.assertIn("DESC_THIN", codes(findings, "warning"))


class TestPruningChecks(SteerTestCase):
    PARA = (
        "This exact paragraph is deliberately long enough to cross the "
        "duplicate-detection threshold of one hundred and twenty characters "
        "so it counts."
    )

    def test_duplicate_paragraph_across_files(self):
        path = self.make_skill(
            "dup-skill",
            body=f"Read references/notes.md first.\n\n{self.PARA}\n",
        )
        self.write("dup-skill/references/notes.md", f"Intro.\n\n{self.PARA}\n")
        findings = validate_skill(path)
        self.assertIn("DUPLICATE_TEXT", codes(findings, "warning"))

    def test_short_repeats_not_flagged(self):
        path = self.make_skill("ok-skill", body="Do it.\n\nDo it.\n")
        findings = validate_skill(path)
        self.assertNotIn("DUPLICATE_TEXT", codes(findings))

    def test_orphan_reference_flagged(self):
        path = self.make_skill("orphan-skill")
        self.write("orphan-skill/references/unused.md", "Nobody points here.\n")
        findings = validate_skill(path)
        self.assertIn("REFERENCE_ORPHAN", codes(findings, "info"))

    def test_mentioned_reference_not_flagged(self):
        path = self.make_skill(
            "pointed-skill",
            body="When mapping fields, read references/mapping.md first.\n",
        )
        self.write("pointed-skill/references/mapping.md", "Field map.\n")
        findings = validate_skill(path)
        self.assertNotIn("REFERENCE_ORPHAN", codes(findings))
