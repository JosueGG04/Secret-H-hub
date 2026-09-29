"""Fixtures: a fresh app on a throwaway database, seeded with a known table."""

import pytest

from secret_hitler import create_app
from secret_hitler.config import TestConfig
from secret_hitler.repository import add_player, all_players, create_game


@pytest.fixture
def app(tmp_path):
    class Cfg(TestConfig):
        DB_PATH = str(tmp_path / "test.db")

    return create_app(Cfg)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin(client):
    """A client that has already signed in as the admin."""
    client.post("/login", data={"username": TestConfig.ADMIN_USER,
                                "password": TestConfig.ADMIN_PASSWORD})
    return client


NAMES = ["Ada", "Bruno", "Cleo", "Dov", "Eli", "Fern"]


@pytest.fixture
def table(app):
    """Six players and three games, so standings and streaks have something to say.

    Ada wins twice then loses; Bruno is Hitler in the first game only.
    Returns {name: player_id}.
    """
    with app.app_context():
        for name in NAMES:
            add_player(name)
        ids = {r["name"]: r["id"] for r in all_players()}

        def roster(hitler, fascist):
            return [(ids[n], "Hitler" if n == hitler else
                             "Fascist" if n == fascist else "Liberal")
                    for n in NAMES[:5]]

        # Liberals win: Ada, Cleo, Dov (Eli is the 5th Liberal)
        create_game("2026-07-01", "liberal_policies", roster("Bruno", "Eli"))
        # Liberals win again
        create_game("2026-07-08", "hitler_executed", roster("Eli", "Bruno"))
        # Fascists win, so Ada loses
        create_game("2026-08-02", "fascist_policies", roster("Eli", "Bruno"))
    return ids


@pytest.fixture
def busy_table(app):
    """14 games across two months — enough for two pages of ten and two month
    chips. Every game has the same five players, so one player's history pages
    too. Returns {name: player_id}.

    March gets 10 games over 4 nights (one night doubled, so it is the month's
    busiest); April gets 4 games over 4 nights.
    """
    nights = (
        [("2026-03-%02d" % d, 2) for d in (2, 9)] +      # 4 games
        [("2026-03-%02d" % d, 3) for d in (16, 23)] +    # 6 games -> 10 in March
        [("2026-04-%02d" % d, 1) for d in (6, 13, 20, 27)]
    )
    with app.app_context():
        for name in NAMES:
            add_player(name)
        ids = {r["name"]: r["id"] for r in all_players()}
        roster = [(ids[n], "Hitler" if n == "Bruno" else "Liberal")
                  for n in NAMES[:5]]
        for played_on, count in nights:
            for _ in range(count):
                create_game(played_on, "liberal_policies", roster)
    return ids
