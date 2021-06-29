import json
import math
import mimetypes
import urllib.parse
import os
import re
from datetime import timedelta, datetime
from functools import wraps
from typing import Union, List, Any, Optional, Callable, Tuple, Iterable

import bleach
import werkzeug.wrappers
from bleach_allowlist import bleach_allowlist
from flask import jsonify, redirect, request, Response, abort, session, send_file, make_response
from flask_login import current_user
from markupsafe import Markup
from sqlalchemy import desc
from werkzeug.exceptions import HTTPException
from sqlalchemy.orm import Query

from .config import _cfg
from .custom_json import CustomJSONEncoder
from .database import db, Base
from .objects import Game, Mod, Featured, ModVersion, ReferralEvent, DownloadEvent, FollowEvent
from .search import search_mods

TRUE_STR = ('true', 'yes', 'on')
PARAGRAPH_PATTERN = re.compile('\n\n|\r\n\r\n')

cleaner = bleach.Cleaner(tags=bleach_allowlist.markdown_tags,
                         attributes=bleach_allowlist.markdown_attrs,
                         filters=[bleach.linkifier.LinkifyFilter])


def first_paragraphs(text: str) -> str:
    return '\n\n'.join(PARAGRAPH_PATTERN.split(text)[0:3])


def many_paragraphs(text: str) -> bool:
    return len(PARAGRAPH_PATTERN.split(text)) > 3


def sanitize_text(text: str) -> Markup:
    return Markup(cleaner.clean(text))


def dumb_object(model):  # type: ignore
    if type(model) is list:
        return [dumb_object(x) for x in model]

    result = {}

    for col in model._sa_class_manager.mapper.mapped_table.columns:
        a = getattr(model, col.name)
        if not isinstance(a, Base):
            result[col.name] = a

    return result


def with_session(f: Callable[..., Any]) -> Callable[..., Any]:
    """Automatically commits to the database, and rolls back if the process throws an error."""
    @wraps(f)
    def go(*args: str, **kwargs: int) -> werkzeug.wrappers.Response:
        try:
            ret = f(*args, **kwargs)
            db.commit()
            return ret
        except:
            db.rollback()
            db.close()
            raise

    return go


def loginrequired(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def wrapper(*args: str, **kwargs: int) -> werkzeug.wrappers.Response:
        if not current_user or current_user.confirmation:
            return redirect("/login?return_to=" + urllib.parse.quote_plus(request.url))
        else:
            return f(*args, **kwargs)

    return wrapper


def adminrequired(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def wrapper(*args: str, **kwargs: int) -> werkzeug.wrappers.Response:
        if not current_user or current_user.confirmation:
            return redirect("/login?return_to=" + urllib.parse.quote_plus(request.url))
        else:
            if not current_user.admin:
                abort(403)
            return f(*args, **kwargs)

    return wrapper


def json_response(obj: Any, status: int = None) -> werkzeug.wrappers.Response:
    data = json.dumps(obj, cls=CustomJSONEncoder, separators=(',', ':'))
    return Response(data, status=status, mimetype='application/json')


def json_output(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def wrapper(*args: str, **kwargs: int) -> werkzeug.wrappers.Response:
        result = f(*args, **kwargs)
        if isinstance(result, tuple):
            return json_response(*result)
        if isinstance(result, (dict, list)):
            return json_response(result)
        # This is a fully fleshed out response, return it immediately
        return result

    return wrapper


def cors(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def wrapper(*args: str, **kwargs: int) -> Tuple[str, int]:
        res = f(*args, **kwargs)
        if request.headers.get('x-cors-status', False):
            if isinstance(res, tuple):
                json_text = res[0].data
                code = res[1]
            else:
                json_text = res.data
                code = 200
            o = json.loads(json_text)
            o['x-status'] = code
            return jsonify(o)
        return res

    return wrapper


def paginate_query(query: Query, page_size: int = 30) -> Tuple[List[Mod], int, int]:
    total_pages = math.ceil(query.count() / page_size)
    page = get_page()
    if page > total_pages:
        page = total_pages
    if page < 1:
        page = 1
    return query.offset(page_size * (page - 1)).limit(page_size), page, total_pages


def get_page() -> int:
    try:
        return int(request.args.get('page', ''))
    except (ValueError, TypeError):
        return 1


def get_paginated_mods(ga: Game = None, query: str = '', page_size: int = 30) -> Tuple[Iterable[Mod], int, int]:
    page = get_page()
    mods, total_pages = search_mods(ga.id if ga else None, query, page, page_size)
    return mods, page, total_pages


def get_featured_mods(game_id: Optional[int], limit: int) -> List[Mod]:
    mods = Featured.query.outerjoin(Mod).filter(Mod.published).order_by(desc(Featured.created))
    if game_id:
        mods = mods.filter(Mod.game_id == game_id)
    return mods.limit(limit).all()


def get_top_mods(game_id: Optional[int], limit: int) -> List[Mod]:
    mods = Mod.query.filter(Mod.published).order_by(desc(Mod.score))
    if game_id:
        mods = mods.filter(Mod.game_id == game_id)
    return mods.limit(limit).all()


def get_new_mods(game_id: Optional[int], limit: int) -> List[Mod]:
    mods = Mod.query.filter(Mod.published).order_by(desc(Mod.created))
    if game_id:
        mods = mods.filter(Mod.game_id == game_id)
    return mods.limit(limit).all()


def get_updated_mods(game_id: Optional[int], limit: int) -> List[Mod]:
    mods = Mod.query.filter(Mod.published, Mod.versions.any(ModVersion.id != Mod.default_version_id))\
        .order_by(desc(Mod.updated))
    if game_id:
        mods = mods.filter(Mod.game_id == game_id)
    return mods.limit(limit).all()


def get_referral_events(mod_id: int, limit: Optional[int] = None) -> List[ReferralEvent]:
    events = ReferralEvent.query\
        .filter(ReferralEvent.mod_id == mod_id)\
        .order_by(desc(ReferralEvent.events))
    if limit:
        events = events.limit(limit)
    return events.all()


# Returns all download events for this mod, optionally within a timeframe from now()-timeframe to now()
def get_download_events(mod_id: int, timeframe: Optional[timedelta] = None) -> List[DownloadEvent]:
    events = DownloadEvent.query\
        .filter(DownloadEvent.mod_id == mod_id)\
        .order_by(DownloadEvent.created)
    if timeframe:
        thirty_days_ago = datetime.now() - timeframe
        events = events.filter(DownloadEvent.created > thirty_days_ago)
    return events.all()


# Returns all follow events for this mod, optionally within a timeframe from now()-timeframe to now()
def get_follow_events(mod_id: int, timeframe: Optional[timedelta] = None) -> List[FollowEvent]:
    events = FollowEvent.query\
        .filter(FollowEvent.mod_id == mod_id)\
        .order_by(FollowEvent.created)
    if timeframe:
        thirty_days_ago = datetime.now() - timeframe
        events = events.filter(FollowEvent.created > thirty_days_ago)
    return events.all()


def get_games() -> List[Game]:
    return Game.query.filter(Game.active).order_by(desc(Game.created)).all()


def get_game_info(**query: str) -> Game:
    if not query:
        query['short'] = 'kerbal-space-program'
    ga = Game.query.filter_by(**query).first()
    if not ga:
        abort(404)
    # TODO get rid of this call so we can cache get_game_info
    set_game_info(ga)
    return ga


def set_game_info(ga: Game) -> None:
    session['game'] = ga.id
    session['gamename'] = ga.name
    session['gameshort'] = ga.short
    session['gameid'] = ga.id


def check_mod_editable(mod: Mod, abort_response: Optional[Union[int, werkzeug.wrappers.Response]] = 403) -> bool:
    if current_user:
        if current_user.admin:
            return True
        if current_user.id == mod.user_id:
            return True
        if any(u.accepted and u.user == current_user for u in mod.shared_authors):
            return True
    if abort_response is not None:
        abort(abort_response)
    return False


def jsonify_exception(e: Exception) -> werkzeug.wrappers.Response:
    if isinstance(e, HTTPException):
        # Start with the correct headers and status code from the error
        response = e.get_response()
        # Replace the body with JSON
        response.mimetype = 'application/json'
        response.data = json.dumps({
            "error": True,
            "reason": f'{e.code} {e.name}: {e.description}',
            "code": e.code,
        }, cls=CustomJSONEncoder, separators=(',', ':'))
        return response
    else:
        # We deliberately loose the original message here because it can contain confidential data.
        return json_response({
            "error": True,
            "code": 500,
            "reason": f'500 Internal Server Error: Clearly you\'ve broken something. '
                      f'Maybe if you refresh no one will notice.',
        }, 500)


# Returns a file using X-Sendfile / X-Accel-Redirect if configured, or serving it directly.
def sendfile(path: str, attachment: bool = True) -> werkzeug.wrappers.Response:
    storage = _cfg('storage')
    if not storage:
        abort(404)

    response = None
    if _cfg("use-x-accel") == 'nginx':
        response = make_response("")
        # mimetypes guesses the mimetype from file extension, it does not access the disk
        response.headers['Content-Type'] = mimetypes.guess_type(path)[0]
        if attachment:
            response.headers['Content-Disposition'] = 'attachment; filename=' + os.path.basename(path)
        else:
            response.headers['Content-Disposition'] = 'inline'
        response.headers['X-Accel-Redirect'] = '/internal/' + path
    if _cfg("use-x-accel") == 'apache':
        response = make_response("")
        response.headers['Content-Type'] = mimetypes.guess_type(path)[0]
        if attachment:
            response.headers['Content-Disposition'] = 'attachment; filename=' + os.path.basename(path)
        else:
            response.headers['Content-Disposition'] = 'inline'
        response.headers['X-Sendfile'] = os.path.join(storage, path)
    if response is None:
        download_path = os.path.join(storage, path)
        if not os.path.isfile(download_path):
            abort(404)
        response = make_response(send_file(download_path, as_attachment=attachment))
    return response
