"""Write endpoints. Every view here is behind admin_required."""

from flask import Blueprint, make_response, render_template, request, url_for

from ..auth import admin_required
from ..domain import MAX_PLAYERS, MIN_PLAYERS, WIN_CONDITIONS
from ..forms import game_form_context, game_form_state, read_picks
from ..repository import (
    add_player as insert_player,
    all_players,
    create_game as record_game,
    delete_game as remove_game,
    find_player,
)

bp = Blueprint("admin", __name__)


def _trigger(resp, event):
    """Fire a client-side htmx event so the page's other panels refresh."""
    resp.headers["HX-Trigger"] = event
    return resp


def _form_error(message):
    # Re-render with what was submitted, so fixing one mistake doesn't mean
    # re-entering the whole game.
    return render_template("partials/_form_error.html", message=message,
                           **game_form_context(request.form)), 422


def _parse_roster(form):
    """Read the ticked players and their roles. Returns (roster, error)."""
    roster = read_picks(form)
    hitler_ct = sum(1 for _, role in roster if role == "Hitler")

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
    # "Record another" passes the last game's night and players along.
    return render_template("partials/_game_form.html",
                           **game_form_context(request.args))


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

    state = game_form_state(f)
    record_game(
        state["played_on"],
        win_condition,
        roster,
        liberal_policies=state["liberal_policies"],
        fascist_policies=state["fascist_policies"],
        notes=state["notes"].strip() or None,
    )

    # The next game is usually the same night at the same table, so offer a
    # form with both kept and the roles cleared.
    again = url_for("admin.new_game_form", played_on=state["played_on"],
                    include=[pid for pid, _ in roster])
    resp = make_response(render_template(
        "partials/_form_success.html",
        faction=WIN_CONDITIONS[win_condition]["faction"],
        again_url=again,
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
    # The request carries the game form's picks too (hx-include), so the
    # re-rendered roster keeps them, and the newcomer arrives ticked: they're
    # being added because they played. An existing name just gets ticked.
    picked = dict(read_picks(request.form))
    name = (request.form.get("name") or "").strip()
    if name:
        insert_player(name)
        player = find_player(name)
        picked.setdefault(player["id"], "Liberal")
    resp = make_response(render_template(
        "partials/_roster_picker.html", players=all_players(), picked=picked))
    return _trigger(resp, "playersChanged")
