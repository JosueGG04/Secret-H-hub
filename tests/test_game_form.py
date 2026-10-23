"""The record-a-game form: chips, kept state, and the 'record another' loop."""

import re
from html import unescape

from werkzeug.datastructures import MultiDict

from secret_hitler.domain import FASCISTS_BY_SIZE, MAX_PLAYERS, MIN_PLAYERS
from secret_hitler.forms import read_picks


def _checked(html, name):
    """Values of the checked inputs called `name`, in page order."""
    return re.findall(r'name="%s" value="([^"]*)"[^>]*?\schecked' % re.escape(name), html)


def _ticked(html):
    return sorted(int(v) for v in _checked(html, "include"))


def _game(ids, **over):
    data = MultiDict({
        "win_condition": "fascist_policies",
        "played_on": "2026-09-09",
        "liberal_policies": "2",
        "fascist_policies": "6",
        "notes": "Bruno's long con",
        "role_%d" % ids["Bruno"]: "Hitler",
        "role_%d" % ids["Eli"]: "Fascist",
    })
    for n in ("Ada", "Bruno", "Cleo", "Dov", "Eli"):
        data.add("include", str(ids[n]))
    for key, value in over.items():
        data.setlist(key, value if isinstance(value, list) else [value])
    return data


# --------------------------------------------------------------------------
# Reading the picks
# --------------------------------------------------------------------------

def test_read_picks_defaults_roles_and_skips_junk():
    form = MultiDict([("include", "3"), ("include", "x"), ("include", "3"),
                      ("include", "4"), ("role_3", "Hitler"), ("role_4", "Overlord"),
                      ("role_5", "Fascist")])                 # 5 isn't ticked
    assert read_picks(form) == [(3, "Hitler"), (4, "Liberal")]


def test_a_junk_player_id_is_a_form_error_not_a_crash(admin, table):
    r = admin.post("/games", data=_game(table, include=["abc"]))
    assert r.status_code == 422
    assert b"You selected 0" in r.data


def test_the_fascist_table_covers_every_legal_size():
    assert sorted(FASCISTS_BY_SIZE) == list(range(MIN_PLAYERS, MAX_PLAYERS + 1))


# --------------------------------------------------------------------------
# The blank form
# --------------------------------------------------------------------------

def test_the_blank_form_starts_on_today_with_nobody_ticked(admin, table):
    body = admin.get("/games/new").data.decode()
    assert _ticked(body) == []
    assert _checked(body, "win_condition") == []
    assert _checked(body, "liberal_policies") == [""]          # not recorded
    assert re.search(r'class="month-tab on"\s+data-date="[\d-]+">Today<', body)


def test_the_outcome_is_required_and_grouped_by_faction(admin, table):
    body = admin.get("/games/new").data.decode()
    radios = re.findall(r'<input type="radio" name="win_condition" value="(\w+)"[^>]*>', body)
    assert radios == ["liberal_policies", "hitler_executed",
                      "fascist_policies", "hitler_chancellor"]
    assert body.count('name="win_condition"') == body.count("required>")


def test_the_tracks_run_the_length_of_the_board(admin, table):
    body = admin.get("/games/new").data.decode()
    lib = re.findall(r'name="liberal_policies" value="(\d*)"', body)
    fas = re.findall(r'name="fascist_policies" value="(\d*)"', body)
    assert lib == [""] + [str(n) for n in range(6)]
    assert fas == [""] + [str(n) for n in range(7)]


def test_the_new_player_box_belongs_to_its_own_form(admin, table):
    """Otherwise Enter in it would record the game."""
    body = admin.get("/games/new").data.decode()
    assert re.search(r'<input[^>]*name="name"[^>]*form="add-player"', body)
    assert '<form id="add-player"' in body
    assert 'hx-include="#game-form"' in body


# --------------------------------------------------------------------------
# Nothing typed is lost
# --------------------------------------------------------------------------

def test_a_rejected_game_comes_back_as_entered(admin, table):
    two_hitlers = _game(table, **{"role_%d" % table["Cleo"]: "Hitler"})
    r = admin.post("/games", data=two_hitlers)
    assert r.status_code == 422
    body = r.data.decode()
    assert "Exactly one player must be Hitler" in body
    assert _ticked(body) == sorted(table[n] for n in ("Ada", "Bruno", "Cleo", "Dov", "Eli"))
    assert _checked(body, "role_%d" % table["Cleo"]) == ["Hitler"]
    assert _checked(body, "role_%d" % table["Eli"]) == ["Fascist"]
    assert _checked(body, "role_%d" % table["Ada"]) == ["Liberal"]
    assert _checked(body, "win_condition") == ["fascist_policies"]
    assert _checked(body, "liberal_policies") == ["2"]
    assert _checked(body, "fascist_policies") == ["6"]
    assert 'value="2026-09-09"' in body
    assert "Bruno's long con" in unescape(body)


def test_rejections_are_swapped_in_rather_than_dropped(client):
    """htmx ignores 4xx bodies unless told otherwise; without this hook a
    rejected game silently does nothing. (The hook itself is browser-side.)"""
    head = client.get("/").data.decode().split("</head>")[0]
    assert "htmx:beforeSwap" in head
    assert "status === 422 || status === 403" in head


def test_adding_a_player_keeps_the_picks_and_ticks_the_newcomer(admin, table):
    data = MultiDict([("name", "Greta"), ("include", str(table["Ada"])),
                      ("include", str(table["Bruno"])),
                      ("role_%d" % table["Bruno"], "Hitler")])
    body = admin.post("/players", data=data).data.decode()
    greta = int(re.search(r'name="include" value="(\d+)"[^>]*>\s*<span[^>]*></span>\s*'
                          r'<span class="pf-name">Greta<', body).group(1))
    assert _ticked(body) == sorted([table["Ada"], table["Bruno"], greta])
    assert _checked(body, "role_%d" % table["Bruno"]) == ["Hitler"]
    assert _checked(body, "role_%d" % greta) == ["Liberal"]


def test_adding_an_existing_name_just_ticks_them(admin, table):
    body = admin.post("/players", data={"name": "ada"}).data.decode()   # any case
    assert _ticked(body) == [table["Ada"]]
    assert body.count('class="pf-name">Ada<') == 1


# --------------------------------------------------------------------------
# Record another
# --------------------------------------------------------------------------

def _again_url(html):
    return unescape(re.search(r'hx-get="([^"]+)"', html).group(1))


def test_record_another_keeps_the_night_and_the_table(admin, table):
    r = admin.post("/games", data=_game(table))
    assert r.status_code == 200
    url = _again_url(r.data.decode())
    assert "played_on=2026-09-09" in url

    body = admin.get(url).data.decode()
    assert _ticked(body) == sorted(table[n] for n in ("Ada", "Bruno", "Cleo", "Dov", "Eli"))
    assert 'value="2026-09-09"' in body
    # A fresh game: roles back to Liberal, no outcome, no counts, no notes.
    assert _checked(body, "role_%d" % table["Bruno"]) == ["Liberal"]
    assert _checked(body, "win_condition") == []
    assert _checked(body, "fascist_policies") == [""]
    assert "Bruno's long con" not in unescape(body)
