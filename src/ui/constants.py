"""
Single source of truth for all visual constants, timings, and layout values.
Nothing in the rest of the codebase should hard-code these values.
"""

# ── Layout ───────────────────────────────────────────────────────────────────

LEFT_PANEL_WEIGHT  = 1   # grid weight — left panel takes 1 share
RIGHT_PANEL_WEIGHT = 2   # grid weight — right panel takes 2 shares
MIN_WINDOW_WIDTH   = 960
MIN_WINDOW_HEIGHT  = 580
DEFAULT_WINDOW_WIDTH  = 1150
DEFAULT_WINDOW_HEIGHT = 700

# ── Timing (milliseconds) ────────────────────────────────────────────────────

ANIMATION_DURATION_MS = 200   # row background colour transition
ANIMATION_STEPS       = 20    # → ~10 ms per step ≈ smooth 100 fps
QUEUE_POLL_MS         = 50    # how often the UI thread drains the worker queue
COPIED_REVERT_MS      = 1500  # "Copied!" → "Copy to clipboard" delay
REJECT_MSG_DURATION_MS = 3000  # how long the "non-WAV ignored" message shows

# ── Row state colours ────────────────────────────────────────────────────────

ROW_IDLE       = "#FAFAFA"   # at rest / white-ish
ROW_PROCESSING = "#FFFDE7"   # light yellow — in progress
ROW_COMPLETE   = "#E8F5E9"   # light green  — done
ROW_ERROR      = "#FFCDD2"   # light red    — error / file not found
ROW_CANCELLED  = "#F5F5F5"   # light grey   — user stopped

# ── Drop-zone ────────────────────────────────────────────────────────────────

DROP_NORMAL_BG     = "#F8F8F8"
DROP_NORMAL_BORDER = "#CCCCCC"
DROP_HOVER_BG      = "#F0FFF4"
DROP_HOVER_BORDER  = "#43A047"

# ── Button colours ───────────────────────────────────────────────────────────

BTN_START_COLOR   = "#43A047"
BTN_START_HOVER   = "#388E3C"
BTN_DANGER_COLOR  = "#E53935"
BTN_DANGER_HOVER  = "#C62828"
BTN_NEUTRAL_COLOR = "#546E7A"
BTN_NEUTRAL_HOVER = "#37474F"
BTN_ACTION_COLOR  = "#1976D2"
BTN_ACTION_HOVER  = "#1565C0"

# ── Application background / panel colours ───────────────────────────────────

APP_BG   = "#EEEEEE"
PANEL_BG = "#FFFFFF"

# ── Typography ───────────────────────────────────────────────────────────────

FONT_BODY    = ("Segoe UI", 12)
FONT_BOLD    = ("Segoe UI", 12, "bold")
FONT_HEADING = ("Segoe UI", 15, "bold")
FONT_SMALL   = ("Segoe UI", 10)
FONT_MONO    = ("Consolas", 11)

COLOR_MUTED = "#888888"
COLOR_BODY  = "#1A1A1A"

# ── Transcription paragraph formatting ───────────────────────────────────────

# Silence gap (seconds) between Whisper segments that triggers a new paragraph
PARAGRAPH_GAP = 1.5
