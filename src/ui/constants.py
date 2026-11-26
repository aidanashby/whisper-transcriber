"""
Single source of truth for all visual constants, timings, and layout values.
Nothing in the rest of the codebase should hard-code these values.

Dark grey panels after Audacity 4, with the icon's green for main actions.
Every text and button colour pair meets WCAG AA (4.5:1) on its background:
green on the panel is 5.7:1, dark text on green 7.7:1.
"""

# ── Layout ───────────────────────────────────────────────────────────────────

MIN_WINDOW_WIDTH      = 640
MIN_WINDOW_HEIGHT     = 420
DEFAULT_WINDOW_WIDTH  = 900
DEFAULT_WINDOW_HEIGHT = 560
DEFAULT_SIDEBAR_WIDTH = 300
MIN_SIDEBAR_WIDTH     = 220
MIN_VIEWER_WIDTH      = 320

# ── Timing (milliseconds) ────────────────────────────────────────────────────

QUEUE_POLL_MS          = 50    # how often the UI thread drains the worker queue
COPIED_REVERT_MS       = 1500  # "Copied!" → "Copy" delay
REJECT_MSG_DURATION_MS = 3000  # how long the "non-WAV ignored" message shows
PLAYER_TICK_MS         = 100   # playhead refresh while playing

# ── Palette ──────────────────────────────────────────────────────────────────

APP_BG        = "#1b1e23"   # gaps between panels
PANEL_BG      = "#2c3037"   # panels, toolbars, title bar
FIELD_BG      = "#1f2227"   # lists, text and entry boxes
BORDER        = "#4a505a"
COLOR_BODY    = "#f1f3f5"
COLOR_MUTED   = "#b0b7c1"
ACCENT        = "#34c26b"   # the icon's green ("Leaf")
ACCENT_HOVER  = "#4fd283"
ACCENT_TEXT   = "#0f1a13"   # text on green
SLATE         = "#474d57"   # secondary buttons
SLATE_HOVER   = "#59606b"
DANGER_TEXT   = "#ffb3bb"   # error text and delete hover
DISABLED_BG   = "#353a42"
DISABLED_TEXT = "#8a919c"
SCROLL        = "#6b727d"
SCROLL_HOVER  = "#8a919c"
ROW_HOVER     = "#262a30"
ROW_SELECTED  = "#23402f"   # FIELD_BG mixed 22% towards ACCENT
FLASH_BG      = "#2f5a3e"   # newly streamed text

# Kept names used across the UI.
BTN_START_COLOR  = ACCENT
BTN_START_HOVER  = ACCENT_HOVER
BTN_NEUTRAL_COLOR = SLATE
BTN_NEUTRAL_HOVER = SLATE_HOVER
BTN_DANGER_COLOR = "#c62f3f"   # white text 5.3:1
BTN_DANGER_HOVER = "#d94352"

# ── Typography ───────────────────────────────────────────────────────────────

FONT_BODY    = ("Segoe UI", 12)
FONT_BOLD    = ("Segoe UI", 12, "bold")
FONT_HEADING = ("Segoe UI", 14, "bold")
FONT_SMALL   = ("Segoe UI", 10)
FONT_TINY    = ("Segoe UI", 8)    # folder line under each file name
FONT_TEXT    = ("Segoe UI", 13)   # the transcript itself
FONT_PENDING = ("Segoe UI", 13)

COLOR_PENDING = COLOR_BODY

# ── Transcription paragraph formatting ───────────────────────────────────────

# Silence gap (seconds) between Whisper segments that triggers a new paragraph
PARAGRAPH_GAP = 1.5
