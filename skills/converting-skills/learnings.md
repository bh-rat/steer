# Learnings

Lessons promoted from real runs (managed with `steer learn`).
Read this before relying on the main instructions.

- Give a later verify step a condition that cannot hold before its prerequisites' artifacts exist; a fresh steer scaffold already passes validate, so a bare 'steer validate' gate reads complete before the port happens <!-- steer:lesson 1 2026-07-04 -->
- In teaching references, describe component commands in prose; concrete scripts/steer.py <component> examples for other skills trip the bundled-runtime consistency scan <!-- steer:lesson 2 2026-07-04 -->
