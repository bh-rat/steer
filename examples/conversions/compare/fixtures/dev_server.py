#!/usr/bin/env python3
"""Stand-in for `npm run dev`: a wrapper that spawns the real server as a child."""
import os
import subprocess
import sys


def main() -> int:
    port = sys.argv[1]
    child = subprocess.Popen([sys.executable, "-m", "http.server",
                              "--bind", "127.0.0.1", port])
    pidfile = os.environ.get("DEV_SERVER_PIDFILE")
    if pidfile:
        with open(pidfile, "w", encoding="utf-8") as f:
            f.write(str(child.pid))
    print(f"wrapper {os.getpid()} spawned server child {child.pid} on port {port}",
          flush=True)
    return child.wait()


if __name__ == "__main__":
    sys.exit(main())
