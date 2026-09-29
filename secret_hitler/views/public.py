"""Read-only pages and the htmx fragments they refresh."""

from flask import Blueprint, abort, render_template, request

from ..forms import game_form_context
from ..stats.dashboard import awards, game_shape_stats, pair_rows
from ..stats.leaderboard import leaderboard_context, valid_month
from ..stats.players import game_detail_rows, player_detail, summary_stats

bp = Blueprint("public", __name__)


@bp.route("/")
def index():
    # index.html includes the leaderboard and (for admins) the record-a-game form,
    # so it needs both of their context bundles.
    return render_template(
        "index.html",
        games=game_detail_rows(),
        summary=summary_stats(),
        **game_form_context(),
        **leaderboard_context(),
    )


@bp.route("/leaderboard")
def leaderboard():
    month = valid_month(request.args.get("month"))
    return render_template("partials/_leaderboard.html", **leaderboard_context(month))


@bp.route("/games/list")
def games_list():
    return render_template("partials/_games.html", games=game_detail_rows())


@bp.route("/summary")
def summary():
    return render_template("partials/_summary.html", summary=summary_stats())


@bp.route("/player/<int:player_id>")
def player_page(player_id):
    detail = player_detail(player_id)
    if not detail:
        abort(404)
    return render_template("player.html", d=detail)


@bp.route("/dashboard")
def dashboard():
    # Server-rendered only: the gameLogged event comes from the admin form on the
    # home page, so there is nothing here for htmx to refresh.
    return render_template(
        "dashboard.html",
        summary=summary_stats(),
        shape=game_shape_stats(),
        awards=awards(),
        pairs=pair_rows(),
    )
