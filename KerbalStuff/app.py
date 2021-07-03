import hashlib
import hmac
import json
import locale
import os
import subprocess
import xml.etree.ElementTree as ET
from time import strftime
from typing import Tuple, List, Dict, Any, Optional, Union
from pathlib import Path

import requests
import werkzeug.wrappers
from flask import Flask, render_template, g, url_for, Response, request
from flask_login import LoginManager, current_user
from flaskext.markdown import Markdown
from sqlalchemy import desc
from werkzeug.exceptions import HTTPException, InternalServerError

from .blueprints.accounts import accounts
from .blueprints.admin import admin
from .blueprints.anonymous import anonymous
from .blueprints.api import api
from .blueprints.blog import blog
from .blueprints.lists import lists
from .blueprints.login_oauth import list_defined_oauths, login_oauth
from .blueprints.mods import mods
from .blueprints.profile import profiles
from .middleware.session_interface import OnlyLoggedInSessionInterface
from .celery import update_from_github
from .common import first_paragraphs, many_paragraphs, json_output, jsonify_exception, dumb_object, sanitize_text
from .config import _cfg, _cfgb, _cfgd, _cfgi, site_logger
from .custom_json import CustomJSONEncoder
from .database import db
from .helpers import is_admin, following_mod
from .kerbdown import KerbDown
from .objects import User, BlogPost

app = Flask(__name__, template_folder='../templates')
# https://flask.palletsprojects.com/en/1.1.x/security/#set-cookie-options
# Set 'Secure', 'HttpOnly' and 'SameSite' attributes for session and remember-me cookiesHTTPS
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SAMESITE='Lax'
)
if not app.debug:
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        REMEMBER_COOKIE_SECURE=True
    )
app.jinja_env.filters['first_paragraphs'] = first_paragraphs
app.jinja_env.filters['bleach'] = sanitize_text
app.jinja_env.auto_reload = app.debug
app.secret_key = _cfg("secret-key")
app.json_encoder = CustomJSONEncoder
app.session_interface = OnlyLoggedInSessionInterface()
Markdown(app, extensions=[KerbDown(), 'fenced_code'])
login_manager = LoginManager(app)

prof_dir = _cfg('profile-dir')
if prof_dir:
    from .middleware.profiler import ConditionalProfilerMiddleware
    from .profiling import sampling_function
    Path(prof_dir).mkdir(parents=True, exist_ok=True)
    app.wsgi_app = ConditionalProfilerMiddleware(  # type: ignore[assignment]
        app.wsgi_app, stream=None, profile_dir=prof_dir, sampling_function=sampling_function)


@login_manager.user_loader
def load_user(username: str) -> User:
    return User.query.filter(User.username == username).first()


login_manager.anonymous_user = lambda: None

app.register_blueprint(profiles)
app.register_blueprint(accounts)
app.register_blueprint(login_oauth)
app.register_blueprint(anonymous)
app.register_blueprint(blog)
app.register_blueprint(admin)
app.register_blueprint(mods)
app.register_blueprint(lists)
app.register_blueprint(api)

try:
    locale.setlocale(locale.LC_ALL, 'en_US')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'en')
    except:
        pass  # give up

# Send ERROR and EXCEPTION level log entries to syslog and per email.
error_to = _cfg("error-to")
if error_to:
    import logging
    from logging.handlers import SMTPHandler

    smtp_host = _cfg('smtp-host')
    smtp_port = _cfgi('smtp-port')
    error_from = _cfg('error-from')
    site_name = _cfg('site-name')
    if smtp_host and smtp_port and error_from and site_name:
        mail_handler = SMTPHandler((smtp_host, smtp_port),
                                   error_from, [error_to],
                                   site_name + ' Application Exception')
        mail_handler.setLevel(logging.ERROR)
        app.logger.addHandler(mail_handler)

# Error handlers. We want to handle errors differently based on their nature, whether it's done via XHR,
# and whether we're in a debug/development environment.

#                 | HTTPException |
# app.debug | XHR | or code>=500  | What to do?
# ---------------------------------------------
# 0         | 0   | 0             | Real 5XX -> log, db rollback, error_5XX.html
# 0         | 0   | 1             | 4XX -> error_404.html or error_4XX.html
# 0         | 1   | 0             | Real 5XX in API -> log, db rollback, jsonified_exception(e)
# 0         | 1   | 1             | 4XX in API -> jsonified_exception(e)
# 1         | 0   | 0             | Real 5XX -> log, db rollback, debugger
# 1         | 0   | 1             | 4XX -> error_404.html or error_4XX.html
# 1         | 1   | 0             | Real 5XX in API -> log, db rollback, jsonified_exception(e)
# 1         | 1   | 1             | 4XX in API -> jsonified_exception(e)


@app.errorhandler(404)
def handle_404(e: HTTPException) -> Union[Tuple[str, int], werkzeug.wrappers.Response]:
    # Switch out the default message
    if e.description == werkzeug.exceptions.NotFound.description:
        e.description = "Requested page not found. Looks like this was deleted, or maybe was never here."

    if request.path.startswith("/api/") \
            or (request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html):
        return jsonify_exception(e)
    return render_template("error_404.html", error=e), 404


# This one handles the remaining 4XX errors. JSONified for XHR requests, otherwise the user gets a nice error screen.
@app.errorhandler(HTTPException)
def handle_http_exception(e: HTTPException) -> Union[Tuple[str, int], werkzeug.wrappers.Response]:
    if e.code and e.code >= 500:
        return handle_generic_exception(e)
    if request.path.startswith("/api/") \
            or (request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html):
        return jsonify_exception(e)
    return render_template("error_4XX.html", error=e), e.code or 400


# And this one handles everything leftover, that means, real otherwise unhandled exceptions.
# https://flask.palletsprojects.com/en/1.1.x/errorhandling/#unhandled-exceptions
@app.errorhandler(Exception)
def handle_generic_exception(e: Union[Exception, HTTPException]) -> Union[Tuple[str, int], werkzeug.wrappers.Response]:
    site_logger.exception(e)
    try:
        db.rollback()
        db.close()
    except:
        pass

    if request.path.startswith("/api/") \
            or (request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html):
        return jsonify_exception(e)
    elif app.debug:
        raise e
    else:
        if not isinstance(e, HTTPException):
            # Create an HTTPException so it has a code, name and description which we access in the template.
            # We deliberately loose the original message here because it can contain confidential data.
            e = InternalServerError()
        if e.description == werkzeug.exceptions.InternalServerError.description:
            e.description = "Clearly you've broken something. Maybe if you refresh no one will notice."
        return render_template("error_5XX.html", error=e), e.code or 500


# I am unsure if this function is still needed or rather, if it still works.
# TODO(Thomas): Investigate and remove
@app.route('/ksp-profile-proxy/<fragment>')
@json_output
def profile_proxy(fragment: str) -> List[Dict[str, Any]]:
    r = requests.post("http://forum.kerbalspaceprogram.com/ajax.php?do=usersearch",
                      data={
                          'securitytoken': 'guest',
                          'do': 'usersearch',
                          'fragment': fragment
                      })
    root = ET.fromstring(r.text)
    results = list()
    for child in root:
        results.append({
            'id': child.attrib['userid'],
            'name': child.text
        })
    return results


@app.route('/version')
def version() -> Response:
    return Response(subprocess.check_output(["git", "log", "-1"]), mimetype="text/plain")


@app.route('/hook', methods=['POST'])
def hook_publish() -> Union[str, Tuple[str, int]]:
    try:
        # Configuration sanity check
        hook_branch = _cfg("hook_branch")
        if not hook_branch:
            app.logger.info("No hook_branch is configured.")
            return "ignored"
        restart_command = _cfg("restart_command")
        if not restart_command:
            app.logger.info("No restart_command is configured.")
            return "ignored"
        # Make sure it's from GitHub
        if not sig_match(request.headers.get("X-Hub-Signature", ''), request.data):
            app.logger.warning("X-Hub-Signature didn't match the request data")
            return "unauthorized", 403
        event = json.loads(request.data.decode("utf-8"))
        # Make sure it's the right repo
        expected_repo = _cfg("hook_repository")
        repo_id = event["repository"]["full_name"]
        if not expected_repo == repo_id:
            app.logger.info("Wrong repository. Expected '%s', got '%s'", expected_repo, repo_id)
            return "ignored"
        # Make sure it's the right branch
        expected_ref = "refs/heads/" + hook_branch
        ref_id = event["ref"]
        if expected_ref != ref_id:
            app.logger.info("Wrong branch. Expected '%s', got '%s'", expected_ref, ref_id)
            return "ignored"
        # Skip if we put "[noupdate]" in any of the commit messages
        if any("[noupdate]" in c["message"] for c in event["commits"]):
            app.logger.info("A commit in the update is tagged [noupdate]. Ignoring the update.")
            return "ignored"
        # Pull and restart site
        app.logger.info("Received push event from github. Starting update process...")
        update_from_github.delay(os.getcwd(), hook_branch, restart_command)
        return "thanks"
    except Exception:
        app.logger.exception('Unable to process github hook data')
        return "internal server error", 500


def sig_match(req_sig: Optional[str], body: bytes) -> bool:
    # Make sure a secret is defined in our config
    hook_secret = _cfg("hook_secret")
    if not hook_secret:
        app.logger.warning('No hook_secret is configured')
        return False
    # Make sure a sig was sent
    if req_sig is None:
        app.logger.warning('No signature provided in the request')
        return False
    # Make sure they match
    # compare_digest takes the same time regardless of how similar the strings are
    # (to make it harder for hackers)
    secret_sig = "sha1=" + hmac.new(hook_secret.encode('ascii'), body, hashlib.sha1).hexdigest()
    return hmac.compare_digest(req_sig, secret_sig)


@app.before_request
def find_dnt() -> None:
    field = "Dnt"
    do_not_track = False
    if field in request.headers:
        do_not_track = True if request.headers[field] == "1" else False
    g.do_not_track = do_not_track


@app.context_processor
def inject() -> Dict[str, Any]:
    protocol = _cfg('protocol')
    domain = _cfg('domain')
    if not protocol or not domain:
        return dict()
    first_visit = True
    dismissed_donation = False
    if request.cookies.get('first_visit') is not None:
        first_visit = False
    if request.cookies.get('dismissed_donation') is not None:
        dismissed_donation = True
    return {
        'announcements': (get_all_announcement_posts()
                          if current_user
                          else get_non_member_announcement_posts()),
        'many_paragraphs': many_paragraphs,
        'analytics_id': _cfg("google_analytics_id"),
        'analytics_domain': _cfg("google_analytics_domain"),
        'disqus_id': _cfg("disqus_id"),
        'dnt': True,
        'root': protocol + "://" + domain,
        'domain': _cfg("domain"),
        'user': current_user,
        'len': len,
        'any': any,
        'following_mod': following_mod,
        'admin': is_admin(),
        'oauth_providers': list_defined_oauths(),
        'dumb_object': dumb_object,
        'first_visit': first_visit,
        'request': request,
        'url_for': url_for,
        'strftime': strftime,
        'site_name': _cfg('site-name'),
        'support_mail': _cfg('support-mail'),
        'source_code': _cfg('source-code'),
        'support_channels': _cfgd('support-channels'),
        'donation_link': _cfg('donation-link'),
        'donation_header_link': _cfgb('donation-header-link') if not dismissed_donation else False,
        'registration': _cfgb('registration')
    }


def get_all_announcement_posts() -> List[BlogPost]:
    return BlogPost.query.filter(BlogPost.announcement).order_by(desc(BlogPost.created)).all()


def get_non_member_announcement_posts() -> List[BlogPost]:
    return BlogPost.query.filter(
        BlogPost.announcement, BlogPost.members_only != True
    ).order_by(desc(BlogPost.created)).all()
