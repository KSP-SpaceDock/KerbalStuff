import math
import os
import time
import zipfile
from datetime import datetime, timezone
from functools import wraps
from typing import Dict, Any, Callable, Optional, Tuple, Iterable, List, Union
import json

import bcrypt
from flask import Blueprint, url_for, current_app, request, abort
from flask_login import login_user, current_user
from sqlalchemy import desc, asc
from werkzeug.utils import secure_filename
import werkzeug
from werkzeug.exceptions import HTTPException

from .accounts import check_password_criteria
from ..ckan import send_to_ckan, notify_ckan
from ..common import json_output, paginate_mods, with_session, get_mods, json_response, \
    check_mod_editable, set_game_info, TRUE_STR, get_page
from ..config import _cfg, _cfgi, site_logger
from ..database import db
from ..email import send_update_notification, send_grant_notice, send_password_changed
from ..objects import GameVersion, Game, Publisher, Mod, Featured, User, ModVersion, SharedAuthor, \
    ModList
from ..search import search_mods, search_users, typeahead_mods, get_mod_score
from ..custom_json import CustomJSONEncoder

api = Blueprint('api', __name__)

default_description = """This is your mod listing! You can edit it as much as you like before you make it public.

To edit **this** text, you can click on the "**Edit this Mod**" button up there.

By the way, you have a lot of flexibility here. You can embed YouTube videos or screenshots. Be creative.

You can check out the SpaceDock [markdown documentation](/markdown) for tips.

Thanks for hosting your mod on SpaceDock!"""


def handle_api_exception(e: Exception) -> werkzeug.wrappers.Response:
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
        return json_response({
            "error": True,
            "code": 500,
            "reason": f'500 Internal Server Error: {str(e)}',
        }, 500)


# some helper functions to keep things consistent
def user_info(user: User) -> Dict[str, Any]:
    return {
        "username": user.username,
        "description": user.description,
        "forumUsername": user.forumUsername,
        "ircNick": user.ircNick,
        "twitterUsername": user.twitterUsername,
        "redditUsername": user.redditUsername
    }


def mod_info(mod: Mod) -> Dict[str, Any]:
    return {
        "name": mod.name,
        "id": mod.id,
        "game": mod.game.name,
        "game_id": mod.game_id,
        "short_description": mod.short_description,
        "downloads": mod.download_count,
        "followers": mod.follower_count,
        "author": mod.user.username,
        "default_version_id": mod.default_version.id,
        "shared_authors": list(),
        "background": mod.background,
        "bg_offset_y": mod.bgOffsetY,
        "license": mod.license,
        "website": mod.external_link,
        "donations": mod.donation_link,
        "source_code": mod.source_link,
        "url": url_for("mods.mod", mod_id=mod.id, mod_name=mod.name)
    }


def version_info(mod: Mod, version: ModVersion) -> Dict[str, Any]:
    return {
        "friendly_version": version.friendly_version,
        "game_version": version.gameversion.friendly_version,
        "id": version.id,
        "created": version.created,
        "download_path": url_for('mods.download', mod_id=mod.id,
                                 mod_name=mod.name,
                                 version=version.friendly_version),
        "changelog": version.changelog,
        "downloads": version.download_count,
    }


def game_version_info(version: ModVersion) -> Dict[str, str]:
    return {
        "id": version.id,
        "friendly_version": version.friendly_version
    }


def game_info(game: Game) -> Dict[str, str]:
    return {
        "id": game.id,
        "name": game.name,
        "publisher_id": game.publisher_id,
        "short_description": game.short_description,
        "description": game.description,
        "created": game.created,
        "background": game.background,
        "bg_offset_x": game.bgOffsetX,
        "bg_offset_y": game.bgOffsetY,
        "link": game.link,
        "short": game.short
    }


def publisher_info(publisher: Publisher) -> Dict[str, str]:
    return {
        "id": publisher.id,
        "name": publisher.name,
        "short_description": publisher.short_description,
        "description": publisher.description,
        "created": publisher.created,
        "background": publisher.background,
        "bg_offset_x": publisher.bgOffsetX,
        "bg_offset_y": publisher.bgOffsetY,
        "link": publisher.link
    }


def user_required(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(*args: str, **kwargs: int) -> str:
        if not current_user:
            abort(json_response({'error': True, 'reason': 'You are not logged in.'}, 401))
        return func(*args, **kwargs)

    return wrapper


def _get_mod(mod_id: int) -> Mod:
    mod = Mod.query.get(mod_id)
    if not mod:
        abort(json_response({'error': True, 'reason': 'Mod not found.'}, 404))
    return mod


def _check_mod_published(mod: Mod) -> None:
    if not mod.published:
        abort(json_response({'error': True, 'reason': 'Mod not published.'}, 401))


def _check_mod_editable(mod: Mod) -> None:
    check_mod_editable(mod, json_response({'error': True, 'reason': 'Not enough rights.'}, 401))


def _get_mod_pending_author(mod: Mod) -> User:
    author = next((a for a in mod.shared_authors if a.user == current_user), None)
    if not author:
        abort(
            json_response({'error': True, 'reason': 'You do not have a pending authorship invite.'},
                          200))
    if author.accepted:
        abort(
            json_response({'error': True, 'reason': 'You do not have a pending authorship invite.'},
                          200))
    return author


def _update_image(old_path: str, base_name: str, base_path: str) -> Optional[str]:
    f = request.files.get('image')
    if not f:
        return None
    storage = _cfg('storage')
    if not storage:
        return None
    file_type = os.path.splitext(os.path.basename(f.filename))[1].lower()
    if file_type not in ('.png', '.jpg', '.jpeg'):
        abort(json_response({'error': True, 'reason': 'This file type is not acceptable.'}, 400))
    filename = base_name + file_type
    full_path = os.path.join(storage, base_path)
    if not os.path.exists(full_path):
        os.makedirs(full_path)
    try:
        os.remove(os.path.join(storage, old_path))
    except:
        pass  # who cares
    f.save(os.path.join(full_path, filename))
    return os.path.join(base_path, filename)


def _get_modversion_paths(mod_name: str, friendly_version: str) -> Tuple[str, str]:
    mod_name_sec = secure_filename(mod_name)
    storage_base = os.path.join(f'{secure_filename(current_user.username)}_{current_user.id!s}',
                                mod_name_sec)
    storage = _cfg('storage')
    if not storage:
        return ('', '')
    storage_path = os.path.join(storage, storage_base)
    filename = f'{mod_name_sec}-{friendly_version}.zip'
    if not os.path.exists(storage_path):
        os.makedirs(storage_path)
    full_path = os.path.join(storage_path, filename)
    # Return tuple of (full path, relative path)
    return (full_path, os.path.join(storage_base, filename))


def serialize_mod_list(mods: Iterable[Mod]) -> Iterable[Dict[str, Any]]:
    results = list()
    for m in mods:
        a = mod_info(m)
        a['versions'] = [version_info(m, v) for v in m.versions]
        results.append(a)
    return results


@api.route("/api/kspversions")
@json_output
def kspversions_list() -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], int]]:
    game = Game.query.filter(Game.ckan_enabled == True).first()
    if game:
        return gameversions_list(str(game.id))
    else:
        return list(), 404


@api.route("/api/<gameid>/versions")
@json_output
def gameversions_list(gameid: str) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], int]]:
    game = Game.query.get(gameid)

    results: List[Dict[str, Any]] = list()
    if not game or not game.active:
        return results, 404

    for v in GameVersion.query \
            .filter(GameVersion.game_id == gameid) \
            .order_by(desc(GameVersion.id)):
        results.append(game_version_info(v))

    return results


@api.route("/api/games")
@json_output
def games_list() -> List[Dict[str, Any]]:
    results = list()
    for v in Game.query.filter(Game.active == True).order_by(desc(Game.name)):
        results.append(game_info(v))
    return results


@api.route("/api/publishers")
@json_output
def publishers_list() -> List[Dict[str, Any]]:
    results = list()
    for v in Publisher.query.order_by(desc(Publisher.id)):
        results.append(publisher_info(v))
    return results


@api.route("/api/typeahead/mod")
@json_output
def typeahead_mod() -> Iterable[Dict[str, Any]]:
    game_id = request.args.get('game_id', '')
    query = request.args.get('query', '')
    return serialize_mod_list(typeahead_mods(game_id, query))


@api.route("/api/search/mod")
@json_output
def search_mod() -> Iterable[Dict[str, Any]]:
    query = request.args.get('query')
    query = '' if not query else query
    page = get_page()
    return serialize_mod_list(search_mods(None, query, page, 30)[0])


@api.route("/api/search/user")
@json_output
def search_user() -> Iterable[Dict[str, Any]]:
    query = request.args.get('query')
    page = request.args.get('page')
    query = '' if not query else query
    page = 0 if not page or not page.isdigit() else int(page)
    results = list()
    for u in search_users(query, page):
        a = user_info(u)
        mods = Mod.query.filter(Mod.user == u, Mod.published == True).order_by(Mod.created)
        a['mods'] = [mod_info(m) for m in mods]
        results.append(a)
    return results


@api.route("/api/browse")
@json_output
def browse() -> Dict[str, Any]:
    # set count per page
    per_page = request.args.get('count', 30)
    try:
        per_page = min(max(int(per_page), 1), 500)
    except (ValueError, TypeError):
        per_page = 30
    mods = Mod.query.filter(Mod.published)
    # detect total pages
    count = mods.count()
    total_pages = max(math.ceil(count / per_page), 1)
    # order by field
    orderby = request.args.get('orderby')
    if orderby == "name":
        orderby = Mod.name
    elif orderby == "updated":
        orderby = Mod.updated
    else:
        orderby = Mod.created
    # order direction
    order = request.args.get('order')
    if order == "desc":
        mods.order_by(desc(orderby))
    else:
        mods.order_by(asc(orderby))
    # current page
    page = request.args.get('page', 1)
    try:
        page = max(int(page), 1)
    except (ValueError, TypeError):
        page = 1
    mods = mods.offset(per_page * (page - 1)).limit(per_page)
    # generate result
    return {
        "total": count,
        "count": per_page,
        "pages": total_pages,
        "page": page,
        "result": serialize_mod_list(mods)
    }


@api.route("/api/browse/new")
@json_output
def browse_new() -> Iterable[Dict[str, Any]]:
    mods = Mod.query.filter(Mod.published).order_by(desc(Mod.created))
    mods, page, total_pages = paginate_mods(mods)
    return serialize_mod_list(mods)


@api.route("/api/browse/top")
@json_output
def browse_top() -> Iterable[Dict[str, Any]]:
    mods, *_ = get_mods()
    return serialize_mod_list(mods)


@api.route("/api/browse/featured")
@json_output
def browse_featured() -> Iterable[Dict[str, Any]]:
    mods = Featured.query.order_by(desc(Featured.created))
    mods, page, total_pages = paginate_mods(mods)
    return serialize_mod_list((f.mod for f in mods))


@api.route("/api/login", methods=['POST'])
@json_output
def login() -> Union[Dict[str, Any], Tuple[Dict[str, Any], int]]:
    username = request.form.get('username')
    password = request.form.get('password')
    if not username or not password:
        return {'error': True, 'reason': 'Missing username or password'}, 400
    user = User.query.filter(User.username.ilike(username)).first()
    if not user:
        return {'error': True, 'reason': 'Username or password is incorrect'}, 400
    if not bcrypt.hashpw(password.encode('utf-8'),
                         user.password.encode('utf-8')) == user.password.encode('utf-8'):
        return {'error': True, 'reason': 'Username or password is incorrect'}, 400
    if user.confirmation and user.confirmation is not None:
        return {'error': True, 'reason': 'User is not confirmed'}, 400
    login_user(user)
    return {'error': False}


@api.route("/api/mod/<int:mod_id>")
@json_output
def mod_info_api(mod_id: int) -> Union[Dict[str, Any], Tuple[Dict[str, Any], int]]:
    mod = Mod.query.get(mod_id)
    if not mod:
        return {'error': True, 'reason': 'Mod not found.'}, 404
    if not mod.published:
        if not current_user:
            return {'error': True, 'reason': 'Mod not published. Authorization needed.'}, 401
        if current_user.id != mod.user_id:
            return {'error': True, 'reason': 'Mod not published. Only owner can see it.'}, 401
    info = mod_info(mod)
    info["versions"] = list()
    for author in mod.shared_authors:
        if author.accepted:
            info["shared_authors"].append(user_info(author.user))
    for v in mod.versions:
        info["versions"].append(version_info(mod, v))
    info["description"] = mod.description
    info["description_html"] = str(current_app.jinja_env.filters['markdown'](mod.description))
    return info


@api.route("/api/mod/<int:mod_id>/<version>")
@json_output
def mod_version(mod_id: int, version: str) -> Union[Dict[str, Any], Tuple[Dict[str, Any], int]]:
    mod = _get_mod(mod_id)
    _check_mod_published(mod)
    if version == "latest" or version == "latest_version":
        v = mod.default_version
    elif version.isdigit():
        v = ModVersion.query.filter(ModVersion.mod == mod,
                                    ModVersion.id == int(version)).first()
    else:
        return {'error': True, 'reason': 'Invalid version.'}, 400
    if not v:
        return {'error': True, 'reason': 'Version not found.'}, 404
    info = version_info(mod, v)
    return info


@api.route("/api/user/<username>")
@json_output
def user_info_api(username: str) -> Union[Dict[str, Any], Tuple[Dict[str, Any], int]]:
    user = User.query.filter(User.username == username).first()
    if not user:
        return {'error': True, 'reason': 'User not found.'}, 404
    if not user.public:
        return {'error': True, 'reason': 'User not public.'}, 401
    mods = Mod.query.filter(Mod.user == user, Mod.published == True).order_by(Mod.created)
    info = user_info(user)
    info['mods'] = [mod_info(m) for m in mods]
    return info


@api.route('/api/user/<username>/change-password', methods=['POST'])
@with_session
@user_required
@json_output
def change_password(username: str) -> Union[Dict[str, Any], Tuple[Union[str, Any], int]]:
    if current_user.username != username:
        return {'error': True, 'reason': 'You are not authorized to change this user\'s password.'}, 403

    old_password = request.form.get('old-password', '')
    new_password = request.form.get('new-password', '')
    new_password_confirm = request.form.get('new-password-confirm', '')

    if not bcrypt.hashpw(old_password.encode('utf-8'), current_user.password.encode('utf-8')) == current_user.password.encode('utf-8'):
        return {'error': True, 'reason': 'The old password you entered doesn\'t match your current account password.'}

    pw_valid, pw_message = check_password_criteria(new_password, new_password_confirm)
    if pw_valid:
        current_user.set_password(new_password)
        send_password_changed(current_user)
        return {'error': False, 'reason': pw_message}

    return {'error': True, 'reason': pw_message}


@api.route('/api/mod/<int:mod_id>/update-bg', methods=['POST'])
@with_session
@json_output
@user_required
def update_mod_background(mod_id: int) -> Dict[str, Any]:
    mod = _get_mod(mod_id)
    _check_mod_editable(mod)
    seq_mod_name = secure_filename(mod.name)
    base_name = f'{seq_mod_name}-{time.time()!s}'
    base_path = os.path.join(f'{secure_filename(mod.user.username)}_{mod.user.id!s}', seq_mod_name)
    new_path = _update_image(mod.background, base_name, base_path)
    if new_path:
        mod.background = new_path
        notify_ckan(mod, 'update-background')
        return {'path': '/content/' + new_path}
    return {'path': None}


@api.route('/api/user/<username>/update-bg', methods=['POST'])
@with_session
@json_output
@user_required
def update_user_background(username: str) -> Union[Dict[str, Any], Tuple[Dict[str, Any], int]]:
    if not current_user.admin and current_user.username != username:
        return {'error': True, 'reason': 'You are not authorized to edit this user\'s background'}, 403
    user = User.query.filter(User.username == username).first()
    base_name = secure_filename(user.username)
    base_path = f'{base_name}-{time.time()!s}_{user.id!s}'
    new_path = _update_image(user.backgroundMedia, base_name, base_path)
    if new_path:
        user.backgroundMedia = new_path
        return {'path': '/content/' + new_path}
    return {'path': None}


@api.route('/api/mod/<int:mod_id>/grant', methods=['POST'])
@with_session
@json_output
def grant_mod(mod_id: int) -> Union[Dict[str, Any], Tuple[Dict[str, Any], int]]:
    mod = _get_mod(mod_id)
    _check_mod_editable(mod)
    new_user = None
    username = request.form.get('user')
    if username:
        new_user = User.query.filter(User.username.ilike(username)).first()
    if new_user is None:
        return {'error': True, 'reason': 'The specified user does not exist.'}, 400
    if mod.user == new_user:
        return {'error': True, 'reason': 'This user has already been added.'}, 400
    if any(m.user == new_user for m in mod.shared_authors):
        return {'error': True, 'reason': 'This user has already been added.'}, 400
    if not new_user.public:
        return {'error': True, 'reason': 'This user has not made their profile public.'}, 400
    author = SharedAuthor()
    author.mod = mod
    author.user = new_user
    mod.shared_authors.append(author)
    db.add(author)
    db.commit()
    send_grant_notice(mod, new_user)
    return {'error': False}, 200


@api.route('/api/mod/<mod_id>/accept_grant', methods=['POST'])
@with_session
@json_output
@user_required
def accept_grant_mod(mod_id: int) -> Tuple[Dict[str, Any], int]:
    mod = _get_mod(mod_id)
    author = _get_mod_pending_author(mod)
    author.accepted = True
    notify_ckan(mod, 'co-author-added')
    return {'error': False}, 200


@api.route('/api/mod/<mod_id>/reject_grant', methods=['POST'])
@with_session
@json_output
@user_required
def reject_grant_mod(mod_id: int) -> Tuple[Dict[str, Any], int]:
    mod = _get_mod(mod_id)
    author = _get_mod_pending_author(mod)
    mod.shared_authors = [a for a in mod.shared_authors if a.user != current_user]
    db.delete(author)
    return {'error': False}, 200


@api.route('/api/mod/<mod_id>/revoke', methods=['POST'])
@with_session
@json_output
@user_required
def revoke_mod(mod_id: int) -> Tuple[Dict[str, Any], int]:
    mod = _get_mod(mod_id)
    _check_mod_editable(mod)
    new_user = None
    username = request.form.get('user')
    if username:
        new_user = User.query.filter(User.username.ilike(username)).first()
    if new_user is None:
        return {'error': True, 'reason': 'The specified user does not exist.'}, 404
    if mod.user == new_user:
        return {'error': True, 'reason': 'You can\'t remove yourself.'}, 400
    if not any(m.user == new_user for m in mod.shared_authors):
        return {'error': True, 'reason': 'This user is not an author.'}, 400
    author = [a for a in mod.shared_authors if a.user == new_user][0]
    mod.shared_authors = [a for a in mod.shared_authors if a.user != current_user]
    db.delete(author)
    notify_ckan(mod, 'co-author-removed')
    return {'error': False}, 200


@api.route('/api/mod/<int:mod_id>/set-default/<int:vid>', methods=['POST'])
@with_session
@json_output
def set_default_version(mod_id: int, vid: int) -> Tuple[Dict[str, Any], int]:
    mod = _get_mod(mod_id)
    _check_mod_editable(mod)
    if not any([v.id == vid for v in mod.versions]):
        return {'error': True, 'reason': 'This mod does not have the specified version.'}, 404
    mod.default_version_id = vid
    notify_ckan(mod, 'default-version-set')
    return {'error': False}, 200


@api.route('/api/pack/create', methods=['POST'])
@json_output
@with_session
@user_required
def create_list() -> Union[Dict[str, Any], Tuple[Dict[str, Any], int]]:
    if not current_user.public:
        return {'error': True, 'reason': 'Only users with public profiles may create mod packs.'}, 403
    name = request.form.get('name')
    if not name:
        return {'error': True, 'reason': 'All fields are required.'}, 400
    game = request.form.get('game')
    if not game:
        return {'error': True, 'reason': 'Please select a game.'}, 400
    if len(name) > 100:
        return {'error': True, 'reason': 'Fields exceed maximum permissible length.'}, 400
    mod_list = ModList(name=name,
                       user=current_user,
                       game_id=game)
    db.add(mod_list)
    db.commit()
    return {'url': url_for("lists.edit_list", list_id=mod_list.id, list_name=mod_list.name)}


@api.route('/api/mod/create', methods=['POST'])
@json_output
@user_required
def create_mod() -> Tuple[Dict[str, Any], int]:
    if not current_user.public:
        return {'error': True, 'reason': 'Only users with public profiles may create mods.'}, 403
    mod_name = request.form.get('name')
    short_description = request.form.get('short-description')
    mod_friendly_version = secure_filename(request.form.get('version', ''))
    # 'game' is deprecated, but kept for compatibility
    game_id = request.form.get('game-id') or request.form.get('game')
    game_short = request.form.get('game-short-name')
    game_friendly_version = request.form.get('game-version')
    mod_licence = request.form.get('license')
    # Validate
    if not mod_name \
            or not short_description \
            or not mod_friendly_version \
            or not (game_id or game_short) \
            or not game_friendly_version \
            or not mod_licence:
        return {'error': True, 'reason': 'All fields are required.'}, 400
    # Validation, continued
    if len(mod_name) > 100 \
            or len(short_description) > 1000 \
            or len(mod_licence) > 128:
        return {'error': True, 'reason': 'Fields exceed maximum permissible length.'}, 400
    game = None
    if game_id:
        game = Game.query.get(game_id)
    elif game_short:
        game = Game.query.filter(Game.short == game_short).first()
    if not game or not game.active:
        return {'error': True, 'reason': 'Game does not exist.'}, 400
    game_version = GameVersion.query \
        .filter(GameVersion.game_id == game.id) \
        .filter(GameVersion.friendly_version == game_friendly_version) \
        .first()
    if not game_version:
        return {'error': True, 'reason': 'Game version does not exist.'}, 400

    full_path, relative_path = _get_modversion_paths(mod_name, mod_friendly_version)
    how_many_chunks = int(request.form.get('dztotalchunkcount', 1))
    which_chunk = int(request.form.get('dzchunkindex', 0))
    if which_chunk == 0:
        if os.path.isfile(full_path):
            os.remove(full_path)

    with open(full_path, 'ab') as f:
        f.seek(int(request.form.get('dzchunkbyteoffset', 0)))
        f.write(request.files['zipball'].stream.read())

    if which_chunk + 1 == how_many_chunks:
        # Last chunk, create the records
        if not zipfile.is_zipfile(full_path):
            os.remove(full_path)
            return {'error': True, 'reason': f'{full_path} is not a valid zip file.'}, 400

        version = ModVersion(friendly_version=mod_friendly_version,
                             gameversion_id=game_version.id,
                             download_path=relative_path)
        # create the mod
        mod = Mod(user=current_user,
                  name=mod_name,
                  short_description=short_description,
                  description=default_description,
                  license=mod_licence,
                  ckan=(game.ckan_enabled and request.form.get('ckan', '').lower() in TRUE_STR),
                  game=game,
                  default_version=version)
        version.mod = mod
        # Save database entry
        db.add(mod)
        db.commit()
        mod.score = get_mod_score(mod)
        db.commit()
        set_game_info(game)
        send_to_ckan(mod)
        return {
            'url': url_for("mods.mod", mod_id=mod.id, mod_name=mod.name) + '?new=true',
            "id": mod.id,
            "name": mod.name
        }, 202

    return { }, 202

# This is called by dropzone
@api.route('/api/mod/<int:mod_id>/update', methods=['POST'])
@with_session
@json_output
@user_required
def update_mod(mod_id: int) -> Tuple[Dict[str, Any], int]:
    mod = _get_mod(mod_id)
    _check_mod_editable(mod)
    friendly_version = secure_filename(request.form.get('version', ''))
    game_friendly_version = request.form.get('game-version')
    if not friendly_version or not game_friendly_version:
        return {'error': True, 'reason': 'All fields are required.'}, 400
    game_version = GameVersion.query \
        .filter(GameVersion.game_id == mod.game_id) \
        .filter(GameVersion.friendly_version == game_friendly_version) \
        .first()
    if not game_version:
        return {'error': True, 'reason': 'Game version does not exist.'}, 400
    for v in mod.versions:
        if v.friendly_version == friendly_version:
            return {
                'error': True,
                'reason': 'We already have this version. '
                          'Did you mistype the version number?'
            }, 400

    full_path, relative_path = _get_modversion_paths(mod.name, friendly_version)
    how_many_chunks = int(request.form.get('dztotalchunkcount', 1))
    which_chunk = int(request.form.get('dzchunkindex', 0))
    if which_chunk == 0:
        if os.path.isfile(full_path):
            os.remove(full_path)

    with open(full_path, 'ab') as f:
        f.seek(int(request.form.get('dzchunkbyteoffset', 0)))
        f.write(request.files['zipball'].stream.read())

    if which_chunk + 1 == how_many_chunks:
        # Last chunk, make records
        if not zipfile.is_zipfile(full_path):
            os.remove(full_path)
            return {'error': True, 'reason': f'{full_path} {which_chunk}/{how_many_chunks} is not a valid zip file.'}, 400

        changelog = request.form.get('changelog')
        version = ModVersion(friendly_version=friendly_version,
                             gameversion_id=game_version.id,
                             download_path=relative_path,
                             changelog=changelog)
        # Assign a sort index
        if mod.versions:
            version.sort_index = max(v.sort_index for v in mod.versions) + 1
        version.mod = mod
        mod.default_version = version
        mod.updated = datetime.now()
        db.commit()
        mod.score = get_mod_score(mod)
        db.commit()
        notify = request.form.get('notify-followers', '').lower()
        if notify in TRUE_STR:
            send_update_notification(mod, version, current_user)
        notify_ckan(mod, 'update')
        return {
            'url': url_for("mods.mod", mod_id=mod.id, mod_name=mod.name),
            'id': version.id
        }, 202

    return { }, 202
