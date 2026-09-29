"""Shared template context for the record-a-game form.

The twin of stats.leaderboard.leaderboard_context: three call sites used to
repeat this bundle by hand (the admin guard, the form route, and the validation
error path), which is exactly how they drift apart.
"""

from datetime import date

from .domain import WIN_CONDITIONS
from .repository import all_players


def game_form_context():
    """Everything _game_form.html and _form_error.html need."""
    return {
        "players": all_players(),
        "win_conditions": WIN_CONDITIONS,
        "today": date.today().isoformat(),
    }
