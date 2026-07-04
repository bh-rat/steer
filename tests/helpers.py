"""Shared test plumbing: isolate STEER_HOME and the working directory."""

import os
import tempfile
import unittest
from pathlib import Path


class SteerTestCase(unittest.TestCase):
    """Base case giving each test an isolated STEER_HOME and temp cwd."""

    def setUp(self):
        super().setUp()
        self._temp = tempfile.TemporaryDirectory(prefix="steer-test-")
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.home = self.root / "steer-home"
        self._old_env = {
            "STEER_HOME": os.environ.get("STEER_HOME"),
            "STEER_SKILL": os.environ.get("STEER_SKILL"),
        }
        os.environ["STEER_HOME"] = str(self.home)
        os.environ.pop("STEER_SKILL", None)
        self._old_cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._old_cwd)
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        super().tearDown()

    def write(self, rel_path: str, content: str) -> Path:
        path = self.root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def make_skill(self, name: str, description: str = None, body: str = "Do things.\n") -> Path:
        description = description or (
            "Does helpful things with files. Use when the user asks for help."
        )
        return self.write(
            f"{name}/SKILL.md",
            f"---\nname: {name}\ndescription: {description}\n---\n\n{body}",
        ).parent
