#!/usr/bin/env python3
"""A server with verbose build output before it becomes ready."""
import http.server
import socketserver
import sys


def main() -> int:
    port = int(sys.argv[1])
    for i in range(4096):
        sys.stdout.write(f"[build] step {i}: compiled module {i} of 4096\n")
    sys.stdout.flush()
    with socketserver.TCPServer(("127.0.0.1", port),
                                http.server.SimpleHTTPRequestHandler) as httpd:
        sys.stdout.write("ready\n")
        sys.stdout.flush()
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
