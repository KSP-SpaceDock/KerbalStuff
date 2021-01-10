from datetime import datetime
from typing import Dict, Any

import pytest
from flask.testing import FlaskClient
from flask import Response
from flask_api import status

from .fixtures.client import client
from KerbalStuff.objects import Publisher, Game, GameVersion, User, Mod, ModVersion
from KerbalStuff.database import db


@pytest.mark.usefixtures("client")
def test_api_mod(client: 'FlaskClient[Response]') -> None:
    # Arrange
    game = Game(
        name='Kerbal Space Program',
        publisher=Publisher(
            name='SQUAD',
        ),
        short='kerbal-space-program',
        active=True,
        ckan_enabled=True,
    )
    mod = Mod(
        name='Test Mod',
        short_description='A mod for testing',
        description='A mod that we will use to test the API',
        user=User(
            username='TestModAuthor',
            description='Test author of a test mod',
            email='webmaster@spacedock.info',
            forumUsername='TestForumUser',
            public=True,
        ),
        license='MIT',
        game=game,
        ckan=False,
        default_version=ModVersion(
            friendly_version="1.0.0.0",
            gameversion=GameVersion(
                friendly_version='1.2.3',
                game=game,
            ),
            download_path='/tmp/blah.zip',
            created=datetime.now(),
        ),
        published=True,
    )
    mod.default_version.mod = mod
    db.add(game)
    db.add(mod)
    db.commit()

    # Act
    publishers_resp = client.get('/api/publishers')
    games_resp = client.get('/api/games')
    kspversions_resp = client.get('/api/kspversions')
    gameversions_resp = client.get('/api/1/versions')
    mod_resp = client.get('/api/mod/1')
    mod_version_resp = client.get('/api/mod/1/latest')
    user_resp = client.get('/api/user/TestModAuthor')
    typeahead_resp = client.get('/api/typeahead/mod?game_id=1&query=Test')
    search_mod_resp = client.get('/api/search/mod?query=Test&page=1')
    search_user_resp = client.get('/api/search/user?query=Test&page=0')

    # Assert
    assert mod_resp.status_code == status.HTTP_200_OK, 'Request should succeed'
    check_mod(mod_resp.json)
    # Not returned by all APIs
    assert mod_resp.json['description'] == 'A mod that we will use to test the API', 'Short description should match'

    assert kspversions_resp.status_code == status.HTTP_200_OK, 'Request should succeed'
    check_game_version(kspversions_resp.json[0])

    assert gameversions_resp.status_code == status.HTTP_200_OK, 'Request should succeed'
    check_game_version(gameversions_resp.json[0])

    assert games_resp.status_code == status.HTTP_200_OK, 'Request should succeed'
    check_game(games_resp.json[0])

    assert publishers_resp.status_code == status.HTTP_200_OK, 'Request should succeed'
    check_publisher(publishers_resp.json[0])

    assert mod_version_resp.status_code == status.HTTP_200_OK, 'Request should succeed'
    check_mod_version(mod_version_resp.json)

    assert user_resp.status_code == status.HTTP_200_OK, 'Request should succeed'
    check_user(user_resp.json)

    assert typeahead_resp.status_code == status.HTTP_200_OK, 'Request should succeed'
    check_mod(typeahead_resp.json[0])

    assert search_mod_resp.status_code == status.HTTP_200_OK, 'Request should succeed'
    check_mod(search_mod_resp.json[0])

    assert search_user_resp.status_code == status.HTTP_200_OK, 'Request should succeed'
    check_user(search_user_resp.json[0])


def check_publisher(publisher_json: Dict[str, Any]) -> None:
    assert publisher_json['id'] == 1, 'Publisher id should match'
    assert publisher_json['name'] == 'SQUAD', 'Publisher name should match'


def check_game(game_json: Dict[str, Any]) -> None:
    assert game_json['id'] == 1, 'Game id should match'
    assert game_json['name'] == 'Kerbal Space Program', 'Game name should match'


def check_game_version(game_version_json: Dict[str, Any]) -> None:
    assert game_version_json['id'] == 1, 'Game version id should match'
    assert game_version_json['friendly_version'] == '1.2.3', 'Game version should match'


def check_mod(mod_json: Dict[str, Any]) -> None:
    assert mod_json['name'] == 'Test Mod', 'Name should match'
    assert mod_json['id'] == 1, 'ID number should match'
    assert mod_json['short_description'] == 'A mod for testing', 'Short description should match'
    assert mod_json['author'] == 'TestModAuthor', 'Author should match'
    assert mod_json['license'] == 'MIT', 'License should match'
    assert mod_json['followers'] == 0, 'Should have no followers'
    assert mod_json['versions'][0]['friendly_version'] == '1.0.0.0', 'Version should match'
    assert mod_json['versions'][0]['game_version'] == '1.2.3', 'Game version should match'


def check_mod_version(mod_version_json: Dict[str, Any]) -> None:
    assert mod_version_json['friendly_version'] == '1.0.0.0', 'Version should match'
    assert mod_version_json['game_version'] == '1.2.3', 'Game version should match'
    assert mod_version_json['download_path'] == '/mod/1/Test%20Mod/download/1.0.0.0', 'Download should match'


def check_user(user_json: Dict[str, Any]) -> None:
    assert user_json['username'] == 'TestModAuthor', 'Username should match'
    assert user_json['description'] == 'Test author of a test mod', 'Description should match'
    assert user_json['forumUsername'] == 'TestForumUser', 'Forum name should match'
    assert user_json['mods'][0]['name'] == 'Test Mod', 'Mod should be returned'
