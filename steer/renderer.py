"""
Flow rendering for terminal and JSON output.

Renders Flow progress and Directives to the terminal (human-readable)
or as JSON (for AI agents). This is the generic rendering layer that any
steer-based tool gets for free.

Output is plain text; consumers can subclass or wrap to add their own
terminal styling (colors, rich panels, etc.).
"""

import json as json_module

from .flow import StepStatus


def render_workflow(flow, ctx, format="text"):
    """Render the flow's current state to the terminal.

    Args:
        flow: A Flow instance
        ctx: A StepContext with current state
        format: "text" for human-readable, "json" for agent-parseable

    Returns:
        The current Directive (or None if all complete).
    """
    directive = flow.get_directive(ctx)
    progress = flow.get_progress(ctx)

    if format == "json":
        render_workflow_json(directive, progress)
    else:
        render_workflow_text(flow, directive, progress)

        # Render step-specific tips if the step has a tips callback
        if directive and directive.step:
            step = flow.get_step(directive.step)
            if step and step.tips:
                step.tips(ctx)

    return directive


def render_workflow_json(directive, progress):
    """Render workflow state as JSON (for agents)."""
    output = {
        "progress": progress,
    }
    if directive:
        output["directive"] = directive.to_dict()
    print(json_module.dumps(output, indent=2))


def render_workflow_text(flow, directive, progress):
    """Render workflow state as human-readable terminal output."""
    # Header
    print()
    print(f"  {flow.name.upper()} WORKFLOW")
    print(f"  {'─' * 41}")

    # Progress line with step indicators
    completed = progress['completed_steps']
    total = progress['total_steps']

    step_parts = []
    for s in progress['steps']:
        name = s['id']
        if s['status'] == 'complete':
            step_parts.append(f"\u2713 {name}")
        elif s['status'] == 'ready':
            step_parts.append(f"\u25cf {name}")
        else:
            step_parts.append(f"\u25cb {name}")

    print(f"  Progress: {completed}/{total} steps  " + "  ".join(step_parts))
    print()

    if directive is None:
        print("  \u2713 All steps complete!")
        print()
        return directive

    # Render the directive
    render_directive(directive)
    return directive


def render_directive(directive):
    """Render a single Directive to the terminal."""
    status_icons = {
        StepStatus.READY: "\u25b8",
        StepStatus.BLOCKED: "\u25b8",
        StepStatus.ERROR: "\u2717",
        StepStatus.COMPLETE: "\u2713",
        StepStatus.NOT_READY: "\u25cb",
    }
    icon = status_icons.get(directive.status, "")

    # Step header
    print(f"  {icon} Next: {directive.step}")
    print(f"    {directive.description}")
    print()

    # Action
    action = directive.action
    if action.get('command'):
        print(f"    Run: {action['command']}")

    if action.get('steps'):
        for i, step_desc in enumerate(action['steps'], 1):
            print(f"    {i}. {step_desc}")

    print()

    # Suggestions
    if directive.suggestions:
        for s in directive.suggestions:
            print(f"    \u2022 {s}")
        print()

    # Constraints
    if directive.constraints:
        for c in directive.constraints:
            level = c.get('level', 'SHOULD')
            rule = c.get('rule', '')
            print(f"    {level}: {rule}")
        print()


def render_commands(commands):
    """Render a list of available commands.

    Args:
        commands: List of (command_str, description) tuples
    """
    print()
    print("  \u25b8 Commands")
    for cmd, desc in commands:
        print(f"    {cmd:<28} {desc}")
