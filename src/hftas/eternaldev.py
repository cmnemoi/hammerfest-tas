"""Client for the eternaldev server (`hftas serve`) serving one game of the workspace."""

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from hftas.presets import LOCALE, RunConfig

DEFAULT_URL = "http://localhost:50317"
# eternaldev has a single built-in user
USER_ID = "00000000-0000-0000-0000-000000000000"


class EternaldevError(Exception):
    pass


class Eternaldev:
    def __init__(self, base_url: str = DEFAULT_URL):
        self.base_url = base_url.rstrip("/")

    def projects(self) -> dict[Path, str]:
        """Returns the id eternaldev derived from the path of each project it serves."""
        return {
            Path(urllib.request.url2pathname(urllib.parse.urlparse(project["local_url"]).path)): project["id"]
            for project in self._request("GET", "/api/v1/projects")
        }

    def modes(self, game_id: str) -> dict[str, list[str]]:
        """Returns the option ids of every mode of the game."""
        game = self._request("GET", f"/api/v1/games/{game_id}")
        modes = game["channels"]["active"]["build"]["modes"]
        return {mode: list(spec["options"]) for mode, spec in modes.items()}

    def profiles(self, game_id: str) -> list[str]:
        """Returns the profiles of game/eternalfest.toml, plus the built-in "default"."""
        project = self._request("GET", f"/api/v1/projects/{game_id}")
        return ["default", *project.get("profiles", {})]

    def create_run(self, game_id: str, config: RunConfig) -> dict:
        # eternaldev silently falls back to the default families on an unknown profile
        if config.profile not in (profiles := self.profiles(game_id)):
            raise EternaldevError(f"Unknown profile {config.profile!r} (available: {', '.join(profiles)})")
        modes = self.modes(game_id)
        if config.mode not in modes:
            raise EternaldevError(f"Unknown mode {config.mode!r} (available: {', '.join(modes)})")
        if unknown := [option for option in config.options if option not in modes[config.mode]]:
            raise EternaldevError(
                f"Unknown options for mode {config.mode!r}: {', '.join(unknown)} "
                f"(available: {', '.join(modes[config.mode])})"
            )
        return self._request("POST", "/api/v1/runs", {
            "game_id": game_id,
            "user_id": USER_ID,
            "channel": "main",
            "version": "0.0.0",
            "game_mode": config.mode,
            "game_options": list(config.options),
            "settings": config.settings.to_json(),
            "profile": config.profile,
            "locale": LOCALE,
        })

    def _request(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base_url + path, data, {"Content-Type": "application/json"}, method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise EternaldevError(f"{method} {path} -> HTTP {error.code}: {error.read().decode(errors='replace')}") from None
        except urllib.error.URLError as error:
            raise EternaldevError(
                f"eternaldev not reachable on {self.base_url} ({error.reason}): start it with `hftas serve`"
            ) from None
