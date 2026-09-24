from hftas.games import GAME_ENV
from tests.conftest import HAMMERFEST

OTHER = "derniers-ordres"


def with_second_game(world, served: str = OTHER):
    world.add_game(OTHER, modes={"solo": ["mirror", "nightmare"]})
    world.eternaldev_serves(served)


def test_the_only_game_of_the_workspace_is_played_by_default(world):
    world.play("sandbox")

    assert world.game.game == HAMMERFEST


def test_with_several_games_the_game_must_be_picked(world, caplog):
    with_second_game(world)

    exit_code = world.play()

    assert exit_code == 1
    assert world.games_started == []
    assert f"pick one with -g/--game or ${GAME_ENV} ({OTHER}, {HAMMERFEST})" in caplog.text


def test_game_picked_with_g_is_played(world):
    with_second_game(world)

    world.play("-g", OTHER)

    assert world.game.game == OTHER


def test_game_picked_in_the_environment_is_played(world, monkeypatch):
    with_second_game(world)
    monkeypatch.setenv(GAME_ENV, OTHER)

    world.play()

    assert world.game.game == OTHER


def test_game_without_presets_plays_solo_as_a_new_account(world):
    with_second_game(world)

    world.play("-g", OTHER)

    assert (world.game.mode, world.game.options, world.game.families[0]) == ("solo", [], "5015")


def test_presets_belong_to_their_game(world, caplog):
    with_second_game(world)

    exit_code = world.play("speedrun-no-rng", "-g", OTHER)

    assert exit_code == 1
    assert f"Unknown preset 'speedrun-no-rng' for {OTHER} (available: none)" in caplog.text


def test_unknown_game_is_rejected_listing_the_games(world, caplog):
    exit_code = world.play("-g", "hammerfest")

    assert exit_code == 1
    assert f"Unknown game 'hammerfest' (available: {HAMMERFEST})" in caplog.text


def test_playing_a_game_eternaldev_does_not_serve_says_how_to_serve_it(world, caplog):
    with_second_game(world, served=HAMMERFEST)

    exit_code = world.play("-g", OTHER)

    assert exit_code == 1
    assert world.games_started == []
    assert f"does not serve {OTHER} (started before the game was added?): restart it with `hftas serve`" in caplog.text


def test_serving_registers_every_game_first_and_keeps_other_projects(world):
    with_second_game(world)
    other_project = world.existing_project("my-own-game")
    world.eternaldev_knows_projects([other_project, (world.root / "games" / OTHER).as_uri()])

    world.workspace.register_games()

    assert world.eternaldev_projects() == [
        (world.root / "games" / OTHER).as_uri(), (world.root / "games" / HAMMERFEST).as_uri(), other_project,
    ]


def test_serving_reads_the_former_eternaldev_projects_format(world):
    own_game = world.existing_project("my-own-game")
    world.workspace.recent_projects.parent.mkdir(parents=True)
    world.workspace.recent_projects.write_text(f'["{world.root / "my-own-game"}"]')

    world.workspace.register_games()

    assert world.eternaldev_projects() == [(world.root / "games" / HAMMERFEST).as_uri(), own_game]


def test_serving_forgets_projects_that_no_longer_exist(world):
    kept = world.existing_project("my-own-game")
    world.eternaldev_knows_projects([(world.root / "game").as_uri(), kept])

    world.workspace.register_games()

    assert world.eternaldev_projects() == [(world.root / "games" / HAMMERFEST).as_uri(), kept]


def test_serving_registers_the_games_when_eternaldev_never_ran(world):
    world.workspace.register_games()

    assert world.eternaldev_projects() == [(world.root / "games" / HAMMERFEST).as_uri()]


def test_registering_keeps_the_newest_projects_within_eternaldev_limit(world):
    older = [world.existing_project(f"game-{i}") for i in range(25)]
    world.eternaldev_knows_projects(older)

    world.workspace.register_games()

    assert world.eternaldev_projects() == [(world.root / "games" / HAMMERFEST).as_uri(), *older[:19]]


def test_recordings_of_each_game_are_kept_apart(world):
    with_second_game(world, served=HAMMERFEST)
    world.record("run", "sandbox", "-g", HAMMERFEST)
    world.eternaldev_serves(OTHER)
    world.record("run", "-g", OTHER)
    world.eternaldev_goes_down()

    world.replay("run", "-g", HAMMERFEST)

    assert (world.game.game, world.game.options) == (HAMMERFEST, ["nightmare", "boost", "insight"])


def test_a_recording_is_named_after_its_preset(world):
    world.hftas("record", "pap-rng")
    world.eternaldev_goes_down()

    world.hftas("replay", "pap-rng")

    assert world.recording_dir("pap-rng").is_dir()
    assert world.game.options == ["boost", "insight"]


def test_status_tells_eternaldev_runs_and_which_games_it_serves(world, capsys):
    with_second_game(world, served=HAMMERFEST)

    exit_code = world.hftas("status")

    out = capsys.readouterr().out
    assert exit_code == 0
    assert f"eternaldev: running on {world.eternaldev.url}" in out
    assert [line.split()[:2] for line in out.splitlines()[1:]] == [[OTHER, "not"], [HAMMERFEST, "served"]]


def test_status_tells_eternaldev_is_down(world, capsys):
    world.eternaldev_goes_down()

    exit_code = world.hftas("status")

    assert exit_code == 1
    assert "eternaldev: not running" in capsys.readouterr().out


def test_games_lists_every_game_with_its_state(world, capsys):
    with_second_game(world)
    world.game_is_not_built(OTHER)

    world.hftas("games")

    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[:2] for line in lines] == [[OTHER, "not"], [HAMMERFEST, "built"]]
