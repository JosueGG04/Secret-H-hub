"""Reads and writes against the three tables. No computed statistics here."""

import sqlite3

from .db import get_db
from .domain import WIN_CONDITIONS, role_faction


def all_players():
    return get_db().execute(
        "SELECT * FROM players ORDER BY name COLLATE NOCASE").fetchall()


def get_player(player_id):
    return get_db().execute(
        "SELECT * FROM players WHERE id=?", (player_id,)).fetchone()


def add_player(name):
    """Insert a player. Returns False if the name is already taken."""
    db = get_db()
    try:
        db.execute("INSERT INTO players (name) VALUES (?)", (name,))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False          # duplicate name; the picker already lists them


def create_game(played_on, win_condition, roster_roles,
                liberal_policies=None, fascist_policies=None, notes=None):
    """roster_roles: list of (player_id, role)."""
    db = get_db()
    winning = WIN_CONDITIONS[win_condition]["faction"]
    n = len(roster_roles)
    cur = db.execute(
        """INSERT INTO games (played_on, num_players, winning_faction, win_condition,
                              liberal_policies, fascist_policies, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (played_on, n, winning, win_condition, liberal_policies, fascist_policies, notes),
    )
    game_id = cur.lastrowid
    for pid, role in roster_roles:
        won = 1 if role_faction(role) == winning else 0
        db.execute(
            "INSERT INTO game_players (game_id, player_id, role, won) VALUES (?, ?, ?, ?)",
            (game_id, pid, role, won),
        )
    db.commit()
    return game_id


def delete_game(game_id):
    db = get_db()
    db.execute("DELETE FROM games WHERE id=?", (game_id,))
    db.commit()
