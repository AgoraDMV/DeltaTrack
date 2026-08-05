"""Logs any request that reaches it, so a file:// page's egress attempts are observable.

Stands in for an attacker-controlled host. Everything is loopback, so nothing leaves
this machine, but from the browser's perspective it is a different origin than `null`.
"""

import http.server
import socketserver
import threading

HITS = []


class Handler(http.server.BaseHTTPRequestHandler):
    def _log_and_ok(self, verb):
        HITS.append(f"{verb} {self.path}")
        print(f"  EGRESS OBSERVED: {verb} {self.path[:90]}", flush=True)
        body = b"x"
        self.send_response(200)
        # Permissive CORS, so any CORS-related failure is clearly NOT the reason
        # a request did or did not arrive.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "image/gif")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._log_and_ok("GET")

    def do_POST(self):
        self._log_and_ok("POST")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", 8973), Handler) as httpd:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        print("listening on 127.0.0.1:8973", flush=True)
        import time

        time.sleep(120)
