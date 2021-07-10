import json
from typing import Tuple, List, Union, Optional

from flask import Blueprint, render_template, url_for, abort, redirect, request
from flask_login import current_user
from sqlalchemy import desc, or_
import werkzeug.wrappers

from ..common import loginrequired, with_session, get_game_info, paginate_query
from ..database import db
from ..objects import Mod, ModList, ModListItem, Game

lists = Blueprint('lists', __name__, template_folder='../../templates/lists')


def _get_mod_list(list_id: str) -> Tuple[ModList, Game, bool]:
    mod_list = ModList.query.get(list_id)
    if not mod_list:
        abort(404)
    ga = Game.query.get(mod_list.game_id)
    editable = False
    if current_user:
        if current_user.admin:
            editable = True
        if current_user.id == mod_list.user_id:
            editable = True
    return mod_list, ga, editable


@lists.route("/packs", defaults={'gameshort': None})
@lists.route("/packs/<gameshort>")
def packs(gameshort: Optional[str]) -> str:
    game = None if not gameshort else get_game_info(short=gameshort)
    query = ModList.query \
        .filter(ModList.mods.any()) \
        .order_by(desc(ModList.created))
    if game:
        query = query.filter(ModList.game_id == game.id)
    packs, page, total_pages = paginate_query(query, 9)
    return render_template("packs.html", ga=game, game=game, packs=packs, page=page, total_pages=total_pages)


@lists.route("/create/pack")
def create_list() -> str:
    games = Game.query.filter(Game.active == True).order_by(desc(Game.id)).all()
    ga = Game.query.order_by(desc(Game.id)).first()
    return render_template("create_list.html", games=games, ga=ga)


@lists.route("/pack/<int:list_id>/delete")
@loginrequired
@with_session
def delete(list_id: str) -> werkzeug.wrappers.Response:
    mod_list = ModList.query.get(list_id)
    if not mod_list:
        abort(404)
    editable = False
    if current_user:
        if current_user.admin:
            editable = True
        if current_user.id == mod_list.user_id:
            editable = True
    if not editable:
        abort(403)
    db.delete(mod_list)
    db.commit()
    return redirect("/profile/" + current_user.username)


@lists.route("/pack/<list_id>/<list_name>")
def view_list(list_id: str, list_name: str) -> str:
    mod_list, ga, editable = _get_mod_list(list_id)
    return render_template("mod_list.html",
                           **{
                               'mod_list': mod_list,
                               'editable': editable,
                               'ga': ga
                           })


@lists.route("/pack/<list_id>/<list_name>/edit", methods=['GET', 'POST'])
@with_session
@loginrequired
def edit_list(list_id: str, list_name: str) -> Union[str, werkzeug.wrappers.Response]:
    mod_list, ga, editable = _get_mod_list(list_id)
    if not editable:
        abort(403)
    if request.method == 'GET':
        return render_template("edit_list.html",
                               **{
                                   'mod_list': mod_list,
                                   'mod_ids': [m.mod.id for m in mod_list.mods],
                                   'ga': ga
                               })
    else:
        name = request.form.get('name', '')
        description = request.form.get('description')
        background = request.form.get('background')
        bgOffsetY = request.form.get('bg-offset-y', 0)
        mods = json.loads(request.form.get('mods', ''))
        if not name or len(name) > 100:
            abort(400)
        if any(mod_list.game != Mod.query.get(mod_id).game for mod_id in mods):
            # The client validates this in a more friendly way,
            # we just need to make sure nobody bypasses it
            abort(400)
        mod_list.name = name
        mod_list.description = description
        if background and background != '':
            mod_list.background = background
        try:
            mod_list.bgOffsetY = int(bgOffsetY)
        except:
            pass
        # Remove mods
        removed_mods = [m for m in mod_list.mods if not m.mod_id in mods]
        for mod in removed_mods:
            mod_list.mods.remove(mod)

        # Add mods
        added_mods = [m for m in mods if not m in [mod.mod.id for mod in mod_list.mods]]
        for m in added_mods:
            mod = Mod.query.get(m)
            mli = ModListItem()
            mli.mod_id = mod.id
            mli.mod_list = mod_list
            mod_list.mods.append(mli)
            db.add(mli)
            db.commit()
        for mod in mod_list.mods:
            mod.sort_index = mods.index(mod.mod.id)
        return redirect(url_for("lists.view_list", list_id=mod_list.id, list_name=mod_list.name))
