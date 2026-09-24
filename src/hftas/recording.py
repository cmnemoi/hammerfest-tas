"""Recordings of a run and every server response, replayable without eternaldev.

A recording directory holds run.json and responses/<key>.{json,body}, keyed by method + path
(same layout as the former mirror.py, so older recordings still replay).
"""

import hashlib
import http.server
import json
import logging
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

log = logging.getLogger("hftas.mirror")

# Hop-by-hop or recomputed headers, never forwarded as-is
SKIPPED_REQUEST_HEADERS = {"host", "accept-encoding", "connection", "content-length"}
SKIPPED_RESPONSE_HEADERS = {"transfer-encoding", "connection", "content-encoding", "content-length", "date", "server"}


class RecordingError(Exception):
    pass


class Recording:
    def __init__(self, directory: Path):
        self.directory = directory

    @property
    def run_file(self) -> Path:
        return self.directory / "run.json"

    def start(self, run: dict) -> None:
        """Starts a new recording: responses of the previous run are dropped."""
        if self.directory.exists():
            for entry in (self.directory / "responses").glob("*"):
                entry.unlink()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.run_file.write_text(json.dumps(run, indent=2) + "\n")

    def run(self) -> dict:
        if not self.run_file.exists():
            raise RecordingError(f"No recorded run in {self.directory}: record one first (`hftas record`)")
        return json.loads(self.run_file.read_text())

    def load(self, method: str, path: str) -> tuple[int, dict, bytes] | None:
        entry = self._entry(method, path)
        if not entry.with_suffix(".json").exists():
            return None
        meta = json.loads(entry.with_suffix(".json").read_text())
        return meta["status"], meta["headers"], entry.with_suffix(".body").read_bytes()

    def save(self, method: str, path: str, status: int, headers: dict, body: bytes) -> None:
        entry = self._entry(method, path)
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.with_suffix(".body").write_bytes(body)
        meta = {"method": method, "path": path, "status": status, "headers": headers}
        entry.with_suffix(".json").write_text(json.dumps(meta, indent=2))

    def _entry(self, method: str, path: str) -> Path:
        key = hashlib.sha256(f"{method} {path}".encode()).hexdigest()[:16]
        return self.directory / "responses" / key


@contextmanager
def mirror(recording: Recording, port: int, upstream: str | None = None) -> Iterator[str]:
    """Serves the recording on 127.0.0.1:port and yields its URL.

    With an upstream, requests are forwarded to it and saved; without, only saved responses are served.
    """
    handler = _make_handler(recording, upstream)
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as error:
        raise RecordingError(f"Cannot listen on port {port} ({error.strerror}): pick another with --port") from None
    url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    log.info("%s %s on %s", "Recording" if upstream else "Replaying", recording.directory, url)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


def _make_handler(recording: Recording, upstream: str | None):
    class Handler(http.server.BaseHTTPRequestHandler):
        def _handle(self):
            request_body = self.rfile.read(int(self.headers.get("Content-Length") or 0)) or None
            if upstream is not None:
                status, headers, body = self._forward(request_body)
                recording.save(self.command, self.path, status, headers, body)
                log.info("%s %s -> %s (%d B, saved)", self.command, self.path, status, len(body))
            elif (saved := recording.load(self.command, self.path)) is not None:
                status, headers, body = saved
                log.info("%s %s -> %s (%d B, replayed)", self.command, self.path, status, len(body))
            else:
                log.error("%s %s was never recorded -> 404", self.command, self.path)
                status, headers, body = 404, {}, b""
            self._respond(status, headers, body)

        def _forward(self, request_body: bytes | None) -> tuple[int, dict, bytes]:
            headers = {k: v for k, v in self.headers.items() if k.lower() not in SKIPPED_REQUEST_HEADERS}
            request = urllib.request.Request(upstream + self.path, request_body, headers, method=self.command)
            try:
                response = urllib.request.urlopen(request)
            except urllib.error.HTTPError as error:
                response = error
            except urllib.error.URLError as error:
                log.error("%s %s: upstream %s unreachable (%s) -> 502", self.command, self.path, upstream, error.reason)
                return 502, {}, b""
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
