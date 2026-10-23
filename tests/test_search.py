"""The match search: each filter on its own, together, and as the page renders it."""

import re
from datetime import date
from html import unescape

import pytest

from secret_hitler.repository import create_game
from secret_hitler.search import date_presets


def _dates(html):
    """The played_on of every game card rendered, in order."""
    return re.findall(r'class="game-date">(\d{4}-\d\d-\d\d)', html)


def _results(client, query=""):
    r = client.get("/search/results" + query)
    assert r.status_code == 200
    return r.data.decode()


# The `table` fixture's three games, newest first.
ALL = ["2026-08-02", "2026-07-08", "2026-07-01"]


# --------------------------------------------------------------------------
# Single filters
# --------------------------------------------------------------------------

def test_no_filters_lists_every_game(client, table):
    assert _dates(_results(client)) == ALL


def test_a_player_in_a_role(client, table):
    assert _dates(_results(client, "?p%d=Hitler" % table["Bruno"])) == ["2026-07-01"]
    assert _dates(_results(client, "?p%d=Fascist" % table["Bruno"])) == ["2026-08-02", "2026-07-08"]


def test_a_player_in_any_role(client, table):
    assert _dates(_results(client, "?p%d=any" % table["Bruno"])) == ALL
    assert "No games match" in _results(client, "?p%d=any" % table["Fern"])   # sat out


def test_several_players_must_all_have_played_as_set(client, table):
    q = "?p%d=Hitler&p%d=Fascist" % (table["Eli"], table["Bruno"])
    assert _dates(_results(client, q)) == ["2026-08-02", "2026-07-08"]
    q = "?p%d=Hitler&p%d=Hitler" % (table["Eli"], table["Bruno"])
    assert "No games match" in _results(client, q)


def test_date_range_is_inclusive(client, table):
    assert _dates(_results(client, "?from=2026-07-08")) == ["2026-08-02", "2026-07-08"]
    assert _dates(_results(client, "?to=2026-07-08")) == ["2026-07-08", "2026-07-01"]
    assert _dates(_results(client, "?from=2026-07-02&to=2026-07-31")) == ["2026-07-08"]


def test_outcome_filters(client, table):
    """A faction means won either way; a win condition means won exactly so."""
    assert _dates(_results(client, "?outcome=Fascist")) == ["2026-08-02"]
    assert _dates(_results(client, "?outcome=Liberal")) == ["2026-07-08", "2026-07-01"]
    assert _dates(_results(client, "?outcome=hitler_executed")) == ["2026-07-08"]
    assert "No games match" in _results(client, "?outcome=hitler_chancellor")


def test_table_size(client, table):
    assert _dates(_results(client, "?size=5")) == ALL
    assert "No games match" in _results(client, "?size=6")


def test_notes_match_literally(client, app, table):
    with app.app_context():
        ids = [table[n] for n in ("Ada", "Bruno", "Cleo", "Dov", "Eli")]
        create_game("2026-09-01", "liberal_policies",
                    [(ids[0], "Hitler")] + [(i, "Liberal") for i in ids[1:]],
                    notes="Won 100% on a_bluff")
    assert _dates(_results(client, "?q=100%25")) == ["2026-09-01"]
    assert _dates(_results(client, "?q=a_bluff")) == ["2026-09-01"]
    assert _dates(_results(client, "?q=BLUFF")) == ["2026-09-01"]     # LIKE ignores case
    # Wildcards are escaped, so they don't match games without notes.
    assert _dates(_results(client, "?q=%25")) == ["2026-09-01"]
    assert "No games match" in _results(client, "?q=_x")
    # Results show the notes, since they're what matched.
    assert "Won 100% on a_bluff" in unescape(_results(client, "?q=bluff"))


def test_filters_combine(client, table):
    q = "?outcome=Liberal&p%d=Hitler&from=2026-07-05" % table["Eli"]
    assert _dates(_results(client, q)) == ["2026-07-08"]


# --------------------------------------------------------------------------
# Junk and the tally
# --------------------------------------------------------------------------

@pytest.mark.parametrize("arg", [
    "?p9999=Hitler", "?pX=Hitler", "?p1=Overlord", "?size=42", "?size=abc",
    "?from=garbage", "?to=2026-13-40", "?outcome=nope", "?outcome=Whig", "?outcome=",
    "?q=%20%20", "?page=junk",
])
def test_junk_filters_are_ignored(client, table, arg):
    assert _dates(_results(client, arg)) == ALL


def test_the_tally_splits_matches_by_faction(client, table):
    body = " ".join(_results(client).split())
    assert "<b>3</b> matches" in body
    assert "2 Liberal" in body and "1 Fascist" in body
    one = " ".join(_results(client, "?outcome=Fascist").split())
    assert "<b>1</b> match " in one


# --------------------------------------------------------------------------
# Paging and the URL
# --------------------------------------------------------------------------

def test_the_pager_carries_the_filters(client, busy_table):
    pid = busy_table["Bruno"]
    body = _results(client, "?p%d=Hitler&size=5" % pid)
    assert len(_dates(body)) == 10
    links = unescape(" ".join(re.findall(r'hx-get="([^"]+)"', body)))
    assert "page=2" in links
    assert "p%d=Hitler" % pid in links and "size=5" in links
    page2 = _results(client, "?p%d=Hitler&size=5&page=2" % pid)
    assert len(_dates(page2)) == 4


def test_results_point_the_url_bar_at_the_full_page(client, busy_table):
    r = client.get("/search/results?outcome=Liberal&from=&q=&size=&page=2")
    assert r.headers["HX-Replace-Url"] == "/search?outcome=Liberal&page=2"
    r = client.get("/search/results?from=garbage")
    assert r.headers["HX-Replace-Url"] == "/search"


def _checked_radios(html, name):
    """Values of the checked radios in one group of the form."""
    return re.findall(r'name="%s" value="(\w*)"[^>]*?\schecked' % name, html)


def test_the_full_page_restores_the_form(client, table):
    pid = table["Bruno"]
    body = client.get("/search?p%d=Hitler&outcome=Liberal&size=5&from=2026-07-01"
                      % pid).data.decode()
    assert _dates(body) == ["2026-07-01"]
    assert _checked_radios(body, "outcome") == ["Liberal"]
    assert _checked_radios(body, "size") == ["5"]
    assert 'value="2026-07-01"' in body
    assert 'value="hi"' in client.get("/search?q=hi").data.decode()


def _chip(html, pid):
    """One player's chip: the tick plus its role buttons."""
    start = html.index('name="p%d"' % pid)
    last = html.index('name="r%d" value="Hitler"' % pid, start)   # the chip's last input
    return html[start:html.index(">", last) + 1]


def _checked(chip_html):
    """Names and values of the ticked inputs in a chip."""
    return re.findall(r'name="(\w+)" value="(\w+)"[^>]*?\schecked', chip_html, re.S)


def test_the_chips_restore_the_player_filters(client, table):
    body = client.get("/search?p%d=Hitler&p%d=any" % (table["Bruno"], table["Ada"])).data.decode()
    assert _checked(_chip(body, table["Bruno"])) == [
        ("p%d" % table["Bruno"], "any"), ("r%d" % table["Bruno"], "Hitler")]
    assert _checked(_chip(body, table["Ada"])) == [
        ("p%d" % table["Ada"], "any"), ("r%d" % table["Ada"], "any")]
    # An unticked player's chip is off, with its role buttons resting on Any.
    assert _checked(_chip(body, table["Cleo"])) == [("r%d" % table["Cleo"], "any")]


def test_the_chip_form_shape_filters_like_a_link(client, table):
    """The form sends p<id>=any for the tick plus r<id> for the role."""
    b, e = table["Bruno"], table["Eli"]
    q = "?p%d=any&r%d=Hitler&r%d=Fascist" % (b, b, e)    # Eli's role sent, but unticked
    assert _dates(_results(client, q)) == ["2026-07-01"]
    assert _dates(_results(client, "?p%d=any&r%d=any" % (b, b))) == ALL
    assert _dates(_results(client, "?p%d=any&r%d=Overlord" % (b, b))) == ALL   # bad role -> any


def test_the_url_bar_folds_the_role_into_the_player(client, table):
    b, e = table["Bruno"], table["Eli"]
    r = client.get("/search/results?p%d=any&r%d=Hitler&r%d=Fascist" % (b, b, e))
    assert r.headers["HX-Replace-Url"] == "/search?p%d=Hitler" % b


def test_the_nav_marks_search(client, table):
    body = client.get("/search").data.decode()
    assert re.search(r'href="/search"\s+class="on"', body)


def test_admins_can_delete_from_the_results(admin, table):
    assert "hx-delete=" in admin.get("/search/results").data.decode()


def test_an_empty_table_has_an_empty_search(client):
    r = client.get("/search")
    assert r.status_code == 200
    assert "No games match" in r.data.decode()


def test_an_unfiltered_form_rests_on_any(client, table):
    body = client.get("/search").data.decode()
    assert _checked_radios(body, "outcome") == [""]
    assert _checked_radios(body, "size") == [""]


def test_conditions_sit_under_their_faction(client, table):
    """Each condition chip carries its faction's colour class and full label."""
    body = client.get("/search").data.decode()
    chips = {title: css for css, title in
             re.findall(r'<label class="opt cond (lib|fas)" title="([^"]+)"', body)}
    assert chips == {
        "Five Liberal policies enacted — Liberal win": "lib",
        "Hitler assassinated — Liberal win": "lib",
        "Six Fascist policies enacted — Fascist win": "fas",
        "Hitler elected Chancellor — Fascist win": "fas",
    }


# --------------------------------------------------------------------------
# Date quick picks
# --------------------------------------------------------------------------

def test_date_presets_only_set_a_start():
    presets = {p["label"]: p["from"] for p in date_presets(date(2026, 10, 22))}
    assert presets == {
        "Any time": "",
        "This month": "2026-10-01",
        "Last 90 days": "2026-07-25",
        "This year": "2026-01-01",
    }


def _lit_presets(html):
    return [t.strip() for t in
            re.findall(r'class="month-tab on"\s+data-from="[^"]*">([^<]+)<', html)]


def test_the_matching_preset_is_lit(client, table):
    first = date.today().replace(day=1).isoformat()
    assert _lit_presets(client.get("/search").data.decode()) == ["Any time"]
    assert _lit_presets(client.get("/search?from=" + first).data.decode()) == ["This month"]
    # An end date makes it a custom range, which no preset describes.
    assert _lit_presets(client.get("/search?from=%s&to=2099-01-01" % first).data.decode()) == []
