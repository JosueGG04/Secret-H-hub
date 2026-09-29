"""The paging arithmetic, independent of any request."""

import pytest

from secret_hitler.pagination import PER_PAGE, Page, valid_page


@pytest.mark.parametrize("raw, expected", [
    ("3", 3), ("1", 1), (3, 3),
    ("0", 1), ("-4", 1),          # below the first page
    ("garbage", 1), ("", 1), (None, 1), ("2.5", 1),
])
def test_valid_page_rejects_anything_but_a_positive_int(raw, expected):
    assert valid_page(raw) == expected


@pytest.mark.parametrize("total, pages", [
    (0, 1),      # an empty list is still one (empty) page
    (1, 1),
    (10, 1),     # exactly one full page
    (11, 2),
    (20, 2),     # exact multiple
    (21, 3),
])
def test_page_count(total, pages):
    assert Page(1, total).pages == pages


@pytest.mark.parametrize("asked, landed", [
    (1, 1), (2, 2), (3, 3),
    (4, 3), (99, 3),      # past the end clamps to the last real page
    (0, 1), (-7, 1),
])
def test_the_number_is_clamped_into_range(asked, landed):
    """A stale ?page=7 left over after games were deleted must not render
    an empty page."""
    assert Page(asked, 21).number == landed


def test_offset_and_item_range_line_up():
    assert [(Page(n, 21).offset, Page(n, 21).first_item, Page(n, 21).last_item)
            for n in (1, 2, 3)] == [(0, 1, 10), (10, 11, 20), (20, 21, 21)]


def test_an_empty_list_reports_no_items():
    p = Page(1, 0)
    assert (p.offset, p.first_item, p.last_item) == (0, 0, 0)


def test_the_ends_know_they_are_the_ends():
    first, middle, last = Page(1, 21), Page(2, 21), Page(3, 21)
    assert (first.has_prev, first.has_next) == (False, True)
    assert (middle.has_prev, middle.has_next) == (True, True)
    assert (last.has_prev, last.has_next) == (True, False)
    # prev/next never point outside the range, even where the button is disabled.
    assert first.prev == 1 and last.next == 3


def test_a_single_page_has_no_neighbours():
    only = Page(1, 4)
    assert (only.has_prev, only.has_next) == (False, False)
    assert only.window == [1]


@pytest.mark.parametrize("number, total, window", [
    (1, 21, [1, 2, 3]),                        # 3 pages: no elision
    (2, 21, [1, 2, 3]),
    (1, 120, [1, 2, None, 12]),                # 12 pages, at the start
    (6, 120, [1, None, 5, 6, 7, None, 12]),    # ...in the middle
    (12, 120, [1, None, 11, 12]),              # ...at the end
    (3, 120, [1, 2, 3, 4, None, 12]),          # no gap of one page
])
def test_window_keeps_the_first_and_last_page_reachable(number, total, window):
    assert Page(number, total).window == window


def test_window_never_shows_a_gap_standing_in_for_one_page():
    """An ellipsis hiding a single number is worse than the number."""
    for total in range(0, 200, 7):
        for number in range(1, Page(1, total).pages + 1):
            w = Page(number, total).window
            shown = [n for n in w if n]
            for a, b in zip(shown, shown[1:]):
                assert b - a != 2, "elided exactly one page: %s" % w


def test_per_page_is_ten():
    assert PER_PAGE == 10
