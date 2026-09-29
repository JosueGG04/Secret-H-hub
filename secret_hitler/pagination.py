"""Offset paging, shared by the Chronicle and a player's appearances."""

PER_PAGE = 10

# How many neighbours of the current page get their own button before the row
# collapses into an ellipsis.
_NEIGHBOURS = 1


def valid_page(raw):
    """Read a ?page= query arg. Anything malformed means the first page."""
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


class Page:
    """One page of a list, plus the numbers a pager needs to draw itself.

    `number` is clamped into [1, pages], so a stale ?page=7 left over after
    games were deleted lands on the last real page instead of an empty one.
    """

    def __init__(self, number, total, per_page=PER_PAGE):
        self.per_page = per_page
        self.total = total
        self.pages = max(1, -(-total // per_page))      # ceil, without math
        self.number = min(max(number, 1), self.pages)
        self.offset = (self.number - 1) * per_page

    @property
    def has_prev(self):
        return self.number > 1

    @property
    def has_next(self):
        return self.number < self.pages

    @property
    def prev(self):
        return max(1, self.number - 1)

    @property
    def next(self):
        return min(self.pages, self.number + 1)

    @property
    def first_item(self):
        """1-based index of this page's first row, for the '11–20 of 21' note."""
        return self.offset + 1 if self.total else 0

    @property
    def last_item(self):
        return min(self.offset + self.per_page, self.total)

    @property
    def window(self):
        """Page numbers to draw, with None marking an elided run.

        Always keeps the first and last page reachable: three pages draw
        1 2 3, and twelve pages sitting on 6 draw 1 … 5 6 7 … 12.
        """
        keep = {1, self.pages}
        keep.update(range(self.number - _NEIGHBOURS, self.number + _NEIGHBOURS + 1))
        shown = sorted(n for n in keep if 1 <= n <= self.pages)

        out = []
        for n in shown:
            if out:
                gap = n - out[-1]
                if gap == 2:
                    out.append(n - 1)   # an ellipsis hiding one page is just
                elif gap > 2:           # as wide as the page number itself
                    out.append(None)
            out.append(n)
        return out

    def __repr__(self):
        return "Page(%d/%d of %d rows)" % (self.number, self.pages, self.total)
