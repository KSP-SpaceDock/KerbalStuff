import math
from typing import Union, List, Tuple

from flask import Blueprint, render_template, redirect, request, abort, url_for
from flask_login import login_user, current_user
from sqlalchemy import desc, or_, func
from sqlalchemy.orm import Query
import werkzeug.wrappers

from ..common import adminrequired, with_session
from ..database import db
from ..email import send_bulk_email
from ..objects import Mod, GameVersion, Game, Publisher, User

admin = Blueprint('admin', __name__, template_folder='../../templates/admin')
ITEMS_PER_PAGE = 10


@admin.route("/admin")
@adminrequired
def admin_main() -> werkzeug.wrappers.Response:
    return redirect(url_for('admin.users', page=1))


@admin.route("/admin/users/<int:page>")
@adminrequired
def users(page: int) -> Union[str, werkzeug.wrappers.Response]:
    if page < 1:
        return redirect(url_for('admin.users', page=1, **request.args))
    query = request.args.get('query', type=str)
    if query:
        query = query.lower()
        users = search_users(query)
        user_count = users.count()
        # We can limit here because SqlAlchemy executes queries lazily.
        users = users.offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)
    else:
        users = User.query.order_by(desc(User.created))
        user_count = users.count()
        users = users.offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)

    total_pages = max(1, math.ceil(user_count / ITEMS_PER_PAGE))
    if page > total_pages:
        return redirect(url_for('admin.users', page=total_pages, **request.args))

    return render_template('admin-users.html', users=users, page=page, total_pages=total_pages, query=query)


@admin.route("/admin/blog")
@adminrequired
def blog() -> str:
    return render_template("admin-blog.html")


@admin.route("/admin/publishers/<int:page>")
@adminrequired
def publishers(page: int) -> Union[str, werkzeug.wrappers.Response]:
    if page < 1:
        return redirect(url_for('admin.publishers', page=1, **request.args))
    query = request.args.get('query', type=str)
    if query:
        query = query.lower()
        publishers = search_publishers(query)
        publisher_count = publishers.count()
        publishers = publishers.offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)
    else:
        publishers = Publisher.query.order_by(desc(Publisher.id))
        publisher_count = publishers.count()
        publishers = publishers.offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)

    total_pages = max(1, math.ceil(publisher_count / ITEMS_PER_PAGE))
    if page > total_pages:
        return redirect(url_for('admin.publishers', page=total_pages, **request.args))

    return render_template('admin-publishers.html', publishers=publishers, publisher_count=publisher_count, page=page,
                           total_pages=total_pages, query=query)


@admin.route("/admin/games/<int:page>")
@adminrequired
def games(page: int) -> Union[str, werkzeug.wrappers.Response]:
    if page < 1:
        return redirect(url_for('admin.games', page=1, **request.args))
    query = request.args.get('query', type=str)
    if query:
        query = query.lower()
        games = search_games(query)
        game_count = games.count()
        games = games.offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)
    else:
        games = Game.query.order_by(desc(Game.id))
        game_count = games.count()
        games = games.offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)

    total_pages = max(1, math.ceil(game_count / ITEMS_PER_PAGE))
    if page > total_pages:
        return redirect(url_for('admin.games', page=total_pages, **request.args))

    publishers = Publisher.query.order_by(desc(Publisher.id))

    return render_template('admin-games.html', games=games, publishers=publishers, game_count=game_count, page=page,
                           total_pages=total_pages, query=query)


@admin.route("/admin/gameversions/<int:page>")
@adminrequired
def game_versions(page: int) -> Union[str, werkzeug.wrappers.Response]:
    if page < 1:
        return redirect(url_for('admin.game_versions', page=1, **request.args))
    query = request.args.get('query', type=str)
    if query:
        query = query.lower()
        game_versions = search_game_versions(query)
        game_version_count = game_versions.count()
        game_versions = game_versions.offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)
    else:
        game_versions = GameVersion.query.order_by(desc(GameVersion.id))
        game_version_count = game_versions.count()
        game_versions = game_versions.offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)

    total_pages = max(1, math.ceil(game_version_count / ITEMS_PER_PAGE))
    if page > total_pages:
        return redirect(url_for('admin.game_versions', page=total_pages, **request.args))

    games = Game.query.order_by(desc(Game.id))

    return render_template('admin-game-versions.html', game_versions=game_versions, games=games,
                           game_version_count=game_version_count, page=page, total_pages=total_pages, query=query)


@admin.route("/admin/email", methods=['GET', 'POST'])
@adminrequired
def email() -> Union[str, werkzeug.wrappers.Response]:
    if request.method == 'GET':
        return render_template('admin-email.html')

    subject = request.form.get('subject')
    body = request.form.get('body')
    modders_only = request.form.get('modders-only') == 'on'
    if not subject or not body:
        abort(400)
    users = User.query
    if modders_only:
        users = db.query(User.email) \
            .filter(or_(User.username == current_user.username,
                        db.query(Mod.id).filter(Mod.user_id == User.id).exists()))
    send_bulk_email([u.email for u in users], subject, body)
    return redirect(url_for('admin.email'))


@admin.route("/admin/links")
@adminrequired
def links() -> str:
    return render_template('admin-links.html')


@admin.route("/admin/impersonate/<username>")
@adminrequired
def impersonate(username: str) -> werkzeug.wrappers.Response:
    user = User.query.filter(User.username == username).first()
    login_user(user)
    return redirect("/")


@admin.route("/versions/create", methods=['POST'])
@adminrequired
@with_session
def create_version() -> werkzeug.wrappers.Response:
    friendly = request.form.get("friendly_version")
    gid = request.form.get("ganame")
    if not friendly or not gid:
        return redirect("/asdf")
    if any(GameVersion.query.filter(GameVersion.friendly_version == friendly)):
        return redirect("/fsda")
    version = GameVersion(friendly_version=friendly, game_id=gid)
    db.add(version)
    db.commit()
    return redirect(url_for('admin.game_versions', page=1, **request.args))


@admin.route("/games/create", methods=['POST'])
@adminrequired
@with_session
def create_game() -> werkzeug.wrappers.Response:
    name = request.form.get("gname")
    sname = request.form.get("sname")
    pid = request.form.get("pname")
    if not name or not pid or not sname:
        return redirect("/asdf")
    if any(Game.query.filter(Game.name == name)):
        return redirect("/fsda")

    go = Game(name=name, publisher_id=pid, short=sname)
    db.add(go)
    db.commit()
    return redirect(url_for('admin.games', page=1, **request.args))


@admin.route("/publishers/create", methods=['POST'])
@adminrequired
@with_session
def create_publisher() -> werkzeug.wrappers.Response:
    name = request.form.get("pname")
    if not name:
        return redirect("/asdf")
    if any(Publisher.query.filter(Publisher.name == name)):
        return redirect("/fsda")
    gname = Publisher(name=name)
    db.add(gname)
    db.commit()
    return redirect(url_for('admin.publishers', page=1, **request.args))


@admin.route("/admin/manual-confirmation/<int:user_id>")
@adminrequired
@with_session
def manual_confirm(user_id: int) -> werkzeug.wrappers.Response:
    user = User.query.get(user_id)
    if not user:
        abort(404)
    user.confirmation = None
    return redirect(url_for('profile.view_profile', username=user.username))


# Note: Add .limit() to the returned object if need, per_page is only used to calculate the offset
def search_users(query: str) -> Query:
    temp = User.query.filter(
        func.lower(User.username).contains(query) |
        func.lower(User.email).contains(query) |
        func.lower(User.description).contains(query) |
        func.lower(User.forumUsername).contains(query) |
        func.lower(User.ircNick).contains(query) |
        func.lower(User.redditUsername).contains(query) |
        func.lower(User.twitterUsername).contains(query)
    ).order_by(desc(User.created))
    return temp


def search_publishers(query: str) -> Query:
    return Publisher.query.filter(
        func.lower(Publisher.name).contains(query) |
        func.lower(Publisher.short_description).contains(query) |
        func.lower(Publisher.description).contains(query) |
        func.lower(Publisher.link).contains(query)
    ).order_by(desc(Publisher.id))


def search_games(query: str) -> Query:
    return Game.query.join(Game.publisher).filter(
        func.lower(Game.name).contains(query) |
        func.lower(Game.altname).contains(query) |
        func.lower(Game.short).contains(query) |
        func.lower(Game.short_description).contains(query) |
        func.lower(Game.description).contains(query) |
        func.lower(Game.link).contains(query) |
        func.lower(Publisher.name).contains(query) |
        (search_publishers(query).filter(Publisher.id == Game.publisher_id).count() > 0)
    ).order_by(desc(Game.id))


def search_game_versions(query: str) -> Query:
    return GameVersion.query.filter(
        func.lower(GameVersion.friendly_version).contains(query) |
        (search_games(query).filter(Game.id == GameVersion.game_id).count() > 0)
    ).order_by(desc(GameVersion.id))
