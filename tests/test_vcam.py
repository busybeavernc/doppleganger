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


def test_elevated_script_always_reports_its_result():
    body = 'copy /y "a" "b" >nul || exit /b 1\r\nregsvr32 /s "x" || exit /b 2\r\nexit /b 0'
    text = vcam.elevated_script(body, r"C:\t\result.txt")
    lines = text.split("\r\n")
    # the body runs as a subroutine; the result line comes after the call, before any body line
    assert lines[1] == "call :main" and lines[2].startswith("(echo %ERRORLEVEL%)>")
    assert lines.index(":main") > 2 and text.rstrip().endswith("exit /b 0")


def test_version_stamp_is_written_as_text_not_a_redirect():
    import inspect
    src = inspect.getsource(vcam.install)
    assert "(echo {DRIVER_VERSION})>" in src  # 'echo 2> file' would redirect stderr instead
