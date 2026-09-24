from hftas.box import should_enter_box

DISTROBOX = "/usr/bin/distrobox"


def test_from_the_host_hftas_runs_in_the_box():
    assert should_enter_box({}, DISTROBOX)


def test_inside_a_container_hftas_runs_in_place():
    # Never re-enter from the box itself: it would loop
    assert not should_enter_box({"CONTAINER_ID": "hammerfest-tas"}, DISTROBOX)


def test_without_distrobox_hftas_runs_in_place():
    assert not should_enter_box({}, None)


def test_hftas_can_be_told_to_run_in_place():
    assert not should_enter_box({"HFTAS_NO_BOX": "1"}, DISTROBOX)
