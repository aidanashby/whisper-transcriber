"""
Window chrome shared by every window: the CustomTkinter theme, the slim
custom title bar, Windows' own title bar recoloured for dialogs, icon fonts,
and centring pop-ups over the main window.

TitleBar and the snap fix are ported from yt-slurp (yt_slurp_gui.py), which
has the reasoning and the mixed-DPI papercut behind them.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

import customtkinter as ctk

from .constants import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_TEXT,
    BORDER,
    BTN_DANGER_COLOR,
    COLOR_BODY,
    COLOR_MUTED,
    DISABLED_TEXT,
    FIELD_BG,
    PANEL_BG,
    SCROLL,
    SCROLL_HOVER,
    SLATE,
    SLATE_HOVER,
)

APP_NAME = "Whisper Transcriber"


def asset_path(name: str) -> Path:
    """assets/<name>, inside the bundle when frozen by PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "assets" / name


def apply_theme() -> None:
    """Dark mode with the app's colours as CustomTkinter's defaults, so
    widgets only pass colours when they differ (secondary buttons)."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
    t = ctk.ThemeManager.theme

    def put(widget, **kw):
        # "transparent" must stay a plain string; colours are (light, dark) pairs.
        t[widget].update({k: v if v == "transparent" else [v, v] for k, v in kw.items()})

    put("CTk", fg_color=PANEL_BG)
    put("CTkToplevel", fg_color=PANEL_BG)
    put("CTkFrame", fg_color=PANEL_BG, top_fg_color=PANEL_BG, border_color=BORDER)
    put("CTkButton", fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
        text_color_disabled=DISABLED_TEXT, border_color=BORDER)
    t["CTkButton"]["corner_radius"] = 4
    put("CTkLabel", text_color=COLOR_BODY)
    put("CTkEntry", fg_color=FIELD_BG, border_color=BORDER, text_color=COLOR_BODY,
        placeholder_text_color=COLOR_MUTED)
    t["CTkEntry"]["corner_radius"] = 4
    put("CTkTextbox", fg_color=FIELD_BG, border_color=BORDER, text_color=COLOR_BODY,
        scrollbar_button_color=SCROLL, scrollbar_button_hover_color=SCROLL_HOVER)
    put("CTkScrollbar", fg_color="transparent", button_color=SCROLL, button_hover_color=SCROLL_HOVER)
    put("CTkScrollableFrame", label_fg_color=PANEL_BG)
    put("CTkRadioButton", fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=COLOR_MUTED,
        text_color=COLOR_BODY, text_color_disabled=DISABLED_TEXT)
    put("CTkProgressBar", fg_color=FIELD_BG, progress_color=ACCENT, border_color=BORDER)
    put("CTkOptionMenu", fg_color=SLATE, button_color=SLATE, button_hover_color=SLATE_HOVER,
        text_color=COLOR_BODY)


def icon_font(size: int):
    """Windows' icon font, or None on PCs without it (use plain characters)."""
    families = tkfont.families()
    family = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None)
    return (family, size) if family else None


def window_handle(win) -> int:
    import ctypes
    from ctypes import wintypes
    get = ctypes.windll.user32.GetParent
    get.argtypes, get.restype = [wintypes.HWND], wintypes.HWND
    return get(win.winfo_id())


def dark_title_bar(win) -> None:
    """Windows' own title bar in the panel colour (Windows 11), or plain dark (Windows 10)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        win.update_idletasks()
        hwnd = wintypes.HWND(window_handle(win))

        def bgr(colour):
            r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
            return b << 16 | g << 8 | r
        # dark mode, border colour, caption colour, caption text
        for attr, value in ((20, 1), (34, bgr(BORDER)), (35, bgr(PANEL_BG)), (36, bgr(COLOR_BODY))):
            v = ctypes.c_int(value)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)
    except (AttributeError, OSError, tk.TclError):
        pass


def place_over(top, parent) -> None:
    """Size a pop-up to its content and centre it over *parent*, so it opens
    on whichever screen the main window is on."""
    try:
        top.update_idletasks()
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 3
        # wm geometry directly: CTkToplevel.geometry() would rescale the numbers
        top.wm_geometry(f"{w}x{h}+{x}+{y}")
    except tk.TclError:
        pass


def style_dialog(top) -> None:
    """Dark caption and the app icon on a CTkToplevel. CTkToplevel sets its
    own icon 200 ms after creation, so this runs after that."""
    def apply():
        try:
            top.iconbitmap(str(asset_path("icon.ico")))
        except tk.TclError:
            pass
        dark_title_bar(top)
    top.after(250, apply)


SNAP_FRAME = 7  # the invisible resize border below the visible window
EDGE_GRIP = 6   # px at the left and right edges that resize the window


def snap_fix(window, work, pointer):
    """Where a snapped window should be if it landed outside the screen it was
    dropped on (work is that screen without its taskbar), or None if it is fine."""
    left, top, right, bottom = work
    slack = 24
    if (window[0] >= left - slack and window[1] >= top - slack and window[2] <= right + slack
            and window[3] <= bottom + slack):
        return None
    mid_x, mid_y = (left + right) // 2, (top + bottom) // 2
    x1, x2 = (left, mid_x) if pointer[0] < mid_x else (mid_x, right)
    # Dropped in a corner means a quarter of the screen
    corner = (bottom - top) // 12
    y1, y2 = (top, mid_y) if pointer[1] < top + corner else (mid_y, bottom) if pointer[1] > bottom - corner \
        else (top, bottom)
    # No invisible border at the sides (TitleBar.strip removes it), so the
    # edges can sit exactly on a screen join: a window edge even slightly on
    # the next screen would be scaled as if the window were all there.
    return x1, y1, x2, y2 + SNAP_FRAME


class TitleBar(tk.Frame):
    """A slim title bar for the main window, in place of Windows' own."""

    HEIGHT = 30

    def __init__(self, root, icon):
        super().__init__(root, bg=PANEL_BG, height=self.HEIGHT)
        self.root = root
        self.old_proc = 0
        self.pack_propagate(False)
        grips = [self]
        if icon is not None:
            self.icon = icon.subsample(max(1, icon.width() // 18))
            grips.append(tk.Label(self, image=self.icon, bg=PANEL_BG))
            grips[-1].pack(side="left", padx=(10, 6))
        grips.append(tk.Label(self, text=APP_NAME, bg=PANEL_BG, fg=COLOR_BODY, font=("Segoe UI", 9)))
        grips[-1].pack(side="left", padx=(0 if icon is not None else 10, 0))
        for w in grips:
            w.bind("<Button-1>", self.drag)
            w.bind("<Double-Button-1>", lambda e: self.toggle())
            w.bind("<Motion>", lambda e: e.widget.configure(cursor="size_ns" if self.on_top_edge(e) else ""))
        font = icon_font(8)
        self.buttons = {}
        for name, icon_char, plain, command in (
                ("Close", "", "×", self.close), ("Maximise", "", "□", self.toggle),
                ("Minimise", "", "–", root.iconify)):
            b = tk.Label(self, text=icon_char if font else plain, bg=PANEL_BG, fg=COLOR_BODY, width=5,
                         font=font or ("Segoe UI", 10))
            b.pack(side="right", fill="y")
            hover = BTN_DANGER_COLOR if name == "Close" else SLATE
            b.bind("<Enter>", lambda e, h=hover: e.widget.configure(bg=h))
            b.bind("<Leave>", lambda e: e.widget.configure(bg=PANEL_BG))
            b.bind("<ButtonRelease-1>", lambda e, run=command: run()
                   if 0 <= e.x < e.widget.winfo_width() and 0 <= e.y < e.widget.winfo_height() else None)
            self.buttons[name] = b
        self.glyphs = ("", "") if font else ("□", "❐")
        root.bind("<Motion>", self.edge_cursor, add="+")
        root.bind("<Button-1>", self.edge_drag, add="+")
        root.bind("<Map>", lambda e: e.widget is root and self.strip(), add="+")
        root.bind("<Configure>", lambda e: e.widget is root and self.show_state(), add="+")

    def strip(self):
        """Hide Windows' caption by giving its space to the window. The caption
        style stays, so Windows still animates, snaps and maximises as usual.
        The invisible side borders go too, so a snapped window's visible edge
        is its real edge (see snap_fix); the window's own margin resizes it
        from the sides instead (edge_drag)."""
        if self.old_proc:
            return
        import ctypes
        from ctypes import wintypes as w
        u = self.user32 = ctypes.WinDLL("user32")  # own copy, so these types affect nothing else
        ptr = ctypes.c_ssize_t
        u.GetWindowLongPtrW.argtypes, u.GetWindowLongPtrW.restype = [w.HWND, ctypes.c_int], ptr
        u.SetWindowLongPtrW.argtypes, u.SetWindowLongPtrW.restype = [w.HWND, ctypes.c_int, ptr], ptr
        u.CallWindowProcW.argtypes, u.CallWindowProcW.restype = [ptr, w.HWND, ctypes.c_uint, w.WPARAM, w.LPARAM], ptr
        u.SetWindowPos.argtypes = [w.HWND, w.HWND] + [ctypes.c_int] * 4 + [ctypes.c_uint]
        u.PostMessageW.argtypes = [w.HWND, ctypes.c_uint, w.WPARAM, w.LPARAM]
        u.IsZoomed.argtypes = [w.HWND]
        hwnd = self.hwnd = window_handle(self.root)
        old = u.GetWindowLongPtrW(hwnd, -4)  # GWLP_WNDPROC

        @ctypes.WINFUNCTYPE(ptr, w.HWND, ctypes.c_uint, w.WPARAM, w.LPARAM)
        def proc(h, msg, wp, lp):
            if msg != 0x83 or not wp:  # WM_NCCALCSIZE
                return u.CallWindowProcW(old, h, msg, wp, lp)
            rect = w.RECT.from_address(lp)
            left, top, right = rect.left, rect.top, rect.right
            u.CallWindowProcW(old, h, msg, wp, lp)
            if u.IsZoomed(h):
                # Maximised windows hang over the screen edge by the frame's width
                rect.top = top + u.GetSystemMetrics(33) + u.GetSystemMetrics(92)
            else:
                rect.top, rect.left, rect.right = top, left, right
            return 0
        self.proc, self.old_proc = proc, old  # kept, or Windows would call freed memory
        u.SetWindowLongPtrW(hwnd, -4, ctypes.cast(proc, ctypes.c_void_p).value)
        u.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x37)  # same place and size, frame changed
        self.bind("<Destroy>", lambda e: e.widget is self and self.unstrip())

    def unstrip(self):
        if self.old_proc:
            self.user32.SetWindowLongPtrW(self.hwnd, -4, self.old_proc)
            self.old_proc = 0

    def side_edge(self, e):
        """HT code for the resize edge under the pointer, or None. Only the
        root's own margin counts, so widgets near the edge keep their clicks."""
        if e.widget is not self.root or self.root.state() == "zoomed":
            return None
        w, h = self.root.winfo_width(), self.root.winfo_height()
        side = "left" if e.x < EDGE_GRIP else "right" if e.x >= w - EDGE_GRIP else None
        if side is None:
            return None
        bottom = e.y >= h - EDGE_GRIP * 2
        return {("left", False): 10, ("right", False): 11, ("left", True): 16, ("right", True): 17}[side, bottom]

    def edge_cursor(self, e):
        code = self.side_edge(e)
        if e.widget is self.root:
            self.root.configure(cursor={10: "size_we", 11: "size_we", 16: "size_ne_sw", 17: "size_nw_se"}.get(code, ""))

    def edge_drag(self, e):
        code = self.side_edge(e)
        if code and self.old_proc:
            self.user32.ReleaseCapture()
            self.user32.PostMessageW(self.hwnd, 0xA1, code, (e.y_root & 0xFFFF) << 16 | (e.x_root & 0xFFFF))

    def on_top_edge(self, e) -> bool:
        return e.y_root - self.winfo_rooty() < 5 and self.root.state() != "zoomed"

    def drag(self, e):
        """Hand the drag to Windows, so snapping works. Posted, not sent: a
        sent one would run Windows' move loop inside this callback."""
        if self.old_proc:
            self.user32.ReleaseCapture()
            # WM_NCLBUTTONDOWN on HTTOP (resize) or HTCAPTION (move)
            self.user32.PostMessageW(self.hwnd, 0xA1, 12 if self.on_top_edge(e) else 2,
                                     (e.y_root & 0xFFFF) << 16 | (e.x_root & 0xFFFF))
            if not self.on_top_edge(e):
                self.after(150, self.after_drag)

    def after_drag(self):
        if self.user32.GetAsyncKeyState(2 if self.user32.GetSystemMetrics(23) else 1) & 0x8000:  # still held
            self.after(150, self.after_drag)
        else:
            self.after(350, self.fix_snap)  # once Windows has finished moving it

    def fix_snap(self):
        """Windows misplaces a window snapped on a screen whose scaling differs
        from the one most of the window was on. Put it where it was dropped."""
        import ctypes
        from ctypes import wintypes as w
        u = self.user32
        if not hasattr(u, "SetThreadDpiAwarenessContext") or not hasattr(u, "IsWindowArranged"):
            return  # too old for this
        u.IsWindowArranged.argtypes = [w.HWND]
        u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        u.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
        u.MonitorFromPoint.argtypes, u.MonitorFromPoint.restype = [w.POINT, w.DWORD], w.HMONITOR
        u.GetMonitorInfoW.argtypes = [w.HMONITOR, ctypes.c_void_p]
        if not u.IsWindowArranged(self.hwnd):
            return
        before = u.SetThreadDpiAwarenessContext(-4)  # real pixels on every screen
        try:
            p, r, info = w.POINT(), w.RECT(), (w.DWORD * 10)(40)
            u.GetCursorPos(ctypes.byref(p))
            u.GetWindowRect(self.hwnd, ctypes.byref(r))
            u.GetMonitorInfoW(u.MonitorFromPoint(p, 2), info)
            fix = snap_fix((r.left, r.top, r.right, r.bottom), tuple(ctypes.c_int32(v).value for v in info[5:9]),
                           (p.x, p.y))
            if fix:
                u.SetWindowPos(self.hwnd, None, fix[0], fix[1], fix[2] - fix[0], fix[3] - fix[1], 0x14)
        finally:
            u.SetThreadDpiAwarenessContext(before)

    def toggle(self):
        self.root.state("normal" if self.root.state() == "zoomed" else "zoomed")

    def show_state(self):
        self.buttons["Maximise"].configure(text=self.glyphs[self.root.state() == "zoomed"])

    def close(self):
        self.root.tk.call(*self.root.tk.splitlist(self.root.protocol("WM_DELETE_WINDOW")))
