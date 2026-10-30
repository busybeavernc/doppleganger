"""Doppleganger entry point: update check, engine, window."""
from __future__ import annotations

import argparse
import logging
import os

from . import updater
from . import vcam as vcamlib
from .config import Config
from .engine import BACKGROUND_FILE, Engine, Output, background_file  # noqa: F401  (re-exported)

log = logging.getLogger("doppleganger")


def main() -> None:
    ap = argparse.ArgumentParser(description="Doppleganger - loop/live virtual camera")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--camera", type=int, help="webcam index (0, 1, ...)")
    ap.add_argument("--seconds", type=float, help="loop length in seconds")
    ap.add_argument("--no-vcam", action="store_true", help="preview only, no virtual camera")
    ap.add_argument("--remove-camera", action="store_true", help="remove the Doppleganger camera and exit")
    ap.add_argument("--minimized", action="store_true", help="start minimized (used when starting with Windows)")
    args = ap.parse_args()

    logging.basicConfig(filename="doppleganger.log", filemode="w", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log.info("Doppleganger v%s starting in %s", updater.current_version(), os.getcwd())

    if args.remove_camera:  # used by the uninstaller
        if vcamlib.installed_version() is not None:
            ok, detail = vcamlib.uninstall()
            log.info("Camera removal: %s (%s)", ok, detail)
        return

    cfg = Config.load(args.config)
    if args.camera is not None:
        cfg.camera_index = args.camera
    if args.seconds is not None:
        cfg.loop_seconds = args.seconds
    if not os.path.exists(args.config):
        cfg.save(args.config)
    if cfg.auto_update and updater.can_self_update():
        startup_update(cfg)

    engine = Engine(cfg, vcam=not args.no_vcam, config_path=args.config)
    if not args.no_vcam and vcamlib.needs_install() and vcamlib.installed_version() is not None:
        engine.install_driver(ask=False)  # this version ships a newer camera driver

    from .ui import MainWindow  # imported late: Tk isn't needed for --remove-camera
    MainWindow(engine, minimized=args.minimized).run()
    log.info("Doppleganger closed")
    logging.shutdown()
    # Everything is saved and released by now; don't let a stray tray/hotkey thread keep us alive.
    os._exit(0)


def startup_update(cfg: Config) -> None:
    """On launch: if a newer release exists, download it with a small progress window and restart.
    Any problem (offline, GitHub down) just skips the update and opens the app normally."""
    try:
        rel = updater.check(cfg.update_repo, cfg.update_token, timeout=4)
    except updater.UpdateError as e:
        log.info("Update check skipped: %s", e)
        return
    if rel is None:
        return
    from .ui import run_startup_update
    path = run_startup_update(rel, cfg.update_token)
    if path:
        updater.apply_and_restart(path)
