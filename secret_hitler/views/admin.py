"""Write endpoints. Every view here is behind admin_required."""

from datetime import date

from flask import Blueprint, make_response, render_template, request

from ..auth import admin_required
from ..domain import MAX_PLAYERS, MIN_PLAYERS, ROLES, WIN_CONDITIONS
from ..forms import game_form_context
from ..repository import (
    add_player as insert_player,
    all_players,
    create_game as record_game,
    delete_game as remove_game,
)

bp = Blueprint("admin", __name__)


def _trigger(resp, event):
    """Fire a client-side htmx event so the page's other panels refresh."""
    resp.headers["HX-Trigger"] = event
    return resp


def _form_error(message):
    return render_template("partials/_form_error.html",
                           message=message, **game_form_context()), 422


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_roster(form):
    """Read the ticked players and their roles. Returns (roster, error)."""
    roster = []
    hitler_ct = 0
    for pid in form.getlist("include"):      # list of player_id strings
        role = form.get("role_%s" % pid, "Liberal")
        if role not in ROLES:
            role = "Liberal"
        if role == "Hitler":
            hitler_ct += 1
        roster.append((int(pid), role))

    n = len(roster)
    if n < MIN_PLAYERS or n > MAX_PLAYERS:
        return None, "Secret Hitler needs %d–%d players. You selected %d." % (
            MIN_PLAYERS, MAX_PLAYERS, n)
    if hitler_ct != 1:
        return None, "Exactly one player must be Hitler (you set %d)." % hitler_ct
    return roster, None


@bp.route("/games/new")
@admin_required
def new_game_form():
    return render_template("partials/_game_form.html", **game_form_context())


@bp.route("/games", methods=["POST"])
@admin_required
def create_game():
    f = request.form

    win_condition = f.get("win_condition", "")
    if win_condition not in WIN_CONDITIONS:
        return _form_error("Choose a valid win condition.")

    roster, error = _parse_roster(f)
    if error:
        return _form_error(error)

    record_game(
        f.get("played_on") or date.today().isoformat(),
        win_condition,
        roster,
        liberal_policies=_as_int(f.get("liberal_policies")),
        fascist_policies=_as_int(f.get("fascist_policies")),
        notes=(f.get("notes") or "").strip() or None,
    )

    resp = make_response(render_template(
        "partials/_form_success.html",
        faction=WIN_CONDITIONS[win_condition]["faction"],
    ))
    return _trigger(resp, "gameLogged")


@bp.route("/games/<int:game_id>", methods=["DELETE"])
@admin_required
def delete_game(game_id):
    remove_game(game_id)
    return _trigger(make_response(""), "gameLogged")


@bp.route("/players", methods=["POST"])
@admin_required
def add_player():
    name = (request.form.get("name") or "").strip()
    if name:
        insert_player(name)
    resp = make_response(render_template(
        "partials/_roster_picker.html", players=all_players()))
    return _trigger(resp, "playersChanged")
