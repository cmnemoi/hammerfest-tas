"""Fakes for the two boundaries of hftas: the eternaldev server and the loader running in Ruffle."""

import http.server
import json
import re
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from hftas.ruffle import Launch

DEFAULT_FAMILIES = "5015,0,7,13,15,18,1000,1028"
FULL_FAMILIES = "0,1,2,3,4,10,11,12,19,100,101,102,103,104,105,106,107,108,109,110,111,112,113,1000,5000,5015"
DELUXE_OPTIONS = ["mirror", "nightmare", "ninja", "bombexpert", "boost", "insight", "firstrun", "noeffect"]


class FakeEternaldev:
    """In-process HTTP server answering like eternaldev serving one project (started from game_dir)."""

    def __init__(self, game_dir: Path, modes: dict[str, list[str]]):
        self.game_id = str(uuid.uuid4())
        self.game_dir = game_dir
        self.modes = modes
        self.profiles = {"full": {"families": FULL_FAMILIES}}
        self.runs: dict[str, dict] = {}
        self._run_profiles: dict[str, str] = {}
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self._handler())

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> "FakeEternaldev":
        threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _route(self, method: str, path: str, body: dict | None) -> tuple[int, object]:
        if (method, path) == ("GET", "/assets/loader.swf"):
            return 200, b"FWS-loader"
        if (method, path) == ("GET", "/api/v1/projects"):
            return 200, [{"id": self.game_id, "local_url": self.game_dir.resolve().as_uri()}]
        if method == "GET" and path == f"/api/v1/projects/{self.game_id}":
            return 200, {"id": self.game_id, "profiles": self.profiles}
        if method == "GET" and path == f"/api/v1/games/{self.game_id}":
            modes = {mode: {"options": {option: {} for option in options}} for mode, options in self.modes.items()}
            build = {"display_name": self.game_dir.name, "modes": modes}
            return 200, {"id": self.game_id, "channels": {"active": {"build": build}}}
        if (method, path) == ("POST", "/api/v1/runs"):
            return self._create_run(body)
        if method == "POST" and (match := re.fullmatch(r"/api/v1/runs/([^/]+)/start", path)):
            run_id = match[1]
            if run_id not in self.runs:
                return 404, {"error": "RunNotFound"}
            profile = self.profiles.get(self._run_profiles[run_id], {})
            return 200, {"run": {"id": run_id}, "key": str(uuid.uuid4()), "families": profile.get("families", DEFAULT_FAMILIES), "items": {}}
        return 404, {"error": "ResourceNotFound"}

    def _create_run(self, body: dict) -> tuple[int, object]:
        # Same validation as eternaldev's $CreateDebugRunOptions (it does not check modes nor options)
        if len(body.get("user_id", "")) != 36 or body.get("game_id") != self.game_id:
            return 422, {"error": "InvalidRequest"}
        run = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "game": {"id": self.game_id},
            "build": {"display_name": "Les Cavernes de Hammerfest", "modes": {"deluxe": {"display_name": "Clones d'ombre"}}},
            "user": {"type": "User", "id": body["user_id"], "display_name": "Eternaldev"},
            "game_mode": body["game_mode"],
            "game_options": body["game_options"],
            "settings": body["settings"],
        }
        self.runs[run["id"]] = run
        self._run_profiles[run["id"]] = body.get("profile", "default")
        return 200, run

    def _handler(self):
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _handle(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                status, payload = fake._route(self.command, self.path, json.loads(raw) if raw else None)
                body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = _handle

            def log_message(self, *args):
                pass

        return Handler


@dataclass(frozen=True)
class GameSession:
    """What the game received once the loader started."""

    game: str
    run_id: str
    mode: str
    options: list[str]
    families: list[str]


@dataclass
class FakeLoader:
    """Stands in for Ruffle: makes the loader's requests against the server it is launched from."""

    sessions: list[GameSession] = field(default_factory=list)
    launches: list[Launch] = field(default_factory=list)

    def launch(self, launch: Launch) -> int:
        self.launches.append(launch)
        params = launch.params
        run = json.loads(params["run"])
        options = json.loads(params["options"])
        try:
            _fetch("GET", launch.swf_url)
            game = json.loads(_fetch("GET", f"{launch.base_url}/api/v1/games/{params['game']}"))
            start = json.loads(_fetch("POST", f"{launch.base_url}/api/v1/runs/{run['id']}/start", b"{}"))
        except urllib.error.HTTPError:
            return 1
        name = game["channels"]["active"]["build"]["display_name"]
        self.sessions.append(GameSession(name, run["id"], options["mode"], options["options"], start["families"].split(",")))
        return 0


def _fetch(method: str, url: str, data: bytes | None = None) -> bytes:
    request = urllib.request.Request(url, data, {"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.read()
