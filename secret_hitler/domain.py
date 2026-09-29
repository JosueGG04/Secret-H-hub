"""Secret Hitler rules the rest of the app scores games against."""

# Each win condition maps to the faction that wins and a human label.
WIN_CONDITIONS = {
    "liberal_policies":  {"faction": "Liberal", "label": "Five Liberal policies enacted"},
    "hitler_executed":   {"faction": "Liberal", "label": "Hitler assassinated"},
    "fascist_policies":  {"faction": "Fascist", "label": "Six Fascist policies enacted"},
    "hitler_chancellor": {"faction": "Fascist", "label": "Hitler elected Chancellor"},
}

ROLES = ["Liberal", "Fascist", "Hitler"]

MIN_PLAYERS = 5
MAX_PLAYERS = 10


def role_faction(role):
    """Hitler counts as a Fascist for win purposes."""
    return "Liberal" if role == "Liberal" else "Fascist"


def condition_label(win_condition):
    """Human label for a stored win_condition, falling back to the raw key."""
    return WIN_CONDITIONS.get(win_condition, {}).get("label", win_condition)
