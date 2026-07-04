#!/usr/bin/env python3
"""A server that dies on startup, the way real ones do."""
import sys

print("FATAL: DATABASE_URL is not set; cannot start", file=sys.stderr)
sys.exit(1)
