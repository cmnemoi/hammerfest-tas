import pytest

from hftas.presets import PresetError, load_presets


def write(tmp_path, content: str):
    path = tmp_path / "presets.toml"
    path.write_text(content)
    return path


def test_a_preset_inherits_the_defaults_it_does_not_override(tmp_path):
    path = write(tmp_path, """
        [defaults]
        profile = "full"
        [defaults.settings]
        music = true
        [presets.quiet]
        options = ["boost"]
        settings = { sound = false }
    """)

    _, presets = load_presets(path)

    quiet = presets["quiet"]
    assert (quiet.profile, quiet.settings.music, quiet.settings.sound) == ("full", True, False)


def test_a_mistyped_preset_key_is_rejected_instead_of_ignored(tmp_path):
    path = write(tmp_path, """
        [presets.pap]
        option = ["boost"]
    """)

    with pytest.raises(PresetError, match=r"\[presets.pap\]: unknown keys \['option'\]"):
        load_presets(path)


def test_a_mistyped_setting_is_rejected(tmp_path):
    path = write(tmp_path, """
        [presets.pap]
        settings = { musique = true }
    """)

    with pytest.raises(PresetError, match="musique"):
        load_presets(path)


def test_options_must_be_a_list(tmp_path):
    path = write(tmp_path, """
        [presets.pap]
        options = "boost"
    """)

    with pytest.raises(PresetError, match="list of option ids"):
        load_presets(path)
