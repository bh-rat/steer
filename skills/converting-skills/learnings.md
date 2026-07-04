# Learnings

Lessons promoted from real runs (managed with `steer learn`).
Read this before relying on the main instructions.

- Give a later verify step a condition that cannot hold before its prerequisites' artifacts exist; a fresh steer scaffold already passes validate, so a bare 'steer validate' gate reads complete before the port happens <!-- steer:lesson 1 2026-07-04 -->
