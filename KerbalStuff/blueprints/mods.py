import logging
import os
import random
import re
import sys
from datetime import datetime, timedelta
from shutil import rmtree
from socket import socket
from typing import Any, Dict, Tuple, Optional, Union, List

import threading
import dns.resolver
import requests
import werkzeug.wrappers

from flask import Blueprint, render_template, send_file, make_response, url_for, abort, session, \
    redirect, request
from flask_login import current_user
from sqlalchemy import desc
from urllib.parse import urlparse
from urllib3.util import connection
from werkzeug.utils import secure_filename

from .api import default_description
from ..ckan import send_to_ckan, notify_ckan
from ..common import get_game_info, set_game_info, with_session, dumb_object, loginrequired, \
    json_output, adminrequired, check_mod_editable, TRUE_STR, \
    get_referral_events, get_download_events, get_follow_events, get_games
from ..config import _cfg
from ..database import db
from ..email import send_autoupdate_notification, send_mod_locked
from ..objects import Mod, ModVersion, DownloadEvent, FollowEvent, ReferralEvent, \
    Featured, Media, GameVersion, Game
from ..search import get_mod_score

mods = Blueprint('mods', __name__, template_folder='../../templates/mods')

SOURCE_REPOSITORY_URL_PATTERN = re.compile(
    r'^https://git(hub|lab).com/(?P<repo_short>[^/]+/[^/]+)/?'
)


def _get_mod_game_info(mod_id: int) -> Tuple[Mod, Game]:
    mod = Mod.query.get(mod_id)
    if not mod:
        abort(404)
    game = mod.game
    if not game:
        get_game_info()
        abort(404)
    set_game_info(game)
    return mod, game


def _restore_game_info() -> Optional[Game]:
    game_id = session.get('gameid')

    if game_id:
        game = Game.query.filter(Game.active == True, Game.id == game_id).one()
        # Make sure it's fully set in the session cookie.
        set_game_info(game)
        return game

    return None


@mods.route("/random")
def random_mod() -> werkzeug.wrappers.Response:
    game_id = session.get('gameid')
    query = Mod.query.with_entities(Mod.id, Mod.name)\
        .filter(Mod.published == True)\
        .order_by(Mod.created)
    if game_id:
        query = query.filter(Mod.game_id == game_id)
    how_many = query.count()
    if how_many < 1:
        abort(404)
    which = random.randint(0, how_many - 1)
    mod_id, mod_name = query.offset(which).first()
    return redirect(url_for("mods.mod", mod_id=mod_id, mod_name=mod_name))


@mods.route("/mod/<int:mod_id>/<path:mod_name>/update")
def update(mod_id: int, mod_name: str) -> str:
    mod = Mod.query.filter(Mod.id == mod_id).one()
    if not mod:
        abort(404)
    check_mod_editable(mod)
    game_versions = GameVersion.query.filter(
        GameVersion.game_id == mod.game_id).order_by(desc(GameVersion.id)).all()
    return render_template("update.html", ga=mod.game, mod=mod, game_versions=game_versions)


@mods.route("/mod/<int:mod_id>.rss", defaults={'mod_name': None})
@mods.route("/mod/<int:mod_id>/<path:mod_name>.rss")
def mod_rss(mod_id: int, mod_name: str) -> str:
    mod, _ = _get_mod_game_info(mod_id)
    return render_template("rss-mod.xml", mod=mod)


@mods.route("/mod/<int:mod_id>", defaults={'mod_name': None})
@mods.route("/mod/<int:mod_id>/<path:mod_name>")
@with_session
def mod(mod_id: int, mod_name: str) -> Union[str, werkzeug.wrappers.Response]:
    protocol = _cfg("protocol")
    domain = _cfg("domain")
    if not protocol or not domain:
        abort(404)
    mod, ga = _get_mod_game_info(mod_id)
    editable = False
    if current_user:
        if current_user.id == mod.user_id:
            if request.args.get('new') is not None:
                return redirect(url_for("mods.edit_mod", mod_id=mod.id, mod_name=mod.name) + '?new=true')
            else:
                editable = True
        elif current_user.admin:
            editable = True
    if not mod.published and not editable:
        abort(403, 'Unfortunately we couldn\'t display the requested mod. Maybe it\'s not public yet?')
    latest = mod.default_version
    referral = request.referrer
    if referral:
        host = urlparse(referral).hostname
        event = ReferralEvent.query\
            .filter(ReferralEvent.mod_id == mod.id, ReferralEvent.host == host)\
            .first()
        if not event:
            event = ReferralEvent()
            event.mod = mod
            event.events = 1
            event.host = host
            db.add(event)
            db.flush()
            db.commit()
            mod.referrals.append(event)
        else:
            event.events += 1
    referrals = [{'host': ref.host, 'count': ref.events} for ref in get_referral_events(mod.id, 10)]
    download_stats = [dumb_object(d) for d in get_download_events(mod.id, timedelta(days=30))]
    downloads_per_version = [(ver.id, ver.friendly_version, ver.download_count)
                             for ver
                             in sorted(mod.versions, key=lambda ver: ver.id)]
    follower_stats = [dumb_object(f) for f in get_follow_events(mod.id, timedelta(days=30))]

    json_versions = list()
    size_versions = dict()
    storage = _cfg('storage')
    if storage:
        for v in mod.versions:
            json_versions.append({'name': v.friendly_version, 'id': v.id})
            size_versions[v.id] = v.format_size(storage)
    if request.args.get('noedit') is not None:
        editable = False
    forum_thread = False
    if mod.external_link is not None:
        try:
            u = urlparse(mod.external_link)
            if u.netloc == 'forum.kerbalspaceprogram.com':
                forum_thread = True
        except Exception as e:
            logging.debug(e)
            pass
    repo_short = None
    if mod.source_link is not None:
        match = SOURCE_REPOSITORY_URL_PATTERN.match(mod.source_link)
        repo_short = match.group('repo_short') if match else None
    total_authors = 1
    pending_invite = False
    owner = editable
    for a in mod.shared_authors:
        if a.accepted:
            total_authors += 1
        if current_user:
            if current_user.id == a.user_id and not a.accepted:
                pending_invite = True
            if current_user.id == a.user_id and a.accepted:
                editable = True
    latest_game_version = GameVersion.query.filter(
        GameVersion.game_id == mod.game_id).order_by(desc(GameVersion.id)).first()
    outdated = False
    if latest:
        outdated = latest.gameversion.id != latest_game_version.id
    return render_template("mod.html",
                           **{
                               'mod': mod,
                               'latest': latest,
                               'featured': Featured.query.filter(Featured.mod_id == mod.id).count() > 0,
                               'editable': editable,
                               'owner': owner,
                               'pending_invite': pending_invite,
                               'download_stats': download_stats,
                               'downloads_per_version': downloads_per_version,
                               'follower_stats': follower_stats,
                               'referrals': referrals,
                               'json_versions': json_versions,
                               'thirty_days_ago': datetime.now() - timedelta(days=30),
                               'latest_game_version': latest_game_version,
                               'outdated': outdated,
                               'forum_thread': forum_thread,
                               'repo_short': repo_short,
                               'stupid_user': request.args.get('stupid_user') is not None and current_user == mod.user,
                               'total_authors': total_authors,
                               "site_name": _cfg('site-name'),
                               'ga': ga,
                               'size_versions': size_versions
                           })


@mods.route("/mod/<int:mod_id>/<path:mod_name>/edit", methods=['GET', 'POST'])
@with_session
@loginrequired
def edit_mod(mod_id: int, mod_name: str) -> Union[str, werkzeug.wrappers.Response]:
    mod, game = _get_mod_game_info(mod_id)
    check_mod_editable(mod)
    if request.method == 'GET':
        original = current_user == mod.user
        return render_template("edit_mod.html", mod=mod, original=original,
                               new=request.args.get('new') is not None and original)
    else:
        name = request.form.get('name', '')
        short_description = request.form.get('short-description', '')
        license = request.form.get('license', '')
        donation_link = request.form.get('donation-link')
        external_link = request.form.get('external-link')
        source_link = request.form.get('source-link')
        description = request.form.get('description')
        ckan = request.form.get('ckan')
        background = request.form.get('background')
        bgOffsetY = request.form.get('bg-offset-y', 0)
        if not name or len(name) > 100 \
            or not short_description or len(short_description) > 1000 \
            or not license or len(license) > 128:
            abort(400)
        mod.name = name
        mod.license = license
        mod.donation_link = donation_link
        mod.external_link = external_link
        mod.source_link = source_link
        if not isinstance(short_description, str):
            short_description = str(short_description)
        mod.short_description = short_description.replace('\r\n', ' ').replace('\n', ' ')
        if not isinstance(description, str):
            description = str(description)
        mod.description = description.replace('\r\n', '\n')
        mod.score = get_mod_score(mod)
        if not mod.license:
            return render_template("edit_mod.html", mod=mod, error="All mods must have a license.")
        if mod.description == default_description:
            return render_template("edit_mod.html", mod=mod, stupid_user=True)
        newly_published = False
        if request.form.get('publish', None):
            if not mod.published:
                newly_published = True
                mod.published = True
        if ckan is None:
            ckan = False
        else:
            ckan = (ckan.lower() in TRUE_STR)

        if not ckan and mod.ckan:
            if not mod.published or newly_published or current_user.admin:
                # Allow unchecking the CKAN badge while the mod isn't published yet
                # or all the time for admins.
                mod.ckan = False

        if ckan and not mod.ckan:
            # Badge checked just now, send it
            mod.ckan = True
            send_to_ckan(mod)
        elif mod.ckan and newly_published:
            # Badge checked previously but published just now, send it
            send_to_ckan(mod)
        elif mod.ckan:
            # Badge checked previously, notify
            notify_ckan(mod, 'edit')

        if background and background != '':
            mod.background = background
        try:
            mod.bgOffsetY = int(bgOffsetY)
        except:
            pass
        return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name, ga=game))


@mods.route("/create/mod")
@loginrequired
@with_session
def create_mod() -> str:
    ga = _restore_game_info()
    return render_template("create.html", games=get_games(), ga=ga)


@mods.route("/mod/<int:mod_id>/stats/downloads", defaults={'mod_name': None})
@mods.route("/mod/<int:mod_id>/<path:mod_name>/stats/downloads")
def export_downloads(mod_id: int, mod_name: str) -> werkzeug.wrappers.Response:
    mod, game = _get_mod_game_info(mod_id)
    download_stats = get_download_events(mod.id)
    response = make_response(render_template("downloads.csv", stats=download_stats))
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment;filename=downloads.csv'
    return response


@mods.route("/mod/<int:mod_id>/stats/followers", defaults={'mod_name': None})
@mods.route("/mod/<int:mod_id>/<path:mod_name>/stats/followers")
def export_followers(mod_id: int, mod_name: str) -> werkzeug.wrappers.Response:
    mod, game = _get_mod_game_info(mod_id)
    follower_stats = get_follow_events(mod.id)
    response = make_response(render_template("followers.csv", stats=follower_stats))
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment;filename=followers.csv'
    return response


@mods.route("/mod/<int:mod_id>/stats/referrals", defaults={'mod_name': None})
@mods.route("/mod/<int:mod_id>/<path:mod_name>/stats/referrals")
def export_referrals(mod_id: int, mod_name: str) -> werkzeug.wrappers.Response:
    mod, game = _get_mod_game_info(mod_id)
    referral_stats = get_referral_events(mod.id)
    response = make_response(render_template("referrals.csv", stats=referral_stats))
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment;filename=referrals.csv'
    return response


@mods.route("/mod/<int:mod_id>/delete", methods=['POST'])
@loginrequired
@with_session
def delete(mod_id: int) -> werkzeug.wrappers.Response:
    mod, game = _get_mod_game_info(mod_id)
    editable = False
    if current_user:
        if current_user.admin:
            editable = True
        if current_user.id == mod.user_id:
            editable = True
    if not editable:
        abort(403)
    db.delete(mod)
    for featured in Featured.query.filter(Featured.mod_id == mod.id).all():
        db.delete(featured)
    for media in Media.query.filter(Media.mod_id == mod.id).all():
        db.delete(media)
    for version in ModVersion.query.filter(ModVersion.mod_id == mod.id).all():
        db.delete(version)
    base_path = os.path.join(secure_filename(mod.user.username) + '_' +
                             str(mod.user.id), secure_filename(mod.name))
    db.commit()
    notify_ckan(mod, 'delete', True)
    storage = _cfg('storage')
    if storage:
        full_path = os.path.join(storage, base_path)
        rmtree(full_path)
    return redirect("/profile/" + current_user.username)


@mods.route("/mod/<int:mod_id>/follow", methods=['POST'])
@loginrequired
@json_output
@with_session
def follow(mod_id: int) -> Dict[str, Any]:
    mod, game = _get_mod_game_info(mod_id)
    if any(m.id == mod.id for m in current_user.following):
        abort(418)
    # Events are aggregated hourly
    an_hour_ago = datetime.now() - timedelta(hours=1)
    event = FollowEvent.query\
        .filter(FollowEvent.mod_id == mod.id, FollowEvent.created > an_hour_ago)\
        .order_by(desc(FollowEvent.created))\
        .first()
    if not event:
        event = FollowEvent()
        event.mod = mod
        event.delta = 1
        event.events = 1
        db.add(event)
        db.flush()
        db.commit()
        mod.follow_events.append(event)
    else:
        event.delta += 1
        event.events += 1
    mod.follower_count += 1
    mod.score = get_mod_score(mod)
    current_user.following.append(mod)
    return {"success": True}


@mods.route("/mod/<int:mod_id>/unfollow", methods=['POST'])
@loginrequired
@json_output
@with_session
def unfollow(mod_id: int) -> Dict[str, Any]:
    mod, game = _get_mod_game_info(mod_id)
    if not any(m.id == mod.id for m in current_user.following):
        abort(418)
    event = FollowEvent.query\
        .filter(FollowEvent.mod_id == mod.id)\
        .order_by(desc(FollowEvent.created))\
        .first()
    # Events are aggregated hourly
    if not event or ((datetime.now() - event.created).seconds / 60 / 60) >= 1:
        event = FollowEvent()
        event.mod = mod
        event.delta = -1
        event.events = 1
        mod.follow_events.append(event)
        db.add(event)
    else:
        event.delta -= 1
        event.events += 1
    mod.follower_count -= 1
    mod.score = get_mod_score(mod)
    current_user.following = [m for m in current_user.following if m.id != int(mod_id)]
    return {"success": True}


@mods.route('/mod/<int:mod_id>/feature', methods=['POST'])
@adminrequired
@json_output
@with_session
def feature(mod_id: int) -> Dict[str, Any]:
    mod, game = _get_mod_game_info(mod_id)
    if any(Featured.query.filter(Featured.mod_id == mod_id).all()):
        abort(409)
    featured = Featured()
    featured.mod = mod
    db.add(featured)
    return {"success": True}


@mods.route('/mod/<int:mod_id>/unfeature', methods=['POST'])
@adminrequired
@json_output
@with_session
def unfeature(mod_id: int) -> Dict[str, Any]:
    _get_mod_game_info(mod_id)
    featured = Featured.query.filter(Featured.mod_id == mod_id).first()
    if not featured:
        abort(404)
    db.delete(featured)
    return {"success": True}


@mods.route('/mod/<int:mod_id>/<path:mod_name>/publish')
@with_session
@loginrequired
def publish(mod_id: int, mod_name: str) -> werkzeug.wrappers.Response:
    mod, game = _get_mod_game_info(mod_id)
    if current_user.id != mod.user_id and not current_user.admin:
        abort(403)
    if mod.locked:
        abort(403)
    if mod.published:
        abort(400)
    if mod.description == default_description:
        return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name, stupid_user=True))
    mod.published = True
    mod.updated = datetime.now()
    mod.score = get_mod_score(mod)
    send_to_ckan(mod)
    return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name))


@mods.route('/mod/<int:mod_id>/lock', methods=['POST'])
@adminrequired
@with_session
def lock(mod_id: int) -> werkzeug.wrappers.Response:
    mod, game = _get_mod_game_info(mod_id)
    if mod.locked:
        abort(400)

    mod.locked = True
    mod.published = False
    mod.locked_by = current_user
    mod.lock_reason = request.form.get('reason')
    send_mod_locked(mod, mod.user)
    notify_ckan(mod, 'locked', True)
    return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name))


@mods.route('/mod/<int:mod_id>/unlock', methods=['POST'])
@adminrequired
@with_session
def unlock(mod_id: int) -> werkzeug.wrappers.Response:
    mod, game = _get_mod_game_info(mod_id)
    if not mod.locked:
        abort(400)

    mod.locked = False
    mod.locked_by = None
    mod.lock_reason = ''
    notify_ckan(mod, 'unlocked', True)
    return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name))


def _allow_download(mod: Mod) -> bool:
    # Anyone can download published mods
    if mod.published:
        return True
    # No user context, can't access unpublished
    if not current_user:
        return False
    # Admins can download everything
    if current_user.admin:
        return True
    # Mod authors can download their own unpublished mods
    if current_user.id == mod.user_id:
        return True
    # But nobody else can
    return False


@mods.route('/mod/<int:mod_id>/download/<version>', defaults={'mod_name': None})
@mods.route('/mod/<int:mod_id>/download', defaults={'mod_name': None, 'version': None})
@mods.route('/mod/<int:mod_id>/<path:mod_name>/download', defaults={'version': None})
@mods.route('/mod/<int:mod_id>/<path:mod_name>/download/<version>')
@with_session
def download(mod_id: int, mod_name: Optional[str], version: Optional[str]) -> Optional[werkzeug.wrappers.Response]:
    mod, game = _get_mod_game_info(mod_id)
    if not _allow_download(mod):
        abort(403, 'Unfortunately the requested mod isn\'t available for download. Maybe it\'s not public yet?')
    mod_version = mod.default_version if not version or version == 'download' \
        else next(filter(lambda v: v.friendly_version == version, mod.versions), None)
    if not mod_version:
        abort(404, 'Unfortunately we couldn\'t find the requested mod version. Maybe it got deleted?')
    # Events are aggregated hourly
    an_hour_ago = datetime.now() - timedelta(hours=1)
    download = DownloadEvent.query\
        .filter(DownloadEvent.version_id == mod_version.id, DownloadEvent.created > an_hour_ago)\
        .order_by(desc(DownloadEvent.created))\
        .first()
    storage = _cfg('storage')
    if not storage:
        abort(404)

    if 'Range' not in request.headers:
        if not download:
            download = DownloadEvent()
            download.mod = mod
            download.version = mod_version
            download.downloads = 1
            db.add(download)
            db.flush()
            db.commit()
            mod.downloads.append(download)
        else:
            download.downloads += 1
        mod.download_count += 1
        mod_version.download_count += 1
        mod.score = get_mod_score(mod)

    protocol = _cfg("protocol")
    cdn_domain = _cfg("cdn-domain")
    if protocol and cdn_domain:
        return redirect(protocol + '://' + cdn_domain + '/' + mod_version.download_path, code=302)

    response = None
    if _cfg("use-x-accel") == 'nginx':
        response = make_response("")
        response.headers['Content-Type'] = 'application/zip'
        response.headers['Content-Disposition'] = 'attachment; filename=' + \
            os.path.basename(mod_version.download_path)
        response.headers['X-Accel-Redirect'] = '/internal/' + mod_version.download_path
    if _cfg("use-x-accel") == 'apache':
        response = make_response("")
        response.headers['Content-Type'] = 'application/zip'
        response.headers['Content-Disposition'] = 'attachment; filename=' + \
            os.path.basename(mod_version.download_path)
        response.headers['X-Sendfile'] = os.path.join(storage, mod_version.download_path)
    if response is None:
        download_path = os.path.join(storage, mod_version.download_path)
        if not os.path.isfile(download_path):
            abort(404)
        response = make_response(send_file(download_path, as_attachment=True))
    return response


_orig_create_connection = connection.create_connection
_create_connection_mutex = threading.Lock()


@mods.route('/mod/<int:mod_id>/version/<version_id>/delete', methods=['POST'])
@with_session
@loginrequired
def delete_version(mod_id: int, version_id: str) -> werkzeug.wrappers.Response:
    mod, game = _get_mod_game_info(mod_id)
    check_mod_editable(mod)
    version = [v for v in mod.versions if v.id == int(version_id)]
    if len(mod.versions) == 1:
        abort(400)
    if len(version) == 0:
        abort(404)
    if version[0].id == mod.default_version_id:
        abort(400)

    protocol = _cfg('protocol')
    cdn_domain = _cfg('cdn-domain')
    if protocol and cdn_domain:
        global _create_connection_mutex
        # Only one thread is allowed to mess with connection.create_connection at a time
        with _create_connection_mutex:
            connection.create_connection = create_connection_cdn_purge
            requests.request('PURGE',
                protocol + '://' + cdn_domain + '/' + version[0].download_path)
            global _orig_create_connection
            connection.create_connection = _orig_create_connection

    db.delete(version[0])
    mod.versions = [v for v in mod.versions if v.id != int(version_id)]
    db.commit()
    return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name, ga=game))


def create_connection_cdn_purge(address: Tuple[str, Union[str, int, None]], *args: str, **kwargs: int) -> socket:
    # Taken from https://stackoverflow.com/a/22614367
    host, port = address

    cdn_internal = _cfg('cdn-internal')
    cdn_domain = _cfg('cdn-domain')
    if cdn_internal and cdn_domain and cdn_domain.startswith(host):
        result = dns.resolver.resolve(cdn_internal)
        host = result[0].to_text()

    global _orig_create_connection
    assert callable(_orig_create_connection)
    return _orig_create_connection((host, port), *args, **kwargs)


@mods.route('/mod/<int:mod_id>/<mod_name>/edit_version', methods=['POST'])
@mods.route('/mod/<int:mod_id>/edit_version', methods=['POST'], defaults={'mod_name': None})
@with_session
@loginrequired
def edit_version(mod_id: int, mod_name: str) -> werkzeug.wrappers.Response:
    mod, game = _get_mod_game_info(mod_id)
    check_mod_editable(mod)
    version_id = int(request.form.get('version-id', ''))
    changelog = request.form.get('changelog')
    versions = [v for v in mod.versions if v.id == version_id]
    if len(versions) == 0:
        abort(404)
    version = versions[0]
    version.changelog = changelog
    return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name, ga=game))


@mods.route('/mod/<int:mod_id>/autoupdate', methods=['POST'])
@with_session
@loginrequired
def autoupdate(mod_id: int) -> werkzeug.wrappers.Response:
    mod, game = _get_mod_game_info(mod_id)
    check_mod_editable(mod)
    default = mod.default_version
    default.gameversion_id = GameVersion.query.filter(
        GameVersion.game_id == mod.game_id).order_by(desc(GameVersion.id)).first().id
    mod.updated = datetime.now()
    mod.score = get_mod_score(mod)
    send_autoupdate_notification(mod)
    notify_ckan(mod, 'version-update')
    return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name, ga=game))
