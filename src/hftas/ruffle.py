"""Launching the Eternalfest loader in Ruffle, directly or under libTAS."""

import json
import logging
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

log = logging.getLogger("hftas.ruffle")

# Ruffle preferences for TAS launches, instead of the user's own
TAS_CONFIG_DIR = Path(__file__).with_name("ruffle-config")


class LaunchError(Exception):
    pass


@dataclass(frozen=True)
class Launch:
    """What the loader needs: the server it is loaded from and the run to play."""

    base_url: str
    run: dict
    tas: bool = True
    # Shifts the clock libTAS gives the game, which seeds its randomness (Ruffle reads it to the microsecond)
    clock_offset_us: int = 0

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

    @property
    def clock(self) -> tuple[int, int]:
        """Seconds and nanoseconds libTAS starts the game's clock at: the start time plus the offset."""
        seconds, microseconds = divmod(self.clock_offset_us, 1_000_000)
        return self.start_time + seconds, microseconds * 1_000


class Launcher(Protocol):
    def launch(self, launch: Launch) -> int: ...


def ruffle_args(launch: Launch, encode: bool = False) -> list[str]:
    args = [
        "--base", f"{launch.base_url}/",
        "--spoof-url", launch.swf_url,
        "--referer", f"{launch.base_url}/runs/{launch.run['id']}",
        "--dummy-external-interface",
    ]
    for key, value in launch.params.items():
        args += ["-P", f"{key}={value}"]
    if launch.tas:
        # - blocking loads: a loaded SWF is parsed in one go, not in slices sized by real time
        #   (its download still completes on other threads: leave a margin before the first input)
        # - gl backend: lets libTAS force software rendering (needed for savestates)
        #   but libTAS then dumps 1x1 videos: encoding replays use vulkan instead
        # - no GUI: the menu bar would eat inputs and change the window size
        # - own config: no OpenH264 download, whose duration shifts every load
        graphics = "vulkan" if encode else "gl"
        args += ["--load-behavior", "blocking", "--graphics", graphics, "--no-gui", "--config", str(TAS_CONFIG_DIR)]
    return args + [launch.swf_url]


def libtas_command(libtas: str, ruffle_path: str, launch: Launch, encode: bool = False) -> list[str]:
    # libTAS joins the game args into one string run through `sh -c`: quote each one,
    # otherwise the spaces and quotes in the JSON params split the command
    game_args = [shlex.quote(arg) for arg in ruffle_args(launch, encode)]
    # libTAS preloads itself into the real binary: pass Ruffle's absolute path, never a wrapper
    seconds, nanoseconds = launch.clock
    clock = ["--system-time-sec", str(seconds)]
    if nanoseconds:
        clock += ["--system-time-nsec", str(nanoseconds)]
    return [libtas, *clock, ruffle_path, *game_args]


class RuffleLauncher:
    def __init__(self, ruffle: str = "ruffle", libtas: str = "libTAS", encode: bool = False):
        self.ruffle = ruffle
        self.libtas = libtas
        self.encode = encode

    def launch(self, launch: Launch) -> int:
        ruffle_path = self._which(self.ruffle)
        env = {"RUST_LOG": "warn,ruffle=info,avm_trace=info", **os.environ}
        if launch.tas:
            command = libtas_command(self._which(self.libtas), ruffle_path, launch, self.encode)
            # libTAS is X11-only: hide Wayland so Ruffle falls back to XWayland
            env.pop("WAYLAND_DISPLAY", None)
            # Qt still picks Wayland from XDG_SESSION_TYPE (connecting to wayland-0 by default),
            # and the libTAS input editor then stops repainting: force its GUI on X11 too
            env["QT_QPA_PLATFORM"] = "xcb"
            seconds, nanoseconds = launch.clock
            clock = datetime.fromtimestamp(seconds + nanoseconds / 1e9).isoformat(timespec="microseconds")
            log.info("Launching Ruffle under libTAS (clock: %s, offset %d µs)", clock, launch.clock_offset_us)
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
