"""Deep tests against the real eternaldev (`hftas serve`): every preset of the game it serves
must start. Skipped for the games it does not serve, and when it is down."""

import json
import urllib.request

import pytest

from hftas.cli import ROOT
from hftas.eternaldev import DEFAULT_URL, Eternaldev, EternaldevError
from hftas.games import Workspace
from hftas.presets import load_presets

pytestmark = pytest.mark.eternaldev

WORKSPACE = Workspace(ROOT)
PRESETS = [
    pytest.param(game, name, config, id=f"{game.name}:{name}")
    for game in WORKSPACE.games()
    for name, config in load_presets(game.presets_file)[1].items()
]


@pytest.fixture(scope="module")
def eternaldev():
    client = Eternaldev(DEFAULT_URL)
    try:
        return client, client.projects()
    except EternaldevError as error:
        pytest.skip(str(error))


@pytest.mark.parametrize("game, name, config", PRESETS)
def test_real_game_starts_every_preset_with_its_profile_families(eternaldev, game, name, config):
    client, projects = eternaldev
    if (game_id := projects.get(game.dir.resolve())) is None:
        pytest.skip(f"eternaldev does not serve {game.name}")

    run = client.create_run(game_id, config)
    start = _post(f"{client.base_url}/api/v1/runs/{run['id']}/start")

    assert run["game_options"] == list(config.options)
    profile = _get(f"{client.base_url}/api/v1/projects/{game_id}")["profiles"].get(config.profile)
    if profile is not None:
        assert start["families"] == profile["families"]


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def _post(url: str) -> dict:
    request = urllib.request.Request(url, b"{}", {"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)
