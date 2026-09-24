"""Playing, recording and replaying runs of a game of the workspace."""

import logging

from hftas.eternaldev import Eternaldev, EternaldevError
from hftas.games import Game
from hftas.presets import RunConfig
from hftas.recording import Recording, mirror
from hftas.ruffle import Launch, Launcher

log = logging.getLogger("hftas")


class Tas:
    def __init__(self, eternaldev: Eternaldev, game: Game, launcher: Launcher, mirror_port: int):
        self.eternaldev = eternaldev
        self.game = game
        self.launcher = launcher
        self.mirror_port = mirror_port

    def play(self, config: RunConfig, tas: bool = True) -> int:
        """Plays a new run straight from eternaldev."""
        run = self._create_run(config)
        return self.launcher.launch(Launch(self.eternaldev.base_url, run, tas))

    def record(self, config: RunConfig, recording: Recording, tas: bool = True) -> int:
        """Plays a new run through a mirror saving every response, for identical replays."""
        run = self._create_run(config)
        recording.start(run)
        with mirror(recording, self.mirror_port, upstream=self.eternaldev.base_url) as url:
            return self.launcher.launch(Launch(url, run, tas))

    def replay(self, recording: Recording, tas: bool = True) -> int:
        """Replays a recorded run: same run, same responses, no eternaldev needed."""
        run = recording.run()
        log.info("Replaying run %s (%s: %s)", run["id"], run["game_mode"], ", ".join(run["game_options"]) or "no option")
        with mirror(recording, self.mirror_port) as url:
            return self.launcher.launch(Launch(url, run, tas))

    def options(self, mode: str) -> list[str]:
        modes = self.eternaldev.modes(self._game_id())
        if mode not in modes:
            raise EternaldevError(f"Unknown mode {mode!r} (available: {', '.join(modes)})")
        return modes[mode]

    def _create_run(self, config: RunConfig) -> dict:
        if not self.game.is_built():
            raise EternaldevError(f"{self.game.name} is not built: run `hftas build -g {self.game.name}`")
        run = self.eternaldev.create_run(self._game_id(), config)
        log.info(
            "%s run %s: %s (%s), profile %s",
            self.game.name, run["id"], config.mode, ", ".join(config.options) or "no option", config.profile,
        )
        return run

    def _game_id(self) -> str:
        projects = self.eternaldev.projects()
        if (game_id := projects.get(self.game.dir.resolve())) is not None:
            return game_id
        raise EternaldevError(
            f"eternaldev on {self.eternaldev.base_url} does not serve {self.game.name} "
            "(started before the game was added?): restart it with `hftas serve`"
        )
