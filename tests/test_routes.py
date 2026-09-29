"""The 12 endpoints: what the public may see, and what only the admin may change."""

import re

import pytest

PUBLIC_PAGES = ["/", "/dashboard", "/leaderboard", "/games/list", "/summary", "/login"]


@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_public_pages_need_no_sign_in(client, table, path):
    assert client.get(path).status_code == 200


def test_the_home_page_boots_on_an_empty_database(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"No games recorded yet" in r.data


def test_player_page_and_missing_player(client, table):
    assert client.get("/player/%d" % table["Ada"]).status_code == 200
    assert client.get("/player/9999").status_code == 404


def test_leaderboard_month_filter(client, table):
    assert b"August 2026" in client.get("/leaderboard").data
    assert client.get("/leaderboard?month=2026-07").status_code == 200


def test_a_malformed_month_falls_back_to_all_time(client, table):
    garbage = client.get("/leaderboard?month=garbage").data
    assert garbage == client.get("/leaderboard").data


# --------------------------------------------------------------------------
# Admin guard
# --------------------------------------------------------------------------

WRITE_PATHS = [
    ("get", "/games/new"),
    ("post", "/games"),
    ("post", "/players"),
    ("delete", "/games/1"),
]


@pytest.mark.parametrize("method, path", WRITE_PATHS)
def test_signed_out_navigation_is_redirected_to_login(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


@pytest.mark.parametrize("method, path", WRITE_PATHS)
def test_signed_out_htmx_calls_get_a_403_fragment(client, method, path):
    r = getattr(client, method)(path, headers={"HX-Request": "true"})
    assert r.status_code == 403
    assert b"Admin sign-in required" in r.data


def test_the_record_panel_is_hidden_from_the_public(client, table):
    assert b"Record a Game" not in client.get("/").data


def test_the_record_panel_appears_for_the_admin(admin, table):
    assert b"Record a Game" in admin.get("/").data


def test_a_wrong_password_does_not_sign_you_in(client):
    r = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 200
    assert b"Incorrect username or password" in r.data
    assert client.get("/games/new").status_code == 302


def test_login_returns_you_to_where_you_were_headed(client):
    r = client.post("/login?next=/dashboard",
                    data={"username": "admin", "password": "test-pw"})
    assert r.headers["Location"] == "/dashboard"


@pytest.mark.parametrize("target", [
    "https://evil.example",
    "//evil.example",          # protocol-relative
    r"/\evil.example",         # some browsers normalise /\ like //
    "",
])
def test_login_refuses_to_redirect_off_site(client, target):
    r = client.post("/login?next=" + target,
                    data={"username": "admin", "password": "test-pw"})
    assert r.headers["Location"] == "/"


def test_logout_drops_admin_access(admin):
    assert admin.get("/logout").status_code == 302
    assert admin.get("/games/new").status_code == 302


# --------------------------------------------------------------------------
# Recording games
# --------------------------------------------------------------------------

def _form(ids, **over):
    data = {
        "win_condition": "liberal_policies",
        "played_on": "2026-09-09",
        "include": [str(ids[n]) for n in ("Ada", "Bruno", "Cleo", "Dov", "Eli")],
        "role_%d" % ids["Bruno"]: "Hitler",
        "role_%d" % ids["Eli"]: "Fascist",
    }
    data.update(over)
    return data


def test_recording_a_game_triggers_the_page_refresh(admin, table):
    r = admin.post("/games", data=_form(table))
    assert r.status_code == 200
    assert r.headers["HX-Trigger"] == "gameLogged"
    assert b"Liberal" in r.data
    # The new night shows up in the log and in the month chips.
    assert b"2026-09-09" in admin.get("/games/list").data
    assert b"September 2026" in admin.get("/leaderboard").data


def test_deleting_a_game_removes_it_from_the_log(admin, table, app):
    admin.post("/games", data=_form(table))
    assert b"2026-09-09" in admin.get("/games/list").data

    with app.app_context():
        from secret_hitler.db import get_db
        game_id = get_db().execute("SELECT max(id) m FROM games").fetchone()["m"]
    r = admin.delete("/games/%d" % game_id)
    assert r.status_code == 200
    assert r.headers["HX-Trigger"] == "gameLogged"
    assert b"2026-09-09" not in admin.get("/games/list").data


@pytest.mark.parametrize("over, message", [
    ({"win_condition": "nonsense"}, b"valid win condition"),
    ({"include": ["1", "2", "3", "4"]}, b"needs 5"),
])
def test_invalid_submissions_are_rejected(admin, table, over, message):
    r = admin.post("/games", data=_form(table, **over))
    assert r.status_code == 422
    assert message in r.data


def test_exactly_one_hitler_is_required(admin, table):
    two = {"role_%d" % table["Cleo"]: "Hitler"}      # on top of Bruno
    r = admin.post("/games", data=_form(table, **two))
    assert r.status_code == 422
    assert b"Exactly one player must be Hitler" in r.data

    none = {"role_%d" % table["Bruno"]: "Liberal"}
    r = admin.post("/games", data=_form(table, **none))
    assert r.status_code == 422
    assert b"you set 0" in r.data


def test_the_failed_form_comes_back_ready_to_resubmit(admin, table):
    r = admin.post("/games", data=_form(table, win_condition="nonsense"))
    assert b"<form" in r.data                 # the form is re-rendered, not lost
    assert b"Record This Game" in r.data


def test_an_unparseable_policy_count_is_stored_as_null(admin, table, app):
    admin.post("/games", data=_form(table, liberal_policies="five"))
    with app.app_context():
        from secret_hitler.db import get_db
        row = get_db().execute(
            "SELECT liberal_policies FROM games ORDER BY id DESC LIMIT 1").fetchone()
    assert row["liberal_policies"] is None


# --------------------------------------------------------------------------
# Players
# --------------------------------------------------------------------------

def test_adding_a_player_refreshes_the_picker(admin, table):
    r = admin.post("/players", data={"name": "Greta"})
    assert r.status_code == 200
    assert r.headers["HX-Trigger"] == "playersChanged"
    assert b"Greta" in r.data


def test_duplicate_and_blank_names_are_ignored(admin, table, app):
    admin.post("/players", data={"name": "ada"})       # case-insensitive clash
    admin.post("/players", data={"name": "   "})
    with app.app_context():
        from secret_hitler.repository import all_players
        assert len(all_players()) == 6                 # the six from the fixture


def test_a_bare_slash_is_an_acceptable_destination(client):
    r = client.post("/login?next=/",
                    data={"username": "admin", "password": "test-pw"})
    assert r.headers["Location"] == "/"


# --------------------------------------------------------------------------
# Navigation
# --------------------------------------------------------------------------

def _highlighted_nav_links(client, path):
    """Names of the nav links carrying the 'on' class on a given page."""
    html = client.get(path).data.decode()
    nav = html[html.index('<nav class="deconav">'):html.index("</nav>")]
    return [re.sub(r"<[^>]+>", "", link).strip()
            for link in re.findall(r"<a\b[^>]*>.*?</a>", nav, re.S)
            if 'class="on"' in link]


@pytest.mark.parametrize("path, active", [
    ("/", "Standings"),
    ("/dashboard", "Dashboard"),
])
def test_the_nav_marks_the_current_page(client, path, active):
    """The 'on' class comes from a request.endpoint comparison in base.html,
    which fails silently — no exception — if the endpoint names ever drift."""
    assert _highlighted_nav_links(client, path) == [active]


def test_the_nav_highlights_nothing_off_those_two_pages(client, table):
    assert _highlighted_nav_links(client, "/player/%d" % table["Ada"]) == []
    assert _highlighted_nav_links(client, "/login") == []
