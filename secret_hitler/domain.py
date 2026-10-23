"""Secret Hitler rules the rest of the app scores games against."""

# Each win condition maps to the faction that wins, a human label, and a
# shorter one for tight spots like the search chips.
WIN_CONDITIONS = {
    "liberal_policies":  {"faction": "Liberal", "label": "Five Liberal policies enacted",
                          "short": "Five Liberal policies"},
    "hitler_executed":   {"faction": "Liberal", "label": "Hitler assassinated",
                          "short": "Hitler assassinated"},
    "fascist_policies":  {"faction": "Fascist", "label": "Six Fascist policies enacted",
                          "short": "Six Fascist policies"},
    "hitler_chancellor": {"faction": "Fascist", "label": "Hitler elected Chancellor",
                          "short": "Hitler elected Chancellor"},
}

ROLES = ["Liberal", "Fascist", "Hitler"]

MIN_PLAYERS = 5
MAX_PLAYERS = 10

# Fascists dealt besides Hitler, by table size: the rulebook's setup table.
# The record form only hints with it; house rules may differ.
FASCISTS_BY_SIZE = {5: 1, 6: 1, 7: 2, 8: 2, 9: 3, 10: 3}

# How long each policy track is; filling one wins the game.
LIBERAL_TRACK = 5
FASCIST_TRACK = 6


def role_faction(role):
    """Hitler counts as a Fascist for win purposes."""
    return "Liberal" if role == "Liberal" else "Fascist"


def condition_label(win_condition):
    """Human label for a stored win_condition, falling back to the raw key."""
    return WIN_CONDITIONS.get(win_condition, {}).get("label", win_condition)
