"""Paging as the pages actually render it: the Chronicle, a player's
appearances, and the Game Nights chart."""

import re

import pytest


def _game_ids(html):
    """The game ids rendered, in order, from a Chronicle fragment."""
    return re.findall(r'id="game-(\d+)"', html)


def _pager(html):
    """Just the pager nav, so assertions can't match the list above it."""
    start = html.index('<nav class="pager"')
    return html[start:html.index("</nav>", start)]


def _button(pager_html, label):
    """The one <button> whose text is `label` (e.g. 'Prev', 'Next')."""
    for tag in re.findall(r"<button\b.*?</button>", pager_html, re.S):
        if label in tag:
            return tag
    raise AssertionError("no %r button in pager" % label)


def _range_note(html):
    """The '11–14 of 14' line under the pager."""
    return re.search(r'class="pager-note">\s*(.+?)\s*</p>', html, re.S).group(1)


def _chart_note(html):
    """The caption under the Game Nights chart, whitespace collapsed — the
    template wraps it across two lines."""
    body = re.search(r'class="chart-note">(.*?)</p>', html, re.S).group(1)
    return " ".join(body.split())


# --------------------------------------------------------------------------
# The Chronicle
# --------------------------------------------------------------------------

def test_a_short_chronicle_shows_no_pager(client, table):
    """Three games fit on one page, so nothing about / changes."""
    body = client.get("/").data.decode()
    assert 'class="pager"' not in body
    assert len(_game_ids(body)) == 3


def test_the_chronicle_pages_at_ten(client, busy_table):
    page1 = client.get("/games/list").data.decode()
    page2 = client.get("/games/list?page=2").data.decode()

    assert len(_game_ids(page1)) == 10
    assert len(_game_ids(page2)) == 4          # 14 games in the fixture
    assert _range_note(page1) == "1–10 of 14"
    assert _range_note(page2) == "11–14 of 14"


def test_the_pages_partition_the_whole_log(client, busy_table):
    page1 = _game_ids(client.get("/games/list").data.decode())
    page2 = _game_ids(client.get("/games/list?page=2").data.decode())
    assert set(page1).isdisjoint(page2)
    assert len(set(page1) | set(page2)) == 14
    # Newest first: within a night, ids descend.
    assert [int(i) for i in page1] == sorted((int(i) for i in page1), reverse=True)
    assert min(int(i) for i in page1) > max(int(i) for i in page2)


def test_the_current_page_is_the_only_one_marked(client, busy_table):
    marked = re.findall(r'class="page-btn on"[^>]*>(\d+)<',
                        _pager(client.get("/games/list?page=2").data.decode()))
    assert marked == ["2"]


def test_the_pager_ends_are_disabled(client, busy_table):
    first = _pager(client.get("/games/list").data.decode())
    assert "disabled" in _button(first, "Prev")
    assert "disabled" not in _button(first, "Next")

    last = _pager(client.get("/games/list?page=2").data.decode())
    assert "disabled" not in _button(last, "Prev")
    assert "disabled" in _button(last, "Next")


@pytest.mark.parametrize("arg", ["?page=99", "?page=0", "?page=garbage", "?page="])
def test_an_out_of_range_or_junk_page_still_renders(client, busy_table, arg):
    r = client.get("/games/list" + arg)
    assert r.status_code == 200
    assert _game_ids(r.data.decode())           # never a blank list


def test_a_stale_page_lands_on_the_last_real_one(client, busy_table):
    assert _range_note(client.get("/games/list?page=99").data.decode()) == "11–14 of 14"


def test_the_refresh_hook_round_trips_the_current_page(client, busy_table):
    """Without this, recording a game throws the reader back to page 1."""
    page2 = client.get("/games/list?page=2").data.decode()
    start = page2.index('<div id="game-list"')
    wrapper = page2[start:page2.index(">", start)]
    assert "/games/list?page=2" in wrapper
    assert 'hx-trigger="gameLogged from:body"' in wrapper


def test_the_pager_sits_outside_every_game_card(client, busy_table):
    """The per-card delete swaps outerHTML on #game-<id>; a pager inside a card
    would be deleted with it."""
    body = client.get("/games/list").data.decode()
    assert body.index('<nav class="pager"') > body.rindex('id="game-')


# --------------------------------------------------------------------------
# A player's appearances
# --------------------------------------------------------------------------

def test_the_player_page_shows_ten_of_their_games(client, busy_table):
    body = client.get("/player/%d" % busy_table["Ada"]).data.decode()
    assert body.count('class="game win-') == 10
    assert 'id="player-games"' in body
    assert _range_note(body) == "1–10 of 14"


def test_player_totals_cover_every_game_not_just_the_page(client, busy_table):
    """The header record and the per-role cards must not be paginated."""
    body = client.get("/player/%d" % busy_table["Ada"]).data.decode()
    stats = body[body.index('class="pstat-grid"'):body.index('class="role-cards"')]
    assert ">14</div>" in stats                   # games played, not 10
    assert "14 game" in body                      # the Appearances count
    roles = body[body.index('class="role-cards"'):body.index('id="player-games"')]
    assert "won of 14 played" in roles            # Ada was Liberal every game


def test_the_player_history_fragment_pages(client, busy_table):
    r = client.get("/player/%d/games?page=2" % busy_table["Ada"])
    assert r.status_code == 200
    body = r.data.decode()
    assert body.count('class="game win-') == 4
    assert _range_note(body) == "11–14 of 14"


def test_the_history_pager_carries_the_player_id(client, busy_table):
    pid = busy_table["Ada"]
    body = client.get("/player/%d" % pid).data.decode()
    assert "/player/%d/games?page=2" % pid in body


def test_a_player_with_no_games_gets_the_empty_state_not_a_pager(client, table):
    body = client.get("/player/%d" % table["Fern"]).data.decode()   # Fern sat out
    assert 'class="pager"' not in body
    assert "No games recorded for Fern yet." in body


def test_the_history_fragment_names_the_player_in_its_empty_state(client, table):
    """The fragment renders without `d`, so it needs its own copy of the name."""
    body = client.get("/player/%d/games" % table["Fern"]).data.decode()
    assert "No games recorded for Fern yet." in body


def test_the_history_fragment_404s_for_a_stranger(client):
    assert client.get("/player/9999/games").status_code == 404


# --------------------------------------------------------------------------
# Game Nights, by month
# --------------------------------------------------------------------------

def _night_labels(html):
    return re.findall(
        r'<div class="night-label"><span class="mo">(\w*)</span>(\d+)</div>', html)


def test_the_dashboard_opens_on_the_newest_month(client, busy_table):
    body = client.get("/dashboard").data.decode()
    assert 'id="game-nights"' in body
    # April is the fixture's newest month: 4 nights, one game each.
    assert _night_labels(body) == [("Apr", "6"), ("Apr", "13"),
                                   ("Apr", "20"), ("Apr", "27")]
    assert _chart_note(body) == "4 nights at the table in April 2026, earliest first."


def test_the_month_chips_scope_the_chart(client, busy_table):
    body = client.get("/dashboard/nights?month=2026-03").data.decode()
    assert [d for _, d in _night_labels(body)] == ["2", "9", "16", "23"]
    assert _chart_note(body) == "4 nights at the table in March 2026, earliest first."


def test_the_active_chip_is_server_rendered_and_months_only(client, busy_table):
    body = client.get("/dashboard/nights?month=2026-03").data.decode()
    start = body.index('class="month-tabs"')
    chips = body[start:body.index("</div>", start)]
    on = re.findall(r'class="month-tab on"[^>]*>([^<]+)<', chips)
    assert [t.strip() for t in on] == ["March 2026"]
    assert "All time" not in chips        # an all-time chart is the thing we bounded


def test_the_chips_target_the_panel_they_live_in(client, busy_table):
    body = client.get("/dashboard").data.decode()
    start = body.index('class="month-tabs"')
    chips = body[start:body.index("</div>", start)]
    assert chips.count('hx-target="#game-nights"') == 2      # two months
    assert "/dashboard/nights?month=2026-03" in chips


def test_the_peak_cap_marks_the_busiest_night_of_that_month(client, busy_table):
    """March's 16th is the first night to reach 3 games, so it takes the one
    printed cap — an index into *this month's* list, not the whole series."""
    body = client.get("/dashboard/nights?month=2026-03").data.decode()
    assert re.findall(r'<span class="cap">(\d+)</span>', body) == ["3"]
    before = body[:body.index('class="cap"')]
    assert before.count('class="night"') == 3          # the 3rd bar, 2026-03-16
    # April's busiest is 1 game a night, so its cap reads 1, not March's 3.
    april = client.get("/dashboard/nights?month=2026-04").data.decode()
    assert re.findall(r'<span class="cap">(\d+)</span>', april) == ["1"]


def test_bars_scale_to_the_month_on_show(client, busy_table):
    """March: 2,2,3,3 games -> the 3-game nights fill the plot."""
    body = client.get("/dashboard/nights?month=2026-03").data.decode()
    heights = [round(float(h)) for h in re.findall(r'height: ([\d.]+)%', body)]
    assert heights == [67, 67, 100, 100]


@pytest.mark.parametrize("arg", ["", "?month=garbage", "?month=2026-13", "?month=1999-01"])
def test_a_junk_month_falls_back_instead_of_blanking(client, busy_table, arg):
    r = client.get("/dashboard/nights" + arg)
    assert r.status_code == 200
    assert "April 2026" in r.data.decode()


def test_the_nights_panel_is_gated_on_there_being_any_games(client):
    body = client.get("/dashboard").data.decode()
    assert "No games recorded yet" in body
    assert 'id="game-nights"' not in body
