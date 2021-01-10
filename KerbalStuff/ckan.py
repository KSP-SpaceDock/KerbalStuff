import threading
import requests
import re
from flask import url_for
from typing import Dict, Iterable

from .config import _cfg
from .objects import Mod, Game, GameVersion
from .database import db

CKAN_BUILDS_URL = 'https://github.com/KSP-CKAN/CKAN-meta/raw/master/builds.json'
MAJOR_MINOR_PATCH_PATTERN = re.compile(r'^([^.]+\.[^.]+\.[^.]+)')


def send_to_ckan(mod: Mod) -> None:
    protocol = _cfg('protocol')
    domain = _cfg('domain')
    url = _cfg('create-url')
    site_name = _cfg('site-name')
    if mod.game.ckan_enabled and mod.ckan and mod.published and url and protocol and domain and site_name:
        site_base_url = protocol + "://" + domain
        _bg_post(url, {
            'name': mod.name,
            'id': mod.id,
            'license': mod.license,
            'username': mod.user.username,
            'email': mod.user.email,
            'short_description': mod.short_description,
            'description': mod.description,
            'external_link': mod.external_link,
            'user_url': site_base_url + url_for("profile.view_profile", username=mod.user.username),
            'mod_url': site_base_url + url_for('mods.mod', mod_name=mod.name, mod_id=mod.id),
            'site_name': site_name,
        })


def notify_ckan(mod: Mod, event_type: str) -> None:
    url = _cfg("notify-url")
    if mod.game.ckan_enabled and mod.ckan and mod.published and url:
        _bg_post(url, {
            'mod_id': mod.id,
            'event_type': event_type,
        })


def _bg_post(url: str, data: Dict[str, str]) -> None:
    """Fire and forget some data to a POST URL in a background thread"""
    threading.Thread(target=requests.post, args=(url, data)).start()


def import_ksp_versions_from_ckan(ksp_game_id: int) -> None:
    current_versions = {gv.friendly_version
                        for gv in Game.query.get(ksp_game_id).versions}
    for version in ksp_versions_from_ckan():
        if version not in current_versions:
            current_versions.add(version)
            db.add(GameVersion(friendly_version=version, game_id=ksp_game_id))
            db.commit()


def ksp_versions_from_ckan() -> Iterable[str]:
    builds = requests.get(CKAN_BUILDS_URL).json()
    for _, full_version in builds['builds'].items():
        m = MAJOR_MINOR_PATCH_PATTERN.match(full_version)
        if m:
            yield m.groups()[0]
