"""The Eternalfest games of the workspace: games/<name> (git submodules), each with its own
presets (presets/<name>.toml) and recordings (recordings/<name>/)."""

import json
import os
import shutil
import subprocess
import tomllib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

GAME_ENV = "HFTAS_GAME"
# eternaldev serves every project of this list, read once at startup (max 20 entries)
RECENT_PROJECTS = Path.home() / ".config" / "eternalfest" / "recent-projects.json"
MAX_RECENT_PROJECTS = 20


class GameError(Exception):
    pass


@dataclass(frozen=True)
class Game:
    name: str
    dir: Path
    presets_file: Path
    recordings_dir: Path

    def is_built(self) -> bool:
        """Whether the content eternaldev serves was built (`hftas build`)."""
        manifest = tomllib.loads((self.dir / "eternalfest.toml").read_text())
        content = manifest.get("content", {}).get("build")
        return content is not None and (self.dir / content).exists()

    def install(self, update_checksums: bool = False) -> None:
        # The Eternalfest registry republished some archives: older lockfiles no longer match them
        env = {"YARN_CHECKSUM_BEHAVIOR": "update"} if update_checksums else {}
        try:
            self._yarn("install", env=env)
        except GameError as error:
            raise GameError(
                f"{error}. On \"remote archive doesn't match the expected checksum\" errors, check the archives "
                f"were republished, then retry with `hftas setup -g {self.name} --update-checksums`"
            ) from None

    def build(self) -> None:
        self._yarn("run", "build")

    def serve(self) -> int:
        """Runs eternaldev from this game until interrupted."""
        return self._yarn("eternalfest", "start", check=False)

    def _yarn(self, *args: str, check: bool = True, env: dict[str, str] | None = None) -> int:
        yarn = shutil.which("yarn")
        if yarn is None:
            raise GameError("yarn not found: run hftas through mise (inside the hammerfest-tas distrobox)")
        code = subprocess.run([yarn, *args], cwd=self.dir, env={**os.environ, **(env or {})}).returncode
        if check and code != 0:
            raise GameError(f"`yarn {' '.join(args)}` failed in {self.dir} (exit code {code})")
        return code


def _is_deleted(project: str) -> bool:
    """Whether a local project was moved or deleted: eternaldev then fails on it at every start."""
    url = urllib.parse.urlparse(project)
    return url.scheme == "file" and not Path(urllib.request.url2pathname(url.path)).exists()


class Workspace:
    def __init__(self, root: Path, recent_projects: Path = RECENT_PROJECTS):
        self.root = root
        self.recent_projects = recent_projects

    def serve(self) -> int:
        """Runs one eternaldev serving every game, until interrupted."""
        games = self.games()
        if not games:
            raise GameError(f"No game in {self.root / 'games'}")
        self.register_games()
        # eternaldev serves every registered game whichever it starts from: prefer the default one
        try:
            start_from = self.game()
        except GameError:
            start_from = games[0]
        return start_from.serve()

    def register_games(self) -> None:
        """Adds every game to the projects eternaldev serves, as `eternalfest start` does for its own."""
        try:
            data = json.loads(self.recent_projects.read_text())
        except FileNotFoundError:
            data = {}
        # eternaldev still reads its former format: a list of paths
        projects = [Path(path).as_uri() for path in data] if isinstance(data, list) else data.get("projects", [])
        ours = [game.dir.resolve().as_uri() for game in self.games()]
        others = [project for project in projects if project not in ours and not _is_deleted(project)]
        projects = [*ours, *others][:MAX_RECENT_PROJECTS]
        self.recent_projects.parent.mkdir(parents=True, exist_ok=True)
        self.recent_projects.write_text(json.dumps({"projects": projects}, indent=2))

    def games(self) -> list[Game]:
        games_dir = self.root / "games"
        if not games_dir.is_dir():
            return []
        return [
            Game(path.name, path, self.root / "presets" / f"{path.name}.toml", self.root / "recordings" / path.name)
            for path in sorted(games_dir.iterdir())
            if (path / "eternalfest.toml").exists()
        ]

    def game(self, name: str | None = None) -> Game:
        """The named game, else $HFTAS_GAME, else the only game of the workspace."""
        games = {game.name: game for game in self.games()}
        name = name or os.environ.get(GAME_ENV) or None
        if not games:
            raise GameError(
                f"No game in {self.root / 'games'}: add one with "
                "`git submodule add https://gitlab.com/eternalfest/games/<name>.git games/<name>`"
            )
        if name is None:
            if len(games) > 1:
                raise GameError(f"Several games: pick one with -g/--game or ${GAME_ENV} ({', '.join(games)})")
            return next(iter(games.values()))
        if name not in games:
            raise GameError(f"Unknown game {name!r} (available: {', '.join(games)})")
        return games[name]

    def by_dir(self, directory: Path) -> Game | None:
        return next((game for game in self.games() if game.dir.resolve() == directory.resolve()), None)
