"""End-to-end CLI tests: new → validate → package → install → list,
plus the runtime subcommands, all through cli.main()."""

import contextlib
import io
import json

from steer.cli import main
from tests.helpers import SteerTestCase


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


DESCRIPTION = "Builds widget reports from CSVs. Use when the user asks for widget reports."


class TestAuthoringLifecycle(SteerTestCase):
    def test_new_validate_package_install_list(self):
        code, out, err = run_cli(
            "new", "widget-reports", "--description", DESCRIPTION,
            "--with", "secrets,store,context,flow", "--scripts",
        )
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "widget-reports" / "SKILL.md").exists())
        self.assertTrue((self.root / "widget-reports" / "flow.toml").exists())

        code, out, err = run_cli("validate", "widget-reports")
        self.assertEqual(code, 0, out + err)

        code, out, err = run_cli("package", "widget-reports", "-o", "widget.zip")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "widget.zip").exists())

        code, out, err = run_cli("install", "widget.zip")
        self.assertEqual(code, 0, err)
        installed = self.root / ".claude" / "skills" / "widget-reports"
        self.assertTrue((installed / "SKILL.md").exists())

        code, out, err = run_cli("list", "--json")
        self.assertEqual(code, 0, err)
        names = [s["name"] for s in json.loads(out)]
        self.assertIn("widget-reports", names)

    def test_new_rejects_bad_name(self):
        code, _, err = run_cli("new", "Bad_Name")
        self.assertEqual(code, 1)
        self.assertIn("Invalid skill name", err)

    def test_new_user_invoked(self):
        code, out, err = run_cli(
            "new", "manual-tool", "--user-invoked",
            "--description", "Rebuilds the release notes from git history.",
        )
        self.assertEqual(code, 0, err)
        content = (self.root / "manual-tool" / "SKILL.md").read_text()
        self.assertIn("disable-model-invocation: true", content)
        from steer.validate import validate_skill
        finding_codes = {f.code for f in validate_skill(self.root / "manual-tool")}
        self.assertNotIn("DESC_NO_TRIGGER", finding_codes)
        self.assertNotIn("DESC_THIN", finding_codes)

    def test_new_refs_teaches_context_pointers(self):
        code, _, err = run_cli(
            "new", "ref-heavy", "--refs", "--description", DESCRIPTION,
        )
        self.assertEqual(code, 0, err)
        content = (self.root / "ref-heavy" / "SKILL.md").read_text()
        self.assertIn("## References", content)
        self.assertTrue((self.root / "ref-heavy" / "references").is_dir())

    def test_validate_reports_errors(self):
        self.write("broken/SKILL.md", "---\nname: nope!\n---\nbody\n")
        code, out, _ = run_cli("validate", "broken")
        self.assertEqual(code, 1)
        self.assertIn("NAME_INVALID", out)
        self.assertIn("DESC_MISSING", out)

    def test_package_blocks_secret_files(self):
        run_cli("new", "leaky", "--description", DESCRIPTION)
        self.write("leaky/.env", "X=1\n")
        code, _, err = run_cli("package", "leaky")
        self.assertEqual(code, 1)
        self.assertIn("SECRET_FILE", err)

    def test_install_refuses_overwrite_without_force(self):
        run_cli("new", "dupe", "--description", DESCRIPTION)
        code, _, _ = run_cli("install", "dupe")
        self.assertEqual(code, 0)
        code, _, err = run_cli("install", "dupe")
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        code, _, _ = run_cli("install", "dupe", "--force")
        self.assertEqual(code, 0)


class TestRuntimeCommands(SteerTestCase):
    def test_secrets_set_check_get_via_stdin_isolated(self):
        # File backend keeps the test off the real OS keychain.
        code, out, _ = run_cli("secrets", "set", "API_KEY", "sk-1",
                               "--skill", "t", "--backend", "file")
        self.assertEqual(code, 0)
        code, out, _ = run_cli("secrets", "check", "API_KEY", "--skill", "t")
        self.assertEqual(code, 0)
        code, out, _ = run_cli("secrets", "get", "API_KEY", "--skill", "t")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "sk-1")

    def test_secrets_check_missing_gives_remediation(self):
        code, _, err = run_cli("secrets", "check", "NOPE", "--skill", "t")
        self.assertEqual(code, 1)
        self.assertIn("steer secrets set NOPE --skill t", err)

    def test_skill_inferred_from_cwd(self):
        import os

        skill_dir = self.make_skill("inferred-skill")
        os.chdir(skill_dir)
        code, out, _ = run_cli("secrets", "set", "K", "v", "--backend", "file")
        self.assertEqual(code, 0)
        self.assertIn("inferred-skill", out)

    def test_store_roundtrip(self):
        code, _, _ = run_cli("store", "put", "k", '{"a": 1}', "--skill", "t")
        self.assertEqual(code, 0)
        code, out, _ = run_cli("store", "get", "k", "--skill", "t")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"a": 1})
        code, out, _ = run_cli("store", "insert", "runs",
                               '{"ok": true}', "--skill", "t")
        self.assertEqual(code, 0)
        code, out, _ = run_cli("store", "find", "runs", "--where", "ok=true",
                               "--skill", "t")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)), 1)

    def test_context_json(self):
        code, out, _ = run_cli("context", "--json", "--only", "system,project")
        self.assertEqual(code, 0)
        snapshot = json.loads(out)
        self.assertIn("system", snapshot)
        self.assertIn("project", snapshot)
        self.assertNotIn("git", snapshot)

    def test_flow_from_skill_dir(self):
        import os

        skill_dir = self.make_skill("flow-skill")
        self.write(
            "flow-skill/flow.toml",
            'name = "f"\n[[steps]]\nid = "a"\ndirective = "Do A"\n'
            "\n[[steps]]\nid = \"b\"\ndirective = \"Do B\"\nrequires = [\"a\"]\n",
        )
        os.chdir(skill_dir)
        ws = self.root / "ws"
        ws.mkdir()
        code, out, _ = run_cli("flow", "next", "--workspace", str(ws), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["step"], "a")
        # Mandate gating via CLI
        code, _, err = run_cli("flow", "done", "b", "--workspace", str(ws))
        self.assertEqual(code, 1)
        self.assertIn("blocked", err)
        code, _, _ = run_cli("flow", "done", "a", "--workspace", str(ws))
        self.assertEqual(code, 0)
        code, out, _ = run_cli("flow", "next", "--workspace", str(ws), "--json")
        self.assertEqual(json.loads(out)["step"], "b")

    def test_new_component_inputs(self):
        code, out, err = run_cli(
            "new", "stripe-sync", "--description", DESCRIPTION,
            "--secrets", "STRIPE_API_KEY,STRIPE_ACCOUNT",
            "--steps", "fetch,transform,review",
        )
        self.assertEqual(code, 0, err)
        content = (self.root / "stripe-sync" / "SKILL.md").read_text()
        self.assertIn("steer secrets check STRIPE_API_KEY", content)
        self.assertIn("steer secrets check STRIPE_ACCOUNT", content)
        flow = (self.root / "stripe-sync" / "flow.toml").read_text()
        self.assertIn('id = "fetch"', flow)
        self.assertIn('id = "transform"', flow)
        self.assertIn('requires = ["transform"]', flow)

    def test_new_rejects_bad_component_inputs(self):
        code, _, err = run_cli("new", "x-skill", "--secrets", "lower_case")
        self.assertEqual(code, 1)
        self.assertIn("UPPER_SNAKE_CASE", err)
        code, _, err = run_cli("new", "y-skill", "--steps", "Bad Step")
        self.assertEqual(code, 1)
        self.assertIn("kebab-case", err)
