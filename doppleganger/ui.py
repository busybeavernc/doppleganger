"""Doppleganger's windows: main control window, always-on-top mini bar, settings, first-run setup.

Branded Midnight / Violet / Aqua (see brand.py). All windows are excluded from
screen capture (when enabled), so screen-sharing viewers never see them. The
engine runs on its own thread; the window only reads its state and sends it requests.
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import cv2
from PIL import Image, ImageTk

from . import brand, library, updater, winutil
from .brand import AMBER, AQUA, BORDER, CLOUD, DANGER, MIDNIGHT, MUTED, SURFACE, SURFACE_HI, VIOLET, VIOLET_DARK
from .cutcontrol import SYNC_THRESHOLD
from .recorder import State

FONT = "Segoe UI" if os.name == "nt" else "Inter"
MODE_BG = {"live": AQUA, "loop": VIOLET, "glitch": AMBER}
MODE_FG = {"live": MIDNIGHT, "loop": CLOUD, "glitch": MIDNIGHT}


def _photo(path: str, width: int | None = None, bg: str = MIDNIGHT) -> ImageTk.PhotoImage:
    """Load a brand image, scaled, flattened onto `bg` (crisp edges on every Tk build)."""
    img = Image.open(path).convert("RGBA")
    if width:
        img = img.resize((width, round(width * img.height / img.width)), Image.LANCZOS)
    flat = Image.new("RGBA", img.size, bg)
    flat.alpha_composite(img)
    return ImageTk.PhotoImage(flat.convert("RGB"))


def apply_theme(root: tk.Misc) -> None:
    """Our own ttk theme in the brand palette (built on 'clam' so every colour is ours)."""
    root.configure(bg=MIDNIGHT)
    s = ttk.Style(root)
    s.theme_use("clam")
    base = (FONT, 10)
    s.configure(".", background=MIDNIGHT, foreground=CLOUD, fieldbackground=SURFACE, bordercolor=BORDER,
                lightcolor=SURFACE, darkcolor=SURFACE, troughcolor=SURFACE, focuscolor=VIOLET,
                selectbackground=VIOLET, selectforeground=CLOUD, font=base, insertcolor=CLOUD)
    s.configure("TFrame", background=MIDNIGHT)
    s.configure("TLabel", background=MIDNIGHT, foreground=CLOUD)
    s.configure("Small.TLabel", font=(FONT, 9), foreground=MUTED)
    s.configure("Head.TLabel", font=(FONT, 11, "bold"))
    s.configure("Title.TLabel", font=(FONT, 17, "bold"))
    s.configure("Tag.TLabel", font=(FONT, 10), foreground=MUTED)
    s.configure("TButton", background=SURFACE, foreground=CLOUD, bordercolor=BORDER, padding=(10, 6),
                lightcolor=SURFACE, darkcolor=SURFACE, focuscolor=SURFACE)
    s.map("TButton", background=[("pressed", BORDER), ("active", SURFACE_HI), ("disabled", MIDNIGHT)],
          foreground=[("disabled", MUTED)])
    s.configure("Accent.TButton", background=VIOLET, foreground=CLOUD, bordercolor=VIOLET,
                lightcolor=VIOLET, darkcolor=VIOLET, focuscolor=VIOLET)
    s.map("Accent.TButton", background=[("pressed", VIOLET_DARK), ("active", "#8B5CF6")])
    s.configure("TCheckbutton", background=MIDNIGHT, foreground=CLOUD, indicatorbackground=SURFACE,
                indicatorforeground=CLOUD, indicatorcolor=SURFACE, focuscolor=MIDNIGHT)
    s.map("TCheckbutton", indicatorcolor=[("selected", VIOLET)], background=[("active", MIDNIGHT)])
    s.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE, foreground=CLOUD, arrowcolor=CLOUD,
                bordercolor=BORDER, lightcolor=SURFACE, darkcolor=SURFACE, padding=(8, 5))
    s.map("TCombobox", fieldbackground=[("readonly", SURFACE)], foreground=[("readonly", CLOUD)],
          selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", CLOUD)])
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", CLOUD)
    root.option_add("*TCombobox*Listbox.selectBackground", VIOLET)
    root.option_add("*TCombobox*Listbox.font", base)
    s.configure("Sync.Horizontal.TProgressbar", troughcolor=SURFACE, background=VIOLET, bordercolor=SURFACE,
                lightcolor=VIOLET, darkcolor=VIOLET, thickness=8)
    s.configure("InSync.Horizontal.TProgressbar", troughcolor=SURFACE, background=AQUA, bordercolor=SURFACE,
                lightcolor=AQUA, darkcolor=AQUA, thickness=8)
    s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=CLOUD, bordercolor=BORDER,
                lightcolor=SURFACE, darkcolor=SURFACE, rowheight=62)
    s.map("Treeview", background=[("selected", SURFACE_HI)], foreground=[("selected", CLOUD)])
    s.configure("TScale", background=VIOLET, troughcolor=SURFACE, bordercolor=SURFACE,
                lightcolor=VIOLET, darkcolor=VIOLET)
    s.configure("TSeparator", background=BORDER)
    s.configure("TLabelframe", background=MIDNIGHT, bordercolor=BORDER, lightcolor=MIDNIGHT, darkcolor=MIDNIGHT)
    s.configure("TLabelframe.Label", background=MIDNIGHT, foreground=MUTED, font=(FONT, 9, "bold"))
    s.configure("Vertical.TScrollbar", background=SURFACE, troughcolor=MIDNIGHT, bordercolor=MIDNIGHT,
                arrowcolor=MUTED, lightcolor=SURFACE, darkcolor=SURFACE)


class HoldButton(tk.Label):
    """Big cut button: press/release go to the engine (tap = cut now, hold = cut when in sync).
    It wears the colour of where you're cutting TO: Violet = to the loop, Aqua = to live."""

    def __init__(self, master, engine, font_size=15, **kw):
        super().__init__(master, text="CUT", fg=CLOUD, bg=VIOLET, cursor="hand2",
                         font=(FONT, font_size, "bold"), padx=10, pady=12, **kw)
        self.e = engine
        self.bind("<ButtonPress-1>", lambda _e: self.e.request("cut_press"))
        self.bind("<ButtonRelease-1>", lambda _e: self.e.request("cut_release"))

    def refresh(self, short: bool = False) -> None:
        e = self.e
        if e.cut.waiting:
            text = f"SYNC {int(e.sync * 100)}%" if short else f"WAITING FOR SYNC  {int(e.sync * 100)}%"
            bg, fg = SURFACE_HI, AQUA
        elif e.mode == "loop":
            text, bg, fg = "CUT TO LIVE", AQUA, MIDNIGHT
        else:
            ready = e.player is not None
            text, bg, fg = "CUT TO LOOP", (VIOLET if ready else SURFACE), (CLOUD if ready else MUTED)
        if self.cget("text") != text:
            self.configure(text=text)
        if self.cget("bg") != bg or self.cget("fg") != fg:
            self.configure(bg=bg, fg=fg)


class MainWindow:
    def __init__(self, engine, minimized: bool = False):
        self.e = engine
        self.cfg = engine.cfg
        self._start_minimized = minimized
        self.root = tk.Tk()
        self.root.title("Doppleganger")
        self.root.geometry("1280x760")
        self.root.minsize(980, 620)
        try:
            self.root.iconbitmap(default=brand.asset("icon.ico"))
        except tk.TclError:
            pass
        self._icon = ImageTk.PhotoImage(Image.open(brand.asset("icon.png")).resize((64, 64), Image.LANCZOS))
        self.root.iconphoto(True, self._icon)
        apply_theme(self.root)
        self._photo = None
        self._last_preview_id = None
        self._lib_version = -1
        self._thumbs: dict[str, ImageTk.PhotoImage] = {}
        self._pending_release = None
        self._engine_thread: threading.Thread | None = None
        self.minibar: MiniBar | None = None
        self.wizard: Wizard | None = None
        self.settings: SettingsWindow | None = None
        self._build()
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- layout ----------
    def _build(self) -> None:
        r = self.root
        r.columnconfigure(0, weight=1)
        r.rowconfigure(0, weight=1)

        self.preview = tk.Label(r, bg=MIDNIGHT, bd=0, highlightthickness=0)
        self.preview.grid(row=0, column=0, sticky="nsew", padx=(14, 0), pady=14)
        self.preview.bind("<Configure>", self._on_preview_resize)

        side = ttk.Frame(r, padding=(16, 12, 16, 8), width=340)
        side.grid(row=0, column=1, sticky="ns")
        side.columnconfigure(0, weight=1)

        self._logo = _photo(brand.asset("logo_dark.png"), 250)
        tk.Label(side, image=self._logo, bg=MIDNIGHT, bd=0).grid(sticky="w", pady=(0, 12))

        # --- status ---
        top = ttk.Frame(side)
        top.grid(sticky="ew")
        self.state_lbl = tk.Label(top, text="LIVE", fg=MIDNIGHT, bg=AQUA, font=(FONT, 15, "bold"), width=7, pady=3)
        self.state_lbl.pack(side="left")
        self.glitch_lbl = tk.Label(top, text="GLITCH", fg=MIDNIGHT, bg=AMBER, font=(FONT, 10, "bold"),
                                   padx=8, pady=6)
        self.out_lbl = ttk.Label(side, text="", style="Small.TLabel", wraplength=300, justify="left")
        self.out_lbl.grid(sticky="w", pady=(6, 0))

        syncrow = ttk.Frame(side)
        syncrow.grid(sticky="ew", pady=(10, 0))
        syncrow.columnconfigure(1, weight=1)
        ttk.Label(syncrow, text="Sync", style="Small.TLabel").grid(row=0, column=0, padx=(0, 8))
        self.sync_bar = ttk.Progressbar(syncrow, maximum=100, style="Sync.Horizontal.TProgressbar")
        self.sync_bar.grid(row=0, column=1, sticky="ew")
        self.sync_pct = ttk.Label(syncrow, text="0%", width=5, anchor="e", style="Small.TLabel")
        self.sync_pct.grid(row=0, column=2)
        self.v_outlines = tk.BooleanVar(value=self.cfg.show_outlines)
        ttk.Checkbutton(side, text="Outlines: you (aqua) · loop (violet)   O", variable=self.v_outlines,
                        command=lambda: self.e.request("outlines")).grid(sticky="w", pady=(6, 0))

        # --- cut ---
        self.cut_btn = HoldButton(side, self.e)
        self.cut_btn.grid(sticky="ew", pady=(12, 3))
        hk = self.cfg.hotkey.strip("<>").upper()
        ttk.Label(side, text=f"Tap: cut now  ·  Hold: cut when in sync  ({hk} / Space)",
                  style="Small.TLabel").grid(sticky="w")

        row = ttk.Frame(side)
        row.grid(sticky="ew", pady=(10, 0))
        for i in range(3):
            row.columnconfigure(i, weight=1)
        gk = self.cfg.glitch_hotkey.strip("<>").upper()
        ttk.Button(row, text=f"Glitch ({gk})", command=lambda: self.e.request("glitch")).grid(
            row=0, column=0, sticky="ew", padx=(0, 4))
        self.rec_btn = ttk.Button(row, text="Record loop", command=lambda: self.e.request("record"))
        self.rec_btn.grid(row=0, column=1, sticky="ew", padx=4)
        if self.e.seg is None:  # AI segmentation unavailable: calibration is needed, keep it handy
            ttk.Button(row, text="Calibrate", command=lambda: self.e.request("calibrate")).grid(
                row=0, column=2, sticky="ew", padx=(4, 0))
        else:
            row.columnconfigure(2, weight=0)

        ttk.Separator(side).grid(sticky="ew", pady=12)

        # --- webcam ---
        ttk.Label(side, text="Webcam", style="Head.TLabel").grid(sticky="w")
        self.cam_var = tk.StringVar(value=self.e.camera_name)
        self.cam_box = ttk.Combobox(side, textvariable=self.cam_var, state="readonly",
                                    postcommand=self._refresh_cameras)
        self.cam_box.grid(sticky="ew", pady=(4, 0))
        self.cam_box.bind("<<ComboboxSelected>>", lambda _e: self.e.request(f"camera:{self.cam_var.get()}"))

        # --- loops ---
        lh = ttk.Frame(side)
        lh.grid(sticky="ew", pady=(12, 4))
        ttk.Label(lh, text="Loops", style="Head.TLabel").pack(side="left")
        self.light_lbl = ttk.Label(lh, text="", style="Small.TLabel", foreground=AMBER)
        self.light_lbl.pack(side="right")
        self.tree = ttk.Treeview(side, show="tree", height=3, selectmode="browse")
        self.tree.column("#0", width=300)
        self.tree.grid(sticky="ew")
        self.tree.bind("<Double-1>", lambda _e: self._use_selected())
        lb = ttk.Frame(side)
        lb.grid(sticky="ew", pady=(4, 0))
        for i in range(3):
            lb.columnconfigure(i, weight=1)
        ttk.Button(lb, text="Use", command=self._use_selected).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(lb, text="Rename", command=self._rename_selected).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(lb, text="Delete", command=self._delete_selected).grid(row=0, column=2, sticky="ew", padx=(4, 0))

        # --- bottom ---
        bot = ttk.Frame(side)
        bot.grid(sticky="ew", pady=(14, 0))
        for i in range(3):
            bot.columnconfigure(i, weight=1)
        ttk.Button(bot, text="Mini bar", command=self.show_minibar).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(bot, text="Settings", command=self.open_settings).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(bot, text="Setup guide", command=self.open_wizard).grid(row=0, column=2, sticky="ew", padx=(4, 0))
        ttk.Label(side, text=f"{brand.TAGLINE}   v{updater.current_version()}", style="Small.TLabel").grid(
            sticky="e", pady=(8, 0))

        self.status = tk.Label(r, text="", anchor="w", padx=14, pady=5, bg=SURFACE, fg=CLOUD, font=(FONT, 9))
        self.status.grid(row=1, column=0, columnspan=2, sticky="ew")

    # ---------- keys (hold-capable Space) ----------
    def _bind_keys(self) -> None:
        r = self.root
        r.bind_all("<KeyPress-space>", self._space_down)
        r.bind_all("<KeyRelease-space>", self._space_up)
        keys = {"r": "record", "b": "glitch", "c": "calibrate", "e": "end_recording", "u": "update", "k": "camera:"}
        for k, action in keys.items():
            for kk in (k, k.upper()):
                r.bind_all(f"<KeyPress-{kk}>", lambda _e, a=action: self._key_action(a))
        r.bind_all("<Escape>", lambda _e: self.e.request("cancel"))
        for kk in ("o", "O"):
            r.bind_all(f"<KeyPress-{kk}>", lambda _e: self._key_action("outlines"))
        for kk in ("m", "M"):
            r.bind_all(f"<KeyPress-{kk}>", lambda _e: None if self._typing() else self.show_minibar())
        for kk in ("g", "G"):
            r.bind_all(f"<KeyPress-{kk}>", lambda _e: None if self._typing() else self.toggle_guides())

    def _typing(self) -> bool:
        w = self.root.focus_get()
        return isinstance(w, (tk.Entry, ttk.Entry)) and not isinstance(w, ttk.Combobox)

    def _key_action(self, action: str) -> None:
        if not self._typing():
            self.e.request(action)

    def _space_down(self, _e=None):
        if self._typing():
            return None
        if self._pending_release is not None:  # auto-repeat: that "release" was fake
            self.root.after_cancel(self._pending_release)
            self._pending_release = None
            return "break"
        self.e.request("cut_press")
        return "break"

    def _space_up(self, _e=None):
        if self._typing():
            return None
        # Wait a moment: on some systems key auto-repeat sends release+press pairs.
        self._pending_release = self.root.after(40, self._space_released)
        return "break"

    def _space_released(self):
        self._pending_release = None
        self.e.request("cut_release")

    # ---------- actions ----------
    def toggle_guides(self):
        self.cfg.show_guides = not self.cfg.show_guides
        self.cfg.save(self.e.config_path)

    def apply_capture_setting(self) -> None:
        hide = self.cfg.hide_from_screen_share
        for w in (self.root, self.minibar and self.minibar.win, self.wizard and self.wizard.win,
                  self.settings and self.settings.win):
            if w is not None:
                try:
                    winutil.hide_from_capture(w, hide)
                except Exception:  # noqa: BLE001
                    pass

    def _refresh_cameras(self) -> None:
        self.cam_box["values"] = self.e.tray_cameras()

    def _selected_loop(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _use_selected(self) -> None:
        p = self._selected_loop()
        if p:
            self.e.request(f"use_loop:{p}")

    def _rename_selected(self) -> None:
        p = self._selected_loop()
        if not p:
            return
        name = simpledialog.askstring("Rename loop", "Name:", initialvalue=library.info(p).name, parent=self.root)
        if name is not None:
            library.rename(p, name)
            self.e.request("library_changed")

    def _delete_selected(self) -> None:
        p = self._selected_loop()
        if p and messagebox.askyesno("Delete loop", f"Delete \"{library.info(p).name}\"? This can't be undone.",
                                     parent=self.root):
            self.e.request(f"delete_loop:{p}")

    def _refresh_library(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for li in library.list_loops(self.cfg.loops_dir):
            if li.path not in self._thumbs:
                th = library.thumbnail(li.path, 96)
                if th is not None:
                    self._thumbs[li.path] = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(th, cv2.COLOR_BGR2RGB)))
            active = li.path == self.e.loop_path
            warn = library.lighting_warning(li.lighting, self.e.live_light)
            details = [f"{int(li.seconds)} s"] + (["in use"] if active else [])
            if warn:
                details.append(f"⚠ {library.lighting_short(warn)}")
            label = f"  {li.name}\n  " + "  ·  ".join(details)
            self.tree.insert("", "end", iid=li.path, text=label, image=self._thumbs.get(li.path, ""))
            if active:
                self.tree.selection_set(li.path)

    # ---------- refresh loop ----------
    def _on_preview_resize(self, ev) -> None:
        w, h = ev.width, ev.height
        pw = min(w, int(h * 16 / 9))
        self.e.preview_size = (max(64, pw - pw % 2), max(36, int(pw * 9 / 16) // 2 * 2))

    def tick(self) -> None:
        e = self.e
        if self._engine_thread is not None and not self._engine_thread.is_alive():
            self.root.destroy()
            return
        rgb = e.preview_rgb
        if rgb is not None and id(rgb) != self._last_preview_id:
            self._last_preview_id = id(rgb)
            if self.root.state() != "withdrawn":
                self._photo = ImageTk.PhotoImage(Image.fromarray(rgb))
                self.preview.configure(image=self._photo)
            if self.minibar is not None and self.minibar.visible:
                self.minibar.refresh(rgb)
        self._refresh_status()
        if self.wizard is not None:
            self.wizard.refresh()
        if self.settings is not None:
            self.settings.refresh()
        self.root.after(33, self.tick)

    def _refresh_status(self) -> None:
        e = self.e
        mode = e.mode
        self.state_lbl.configure(text=mode.upper(), bg=MODE_BG[mode], fg=MODE_FG[mode])
        if e.glitch.active and not self.glitch_lbl.winfo_ismapped():
            self.glitch_lbl.pack(side="left", padx=8)
        elif not e.glitch.active and self.glitch_lbl.winfo_ismapped():
            self.glitch_lbl.pack_forget()
        pct = int(e.sync * 100)
        insync = e.sync >= SYNC_THRESHOLD
        self.sync_bar.configure(value=pct, style="InSync.Horizontal.TProgressbar" if insync
                                else "Sync.Horizontal.TProgressbar")
        self.sync_pct.configure(text=f"{pct}%", foreground=AQUA if insync else MUTED)
        self.cut_btn.refresh()
        o = e.output
        if o.connected:
            name = "Doppleganger camera" if o.backend == "doppleganger" else "OBS Virtual Camera"
            self.out_lbl.configure(text=f"● Sending to {name}" + ("  ·  in use" if o.viewer_connected else ""),
                                   foreground=AQUA)
        else:
            self.out_lbl.configure(text=f"● Not sending to Zoom: {o.error}", foreground=DANGER)
        rec = e.recorder.state
        self.rec_btn.configure(text="Cancel recording" if e.recording_active else
                               ("Stitching..." if rec == State.PROCESSING else "Record loop"))
        if self.v_outlines.get() != self.cfg.show_outlines:
            self.v_outlines.set(self.cfg.show_outlines)
        warn = e.lighting_warning
        self.light_lbl.configure(text=f"⚠ {warn}" if warn else "")
        if e.library_version != self._lib_version:
            self._lib_version = e.library_version
            self._refresh_library()
        if self.cam_var.get() != e.camera_name:
            self.cam_var.set(e.camera_name)
        msg = e.message
        if e.mic.is_muted:
            msg = (msg + "   ·   " if msg else "") + "Microphone muted while the LOOP is on air"
        self.status.configure(text=msg)

    # ---------- other windows ----------
    def show_minibar(self) -> None:
        if self.minibar is None:
            self.minibar = MiniBar(self)
        self.minibar.show()
        self.root.withdraw()
        self.cfg.mini_bar = True
        self.cfg.save(self.e.config_path)

    def show_main(self) -> None:
        if self.minibar is not None:
            self.minibar.hide()
        self.root.deiconify()
        self.root.lift()
        self.cfg.mini_bar = False
        self.cfg.save(self.e.config_path)
        self.root.after(150, self.apply_capture_setting)

    def open_wizard(self) -> None:
        if self.wizard is None or not self.wizard.alive:
            self.wizard = Wizard(self)
        self.wizard.win.lift()

    def open_settings(self) -> None:
        if self.settings is None or not self.settings.alive:
            self.settings = SettingsWindow(self)
        self.settings.win.lift()

    # ---------- lifecycle ----------
    def on_close(self) -> None:
        if self.e.mode == "loop" and not messagebox.askyesno(
                "Quit Doppleganger?", "The LOOP is on air. Quitting stops the Doppleganger camera picture.\n\nQuit?",
                parent=self.root):
            return
        self.e.stop()

    def run(self) -> None:
        self._engine_thread = threading.Thread(target=self.e.run, daemon=True, name="engine")
        self._engine_thread.start()
        self.root.after(200, self.apply_capture_setting)
        self.root.after(33, self.tick)
        if self._start_minimized:
            self.root.after(300, self.root.iconify)  # started with Windows: stay out of the way
        elif self.cfg.mini_bar:
            self.root.after(300, self.show_minibar)
        if not self.cfg.setup_done:
            if self.e.player is not None and self.e.tray_driver_installed():
                self.cfg.setup_done = True  # already set up with an earlier version
                self.cfg.save(self.e.config_path)
            else:
                self.root.after(600, self.open_wizard)
        self.root.mainloop()
        self.e.stop()
        self._engine_thread.join(timeout=5)


class SettingsWindow:
    def __init__(self, main: MainWindow):
        self.main = main
        self.e = main.e
        self.cfg = main.cfg
        self.alive = True
        self.win = tk.Toplevel(main.root)
        self.win.title("Doppleganger settings")
        self.win.resizable(False, False)
        self.win.transient(main.root)
        self.win.configure(bg=MIDNIGHT)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        f = ttk.Frame(self.win, padding=20)
        f.pack(fill="both")
        ttk.Label(f, text="Settings", style="Title.TLabel").grid(sticky="w", pady=(0, 10))

        ttk.Label(f, text="Privacy", style="Head.TLabel").grid(sticky="w", pady=(4, 2))
        self.v_mute = tk.BooleanVar(value=self.cfg.mute_mic_on_loop)
        self.v_hide = tk.BooleanVar(value=self.cfg.hide_from_screen_share)
        ttk.Checkbutton(f, text="Mute my microphone while the LOOP is on air", variable=self.v_mute,
                        command=self._changed).grid(sticky="w")
        ttk.Checkbutton(f, text="Hide Doppleganger's windows from screen sharing", variable=self.v_hide,
                        command=self._changed).grid(sticky="w")

        ttk.Label(f, text="Cuts & preview", style="Head.TLabel").grid(sticky="w", pady=(12, 2))
        self.v_fade = tk.BooleanVar(value=self.cfg.crossfade_ms > 0)
        self.v_guides = tk.BooleanVar(value=self.cfg.show_guides)
        ttk.Checkbutton(f, text="Soft 0.3 s crossfade on cuts (off = hard cut)", variable=self.v_fade,
                        command=self._changed).grid(sticky="w")
        ttk.Checkbutton(f, text="Show alignment guides in the preview (G)", variable=self.v_guides,
                        command=self._changed).grid(sticky="w")
        self.v_outlines = tk.BooleanVar(value=self.cfg.show_outlines)
        ttk.Checkbutton(f, text="Show live (aqua) and loop (violet) outlines (O)", variable=self.v_outlines,
                        command=self._changed).grid(sticky="w")
        op = ttk.Frame(f)
        op.grid(sticky="ew", pady=(6, 0))
        ttk.Label(op, text="Overlay strength").pack(side="left")
        self.v_opacity = tk.DoubleVar(value=self.cfg.overlay_opacity)
        ttk.Scale(op, from_=0.15, to=0.6, variable=self.v_opacity, length=180,
                  command=lambda _v: self._changed()).pack(side="left", padx=10)

        ttk.Label(f, text="Hotkeys (work while Zoom is focused)", style="Head.TLabel").grid(sticky="w", pady=(12, 2))
        hk, gk = self.cfg.hotkey.strip("<>").upper(), self.cfg.glitch_hotkey.strip("<>").upper()
        ttk.Label(f, text=f"{hk}: tap = cut now, hold = cut when in sync     {gk}: fake a bad connection",
                  style="Small.TLabel").grid(sticky="w")

        ttk.Label(f, text="Finding you in the picture", style="Head.TLabel").grid(sticky="w", pady=(12, 2))
        cal = ttk.Frame(f)
        cal.grid(sticky="ew")
        how = ("AI person detection - no setup needed. Calibrating the room is an optional fallback."
               if self.e.seg is not None else "Room calibration (AI detection isn't available on this PC).")
        ttk.Label(cal, text=how, style="Small.TLabel", wraplength=330, justify="left").pack(side="left")
        ttk.Button(cal, text="Calibrate room", command=lambda: self.e.request("calibrate")).pack(side="right")

        ttk.Label(f, text="Doppleganger camera", style="Head.TLabel").grid(sticky="w", pady=(12, 2))
        self.v_startup = tk.BooleanVar(value=winutil.starts_with_windows())
        self.startup_chk = ttk.Checkbutton(
            f, text="Start Doppleganger (minimized) when Windows starts - so Zoom always gets a picture",
            variable=self.v_startup, command=self._startup_changed)
        self.startup_chk.grid(sticky="w")
        if winutil.startup_command() is None:
            self.startup_chk.state(["disabled"])
        cam = ttk.Frame(f)
        cam.grid(sticky="ew")
        self.drv_lbl = ttk.Label(cam, text="", style="Small.TLabel")
        self.drv_lbl.pack(side="left")
        self.drv_btn = ttk.Button(cam, text="Install", command=self._driver)
        self.drv_btn.pack(side="right")

        ttk.Label(f, text="Updates", style="Head.TLabel").grid(sticky="w", pady=(12, 2))
        up = ttk.Frame(f)
        up.grid(sticky="ew")
        ttk.Label(up, text=f"Version {updater.current_version()} · checks automatically when opened",
                  style="Small.TLabel").pack(side="left")
        ttk.Button(up, text="Check now", command=lambda: self.e.request("update")).pack(side="right")
        ttk.Button(f, text="Done", style="Accent.TButton", command=self.close).grid(sticky="e", pady=(16, 0))
        self.refresh()
        self.win.after(150, main.apply_capture_setting)

    def _changed(self) -> None:
        c = self.cfg
        mute_changed = c.mute_mic_on_loop != self.v_mute.get()
        hide_changed = c.hide_from_screen_share != self.v_hide.get()
        c.mute_mic_on_loop = self.v_mute.get()
        c.hide_from_screen_share = self.v_hide.get()
        c.show_guides = self.v_guides.get()
        c.show_outlines = self.v_outlines.get()
        c.crossfade_ms = 300 if self.v_fade.get() else 0
        c.overlay_opacity = round(float(self.v_opacity.get()), 2)
        c.save(self.e.config_path)
        if mute_changed:
            self.e.request("mic_setting")
        if hide_changed:
            self.main.apply_capture_setting()

    def _startup_changed(self) -> None:
        try:
            winutil.set_start_with_windows(self.v_startup.get())
        except OSError as ex:
            messagebox.showerror("Doppleganger", f"Couldn't change the startup setting: {ex}", parent=self.win)
            self.v_startup.set(winutil.starts_with_windows())

    def _driver(self) -> None:
        self.e.request("uninstall_driver" if self.e.tray_driver_installed() else "install_driver")

    def refresh(self) -> None:
        if not self.alive:
            return
        self.v_guides.set(self.cfg.show_guides)
        self.v_outlines.set(self.cfg.show_outlines)
        installed = self.e.tray_driver_installed()
        self.drv_lbl.configure(text="Installed ✓ - choose \"Doppleganger\" in Zoom" if installed
                               else "Not installed")
        self.drv_btn.configure(text="Remove" if installed else "Install",
                               state="normal" if (installed or self.e.tray_driver_available()) else "disabled")

    def close(self) -> None:
        self.alive = False
        self.win.destroy()
        self.main.settings = None


class MiniBar:
    """Compact always-on-top control strip to park beside Zoom."""

    TW, TH = 192, 108

    def __init__(self, main: MainWindow):
        self.main = main
        self.e = main.e
        self.win = tk.Toplevel(main.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=MIDNIGHT, highlightthickness=1, highlightbackground=BORDER)
        self.visible = False
        self._blank = ImageTk.PhotoImage(Image.new("RGB", (self.TW, self.TH), MIDNIGHT))
        self._photo = None
        f = tk.Frame(self.win, bg=MIDNIGHT, padx=8, pady=8)
        f.pack()
        self._mark = _photo(brand.asset("icon.png"), 22)
        grip = tk.Label(f, image=self._mark, bg=MIDNIGHT, cursor="fleur")
        grip.grid(row=0, column=0, sticky="n", padx=(0, 8))
        self.thumb = tk.Label(f, image=self._blank, bg=MIDNIGHT, bd=0)
        self.thumb.grid(row=0, column=1)
        right = tk.Frame(f, bg=MIDNIGHT)
        right.grid(row=0, column=2, sticky="ns", padx=(10, 0))
        self.state_lbl = tk.Label(right, text="LIVE", fg=MIDNIGHT, bg=AQUA, font=(FONT, 11, "bold"))
        self.state_lbl.pack(fill="x")
        self.sync = ttk.Progressbar(right, maximum=100, length=150, style="Sync.Horizontal.TProgressbar")
        self.sync.pack(fill="x", pady=5)
        self.cut = HoldButton(right, self.e, font_size=11)
        self.cut.configure(pady=6)
        self.cut.pack(fill="x")
        row = tk.Frame(right, bg=MIDNIGHT)
        row.pack(fill="x", pady=(5, 0))
        ttk.Button(row, text="Glitch", width=7, command=lambda: self.e.request("glitch")).pack(side="left")
        ttk.Button(row, text="Full view", width=9, command=main.show_main).pack(side="right")
        for w in (grip, self.thumb):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag)
            w.bind("<ButtonRelease-1>", self._drag_end)
        self.win.bind("<KeyPress-space>", main._space_down)
        self.win.bind("<KeyRelease-space>", main._space_up)
        self._place()

    def _place(self) -> None:
        pos = self.main.cfg.mini_bar_pos
        if not pos:
            self.win.update_idletasks()
            x = self.win.winfo_screenwidth() - self.win.winfo_reqwidth() - 24
            pos = f"+{max(0, x)}+60"
        self.win.geometry(pos)

    def _drag_start(self, ev):
        self._dx, self._dy = ev.x_root - self.win.winfo_x(), ev.y_root - self.win.winfo_y()

    def _drag(self, ev):
        self.win.geometry(f"+{ev.x_root - self._dx}+{ev.y_root - self._dy}")

    def _drag_end(self, _ev):
        self.main.cfg.mini_bar_pos = f"+{self.win.winfo_x()}+{self.win.winfo_y()}"
        self.main.cfg.save(self.e.config_path)

    def show(self) -> None:
        self.win.deiconify()
        self.visible = True
        self.win.after(150, self.main.apply_capture_setting)

    def hide(self) -> None:
        self.win.withdraw()
        self.visible = False

    def refresh(self, rgb) -> None:
        e = self.e
        mode = "glitch" if e.glitch.active else e.mode
        self.state_lbl.configure(text=mode.upper(), bg=MODE_BG[mode], fg=MODE_FG[mode])
        insync = e.sync >= SYNC_THRESHOLD
        self.sync.configure(value=int(e.sync * 100),
                            style="InSync.Horizontal.TProgressbar" if insync else "Sync.Horizontal.TProgressbar")
        self.cut.refresh(short=True)
        if rgb is not None:
            small = cv2.resize(rgb, (self.TW, self.TH), interpolation=cv2.INTER_AREA)
            self._photo = ImageTk.PhotoImage(Image.fromarray(small))
            self.thumb.configure(image=self._photo)


class Wizard:
    """First-run setup: camera -> webcam -> calibrate -> first loop -> Zoom."""

    STEPS = ("welcome", "camera", "webcam", "calibrate", "record", "zoom")

    def __init__(self, main: MainWindow):
        self.main = main
        self.e = main.e
        if self.e.seg is not None:  # AI detection finds you without calibrating the room
            self.STEPS = tuple(s for s in self.STEPS if s != "calibrate")
        self.win = tk.Toplevel(main.root)
        self.win.title("Doppleganger setup")
        self.win.resizable(False, False)
        self.win.transient(main.root)
        self.win.configure(bg=MIDNIGHT)
        self.alive = True
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.step = 0
        self._logo = _photo(brand.asset("logo_dark.png"), 330)
        self.body = ttk.Frame(self.win, padding=24, width=480, height=350)
        self.body.pack(fill="both", expand=True)
        self.body.pack_propagate(False)
        nav = ttk.Frame(self.win, padding=(24, 0, 24, 18))
        nav.pack(fill="x")
        self.dots = tk.Label(nav, bg=MIDNIGHT, fg=MUTED, font=(FONT, 10))
        self.dots.pack(side="left")
        self.next_btn = ttk.Button(nav, text="Next", style="Accent.TButton", command=self.next)
        self.next_btn.pack(side="right")
        self.back_btn = ttk.Button(nav, text="Back", command=self.back)
        self.back_btn.pack(side="right", padx=6)
        self.skip_btn = ttk.Button(nav, text="Skip setup", command=self.finish)
        self.skip_btn.pack(side="right", padx=6)
        self.status = None
        self.render()
        main.root.update_idletasks()
        self.win.geometry(f"+{main.root.winfo_rootx() + 40}+{main.root.winfo_rooty() + 60}")
        self.win.after(150, main.apply_capture_setting)

    # --- navigation ---
    def next(self):
        if self.step >= len(self.STEPS) - 1:
            self.finish()
            return
        self.step += 1
        self.render()

    def back(self):
        if self.step > 0:
            self.step -= 1
            self.render()

    def finish(self):
        self.main.cfg.setup_done = True
        self.main.cfg.save(self.e.config_path)
        self.close()

    def close(self):
        self.alive = False
        self.win.destroy()
        self.main.wizard = None

    # --- pages ---
    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()
        self.status = None

    def _title(self, text):
        ttk.Label(self.body, text=text, style="Title.TLabel").pack(anchor="w", pady=(0, 12))

    def _para(self, text):
        ttk.Label(self.body, text=text, wraplength=430, justify="left").pack(anchor="w", pady=(0, 9))

    def _button(self, text, action):
        ttk.Button(self.body, text=text, style="Accent.TButton", command=lambda: self.e.request(action)).pack(
            anchor="w", pady=(4, 0))

    def _status(self):
        self.status = ttk.Label(self.body, text="", wraplength=430, justify="left")
        self.status.pack(anchor="w", pady=(12, 0))

    def render(self):
        self._clear()
        getattr(self, f"_page_{self.STEPS[self.step]}")()
        self.dots.configure(text="  ".join("●" if i == self.step else "○" for i in range(len(self.STEPS))))
        self.back_btn.configure(state="normal" if self.step else "disabled")
        last = self.step == len(self.STEPS) - 1
        self.next_btn.configure(text="Finish" if last else "Next")
        if last:
            self.skip_btn.pack_forget()
        self.refresh()

    def _page_welcome(self):
        tk.Label(self.body, image=self._logo, bg=MIDNIGHT).pack(anchor="w", pady=(4, 18))
        self._para("Doppleganger records a short, seamless loop of you, then lets you switch between "
                   "that loop and your live webcam during a meeting - without anyone noticing.")
        self._para("This guide takes about 2 minutes: add the camera, pick your webcam, "
                   "and record your first loop.")

    def _page_camera(self):
        self._title("1  Add the Doppleganger camera")
        self._para("This adds a camera named \"Doppleganger\" that Zoom, Teams and browsers can use. "
                   "Windows asks for permission once.")
        self._button("Install camera", "install_driver")
        self._status()

    def _page_webcam(self):
        self._title("2  Choose your webcam")
        self._para("Pick the webcam you want people to see. You should see yourself in the main window.")
        var = tk.StringVar(value=self.e.camera_name)
        box = ttk.Combobox(self.body, textvariable=var, state="readonly", values=self.e.tray_cameras(), width=42)
        box.pack(anchor="w")
        box.bind("<<ComboboxSelected>>", lambda _e: self.e.request(f"camera:{var.get()}"))

    def _page_calibrate(self):
        self._title("3  Calibrate your silhouette")
        self._para("For about 10 seconds, keep facing the camera and lean or step slowly to the side the "
                   "preview asks for. Doppleganger learns what your room looks like without you, so it can "
                   "outline you precisely.")
        self._button("Start calibration", "calibrate")
        self._status()

    def _page_record(self):
        self._title(f"{self.STEPS.index('record')}  Record your first loop")
        self._para("Sit as you would in a meeting. Hold still for the first 10 seconds, then look natural - "
                   "nod, blink, glance at the screen. In the last 10 seconds, step back into your silhouette "
                   "until it glows aqua, and hold still.")
        self.rec_button = ttk.Button(self.body, text="Start recording", style="Accent.TButton",
                                     command=lambda: self.e.request("record"))
        self.rec_button.pack(anchor="w", pady=(4, 0))
        self._status()

    def _page_zoom(self):
        self._title(f"{self.STEPS.index('zoom')}  Use it in your meeting")
        hk = self.main.cfg.hotkey.strip("<>").upper()
        gk = self.main.cfg.glitch_hotkey.strip("<>").upper()
        self._para("In Zoom: Settings → Video → Camera → \"Doppleganger\".  In Teams: Settings → Devices → Camera.")
        self._para(f"Tap {hk} to cut instantly. Hold {hk} and Doppleganger cuts by itself the moment you're in "
                   f"sync. {gk} fakes a bad connection if you're called on unexpectedly.")
        self._para("While the loop is on air your microphone is muted, and Doppleganger never appears in "
                   "screen shares. The Mini bar keeps the controls beside Zoom.")
        if winutil.startup_command() is not None:
            self._startup = tk.BooleanVar(value=winutil.starts_with_windows())
            ttk.Checkbutton(self.body, text="Start Doppleganger when Windows starts (recommended - Zoom then "
                            "always gets a picture)", variable=self._startup,
                            command=lambda: winutil.set_start_with_windows(self._startup.get())).pack(
                anchor="w", pady=(6, 0))

    def refresh(self):
        if not self.alive or self.status is None:
            return
        e = self.e
        page = self.STEPS[self.step]
        txt, col = "", CLOUD
        if page == "camera":
            if e.tray_driver_installed():
                txt, col = "✓ Installed - you can choose \"Doppleganger\" in Zoom.", AQUA
            elif not e.tray_driver_available():
                txt, col = "The camera comes with the installed app. (From source, OBS Virtual Camera is used.)", MUTED
            else:
                txt = e.message or "Not installed yet."
        elif page == "calibrate":
            if e.calibrator is not None:
                txt = f"Calibrating... {int(e.calibrator.coverage * 100)}% of the room seen"
            elif e.background is not None:
                txt, col = "✓ Calibrated.", AQUA
        elif page == "record":
            self.rec_button.configure(text="Cancel recording" if e.recording_active else "Start recording")
            st = e.recorder.state
            if st in (State.COUNTDOWN, State.RECORDING):
                txt = f"Recording... {int(e.recorder.elapsed)} / {int(e.cfg.loop_seconds)} s"
            elif st == State.PROCESSING:
                txt = "Stitching your loop..."
            elif e.player is not None:
                txt, col = "✓ You have a loop. Record more any time.", AQUA
        self.status.configure(text=txt, foreground=col)


def run_startup_update(rel, token: str) -> str | None:
    """Small 'Updating...' window while the new version downloads. Returns the downloaded path."""
    root = tk.Tk()
    root.title("Doppleganger")
    root.resizable(False, False)
    apply_theme(root)
    f = ttk.Frame(root, padding=22)
    f.pack()
    logo = _photo(brand.asset("logo_dark.png"), 260)
    tk.Label(f, image=logo, bg=MIDNIGHT).pack(anchor="w", pady=(0, 12))
    ttk.Label(f, text=f"Updating to v{rel.version}...", style="Head.TLabel").pack(anchor="w")
    bar = ttk.Progressbar(f, maximum=100, length=360, style="InSync.Horizontal.TProgressbar")
    bar.pack(pady=(10, 0))
    result: dict = {}

    def work():
        try:
            result["path"] = updater.download(rel, token, lambda p: result.__setitem__("p", p))
        except updater.UpdateError as ex:
            result["err"] = str(ex)

    t = threading.Thread(target=work, daemon=True)
    t.start()

    def poll():
        bar["value"] = int(result.get("p", 0) * 100)
        if t.is_alive():
            root.after(100, poll)
        else:
            root.destroy()

    root.after(100, poll)
    root.mainloop()
    return result.get("path")
