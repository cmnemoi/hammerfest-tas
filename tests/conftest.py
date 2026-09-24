import json
import shutil
from pathlib import Path

import pytest

from hftas.cli import main
from hftas.games import GAME_ENV, Workspace
from tests.fakes import DELUXE_OPTIONS, FakeEternaldev, FakeLoader, GameSession

REPO = Path(__file__).resolve().parents[1]
HAMMERFEST = "hammerfest-deluxe"


class TasWorld:
    """Test DSL: a workspace of built games, one of them served by a fake eternaldev, launched in a fake loader."""

    def __init__(self, root: Path):
        self.root = root
        self.workspace = Workspace(root, recent_projects=root / "eternalfest" / "recent-projects.json")
        self.loader = FakeLoader()
        self.port = 0
        self.eternaldev: FakeEternaldev | None = None
        self._modes: dict[str, dict[str, list[str]]] = {}
        # The real game with its real presets
        self.add_game(HAMMERFEST, modes={"deluxe": DELUXE_OPTIONS, "solo": ["mirror", "nightmare"]})
        shutil.copy(REPO / "presets" / f"{HAMMERFEST}.toml", root / "presets" / f"{HAMMERFEST}.toml")
        self.eternaldev_serves(HAMMERFEST)

    # --- Setup ---------------------------------------------------------------

    def add_game(self, name: str, modes: dict[str, list[str]]) -> None:
        game_dir = self.root / "games" / name
        (game_dir / "build").mkdir(parents=True)
        (game_dir / "eternalfest.toml").write_text('[content]\nbuild = "./build/game.xml"\n')
        (game_dir / "build" / "game.xml").write_text("<game/>")
        (self.root / "presets").mkdir(exist_ok=True)
        self._modes[name] = modes

    def eternaldev_serves(self, name: str) -> None:
        if self.eternaldev is not None:
            self.eternaldev.stop()
        self.eternaldev = FakeEternaldev(self.root / "games" / name, modes=self._modes[name]).start()

    def existing_project(self, name: str) -> str:
        (self.root / name).mkdir()
        return (self.root / name).as_uri()

    def eternaldev_knows_projects(self, projects: list[str]) -> None:
        self.workspace.recent_projects.parent.mkdir(parents=True, exist_ok=True)
        self.workspace.recent_projects.write_text(json.dumps({"projects": projects}))

    # --- Actions -------------------------------------------------------------

    def hftas(self, command: str, *args: str) -> int:
        return main(
            [command, *args, "--server", self.eternaldev.url, "--port", str(self.port)],
            launcher=self.loader,
            workspace=self.workspace,
        )

    def run(self, *args: str) -> int:
        return self.hftas("run", *args)

    def run_named(self, name: str, *args: str) -> int:
        return self.hftas("run", *args, "--name", name)

    # --- Situations ----------------------------------------------------------

    def eternaldev_goes_down(self) -> None:
        self.eternaldev.stop()

    def game_is_not_built(self, name: str = HAMMERFEST) -> None:
        (self.root / "games" / name / "build" / "game.xml").unlink()

    def recorded_response_is_lost(self, name: str, path: str, game: str = HAMMERFEST) -> None:
        for meta in (self.recording_dir(name, game) / "responses").glob("*.json"):
            if f'"path": "{path}"' in meta.read_text():
                meta.unlink()
                return
        raise AssertionError(f"{path} was not recorded")

    # --- Observations --------------------------------------------------------

    def eternaldev_projects(self) -> list[str]:
        return json.loads(self.workspace.recent_projects.read_text())["projects"]

    def recording_dir(self, name: str, game: str = HAMMERFEST) -> Path:
        return self.root / "recordings" / game / name

    @property
    def games_started(self) -> list[GameSession]:
        return self.loader.sessions

    @property
    def game(self) -> GameSession:
        assert self.loader.sessions, "no game was started"
        return self.loader.sessions[-1]


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.delenv(GAME_ENV, raising=False)
    world = TasWorld(tmp_path)
    yield world
    try:
        world.eternaldev.stop()
    except OSError:
        pass
