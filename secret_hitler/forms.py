"""Shared template context for the record-a-game form.

The twin of stats.leaderboard.leaderboard_context: three call sites used to
repeat this bundle by hand (the admin guard, the form route, and the validation
error path), which is exactly how they drift apart.
"""

from datetime import date, timedelta

from .domain import (
    FASCIST_TRACK, FASCISTS_BY_SIZE, LIBERAL_TRACK, ROLES, WIN_CONDITIONS,
)
from .repository import all_players


def read_picks(source):
    """The ticked players and their roles, as [(player_id, role)].

    Each chip sends include=<id> for the tick and role_<id> from its role
    buttons. A role that isn't a real one reads as Liberal, and a junk or
    repeated id is skipped, so this never raises on a hand-made request.
    """
    picks, seen = [], set()
    for raw in source.getlist("include"):
        try:
            pid = int(raw)
        except ValueError:
            continue
        if pid in seen:
            continue
        seen.add(pid)
        role = source.get("role_%d" % pid)
        picks.append((pid, role if role in ROLES else "Liberal"))
    return picks


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def game_form_state(source=None):
    """What the form shows: blank, or `source` (a submitted form, or the query
    string of a 'record another' link) so nothing typed is lost."""
    source = source or {}
    today = date.today().isoformat()
    win = source.get("win_condition")
    return {
        "picked": dict(read_picks(source)) if source else {},
        "played_on": source.get("played_on") or today,
        "win_condition": win if win in WIN_CONDITIONS else None,
        "liberal_policies": _as_int(source.get("liberal_policies")),
        "fascist_policies": _as_int(source.get("fascist_policies")),
        "notes": source.get("notes") or "",
    }


def game_form_context(source=None):
    """Everything _game_form.html and _form_error.html need."""
    today = date.today()
    return {
        "players": all_players(),
        "win_conditions": WIN_CONDITIONS,
        "form": game_form_state(source),
        "day_picks": [
            {"label": "Today", "date": today.isoformat()},
            {"label": "Yesterday", "date": (today - timedelta(days=1)).isoformat()},
        ],
        "liberal_track": LIBERAL_TRACK,
        "fascist_track": FASCIST_TRACK,
        "fascists_by_size": FASCISTS_BY_SIZE,
    }
