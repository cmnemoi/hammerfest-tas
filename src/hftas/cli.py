"""hftas: play, record and replay local Eternalfest games under libTAS.

Games are git submodules in games/<name>; -g picks one (default: $HFTAS_GAME, else the only game).
From the host, hftas runs itself inside the hammerfest-tas distrobox.

  hftas games                            list the games of the workspace
  hftas setup                            install and build every game
  hftas serve                            serve every game with eternaldev (own terminal)
  hftas status                           is eternaldev running, which games does it serve
  hftas presets                          list the run presets (presets/<game>.toml)
  hftas options                          list the options of the mode
  hftas play speedrun-no-rng             play a new run under libTAS, straight from eternaldev
  hftas play sandbox -o ninja -x insight   ... with an extra option, without another
  hftas play sandbox --ruffle-only       ... in Ruffle alone, to test something
  hftas record pap-rng                   play a new run and record it in recordings/<game>/pap-rng
  hftas replay pap-rng                   replay it identically, without eternaldev
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


def _recording(args, name: str | None) -> Recording:
    return Recording(args.dir or _game(args).recordings_dir / (name or "custom"))


def cmd_games(args) -> int:
    for game in args.workspace.games():
        presets = load_presets(game.presets_file)[1]
        print(f"{game.name:24} {'built' if game.is_built() else 'not built':10} {len(presets)} preset(s)")
    return 0


def cmd_setup(args) -> int:
    games = [_game(args)] if args.game else args.workspace.games()
    for game in games:
        log.info("Installing and building %s", game.name)
        game.install(update_checksums=args.update_checksums)
        game.build()
    return 0


def cmd_build(args) -> int:
    _game(args).build()
    return 0


def cmd_serve(args) -> int:
    return args.workspace.serve()


def cmd_status(args) -> int:
    try:
        projects = Eternaldev(args.server).projects()
    except EternaldevError:
        print(f"eternaldev: not running on {args.server} (start it with `hftas serve`)")
        return 1
    print(f"eternaldev: running on {args.server}")
    for game in args.workspace.games():
        state = "served" if game.dir.resolve() in projects else "not served (restart `hftas serve`)"
        print(f"  {game.name:24} {state}{'' if game.is_built() else ', not built (`hftas build`)'}")
    return 0


def cmd_presets(args) -> int:
    _, presets = load_presets(_game(args).presets_file)
    for name, config in presets.items():
        print(f"{name:20} {config.mode:8} {config.profile:8} {', '.join(config.options) or '-'}")
    return 0


def cmd_options(args) -> int:
    mode = args.mode or load_presets(_game(args).presets_file)[0].mode
    for option in _tas(args).options(mode):
        print(option)
    return 0


def cmd_play(args) -> int:
    return _tas(args).play(_config(args), args.tas)


def cmd_record(args) -> int:
    return _tas(args).record(_config(args), _recording(args, args.name or args.preset), args.tas)


def cmd_replay(args) -> int:
    return _tas(args).replay(_recording(args, args.name), args.tas)


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

    command("games", cmd_games, "list the games of the workspace")
    command("setup", cmd_setup, "install and build every game (or -g one)").add_argument(
        "--update-checksums", action="store_true",
        help="accept the registry's archives when they no longer match the lockfile checksums (rewrites yarn.lock)",
    )
    command("build", cmd_build, "build a game, after changing it")
    command("serve", cmd_serve, "serve every game with eternaldev until Ctrl+C")
    command("status", cmd_status, "tell whether eternaldev is running and which games it serves")
    command("presets", cmd_presets, "list the run presets of a game")
    command("options", cmd_options, "list the options of a mode").add_argument("--mode", help="default: from the presets")

    for name, function, help in [
        ("play", cmd_play, "play a new run straight from eternaldev"),
        ("record", cmd_record, "play a new run and record it for replays"),
    ]:
        sub = command(name, function, help)
        sub.add_argument("preset", nargs="?", help="preset from presets/<game>.toml (default: its [defaults])")
        sub.add_argument("-o", "--option", action="append", default=[], help="add an option (repeatable)")
        sub.add_argument("-x", "--without", action="append", default=[], help="remove an option of the preset (repeatable)")
        sub.add_argument("--mode", help="game mode (default: from the preset)")
        sub.add_argument("--profile", help="eternaldev profile giving the families (default: from the preset)")
        sub.add_argument("--ruffle-only", dest="tas", action="store_false", help=RUFFLE_ONLY_HELP)
        if name == "record":
            sub.add_argument("--name", help="recording name (default: the preset)")
            sub.add_argument("--dir", type=Path, help="recording directory (default: recordings/<game>/NAME)")

    replay = command("replay", cmd_replay, "replay a recorded run, without eternaldev")
    replay.add_argument("name", nargs="?", help="recording name (recordings/<game>/NAME)")
    replay.add_argument("--dir", type=Path, help="recording directory, e.g. an older mirror/")
    replay.add_argument("--ruffle-only", dest="tas", action="store_false", help=RUFFLE_ONLY_HELP)
    return parser


if __name__ == "__main__":
    sys.exit(main())
