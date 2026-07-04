---
name: webapp-testing
description: Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs. Use when the user asks to test, debug, screenshot, or automate a local web app.
license: Complete terms in LICENSE.txt
metadata:
  version: 0.1.0
---

# webapp-testing
Test and debug local web applications by writing native Python Playwright
scripts. The user gets verified frontend behavior, screenshots, console
logs, or automation results; every server started for the job is managed,
its output captured, and stopped cleanly afterwards.

## Before you start

1. **Ground yourself.** Run `steer context --tools node,npm,playwright`
   and read the snapshot; it tells you the platform, project type, and
   whether node and playwright exist here before you write any script.
2. **Apply past lessons.** Run `steer learn show --skill webapp-testing`
   and follow what it says; those lessons came from real previous runs.

## Decision tree

```
User task -> Is it static HTML?
    - Yes -> Read the HTML file directly to identify selectors
             - Works -> Write a Playwright script using those selectors
             - Fails or incomplete -> Treat as dynamic (below)
    - No (dynamic webapp) -> Is the server already running?
             - No  -> Start it managed (see Servers below), then script
             - Yes -> Reconnaissance then action (below)
```

## Servers

Start every server through steer so nothing leaks or zombies, stdout and
stderr are captured to a log, and readiness is checked before your
automation runs:

    steer proc start app --ready-port 5173 -- npm run dev
    steer proc status app     # running? port open?
    steer proc logs app       # captured output, e.g. startup errors
    steer proc stop app       # TERM then KILL, the whole process group

Multiple servers (e.g. backend + frontend):

    steer proc start backend --ready-port 3000 --cwd backend -- python3 server.py
    steer proc start frontend --ready-port 5173 --cwd frontend -- npm run dev

If a start fails, the error already contains the log tail: read it and
fix the cause instead of retrying blindly. Always stop what you started,
even when your automation failed.

## Writing the automation script

Include only Playwright logic; the server is already running and ready:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)  # always headless
    page = browser.new_page()
    page.goto('http://localhost:5173')
    page.wait_for_load_state('networkidle')  # CRITICAL: wait for JS to execute
    # ... your automation logic
    browser.close()
```

## Reconnaissance then action

1. **Inspect the rendered DOM**:
   ```python
   page.screenshot(path='out/inspect.png', full_page=True)
   content = page.content()
   page.locator('button').all()
   ```
2. **Identify selectors** from what you actually saw.
3. **Act** using the discovered selectors.

## References

Load these only when that branch of the work is hit:

- When discovering buttons, links, or inputs on a page, first read
  `references/element_discovery.py`.
- When automating a static local HTML file (file:// URLs), first read
  `references/static_html_automation.py`.
- When you need browser console output during automation, first read
  `references/console_logging.py`.

## Learning

This skill improves with use. As you work:

- The moment the user corrects you, or something fails and then works a
  different way, capture it:
  `steer learn note "<one imperative rule>" --kind correction --skill webapp-testing`
  Lessons are atomic rules ("Use X not Y when Z"), never secrets.
- When a lesson from `steer learn show --skill webapp-testing` helped, run
  `steer learn confirm <id> --skill webapp-testing`; when one was wrong,
  `steer learn dispute <id> --skill webapp-testing`.
- Before finishing, record the outcome:
  `steer learn run ok --skill webapp-testing` (or `failed` with `--note`).

If a `learnings.md` exists in this skill, read it too; those are
promoted lessons that shipped with the skill.

## Gotchas

- Dynamic apps render after load: never inspect the DOM before
  `page.wait_for_load_state('networkidle')`. Empty or partial results
  usually mean you inspected too early.
- A server that exits right after starting: `steer proc logs app` shows
  why (port in use, missing dependency). Fix the cause, then start again.
- `steer proc start` refuses a name that is already running; that is the
  leftover server from a previous task. Stop it or reuse it deliberately.
- Prefer stable selectors: `text=`, `role=`, ids. Brittle positional
  chains break on the next render.
- Use `sync_playwright()` for scripts and always close the browser.
- Prefer `page.wait_for_selector()` over arbitrary sleeps.
