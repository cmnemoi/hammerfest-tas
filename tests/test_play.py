import pytest

from tests.fakes import DEFAULT_FAMILIES

CARROT_FAMILY = "108"  # unlocks every Deluxe feature


@pytest.mark.parametrize("preset, options", [
    ("speedrun-no-rng", ["nightmare", "boost", "noeffect"]),
    ("speedrun-rng", ["nightmare", "boost"]),
    ("pap-no-rng", ["boost", "insight", "noeffect"]),
    ("pap-rng", ["boost", "insight"]),
    ("sandbox", ["nightmare", "boost", "insight"]),
])
def test_each_preset_starts_a_deluxe_game_with_its_options(world, preset, options):
    exit_code = world.run(preset)

    assert exit_code == 0
    assert (world.game.mode, world.game.options) == ("deluxe", options)


def test_without_preset_the_game_starts_with_no_option(world):
    world.run()

    assert world.game.options == []


def test_options_can_be_added_to_and_removed_from_a_preset(world):
    world.run("sandbox", "-o", "ninja", "-x", "insight")

    assert world.game.options == ["nightmare", "boost", "ninja"]


def test_adding_an_option_already_in_the_preset_does_not_duplicate_it(world):
    world.run("pap-rng", "-o", "boost")

    assert world.game.options == ["boost", "insight"]


def test_removing_an_option_absent_from_the_preset_is_rejected(world, caplog):
    exit_code = world.run("pap-rng", "-x", "nightmare")

    assert exit_code == 1
    assert world.games_started == []
    assert "Cannot remove nightmare" in caplog.text


def test_unknown_preset_is_rejected_listing_the_presets(world, caplog):
    exit_code = world.run("speedrun")

    assert exit_code == 1
    assert world.games_started == []
    assert "Unknown preset 'speedrun'" in caplog.text and "speedrun-no-rng" in caplog.text


def test_mistyped_option_is_rejected_before_the_game_starts(world, caplog):
    # eternaldev itself accepts any option id: the game would silently start without it
    exit_code = world.run("-o", "tornade")

    assert exit_code == 1
    assert world.games_started == []
    assert "Unknown options for mode 'deluxe': tornade" in caplog.text and "boost" in caplog.text


def test_presets_play_with_every_quest_completed(world):
    world.run("speedrun-no-rng")

    assert CARROT_FAMILY in world.game.families


def test_default_profile_plays_as_a_new_account(world):
    world.run("speedrun-no-rng", "--profile", "default")

    assert world.game.families == DEFAULT_FAMILIES.split(",")


def test_unknown_profile_is_rejected_instead_of_playing_as_a_new_account(world, caplog):
    # eternaldev silently falls back to the default families on an unknown profile
    exit_code = world.run("sandbox", "--profile", "ful")

    assert exit_code == 1
    assert world.games_started == []
    assert "Unknown profile 'ful'" in caplog.text


def test_unreachable_eternaldev_fails_explicitly(world, caplog):
    world.eternaldev_goes_down()

    exit_code = world.run("sandbox")

    assert exit_code == 1
    assert "start it with `hftas serve`" in caplog.text


def test_unbuilt_game_fails_explicitly(world, caplog):
    world.game_is_not_built()

    exit_code = world.run("sandbox")

    assert exit_code == 1
    assert world.games_started == []
    assert "hftas build -g hammerfest-deluxe" in caplog.text


def test_games_start_under_libtas_by_default(world):
    world.run("sandbox")

    assert world.loader.launches[-1].tas


def test_ruffle_only_starts_the_game_without_libtas(world):
    world.run("sandbox", "--ruffle-only")

    assert not world.loader.launches[-1].tas


def test_the_mode_can_be_changed(world):
    world.run("--mode", "solo", "-o", "mirror")

    assert (world.game.mode, world.game.options) == ("solo", ["mirror"])
