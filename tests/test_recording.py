import socket

from hftas.ruffle import libtas_command


def test_a_recorded_run_replays_identically_without_eternaldev(world):
    world.record("pap-no-rng", "pap-no-rng")
    recorded = world.game
    world.eternaldev_goes_down()

    exit_code = world.replay("pap-no-rng")

    assert exit_code == 0
    assert world.game == recorded


def test_replays_give_libtas_the_exact_same_launch(world):
    world.port = _free_port()  # the mirror URL is part of the launch: replays use a fixed port
    world.record("run", "speedrun-no-rng")
    world.replay("run")
    world.replay("run")

    first, second = (libtas_command("libTAS", "/usr/local/bin/ruffle", launch) for launch in world.loader.launches[1:])
    assert first == second


def test_replays_start_under_libtas_unless_asked_otherwise(world):
    world.record("run", "sandbox")

    world.replay("run")
    world.replay("run", "--ruffle-only")

    assert [launch.tas for launch in world.loader.launches[1:]] == [True, False]


def test_recording_again_replaces_the_previous_run(world):
    world.record("run", "speedrun-rng")
    world.record("run", "pap-rng")

    world.replay("run")

    assert world.game.options == ["boost", "insight"]
    assert world.game.run_id == world.games_started[1].run_id


def test_replaying_a_missing_recording_fails_explicitly(world, caplog):
    exit_code = world.replay("never-recorded")

    assert exit_code == 1
    assert world.games_started == []
    assert "No recorded run" in caplog.text


def test_a_request_missing_from_the_recording_is_not_served(world):
    world.record("run", "sandbox")
    world.recorded_response_is_lost("run", f"/api/v1/games/{world.eternaldev.game_id}")

    exit_code = world.replay("run")

    assert exit_code != 0
    assert len(world.games_started) == 1


def test_busy_mirror_port_fails_explicitly(world, caplog):
    world.record("run", "sandbox")
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        world.port = busy.getsockname()[1]

        exit_code = world.replay("run")

    assert exit_code == 1
    assert "--port" in caplog.text


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
