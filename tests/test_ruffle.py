import subprocess

from hftas.ruffle import Launch, libtas_command, ruffle_args

RUN = {
    "id": "1e12d8eb-6ccd-4308-922c-2db6e3d684a8",
    "created_at": "2026-09-24T11:11:19.316Z",
    "game": {"id": "34889f53-9810-cd24-05e1-1c26631b73ac"},
    # Real runs carry the build: display names with quotes and spaces
    "build": {"display_name": "Les Cavernes de Hammerfest", "options": {"shadowclones": "Clones d'ombre", "x": "a \"b\" $HOME `id`;"}},
    "game_mode": "deluxe",
    "game_options": ["nightmare", "noeffect"],
    "settings": {"detail": True, "shake": True, "sound": True, "music": False, "volume": 100, "locale": "fr-FR"},
}


def test_libtas_hands_ruffle_every_argument_intact_through_its_shell():
    launch = Launch("http://127.0.0.1:8765", RUN, tas=True)
    game_args = libtas_command("libTAS", "/usr/local/bin/ruffle", launch)[4:]

    # libTAS joins the game arguments and runs them with `sh -c`
    received = subprocess.run(
        ["sh", "-c", "printf '%s\\0' " + " ".join(game_args)], capture_output=True, check=True,
    ).stdout.decode().split("\0")[:-1]

    assert received == ruffle_args(launch)


def test_libtas_clock_starts_at_the_run_creation():
    launch = Launch("http://127.0.0.1:8765", RUN, tas=True)

    command = libtas_command("libTAS", "/usr/local/bin/ruffle", launch)

    assert command[1:3] == ["--system-time-sec", "1790248279"]


def test_only_tas_launches_use_blocking_loads():
    assert "--load-behavior" not in ruffle_args(Launch("http://127.0.0.1:8765", RUN, tas=False))
    assert "--load-behavior" in ruffle_args(Launch("http://127.0.0.1:8765", RUN, tas=True))


def test_loader_gets_the_run_options_from_its_flashvars():
    params = Launch("http://127.0.0.1:8765", RUN).params

    assert params["game"] == RUN["game"]["id"]
    assert '"options":["nightmare","noeffect"]' in params["options"]
