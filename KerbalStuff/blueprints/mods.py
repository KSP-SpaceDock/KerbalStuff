import os
import random
from datetime import datetime, timedelta
from shutil import rmtree
from urllib.parse import urlparse, quote_plus

from flask import Blueprint, render_template, send_file, make_response, url_for, abort, session, \
    redirect, request
from flask_login import current_user
from sqlalchemy import desc
from werkzeug.utils import secure_filename

from .api import default_description
from ..ckan import send_to_ckan, notify_ckan
from ..common import get_game_info, set_game_info, with_session, dumb_object, loginrequired, \
    json_output, adminrequired, check_mod_editable, get_version_size
from ..config import _cfg
from ..database import db
from ..email import send_autoupdate_notification, send_mod_locked
from ..objects import Mod, ModVersion, DownloadEvent, FollowEvent, ReferralEvent, \
    Featured, Media, GameVersion, Game

mods = Blueprint('mods', __name__, template_folder='../../templates/mods')


def _get_mod_game_info(mod_id):
    mod = Mod.query.get(mod_id)
    if not mod:
        abort(404)
    game = mod.game
    if not game:
        get_game_info()
        abort(404)
    set_game_info(game)
    return mod, game


def _restore_game_info():
    game_id = session.get('gameid')

    if game_id:
        game = Game.query.filter(Game.active == True, Game.id == game_id).one()
        # Make sure it's fully set in the session cookie.
        set_game_info(game)
        return game

    return None


@mods.route("/random")
def random_mod():
    game_id = session.get('gameid')
    mods = Mod.query.with_entities(Mod.id, Mod.name).filter(Mod.published == True)
    if game_id:
        mods = mods.filter(Mod.game_id == game_id)
    mods = mods.all()
    if not mods:
        abort(404)
    mod_id, mod_name = random.choice(mods)
    return redirect(url_for("mods.mod", mod_id=mod_id, mod_name=mod_name))


@mods.route("/mod/<int:mod_id>/<path:mod_name>/update")
def update(mod_id, mod_name):
    mod = Mod.query.filter(Mod.id == mod_id).one()
    if not mod:
        abort(404)
    check_mod_editable(mod)
    game_versions = GameVersion.query.filter(GameVersion.game_id == mod.game_id).order_by(desc(GameVersion.id)).all()
    return render_template("update.html", mod=mod, game_versions=game_versions)


@mods.route("/mod/<int:mod_id>.rss", defaults={'mod_name': None})
@mods.route("/mod/<int:mod_id>/<path:mod_name>.rss")
def mod_rss(mod_id, mod_name):
    mod, _ = _get_mod_game_info(mod_id)
    return render_template("rss-mod.xml", mod=mod)


@mods.route("/mod/<int:mod_id>", defaults={'mod_name': None})
@mods.route("/mod/<int:mod_id>/<path:mod_name>")
@with_session
def mod(mod_id, mod_name):
    mod, ga = _get_mod_game_info(mod_id)
    editable = False
    if current_user:
        if current_user.admin:
            editable = True
        if current_user.id == mod.user_id:
            editable = True
    if not mod.published and not editable:
        abort(401)
    latest = mod.default_version
    referral = request.referrer
    if referral:
        host = urlparse(referral).hostname
        event = ReferralEvent.query\
                .filter(ReferralEvent.mod_id == mod.id)\
                .filter(ReferralEvent.host == host)\
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
    thirty_days_ago = datetime.now() - timedelta(days=30)
    referrals = list()
    for r in ReferralEvent.query\
        .filter(ReferralEvent.mod_id == mod.id)\
        .order_by(desc(ReferralEvent.events)):
        referrals.append( { 'host': r.host, 'count': r.events } )
    download_stats = list()
    for d in DownloadEvent.query\
        .filter(DownloadEvent.mod_id == mod.id)\
        .filter(DownloadEvent.created > thirty_days_ago)\
        .order_by(DownloadEvent.created):
        download_stats.append(dumb_object(d))
    follower_stats = list()
    for f in FollowEvent.query\
        .filter(FollowEvent.mod_id == mod.id)\
        .filter(FollowEvent.created > thirty_days_ago)\
        .order_by(FollowEvent.created):
        follower_stats.append(dumb_object(f))
    json_versions = list()
    size_versions = dict()
    for v in mod.versions:
        json_versions.append({ 'name': v.friendly_version, 'id': v.id })
        size_versions[v.id] = get_version_size(os.path.join(_cfg('storage'), v.download_path))
    if request.args.get('noedit') is not None:
        editable = False
    forumThread = False
    if mod.external_link is not None:
        try:
            u = urlparse(mod.external_link)
            if u.netloc == 'forum.kerbalspaceprogram.com':
                forumThread = True
        except Exception as e:
            print(e)
            pass
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
    games = Game.query.filter(Game.active == True).order_by(desc(Game.id)).all()
    game_versions = GameVersion.query.filter(GameVersion.game_id == mod.game_id).order_by(desc(GameVersion.id)).all()
    outdated = False
    if latest:
        outdated = latest.gameversion.id != game_versions[0].id and latest.gameversion.friendly_version != '1.0.5'
    return render_template("mod.html",
        **{
            'mod': mod,
            'latest': latest,
            'safe_name': secure_filename(mod.name)[:64],
            'featured': any(Featured.query.filter(Featured.mod_id == mod.id)),
            'editable': editable,
            'owner': owner,
            'pending_invite': pending_invite,
            'download_stats': download_stats,
            'follower_stats': follower_stats,
            'referrals': referrals,
            'json_versions': json_versions,
            'thirty_days_ago': thirty_days_ago,
            'share_link': quote_plus(_cfg("protocol") + "://" + _cfg("domain") + "/mod/" + str(mod.id)),
            'game_versions': game_versions,
            'games':  games,
            'outdated': outdated,
            'forum_thread': forumThread,
            'new': request.args.get('new') is not None,
            'stupid_user': request.args.get('stupid_user') is not None,
            'total_authors': total_authors,
            "site_name": _cfg('site-name'),
            "support_mail": _cfg('support-mail'),
            'ga': ga,
            'size_versions': size_versions
        })


@mods.route("/mod/<int:mod_id>/<path:mod_name>/edit", methods=['GET', 'POST'])
@with_session
@loginrequired
def edit_mod(mod_id, mod_name):
    mod, game = _get_mod_game_info(mod_id)
    check_mod_editable(mod)
    if request.method == 'GET':
        return render_template("edit_mod.html", mod=mod, original=mod.user == current_user)
    else:
        short_description = request.form.get('short-description')
        license = request.form.get('license')
        donation_link = request.form.get('donation-link')
        external_link = request.form.get('external-link')
        source_link = request.form.get('source-link')
        description = request.form.get('description')
        ckan = request.form.get('ckan')
        background = request.form.get('background')
        bgOffsetY = request.form.get('bg-offset-y')
        if not license or license == '':
            return render_template("edit_mod.html", mod=mod, error="All mods must have a license.")
        mod.short_description = short_description
        mod.license = license
        mod.donation_link = donation_link
        mod.external_link = external_link
        mod.source_link = source_link
        mod.description = description
        if ckan is None:
            ckan = False
        else:
            ckan = (ckan.lower() in ['true', 'yes', 'on'])
        if ckan:
            if not mod.ckan:
                mod.ckan = ckan
                send_to_ckan(mod)
            else:
                notify_ckan(mod, 'edit')
        if background and background != '':
            mod.background = background
        try:
            mod.bgOffsetY = int(bgOffsetY)
        except:
            pass
        return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name,ga=game))


@mods.route("/create/mod")
@loginrequired
@with_session
def create_mod():
    ga = _restore_game_info()
    games = Game.query.filter(Game.active == True).order_by(desc(Game.id)).all()
    return render_template("create.html", games=games, ga=ga)


@mods.route("/mod/<int:mod_id>/stats/downloads", defaults={'mod_name': None})
@mods.route("/mod/<int:mod_id>/<path:mod_name>/stats/downloads")
def export_downloads(mod_id, mod_name):
    mod, game = _get_mod_game_info(mod_id)
    download_stats = DownloadEvent.query\
        .filter(DownloadEvent.mod_id == mod.id)\
        .order_by(DownloadEvent.created)
    response = make_response(render_template("downloads.csv", stats=download_stats))
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment;filename=downloads.csv'
    return response


@mods.route("/mod/<int:mod_id>/stats/followers", defaults={'mod_name': None})
@mods.route("/mod/<int:mod_id>/<path:mod_name>/stats/followers")
def export_followers(mod_id, mod_name):
    mod, game = _get_mod_game_info(mod_id)
    follower_stats = FollowEvent.query\
        .filter(FollowEvent.mod_id == mod.id)\
        .order_by(FollowEvent.created)
    response = make_response(render_template("followers.csv", stats=follower_stats))
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment;filename=followers.csv'
    return response


@mods.route("/mod/<int:mod_id>/stats/referrals", defaults={'mod_name': None})
@mods.route("/mod/<int:mod_id>/<path:mod_name>/stats/referrals")
def export_referrals(mod_id, mod_name):
    mod, game = _get_mod_game_info(mod_id)
    referral_stats = ReferralEvent.query\
            .filter(ReferralEvent.mod_id == mod.id)\
            .order_by(desc(ReferralEvent.events))
    response = make_response(render_template("referrals.csv", stats=referral_stats))
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment;filename=referrals.csv'
    return response


@mods.route("/mod/<int:mod_id>/delete", methods=['POST'])
@loginrequired
@with_session
def delete(mod_id):
    mod, game = _get_mod_game_info(mod_id)
    editable = False
    if current_user:
        if current_user.admin:
            editable = True
        if current_user.id == mod.user_id:
            editable = True
    if not editable:
        abort(401)
    db.delete(mod)
    for featured in Featured.query.filter(Featured.mod_id == mod.id).all():
        db.delete(featured)
    for media in Media.query.filter(Media.mod_id == mod.id).all():
        db.delete(media)
    for version in ModVersion.query.filter(ModVersion.mod_id == mod.id).all():
        db.delete(version)
    base_path = os.path.join(secure_filename(mod.user.username) + '_' + str(mod.user.id), secure_filename(mod.name))
    full_path = os.path.join(_cfg('storage'), base_path)
    db.commit()
    notify_ckan(mod, 'delete')
    rmtree(full_path)
    return redirect("/profile/" + current_user.username)


@mods.route("/mod/<int:mod_id>/follow", methods=['POST'])
@loginrequired
@json_output
@with_session
def follow(mod_id):
    mod, game = _get_mod_game_info(mod_id)
    if any(m.id == mod.id for m in current_user.following):
        abort(418)
    event = FollowEvent.query\
            .filter(FollowEvent.mod_id == mod.id)\
            .order_by(desc(FollowEvent.created))\
            .first()
    # Events are aggregated hourly
    if not event or ((datetime.now() - event.created).seconds / 60 / 60) >= 1:
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
    current_user.following.append(mod)
    return { "success": True }


@mods.route("/mod/<int:mod_id>/unfollow", methods=['POST'])
@loginrequired
@json_output
@with_session
def unfollow(mod_id):
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
    current_user.following = [m for m in current_user.following if m.id != int(mod_id)]
    return { "success": True }


@mods.route('/mod/<int:mod_id>/feature', methods=['POST'])
@adminrequired
@json_output
@with_session
def feature(mod_id):
    mod, game = _get_mod_game_info(mod_id)
    if any(Featured.query.filter(Featured.mod_id == mod_id).all()):
        abort(409)
    featured = Featured()
    featured.mod = mod
    db.add(featured)
    return { "success": True }


@mods.route('/mod/<int:mod_id>/unfeature', methods=['POST'])
@adminrequired
@json_output
@with_session
def unfeature(mod_id):
    _get_mod_game_info(mod_id)
    featured = Featured.query.filter(Featured.mod_id == mod_id).first()
    if not featured:
        abort(404)
    db.delete(featured)
    return { "success": True }


@mods.route('/mod/<int:mod_id>/<path:mod_name>/publish')
@with_session
@loginrequired
def publish(mod_id, mod_name):
    mod, game = _get_mod_game_info(mod_id)
    if current_user.id != mod.user_id and not current_user.admin:
        abort(401)
    if mod.locked:
        abort(403)
    if mod.description == default_description:
        return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name, stupid_user=True))
    mod.published = True
    mod.updated = datetime.now()
    send_to_ckan(mod)
    return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name))


@mods.route('/mod/<int:mod_id>/lock', methods=['POST'])
@adminrequired
@with_session
def lock(mod_id):
    mod, game = _get_mod_game_info(mod_id)
    if mod.locked:
        abort(400)

    mod.locked = True
    mod.published = False
    mod.locked_by = current_user
    mod.lock_reason = request.form.get('reason')
    send_mod_locked(mod, mod.user)
    notify_ckan(mod, 'locked')
    return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name))


@mods.route('/mod/<int:mod_id>/unlock', methods=['POST'])
@adminrequired
@with_session
def unlock(mod_id):
    mod, game = _get_mod_game_info(mod_id)
    if not mod.locked:
        abort(400)

    mod.locked = False
    mod.locked_by = None
    mod.lock_reason = ''
    notify_ckan(mod, 'unlocked')
    return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name))


@mods.route('/mod/<int:mod_id>/download/<version>', defaults={ 'mod_name': None })
@mods.route('/mod/<int:mod_id>/<path:mod_name>/download/<version>')
@with_session
def download(mod_id, mod_name, version):
    mod, game = _get_mod_game_info(mod_id)
    if not mod.published and (not current_user or current_user.id != mod.user_id):
        abort(401)
    version = ModVersion.query.filter(ModVersion.mod_id == mod_id,
                                      ModVersion.friendly_version == version).first()
    if not version:
        abort(404)
    download = DownloadEvent.query\
            .filter(DownloadEvent.mod_id == mod.id and DownloadEvent.version_id == version.id)\
            .order_by(desc(DownloadEvent.created))\
            .first()
    if not os.path.isfile(os.path.join(_cfg('storage'), version.download_path)):
        abort(404)

    if not 'Range' in request.headers:
        # Events are aggregated hourly
        if not download or ((datetime.now() - download.created).seconds / 60 / 60) >= 1:
            download = DownloadEvent()
            download.mod = mod
            download.version = version
            download.downloads = 1
            db.add(download)
            db.flush()
            db.commit()
            mod.downloads.append(download)
        else:
            download.downloads += 1
        mod.download_count += 1

    if _cfg("cdn-domain"):
        return redirect("http://" + _cfg("cdn-domain") + '/' + version.download_path, code=302)

    response = None
    if _cfg("use-x-accel") == 'nginx':
        response = make_response("")
        response.headers['Content-Type'] = 'application/zip'
        response.headers['Content-Disposition'] = 'attachment; filename=' + os.path.basename(version.download_path)
        response.headers['X-Accel-Redirect'] = '/internal/' + version.download_path
    if _cfg("use-x-accel") == 'apache':
        response = make_response("")
        response.headers['Content-Type'] = 'application/zip'
        response.headers['Content-Disposition'] = 'attachment; filename=' + os.path.basename(version.download_path)
        response.headers['X-Sendfile'] = os.path.join(_cfg('storage'), version.download_path)
    if response is None:
        response = make_response(send_file(os.path.join(_cfg('storage'), version.download_path), as_attachment = True))
    return response


@mods.route('/mod/<int:mod_id>/version/<version_id>/delete', methods=['POST'])
@with_session
@loginrequired
def delete_version(mod_id, version_id):
    mod, game = _get_mod_game_info(mod_id)
    check_mod_editable(mod)
    version = [v for v in mod.versions if v.id == int(version_id)]
    if len(mod.versions) == 1:
        abort(400)
    if len(version) == 0:
        abort(404)
    if version[0].id == mod.default_version_id:
        abort(400)
    db.delete(version[0])
    mod.versions = [v for v in mod.versions if v.id != int(version_id)]
    db.commit()
    return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name,ga=game))


@mods.route('/mod/<int:mod_id>/<mod_name>/edit_version', methods=['POST'])
@mods.route('/mod/<int:mod_id>/edit_version', methods=['POST'], defaults={ 'mod_name': None })
@with_session
@loginrequired
def edit_version(mod_name, mod_id):
    mod, game = _get_mod_game_info(mod_id)
    check_mod_editable(mod)
    version_id = int(request.form.get('version-id'))
    changelog = request.form.get('changelog')
    version = [v for v in mod.versions if v.id == version_id]
    if len(version) == 0:
        abort(404)
    version = version[0]
    version.changelog = changelog
    return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name,ga=game))


@mods.route('/mod/<int:mod_id>/autoupdate', methods=['POST'])
@with_session
@loginrequired
def autoupdate(mod_id):
    mod, game = _get_mod_game_info(mod_id)
    check_mod_editable(mod)
    default = mod.default_version
    default.gameversion_id = GameVersion.query.filter(GameVersion.game_id == mod.game_id).order_by(desc(GameVersion.id)).first().id
    mod.updated = datetime.now()
    send_autoupdate_notification(mod)
    notify_ckan(mod, 'version-update')
    return redirect(url_for("mods.mod", mod_id=mod.id, mod_name=mod.name, ga=game))
