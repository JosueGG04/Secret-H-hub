"""Standings, all-time or scoped to a single month."""

import re
from datetime import datetime

from ..db import get_db

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def valid_month(month):
    """Normalise a ?month= query arg; anything malformed means 'all time'."""
    return month if month and MONTH_RE.match(month) else None


def month_label(month):
    """'2026-07' -> 'July 2026'. Falls back to the raw string if unparseable."""
    try:
        return datetime.strptime(month + "-01", "%Y-%m-%d").strftime("%B %Y")
    except ValueError:
        return month


def available_months(limit=12):
    """Months that have games, newest first, capped so the chip row stays bounded."""
    rows = get_db().execute(
        "SELECT DISTINCT substr(played_on, 1, 7) AS m FROM games ORDER BY m DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [{"value": r["m"], "label": month_label(r["m"])} for r in rows]


def leaderboard_rows(min_games=1, month=None):
    """Standings rows. Pass month as 'YYYY-MM' to score only that month's games."""
    db = get_db()
    rows = db.execute(
        """
        SELECT p.id, p.name,
               COUNT(gp.id)                          AS games,
               COALESCE(SUM(gp.won), 0)              AS wins,
               COALESCE(SUM(CASE WHEN gp.role='Liberal' THEN 1 ELSE 0 END), 0) AS lib_games,
               COALESCE(SUM(CASE WHEN gp.role='Fascist' THEN 1 ELSE 0 END), 0) AS fas_games,
               COALESCE(SUM(CASE WHEN gp.role='Hitler'  THEN 1 ELSE 0 END), 0) AS hitler_games
        FROM players p
        LEFT JOIN (
            -- The month predicate lives here, not in the ON clause: filtering the
            -- join would still leave other months' rows for COUNT/SUM to see.
            SELECT gp.id, gp.player_id, gp.role, gp.won
            FROM game_players gp
            JOIN games g ON g.id = gp.game_id
            WHERE ? IS NULL OR substr(g.played_on, 1, 7) = ?
        ) gp ON gp.player_id = p.id
        GROUP BY p.id
        """,
        (month, month),
    ).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        if month and not d["games"]:
            continue          # a monthly board lists only that month's participants
        d["losses"] = d["games"] - d["wins"]
        d["win_rate"] = (d["wins"] / d["games"]) if d["games"] else 0.0
        d["ranked"] = d["games"] >= min_games
        result.append(d)

    # Ranked players first (by wins, then win rate, then games, then name); unranked after.
    result.sort(key=lambda d: (
        not d["ranked"],
        -d["wins"],
        -d["win_rate"],
        -d["games"],
        d["name"].lower(),
    ))
    rank = 0
    prev_wins = None
    for i, d in enumerate(result):
        if d["ranked"]:
            if d["wins"] != prev_wins:
                rank = i + 1
                prev_wins = d["wins"]
            d["rank"] = rank
        else:
            d["rank"] = None
    return result


def faction_split(month=None):
    """Liberal vs Fascist game wins, all time or for one 'YYYY-MM' month."""
    row = get_db().execute(
        """SELECT COUNT(*) AS games,
                  COALESCE(SUM(winning_faction='Liberal'), 0) AS lib
           FROM games
           WHERE ? IS NULL OR substr(played_on, 1, 7) = ?""",
        (month, month),
    ).fetchone()
    games, lib = row["games"], row["lib"]
    fas = games - lib
    return {
        "games": games,
        "lib": lib,
        "fas": fas,
        "lib_pct": (lib / games * 100) if games else 0.0,
        "fas_pct": (fas / games * 100) if games else 0.0,
    }


def leaderboard_context(month=None):
    """Everything _leaderboard.html needs, so index() and leaderboard() can't drift."""
    return {
        "board": leaderboard_rows(month=month),
        "split": faction_split(month),
        "month": month,
        "month_label": month_label(month) if month else None,
        "months": available_months(),
    }
