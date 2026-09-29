"""Table-wide totals, the game log, and a single player's record."""

from ..db import get_db
from ..domain import ROLES, condition_label
from ..repository import get_player


def summary_stats():
    row = get_db().execute(
        """SELECT (SELECT COUNT(*) FROM games)   AS total,
                  (SELECT COUNT(*) FROM games WHERE winning_faction='Liberal') AS lib,
                  (SELECT COUNT(*) FROM players) AS players"""
    ).fetchone()
    total, lib = row["total"], row["lib"]
    fas = total - lib
    return {
        "total_games": total,
        "liberal_wins": lib,
        "fascist_wins": fas,
        "liberal_pct": (lib / total * 100) if total else 0,
        "fascist_pct": (fas / total * 100) if total else 0,
        "total_players": row["players"],
    }


def game_detail_rows(limit=None, offset=0):
    """Recent games with their rosters attached. Newest night first.

    Pass limit/offset for one page of the Chronicle; the roster query then
    narrows to that page's games, so this stays two queries either way.
    """
    db = get_db()
    sql = "SELECT * FROM games ORDER BY played_on DESC, id DESC"
    if limit is None:
        games = db.execute(sql).fetchall()
    else:
        games = db.execute(sql + " LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    if not games:
        return []

    ids = [g["id"] for g in games]
    rosters = {}
    for r in db.execute(
        """SELECT gp.game_id, gp.role, gp.won, p.name, p.id AS player_id
           FROM game_players gp JOIN players p ON p.id = gp.player_id
           WHERE gp.game_id IN (%s)
           ORDER BY (gp.role='Hitler') DESC, (gp.role='Fascist') DESC, p.name"""
        % ",".join("?" * len(ids)),
        ids,
    ):
        rosters.setdefault(r["game_id"], []).append(dict(r))

    out = []
    for game in games:
        d = dict(game)
        d["condition_label"] = condition_label(game["win_condition"])
        d["roster"] = rosters.get(game["id"], [])
        out.append(d)
    return out


def player_detail(player_id):
    """A player's record. Totals and the per-role split cover every game they
    played; the visible history is paged separately by player_history()."""
    p = get_player(player_id)
    if not p:
        return None
    rows = get_db().execute(
        "SELECT role, won FROM game_players WHERE player_id = ?", (player_id,)
    ).fetchall()

    def bucket(role):
        gp = [r for r in rows if r["role"] == role]
        wins = sum(r["won"] for r in gp)
        return {"games": len(gp), "wins": wins,
                "rate": (wins / len(gp)) if gp else 0.0}

    games = len(rows)
    wins = sum(r["won"] for r in rows)
    return {
        "player": dict(p),
        "games": games,
        "wins": wins,
        "losses": games - wins,
        "win_rate": (wins / games) if games else 0.0,
        "by_role": {role: bucket(role) for role in ROLES},
    }


def player_history(player_id, limit=None, offset=0):
    """One page of a player's appearances, most recent night first."""
    sql = """SELECT gp.*, g.played_on, g.winning_faction, g.win_condition, g.num_players
             FROM game_players gp JOIN games g ON g.id = gp.game_id
             WHERE gp.player_id = ?
             ORDER BY g.played_on DESC, g.id DESC"""
    params = [player_id]
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params += [limit, offset]

    history = []
    for r in get_db().execute(sql, params):
        d = dict(r)
        d["condition_label"] = condition_label(r["win_condition"])
        history.append(d)
    return history
