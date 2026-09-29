"""Read-only pages and the htmx fragments they refresh."""

from flask import Blueprint, abort, render_template, request

from ..forms import game_form_context
from ..pagination import PER_PAGE, Page, valid_page
from ..repository import count_games, count_player_games, get_player
from ..stats.dashboard import awards, game_shape_stats, nights_context, pair_rows
from ..stats.leaderboard import leaderboard_context, valid_month
from ..stats.players import (
    game_detail_rows, player_detail, player_history, summary_stats,
)

bp = Blueprint("public", __name__)


def chronicle_context(page_number=1):
    """One page of the game log, so index() and games_list() can't drift."""
    page = Page(page_number, count_games())
    return {"games": game_detail_rows(PER_PAGE, page.offset), "page": page}


def history_context(player, page_number=1):
    """One page of a player's appearances, with the pager's own numbers."""
    page = Page(page_number, count_player_games(player["id"]))
    return {
        "history": player_history(player["id"], PER_PAGE, page.offset),
        "page": page,
        "player_id": player["id"],
        "player_name": player["name"],
    }


@bp.route("/")
def index():
    # index.html includes the leaderboard and (for admins) the record-a-game form,
    # so it needs both of their context bundles.
    return render_template(
        "index.html",
        summary=summary_stats(),
        **chronicle_context(),
        **game_form_context(),
        **leaderboard_context(),
    )


@bp.route("/leaderboard")
def leaderboard():
    month = valid_month(request.args.get("month"))
    return render_template("partials/_leaderboard.html", **leaderboard_context(month))


@bp.route("/games/list")
def games_list():
    page = valid_page(request.args.get("page"))
    return render_template("partials/_games.html", **chronicle_context(page))


@bp.route("/summary")
def summary():
    return render_template("partials/_summary.html", summary=summary_stats())


@bp.route("/player/<int:player_id>")
def player_page(player_id):
    detail = player_detail(player_id)
    if not detail:
        abort(404)
    return render_template("player.html", d=detail,
                           **history_context(detail["player"]))


@bp.route("/player/<int:player_id>/games")
def player_games(player_id):
    player = get_player(player_id)
    if not player:
        abort(404)
    page = valid_page(request.args.get("page"))
    return render_template("partials/_player_games.html",
                           **history_context(player, page))


@bp.route("/dashboard")
def dashboard():
    # Only the Game Nights chart is interactive here; the rest is server-rendered,
    # since the gameLogged event comes from the admin form on the home page.
    return render_template(
        "dashboard.html",
        summary=summary_stats(),
        shape=game_shape_stats(),
        awards=awards(),
        pairs=pair_rows(),
        nights=nights_context(),
    )


@bp.route("/dashboard/nights")
def dashboard_nights():
    return render_template("partials/_nights.html",
                           nights=nights_context(request.args.get("month")))
