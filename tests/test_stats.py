"""Standings, monthly scoping, player records, and the dashboard aggregates."""

import pytest

from secret_hitler.repository import create_game
from secret_hitler.stats.dashboard import (
    awards, game_shape_stats, nights_context, pair_rows,
)
from secret_hitler.stats.leaderboard import (
    available_months, faction_split, leaderboard_rows, month_label, valid_month,
)
from secret_hitler.stats.players import (
    game_detail_rows, player_detail, player_history, summary_stats,
)


def test_summary_counts_both_factions(app, table):
    with app.app_context():
        s = summary_stats()
    assert s["total_games"] == 3
    assert s["liberal_wins"] == 2
    assert s["fascist_wins"] == 1
    assert s["total_players"] == 6
    assert round(s["liberal_pct"] + s["fascist_pct"]) == 100


def test_summary_is_safe_on_an_empty_table(app):
    with app.app_context():
        s = summary_stats()
    assert s == {"total_games": 0, "liberal_wins": 0, "fascist_wins": 0,
                 "liberal_pct": 0, "fascist_pct": 0, "total_players": 0}


def test_leaderboard_ranks_by_wins_and_lists_non_players(app, table):
    with app.app_context():
        board = leaderboard_rows()
    by_name = {r["name"]: r for r in board}

    # Ada played all three, winning the two Liberal games.
    assert by_name["Ada"]["games"] == 3
    assert by_name["Ada"]["wins"] == 2
    assert by_name["Ada"]["losses"] == 1
    assert by_name["Ada"]["win_rate"] == 2 / 3

    # Fern never played, so she is listed with an empty record and no rank.
    assert by_name["Fern"]["games"] == 0
    assert by_name["Fern"]["rank"] is None

    # The board is ordered by wins descending among ranked players.
    ranked = [r for r in board if r["ranked"]]
    assert ranked == sorted(ranked, key=lambda r: -r["wins"])
    assert ranked[0]["rank"] == 1


def test_tied_players_share_a_rank(app, table):
    with app.app_context():
        board = leaderboard_rows()
    for a, b in zip(board, board[1:]):
        if a["ranked"] and b["ranked"] and a["wins"] == b["wins"]:
            assert a["rank"] == b["rank"]


def test_role_mix_adds_up_to_games_played(app, table):
    with app.app_context():
        for r in leaderboard_rows():
            assert r["lib_games"] + r["fas_games"] + r["hitler_games"] == r["games"]


def test_monthly_board_only_counts_that_month(app, table):
    with app.app_context():
        july = {r["name"]: r for r in leaderboard_rows(month="2026-07")}
        august = {r["name"]: r for r in leaderboard_rows(month="2026-08")}

    assert july["Ada"]["games"] == 2 and july["Ada"]["wins"] == 2
    assert august["Ada"]["games"] == 1 and august["Ada"]["wins"] == 0
    # A monthly board lists only that month's participants — Fern sat out.
    assert "Fern" not in july


def test_faction_split_all_time_and_monthly(app, table):
    with app.app_context():
        everything = faction_split()
        july = faction_split("2026-07")
        august = faction_split("2026-08")

    assert (everything["games"], everything["lib"], everything["fas"]) == (3, 2, 1)
    assert round(everything["lib_pct"] + everything["fas_pct"]) == 100
    assert (july["lib"], july["fas"], july["lib_pct"]) == (2, 0, 100.0)
    assert (august["lib"], august["fas"], august["fas_pct"]) == (0, 1, 100.0)


def test_faction_split_is_safe_on_an_empty_table(app):
    with app.app_context():
        assert faction_split() == {"games": 0, "lib": 0, "fas": 0,
                                   "lib_pct": 0.0, "fas_pct": 0.0}


def test_available_months_are_newest_first(app, table):
    with app.app_context():
        months = available_months()
    assert [m["value"] for m in months] == ["2026-08", "2026-07"]
    assert months[0]["label"] == "August 2026"


def test_month_label_and_validation():
    assert month_label("2026-07") == "July 2026"
    assert month_label("nonsense") == "nonsense"      # unparseable passes through
    assert valid_month("2026-07") == "2026-07"
    assert valid_month("2026-13") is None             # no thirteenth month
    assert valid_month("garbage") is None
    assert valid_month(None) is None


def test_game_log_attaches_the_right_roster(app, table):
    with app.app_context():
        games = game_detail_rows()
    assert len(games) == 3
    # Newest night first.
    assert [g["played_on"] for g in games] == ["2026-08-02", "2026-07-08", "2026-07-01"]
    for g in games:
        assert len(g["roster"]) == g["num_players"] == 5
        assert g["condition_label"]
        # Hitler is listed first, then Fascists, then Liberals.
        assert g["roster"][0]["role"] == "Hitler"


def test_player_detail_splits_the_record_by_role(app, table):
    with app.app_context():
        d = player_detail(table["Bruno"])
    assert d["player"]["name"] == "Bruno"
    assert d["games"] == 3
    assert d["wins"] + d["losses"] == d["games"]
    # Bruno was Hitler once and Fascist twice — never a Liberal.
    assert d["by_role"]["Hitler"]["games"] == 1
    assert d["by_role"]["Fascist"]["games"] == 2
    assert d["by_role"]["Liberal"]["games"] == 0


def test_player_history_is_newest_first(app, table):
    with app.app_context():
        history = player_history(table["Bruno"])
    assert [h["played_on"] for h in history] == [
        "2026-08-02", "2026-07-08", "2026-07-01"]
    for h in history:
        assert h["condition_label"]


def test_player_detail_is_none_for_a_stranger(app):
    with app.app_context():
        assert player_detail(9999) is None


def test_game_shape_keeps_a_row_for_every_condition(app, table):
    with app.app_context():
        shape = game_shape_stats()
    assert shape["total_games"] == 3
    assert len(shape["conditions"]) == 4          # including the ones at zero
    assert sum(c["count"] for c in shape["conditions"]) == 3
    for row in shape["by_size"]:
        assert row["lib"] + row["fas"] == row["games"]
        assert round(row["lib_pct"] + row["fas_pct"]) == 100


def test_nights_default_to_the_most_recent_month(app, table):
    with app.app_context():
        n = nights_context()
    # The fixture's newest night is 2026-08-02, alone in its month.
    assert n["month"] == "2026-08"
    assert n["month_label"] == "August 2026"
    assert [x["played_on"] for x in n["nights"]] == ["2026-08-02"]
    assert [m["value"] for m in n["months"]] == ["2026-08", "2026-07"]


def test_nights_scope_to_the_month_asked_for(app, table):
    with app.app_context():
        n = nights_context("2026-07")
    assert [x["played_on"] for x in n["nights"]] == ["2026-07-01", "2026-07-08"]
    assert n["nights"][0]["label"] == "Jul 1"
    for x in n["nights"]:
        assert x["lib"] + x["fas"] == x["games"]


@pytest.mark.parametrize("bad", ["garbage", "2026-13", "1999-01", None, ""])
def test_a_bad_or_empty_month_falls_back_to_the_newest(app, table, bad):
    """Including a well-formed month with no games — it must not render blank."""
    with app.app_context():
        assert nights_context(bad)["month"] == "2026-08"


def test_the_peak_cap_indexes_into_the_month_on_show(app, table):
    """peak is compared to loop.index0 in the template, so it has to be an
    index into the filtered list, not the whole series."""
    with app.app_context():
        create_game("2026-07-08", "liberal_policies", [
            (table[n], "Hitler" if n == "Ada" else "Liberal")
            for n in ("Ada", "Bruno", "Cleo", "Dov", "Eli")
        ])
        n = nights_context("2026-07")
    # 2026-07-08 now has 2 games and is the month's busiest, at index 1.
    assert n["busiest"] == 2
    assert n["peak"] == 1
    assert n["nights"][n["peak"]]["played_on"] == "2026-07-08"


def test_nights_are_empty_with_no_games_at_all(app):
    with app.app_context():
        n = nights_context()
    assert n["nights"] == [] and n["month"] is None and n["busiest"] == 0


def test_awards_drop_tiles_with_no_qualifier(app, table):
    with app.app_context():
        # min_games=99 leaves nobody seasoned enough for the streak tiles.
        tiles = awards(min_games=99, min_role_games=1)
    labels = [t["label"] for t in tiles]
    assert "Longest Streak" not in labels
    assert "Most Faithful" in labels               # no minimum on that one

    with app.app_context():
        tiles = awards(min_games=1, min_role_games=1)
    for t in tiles:
        assert t["name"] and t["player_id"] and t["value"]


def test_pairs_need_a_minimum_shared_history(app, table):
    with app.app_context():
        assert pair_rows(min_together=99)["duos"] == []
        pairs = pair_rows(min_together=1)
    assert pairs["min_together"] == 1
    for duo in pairs["duos"]:
        assert duo["wins"] + duo["losses"] == duo["games"]
        assert 0 <= duo["rate"] <= 1
    for feud in pairs["rivals"]:
        # The winner of the feud is named first, so the edge is never negative.
        assert feud["edge"] >= 0
        assert feud["w1"] >= feud["w2"]


def test_a_new_game_lands_in_the_standings(app, table):
    with app.app_context():
        ids = table
        create_game("2026-09-01", "hitler_chancellor", [
            (ids["Ada"], "Hitler"), (ids["Bruno"], "Fascist"),
            (ids["Cleo"], "Liberal"), (ids["Dov"], "Liberal"),
            (ids["Eli"], "Liberal"),
        ])
        board = {r["name"]: r for r in leaderboard_rows()}
    # Fascists win on hitler_chancellor, so Ada and Bruno pick up a win.
    assert board["Ada"]["wins"] == 3
    assert board["Cleo"]["losses"] == 2
