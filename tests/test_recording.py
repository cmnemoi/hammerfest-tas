import socket

from hftas.ruffle import libtas_command


def test_the_first_run_is_recorded_then_replayed_identically_without_eternaldev(world):
    world.run_named("run", "pap-no-rng")
    recorded = world.game
    world.eternaldev_goes_down()

    exit_code = world.run_named("run")

    assert exit_code == 0
    assert world.game == recorded


def test_replays_give_libtas_the_exact_same_launch(world):
    world.port = _free_port()  # the mirror URL is part of the launch: replays use a fixed port
    world.run_named("run", "speedrun-no-rng")
    world.run_named("run")
    world.run_named("run")

    first, second = (libtas_command("libTAS", "/usr/local/bin/ruffle", launch) for launch in world.loader.launches[1:])
    assert first == second


def test_replays_start_under_libtas_unless_asked_otherwise(world):
    world.run_named("run", "sandbox")

    world.run_named("run")
    world.run_named("run", "--ruffle-only")

    assert [launch.tas for launch in world.loader.launches[1:]] == [True, False]


def test_new_records_a_new_run_in_place_of_the_previous_one(world):
    world.run_named("run", "speedrun-rng")
    world.run_named("run", "pap-rng", "--new")

    world.run_named("run")

    assert world.game.options == ["boost", "insight"]
    assert world.game.run_id == world.games_started[1].run_id


def test_options_of_a_recorded_run_cannot_change(world, caplog):
    world.run("pap-rng")

    exit_code = world.run("pap-rng", "-o", "ninja")

    assert exit_code == 1
    assert len(world.games_started) == 1
    assert "--new" in caplog.text


def test_without_preset_nor_name_the_run_is_recorded_as_default(world):
    world.run()

    assert world.recording_dir("default").is_dir()


def test_a_request_missing_from_the_recording_is_not_served(world):
    world.run_named("run", "sandbox")
    world.recorded_response_is_lost("run", f"/api/v1/games/{world.eternaldev.game_id}")

    exit_code = world.run_named("run")

    assert exit_code != 0
    assert len(world.games_started) == 1


def test_busy_mirror_port_fails_explicitly(world, caplog):
    world.run_named("run", "sandbox")
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        world.port = busy.getsockname()[1]

        exit_code = world.run_named("run")

    assert exit_code == 1
    assert "--port" in caplog.text


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
