import sys
import time

from steer import proc
from steer.context import gather, to_markdown
from tests.helpers import SteerTestCase


class TestContext(SteerTestCase):
    def test_gather_sections(self):
        snapshot = gather(workspace=str(self.root))
        for section in ("system", "agent", "git", "project", "tools", "env"):
            self.assertIn(section, snapshot)

    def test_project_detection(self):
        self.write("proj/package.json", "{}")
        self.write("proj/pnpm-lock.yaml", "")
        self.write("proj/Dockerfile", "FROM scratch\n")
        snapshot = gather(workspace=str(self.root / "proj"), only=["project"])
        self.assertIn("node", snapshot["project"]["types"])
        self.assertIn("pnpm", snapshot["project"]["package_managers"])
        self.assertIn("docker", snapshot["project"]["extras"])

    def test_only_filters(self):
        snapshot = gather(only=["system"])
        self.assertEqual(list(snapshot), ["system"])

    def test_unknown_section_raises(self):
        with self.assertRaises(ValueError):
            gather(only=["nope"])

    def test_markdown_renders(self):
        text = to_markdown(gather(workspace=str(self.root)))
        self.assertIn("## Context snapshot", text)
        self.assertIn("**System**", text)

    def test_env_never_dumps_everything(self):
        import os

        os.environ["STEER_SUPER_SECRET_TEST"] = "boom"
        try:
            snapshot = gather(only=["env"])
            self.assertNotIn("STEER_SUPER_SECRET_TEST", snapshot["env"])
        finally:
            del os.environ["STEER_SUPER_SECRET_TEST"]


class TestProc(SteerTestCase):
    def test_start_status_stop(self):
        ws = str(self.root)
        info = proc.start("sleeper", [sys.executable, "-c",
                                      "import time; time.sleep(30)"],
                          workspace=ws)
        self.assertTrue(info["running"])
        try:
            status = proc.status("sleeper", ws)
            self.assertTrue(status["running"])
            self.assertIn("sleeper", [p["name"] for p in proc.list_procs(ws)])
        finally:
            result = proc.stop("sleeper", ws)
        self.assertTrue(result["stopped"])
        time.sleep(0.2)
        self.assertFalse(proc.status("sleeper", ws)["running"])

    def test_double_start_refused(self):
        ws = str(self.root)
        proc.start("once", [sys.executable, "-c", "import time; time.sleep(30)"],
                   workspace=ws)
        try:
            with self.assertRaises(proc.ProcError):
                proc.start("once", ["true"], workspace=ws)
        finally:
            proc.stop("once", ws)

    def test_immediate_exit_reports_log(self):
        ws = str(self.root)
        with self.assertRaises(proc.ProcError) as ctx:
            proc.start("dying",
                       [sys.executable, "-c",
                        "import sys; print('boom'); sys.exit(3)"],
                       workspace=ws, ready_port=19999, timeout=5)
        self.assertIn("boom", str(ctx.exception))

    def test_ready_log(self):
        ws = str(self.root)
        info = proc.start(
            "logger",
            [sys.executable, "-u", "-c",
             "import time; print('SERVER READY'); time.sleep(30)"],
            workspace=ws, ready_log="SERVER READY", timeout=10,
        )
        try:
            self.assertTrue(info["running"])
        finally:
            proc.stop("logger", ws)

    def test_stop_unknown_raises(self):
        with self.assertRaises(proc.ProcError):
            proc.stop("never-started", str(self.root))


class TestCreateModule(SteerTestCase):
    def test_create_with_components_validates_clean(self):
        from steer.create import create_skill
        from steer.validate import has_errors, validate_skill

        create_skill(
            "full-skill", parent_dir=str(self.root),
            description="Does full things with data. Use when the user wants "
                        "full things.",
            components=["secrets", "store", "context", "flow", "proc"],
            scripts=True, refs=True,
        )
        skill_dir = self.root / "full-skill"
        findings = validate_skill(skill_dir)
        self.assertFalse(has_errors(findings), findings)
        content = (skill_dir / "SKILL.md").read_text()
        for marker in ("python3 scripts/steer.py context",
                       "python3 scripts/steer.py secrets check",
                       "python3 scripts/steer.py flow status",
                       "python3 scripts/steer.py store",
                       "python3 scripts/steer.py proc"):
            self.assertIn(marker, content)
        self.assertTrue((skill_dir / "scripts" / "steer.py").exists())
        self.assertTrue((skill_dir / "flow.toml").exists())
        self.assertTrue((skill_dir / "scripts" / "example.py").exists())
        self.assertTrue((skill_dir / "references").is_dir())

    def test_minimal_skill_validates_clean(self):
        from steer.create import create_skill
        from steer.validate import validate_skill

        create_skill(
            "tiny-skill", parent_dir=str(self.root),
            description="Does tiny things quickly. Use when the user asks "
                        "for tiny things.",
        )
        findings = validate_skill(self.root / "tiny-skill")
        self.assertEqual([f for f in findings if f.level != "info"], [],
                         findings)

    def test_unknown_component_rejected(self):
        from steer.create import create_skill

        with self.assertRaises(ValueError):
            create_skill("x-skill", components=["telepathy"])


class TestProcNameSafety(SteerTestCase):
    def test_traversal_name_rejected(self):
        with self.assertRaises(ValueError):
            proc.start("../evil", [sys.executable, "-c", "pass"],
                       workspace=str(self.root))

    def test_pid_match_is_case_insensitive(self):
        # macOS framework Python re-execs as .../MacOS/Python (capital P)
        # while argv[0] said .../bin/python; the guard must not care.
        child = __import__("subprocess").Popen(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            start_new_session=True)
        try:
            self.assertTrue(proc._pid_matches(child.pid,
                                              sys.executable.upper()))
        finally:
            child.kill()
            child.wait()

    def test_zombie_does_not_count_as_running(self):
        import os
        import subprocess
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True)
        os.kill(child.pid, 9)
        time.sleep(0.3)  # dead but unreaped: a zombie of this process
        try:
            self.assertFalse(proc._pid_matches(child.pid, sys.executable))
        finally:
            child.wait()
