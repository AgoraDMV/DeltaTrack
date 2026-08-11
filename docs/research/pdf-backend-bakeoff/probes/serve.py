"""Logging server standing in for an attacker-controlled host.

Everything is loopback, so nothing leaves this machine, but from the browser's point of
view it is a different origin than `null`.

Two listeners, not one. The predecessor probe spoke only HTTP, which meant a WebRTC STUN
attempt could not have appeared in its log *regardless of whether the browser made one* --
a check structurally incapable of firing, which reads identically to a pass. The UDP
listener closes that: a STUN binding request is a UDP datagram, and any datagram arriving
on the port is recorded.

Assert on what the SERVER received, never on whether JavaScript threw. Under CSP most
vectors report `attempted` with no exception; they simply produce no request.
"""

from __future__ import annotations

import argparse
import http.server
import json
import socket
import socketserver
import threading
import time

HITS: list[dict] = []
_LOCK = threading.Lock()


def record(kind: str, detail: str) -> None:
    with _LOCK:
        HITS.append({"kind": kind, "detail": detail, "t": round(time.time(), 3)})
    print(f"  EGRESS OBSERVED [{kind}] {detail[:110]}", flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def _log_and_ok(self, verb: str) -> None:
        body = b"x"
        record("http", f"{verb} {self.path}")
        self.send_response(200)
        # Permissive CORS so a CORS failure can never be mistaken for the reason a
        # request did or did not arrive. CORS gates reading the RESPONSE, not sending
        # the REQUEST, and is not an egress control.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "image/gif")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._log_and_ok("GET")

    def do_POST(self) -> None:
        self._log_and_ok("POST")

    def do_PUT(self) -> None:
        self._log_and_ok("PUT")

    def log_message(self, *_a) -> None:
        pass


def udp_listener(port: int, stop: threading.Event) -> None:
    """Catch STUN (and anything else) on the same port number, over UDP.

    A STUN binding request carries the 0x2112A442 magic cookie at offset 4, which is
    enough to label it rather than report a bare datagram.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.settimeout(0.5)
    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(4096)
        except (TimeoutError, socket.timeout):
            continue
        except OSError:
            break
        label = "stun" if len(data) >= 8 and data[4:8] == b"\x21\x12\xa4\x42" else "udp"
        record(label, f"{len(data)} bytes from {addr[0]}:{addr[1]}")
    sock.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8973)
    ap.add_argument("--seconds", type=float, default=120)
    ap.add_argument("--dump", default=None, help="write observed hits as JSON on exit")
    args = ap.parse_args()

    stop = threading.Event()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as httpd:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        threading.Thread(target=udp_listener, args=(args.port, stop), daemon=True).start()
        print(f"listening on 127.0.0.1:{args.port} (tcp+udp)", flush=True)
        try:
            time.sleep(args.seconds)
        except KeyboardInterrupt:
            pass
        stop.set()
    if args.dump:
        with open(args.dump, "w") as fh:
            json.dump(HITS, fh, indent=1)
    print(f"total hits: {len(HITS)}", flush=True)


if __name__ == "__main__":
    main()
