"""Run configurations: which mode, options, profile and settings a run starts with, and its clock."""

import tomllib
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

LOCALE = "fr-FR"


class PresetError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    detail: bool = True
    shake: bool = True
    sound: bool = True
    music: bool = False

    def to_json(self) -> dict:
        return {
            "detail": self.detail,
            "shake": self.shake,
            "sound": self.sound,
            "music": self.music,
            "volume": 100,
            "locale": LOCALE,
        }


@dataclass(frozen=True)
class RunConfig:
    mode: str
    options: tuple[str, ...]
    profile: str
    settings: Settings
    # Clock libTAS gives the game, which seeds its randomness (None: the run's creation time)
    clock: datetime | None = None

    def with_options(self, added: list[str], removed: list[str]) -> "RunConfig":
        unknown = [option for option in removed if option not in self.options and option not in added]
        if unknown:
            raise PresetError(f"Cannot remove {', '.join(unknown)}: not in {list(self.options)}")
        options = [option for option in self.options if option not in removed]
        options += [option for option in added if option not in options and option not in removed]
        return replace(self, options=tuple(options))


# What a game without presets file plays: every Eternalfest game has the solo mode and the
# built-in "default" profile (new account)
BASE_CONFIG = RunConfig(mode="solo", options=(), profile="default", settings=Settings())


def load_presets(path: Path) -> tuple[RunConfig, dict[str, RunConfig]]:
    """Returns the default config and the named presets of a game's presets file (optional)."""
    if not path.exists():
        return BASE_CONFIG, {}
    data = tomllib.loads(path.read_text())
    raw_defaults = data.get("defaults", {})
    defaults = _read_config(raw_defaults, base=None, where="[defaults]")
    presets = {
        name: _read_config(raw, base=defaults, where=f"[presets.{name}]")
        for name, raw in data.get("presets", {}).items()
    }
    return defaults, presets


def _read_config(raw: dict, base: RunConfig | None, where: str) -> RunConfig:
    known = {"mode", "options", "profile", "settings", "clock"}
    if extra := set(raw) - known:
        raise PresetError(f"{where}: unknown keys {sorted(extra)} (expected {sorted(known)})")
    base = base or BASE_CONFIG
    settings = base.settings
    if "settings" in raw:
        try:
            settings = replace(settings, **raw["settings"])
        except TypeError as error:
            raise PresetError(f"{where}.settings: {error}") from None
    options = raw.get("options", base.options)
    if not isinstance(options, (list, tuple)) or not all(isinstance(option, str) for option in options):
        raise PresetError(f"{where}: options must be a list of option ids")
    clock = raw.get("clock", base.clock)
    if clock is not None and not isinstance(clock, datetime):
        raise PresetError(f"{where}: clock must be a TOML date-time (2026-10-04T19:33:39.001Z), not {clock!r}")
    if clock is not None and clock.tzinfo is None:
        # a local time would give another seed on a computer in another time zone
        raise PresetError(f"{where}: clock {clock.isoformat()} needs a time zone (Z or +02:00)")
    return RunConfig(
        mode=raw.get("mode", base.mode),
        options=tuple(options),
        profile=raw.get("profile", base.profile),
        settings=settings,
        clock=clock,
    )
