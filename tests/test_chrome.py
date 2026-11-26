from src.ui.chrome import SNAP_FRAME, snap_fix

# Second screen to the right of the laptop, as on the Gigabyte Aero.
WORK = (2560, 0, 4480, 1152)


def test_window_inside_the_screen_needs_no_fix():
    assert snap_fix((2600, 10, 3400, 900), WORK, (3000, 500)) is None


def test_left_half_starts_exactly_on_the_screen_join():
    fix = snap_fix((1702, 0, 3527, 1159), WORK, (2570, 500))
    assert fix == (2560, 0, 3520, 1152 + SNAP_FRAME)


def test_top_right_quarter():
    fix = snap_fix((1702, 0, 3527, 1159), WORK, (4470, 5))
    assert fix == (3520, 0, 4480, 576 + SNAP_FRAME)


# Swapped layout: the second screen sits to the left, so its x is negative.
LEFT_WORK = (-1920, 0, 0, 1152)


def test_right_half_ends_exactly_on_the_join_when_screens_are_swapped():
    fix = snap_fix((-960, 0, 900, 1159), LEFT_WORK, (-5, 500))
    assert fix == (-960, 0, 0, 1152 + SNAP_FRAME)


def test_left_half_of_laptop_starts_on_the_join_when_screens_are_swapped():
    laptop = (0, 0, 2560, 1528)
    fix = snap_fix((-700, 0, 1280, 1535), laptop, (5, 700))
    assert fix == (0, 0, 1280, 1528 + SNAP_FRAME)
