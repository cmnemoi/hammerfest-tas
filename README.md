# Hammerfest TAS

TAS of Eternalfest games, played locally: each game (`games/<name>`, git submodule) is built and
served by eternaldev, then launched in Ruffle under libTAS.

```
games/<name>/              the games (git submodules)
presets/<name>.toml        run presets of each game (optional)
recordings/<name>/<run>/   recorded runs, replayable without eternaldev
```

## Setup

```sh
distrobox assemble create --file distrobox.ini   # system deps, Ruffle, libTAS
distrobox enter hammerfest-tas
mise install && mise run setup                   # tools, submodules, hftas, game builds
```

## Usage

```sh
hftas serve                      # eternaldev serving every game (own terminal)
hftas status                     # is it running, which games does it serve

hftas games                      # games of the workspace
hftas presets                    # run presets of the game
hftas options                    # options of its mode
hftas play speedrun-no-rng       # play a new run under libTAS
hftas play sandbox -o ninja -x insight --profile default
hftas play sandbox --ruffle-only # in Ruffle alone, to test something
hftas record pap-rng             # play and record it in recordings/<game>/pap-rng
hftas replay pap-rng             # replay it identically, eternaldev not needed
hftas build                      # after changing a game, then record again
```

hftas works from the host too: it then runs itself inside the distrobox (`HFTAS_NO_BOX=1` to
run in place, e.g. with the dependencies installed on the host).

The default game is `HFTAS_GAME` in `mise.toml` (hammerfest-deluxe); pick another with
`-g <name>`. Click in the game to start the run.

## Adding a game

```sh
git submodule add https://gitlab.com/eternalfest/games/<name>.git games/<name>
hftas setup -g <name>            # install and build it
```

Optionally write `presets/<name>.toml` (see `presets/hammerfest-deluxe.toml`); without it, runs
play the solo mode as a new account. Restart `hftas serve` so eternaldev serves the new game.

## Tests

```sh
mise run test    # deep tests also run against the real eternaldev when `hftas serve` is up
```
