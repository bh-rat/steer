"""
Per-skill credential management.

Skills get zipped, uploaded, and shared; credentials must live outside
the skill directory. Steer resolves a secret in this order:

1. Environment variable with the exact key name (``STRIPE_API_KEY``)
2. OS keychain (macOS ``security``, Linux ``secret-tool``)
3. Steer's file store: ``~/.steer/skills/<skill>/secrets.json`` (0600)

Errors are written for agents: a missing secret tells the agent exactly
what command to ask the human to run.

Usage (library):
    from steer.secrets import Secrets
    secrets = Secrets("my-skill")
    key = secrets.require("STRIPE_API_KEY", hint="dashboard.stripe.com/apikeys")

Usage (CLI, from SKILL.md):
    steer secrets check STRIPE_API_KEY --skill my-skill
    steer secrets set STRIPE_API_KEY --skill my-skill
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .paths import skill_data_dir

ENV = "env"
KEYCHAIN = "keychain"
FILE = "file"

_SUBPROCESS_TIMEOUT = 10


class MissingSecretError(Exception):
    """A required secret is not available in any backend."""

    def __init__(self, skill: str, key: str, hint: Optional[str] = None):
        self.skill = skill
        self.key = key
        self.hint = hint
        super().__init__(remediation_message(skill, key, hint))


def remediation_message(skill: str, key: str, hint: Optional[str] = None) -> str:
    """Agent-facing instructions for getting a secret in place."""
    lines = [
        f"Secret '{key}' is not set for skill '{skill}'.",
        "Ask the user to provide it, then store it with:",
        f"  steer secrets set {key} --skill {skill}",
        f"(or export {key}=... in the environment)",
    ]
    if hint:
        lines.insert(1, f"Where to find it: {hint}")
    return "\n".join(lines)


def _keychain_service(skill: str) -> str:
    return f"steer.{skill}"


def _run(cmd: List[str], input_text: Optional[str] = None) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, input=input_text, capture_output=True, text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)


class _KeychainBackend:
    """OS keychain via macOS `security` or Linux `secret-tool`."""

    def __init__(self) -> None:
        self.tool: Optional[str] = None
        if sys.platform == "darwin" and shutil.which("security"):
            self.tool = "security"
        elif shutil.which("secret-tool"):
            self.tool = "secret-tool"

    @property
    def available(self) -> bool:
        return self.tool is not None

    def get(self, skill: str, key: str) -> Optional[str]:
        service = _keychain_service(skill)
        if self.tool == "security":
            code, out, _ = _run(
                ["security", "find-generic-password", "-s", service, "-a", key, "-w"]
            )
            return out.rstrip("\n") if code == 0 else None
        if self.tool == "secret-tool":
            code, out, _ = _run(["secret-tool", "lookup", "service", service, "key", key])
            return out.rstrip("\n") if code == 0 else None
        return None

    def set(self, skill: str, key: str, value: str) -> bool:
        service = _keychain_service(skill)
        if self.tool == "security":
            code, _, _ = _run(
                ["security", "add-generic-password", "-U",
                 "-s", service, "-a", key, "-w", value,
                 "-l", f"steer secret: {skill}/{key}"]
            )
            return code == 0
        if self.tool == "secret-tool":
            code, _, _ = _run(
                ["secret-tool", "store", "--label", f"steer secret: {skill}/{key}",
                 "service", service, "key", key],
                input_text=value,
            )
            return code == 0
        return False

    def unset(self, skill: str, key: str) -> bool:
        service = _keychain_service(skill)
        if self.tool == "security":
            code, _, _ = _run(
                ["security", "delete-generic-password", "-s", service, "-a", key]
            )
            return code == 0
        if self.tool == "secret-tool":
            code, _, _ = _run(["secret-tool", "clear", "service", service, "key", key])
            return code == 0
        return False


class Secrets:
    """Credential access for one skill."""

    def __init__(self, skill: str):
        if not skill:
            raise ValueError("Secrets requires a skill name")
        self.skill = skill
        self._keychain = _KeychainBackend()

    # -- file backend -------------------------------------------------

    def _file_path(self) -> Path:
        return skill_data_dir(self.skill) / "secrets.json"

    def _index_path(self) -> Path:
        # Names (never values) of keys stored in the OS keychain, so
        # list() can enumerate them.
        return skill_data_dir(self.skill) / "keychain-keys.json"

    def _read_json(self, path: Path) -> Dict:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_json(self, path: Path, data: Dict) -> None:
        skill_data_dir(self.skill, create=True)
        path.parent.chmod(0o700)
        # Create 0600 from the first byte: never a window where another
        # local user can read the plaintext.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2) + "\n")
        path.chmod(0o600)  # tighten pre-existing files too

    # -- resolution ---------------------------------------------------

    def get_with_origin(self, key: str) -> Tuple[Optional[str], Optional[str]]:
        """Resolve a secret, returning (value, origin)."""
        env_value = os.environ.get(key)
        if env_value:
            return env_value, ENV
        keychain_value = self._keychain.get(self.skill, key)
        if keychain_value is not None:
            return keychain_value, KEYCHAIN
        file_value = self._read_json(self._file_path()).get(key)
        if file_value is not None:
            return file_value, FILE
        return None, None

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        value, _ = self.get_with_origin(key)
        return value if value is not None else default

    def status(self, key: str) -> Optional[str]:
        """Which backend currently provides this key, or None."""
        _, origin = self.get_with_origin(key)
        return origin

    def require(self, key: str, hint: Optional[str] = None) -> str:
        """Get a secret or raise MissingSecretError with agent guidance."""
        value, _ = self.get_with_origin(key)
        if value is None:
            raise MissingSecretError(self.skill, key, hint)
        return value

    # -- mutation -----------------------------------------------------

    def set(self, key: str, value: str, backend: str = "auto") -> str:
        """Store a secret. Returns the backend used."""
        if backend not in ("auto", KEYCHAIN, FILE):
            raise ValueError(f"Unknown backend: {backend}")
        if backend in ("auto", KEYCHAIN) and self._keychain.available:
            if self._keychain.set(self.skill, key, value):
                index = self._read_json(self._index_path())
                names = set(index.get("keys", []))
                names.add(key)
                self._write_json(self._index_path(), {"keys": sorted(names)})
                return KEYCHAIN
            if backend == KEYCHAIN:
                raise RuntimeError("Keychain write failed")
        if backend == KEYCHAIN:
            raise RuntimeError("No keychain backend available on this system")
        data = self._read_json(self._file_path())
        data[key] = value
        self._write_json(self._file_path(), data)
        return FILE

    def unset(self, key: str) -> List[str]:
        """Remove a secret from all steer-managed backends. Returns origins removed."""
        removed = []
        if self._keychain.available and self._keychain.unset(self.skill, key):
            removed.append(KEYCHAIN)
        index = self._read_json(self._index_path())
        names = set(index.get("keys", []))
        if key in names:
            names.discard(key)
            self._write_json(self._index_path(), {"keys": sorted(names)})
        data = self._read_json(self._file_path())
        if key in data:
            del data[key]
            self._write_json(self._file_path(), data)
            removed.append(FILE)
        return removed

    def list_keys(self) -> Dict[str, Optional[str]]:
        """Known key names -> backend that currently resolves them.

        Covers steer-managed backends plus any currently-set env vars for
        those names. (Env-only secrets steer has never seen can't be
        enumerated.)
        """
        names = set(self._read_json(self._file_path()).keys())
        names |= set(self._read_json(self._index_path()).get("keys", []))
        return {name: self.status(name) for name in sorted(names)}
