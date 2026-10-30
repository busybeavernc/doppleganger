"""Entry point for the packaged Doppleganger.exe (and `python launcher.py`)."""
import os
import sys
import traceback


def _app_dir() -> str:
    # Keep config.json and loops/ next to the .exe, not in a temp folder.
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _error_box(msg: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "Doppleganger", 0x10)
    except Exception:  # noqa: BLE001 - not on Windows
        print(msg, file=sys.stderr)


if __name__ == "__main__":
    os.chdir(_app_dir())
    try:
        from doppleganger.app import main
        main()
    except Exception as e:  # noqa: BLE001
        with open("doppleganger-error.log", "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        _error_box(f"Doppleganger stopped:\n\n{e}\n\nDetails were saved to doppleganger-error.log")
        sys.exit(1)
