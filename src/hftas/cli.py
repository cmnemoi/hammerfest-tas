"""hftas: TAS local Eternalfest games under libTAS.

Games are git submodules in games/<name>; -g picks one (default: $HFTAS_GAME, else the only game).
From the host, hftas runs itself inside the hammerfest-tas distrobox.

  hftas serve                  serve every game with eternaldev (own terminal)
  hftas status                 eternaldev, games, their options, presets and recordings
  hftas run pap-rng            first time: new run of the preset, recorded in recordings/<game>/pap-rng
                               then: replays that same run, to TAS it (eternaldev not needed)
  hftas run pap-rng --new      record a new run in its place
  hftas run sandbox -o ninja -x insight   new run with an extra option, without another
  hftas build                  install and build every game (or -g one), after changing it
"""

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

from hftas.box import enter_box_if_needed
from hftas.eternaldev import DEFAULT_URL, Eternaldev, EternaldevError
from hftas.games import GAME_ENV, Game, GameError, Workspace
from hftas.presets import PresetError, RunConfig, load_presets
from hftas.recording import Recording, RecordingError
from hftas.ruffle import LaunchError, Launcher, RuffleLauncher
from hftas.tas import Tas

ROOT = Path(__file__).resolve().parents[2]
RUFFLE_ONLY_HELP = "launch Ruffle alone instead of under libTAS, to test something"
log = logging.getLogger("hftas")


def main(argv: list[str] | None = None, launcher: Launcher | None = None, workspace: Workspace | None = None) -> int:
    if argv is None:  # real command line, not a test
        enter_box_if_needed(ROOT, sys.argv[1:])
    args = _parser().parse_args(argv)
    args.launcher = launcher or RuffleLauncher()
    args.workspace = workspace or Workspace(ROOT)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s", datefmt="%H:%M:%S")
    try:
        return args.command(args)
    except (EternaldevError, GameError, PresetError, RecordingError, LaunchError) as error:
        log.error("%s", error)
        return 1
    except KeyboardInterrupt:
        return 130


def _game(args) -> Game:
    return args.workspace.game(args.game)


def _tas(args) -> Tas:
    return Tas(Eternaldev(args.server), _game(args), args.launcher, args.port)


def _config(args) -> RunConfig:
    defaults, presets = load_presets(_game(args).presets_file)
    if args.preset is None:
        config = defaults
    elif args.preset in presets:
        config = presets[args.preset]
    else:
        raise PresetError(f"Unknown preset {args.preset!r} for {_game(args).name} (available: {', '.join(presets) or 'none'})")
    config = config.with_options(args.option, args.without)
    if args.mode is not None:
        config = replace(config, mode=args.mode)
    if args.profile is not None:
        config = replace(config, profile=args.profile)
    return config


def _recording(args) -> Recording:
    return Recording(args.dir or _game(args).recordings_dir / (args.name or args.preset or "default"))


def _games(args) -> list[Game]:
    return [_game(args)] if args.game else args.workspace.games()


def cmd_run(args) -> int:
    recording = _recording(args)
    if recording.exists() and not args.new:
        if args.option or args.without or args.mode or args.profile:
            raise RecordingError(
                f"{recording.directory.name} is already recorded, so its options are fixed: "
                "drop them, or record a new run with --new"
            )
        return _tas(args).replay(recording, args.tas)
    return _tas(args).record(_config(args), recording, args.tas)


def cmd_build(args) -> int:
    for game in _games(args):
        log.info("Installing and building %s", game.name)
        game.install(update_checksums=args.update_checksums)
        game.build()
    return 0


def cmd_serve(args) -> int:
    return args.workspace.serve()


def cmd_status(args) -> int:
    eternaldev = Eternaldev(args.server)
    try:
        projects = eternaldev.projects()
        print(f"eternaldev: running on {args.server}")
    except EternaldevError:
        projects = None
        print(f"eternaldev: not running on {args.server} (start it with `hftas serve`)")
    for game in _games(args):
        game_id = projects.get(game.dir.resolve()) if projects is not None else None
        state = ["built" if game.is_built() else "not built (`hftas build`)"]
        if projects is not None:
            state.append("served" if game_id else "not served (restart `hftas serve`)")
        defaults, presets = load_presets(game.presets_file)
        print(f"\n{game.name}: {', '.join(state)}")
        if game_id is not None:
            print(f"  options ({defaults.mode}): {', '.join(eternaldev.modes(game_id).get(defaults.mode, [])) or '-'}")
        print("  presets:")
        for name, config in {"(default)": defaults, **presets}.items():
            print(f"    {name:20} {', '.join(config.options) or '-'}")
        recordings = sorted(d.name for d in game.recordings_dir.glob("*") if Recording(d).exists())
        print(f"  recordings: {', '.join(recordings) or '-'}")
    return 0 if projects is not None else 1


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-g", "--game", help=f"game of games/ (default: ${GAME_ENV}, else the only game)")
    common.add_argument("--server", default=DEFAULT_URL, help=f"eternaldev URL (default: {DEFAULT_URL})")
    common.add_argument("--port", type=int, default=8765, help="port of the record/replay mirror (default: 8765)")

    parser = argparse.ArgumentParser(prog="hftas", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(required=True, metavar="COMMAND")

    def command(name: str, function, help: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help, parents=[common])
        sub.set_defaults(command=function)
        return sub

    command("serve", cmd_serve, "serve every game with eternaldev until Ctrl+C")
    command("status", cmd_status, "show eternaldev, the games, their options, presets and recordings")
    command("build", cmd_build, "install and build every game (or -g one), after changing it").add_argument(
        "--update-checksums", action="store_true",
        help="accept the registry's archives when they no longer match the lockfile checksums (rewrites yarn.lock)",
    )

    run = command("run", cmd_run, "record a new run, or replay it once recorded")
    run.add_argument("preset", nargs="?", help="preset from presets/<game>.toml (default: its [defaults])")
    run.add_argument("--name", help="recording name (default: the preset)")
    run.add_argument("--new", action="store_true", help="record a new run even if one is recorded")
    run.add_argument("-o", "--option", action="append", default=[], help="add an option (repeatable, new runs only)")
    run.add_argument("-x", "--without", action="append", default=[], help="remove an option of the preset (repeatable, new runs only)")
    run.add_argument("--mode", help="game mode (default: from the preset, new runs only)")
    run.add_argument("--profile", help="eternaldev profile giving the families (default: from the preset, new runs only)")
    run.add_argument("--dir", type=Path, help="recording directory (default: recordings/<game>/NAME), e.g. an older mirror/")
    run.add_argument("--ruffle-only", dest="tas", action="store_false", help=RUFFLE_ONLY_HELP)
    return parser


if __name__ == "__main__":
    sys.exit(main())
