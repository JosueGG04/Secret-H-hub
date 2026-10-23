"""The match search: query-string filters in, matching games out.

Every filter is optional and they AND together. Malformed values are dropped
rather than rejected, like ?page= and ?month=, so a hand-edited or stale URL
still renders a sensible list.
"""

from datetime import date, timedelta

from .db import get_db
from .domain import MAX_PLAYERS, MIN_PLAYERS, ROLES, WIN_CONDITIONS
from .stats.players import attach_rosters

# A player filter's value: in the game at all, or in a specific role.
ANY_ROLE = "any"
PLAYER_CHOICES = [ANY_ROLE] + ROLES
FACTIONS = ["Liberal", "Fascist"]
# One outcome filter covers both questions: a faction means "won either way",
# a win condition means "won exactly this way". One choice can't contradict
# itself the way separate faction and condition filters could.
OUTCOMES = FACTIONS + list(WIN_CONDITIONS)
SIZES = list(range(MIN_PLAYERS, MAX_PLAYERS + 1))


def _valid_date(raw):
    try:
        return date.fromisoformat(raw).isoformat() if raw else None
    except ValueError:
        return None


def _valid_size(raw):
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    return n if MIN_PLAYERS <= n <= MAX_PLAYERS else None


def parse_filters(args, player_ids):
    """Read the search form out of request.args.

    Players come in as one key each, p<id>=any|Liberal|Fascist|Hitler, so the
    whole filter set stays single-valued and can be handed to url_for().
    The form's chips send p<id>=any for the tick and r<id>=<role> from the
    role buttons beside it; r<id> wins when present, and links fold the two
    back into p<id>. An r<id> without its p<id> is an unticked player.
    `player_ids` is the set of real ids; anything else is ignored.
    """
    players = {}
    for key, value in args.items():
        if not key.startswith("p") or value not in PLAYER_CHOICES:
            continue
        try:
            pid = int(key[1:])
        except ValueError:
            continue
        if pid in player_ids:
            role = args.get("r%d" % pid)
            players[pid] = role if role in PLAYER_CHOICES else value

    outcome = args.get("outcome")
    return {
        "players": players,
        "from": _valid_date(args.get("from")),
        "to": _valid_date(args.get("to")),
        "outcome": outcome if outcome in OUTCOMES else None,
        "size": _valid_size(args.get("size")),
        "q": (args.get("q") or "").strip() or None,
    }


def filter_args(filters):
    """The canonical query string for a filter set, for links and the URL bar."""
    out = {"p%d" % pid: role for pid, role in sorted(filters["players"].items())}
    for key in ("from", "to", "outcome", "size", "q"):
        if filters[key] is not None:
            out[key] = filters[key]
    return out


def date_presets(today):
    """Quick picks for the When row. Each only sets a start date (and clears
    the end), so the date boxes stay the one source of truth."""
    return [
        {"label": "Any time", "from": ""},
        {"label": "This month", "from": today.replace(day=1).isoformat()},
        {"label": "Last 90 days", "from": (today - timedelta(days=89)).isoformat()},
        {"label": "This year", "from": today.replace(month=1, day=1).isoformat()},
    ]


def _escape_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _where(filters):
    clauses, params = [], []
    for pid, role in sorted(filters["players"].items()):
        sql = ("EXISTS (SELECT 1 FROM game_players gp"
               " WHERE gp.game_id = g.id AND gp.player_id = ?")
        params.append(pid)
        if role != ANY_ROLE:
            sql += " AND gp.role = ?"
            params.append(role)
        clauses.append(sql + ")")

    for key, sql in (("from", "g.played_on >= ?"),
                     ("to", "g.played_on <= ?"),
                     ("size", "g.num_players = ?")):
        if filters[key] is not None:
            clauses.append(sql)
            params.append(filters[key])

    if filters["outcome"] in FACTIONS:
        clauses.append("g.winning_faction = ?")
        params.append(filters["outcome"])
    elif filters["outcome"]:
        clauses.append("g.win_condition = ?")
        params.append(filters["outcome"])

    if filters["q"]:
        clauses.append("g.notes LIKE ? ESCAPE '\\'")
        params.append("%" + _escape_like(filters["q"]) + "%")

    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def search_tally(filters):
    """How many games match, and how they split by winning faction."""
    where, params = _where(filters)
    row = get_db().execute(
        """SELECT COUNT(*) AS total,
                  COALESCE(SUM(g.winning_faction = 'Liberal'), 0) AS lib
           FROM games g""" + where,
        params,
    ).fetchone()
    return {"total": row["total"], "lib": row["lib"], "fas": row["total"] - row["lib"]}


def search_games(filters, limit, offset=0):
    """One page of matching games, newest night first, rosters attached."""
    where, params = _where(filters)
    games = get_db().execute(
        "SELECT g.* FROM games g" + where +
        " ORDER BY g.played_on DESC, g.id DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return attach_rosters(games)
