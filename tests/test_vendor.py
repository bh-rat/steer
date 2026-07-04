"""The bundled runtime: amalgamation rules, integrity, end-to-end runs."""

import ast
import os
import subprocess
import sys
from pathlib import Path

import steer.cli  # noqa: F401 -- importing it registers the cli_* commands
from steer import __version__, vendor
from steer.create import COMPONENTS, create_skill
from steer.runtime_cli import COMPONENT_ORDER, RUNTIME_REGISTRARS
from steer.validate import validate_skill

from .helpers import SteerTestCase

REPO_ROOT = Path(__file__).resolve().parent.parent
ALL = list(vendor.COMPONENT_MODULES)


def _run(blob, args, cwd):
    return subprocess.run([sys.executable, str(blob), *args],
                          capture_output=True, text=True, cwd=cwd,
                          env={**os.environ}, timeout=60)


class VendorRulesTest(SteerTestCase):
    """The invariants that make flat-namespace amalgamation safe."""

    def test_component_registries_agree(self):
        self.assertEqual(tuple(vendor.COMPONENT_MODULES), COMPONENT_ORDER)
        self.assertEqual(COMPONENTS, COMPONENT_ORDER)
        self.assertEqual(set(RUNTIME_REGISTRARS), set(COMPONENT_ORDER))

    def test_no_top_level_name_collisions(self):
        modules = vendor._bundle_modules(ALL)
        owners = {}  # name -> (module, source segment)
        for module in modules:
            source = (REPO_ROOT / "steer" / f"{module}.py").read_text()
            tree = ast.parse(source)
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                    names = [node.name]
                elif isinstance(node, ast.Assign):
                    names = [t.id for t in node.targets
                             if isinstance(t, ast.Name)]
                elif isinstance(node, ast.AnnAssign) and isinstance(
                        node.target, ast.Name):
                    names = [node.target.id]
                else:
                    continue
                segment = ast.get_source_segment(source, node)
                for name in names:
                    if name in owners:
                        other_module, other_segment = owners[name]
                        self.assertEqual(
                            segment, other_segment,
                            f"{name!r} defined differently in "
                            f"{other_module}.py and {module}.py; the "
                            f"amalgamated bundle would silently keep one")
                    owners[name] = (module, segment)

    def test_module_imports_are_flat_safe(self):
        # `from . import x` has no flat equivalent; generate() must refuse.
        source = "from . import frontmatter\n"
        with self.assertRaises(vendor.VendorError):
            vendor._rewrite_module_imports("fake", source,
                                           ast.parse(source), known=set())

    def test_generate_is_deterministic_and_order_insensitive(self):
        self.assertEqual(vendor.generate(["store", "secrets"]),
                         vendor.generate(["secrets", "store"]))

    def test_top_level_alias_must_come_from_earlier_module(self):
        source = "from .zzz import later_name as alias\n"
        with self.assertRaises(vendor.VendorError):
            vendor._rewrite_module_imports("fake", source,
                                           ast.parse(source), known=set())
        # Inside a function the assignment runs at call time; no constraint.
        deferred = "def f():\n    from .zzz import later_name as alias\n"
        vendor._rewrite_module_imports("fake", deferred,
                                       ast.parse(deferred), known=set())

    def test_hoisted_import_conflicts_are_refused(self):
        imports = vendor._HoistedImports()
        imports.collect("m1", ast.parse("from x import q\n"))
        imports.collect("m3", ast.parse("from x import q\n"))  # same source
        with self.assertRaises(vendor.VendorError):
            imports.collect("m2", ast.parse("from z import q\n"))

    def test_bundle_has_one_top_import_block(self):
        # The generated file must lint like hand-written code: docstring,
        # then a single deduplicated import block, then everything else.
        body = ast.parse(vendor.generate(ALL)).body
        import_idx = [i for i, node in enumerate(body)
                      if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertTrue(import_idx)
        first_other = next(
            i for i, node in enumerate(body[1:], start=1)
            if not isinstance(node, (ast.Import, ast.ImportFrom)))
        self.assertLess(max(import_idx), first_other,
                        "import found below the top import block (E402)")
        bindings = [alias.asname or alias.name.split(".")[0]
                    for i in import_idx for alias in body[i].names]
        self.assertEqual(len(bindings), len(set(bindings)),
                         "duplicate import binding (F811)")

    def test_module_time_seam_reads_are_refused(self):
        for source in ("X = CLI_HINT\n",
                       "HELP = f\"{CLI_HINT} store get\"\n",
                       "def f(x=VENDORED_SKILL_ROOT):\n    return x\n"):
            with self.assertRaises(vendor.VendorError):
                vendor._check_no_module_time_seam_reads(
                    "fake", ast.parse(source))
        vendor._check_no_module_time_seam_reads(
            "fake", ast.parse("def f():\n    return CLI_HINT\n"))

    def test_generate_rejects_unknown_components(self):
        with self.assertRaises(ValueError):
            vendor.generate(["secrets", "telepathy"])
        with self.assertRaises(ValueError):
            vendor.generate([])


class BundleRunsTest(SteerTestCase):
    """Each bundle is a working program with exactly its components."""

    def test_every_single_component_bundle_answers_help(self):
        for component in ALL:
            skill = self.make_skill(f"only-{component}")
            blob = vendor.write_runtime(skill, [component])
            result = _run(blob, ["--help"], cwd=self.root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(component, result.stdout)
            absent = set(ALL) - {component}
            for other in absent:
                self.assertNotIn(f" {other} ", result.stdout)

    def test_subset_bundle_carries_no_excluded_component_code(self):
        # Excluded handlers must be absent entirely, not just unregistered:
        # their stripped lazy imports would otherwise leave truly undefined
        # names in the file (F821 in any consumer repo that lints skills).
        source = vendor.generate(["secrets"])
        for other in set(ALL) - {"secrets"}:
            self.assertNotIn(f"_cmd_{other}", source)
            self.assertNotIn(f"register_{other}_cli", source)
        self.assertNotIn("ProcError", source)
        self.assertNotIn("render_workflow", source)

    def test_store_and_secrets_from_workspace_without_flags(self):
        skill = self.make_skill("mem-skill")
        blob = vendor.write_runtime(skill, ["secrets", "store"])
        work = self.root / "elsewhere"
        work.mkdir()

        put = _run(blob, ["store", "put", "k", '{"n": 1}'], cwd=work)
        self.assertEqual(put.returncode, 0, put.stderr)
        got = _run(blob, ["store", "get", "k"], cwd=work)
        self.assertIn('"n": 1', got.stdout)
        # Data landed under the isolated STEER_HOME, keyed by the skill
        # name inferred from the bundle's own location.
        self.assertTrue((self.home / "skills" / "mem-skill" /
                         "store.db").is_file())

        missing = _run(blob, ["secrets", "check", "API_KEY"], cwd=work)
        self.assertEqual(missing.returncode, 1)
        self.assertIn("scripts/steer.py secrets set", missing.stderr)
        env = {**os.environ, "API_KEY": "x"}
        present = subprocess.run(
            [sys.executable, str(blob), "secrets", "check", "API_KEY"],
            capture_output=True, text=True, cwd=work, env=env)
        self.assertEqual(present.returncode, 0)

        got_missing = _run(blob, ["secrets", "get", "API_KEY"], cwd=work)
        self.assertEqual(got_missing.returncode, 1)
        self.assertNotIn("Traceback", got_missing.stderr)
        self.assertIn("secrets set API_KEY", got_missing.stderr)

    def test_bundle_identity_beats_steer_skill_env(self):
        skill = self.make_skill("own-skill")
        blob = vendor.write_runtime(skill, ["store"])
        work = self.root / "envws"
        work.mkdir()
        env = {**os.environ, "STEER_SKILL": "other-skill"}
        put = subprocess.run(
            [sys.executable, str(blob), "store", "put", "k", "1"],
            capture_output=True, text=True, cwd=work, env=env)
        self.assertEqual(put.returncode, 0, put.stderr)
        self.assertTrue((self.home / "skills" / "own-skill" /
                         "store.db").is_file())
        self.assertFalse((self.home / "skills" / "other-skill").exists())

    def test_runtime_hints_are_runnable_from_anywhere(self):
        create_skill("hinty", parent_dir=str(self.root), components=["flow"])
        blob = self.root / "hinty" / "scripts" / "steer.py"
        work = self.root / "hintws"
        work.mkdir()
        (work / "out").mkdir()
        (work / "out" / "config.json").write_text("{}")
        nxt = _run(blob, ["flow", "next"], cwd=work)
        self.assertEqual(nxt.returncode, 0, nxt.stderr)
        # Printed directives must spell this bundle by absolute path; a
        # workspace-relative "python3 scripts/steer.py" would not run
        # from the workspace the agent actually sits in.
        self.assertIn("flow done review", nxt.stdout)
        self.assertIn(str(blob.resolve()), nxt.stdout)

    def test_flow_drives_from_workspace(self):
        result = create_skill("flowy", parent_dir=str(self.root),
                              components=["flow"])
        self.assertIn("scripts/steer.py", result.created)
        skill = self.root / "flowy"
        blob = skill / "scripts" / "steer.py"
        work = self.root / "ws"
        work.mkdir()

        status = _run(blob, ["flow", "status"], cwd=work)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("prepare", status.stdout)
        blocked = _run(blob, ["flow", "done", "review"], cwd=work)
        self.assertEqual(blocked.returncode, 1)
        (work / "out").mkdir()
        (work / "out" / "config.json").write_text("{}")
        done = _run(blob, ["flow", "done", "review"], cwd=work)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_sibling_scripts_import_the_bundle_as_steer(self):
        skill = self.make_skill("libby")
        vendor.write_runtime(skill, ["store"])
        probe = skill / "scripts" / "probe.py"
        probe.write_text(
            "from steer import Store\n"
            "from steer.output import print_envelope\n"
            "with Store('libby') as s:\n"
            "    s.put('via', 'lib')\n"
            "print_envelope('ok', 'imported')\n")
        work = self.root / "ws"
        work.mkdir()
        result = subprocess.run([sys.executable, str(probe)],
                                capture_output=True, text=True, cwd=work,
                                env={**os.environ})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"status": "ok"', result.stdout)


class BundleIntegrityTest(SteerTestCase):
    """Header, state detection, and the validate/create/package wiring."""

    def test_header_and_state_lifecycle(self):
        skill = self.make_skill("fresh-skill")
        blob = vendor.write_runtime(skill, ["secrets", "flow"])
        header = vendor.read_runtime_header(skill)
        self.assertEqual(header.version, __version__)
        self.assertEqual(header.components, ["secrets", "flow"])
        self.assertEqual(vendor.runtime_state(skill), "fresh")

        blob.write_text(blob.read_text() + "# tweak\n")
        self.assertEqual(vendor.runtime_state(skill), "edited")

        vendor.write_runtime(skill, ["secrets", "flow"])
        stale = blob.read_text().replace(
            f"version={__version__}", "version=0.0.0", 1)
        blob.write_text(stale)
        self.assertEqual(vendor.runtime_state(skill), "stale")

    def test_create_skill_bundles_only_chosen_components(self):
        create_skill("subset", parent_dir=str(self.root),
                     components=["secrets"])
        header = vendor.read_runtime_header(self.root / "subset")
        self.assertEqual(header.components, ["secrets"])
        body = (self.root / "subset" / "SKILL.md").read_text()
        self.assertIn(f"{vendor.RUNTIME_PROG} secrets check", body)
        self.assertNotIn("steer secrets check S", body.replace(
            "scripts/steer.py", ""))

        create_skill("bare", parent_dir=str(self.root))
        self.assertFalse(
            (self.root / "bare" / "scripts" / "steer.py").exists())

    def test_validate_scans_flow_toml_for_runtime_calls(self):
        skill = self.make_skill("flowcall", body="Follow the flow.\n")
        (skill / "flow.toml").write_text(
            'name = "flowcall"\n\n[[steps]]\nid = "s"\n'
            'description = "d"\n'
            'directive = "run: python3 {skill_dir}/scripts/steer.py '
            'store get k"\n')
        vendor.write_runtime(skill, ["flow"])
        codes = {f.code for f in validate_skill(skill)}
        self.assertIn("RUNTIME_COMPONENT", codes)

    def test_validate_flags_runtime_problems(self):
        skill = self.make_skill(
            "misfit",
            body="Run `python3 scripts/steer.py proc start x -- sleep 1`.\n")
        vendor.write_runtime(skill, ["store"])
        codes = {f.code for f in validate_skill(skill)}
        self.assertIn("RUNTIME_COMPONENT", codes)
        packaging = [f for f in validate_skill(skill, for_packaging=True)
                     if f.code == "RUNTIME_COMPONENT"]
        self.assertEqual(packaging[0].level, "error")

    def test_validate_flags_missing_bundle_and_installed_spelling(self):
        no_bundle = self.make_skill(
            "askew", body="Run `python3 scripts/steer.py store get k`.\n")
        codes = {f.code for f in validate_skill(no_bundle)}
        self.assertIn("RUNTIME_MISSING", codes)

        mixed = self.make_skill(
            "mixed",
            body="Run `python3 scripts/steer.py store get k` "
                 "or `steer store get k`.\n")
        vendor.write_runtime(mixed, ["store"])
        codes = {f.code for f in validate_skill(mixed)}
        self.assertIn("RUNTIME_SPELLING", codes)

    def test_example_bundle_is_fresh(self):
        # The committed example must match this steer's output exactly;
        # regenerate it (steer bundle) whenever runtime code changes.
        self.assertEqual(
            vendor.runtime_state(REPO_ROOT / "examples" / "repo-health"),
            "fresh")
