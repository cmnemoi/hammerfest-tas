"""The clock libTAS gives the game seeds its randomness: a recording keeps the clock it is played with."""

MICROSECOND = 1_000


def test_a_run_recorded_with_a_clock_offset_replays_with_that_clock(world):
    world.run_named("run", "sandbox", "--clock-offset", "250")
    recorded = world.libtas_clock()

    world.run_named("run")

    assert world.libtas_clock() == recorded


def test_the_clock_offset_shifts_the_clock_by_that_many_microseconds(world):
    world.run_named("run", "sandbox")
    original = world.libtas_clock()

    world.run_named("run", "--clock-offset", "250")

    assert world.libtas_clock() == original + 250 * MICROSECOND


def test_the_clock_offset_of_a_recorded_run_can_change_and_is_then_kept(world):
    world.run_named("run", "sandbox")
    original = world.libtas_clock()
    world.run_named("run", "--clock-offset", "7")

    world.run_named("run")

    assert world.libtas_clock() == original + 7 * MICROSECOND


def test_a_clock_offset_of_zero_brings_back_the_original_clock(world):
    world.run_named("run", "sandbox")
    original = world.libtas_clock()
    world.run_named("run", "--clock-offset", "7")

    world.run_named("run", "--clock-offset", "0")

    assert world.libtas_clock() == original


def test_a_new_run_does_not_inherit_the_clock_offset_of_the_previous_one(world):
    world.run_named("run", "sandbox", "--clock-offset", "7")
    world.run_named("run", "sandbox", "--new")
    new_run_clock = world.libtas_clock()

    world.run_named("run")

    assert world.libtas_clock() == new_run_clock
    assert new_run_clock % 1_000_000_000 == 0  # the run creation time, to the second


def test_a_clock_offset_of_a_second_or_more_carries_into_the_seconds(world):
    world.run_named("run", "sandbox")
    original = world.libtas_clock()

    world.run_named("run", "--clock-offset", "2500000")

    assert world.libtas_clock() == original + 2_500_000 * MICROSECOND


def test_a_negative_clock_offset_is_rejected_before_the_game_starts(world, caplog):
    exit_code = world.run_named("run", "sandbox", "--clock-offset", "-1")

    assert exit_code == 1
    assert world.games_started == []
    assert "--clock-offset" in caplog.text


def test_a_preset_clock_is_the_clock_libtas_gives_the_game(world):
    world.preset_sets_clock("sandbox", "2026-10-04T19:33:39.001Z")

    world.run("sandbox")

    assert world.libtas_clock() == 1_791_142_419_001_000_000


def test_a_clock_set_on_a_preset_applies_to_its_existing_recording(world):
    world.run("sandbox")
    world.preset_sets_clock("sandbox", "2026-10-04T19:33:39.001Z")

    world.run("sandbox")

    assert world.libtas_clock() == 1_791_142_419_001_000_000


def test_a_preset_clock_keeps_its_time_zone(world):
    world.preset_sets_clock("sandbox", "2026-10-04T21:33:39.001+02:00")

    world.run("sandbox")

    assert world.libtas_clock() == 1_791_142_419_001_000_000


def test_the_clock_offset_shifts_from_the_preset_clock(world):
    world.preset_sets_clock("sandbox", "2026-10-04T19:33:39.001Z")

    world.run("sandbox", "--clock-offset", "999000")

    assert world.libtas_clock() == 1_791_142_420_000_000_000


def test_other_presets_keep_the_run_creation_clock(world):
    world.preset_sets_clock("sandbox", "2026-10-04T19:33:39.001Z")

    world.run("pap-rng")

    assert world.libtas_clock() % 1_000_000_000 == 0
    assert world.libtas_clock() != 1_791_142_419_000_000_000
