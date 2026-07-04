import os

from steer.secrets import MissingSecretError, Secrets
from steer.store import Store
from tests.helpers import SteerTestCase


class FileOnlySecrets(Secrets):
    """Secrets with the keychain disabled, so tests never touch the OS."""

    def __init__(self, skill):
        super().__init__(skill)
        self._keychain.tool = None


class TestSecrets(SteerTestCase):
    def test_file_backend_roundtrip(self):
        secrets = FileOnlySecrets("test-skill")
        backend = secrets.set("API_KEY", "sk-123")
        self.assertEqual(backend, "file")
        self.assertEqual(secrets.get("API_KEY"), "sk-123")
        self.assertEqual(secrets.status("API_KEY"), "file")

    def test_file_permissions(self):
        secrets = FileOnlySecrets("test-skill")
        secrets.set("API_KEY", "sk-123")
        mode = secrets._file_path().stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_env_wins(self):
        secrets = FileOnlySecrets("test-skill")
        secrets.set("MY_TOKEN", "from-file")
        os.environ["MY_TOKEN"] = "from-env"
        try:
            value, origin = secrets.get_with_origin("MY_TOKEN")
            self.assertEqual(value, "from-env")
            self.assertEqual(origin, "env")
        finally:
            del os.environ["MY_TOKEN"]

    def test_require_raises_with_guidance(self):
        secrets = FileOnlySecrets("test-skill")
        with self.assertRaises(MissingSecretError) as ctx:
            secrets.require("ABSENT_KEY", hint="example.com/keys")
        message = str(ctx.exception)
        self.assertIn("steer secrets set ABSENT_KEY --skill test-skill", message)
        self.assertIn("example.com/keys", message)

    def test_unset_and_list(self):
        secrets = FileOnlySecrets("test-skill")
        secrets.set("A", "1")
        secrets.set("B", "2")
        self.assertEqual(set(secrets.list_keys()), {"A", "B"})
        removed = secrets.unset("A")
        self.assertIn("file", removed)
        self.assertEqual(set(secrets.list_keys()), {"B"})
        self.assertIsNone(secrets.get("A"))

    def test_secrets_stored_outside_skill_dir(self):
        secrets = FileOnlySecrets("test-skill")
        secrets.set("API_KEY", "sk-123")
        self.assertTrue(
            str(secrets._file_path()).startswith(str(self.home)),
            "secrets must live under STEER_HOME, never inside a skill dir",
        )


class TestStore(SteerTestCase):
    def test_kv_roundtrip(self):
        with Store("test-skill") as store:
            store.put("config", {"a": 1})
            self.assertEqual(store.get("config"), {"a": 1})
            store.put("config", {"a": 2})
            self.assertEqual(store.get("config"), {"a": 2})
            self.assertEqual(store.keys(), ["config"])
            self.assertTrue(store.delete("config"))
            self.assertIsNone(store.get("config"))

    def test_documents(self):
        with Store("test-skill") as store:
            store.insert("runs", {"file": "a.csv", "ok": True})
            store.insert("runs", {"file": "b.csv", "ok": False})
            found = store.find("runs", {"ok": True})
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["file"], "a.csv")
            self.assertIn("_id", found[0])
            self.assertEqual(store.count("runs"), 2)

    def test_raw_query(self):
        with Store("test-skill") as store:
            store.insert("runs", {"n": 1})
            rows = store.query("SELECT COUNT(*) AS total FROM runs")
            self.assertEqual(rows[0]["total"], 1)

    def test_scopes_are_separate(self):
        user_store = Store("test-skill", scope="user")
        ws = self.root / "project"
        ws.mkdir()
        ws_store = Store("test-skill", scope="workspace", workspace=str(ws))
        try:
            user_store.put("k", "user-value")
            ws_store.put("k", "ws-value")
            self.assertEqual(user_store.get("k"), "user-value")
            self.assertEqual(ws_store.get("k"), "ws-value")
            self.assertTrue(str(ws_store.path).startswith(str(ws.resolve())))
        finally:
            user_store.close()
            ws_store.close()

    def test_bad_table_name_rejected(self):
        with Store("test-skill") as store:
            with self.assertRaises(ValueError):
                store.insert("bad-name; DROP", {"x": 1})


class TestPathSafety(SteerTestCase):
    def test_store_rejects_traversal_names(self):
        for bad in ("../escape", "a/b", "..", ".hidden", "UPPER"):
            with self.assertRaises(ValueError, msg=bad):
                Store(bad)
            with self.assertRaises(ValueError, msg=bad):
                Store(bad, scope="workspace", workspace=str(self.root))

    def test_secrets_reject_traversal_names(self):
        secrets = FileOnlySecrets("../escape")
        with self.assertRaises(ValueError):
            secrets.set("API_KEY", "v", backend="file")

    def test_secrets_file_is_0600(self):
        secrets = FileOnlySecrets("perm-skill")
        secrets.set("API_KEY", "sk-123", backend="file")
        mode = (self.home / "skills" / "perm-skill" / "secrets.json").stat().st_mode
        self.assertEqual(mode & 0o777, 0o600)

    def test_corrupt_secrets_json_is_tolerated(self):
        secrets = FileOnlySecrets("corrupt-skill")
        secrets.set("API_KEY", "sk-123", backend="file")
        path = self.home / "skills" / "corrupt-skill" / "secrets.json"
        path.write_text('["not", "a", "dict"]')
        self.assertIsNone(secrets.get("API_KEY"))
        self.assertEqual(secrets.list_keys(), {})
