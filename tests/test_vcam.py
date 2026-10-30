from unittest import mock

from doppleganger import vcam
from doppleganger.app import background_file

CAMS = [(0, "OBS Virtual Camera"), (1, "Integrated Camera"), (2, "Logitech BRIO"), (3, "Doppleganger")]


def test_virtual_cameras_are_never_offered():
    with mock.patch.object(vcam, "list_cameras", return_value=CAMS):
        assert [n for _, n in vcam.real_cameras()] == ["Integrated Camera", "Logitech BRIO"]


def test_remembered_camera_found_by_name_even_if_index_moved():
    with mock.patch.object(vcam, "list_cameras", return_value=CAMS):
        assert vcam.resolve_camera("Logitech BRIO", 0) == (2, "Logitech BRIO")


def test_unknown_or_virtual_choice_falls_back_to_a_real_camera():
    with mock.patch.object(vcam, "list_cameras", return_value=CAMS):
        assert vcam.resolve_camera("", 0) == (1, "Integrated Camera")        # index 0 is OBS: skip
        assert vcam.resolve_camera("Gone Cam", 2) == (2, "Logitech BRIO")    # keep a real index
        assert vcam.resolve_camera("Doppleganger", 3) == (1, "Integrated Camera")  # never feed back


def test_no_camera_list_uses_configured_index():
    with mock.patch.object(vcam, "list_cameras", return_value=[]):
        assert vcam.resolve_camera("", 1) == (1, "Camera 1")


def test_calibration_file_is_per_camera():
    assert background_file("Logitech BRIO") == "background-logitech-brio.png"
    assert background_file("Integrated Camera") != background_file("Logitech BRIO")


def test_doppleganger_camera_not_installed_off_windows():
    assert vcam.installed_version() is None or vcam.is_windows()
