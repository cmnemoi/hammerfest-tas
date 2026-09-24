# Hammerfest TAS

Make TAS of [Eternalfest](https://eternalfest.net/) contrées with [libTAS](https://github.com/clementgallet/libTAS).

## Requirements

- Linux
- [distrobox](https://distrobox.it) with [Podman](https://podman.io) or [Docker](https://www.docker.com)
- [mise](https://mise.jdx.dev)

## Install

```sh
git clone https://github.com/cmnemoi/hammerfest-tas.git
distrobox assemble create --file distrobox.ini
distrobox enter hammerfest-tas
mise install && mise run setup
```

## Play

In one terminal, start the Eternaldev server:

```sh
hftas serve
```

In another, launch a run:

```sh
hftas run speedrun-no-rng
```

The first time, this records a new run in `recordings/`. After that, the same command
replays that run, and that replay is what you TAS on.

`hftas run speedrun-no-rng --new` records a new run in its place.

## libTAS settings

Set these once in the libTAS window, which remembers them:

- Frames per second: 40
- Runtime → Time tracking: `clock_gettime()` monotonic

## Presets

A preset is a set of options, defined in `presets/<contrée>.toml`. `hftas run` without a
preset uses the contrée's defaults. For Hammerfest Deluxe:

| Preset | Options |
| --- | --- |
| `speedrun-no-rng` | Cauchemar, Tornade, Pas d'objets d'aide |
| `speedrun-rng` | Cauchemar, Tornade |
| `pap-no-rng` | Tornade, Intuition, Pas d'objets d'aide |
| `pap-rng` | Tornade, Intuition |
| `sandbox` | Cauchemar, Tornade, Intuition |

`hftas status` lists the presets and options of every contrée. Add or remove an option with
`-o` / `-x`: `hftas run sandbox -o ninja -x insight`.

## Contrées

The contrées are in `games/`. `hftas run` plays `HFTAS_GAME` (set in `mise.toml`). Use `-g`
to play another one:

```sh
hftas run -g derniers-ordres
```

## Add a contrée

```sh
git submodule add https://gitlab.com/eternalfest/games/<name>.git games/<name>
hftas build -g <name>
```

Then restart `hftas serve`. Presets are optional: see `presets/hammerfest-deluxe.toml`.

## Tests

```sh
mise run test
```

## License

[Apache 2.0](LICENSE)
