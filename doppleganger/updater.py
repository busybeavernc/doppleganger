"""Self-update from GitHub Releases (packaged Windows .exe only).

Each build on GitHub publishes a release tagged vX.Y.N with Doppleganger.exe attached.
The app compares that tag with its own version; to update it downloads the new
.exe next to itself, then a tiny batch script swaps the files once the app has
exited and starts the new version.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from . import __version__

ASSET_NAME = "Doppleganger.exe"


def current_version() -> str:
    try:
        from ._build import VERSION  # written by the GitHub build
        return VERSION
    except ImportError:
        return __version__


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4]) or (0,)


def can_self_update() -> bool:
    return bool(getattr(sys, "frozen", False)) and os.name == "nt"


@dataclass
class Release:
    version: str
    download_url: str
    notes: str = ""


class UpdateError(Exception):
    pass


def _request(url: str, token: str, accept: str = "application/vnd.github+json") -> urllib.request.Request:
    headers = {"User-Agent": "Doppleganger-updater", "Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def check(repo: str, token: str = "", timeout: float = 5.0) -> Release | None:
    """Newer release than the running version, or None if up to date."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        with urllib.request.urlopen(_request(url, token), timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError("No releases found (if the repo is private, set update_token in config.json)") from e
        raise UpdateError(f"GitHub returned {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError("Couldn't reach GitHub") from e

    tag = data.get("tag_name", "")
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET_NAME), None)
    if asset is None or parse_version(tag) <= parse_version(current_version()):
        return None
    # Private repos need the API asset URL (works with a token); public can use the plain link.
    dl = asset["url"] if token else asset["browser_download_url"]
    return Release(tag.lstrip("v"), dl, data.get("body", ""))


def download(release: Release, token: str = "",
             progress: Callable[[float], None] | None = None) -> str:
    """Download the new .exe next to the running one. Returns its path."""
    dest = os.path.join(os.path.dirname(sys.executable), ASSET_NAME + ".new")
    req = _request(release.download_url, token, accept="application/octet-stream")
    try:
        with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while chunk := r.read(1 << 16):
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
    except (urllib.error.URLError, OSError) as e:
        if os.path.exists(dest):
            os.remove(dest)
        raise UpdateError(f"Download failed: {e}") from e
    if os.path.getsize(dest) < 1_000_000:  # sanity check: a real build is tens of MB
        os.remove(dest)
        raise UpdateError("Downloaded file looks incomplete")
    return dest


def apply_and_restart(new_exe: str) -> None:
    """Swap in the new .exe after this process exits, relaunch it, and exit now."""
    exe = sys.executable
    script = os.path.join(tempfile.gettempdir(), "doppleganger_update.bat")
    with open(script, "w", encoding="utf-8") as f:
        f.write(f"""@echo off
set tries=0
:wait
set /a tries+=1
timeout /t 1 /nobreak >nul
move /y "{new_exe}" "{exe}" >nul 2>&1 || (if %tries% lss 30 goto wait)
start "" "{exe}"
del "%~f0"
""")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(["cmd", "/c", script], creationflags=flags, close_fds=True, env=clean_environment())
    os._exit(0)


def clean_environment() -> dict[str, str]:
    """Environment for relaunching ourselves as a brand-new app.

    A packaged (PyInstaller) app marks its environment with its private unpack
    folder. If the relaunched .exe inherits those markers, it looks for
    python312.dll in the OLD folder - which is deleted when this process exits -
    and fails with "Failed to load Python DLL". So strip them and ask for a reset.
    """
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith("_PYI") and k.upper() != "_MEIPASS2"}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env
