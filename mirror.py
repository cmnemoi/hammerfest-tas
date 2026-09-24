"""Local HTTP mirror of eternalfest.net, so the game loads identically on every launch.

  mirror.py record DIR PORT   forward requests to eternalfest.net and save the responses in DIR
  mirror.py replay DIR PORT   serve only the responses saved in DIR, never touching the network

Responses are keyed by method + path. Request headers (cookie included) are never saved.
"""

import hashlib
import http.server
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

UPSTREAM = "https://eternalfest.net"
# Hop-by-hop or recomputed headers, never forwarded as-is
SKIPPED_REQUEST_HEADERS = {"host", "accept-encoding", "connection", "content-length"}
SKIPPED_RESPONSE_HEADERS = {"transfer-encoding", "connection", "content-encoding", "content-length", "date", "server"}


def log(message: str) -> None:
    print(f"[mirror] {message}", file=sys.stderr, flush=True)


class Mirror:
    def __init__(self, directory: Path):
        self.directory = directory

    def _entry(self, method: str, path: str) -> Path:
        key = hashlib.sha256(f"{method} {path}".encode()).hexdigest()[:16]
        return self.directory / "responses" / key

    def load(self, method: str, path: str) -> tuple[int, dict, bytes] | None:
        entry = self._entry(method, path)
        if not entry.with_suffix(".json").exists():
            return None
        meta = json.loads(entry.with_suffix(".json").read_text())
        return meta["status"], meta["headers"], entry.with_suffix(".body").read_bytes()

    def save(self, method: str, path: str, status: int, headers: dict, body: bytes) -> None:
        entry = self._entry(method, path)
        entry.parent.mkdir(parents=True, exist_ok=True)
        if entry.with_suffix(".body").exists() and entry.with_suffix(".body").read_bytes() != body:
            log(f"WARN {method} {path} answered differently than last time: overwriting")
        entry.with_suffix(".body").write_bytes(body)
        meta = {"method": method, "path": path, "status": status, "headers": headers}
        entry.with_suffix(".json").write_text(json.dumps(meta, indent=2))


def make_handler(mirror: Mirror, record: bool):
    class Handler(http.server.BaseHTTPRequestHandler):
        def _handle(self):
            request_body = self.rfile.read(int(self.headers.get("Content-Length") or 0)) or None
            if record:
                status, headers, body = self._forward(request_body)
                mirror.save(self.command, self.path, status, headers, body)
                log(f"{self.command} {self.path} -> {status} ({len(body)} B, saved)")
            else:
                saved = mirror.load(self.command, self.path)
                if saved is None:
                    log(f"ERROR {self.command} {self.path} was never recorded -> 404")
                    status, headers, body = 404, {}, b""
                else:
                    status, headers, body = saved
                    log(f"{self.command} {self.path} -> {status} ({len(body)} B, replayed)")
            self._respond(status, headers, body)

        def _forward(self, request_body: bytes | None) -> tuple[int, dict, bytes]:
            headers = {k: v for k, v in self.headers.items() if k.lower() not in SKIPPED_REQUEST_HEADERS}
            request = urllib.request.Request(UPSTREAM + self.path, request_body, headers, method=self.command)
            try:
                response = urllib.request.urlopen(request)
            except urllib.error.HTTPError as error:
                response = error
            kept = {k: v for k, v in response.headers.items() if k.lower() not in SKIPPED_RESPONSE_HEADERS}
            return response.status, kept, response.read()

        def _respond(self, status: int, headers: dict, body: bytes) -> None:
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

        def log_message(self, *args):
            pass  # replaced by our own one-line logs

    return Handler


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[1] not in ("record", "replay"):
        sys.exit(__doc__)
    mode, directory, port = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
    handler = make_handler(Mirror(directory), record=(mode == "record"))
    log(f"{mode} mode on http://127.0.0.1:{port} ({directory})")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()


if __name__ == "__main__":
    main()
