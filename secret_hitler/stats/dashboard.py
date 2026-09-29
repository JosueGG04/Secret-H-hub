"""Aggregates behind /dashboard: how games end, superlatives, and pairings."""

import itertools
from datetime import datetime

from ..db import get_db
from ..domain import WIN_CONDITIONS, role_faction
from .leaderboard import available_months, month_label, valid_month


def _night_label(played_on):
    """'2026-07-03' -> ('Jul', '3'). Falls back to the raw string if unparseable.

    Month and day stay separate so the narrow layout can drop the month.
    """
    try:
        d = datetime.strptime(played_on, "%Y-%m-%d")
    except ValueError:
        return "", played_on
    return d.strftime("%b"), str(d.day)   # %-d is not portable to Windows


def nights_context(month=None):
    """One month of game nights, oldest first, plus the chip row's own data.

    The chart draws one column per night, so it is scoped to a single month to
    keep its width bounded; `month=None` means the most recent month on record.
    Mirrors stats.leaderboard.leaderboard_context().
    """
    months = available_months()
    month = valid_month(month)
    if month is None or month not in [m["value"] for m in months]:
        month = months[0]["value"] if months else None

    nights = []
    if month:
        for r in get_db().execute(
            """SELECT played_on, COUNT(*) AS games,
                      COALESCE(SUM(winning_faction='Liberal'), 0) AS lib
               FROM games
               WHERE substr(played_on, 1, 7) = ?
               GROUP BY played_on ORDER BY played_on""",
            (month,),
        ):
            d = dict(r)
            d["fas"] = d["games"] - d["lib"]
            d["month"], d["day"] = _night_label(d["played_on"])
            d["label"] = ("%s %s" % (d["month"], d["day"])).strip()
            nights.append(d)

    # Bars scale to the busiest night of the month on show, so a quiet month
    # still fills the plot; exact counts stay in each bar's tooltip.
    busiest = max((n["games"] for n in nights), default=0)
    # Only the first peak gets a printed cap — nights often tie at the top and
    # a number over each one is noise. An index into *this* month's list.
    peak = next((i for i, n in enumerate(nights) if n["games"] == busiest), None)

    return {
        "nights": nights,
        "busiest": busiest,
        "peak": peak,
        "month": month,
        "month_label": month_label(month) if month else None,
        "months": months,
    }


def game_shape_stats():
    """How games end and how table size skews them."""
    db = get_db()
    total = db.execute("SELECT COUNT(*) c FROM games").fetchone()["c"]

    counts = {r["win_condition"]: r["c"] for r in db.execute(
        "SELECT win_condition, COUNT(*) c FROM games GROUP BY win_condition"
    )}
    # Every condition gets a row, even at zero, so the chart keeps its shape.
    conditions = [
        {"key": key, "label": meta["label"], "faction": meta["faction"],
         "count": counts.get(key, 0),
         "pct": (counts.get(key, 0) / total * 100) if total else 0.0}
        for key, meta in WIN_CONDITIONS.items()
    ]
    conditions.sort(key=lambda c: (-c["count"], c["label"]))
    most = conditions[0]["count"] if conditions else 0

    by_size = []
    for r in db.execute(
        """SELECT num_players AS n, COUNT(*) AS games,
                  COALESCE(SUM(winning_faction='Liberal'), 0) AS lib
           FROM games GROUP BY num_players ORDER BY num_players"""
    ):
        d = dict(r)
        d["fas"] = d["games"] - d["lib"]
        d["lib_pct"] = d["lib"] / d["games"] * 100
        d["fas_pct"] = d["fas"] / d["games"] * 100
        by_size.append(d)

    return {
        "conditions": conditions,
        "most": most,
        "by_size": by_size,
        "total_games": total,
    }


def _player_tallies():
    """Per-player counters, walked in roster order so streaks stay chronological."""
    rows = get_db().execute(
        """SELECT gp.player_id, gp.role, gp.won, p.name, g.played_on, g.id AS game_id
           FROM game_players gp
           JOIN games g   ON g.id = gp.game_id
           JOIN players p ON p.id = gp.player_id
           ORDER BY gp.player_id, g.played_on, g.id"""
    ).fetchall()

    stats = {}
    for r in rows:
        s = stats.setdefault(r["player_id"], {
            "id": r["player_id"], "name": r["name"], "games": 0,
            "lib_games": 0, "lib_wins": 0, "fas_games": 0, "fas_wins": 0,
            "hitler": 0, "results": [],
        })
        s["games"] += 1
        s["results"].append(r["won"])
        if r["role"] == "Hitler":
            s["hitler"] += 1
        if role_faction(r["role"]) == "Liberal":
            s["lib_games"] += 1
            s["lib_wins"] += r["won"]
        else:
            s["fas_games"] += 1
            s["fas_wins"] += r["won"]
    return stats


def _longest_run(results, target):
    best = run = 0
    for won in results:
        run = run + 1 if won == target else 0
        best = max(best, run)
    return best


def awards(min_games=5, min_role_games=3):
    """Superlatives for the hall of fame. Tiles with no qualifier are dropped."""
    stats = _player_tallies()
    for s in stats.values():
        s["streak"] = _longest_run(s["results"], 1)
        s["drought"] = _longest_run(s["results"], 0)

    def pick(candidates, value):
        """Highest value wins; ties break on games played, then name — as in leaderboard_rows."""
        if not candidates:
            return None
        return sorted(candidates, key=lambda s: (-value(s), -s["games"], s["name"].lower()))[0]

    everyone = list(stats.values())
    tiles = []

    def add(label, winner, value, detail):
        if winner:
            tiles.append({"label": label, "player_id": winner["id"], "name": winner["name"],
                          "value": value(winner), "detail": detail(winner)})

    libs = [s for s in everyone if s["lib_games"] >= min_role_games]
    add("Best Liberal", pick(libs, lambda s: s["lib_wins"] / s["lib_games"]),
        lambda s: "%.0f%%" % (s["lib_wins"] / s["lib_games"] * 100),
        lambda s: "%d of %d as Liberal" % (s["lib_wins"], s["lib_games"]))

    fas = [s for s in everyone if s["fas_games"] >= min_role_games]
    add("Best Fascist", pick(fas, lambda s: s["fas_wins"] / s["fas_games"]),
        lambda s: "%.0f%%" % (s["fas_wins"] / s["fas_games"] * 100),
        lambda s: "%d of %d on the right" % (s["fas_wins"], s["fas_games"]))

    seasoned = [s for s in everyone if s["games"] >= min_games]
    add("Longest Streak", pick([s for s in seasoned if s["streak"] > 1], lambda s: s["streak"]),
        lambda s: "%d" % s["streak"], lambda s: "wins in a row")
    add("Coldest Streak", pick([s for s in seasoned if s["drought"] > 1], lambda s: s["drought"]),
        lambda s: "%d" % s["drought"], lambda s: "losses in a row")

    add("Most Faithful", pick(everyone, lambda s: s["games"]),
        lambda s: "%d" % s["games"], lambda s: "games at the table")
    add("Marked by Fate", pick([s for s in everyone if s["hitler"] > 0], lambda s: s["hitler"]),
        lambda s: "%d" % s["hitler"], lambda s: "times dealt Hitler")

    return tiles


def pair_rows(min_together=4, limit=6):
    """Who wins together, and who keeps beating whom.

    Walked in Python rather than a self-join: ~950 pairings across the whole
    table, and this way the Liberal/Fascist split reuses role_faction().
    """
    rows = get_db().execute(
        """SELECT gp.game_id, gp.player_id, gp.role, gp.won, p.name
           FROM game_players gp JOIN players p ON p.id = gp.player_id"""
    ).fetchall()

    by_game = {}
    for r in rows:
        by_game.setdefault(r["game_id"], []).append(r)

    allies, rivals = {}, {}
    for roster in by_game.values():
        roster = sorted(roster, key=lambda r: r["name"].lower())
        for a, b in itertools.combinations(roster, 2):
            key = (a["player_id"], b["player_id"])
            if role_faction(a["role"]) == role_faction(b["role"]):
                d = allies.setdefault(key, {"id1": a["player_id"], "n1": a["name"],
                                            "id2": b["player_id"], "n2": b["name"],
                                            "games": 0, "wins": 0})
                d["games"] += 1
                d["wins"] += a["won"]          # same faction, so one outcome covers both
            else:
                d = rivals.setdefault(key, {"id1": a["player_id"], "n1": a["name"],
                                            "id2": b["player_id"], "n2": b["name"],
                                            "games": 0, "w1": 0, "w2": 0})
                d["games"] += 1
                d["w1"] += a["won"]
                d["w2"] += b["won"]

    duos = [d for d in allies.values() if d["games"] >= min_together]
    for d in duos:
        d["losses"] = d["games"] - d["wins"]
        d["rate"] = d["wins"] / d["games"]
    duos.sort(key=lambda d: (-d["rate"], -d["games"], d["n1"].lower()))

    feuds = [d for d in rivals.values() if d["games"] >= min_together]
    for d in feuds:
        # Name the winner of the feud first so the row reads as a verdict.
        if d["w2"] > d["w1"]:
            d["id1"], d["n1"], d["w1"], d["id2"], d["n2"], d["w2"] = \
                d["id2"], d["n2"], d["w2"], d["id1"], d["n1"], d["w1"]
        d["edge"] = d["w1"] - d["w2"]
    feuds.sort(key=lambda d: (-d["edge"], -d["games"], d["n1"].lower()))

    return {"duos": duos[:limit], "rivals": feuds[:limit],
            "min_together": min_together}
