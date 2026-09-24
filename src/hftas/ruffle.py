"""Launching the Eternalfest loader in Ruffle, directly or under libTAS."""

import json
import logging
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

log = logging.getLogger("hftas.ruffle")


class LaunchError(Exception):
    pass


@dataclass(frozen=True)
class Launch:
    """What the loader needs: the server it is loaded from and the run to play."""

    base_url: str
    run: dict
    tas: bool = True

    @property
    def swf_url(self) -> str:
        return f"{self.base_url}/assets/loader.swf"

    @property
    def params(self) -> dict[str, str]:
        """FlashVars Eternalfest gives the loader."""
        run = self.run
        options = {
            "mode": run["game_mode"],
            "options": run["game_options"],
            "settings": {**run["settings"], "volume": 100},
            "locale": run["settings"]["locale"],
        }
        return {
            "object_id": "swf1234",
            "run": json.dumps(run, separators=(",", ":")),
            "game": run["game"]["id"],
            "options": json.dumps(options, separators=(",", ":")),
        }

    @property
    def start_time(self) -> int:
        """Clock libTAS gives the game: the run's creation, so it never changes between replays."""
        return int(datetime.fromisoformat(self.run["created_at"]).timestamp())


class Launcher(Protocol):
    def launch(self, launch: Launch) -> int: ...


def ruffle_args(launch: Launch) -> list[str]:
    args = [
        "--base", f"{launch.base_url}/",
        "--spoof-url", launch.swf_url,
        "--referer", f"{launch.base_url}/runs/{launch.run['id']}",
        "--dummy-external-interface",
    ]
    for key, value in launch.params.items():
        args += ["-P", f"{key}={value}"]
    if launch.tas:
        # - blocking loads: network latency no longer shifts frames, so movies stay in sync
        # - gl backend: lets libTAS force software rendering (needed for savestates)
        # - no GUI: the menu bar would eat inputs and change the window size
        args += ["--load-behavior", "blocking", "--graphics", "gl", "--no-gui"]
    return args + [launch.swf_url]


def libtas_command(libtas: str, ruffle_path: str, launch: Launch) -> list[str]:
    # libTAS joins the game args into one string run through `sh -c`: quote each one,
    # otherwise the spaces and quotes in the JSON params split the command
    game_args = [shlex.quote(arg) for arg in ruffle_args(launch)]
    # libTAS preloads itself into the real binary: pass Ruffle's absolute path, never a wrapper
    return [libtas, "--system-time-sec", str(launch.start_time), ruffle_path, *game_args]


class RuffleLauncher:
    def __init__(self, ruffle: str = "ruffle", libtas: str = "libTAS"):
        self.ruffle = ruffle
        self.libtas = libtas

    def launch(self, launch: Launch) -> int:
        ruffle_path = self._which(self.ruffle)
        env = {"RUST_LOG": "warn,ruffle=info,avm_trace=info", **os.environ}
        if launch.tas:
            command = libtas_command(self._which(self.libtas), ruffle_path, launch)
            # libTAS is X11-only: hide Wayland so Ruffle falls back to XWayland
            env.pop("WAYLAND_DISPLAY", None)
            log.info("Launching Ruffle under libTAS (clock: %s)", datetime.fromtimestamp(launch.start_time).isoformat())
        else:
            command = [ruffle_path, *ruffle_args(launch)]
            log.info("Launching Ruffle on %s", launch.swf_url)
        return subprocess.run(command, env=env).returncode

    @staticmethod
    def _which(command: str) -> str:
        path = shutil.which(command)
        if path is None:
            raise LaunchError(f"Command not found: {command} (are you inside the hammerfest-tas distrobox?)")
        return path
