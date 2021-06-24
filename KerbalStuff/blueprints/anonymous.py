import os.path

import werkzeug.wrappers
from flask import Blueprint, render_template, abort, request, Response, make_response, send_file
from flask_login import current_user
from sqlalchemy import desc
from datetime import timezone

from ..common import dumb_object, paginate_query, get_paginated_mods, get_game_info, get_games, \
    get_featured_mods, get_top_mods, get_new_mods, get_updated_mods, sendfile
from ..config import _cfg
from ..database import db
from ..objects import Featured, Mod, ModVersion, User

anonymous = Blueprint('anonymous', __name__, template_folder='../../templates/anonymous')


@anonymous.route("/")
def index() -> str:
    return render_template("index.html", games=get_games())


@anonymous.route("/<gameshort>")
def game(gameshort: str) -> str:
    ga = get_game_info(short=gameshort)
    featured = get_featured_mods(ga.id, 6)
    top = get_top_mods(ga.id, 6)
    new = get_new_mods(ga.id, 6)
    recent = get_updated_mods(ga.id, 6)
    user_count = User.query.count()
    mod_count = Mod.query.filter(Mod.game_id == ga.id, Mod.published == True).count()
    following = sorted(filter(lambda m: m.game_id == ga.id, current_user.following),
                       key=lambda m: m.updated, reverse=True)[:6] if current_user else list()
    return render_template("game.html",
                           ga=ga,
                           featured=featured,
                           new=new,
                           top=top,
                           recent=recent,
                           user_count=user_count,
                           mod_count=mod_count,
                           yours=following)


@anonymous.route("/content/<path:path>")
def content(path: str) -> werkzeug.wrappers.Response:
    storage = _cfg('storage')
    if not storage:
        abort(404)

    return sendfile(path, True)


@anonymous.route("/browse")
def browse() -> str:
    featured = get_featured_mods(None, 6)
    top = get_top_mods(None, 6)
    new = get_new_mods(None, 6)
    return render_template("browse.html", featured=featured, top=top, new=new)


@anonymous.route("/browse/new")
def browse_new() -> str:
    mods = Mod.query.filter(Mod.published).order_by(desc(Mod.created))
    mods, page, total_pages = paginate_query(mods)
    return render_template("browse-list.html", mods=mods, page=page, total_pages=total_pages,
                           url="/browse/new", name="Newest Mods", rss="/browse/new.rss")


@anonymous.route("/browse/new.rss")
def browse_new_rss() -> Response:
    site_name = _cfg('site-name')
    if not site_name:
        abort(404)
    mods = get_new_mods(None, 30)
    return Response(render_template("rss.xml", mods=mods, title="New mods on " + site_name,
                                    description="The newest mods on " + site_name,
                                    url="/browse/new"), mimetype="text/xml")


@anonymous.route("/browse/updated")
def browse_updated() -> str:
    mods = Mod.query.filter(Mod.published, Mod.versions.any(ModVersion.id != Mod.default_version_id)).order_by(desc(Mod.updated))
    mods, page, total_pages = paginate_query(mods)
    return render_template("browse-list.html", mods=mods, page=page, total_pages=total_pages,
                           url="/browse/updated", name="Recently Updated Mods", rss="/browse/updated.rss")


@anonymous.route("/browse/updated.rss")
def browse_updated_rss() -> Response:
    site_name = _cfg('site-name')
    if not site_name:
        abort(404)
    mods = get_updated_mods(None, 30)
    return Response(render_template("rss.xml", mods=mods, title="Recently updated on " + site_name,
                                    description="Mods on " +
                                    site_name + " updated recently",
                                    url="/browse/updated"), mimetype="text/xml")


@anonymous.route("/browse/top")
def browse_top() -> str:
    mods, page, total_pages = get_paginated_mods()
    return render_template("browse-list.html", mods=mods, page=page, total_pages=total_pages,
                           url="/browse/top", name="Popular Mods")


@anonymous.route("/browse/featured")
def browse_featured() -> str:
    mods = Featured.query.order_by(desc(Featured.created))
    mods, page, total_pages = paginate_query(mods)
    mods = [f.mod for f in mods]
    return render_template("browse-list.html", mods=mods, page=page, total_pages=total_pages,
                           url="/browse/featured", name="Featured Mods", rss="/browse/featured.rss")


@anonymous.route("/browse/featured.rss")
def browse_featured_rss() -> Response:
    site_name = _cfg('site-name')
    if not site_name:
        abort(404)
    mods = []
    for fm in get_featured_mods(None, 30):
        # Add each mod but with created set to when it was featured
        fmod = dumb_object(fm.mod)
        fmod['created'] = fm.created.astimezone(timezone.utc)
        mods.append(fmod)
    return Response(render_template("rss.xml", mods=mods, title="Featured mods on " + site_name,
                                    description="Featured mods on " + site_name,
                                    url="/browse/featured"),
                    mimetype="text/xml")


@anonymous.route("/browse/all")
def browse_all() -> str:
    mods, page, total_pages = get_paginated_mods()
    return render_template("browse-list.html", mods=mods, page=page, total_pages=total_pages,
                           url="/browse/all", name="All Mods")


@anonymous.route("/<gameshort>/browse")
def singlegame_browse(gameshort: str) -> str:
    ga = get_game_info(short=gameshort)
    featured = get_featured_mods(ga.id, 6)
    top = get_top_mods(ga.id, 6)
    new = get_new_mods(ga.id, 6)
    return render_template("browse.html", featured=featured, top=top, ga=ga, new=new)


@anonymous.route("/<gameshort>/browse/new")
def singlegame_browse_new(gameshort: str) -> str:
    ga = get_game_info(short=gameshort)
    mods = Mod.query.filter(Mod.published, Mod.game_id == ga.id).order_by(desc(Mod.created))
    mods, page, total_pages = paginate_query(mods)
    return render_template("browse-list.html", mods=mods, page=page, total_pages=total_pages, ga=ga,
                           url="/browse/new", name="Newest Mods", rss="/browse/new.rss")


@anonymous.route("/<gameshort>/browse/new.rss")
def singlegame_browse_new_rss(gameshort: str) -> Response:
    site_name = _cfg('site-name')
    if not site_name:
        abort(404)
    ga = get_game_info(short=gameshort)
    mods = get_new_mods(ga.id, 30)
    return Response(render_template("rss.xml", mods=mods, title="New mods on " + site_name, ga=ga,
                                    description="The newest mods on " + site_name,
                                    url="/browse/new"),
                    mimetype="text/xml")


@anonymous.route("/<gameshort>/browse/updated")
def singlegame_browse_updated(gameshort: str) -> str:
    ga = get_game_info(short=gameshort)
    mods = Mod.query.filter(Mod.published, Mod.game_id == ga.id, Mod.versions.any(ModVersion.id != Mod.default_version_id)).order_by(desc(Mod.updated))
    mods, page, total_pages = paginate_query(mods)
    return render_template("browse-list.html", mods=mods, page=page, total_pages=total_pages, ga=ga,
                           url="/browse/updated", name="Recently Updated Mods", rss="/browse/updated.rss")


@anonymous.route("/<gameshort>/browse/updated.rss")
def singlegame_browse_updated_rss(gameshort: str) -> Response:
    site_name = _cfg('site-name')
    if not site_name:
        abort(404)
    ga = get_game_info(short=gameshort)
    mods = get_updated_mods(ga.id, 30)
    return Response(render_template("rss.xml", mods=mods, title="Recently updated on " + site_name, ga=ga,
                                    description="Mods on " +
                                    site_name + " updated recently",
                                    url="/browse/updated"),
                    mimetype="text/xml")


@anonymous.route("/<gameshort>/browse/top")
def singlegame_browse_top(gameshort: str) -> str:
    ga = get_game_info(short=gameshort)
    mods, page, total_pages = get_paginated_mods(ga)
    return render_template("browse-list.html", mods=mods, page=page, total_pages=total_pages, ga=ga,
                           url="/browse/top", name="Popular Mods")


@anonymous.route("/<gameshort>/browse/featured")
def singlegame_browse_featured(gameshort: str) -> str:
    ga = get_game_info(short=gameshort)
    mods = Featured.query.outerjoin(Mod).filter(
        Mod.game_id == ga.id).order_by(desc(Featured.created))
    mods, page, total_pages = paginate_query(mods)
    mods = [f.mod for f in mods]
    return render_template("browse-list.html", mods=mods, page=page, total_pages=total_pages, ga=ga,
                           url="/browse/featured", name="Featured Mods", rss="/browse/featured.rss")


@anonymous.route("/<gameshort>/browse/featured.rss")
def singlegame_browse_featured_rss(gameshort: str) -> Response:
    site_name = _cfg('site-name')
    if not site_name:
        abort(404)
    ga = get_game_info(short=gameshort)
    mods = []
    for fm in get_featured_mods(ga.id, 30):
        # Add each mod but with created set to when it was featured
        fmod = dumb_object(fm.mod)
        fmod['created'] = fm.created.astimezone(timezone.utc)
        mods.append(fmod)
    return Response(render_template("rss.xml", mods=mods, title="Featured mods on " + site_name, ga=ga,
                                    description="Featured mods on " + site_name,
                                    url="/browse/featured"),
                    mimetype="text/xml")


@anonymous.route("/<gameshort>/browse/all")
def singlegame_browse_all(gameshort: str) -> str:
    ga = get_game_info(short=gameshort)
    mods, page, total_pages = get_paginated_mods(ga)
    return render_template("browse-list.html", mods=mods, page=page, total_pages=total_pages, ga=ga,
                           url="/browse/all", name="All Mods")


@anonymous.route("/about")
def about() -> str:
    return render_template("about.html")


@anonymous.route("/markdown")
def markdown_info() -> str:
    return render_template("markdown.html")


@anonymous.route("/privacy")
def privacy() -> str:
    return render_template("privacy.html")


@anonymous.route("/search")
def search() -> str:
    query = request.args.get('query') or ''
    mods, page, total_pages = get_paginated_mods(query=query)
    return render_template("browse-list.html", mods=mods, page=page, total_pages=total_pages, search=True, query=query)


@anonymous.route("/<gameshort>/search")
def singlegame_search(gameshort: str) -> str:
    ga = get_game_info(short=gameshort)
    query = request.args.get('query') or ''
    mods, page, total_pages = get_paginated_mods(ga, query)
    return render_template("browse-list.html", mods=mods, page=page, total_pages=total_pages, search=True, query=query, ga=ga)
