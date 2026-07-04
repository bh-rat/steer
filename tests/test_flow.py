from pathlib import Path

from steer.flow import (
    Flow,
    FlowBlockedError,
    Step,
    StepStatus,
    find_flow_file,
    load_flow,
)
from tests.helpers import SteerTestCase

FLOW_TOML = """\
name = "demo"

[[steps]]
id = "config"
description = "Create the config"
directive = "Write out/config.json"

[steps.verify]
file_exists = "out/config.json"

[[steps]]
id = "review"
description = "Review it"
directive = "Read the config and confirm"
requires = ["config"]

[[steps]]
id = "publish"
description = "Publish"
command = "true"
requires = ["review"]

[steps.verify]
command = "test -f out/published"
"""


class TestFlowEngine(SteerTestCase):
    def _flow(self):
        flow = Flow("t", workspace=str(self.root))
        flow.add_step(Step(
            id="first",
            description="First",
            verify=lambda ctx: (Path(ctx.workspace) / "first.txt").exists(),
        ))
        flow.add_step(Step(id="approve", description="Approve",
                           requires=["first"]))
        return flow

    def test_directive_walks_to_first_incomplete(self):
        flow = self._flow()
        directive = flow.get_directive(flow.context())
        self.assertEqual(directive.step, "first")
        self.assertEqual(directive.status, StepStatus.READY)

    def test_mandate_blocked_until_prereq_real(self):
        flow = self._flow()
        with self.assertRaises(FlowBlockedError):
            flow.mark_complete("approve")

    def test_mandate_persists(self):
        flow = self._flow()
        (self.root / "first.txt").touch()
        self.assertTrue(flow.mark_complete("approve"))
        # A fresh Flow instance sees the persisted completion.
        fresh = self._flow()
        directive = fresh.get_directive(fresh.context())
        self.assertEqual(directive.status, StepStatus.COMPLETE)

    def test_verified_step_cannot_be_marked(self):
        flow = self._flow()
        self.assertFalse(flow.mark_complete("first"))

    def test_reset(self):
        flow = self._flow()
        (self.root / "first.txt").touch()
        flow.mark_complete("approve")
        flow.reset("approve")
        directive = flow.get_directive(flow.context())
        self.assertEqual(directive.step, "approve")

    def test_progress(self):
        flow = self._flow()
        (self.root / "first.txt").touch()
        progress = flow.get_progress(flow.context())
        self.assertEqual(progress["completed_steps"], 1)
        self.assertEqual(progress["current_step"], "approve")


class TestDeclarativeFlow(SteerTestCase):
    def test_load_and_walk(self):
        path = self.write("skill/flow.toml", FLOW_TOML)
        ws = self.root / "ws"
        ws.mkdir()
        flow = load_flow(path, workspace=str(ws))
        self.assertEqual(flow.name, "demo")
        self.assertEqual([s.id for s in flow.steps],
                         ["config", "review", "publish"])

        directive = flow.get_directive(flow.context())
        self.assertEqual(directive.step, "config")

        (ws / "out").mkdir()
        (ws / "out" / "config.json").write_text("{}")
        directive = flow.get_directive(flow.context())
        self.assertEqual(directive.step, "review")

        flow.mark_complete("review")
        directive = flow.get_directive(flow.context())
        self.assertEqual(directive.step, "publish")
        self.assertEqual(directive.action.get("command"), "true")

        (ws / "out" / "published").touch()
        directive = flow.get_directive(flow.context())
        self.assertEqual(directive.status, StepStatus.COMPLETE)

    def test_unknown_verify_condition_rejected(self):
        path = self.write(
            "bad/flow.toml",
            'name = "bad"\n[[steps]]\nid = "a"\n[steps.verify]\nmagic = "x"\n',
        )
        with self.assertRaises(ValueError):
            load_flow(path)

    def test_missing_id_rejected(self):
        path = self.write(
            "bad2/flow.toml", 'name = "bad2"\n[[steps]]\ndescription = "x"\n'
        )
        with self.assertRaises(ValueError):
            load_flow(path)

    def test_find_flow_file(self):
        skill_dir = self.make_skill("flowy-skill")
        self.assertIsNone(find_flow_file(skill_dir))
        self.write("flowy-skill/flow.toml", FLOW_TOML)
        self.assertEqual(find_flow_file(skill_dir).name, "flow.toml")

    def test_env_verifier(self):
        import os

        path = self.write(
            "envf/flow.toml",
            'name = "envf"\n[[steps]]\nid = "a"\ndirective = "set it"\n'
            '[steps.verify]\nenv = "STEER_TEST_FLAG_XYZ"\n',
        )
        flow = load_flow(path, workspace=str(self.root))
        self.assertEqual(flow.get_directive(flow.context()).step, "a")
        os.environ["STEER_TEST_FLAG_XYZ"] = "1"
        try:
            directive = flow.get_directive(flow.context())
            self.assertEqual(directive.status, StepStatus.COMPLETE)
        finally:
            del os.environ["STEER_TEST_FLAG_XYZ"]


class TestStateRobustness(SteerTestCase):
    def test_non_object_state_file_tolerated(self):
        flow = load_flow(self.write("flow.toml", FLOW_TOML),
                         workspace=str(self.root))
        state_file = self.root / ".steer" / "flows" / "demo.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        for junk in ("[]", '"oops"', "42"):
            state_file.write_text(junk)
            self.assertEqual(flow.load_state()["completed"], [])


class TestPlaceholderExpansion(SteerTestCase):
    def test_skill_dir_expands_in_command_and_verify(self):
        flow_file = self.write(
            "skill-a/flow.toml",
            'name = "demo-x"\n'
            "[[steps]]\n"
            'id = "run"\n'
            'directive = "Run the collector"\n'
            'command = "python3 {skill_dir}/scripts/go.py"\n'
            "[steps.verify]\n"
            'command = "test -d {skill_dir}"\n',
        )
        flow = load_flow(flow_file, workspace=str(self.root))
        step = flow.get_step("run")
        directive = step.get_directive(flow.context())
        expected = str((self.root / "skill-a").resolve())
        self.assertEqual(directive.action["command"],
                         f"python3 {expected}/scripts/go.py")
        self.assertTrue(step.verify(flow.context()))
